"""Naphtali-Sandholm fallback: simultaneous damped Newton on (x, T, V) (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from .inside_out import (
    _Column,
    _enthalpy_at,
    _exact_residuals,
    _finalize_duties,
    _h_equation_stages,
    _l_profile,
    _Profile,
    _stage_overall,
    _v_free_indices,
)
from .linalg import _gauss
from .spec import (
    _FLOW_FLOOR,
    _MESH_H_TOL,
    _MESH_M_TOL,
    _MESH_M_TOL_REACTIVE,
    _MESH_M_TOL_ZERO_ONE_TEAR,
    _NS_MAX,
    _NS_MAX_ZERO_ONE_TEAR,
    ColumnConvergenceError,
    _is_reactive_package,
)
from .thermo_adapter import _flash_ready, _ThermoBox

# --------------------------------------------------------------------------------------
# Naphtali-Sandholm fallback
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# Newton controller (P1-11 step 4, ruling on issue #153 16:54): per-variable-class
# step cap before the Armijo backtracking, then Levenberg-Marquardt damping on the
# normal equations with the damping adapted from the achieved-vs-predicted ratio.
#
# Measured motivation (step-4 probe on the 20-stage MDEA absorber, posted on #153):
# the FD Jacobian is accurate (max |J(1e-7) - J(1e-5)| / max|J| = 5.9e-7, M rows
# all well-conditioned) and one FULL Newton step achieves max|r| 10259 -> 2346.7
# where the linear model predicts 8.3e-11 - an 11-order validity gap. The reactive
# K-values swing orders of magnitude with loading, so the linearisation dies far
# from the trial state: the uncapped Newton direction is not trustworthy at any
# lambda the line search can reach. The caps bound the step into the model's
# measured validity radius; LM takes over when even the capped step overshoots.

#: |delta T_j| <= _NS_DT_CAP kelvin per pass. The reactive exotherm bulge spans
#: ~33 K over 20 stages; a single pass moving a stage more than a few K is
#: outside the frozen-model validity radius (measured: the uncapped step's
#: predicted 8e-11 residual becomes 2.3e3 achieved).
_NS_DT_CAP = 5.0
#: |delta V_j| <= _NS_DV_REL * V_j per pass (relative traffic cap).
_NS_DV_REL = 0.5
#: |delta x_ij| <= max(_NS_DX_REL * x_ij, _NS_DX_ABS) per pass: bounds the
#: RELATIVE composition move (the packed variable is raw x, so this is the
#: delta-ln-x bound the ruling names, with an absolute floor at the packing's
#: zero clamp so trace components can still grow from ~0).
_NS_DX_REL = 0.5
_NS_DX_ABS = 1e-3
#: LM damping attempts per pass before the pass is abandoned.
_NS_LM_TRIES = 6


def _cap_ns_step(
    u: list[float], step: list[float], col: _Column, v_free: list[int]
) -> tuple[list[float], int]:
    """Cap the packed Newton step per variable class; return (capped, cap hits).

    One mechanism for every package (no per-case branch): the cap bounds each
    pass's move into the linear model's measured validity radius (see the
    constants above) instead of letting the line search discover overshoot by
    halving lambda ten times from an unbounded direction.
    """
    nc = len(col.comps)
    capped = list(step)
    hits = 0
    for i, x in enumerate(u[: nc * col.n]):
        limit = max(_NS_DX_REL * abs(x), _NS_DX_ABS)
        if abs(capped[i]) > limit:
            capped[i] = math.copysign(limit, capped[i])
            hits += 1
    t_base = nc * col.n
    for j in range(col.n):
        if abs(capped[t_base + j]) > _NS_DT_CAP:
            capped[t_base + j] = math.copysign(_NS_DT_CAP, capped[t_base + j])
            hits += 1
    v_base = t_base + col.n
    for idx in range(len(v_free)):
        limit = _NS_DV_REL * max(abs(u[v_base + idx]), _FLOW_FLOOR)
        if abs(capped[v_base + idx]) > limit:
            capped[v_base + idx] = math.copysign(limit, capped[v_base + idx])
            hits += 1
    return capped, hits


def _lm_damped_step(jac: list[list[float]], r0: list[float], lam: float) -> list[float] | None:
    """Levenberg-Marquardt step: solve (J'J + lam*diag(J'J)) d = -J'r.

    Marquardt scaling (diag(J'J), not identity) keeps the damping per-variable:
    the packed unknowns span mole fractions ~1e-2, temperatures ~300 K and
    flows ~100 mol/s, so an identity damping would strangle the temperature and
    flow blocks first for no reason. Returns None when the damped system is
    singular (the caller abandons the pass).
    """
    m = len(r0)
    n_unk = len(jac[0]) if jac else 0
    if n_unk == 0:
        return None
    jtj = [[0.0] * n_unk for _ in range(n_unk)]
    g = [0.0] * n_unk
    for k in range(m):
        row = jac[k]
        rk = r0[k]
        for i in range(n_unk):
            ri = row[i]
            if ri == 0.0:
                continue
            g[i] -= ri * rk
            for j in range(i, n_unk):
                jtj[i][j] += ri * row[j]
    for i in range(n_unk):
        for j in range(i + 1, n_unk):
            jtj[j][i] = jtj[i][j]
    a = [[jtj[i][j] + (lam * jtj[i][i] if i == j else 0.0) for j in range(n_unk)] for i in range(n_unk)]
    try:
        return _gauss(a, g)
    except ColumnConvergenceError:
        return None


def _ns_try_accept(
    svec: list[float],
    u: list[float],
    n_unk: int,
    residuals: Callable[[list[float]], list[float]],
    m_norm_of: Callable[[list[float]], float],
    h_norm_of: Callable[[list[float]], float],
    m_current: float,
    h_current: float,
    live_norm: bool,
    ex_m: float,
    ex_h: float,
    prof: _Profile,
    col: _Column,
    tb: _ThermoBox,
    v_free: list[int],
    t_bot_tear: float | None,
    force_exact: bool = False,
) -> tuple[bool, tuple[float, float], float]:
    """One trial state through the joint descent + exact-gate tests.

    Returns (accepted, achieved scaled norms, sum-of-squares of the trial
    residuals for the LM trust ratio). The acceptance semantics are the pass
    loop's existing ones, unchanged.
    """
    u_try = [u[i] + svec[i] for i in range(n_unk)]
    try:
        r_try = residuals(u_try)
        trial_m = m_norm_of(r_try)
        trial_h = h_norm_of(r_try)
        ss_try = sum(rv * rv for rv in r_try)
    except (ColumnConvergenceError, ValueError):
        # A trial step landed in a degenerate or off-chemistry state the
        # residual machinery cannot evaluate (SaturationError is a
        # ValueError subclass); reject it and shrink the step.
        trial_m, trial_h, ss_try = float("inf"), float("inf"), float("inf")
    # Joint max-norm descent: a step that polishes M while letting H
    # drift is rejected (measured P1-09 rectifier: the M-only search
    # walked M to 1e-8 with H pinned at 0.34 - the state had drifted
    # into an energy-infeasible corner the model refresh never
    # recovered from).
    if max(trial_m, trial_h) >= max(m_current, h_current):
        return False, (trial_m, trial_h), ss_try
    _apply_state(prof, u_try, col, v_free, t_bot_tear)
    if not (live_norm or force_exact):
        return True, (trial_m, trial_h), ss_try
    # Live-norm acceptance: the frozen-row descent must also not worsen
    # either exact (refreshed-thermo) norm. Trials that improve the frozen
    # rows while walking either exact residual uphill are rejected and the
    # pre-step state restored (measured P1-09 stripper: frozen rows closed
    # to 6.9e-10 while refreshed exact M rose to 1.00 - the diverged trial
    # displaced a near-converged state the mesh could have kept).
    _refresh_y(col, tb, prof)
    try:
        ex_try_m, ex_try_h = _exact_residuals(col, tb, prof)
    except (ColumnConvergenceError, ValueError):
        ex_try_m, ex_try_h = float("inf"), float("inf")
    if max(ex_try_m, ex_try_h) < max(ex_m, ex_h):
        return True, (trial_m, trial_h), ss_try
    _apply_state(prof, u, col, v_free, t_bot_tear)
    return False, (trial_m, trial_h), ss_try


@dataclass(frozen=True)
class _NsPass:
    """Thermo data frozen for one Naphtali-Sandholm Newton pass."""

    k_stages: list[dict[str, float]]
    h_vap: list[tuple[float, float, float]]
    h_liq: list[tuple[float, float, float]]
    h_cond: tuple[float, float, float] | None


def _ns_residual_function(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    models: _NsPass,
    h_stages: list[int],
    t_bot_tear: float | None,
) -> Callable[[list[float]], list[float]]:
    """Build the residual function for one Newton pass (fresh closures per pass).

    Full NS equation set: per stage one M balance per component, the summation
    sum_i x_ij = 1, and the H balance where the duty is not an output. K is
    evaluated LIVE at each stage's current state: with frozen K the M rows carry
    no temperature information and the stage temperatures float free - the SVD
    of the frozen-K Jacobian shows the kettle T as an exact null direction, and
    fixing it with a separate bubble row over-determines the composition block.
    With live K the M + summation block is locally square in (x_j, T_j) and
    embeds the bubble condition, so no extra rows are needed.

    A per-stage K cache keeps the finite-difference Jacobian affordable: a
    perturbation of one packed unknown changes only its own stage's state, so
    all other stages hit the cache and cost no flash.
    """
    k_cache: dict[
        tuple[tuple[tuple[str, float], ...], tuple[tuple[str, float], ...], float, float],
        dict[str, float],
    ] = {}

    def _live_k(
        j: int, xs: list[dict[str, float]], ts: list[float], vs: list[float], liquid: list[float]
    ) -> dict[str, float]:
        part = col.feeds[j]
        stage_total = liquid[j] + vs[j] + part.total - col.draw_l[j] - col.draw_v[j]
        overall: dict[str, float] = {}
        for src_comp, src_flow in ((xs[j], liquid[j]), (part.x, part.l_flow), (part.y, part.v_flow)):
            for cid, frac in src_comp.items():
                overall[cid] = overall.get(cid, 0.0) + frac * src_flow
        if stage_total > _FLOW_FLOOR:
            overall = {cid: v / stage_total for cid, v in overall.items()}
        key = (
            tuple(sorted(xs[j].items())),
            tuple(sorted(overall.items())),
            round(ts[j], 12),
            col.pressures[j],
        )
        hit = k_cache.get(key)
        if hit is not None:
            return hit
        # The thermo flash validates normalized compositions; Newton trial states
        # can be far off-normalized or degenerate (all flows at the floor), so
        # evaluate K at the normalized projection - or at the feed composition
        # when the trial state carries no composition at all.
        liq = xs[j] or col.feed_comp
        liq_sum = sum(liq.values())
        liq = {cid: v / liq_sum for cid, v in liq.items()} if liq_sum > _FLOW_FLOOR else col.feed_comp
        overall_sum = sum(overall.values())
        overall = (
            {cid: v / overall_sum for cid, v in overall.items()}
            if overall_sum > _FLOW_FLOOR
            else col.feed_comp
        )
        k = (
            tb.k_values([liq, overall, col.feed_comp], ts[j], col.pressures[j])
            or tb.k_estimate(liq, ts[j], col.pressures[j])
            or models.k_stages[j]
        )
        k_cache[key] = k
        return k

    def residuals(u: list[float]) -> list[float]:
        n = col.n
        xs = _unpack_x(u, col)
        ts = _unpack_t(u, col)
        vs = _unpack_v(u, col, _v_free_indices(col), t_bot_tear)
        liquid = _l_profile(col, l0, vs)
        k_live = [_live_k(j, xs, ts, vs, liquid) for j in range(n)]
        out: list[float] = []
        for j in range(n):
            part = col.feeds[j]
            for cid in col.comps:
                inflow = liquid[j - 1] * xs[j - 1].get(cid, 0.0) if j > 0 else 0.0
                if j == 0 and col.condenser == "total":
                    inflow = l0 * k_live[0].get(cid, 1.0) * xs[0].get(cid, 0.0)
                inflow += (
                    vs[j + 1] * k_live[j + 1].get(cid, 1.0) * xs[j + 1].get(cid, 0.0) if j + 1 < n else 0.0
                )
                inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
                outflow = (liquid[j] + col.draw_l[j]) * xs[j].get(cid, 0.0) + (
                    vs[j] + col.draw_v[j]
                ) * k_live[j].get(cid, 1.0) * xs[j].get(cid, 0.0)
                out.append(inflow - outflow)
            # Canonical NS summation row (Naphtali & Sandholm 1971): sum_i x_ij
            # = sum_i K_ij x_ij, i.e. the bubble condition sum_i x_ij (1 - K_ij)
            # = 0. The former sum(x) - 1 form made the row vanish whenever K was
            # near 1 for every component (wide absorber mid-stages), so the row
            # carried no temperature information exactly where the walk needed
            # it; this form scales with the local volatility spread.
            out.append(
                sum(xs[j].values()) - sum(k_live[j].get(cid, 1.0) * xs[j].get(cid, 0.0) for cid in col.comps)
            )
            if j in h_stages:
                h_in = (
                    (vs[j + 1] * _enthalpy_at(models.h_vap[j + 1], ts[j + 1]) if j + 1 < n else 0.0)
                    + (liquid[j - 1] * _enthalpy_at(models.h_liq[j - 1], ts[j - 1]) if j > 0 else 0.0)
                    + (
                        l0 * _enthalpy_at(models.h_cond, ts[0])
                        if j == 0 and models.h_cond is not None
                        else 0.0
                    )
                    + part.h_flow
                )
                h_out = (vs[j] + col.draw_v[j]) * _enthalpy_at(models.h_vap[j], ts[j]) + (
                    liquid[j] + col.draw_l[j]
                ) * _enthalpy_at(models.h_liq[j], ts[j])
                out.append(h_in - h_out)
        return out

    return residuals


def _naphtali_sandholm(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
    """Fallback: simultaneous damped Newton on (x, T, V) with K frozen per pass.

    Unknowns: the liquid mole fractions x_ij, the stage temperatures T_j and the
    free vapour flows V_j. Equations: the M balances, the summations
    sum_i x_ij = 1, and the H balances whose duty is not an output - square per
    stage grouping (Naphtali & Sandholm 1971). K-values and enthalpy lines
    refresh from the thermo plugin between Newton passes.
    """
    n = col.n
    l0 = prof.l0
    h_stages = _h_equation_stages(col)
    v_free = _v_free_indices(col)
    f_scale = max(col.f_total, 1.0)
    h_scale = max(col.f_total * 2e4, 1.0)
    n_m = n * len(col.comps) + n  # component M rows + summation rows

    def m_norm_of(r: list[float]) -> float:
        """Scaled max residual over the M + summation rows (the exact-M gate's block)."""
        return max(abs(r[i]) for i in range(n_m)) / f_scale

    def h_norm_of(r: list[float]) -> float:
        """Scaled max residual over the H rows (the line-search's second block)."""
        return max(abs(r[i]) for i in range(n_m, len(r))) / h_scale

    ns_max = _NS_MAX if col.n_tears >= 2 else _NS_MAX_ZERO_ONE_TEAR
    live_norm = col.n_tears < 2
    best_u: list[float] | None = None
    best_m = float("inf")
    best_h = float("inf")
    if col.n_tears >= 2:
        m_tol = _MESH_M_TOL
    elif _is_reactive_package(tb):
        m_tol = _MESH_M_TOL_REACTIVE
    else:
        # Same gate the mesh accepts at (_MESH_M_TOL_ZERO_ONE_TEAR): the NS
        # state hands off to _solve_mesh's inside-out polish, and the polish
        # lifts the state further before the mesh's own acceptance decides.
        # A tighter intermediate gate only discarded measurably converged
        # states (measured P1-09 stripper: NS polished a warm-chained state
        # to M=2.90e-7, H=4.46e-10 and the 1e-7 gate typed the tear failed).
        m_tol = _MESH_M_TOL_ZERO_ONE_TEAR
    for _ in range(ns_max):
        prof.ns_passes += 1
        k_stages = [
            tb.k_values(
                [
                    _flash_ready(prof.x[j], col.feed_comp),
                    _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                    col.feed_comp,
                ],
                prof.T[j],
                col.pressures[j],
            )
            or tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
            or {cid: 1.0 for cid in col.comps}
            for j in range(n)
        ]
        h_vap = [
            tb.phase_enthalpy_model(_flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j], True)
            for j in range(n)
        ]
        h_liq = [
            tb.phase_enthalpy_model(
                _flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j], False
            )
            for j in range(n)
        ]
        h_cond = (
            tb.phase_enthalpy_model(prof.y[0] or col.feed_comp, prof.T[0], col.pressures[0], False)
            if col.condenser == "total"
            else None
        )
        models = _NsPass(k_stages=k_stages, h_vap=h_vap, h_liq=h_liq, h_cond=h_cond)
        residuals = _ns_residual_function(col, tb, l0, models, h_stages, t_bot_tear)

        u = _pack_state(prof, col, v_free)
        r0 = residuals(u)
        # The pass gate must carry exact-residual semantics, not the NS residual's.
        # The NS residual derives vapour compositions as K*x (equilibrium-consistent
        # by construction), so a state whose STORED y is stale reads as converged
        # internally while the exact check - which uses the stored y - is wide open.
        # Measured P1-09 absorber, seed state (y = gas-feed composition, not K*x):
        # NS-internal M=6.3e-3 vs exact M=1.00 - the former gate broke before the
        # first Newton step and the fallback never ran for these columns.
        _refresh_y(col, tb, prof)
        ex_m, ex_h = _exact_residuals(col, tb, prof)
        # Live-norm acceptance (zero/one-tear columns): keep the best exact state
        # across passes and restore it at exit. NS's finite-difference Newton can
        # walk PAST the near-converged state it started from into an unevaluable
        # one (measured P1-09 stripper, physical branch at boilup 20-50 mol/s:
        # inside-out best M=2.2e-11/H=1.7e-1 or M=1.5e-2/H=3.4e-6, then NS's own
        # final state M=1.00 - a stage the thermo can no longer evaluate). The
        # best-exact state is what the inside-out polish in _solve_mesh needs.
        if live_norm and ex_m + ex_h < best_m + best_h:
            best_u, best_m, best_h = list(u), ex_m, ex_h
        if ex_m < m_tol and ex_h < _MESH_H_TOL:
            break
        # Baseline norms for the line search's descent test (a descent proxy on
        # the frozen models; acceptance is decided by the exact gate above on
        # the NEXT pass, so a polished-but-not-exact state keeps iterating).
        m_current = m_norm_of(r0)
        h_current = h_norm_of(r0)
        n_unk = len(u)
        jac = [[0.0] * n_unk for _ in range(len(r0))]
        for i in range(n_unk):
            delta = max(abs(u[i]) * 1e-7, 1e-9)
            u2 = list(u)
            u2[i] += delta
            r1 = residuals(u2)
            for row in range(len(r0)):
                jac[row][i] = (r1[row] - r0[row]) / delta
        try:
            step = _gauss(jac, [-r for r in r0])
        except ColumnConvergenceError:
            break
        # Linear-model prediction of the full uncapped Newton step: the
        # denominator of the achieved-vs-predicted trust test in the trace.
        # Measured absorber probe: max|r| predicted 8.3e-11 vs 2346.7 achieved -
        # the 11-order validity gap that motivates the controller.
        lin = [r0[i] + sum(jac[i][j] * step[j] for j in range(n_unk)) for i in range(len(r0))]
        pred_m = max(abs(lin[i]) for i in range(n_m)) / f_scale
        pred_h = max((abs(lin[i]) for i in range(n_m, len(r0))), default=0.0) / h_scale

        # The hoisted trial-acceptance call's per-pass context (plain tuple: the
        # values rebind every pass, so no closure over loop variables).
        ns_ctx = (
            u,
            n_unk,
            residuals,
            m_norm_of,
            h_norm_of,
            m_current,
            h_current,
            live_norm,
            ex_m,
            ex_h,
            prof,
            col,
            tb,
            v_free,
            t_bot_tear,
        )

        lam = 1.0
        accepted = False
        ach_m = ach_h = float("inf")
        ss0 = sum(rv * rv for rv in r0)
        for _ in range(10):
            # svec semantics: the helper builds u_try = u + svec, so the
            # lambda-scaled STEP goes in - not u + lam*step (measured
            # absorber[8] bisect: passing the trial state doubled it and
            # every trial read trial_m ~2600 against m_cur=218).
            ok, ach, _ss = _ns_try_accept([lam * step[i] for i in range(n_unk)], *ns_ctx)
            if ok:
                accepted = True
                ach_m, ach_h = ach
                break
            lam *= 0.5
        via = "newton"
        cap_hits = 0
        lam_lm = 0.0
        # The controller is scoped to reactive packages: that is where the
        # uncapped step's validity gap is measured (11 orders, reactive
        # absorber). Non-reactive columns converge via the baseline Newton
        # line search plus the inside-out polish; engaging LM there shifted a
        # converged stripper's D by 1e-4 and degraded its boundary C1 closure
        # from 3.9e-6 to 1.26e-5 relative (measured N4-r0.8 probe) for no
        # convergence gain. Scoped on the package, not the tear count, so the
        # reactive regenerator keeps the controller at any tear count.
        if not accepted and _is_reactive_package(tb):
            # The uncapped step overshot at every lambda (measured reactive
            # absorber: the step's linear prediction misses by 11 orders, so
            # the line search rejects all its trials and NS stalled after one
            # pass). Engage the step controller: the cap bounds each
            # coordinate's move into the linear model's measured validity
            # radius, and a Levenberg-Marquardt damped step on the normal
            # equations trades residual reduction for model trust, with the
            # damping adapted from the achieved-vs-predicted reduction ratio
            # (the standard trust-region test).
            step, cap_hits = _cap_ns_step(u, step, col, v_free)
            lam_lm = 1.0
            for _ in range(_NS_LM_TRIES):
                d_step = _lm_damped_step(jac, r0, lam_lm)
                if d_step is None:
                    break
                d_step, extra_caps = _cap_ns_step(u, d_step, col, v_free)
                cap_hits += extra_caps
                lin_lm = [r0[i] + sum(jac[i][j] * d_step[j] for j in range(n_unk)) for i in range(len(r0))]
                ss_lin = sum(rv * rv for rv in lin_lm)
                # force_exact: an LM acceptance on a non-reactive column must
                # also close exact residuals. At the FD floor the frozen rows
                # lag the true state, so a frozen-only gate can accept a step
                # that wrecks a floor-converged profile (measured deethanizer:
                # LM accepted via frozen M while exact went M=4.2e-6 -> 8.1,
                # and the polish path then found no floor state to rescue).
                # Rejected LM trials leave the state as the line search did -
                # intact for the polish.
                ok, ach, ss_try = _ns_try_accept(d_step, *ns_ctx, force_exact=True)
                denom = ss0 - ss_lin
                rho = (ss0 - ss_try) / denom if denom > 0.0 else float("inf")
                if ok:
                    accepted = True
                    ach_m, ach_h = ach
                    via = "lm"
                    break
                # Damping adaptation: a rejected trial (rho <= 0) or a poor
                # model match (rho < 0.25) means the step overreached even
                # damped - raise lambda; a good match pre-acceptance would
                # lower it, but a trial this good is accepted above.
                lam_lm *= 4.0 if rho < 0.25 else 2.0
        prof.ns_trace.append(
            f"pass {prof.ns_passes}: exact M={ex_m:.3e} H={ex_h:.3e} | lin-pred M={pred_m:.3e} "
            f"H={pred_h:.3e} | caps={cap_hits} lam={lam:.3g} lam_lm={lam_lm:.3g} "
            f"achieved M={ach_m:.3e} H={ach_h:.3e} via={via}"
        )
        if not accepted:
            break
    else:
        if live_norm and best_u is not None:
            _apply_state(prof, best_u, col, v_free, t_bot_tear)
        raise ColumnConvergenceError("Naphtali-Sandholm fallback did not converge within budget")
    if live_norm and best_u is not None:
        _apply_state(prof, best_u, col, v_free, t_bot_tear)
    _refresh_y(col, tb, prof)
    m_res, h_res = _exact_residuals(col, tb, prof)
    prof.ns_used = True
    # Same tolerances as the inside-out acceptance gate: the enthalpy-line
    # anchor floor sits around 1e-3-1e-4 relative, while mass closes to
    # machine precision. Demanding 1e-6 on H here would reject a solution
    # the mesh itself accepts.
    if m_res > m_tol or h_res > _MESH_H_TOL:
        raise ColumnConvergenceError(
            f"Naphtali-Sandholm fallback stalled: max residuals M={m_res:.2e}, H={h_res:.2e}"
            + (f" | {'; '.join(prof.ns_trace)}" if prof.ns_trace else "")
        )
    _finalize_duties(col, tb, prof)
    return prof


def _pack_state(prof: _Profile, col: _Column, v_free: list[int]) -> list[float]:
    # .get with a 0.0 default: the seed profile for a zero/one-tear column can
    # carry only the components present in the seed compositions (measured P1-09
    # absorber: a pure-nC4 liquid seed gives x = {"nC4": 1.0} and a bare
    # [cid] lookup raises KeyError before the first Newton pass - the fallback
    # never ran at all for these columns).
    u = [prof.x[j].get(cid, 0.0) for j in range(col.n) for cid in col.comps]
    u.extend(prof.T)
    u.extend(prof.V[j] for j in v_free)
    return u


def _unpack_x(u: list[float], col: _Column) -> list[dict[str, float]]:
    out = []
    pos = 0
    for _ in range(col.n):
        out.append({cid: max(u[pos + i], 0.0) for i, cid in enumerate(col.comps)})
        pos += len(col.comps)
    return out


def _unpack_t(u: list[float], col: _Column) -> list[float]:
    base = col.n * len(col.comps)
    # Trial temperatures are clamped to the two-phase operating band (spec D):
    # an unclamped Newton trial can leave it and degenerate the live-K flash.
    return [min(max(u[base + j], col.t_band_lo), col.t_band_hi) for j in range(col.n)]


def _unpack_v(u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None) -> list[float]:
    base = col.n * len(col.comps) + col.n
    full = [_FLOW_FLOOR] * col.n
    for idx, j in enumerate(v_free):
        full[j] = max(_FLOW_FLOOR, u[base + idx])
    if t_bot_tear is not None:
        full[col.n - 1] = t_bot_tear
    return full


def _apply_state(
    prof: _Profile, u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None
) -> None:
    # _unpack_x clamps Newton trial values at zero without renormalizing (the
    # residual algebra needs the raw clamped values); the applied profile must
    # be a valid composition - downstream consumers flash it.
    prof.x = [
        _flash_ready({cid: max(v, 0.0) for cid, v in xs.items()}, col.feed_comp) for xs in _unpack_x(u, col)
    ]
    prof.T = _unpack_t(u, col)
    prof.V = _unpack_v(u, col, v_free, t_bot_tear)
    prof.L = _l_profile(col, prof.l0, prof.V)


def _refresh_y(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Recompute vapour compositions y = K(T, P) x from the current stage states.

    The Newton apply writes x/T/V/L only; downstream consumers (boundary
    streams, spec residuals, duties, info) need the vapour side of the same
    equilibrium, not the stale flash composition from an earlier state.
    """
    for j in range(col.n):
        k = tb.k_values(
            [
                _flash_ready(prof.x[j], col.feed_comp),
                _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                col.feed_comp,
            ],
            prof.T[j],
            col.pressures[j],
        )
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None:
            k = {cid: 1.0 for cid in col.comps}
        y = {cid: k.get(cid, 1.0) * prof.x[j].get(cid, 0.0) for cid in col.comps}
        total = sum(y.values())
        if total > _FLOW_FLOOR:
            y = {cid: v / total for cid, v in y.items()}
        prof.y[j] = y
