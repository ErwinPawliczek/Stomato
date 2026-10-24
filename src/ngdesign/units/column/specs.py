"""Mesh driver and the bounded spec secant over the column tears (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file: converge the
MESH at given tear values (inside-out with the Naphtali-Sandholm fallback),
report duties, and drive the column specs onto their targets.
"""

from __future__ import annotations

import math
from typing import Any

from .inside_out import (
    _Column,
    _exact_residuals,
    _finalize_duties,
    _inner_solve,
    _InnerModel,
    _l_profile,
    _Profile,
    _refresh_model,
    _seed_profile,
    _temperature_seed,
    _vapour_tear_stages,
    bisect_feed_phase,
)
from .linalg import _gauss
from .naphtali_sandholm import _naphtali_sandholm
from .spec import (
    _BAND_LIMIT_EPS,
    _FLOW_FLOOR,
    _MESH_H_TOL,
    _MESH_M_TOL,
    _MESH_M_TOL_REACTIVE,
    _MESH_M_TOL_ZERO_ONE_TEAR,
    _NS_FLOOR_M,
    _OUTER_DAMP,
    _OUTER_DAMP_ZERO_ONE,
    _OUTER_MAX,
    _POLISH_M_TOL_ZERO_ONE_TEAR,
    _SPEC_MAX,
    _SPEC_TOL,
    _STAGNATION_MAX,
    _STAGNATION_MAX_ZERO_ONE_TEAR,
    ColumnConvergenceError,
    ColumnSpecError,
    _is_reactive_package,
    _Params,
)
from .thermo_adapter import _flash_ready, _ThermoBox

# --------------------------------------------------------------------------------------
# Mesh driver and duty reporting
# --------------------------------------------------------------------------------------


def _apply_tears(col: _Column, prof: _Profile, t_top: float | None, t_bot: float | None) -> None:
    """Write the tear values into the profile (reflux, distillate vapour, boilup).

    Only what IS a tear gets written (spec B): the vapour-tear stages come from
    the shared helper - a partial condenser's V_1 and a kettle's V_N - and a
    total condenser's tear is the reflux L_0 above stage 1. A configuration
    without the hardware leaves that stage flow to its enthalpy balance.
    """
    if col.condenser == "total":
        prof.l0 = max(t_top, _FLOW_FLOOR) if t_top is not None else prof.l0
    else:
        prof.l0 = 0.0
        if 0 in _vapour_tear_stages(col) and t_top is not None:
            prof.V[0] = max(t_top, _FLOW_FLOOR)
    if col.n - 1 in _vapour_tear_stages(col) and t_bot is not None:
        prof.V[col.n - 1] = max(t_bot, _FLOW_FLOOR)


def _reject_band_limit(col: _Column, prof: _Profile) -> None:
    """A profile sitting on the temperature band is a failed mesh, not a solution.

    ``t_band_lo``/``t_band_hi`` are the walk's trust region (spec C), never an
    operating point: a stage clamped at the limit means the correlation drove
    the temperature out of the two-phase window and the clamp caught it. The
    P1-09 review found the 4-stage C1/nC4 stripper "converging" with every stage
    at the 270 K floor (spec P1-10 records the branch map); accepting that would
    pin unphysical columns into the results. Raises the typed error naming the
    stages so the spec layer treats it like any other non-convergence.
    """
    if col.n_tears >= 2:
        # Two-tear columns keep their benchmarked behaviour untouched (the
        # deethanizer mesh test rides the band at fixed tears today); extending
        # the guard there is measured under spec P1-10, not here.
        return
    pinned = [
        j + 1
        for j, t in enumerate(prof.T)
        if abs(t - col.t_band_lo) <= _BAND_LIMIT_EPS or abs(t - col.t_band_hi) <= _BAND_LIMIT_EPS
    ]
    if pinned:
        raise ColumnConvergenceError(
            f"mesh accepted a profile on the temperature band limit (stages {pinned} at "
            f"{col.t_band_lo:.2f}/{col.t_band_hi:.2f} K): the band is a trust region, not a solution"
        )


#: Heat-of-reaction continuation ladder for cold reactive zero/one-tear mesh
#: solves (P1-11 R1, ruling on #153).  Measured justification: with the exact-
#: residual Jacobian (seeds evaluated at each trial state), Naphtali–Sandholm
#: still cannot close the exothermic absorber directly - cold, the first pass's
#: damped solves go singular; warm, the max-norm acceptance trades M blow-ups
#: for a ~5 %/pass H crawl that stalls near 0.02 after 29 passes, far from the
#: 1e-2 gate.  The ladder warm-chains converged profiles across heat-scale
#: fractions so each step's energy shift (~0.026 normalized at 0.25) is inside
#: NS's measured warm-descent reach.  Generic: it drives whatever heat-scale
#: capability the thermo instance exposes and is a no-op without one.
_CONTINUATION_SCALES: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


def _solve_mesh(
    col: _Column,
    tb: _ThermoBox,
    t_top: float | None,
    t_bot: float | None,
    seed: _Profile | None,
    allow_fallback: bool = True,
) -> _Profile:
    """Mesh entry: dispatch cold reactive zero/one-tear solves to the continuation.

    A cold solve (``seed is None``) on a reactive zero/one-tear column walks the
    thermo's ``_heat_scale`` capability up ``_CONTINUATION_SCALES``, warm-chaining
    each converged profile into the next step; everything else (warm seeds,
    two-tear columns, packages without the capability) solves directly at the
    current scale, byte-identical to the un-continued path.
    """
    thermo = getattr(tb, "_thermo", tb)
    if col.n_tears < 2 and seed is None and _is_reactive_package(tb) and hasattr(thermo, "_heat_scale"):
        original = thermo._heat_scale
        prof: _Profile | None = None
        try:
            for scale in _CONTINUATION_SCALES:
                thermo._heat_scale = scale
                prof = _solve_mesh_at_heat(col, tb, t_top, t_bot, prof, allow_fallback)
            assert prof is not None
            return prof
        finally:
            thermo._heat_scale = original
    return _solve_mesh_at_heat(col, tb, t_top, t_bot, seed, allow_fallback)


