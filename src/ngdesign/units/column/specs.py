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
    bisect_feed_phase,
)
from .linalg import _gauss
from .naphtali_sandholm import _naphtali_sandholm
from .spec import (
    _FLOW_FLOOR,
    _MESH_H_TOL,
    _MESH_M_TOL,
    _OUTER_DAMP,
    _OUTER_MAX,
    _SPEC_MAX,
    _SPEC_TOL,
    ColumnConvergenceError,
    ColumnSpecError,
    _Params,
)
from .thermo_adapter import _flash_ready, _ThermoBox

# --------------------------------------------------------------------------------------
# Mesh driver and duty reporting
# --------------------------------------------------------------------------------------


def _apply_tears(col: _Column, prof: _Profile, t_top: float | None, t_bot: float | None) -> None:
    """Write the tear values into the profile (reflux, distillate vapour, boilup)."""
    if col.condenser == "total":
        prof.l0 = max(t_top, _FLOW_FLOOR) if t_top is not None else prof.l0
    elif col.condenser == "partial":
        prof.l0 = 0.0
        if t_top is not None:
            prof.V[0] = max(t_top, _FLOW_FLOOR)
    else:
        prof.l0 = 0.0
    if col.reboiler == "kettle" and t_bot is not None:
        prof.V[col.n - 1] = max(t_bot, _FLOW_FLOOR)


def _solve_mesh(
    col: _Column, tb: _ThermoBox, t_top: float | None, t_bot: float | None, seed: _Profile | None
) -> _Profile:
    """Converge the MESH equations at given tear values: inside-out, NS fallback."""
    prof: _Profile | None = None
    if seed is None:
        t_top_seed, t_bot_seed = _temperature_seed(col, tb)
        prof = _seed_profile(col, t_top_seed, t_bot_seed)
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
    for outer in range(1, _OUTER_MAX + 1):
        t_prev, v_prev = list(prof.T), list(prof.V)
        model = _refresh_model(col, tb, prof, model)
        prof.outer = outer
        _inner_solve(col, model, prof, t_bot)  # accumulates prof.inner itself
        w = _OUTER_DAMP
        # Feedback damping between sweeps on temperature and vapour profiles:
        # the frozen-model update overshoots near unstable tears.
        for j in range(col.n):
            prof.T[j] = t_prev[j] + w * (prof.T[j] - t_prev[j])
            prof.V[j] = v_prev[j] + w * (prof.V[j] - v_prev[j])
        prof.L = _l_profile(col, prof.l0, prof.V)
        m_res, h_res = _exact_residuals(col, tb, prof)
        if m_res < _MESH_M_TOL and h_res < _MESH_H_TOL:
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
            if stalled >= 3:
                break
    # The inside-out loop stalled or exhausted its budget: hand the best profile
    # to the Naphtali-Sandholm Newton fallback, which polishes from there.
    if best_prof is not None:
        prof = _copy_profile(col, best_prof)
    try:
        _naphtali_sandholm(col, tb, prof, t_bot)
    except ColumnConvergenceError as exc:
        raise ColumnConvergenceError(
            f"column did not converge in {_OUTER_MAX} inside-out sweeps and the "
            f"Naphtali-Sandholm fallback failed: {exc}"
        ) from exc
    return prof


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
    )


def _initial_tears(col: _Column, params: _Params) -> tuple[float, float]:
    """Starting guesses for the two tear flows (top reflux, kettle boilup), mol/s.

    Plain fractions of the feed: the spec secant moves them, the mesh converges
    from any sane start, and elaborate temperature-based seeds bought nothing.
    """
    return 0.5 * col.f_total, 0.8 * col.f_total


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
    draw_total = sum(dr.flow for dr in params.draws)
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
    free_top = t_top is not None and not pin_top
    free_bot = t_bot is not None and not pin_bot
    if col.condenser == "total" and pin_top and free_bot and t_top is not None:
        # Seed the first mesh at high vapour traffic: a fully-boiling column has
        # every stage two-phase and the mesh converges robustly there; the warm-
        # started secant then walks the kettle tear down to the specification.
        t_bot = t_top + col.f_total * 0.2

    state: dict[str, _Profile | None] = {"seed": None}

    def mesh_at(top: float | None, bot: float | None) -> _Profile:
        """Solve the mesh at given tears, backtracking toward the seed on failure."""
        last: ColumnConvergenceError | None = None
        for _attempt in range(3):
            try:
                prof = _solve_mesh(col, tb, top, bot, state["seed"])
                state["seed"] = _copy_profile(col, prof)
                return prof
            except ColumnConvergenceError as exc:
                last = exc
            except ValueError as exc:
                # Unconverged iterates can leave the flash's physical domain
                # (pydantic stream validation inside the PR package). That is a
                # convergence failure of this iterate, not a caller error.
                last = ColumnConvergenceError(f"iterate left the flash domain: {exc}")
            seed = state["seed"]
            if seed is None:
                break
            if top is not None:
                top = top + 0.5 * (seed.l0 - top)
            if bot is not None:
                bot = bot + 0.5 * (seed.V[col.n - 1] - bot)
        raise ColumnConvergenceError(f"mesh failed at tears {(top, bot)}: {last}")

    def apply_vector(v: list[float]) -> tuple[float | None, float | None]:
        """Map the free-tear vector back onto (top, bot) tears."""
        it = iter(v)
        a = next(it) if free_top else t_top
        b2 = next(it) if free_bot else t_bot
        return a, b2

    def tears_of(v: list[float]) -> tuple[float, float]:
        """Unpack the free-tear vector into concrete tears.

        The ``None`` members of ``apply_vector``'s result denote a pinned tear
        that was never set from specs; the spec loop only runs when every
        tear is either pinned to a value or free, so None here is a caller
        bug and must surface as a typed error.
        """
        top, bot = apply_vector(v)
        if top is None or bot is None:
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
        # Everything pinned algebraically: the tears already encode both targets.
        prof = mesh_at(t_top, t_bot)
        g0, s0 = _spec_g(col, params, prof, skip)
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
        x = [min(max(x[i] + step[i], _FLOW_FLOOR), flow_cap) for i in range(nf)]
    raise ColumnSpecError(
        f"column specs could not be satisfied within {_SPEC_MAX} secant iterations "
        f"(residuals {[round(r, 6) for r in rel]}); the specification is likely infeasible "
        f"for this column (stages, pressure, feeds)"
    )
