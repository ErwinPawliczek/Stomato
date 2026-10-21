"""Naphtali-Sandholm fallback: simultaneous damped Newton on (x, T, V) (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file.
"""

from __future__ import annotations

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
        lam = 1.0
        accepted = False
        for _ in range(10):
            u_try = [u[i] + lam * step[i] for i in range(n_unk)]
            try:
                r_try = residuals(u_try)
                trial_m = m_norm_of(r_try)
                trial_h = h_norm_of(r_try)
            except (ColumnConvergenceError, ValueError):
                # A trial step landed in a degenerate or off-chemistry state the
                # residual machinery cannot evaluate (SaturationError is a
                # ValueError subclass); reject it and shrink the step.
                trial_m = float("inf")
                trial_h = float("inf")
            # Joint max-norm descent: a step that polishes M while letting H
            # drift is rejected (measured P1-09 rectifier: the M-only search
            # walked M to 1e-8 with H pinned at 0.34 - the state had drifted
            # into an energy-infeasible corner the model refresh never
            # recovered from).
            if max(trial_m, trial_h) < max(m_current, h_current):
                _apply_state(prof, u_try, col, v_free, t_bot_tear)
                if not live_norm:
                    accepted = True
                    break
                # Live-norm acceptance: the frozen-row descent must also not
                # worsen the exact (refreshed-thermo) residuals. Trials that
                # improve the frozen rows while walking the exact residuals
                # uphill are rejected and the pre-step state restored
                # (measured P1-09 stripper: frozen rows closed to 6.9e-10
                # while refreshed exact M rose to 1.00 - the diverged trial
                # displaced a near-converged state the mesh could have kept).
                _refresh_y(col, tb, prof)
                try:
                    ex_try_m, ex_try_h = _exact_residuals(col, tb, prof)
                except (ColumnConvergenceError, ValueError):
                    ex_try_m, ex_try_h = float("inf"), float("inf")
                if max(ex_try_m, ex_try_h) < max(ex_m, ex_h):
                    accepted = True
                    break
                _apply_state(prof, u, col, v_free, t_bot_tear)
            lam *= 0.5
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