def _solve_mesh_at_heat(
    col: _Column,
    tb: _ThermoBox,
    t_top: float | None,
    t_bot: float | None,
    seed: _Profile | None,
    allow_fallback: bool = True,
) -> _Profile:
    """Converge the MESH equations at given tear values: inside-out, NS fallback.

    The stagnation patience and the stage-level M gate follow the configuration
    (spec D): two-tear columns keep the original 1e-8 gate and patience-3;
    zero/one-tear columns use their own named constants - spec.py records the
    measured justification for each. A relaxed M gate is acceptable there
    because the boundary-stream overall balances (what users read) close at
    machine precision regardless; the stage-level floor is the inside-out Kb
    correlation's noise.
    """
    zero_one = col.n_tears < 2
    if zero_one and _is_reactive_package(tb):
        m_tol = _MESH_M_TOL_REACTIVE
    elif zero_one:
        m_tol = _MESH_M_TOL_ZERO_ONE_TEAR
    else:
        m_tol = _MESH_M_TOL
    patience = _STAGNATION_MAX_ZERO_ONE_TEAR if zero_one else _STAGNATION_MAX
    prof: _Profile | None = None
    if seed is None:
        t_top_seed, t_bot_seed = _temperature_seed(col, tb)
        prof = _seed_profile(col, tb, t_top_seed, t_bot_seed, v_bot_tear=t_bot)
    else:
        # Copy: the sweep loop mutates the profile in place, and a failed mesh
        # must not corrupt the seed the spec layer warm-starts from.
        prof = _copy_profile(col, seed)
    _apply_tears(col, prof, t_top, t_bot)
    model: _InnerModel | None = None
    stalled = 0
    best_prof: _Profile | None = None
    best_m = float("inf")
    best_h = float("inf")
    if zero_one:
        # Never hand the fallback a state worse than the one it was given: a
        # warm seed (the secant's last converged profile, re-teared) is already
        # near-converged, but the first inside-out sweeps can wander off it.
        # Measured P1-10 stripper on the physical branch warm from V=41: the
        # sweeps drove exact M to 1e-10 while H drifted to 1e-1, and the
        # Naphtali-Sandholm fallback started from that wandered state and
        # stalled at every neighbouring tear - while starting NS from the
        # incoming state itself converges in a few passes at every tear
        # 24-48 (each ~0.2 s). Two-tear columns keep the original loop
        # untouched: their benchmarked mesh sequence is locked (bench 4,959).
        best_m, best_h = _exact_residuals(col, tb, prof)
        best_prof = _copy_profile(col, prof)
    ns_direct = False
    ns_floor = False
    if (
        zero_one
        and not _is_reactive_package(tb)
        and (seed is not None or (col.n_tears == 1 and col.reboiler == "kettle"))
    ):
        # Naphtali-Sandholm FIRST for non-reactive zero/one-tear columns:
        # - warm (a promoted seed exists): NS from the re-teared seed converges
        #   in ~0.2 s at every neighbouring kettle tear (measured P1-10, V=24-76
        #   from the V=41 physical profile), while the sweep loop first wanders
        #   off the seed (M closes to 1e-10 while H drifts to 1e-1) and NS
        #   started from that wandered state stalls. The best-state tracker
        #   cannot rescue this: the wandered state can beat the seed on the
        #   M+H sum while being a worse NS start.
        # - cold (no seed): one-tear kettle strippers only (measured P1-10
        #   E-NSCOLD: NS from the crude hot-bottom seed converges outright at
        #   every tear V=24-48 mol/s in 0.2-0.3 s; the inside-out loop from the
        #   same seed reaches the band-floor branch at most tears). Absorbers
        #   (zero tears) keep the inside-out loop - their measured P1-09 sweep
        #   sequence is locked, and NS is measurably worse there on reactive
        #   packages. Two-tear columns keep the original loop untouched: their
        #   benchmarked mesh sequence is locked (bench 4,959).
        try:
            _naphtali_sandholm(col, tb, prof, t_bot)
            ns_direct = True
        except ColumnConvergenceError:
            # NS may raise at its finite-difference floor while holding a
            # physically converged state (measured P1-10 stripper: M = 4.2e-6
            # - 7.3e-6 against the 1e-6 gate, with the boundary total balance
            # closed at D + B = 100.00000000 on a 100 mol/s feed; a stalled
            # state sits at 1e-2 or worse). Keep that state for the polish
            # stage below; otherwise restart from the untouched seed.
            if _at_ns_floor(col, tb, prof):
                ns_floor = True
            elif seed is None:
                t_top_seed, t_bot_seed = _temperature_seed(col, tb)
                prof = _seed_profile(col, tb, t_top_seed, t_bot_seed, v_bot_tear=t_bot)
                _apply_tears(col, prof, t_top, t_bot)
            else:
                prof = _copy_profile(col, seed)
                _apply_tears(col, prof, t_top, t_bot)
    if ns_direct or ns_floor:
        # The sweeps can only wander off a near-converged NS state, so the
        # inside-out loop is skipped entirely; the polish stage below still
        # runs and its gate decides acceptance.
        best_prof = _copy_profile(col, prof)
    for outer in range(1, 1 if (ns_direct or ns_floor) else _OUTER_MAX + 1):
        t_prev, v_prev = list(prof.T), list(prof.V)
        model = _refresh_model(col, tb, prof, model)
        prof.outer = outer
        _inner_solve(col, model, prof, t_bot)  # accumulates prof.inner itself
        if col.n_tears >= 2:
            # Feedback damping between sweeps on temperature and vapour profiles:
            # the frozen-model update overshoots near unstable tears. Two-tear
            # columns only - their seed is a real distillation profile. A
            # zero/one-tear column's feed-traffic seed is crude, and the
            # half-step back toward it stalled wide absorbers in a limit cycle
            # (measured, P1-09: the 8-stage absorber froze at M=1.2e-3 over
            # 9 sweeps; undamped it closes at sweep 2 with M=8.8e-11).
            for j in range(col.n):
                prof.T[j] = t_prev[j] + _OUTER_DAMP * (prof.T[j] - t_prev[j])
                prof.V[j] = v_prev[j] + _OUTER_DAMP * (prof.V[j] - v_prev[j])
        elif _OUTER_DAMP_ZERO_ONE < 1.0:
            for j in range(col.n):
                prof.T[j] = t_prev[j] + _OUTER_DAMP_ZERO_ONE * (prof.T[j] - t_prev[j])
                prof.V[j] = v_prev[j] + _OUTER_DAMP_ZERO_ONE * (prof.V[j] - v_prev[j])
        prof.L = _l_profile(col, prof.l0, prof.V)
        m_res, h_res = _exact_residuals(col, tb, prof)
        if m_res < m_tol and h_res < _MESH_H_TOL:
            _reject_band_limit(col, prof)
            _finalize_duties(col, tb, prof)
            return prof
        # Stagnation = NO improvement in either residual for 3 consecutive
        # sweeps. Early sweeps wobble in mass while enthalpy still improves
        # monotonically; a single combined metric misreads that as stagnation
        # and hands a healthy iteration to the fallback.
        if m_res < best_m or h_res < best_h:
            stalled = 0
            if best_prof is None or m_res + h_res < best_m + best_h:
                best_prof, best_m, best_h = _copy_profile(col, prof), m_res, h_res
        else:
            stalled += 1
            if stalled >= patience:
                break
    # The inside-out loop stalled or exhausted its budget: hand the best profile
    # to the Naphtali-Sandholm Newton fallback, which polishes from there.
    # Retreat probes skip the fallback: a candidate tear only needs the
    # inside-out verdict, and a full NS run per failing candidate costs tens of
    # seconds (measured P1-09 stripper retreat ladder).
    if best_prof is not None:
        prof = _copy_profile(col, best_prof)
    if not allow_fallback and not (ns_direct or ns_floor):
        # Probe verdict path: only an UNCONVERGED inside-out loop without NS
        # success raises here; a converged NS-first state falls through to the
        # polish gate below (the NS-first attempt runs even in probes - one-tear
        # kettles only, measured 0.2-0.3 s per call).
        raise ColumnConvergenceError(
            f"inside-out mesh did not converge at tears {(t_top, t_bot)} "
            f"(best residuals M={best_m:.2e}, H={best_h:.2e})"
        )
    if not (ns_direct or ns_floor):
        try:
            _naphtali_sandholm(col, tb, prof, t_bot)
        except ColumnConvergenceError as exc:
            # NS may raise at its finite-difference floor while holding a
            # physically converged state (measured P1-10 stripper, kettle
            # vapour 50-76 mol/s on the physical branch: NS exits at
            # M = 4.2e-6 - 5.6e-6 against the 1e-6 gate, with the boundary
            # total balance closed at D + B = 100.00000000 on a 100 mol/s
            # feed). Non-reactive zero/one-tear columns hand that state to the
            # polish below; everything else, and a genuinely stalled state
            # (measured stalls sit at M >= 1e-2), is a failure.
            polishable = not _is_reactive_package(tb)
            if not (polishable and _at_ns_floor(col, tb, prof)):
                raise ColumnConvergenceError(
                    f"column did not converge in {_OUTER_MAX} inside-out sweeps and the "
                    f"Naphtali-Sandholm fallback failed after {prof.ns_passes} passes: {exc} "
                    f"(best inside-out profile residuals M={best_m:.2e}, H={best_h:.2e} over "
                    f"{prof.outer} outer sweeps, {prof.inner} inner iterations)"
                ) from exc
    if zero_one and not _is_reactive_package(tb):
        # NS globalizes; the inside-out polishes. NS's finite-difference Newton
        # floors at M=3.9e-8 (measured P1-09 absorber: passes 20-30 stagnant),
        # while the anchored-correlation inside-out closes to machine precision
        # from a near-converged state (measured N=2/N=4: M ~ 1e-10). Warm-start
        # sweeps lift the solution the last two decades onto the strict gate.
        model = None
        stalled = 0
        m_ns, h_ns = _exact_residuals(col, tb, prof)
        pol_m, pol_h = m_ns, h_ns
        best_prof = _copy_profile(col, prof)
        for outer in range(1, _OUTER_MAX + 1):
            model = _refresh_model(col, tb, prof, model)
            prof.outer = outer
            _inner_solve(col, model, prof, t_bot)
            m_pol, h_pol = _exact_residuals(col, tb, prof)
            if m_pol < _POLISH_M_TOL_ZERO_ONE_TEAR and h_pol < _MESH_H_TOL:
                break
            if m_pol + h_pol < pol_m + pol_h:
                stalled = 0
                pol_m, pol_h = m_pol, h_pol
                best_prof = _copy_profile(col, prof)
            else:
                stalled += 1
                if stalled >= _STAGNATION_MAX_ZERO_ONE_TEAR:
                    break
        # Whatever the polish did, hand back the best state seen: the sweeps
        # mutate the profile in place, and a diverging polish sweep must never
        # displace the NS solution it started from.
        prof = _copy_profile(col, best_prof)
        # If the polish stalls, the NS state stands: its floor is the measured
        # solver limit (named in _MESH_M_TOL_ZERO_ONE_TEAR), and the boundary
        # overall balances close far tighter than the stage residual.
    _reject_band_limit(col, prof)
    _finalize_duties(col, tb, prof)
    return prof


def _at_ns_floor(col: _Column, tb: _ThermoBox, prof: _Profile) -> bool:
    """True when a Naphtali-Sandholm exit left a physically converged state.

    NS raises at its finite-difference Newton floor (spec P1-10, measured
    M = 4e-6 - 7e-6 against the 1e-6 gate with the boundary total balance
    closed at D + B = 100.00000000 on a 100 mol/s feed); a stalled state sits
    at M >= 1e-2. The bound is _NS_FLOOR_M.
    """
    m_ns, h_ns = _exact_residuals(col, tb, prof)
    return m_ns < _NS_FLOOR_M and h_ns < _MESH_H_TOL


def _copy_profile(col: _Column, src: _Profile) -> _Profile:
    """Deep-copy a profile: lists and per-stage composition dicts are mutable."""
    return _Profile(
        T=list(src.T),
        V=list(src.V),
        L=list(src.L),
        x=[dict(c) for c in src.x],
        y=[dict(c) for c in src.y],
        l0=src.l0,
        d=src.d,
        b=src.b,
        qc=src.qc,
        qr=src.qr,
        outer=src.outer,
        inner=src.inner,
        ns_used=src.ns_used,
        ns_passes=src.ns_passes,
        ns_trace=list(src.ns_trace),
    )


def _initial_tears(col: _Column, params: _Params) -> tuple[float | None, float | None]:
    """Starting guesses for the tear flows that exist; None for absent hardware.

    Plain fractions of the feed: the spec secant moves them, the mesh converges
    from any sane start, and elaborate temperature-based seeds bought nothing.
    The top tear is the reflux for a total condenser and the stage-1 vapour for
    a partial condenser; the bottom tear is the kettle boilup (mol/s). A
    configuration without the hardware carries no tear there - its stage flow
    is an outcome of the enthalpy balance, never a guessable input (spec B).
    """
    t_top: float | None = 0.5 * col.f_total if col.condenser != "none" else None
    t_bot: float | None = None
    if col.reboiler == "kettle":
        if col.n_tears < 2:
            # Configuration-aware boilup guess: the kettle's liquid supply is the
            # LIQUID feed traffic, not the whole feed. The ratio spec is
            # V_kettle/bottoms, so with L_in the liquid traffic the feasible
            # boilup is r*L_in/(1+r); the two-tear guess 0.8*F sits above a
            # stripper's L_in by the entire feed vapour and makes the mesh
            # mass-infeasible at the very first secant point (measured P1-09:
            # 60 mol/s feed, 14.7 mol/s liquid, boilup guessed 48 - stage
            # liquid traffic went negative and the mesh could never close).
            liq_in = sum(part.l_flow for part in col.feeds)
            ratio = params.specs.get("boilup_ratio")
            if ratio is not None:
                r = float(ratio)
            elif any(key == "component_recovery" for key in params.specs):
                # Recovery specs have no ratio to read; the 0.8 default lands the
                # P1-10 stripper at V=79.5 - inside the 78-82 collapse zone where
                # NS stalls (M~0.96 from the crude seed) and the sweeps return
                # wrong-root profiles with PLATEAUED recovery (the secant Jacobian
                # then reads singular on the first iteration). Start inside the
                # NS-converging window instead: the recovery secant walks UP the
                # physical branch from here (damped steps; the measured branch
                # spans V=41-88 with recovery 0.86-0.97).
                r = 0.45
            else:
                r = 0.8
            # The no-recycle ratio-exact guess r*L/(1+r) sits BELOW the true
            # feasible window: the rising vapour partially condenses on its way
            # up, inflating the kettle's liquid supply (measured P1-09 stripper:
            # the ratio-exact 6.54 fails, the walk opens at ~7 and closes at
            # ~12, with boilup ratio 0.8 reachable near 9.6). The mass-feasible
            # upper bound min(r, 0.95)*L_in keeps the guess inside the window;
            # the spec secant refines from there.
            t_bot = min(r, 0.95) * liq_in
        else:
            t_bot = 0.8 * col.f_total
    if col.condenser == "total" and col.n_tears < 2 and "reflux_ratio" in params.specs:
        # Same reasoning for the one-tear rectifier: the reflux divides the
        # overhead vapour (the vapour feed traffic), l0 = RR*V/(1+RR); the
        # 0.5*F guess can exceed the overhead vapour and force a negative
        # distillate on liquid-rich feeds.
        vap_in = sum(part.v_flow for part in col.feeds)
        rr = float(params.specs["reflux_ratio"])
        t_top = rr * vap_in / (1.0 + rr)
    return t_top, t_bot


def _fenske_alpha(col: _Column, tb: _ThermoBox, cid: str, product: str) -> float | None:
    """Mean relative volatility of cid against its limiting reference component.

    The Fenske total-reflux bound needs the mean stage relative volatility.
    K is evaluated from real two-phase flashes just inside the feed's bubble
    and dew points at the mid column pressure - the ends of the true stage
    temperature window - and combined GEOMETRICALLY (alpha varies roughly
    exponentially with temperature along the profile). Single-phase flashes
    are useless here: the seed band ends sit OUTSIDE the two-phase envelope,
    where only the temperature-insensitive Clausius-Clapeyron Raoult estimate
    is available (measured: it returned alpha=2.49 at both ends on the C3/iC4
    case and masked an unreachable spec; the two-phase end flashes give 1.83).

    Returns None when either window end yields no two-phase flash K, or when
    the component is not the key for its product side (alpha <= 1: the Fenske
    enrichment bound does not apply to an anti-enrichment purity spec).
    """
    if cid not in col.feed_comp:
        return None
    p_mid = 0.5 * (col.pressures[0] + col.pressures[-1])
    t_bub = bisect_feed_phase(col, tb, p_mid, want_vapor=False)
    t_dew = bisect_feed_phase(col, tb, p_mid, want_vapor=True)
    alphas: list[float] = []
    for t in (t_bub + 2.0, t_dew - 2.0):
        if t <= t_bub + 1.0:
            continue  # two-phase window too narrow to sample twice
        k = tb.k_values([_flash_ready(col.feed_comp, col.feed_comp)], t, p_mid)
        if k is None or cid not in k or len(k) < 2:
            continue
        others = [v for name, v in k.items() if name != cid]
        if min(others) <= 0.0 or k[cid] <= 0.0:
            continue
        ref = min(others) if product == "distillate" else max(others)
        alpha = k[cid] / ref if product == "distillate" else ref / k[cid]
        if alpha > 1.0:
            alphas.append(alpha)
    if not alphas:
        return None
    return math.prod(alphas) ** (1.0 / len(alphas))


def _check_spec_feasibility(col: _Column, tb: _ThermoBox, params: _Params) -> None:
    """Reject provably unreachable specs BEFORE the secant/spec walk.

    An infeasible spec used to surface only after the secant had wandered into
    degenerate tear corners (measured 162 s on the 0.999-purity case). Each
    check here rejects only what is unreachable even at total reflux - the
    maximum-separation limit of any finite column - and is deliberately
    permissive near its own boundary:

    - distillate/bottoms rates: the [0, available-feed] window is enforced in
      ``_parse_params`` (the draw-room check); nothing left to add here.
    - product purity: Fenske at total reflux (Fenske, Ind. Eng. Chem. 24:482,
      1932). The most favorable split (vanishing opposite product) needs
      separation factor S = p/(1-p) * (1-z)/z for a distillate purity p of a
      component at feed fraction z, and S = p/(1-p) * z/(1-z) for a bottoms
      purity. A column with N stages delivers at most S_max = alpha^N; if
      S_max < S the target is unreachable even at total reflux.
    - component recovery: r <= alpha^N / (1 + alpha^N) at total reflux, from
      the Fenske pair relation d_i/b_i = alpha^N with the limiting reference
      component overwhelmingly reporting to the other product (same permissive
      bias as the purity bound).
    - reflux/boilup ratios: positivity is enforced in ``_parse_params``; the
      meaningful lower bound (R > R_min) has no cheap closed form and is the
      secant bracket abort's job (see ``_solve_specs``).
    """
    for key, target_d in params.specs.items():
        if key not in ("product_purity", "component_recovery"):
            continue
        comp = str(target_d["component"])
        product = str(target_d.get("product", "distillate"))
        value = float(target_d["value"])
        alpha = _fenske_alpha(col, tb, comp, product)
        if alpha is None:
            continue
        s_max = alpha**col.n
        if key == "component_recovery":
            r_max = s_max / (1.0 + s_max)
            if value > r_max:
                raise ColumnSpecError(
                    f"specs.{key} {value} exceeds the total-reflux recovery limit {r_max:.4g} "
                    f"(alpha={alpha:.3g} over {col.n} stages); the specification is infeasible"
                )
            continue
        z = col.feed_comp.get(comp, 0.0)
        if not 0.0 < z < 1.0:
            continue
        if product == "distillate":
            s_need = (value / (1.0 - value)) * ((1.0 - z) / z)
        else:
            s_need = (value / (1.0 - value)) * (z / (1.0 - z))
        if s_max < s_need:
            n_min = math.ceil(math.log(s_need) / math.log(alpha))
            raise ColumnSpecError(
                f"specs.{key} {value} of {comp!r} in the {product} needs at least {n_min} "
                f"equilibrium stages at TOTAL reflux (alpha={alpha:.3g}); this column has "
                f"{col.n}, so the specification is infeasible"
            )


def _spec_g(col: _Column, params: _Params, prof: _Profile, skip: set[str]) -> tuple[list[float], list[float]]:
    """Raw spec residuals and their scales; the secant drives rel = g / scale to zero."""
    g: list[float] = []
    scales: list[float] = []
    for key, raw_target in params.specs.items():
        if key in skip:
            continue
        if key in ("component_recovery", "product_purity"):
            target_d: dict[str, Any] = raw_target
            comp = str(target_d["component"])
            value = float(target_d["value"])
            is_dist = str(target_d.get("product", "distillate")) == "distillate"
            out_frac = (prof.y[0] if is_dist else prof.x[col.n - 1]).get(comp, 0.0)
            if key == "product_purity":
                g.append(out_frac - value)
            else:
                out_flow = prof.d if is_dist else prof.b
                feed_frac = col.feed_comp.get(comp, 0.0) * col.f_total
                measured = out_flow * out_frac / max(feed_frac, _FLOW_FLOOR)
                g.append(measured - value)
            scales.append(max(value, 1e-12))
            continue
        target = float(raw_target)
        if key == "reflux_ratio":
            g.append(prof.l0 / max(prof.d, _FLOW_FLOOR) - target)
        elif key == "boilup_ratio":
            g.append(prof.V[col.n - 1] / max(prof.b, _FLOW_FLOOR) - target)
        elif key == "distillate_rate":
            g.append(prof.d - target)
        elif key == "bottoms_rate":
            g.append(prof.b - target)
        elif key == "condenser_duty_W":
            g.append(prof.qc - target)
        elif key == "reboiler_duty_W":
            g.append(prof.qr - target)
        else:  # pragma: no cover - _parse_params rejects unknown keys
            raise ColumnSpecError(f"unsupported spec {key!r}")
        scales.append(max(target, 1e-12))
    return g, scales


def _solve_specs(col: _Column, tb: _ThermoBox, params: _Params) -> _Profile:
    """Drive the column specs onto their targets: bounded secant over the tears.

    Ratio-plus-rate pairs (reflux_ratio + distillate_rate and friends) pin the
    corresponding tear algebraically - l0 = R*D etc. - leaving a one-dimensional
    secant in the remaining tear. The mesh vapour profile barely responds to the
    reflux tear, so the full 2-D system is near-singular; the pinned ratio's
    residual is satisfied by construction and dropped. A spec that pins a tear
    directly (distillate_rate on a partial condenser) is applied as a constant.
    """
    _check_spec_feasibility(col, tb, params)
    t_top, t_bot = _initial_tears(col, params)
    specs = params.specs
    d_spec = specs.get("distillate_rate")
    b_spec = specs.get("bottoms_rate")
    r_spec = specs.get("reflux_ratio")
    vb_spec = specs.get("boilup_ratio")
    draw_total = sum(dr.flow for dr in params.draws if dr.flow is not None)
    pin_top = False
    pin_bot = False
    skip: set[str] = set()
    if col.condenser == "total" and r_spec is not None and d_spec is not None:
        t_top = float(r_spec) * float(d_spec)
        pin_top = True
        skip.add("reflux_ratio")
    elif col.condenser == "total" and r_spec is not None and b_spec is not None:
        t_top = float(r_spec) * max(col.f_total - float(b_spec) - draw_total, _FLOW_FLOOR)
        pin_top = True
        skip.add("reflux_ratio")
    if col.reboiler == "kettle" and vb_spec is not None and d_spec is not None:
        t_bot = float(vb_spec) * max(col.f_total - float(d_spec) - draw_total, _FLOW_FLOOR)
        pin_bot = True
        skip.add("boilup_ratio")
    elif col.reboiler == "kettle" and vb_spec is not None and b_spec is not None:
        t_bot = float(vb_spec) * float(b_spec)
        pin_bot = True
        skip.add("boilup_ratio")
    if col.condenser == "partial" and d_spec is not None:
        t_top = float(d_spec)
        pin_top = True
        skip.add("distillate_rate")
    if col.n_tears < 2 and col.condenser == "total" and d_spec is not None and not pin_top:
        # A total condenser's distillate-rate spec drives the reflux tear: the
        # overhead draw satisfies d = V0 - l0, so the secant walks l0 until the
        # mesh's own distillate matches the spec (spec B: the reflux IS this
        # configuration's top tear). Two-tear columns keep their original
        # both-tears-free secant and its benchmarked mesh sequence.
        t_top = max(float(col.f_total) - float(d_spec), _FLOW_FLOOR)
        free_top = True
    free_top = t_top is not None and not pin_top
    free_bot = t_bot is not None and not pin_bot
    if col.condenser == "total" and pin_top and free_bot and t_top is not None:
        # Seed the first mesh at high vapour traffic: a fully-boiling column has
        # every stage two-phase and the mesh converges robustly there; the warm-
        # started secant then walks the kettle tear down to the specification.
        t_bot = t_top + col.f_total * 0.2

    state: dict[str, _Profile | None] = {"seed": None, "seed2": None}

    # Tears the last successful mesh_at call ACTUALLY solved. The geometric
    # retreat and the warm restart can return a profile at a shifted tear; the
    # secant must know where its residual came from (see the rebase below).
    actual: dict[str, float | None] = {"top": None, "bot": None}

    def solved_tears(prof: _Profile) -> _Profile:
        """Record the tears a returned profile actually solved, then pass it through."""
        if col.condenser == "total":
            actual["top"] = prof.l0
        elif col.condenser == "partial":
            actual["top"] = prof.V[0]
        else:
            actual["top"] = None
        actual["bot"] = prof.V[col.n - 1] if col.reboiler == "kettle" else None
        return prof

    def promote(prof: _Profile) -> None:
        """Store a converged profile as the restart seed, demoting the old one.

        Warm restart basins are DIRECTIONAL (measured P1-09 stripper: the
        37.5 mol/s tear converges warm from the V=40 floor seed but fails from
        the V=37.15 seed below it), so the second-most-recent seed is kept as a
        second restart option - it usually comes from the other side of a
        failing tear band.
        """
        state["seed2"] = state["seed"]
        state["seed"] = _copy_profile(col, prof)

    def mesh_at(top: float | None, bot: float | None, probe: bool = False) -> _Profile:
        """Solve the mesh at given tears, retreating toward the seed on failure.

        Two-tear columns keep the original three-attempt backtracking only, so
        their benchmarked flash count cannot move. Zero/one-tear columns add a
        geometric retreat of the tear itself: the inside-out mesh's basin is
        irregular for feed-determined columns (measured P1-09 stripper at
        boilup ratio 0.5: candidate kettle flows 36 and 40 mol/s converge while
        33.1 and 49.7 fail), so a failing candidate is not proof of
        infeasibility - a smaller neighbour often converges and still brackets
        the specification for the secant.

        A ``probe`` call (damped-step trials and retreat candidates) runs the
        inside-out mesh ONCE with the NS fallback disabled: the candidate needs
        only the inside-out verdict, and a full NS run per failing candidate
        costs tens of seconds (measured on the P1-09 stripper).
        """
        start_top, start_bot = top, bot
        last: ColumnConvergenceError | None = None
        # Zero/one-tear columns solve every secant mesh evaluation COLD. The
        # mesh has multiple roots at one tear (measured P1-09 rectifier at
        # reflux 20.4: d=83.9 vs d=81.0 depending on the warm start), so a
        # warm-started evaluation returns whichever root the seed's basin
        # holds; the spec residual then hops between roots as the secant's
        # finite-difference probes and main line land in different basins, and
        # the Jacobian reads noise. A cold start always takes the mixed-feed
        # seed's root, making g(tear) single-valued - and the mixed-feed seed
        # keeps cold solves at 1-3 sweeps. Two-tear columns keep the warm
        # start: their benchmarked mesh sequence is locked.
        cold = col.n_tears < 2
        if probe:
            try:
                prof = _solve_mesh(col, tb, top, bot, None if cold else state["seed"], allow_fallback=False)
                promote(prof)
                return solved_tears(prof)
            except (ColumnConvergenceError, ValueError) as exc:
                # Same seed restart as the main path, inside-out only (a probe
                # must stay cheap): a cold probe failure in a scattered-basin
                # band is not the tear's verdict when a warm restart from the
                # last converged profile solves it. Both seeds are tried - warm
                # basins are directional (see promote).
                if cold:
                    for key in ("seed", "seed2"):
                        s = state[key]
                        if s is None:
                            continue
                        try:
                            prof = _solve_mesh(col, tb, top, bot, s, allow_fallback=False)
                            promote(prof)
                            return solved_tears(prof)
                        except (ColumnConvergenceError, ValueError):
                            continue
                raise ColumnConvergenceError(f"mesh probe failed at tears {(top, bot)}: {exc}") from exc
        for _attempt in range(3):
            try:
                prof = _solve_mesh(col, tb, top, bot, None if cold else state["seed"])
                promote(prof)
                return solved_tears(prof)
            except ColumnConvergenceError as exc:
                last = exc
            except ValueError as exc:
                # Unconverged iterates can leave the flash's physical domain
                # (pydantic stream validation inside the PR package). That is a
                # convergence failure of this iterate, not a caller error.
                last = ColumnConvergenceError(f"iterate left the flash domain: {exc}")
            # Seed restart (zero/one-tear columns): a cold failure at this tear
            # is not proof of infeasibility - the mixed-feed seed's basin is
            # scattered for feed-determined columns (measured P1-09 stripper,
            # boilup ratio 0.5: cold solves converge on scattered tear bands
            # 33/38-45/46-55 and fail between them, while the spec's root sits
            # at V_N ~ 44.8 mol/s, D 10.45, B 89.55 - ratio 0.5004 - inside a
            # cold-failing band). Restart the mesh AT THE SAME tears
            # warm-started from the last converged profile: its basin usually
            # contains the neighbouring tear, so the secant can walk through
            # the band instead of reading infeasibility into it.
            if cold:
                for key in ("seed", "seed2"):
                    s = state[key]
                    if s is None:
                        continue
                    try:
                        prof = _solve_mesh(col, tb, top, bot, s)
                        promote(prof)
                        return solved_tears(prof)
                    except (ColumnConvergenceError, ValueError):
                        continue
            seed = state["seed"]
            if seed is None:
                break
            if top is not None:
                # Backtrack toward the seed value of the SAME tear quantity:
                # the reflux L_0 for a total condenser, the stage-1 vapour V_1
                # for a partial condenser (its distillate draw is the tear),
                # and the boilup V_N for a kettle. A configuration without the
                # hardware has no tear there, so nothing to backtrack (spec B).
                target = seed.l0 if col.condenser == "total" else seed.V[0]
                top = top + 0.5 * (target - top)
            if bot is not None:
                bot = bot + 0.5 * (seed.V[col.n - 1] - bot)
        if col.n_tears < 2:
            for frac in (0.8, 0.64, 0.512, 0.41, 0.328, 0.262):
                try:
                    prof = mesh_at(
                        None if start_top is None else start_top * frac,
                        None if start_bot is None else start_bot * frac,
                        probe=True,
                    )
                    return prof
                except ColumnConvergenceError:
                    continue
        raise ColumnConvergenceError(f"mesh failed at tears {(top, bot)}: {last}")

    def apply_vector(v: list[float]) -> tuple[float | None, float | None]:
        """Map the free-tear vector back onto (top, bot) tears."""
        it = iter(v)
        a = next(it) if free_top else t_top
        b2 = next(it) if free_bot else t_bot
        return a, b2

    def tears_of(v: list[float]) -> tuple[float | None, float | None]:
        """Unpack the free-tear vector into concrete tears; None = absent hardware.

        A ``None`` from ``apply_vector`` is legitimate for a configuration
        without the hardware (spec B); it is a caller bug only when a FREE
        tear slot reads None - that would mean the secant is iterating a tear
        that does not exist, and must surface as a typed error.
        """
        top, bot = apply_vector(v)
        if (free_top and top is None) or (free_bot and bot is None):
            raise ColumnSpecError("column spec tears unresolved before secant solve")
        return top, bot

    x: list[float] = []
    # Separation direction per free tear slot: more reflux (total-condenser top
    # tear) and more boilup mean MORE separation; a partial-condenser distillate
    # tear is inverted (a bigger distillate draw means less refluxing).
    tear_dir: list[float] = []
    if free_top and t_top is not None:
        x.append(float(t_top))
        tear_dir.append(1.0 if col.condenser == "total" else -1.0)
    if free_bot and t_bot is not None:
        x.append(float(t_bot))
        tear_dir.append(1.0)
    if not x:
        # Zero free tears: the feeds determine the column, so one mesh solve at
        # the given tears (None for absent hardware) IS the answer - no secant
        # (spec A). Any remaining unskipped spec must already hold by
        # construction or the configuration is infeasible.
        prof = mesh_at(t_top, t_bot)
        g0, s0 = _spec_g(col, params, prof, skip)
        if not g0:
            return prof
        rel0 = [gi / s for gi, s in zip(g0, s0, strict=True)]
        if max(abs(r) for r in rel0) < _SPEC_TOL:
            return prof
        raise ColumnSpecError(
            f"column specs cannot be driven: no free tear variables remain; "
            f"residuals {[round(r, 6) for r in rel0]}"
        )

    flow_cap = 50.0 * col.f_total
    best_res = float("inf")
    # Monotone-bracket abort state: purity/recovery residuals are monotone in
    # the separation level, so if every still-unmet separation residual sits on
    # the wrong side of its target and the secant keeps stepping FURTHER from
    # the maximum-separation corner without any of them improving, both bracket
    # ends (worst and best separation explored) are on the wrong side - the
    # target is unreachable. Raise immediately instead of wandering into
    # degenerate tears (measured 162 s on the 0.999-purity case before this).
    keys = [k for k in params.specs if k not in skip]
    sep_idx = [k for k, key in enumerate(keys) if key in ("product_purity", "component_recovery")]
    best_wrong = [float("inf")] * len(sep_idx)
    flee = 0
    stale = 0
    rel: list[float] = []
    for _ in range(_SPEC_MAX):
        top, bot = tears_of(x)
        prof = mesh_at(top, bot)
        if col.n_tears < 2:
            # Retreat-honest secant: mesh_at may have solved a DIFFERENT tear
            # than requested - the geometric retreat and the warm restart both
            # return profiles at shifted tears, and the residual just read
            # belongs to the ACTUAL tear. Rebase the secant variable onto it so
            # the Jacobian measures the residual's real local slope instead of
            # comparing evaluations at two different tears. Measured P1-09
            # stripper, boilup ratio 0.3: the 29.8 mol/s initial tear retreats
            # to the V=30.0 floor solve (ratio 0.4033) and the secant read
            # g=+0.1033 from x=29.8 for six consecutive iterations - stuck.
            # Rebased, it walks the solvable window toward its root directly.
            xi = 0
            if free_top:
                if actual["top"] is not None:
                    x[xi] = actual["top"]
                xi += 1
            if free_bot and actual["bot"] is not None:
                x[xi] = actual["bot"]
        g, scales = _spec_g(col, params, prof, skip)
        rel = [gi / s for gi, s in zip(g, scales, strict=True)]
        if max(abs(r) for r in rel) < _SPEC_TOL:
            return prof
        res = max(abs(r) for r in rel)
        if res < best_res - 1e-4 * best_res:
            best_res, stale = res, 0
        else:
            stale += 1
            if stale >= 6:
                raise ColumnSpecError(
                    f"column spec residual stuck near {res:.4g} over 6 secant iterations; "
                    f"the specification is likely infeasible for this column"
                )
        jac_cols = []
        for i in range(len(x)):
            dx = max(0.02 * abs(x[i]), 1e-3 * col.f_total)
            x2 = list(x)
            x2[i] += dx
            prof2: _Profile | None = None
            # A finite-difference probe may land in an unsolvable tear region
            # long before the main line does; shrink the probe before giving up
            # on the secant entirely.
            last_probe_err: ColumnConvergenceError | None = None
            for _shrink in range(3):
                t2_top, t2_bot = tears_of(x2)
                try:
                    prof2 = mesh_at(t2_top, t2_bot)
                    break
                except ColumnConvergenceError as exc:
                    last_probe_err = exc
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
            if prof2 is None:
                raise ColumnSpecError(
                    f"spec secant cannot probe the column state (tears {apply_vector(x2)}); "
                    f"the specification is likely infeasible: {last_probe_err}"
                ) from last_probe_err
            g2, _ = _spec_g(col, params, prof2, skip)
            # Jacobian on the SAME scaled residuals the rhs uses - mixing raw
            # differences with a scaled rhs shrank rate-spec steps by the rate
            # scale (45x here) and crawled toward the target.
            rel2 = [g2i / s for g2i, s in zip(g2, scales, strict=True)]
            jac_cols.append([(rel2[k] - rel[k]) / dx for k in range(len(rel))])
        nf = len(x)
        matrix = [[jac_cols[i][k] for i in range(nf)] for k in range(nf)]
        try:
            step = _gauss(matrix, [-r for r in rel])
        except ZeroDivisionError as exc:
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {[round(r, 6) for r in rel]}"
            ) from exc
        if any(abs(v) > flow_cap for v in step):
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {[round(r, 6) for r in rel]}"
            )
        if col.n_tears < 2:
            # Damp the secant step for zero/one-tear columns (measured P1-10
            # recovery case): the full Newton step from the ratio-0.5 root
            # (V=44.8) extrapolated the shallow recovery slope straight to
            # V=79.5, where the cold mesh collapses (NS stalls at M~0.96 from
            # the crude seed) and the inside-out sweeps land on a WRONG root -
            # component recovery DROPPED with more boilup, the Jacobian read
            # singular, and the walk aborted. The physical branch is smooth in
            # the tear; steps of at most a quarter of the current tear keep
            # every evaluation on it (the branch spans V=41-88 with recovery
            # 0.86-0.95+; _SPEC_MAX=20 leaves ample iterations).
            for i in range(nf):
                cap = 0.25 * abs(x[i])
                step[i] = max(-cap, min(cap, step[i]))
        if sep_idx:
            sep_step = sum(tear_dir[i] * step[i] for i in range(nf))
            improved = False
            wrong = False
            for k, j in zip(sep_idx, range(len(sep_idx)), strict=True):
                if abs(rel[k]) < _SPEC_TOL:
                    best_wrong[j] = 0.0
                    continue
                wrong = True
                if abs(rel[k]) < best_wrong[j] - 1e-12:
                    best_wrong[j] = abs(rel[k])
                    improved = True
            if wrong and not improved:
                away = all((rel[k] < 0.0) == (sep_step < 0.0) for k in sep_idx if abs(rel[k]) >= _SPEC_TOL)
                if away:
                    flee += 1
                    if flee >= 2:
                        raise ColumnSpecError(
                            f"column specs are unreachable: the separation bracket shows the "
                            f"target on the far side of the maximum-separation corner "
                            f"(separation residuals {[round(r, 6) for r in rel]}); the "
                            f"specification is infeasible for this column"
                        )
                else:
                    flee = 0
            else:
                flee = 0
        if col.n_tears < 2:
            # Damped Newton on the tear update, one-tear columns only: the
            # ratio/boilup curve is flat near the seed (measured P1-09 stripper:
            # ratio 0.593 at boilup 8.0) so the linear secant step lands far
            # outside the narrow mesh-convergent tear window (the undamped step
            # doubled the boilup guess and the mesh died there). Trial the mesh
            # at geometrically shrinking fractions of the step before accepting
            # it. Two-tear columns keep the undamped update unchanged - the
            # distillation bench depends on its exact mesh sequence.
            for frac in (1.0, 0.5, 0.25, 0.125):
                cand = [min(max(x[i] + frac * step[i], _FLOW_FLOOR), flow_cap) for i in range(nf)]
                t_top_c, t_bot_c = tears_of(cand)
                try:
                    mesh_at(t_top_c, t_bot_c)
                    x = cand
                    break
                except ColumnConvergenceError:
                    continue
            else:
                raise ColumnSpecError(
                    "column spec secant step produced no solvable mesh at any damped fraction; "
                    f"residuals {[round(r, 6) for r in rel]}"
                )
        else:
            x = [min(max(x[i] + step[i], _FLOW_FLOOR), flow_cap) for i in range(nf)]
    raise ColumnSpecError(
        f"column specs could not be satisfied within {_SPEC_MAX} secant iterations "
        f"(residuals {[round(r, 6) for r in rel]}); the specification is likely infeasible "
        f"for this column (stages, pressure, feeds)"
    )
