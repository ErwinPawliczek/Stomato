"""Inside-out (Boston-Sullivan) column model and MESH solver (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file: the static
problem data, stage profiles, temperature seeds, the outer-sweep model refresh,
the tridiagonal M-equations, the one-shot H solve, the inner loop, the exact
residual check, and duty reporting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ngdesign.contracts import PhaseKind, StreamState

from .linalg import _gauss, _thomas
from .spec import (
    _FLOW_FLOOR,
    _INNER_MAX,
    _INNER_TOL,
    _OUTER_DAMP,
    _SEED_SPAN_MAX,
    ColumnConvergenceError,
    _DrawSpec,
    _Params,
)
from .thermo_adapter import _flash_ready, _ThermoBox

# --------------------------------------------------------------------------------------
# Column model
# --------------------------------------------------------------------------------------


@dataclass
class _StageFeed:
    """The flashed feed parts entering one stage (SI; h_flow = enthalpy flow, W)."""

    v_flow: float = 0.0
    y: dict[str, float] = field(default_factory=dict)
    l_flow: float = 0.0
    x: dict[str, float] = field(default_factory=dict)
    h_flow: float = 0.0
    total: float = 0.0


@dataclass
class _Column:
    """All static problem data for one solve. Stage index 0 = stage 1 (top)."""

    n: int
    condenser: str
    reboiler: str
    pressures: list[float]
    feeds: list[_StageFeed]
    draw_l: list[float]
    draw_v: list[float]
    draws: list[_DrawSpec]
    comps: list[str]
    f_total: float
    z_total: dict[str, float]
    feed_comp: dict[str, float]
    # Two-phase operating window for the inner temperature walk, set from the
    # temperature seed in _build_column.
    t_band_lo: float = 150.0
    t_band_hi: float = 600.0


@dataclass
class _Profile:
    """One stage profile (possibly mid-iteration). Index 0 = stage 1 (top)."""

    T: list[float]
    V: list[float]
    L: list[float]
    x: list[dict[str, float]]
    y: list[dict[str, float]]
    l0: float = 0.0  # reflux entering stage 1 (the total-condenser tear); 0 otherwise
    d: float = 0.0
    b: float = 0.0
    qc: float = 0.0  # condenser duty removed, W
    qr: float = 0.0  # reboiler duty added, W
    outer: int = 0
    inner: int = 0
    ns_used: bool = False


def _flash_stage_feeds(col_params: _Params, tb: _ThermoBox) -> list[_StageFeed]:
    """Flash every feed and split it into the vapour/liquid parts entering its stage."""
    stage_feeds = [_StageFeed() for _ in range(col_params.n_stages)]
    for f in col_params.feeds:
        state = tb.pt(f.comp, f.T, f.P, f.flow)
        part = stage_feeds[f.stage - 1]
        part.total += f.flow
        part.h_flow += state.enthalpy * f.flow
        vapor_part = state.vapor_fraction * f.flow
        liquid_part = (1.0 - state.vapor_fraction) * f.flow
        if vapor_part > _FLOW_FLOOR and state.phases:
            vapor_phase = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
            part.v_flow += vapor_part
            for cid, frac in vapor_phase.composition.items():
                part.y[cid] = part.y.get(cid, 0.0) + frac * vapor_part
        if liquid_part > _FLOW_FLOOR and state.phases:
            liquid_phases = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
            total_liq = sum(p.mole_fraction for p in liquid_phases)
            if total_liq > 0.0:
                part.l_flow += liquid_part
                for phase in liquid_phases:
                    weight = phase.mole_fraction / total_liq
                    for cid, frac in phase.composition.items():
                        part.x[cid] = part.x.get(cid, 0.0) + frac * weight * liquid_part
    for part in stage_feeds:
        if part.v_flow > _FLOW_FLOOR:
            s = sum(part.y.values())
            part.y = {cid: v / s for cid, v in part.y.items()}
        else:
            part.v_flow = 0.0
        if part.l_flow > _FLOW_FLOOR:
            s = sum(part.x.values())
            part.x = {cid: v / s for cid, v in part.x.items()}
        else:
            part.l_flow = 0.0
    return stage_feeds


def _build_column(col_params: _Params, tb: _ThermoBox) -> _Column:
    feeds = _flash_stage_feeds(col_params, tb)
    comps = sorted({cid for part in feeds for cid in part.y} | {cid for part in feeds for cid in part.x})
    f_total = sum(part.total for part in feeds)
    moles: dict[str, float] = {}
    for f in col_params.feeds:
        for cid, frac in f.comp.items():
            moles[cid] = moles.get(cid, 0.0) + frac * f.flow
    z_total = {cid: n / f_total for cid, n in sorted(moles.items())}
    col = _Column(
        n=col_params.n_stages,
        condenser=col_params.condenser,
        reboiler=col_params.reboiler,
        pressures=list(col_params.pressures),
        feeds=feeds,
        draw_l=[0.0] * col_params.n_stages,
        draw_v=[0.0] * col_params.n_stages,
        draws=list(col_params.draws),
        comps=comps,
        f_total=f_total,
        z_total=z_total,
        feed_comp=dict(z_total),
    )
    col.draw_l, col.draw_v = _draw_flows(col)
    # Clamp the inner temperature walk to a window around the physical operating
    # range: the seed estimates the distillate/bottoms temperatures, and stages
    # wandering far outside that range sit in single-phase states where the
    # equilibrium correlation degenerates and the profile collapses.
    t_top, t_bot = _temperature_seed(col, tb)
    if t_bot > t_top + 20.0:
        col.t_band_lo = max(t_top - 30.0, 150.0)
        col.t_band_hi = min(t_bot + 30.0, 600.0)
    return col


def _draw_flows(col: _Column) -> tuple[list[float], list[float]]:
    draw_l = [0.0] * col.n
    draw_v = [0.0] * col.n
    for d in col.draws:
        if d.vapor:
            draw_v[d.stage - 1] += d.flow
        else:
            draw_l[d.stage - 1] += d.flow
    return draw_l, draw_v


def _l_profile(col: _Column, l0: float, v: list[float]) -> list[float]:
    """Liquid profile from the stage-wise total balances, closed form:

    L_j = L_0 + sum_{m<=j}(F_m - S_m) + V_{j+1} - V_1  (V_{N+1} = 0),
    the telescoped sum of the stage total material balances.
    """
    out = []
    cum = 0.0
    v1 = v[0]
    for j in range(col.n):
        cum += col.feeds[j].total - col.draw_l[j] - col.draw_v[j]
        v_above = v[j + 1] if j + 1 < col.n else 0.0
        out.append(max(l0 + cum + v_above - v1, _FLOW_FLOOR))
    return out


def _d_and_b(col: _Column, l0: float, v: list[float], liquid: list[float]) -> tuple[float, float]:
    """Distillate and bottoms from the boundary balances.

    Total condenser: the hardware splits V_1 into reflux L_0 + distillate D.
    Partial/none: the distillate is the stage-1 vapour V_1 itself.
    The bottoms is the liquid leaving stage N.

    The values are kept raw (possibly negative mid-iteration): flooring them
    would flatten the spec residuals' gradient and stall the secant loop. The
    converged solution satisfies the specs, so the reported flows are positive.
    """
    d = v[0] - l0 if col.condenser == "total" else v[0]
    return d, liquid[col.n - 1]


def _temperature_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float]:
    """Estimate (T_top, T_bottom) for the starting profile.

    Two estimates. (1) Pure-component extremes: coldest and hottest component
    saturation temperatures at the end pressures - good for narrow-boiling
    feeds (their own bubble/dew can sit within a few kelvin, on either side).
    (2) Equilibrium-based: flash the feed at the mid-column pressure, take the
    bubble point of the vapour phase at the top pressure as T_top and of the
    liquid phase at the bottom pressure as T_bottom - the distillate/bottoms
    compositions of an average split. Extremes win for narrow boiling, but for
    wide-boiling feeds they smear the profile across the whole component list
    (a trace of C1 drops the top seed ~70 K into a region where the flash of
    C3+ liquids degenerates), so wide spans defer to the equilibrium estimate.
    """
    ext = _extreme_seed(col, tb)
    if ext is not None:
        t_top, t_bot = ext
        if t_bot > t_top + 1.0 and t_bot - t_top <= _SEED_SPAN_MAX:
            return t_top + 2.0, t_bot
    eq = _equilibrium_seed(col, tb)
    if eq is not None and eq[1] > eq[0] + 1.0:
        return eq[0] + 2.0, eq[1]
    t_top = bisect_feed_phase(col, tb, col.pressures[0], want_vapor=True)
    t_bot = bisect_feed_phase(col, tb, col.pressures[-1], want_vapor=False)
    if t_bot <= t_top:
        t_feed = tb.pt(col.feed_comp, 300.0, col.pressures[-1]).T
        t_top, t_bot = t_feed - 25.0, t_feed + 25.0
    return t_top, t_bot


def _extreme_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float] | None:
    """Coldest / hottest pure-component saturation temperatures, if flasheable."""
    sats_top: list[float] = []
    sats_bot: list[float] = []
    for cid in col.feed_comp:
        pure = {cid: 1.0}
        t_sat = tb.bubble_temperature(pure, col.pressures[0])
        if t_sat is not None:
            sats_top.append(t_sat)
        t_sat = tb.bubble_temperature(pure, col.pressures[-1])
        if t_sat is not None:
            sats_bot.append(t_sat)
    if not sats_top or not sats_bot:
        return None
    return min(sats_top), max(sats_bot)


def _equilibrium_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float] | None:
    """Feed flash at the mid pressure; bubble points of each phase at the ends."""
    p_mid = 0.5 * (col.pressures[0] + col.pressures[-1])
    t_bub = bisect_feed_phase(col, tb, p_mid, want_vapor=False)
    t_dew = bisect_feed_phase(col, tb, p_mid, want_vapor=True)
    if not t_dew > t_bub + 2.0:
        return None
    state = tb.pt(col.feed_comp, 0.5 * (t_bub + t_dew), p_mid)
    vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
    liq = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
    if vap is None or liq is None:
        return None
    t_top = tb.bubble_temperature(_flash_ready(vap.composition, col.feed_comp), col.pressures[0])
    t_bot = tb.bubble_temperature(_flash_ready(liq.composition, col.feed_comp), col.pressures[-1])
    if t_top is None or t_bot is None:
        return None
    return t_top, t_bot


def bisect_feed_phase(col: _Column, tb: _ThermoBox, p: float, want_vapor: bool) -> float:
    """Bounded bisection on the feed flash for its dew (want_vapor) / bubble point."""
    lo, hi = 100.0, 700.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        vf = tb.pt(col.feed_comp, mid, p).vapor_fraction
        if want_vapor:
            lo, hi = (mid, hi) if vf < 0.97 else (lo, mid)
        else:
            lo, hi = (lo, mid) if vf > 0.03 else (mid, hi)
    return 0.5 * (lo + hi)


def _seed_profile(col: _Column, t_top: float, t_bot: float) -> _Profile:
    n = col.n
    temps = [t_top + (t_bot - t_top) * (j / max(n - 1, 1)) for j in range(n)]
    z = col.feed_comp
    d_guess = max(0.35 * col.f_total, _FLOW_FLOOR)
    v1_guess = d_guess * 2.5
    vn_guess = (col.f_total - d_guess) * 1.5
    vapour = [max(v1_guess + (vn_guess - v1_guess) * (j / max(n - 1, 1)), _FLOW_FLOOR) for j in range(n)]
    l0 = max(v1_guess - d_guess, _FLOW_FLOOR) if col.condenser == "total" else 0.0
    if col.condenser == "partial":
        vapour[0] = max(d_guess, _FLOW_FLOOR)
    liquid = _l_profile(col, l0, vapour)
    x = [dict(z) for _ in range(n)]
    y = [dict(z) for _ in range(n)]
    return _Profile(T=temps, V=vapour, L=liquid, x=x, y=y, l0=l0)


# --------------------------------------------------------------------------------------
# Inside-out (Boston-Sullivan) solver
# --------------------------------------------------------------------------------------


@dataclass
class _InnerModel:
    """Frozen per-sweep models: raw K, alpha_ij, the ln Kb = A + B/T fit, enthalpy lines."""

    k_raw: list[dict[str, float]]
    alpha: list[dict[str, float]]
    ref_comp: str
    corr_a: float
    corr_b: float
    h_vap: list[tuple[float, float, float]]  # (h0, cp, T_ref) per stage, vapour
    h_liq: list[tuple[float, float, float]]  # per stage, liquid
    h_cond: tuple[float, float, float] | None  # condensate (total-condenser reflux) line
    fit_T: list[float]  # temperatures the enthalpy lines were fitted at


def _stage_overall(col: _Column, prof: _Profile, j: int) -> dict[str, float]:
    """Overall composition sitting on stage j: flows-weighted liquid, vapour and feed."""
    part = col.feeds[j]
    total = prof.L[j] + prof.V[j] + part.total - col.draw_l[j] - col.draw_v[j]
    if total <= _FLOW_FLOOR:
        return col.feed_comp
    acc: dict[str, float] = {}
    for src_comp, src_flow in (
        (prof.x[j], prof.L[j]),
        (prof.y[j], prof.V[j]),
        (part.x, part.l_flow),
        (part.y, part.v_flow),
    ):
        for cid, frac in src_comp.items():
            acc[cid] = acc.get(cid, 0.0) + frac * src_flow
    return {cid: v / total for cid, v in acc.items() if v > 0.0} or col.feed_comp


def _refresh_model(col: _Column, tb: _ThermoBox, prof: _Profile, model: _InnerModel | None) -> _InnerModel:
    """One outer sweep: real K-values per stage, alpha against a column-wide reference
    component, the ln Kb = A + B/T correlation (least squares over the stage points),
    and per-stage linear enthalpy models (refitted only when temperatures moved)."""
    n = col.n
    k_stages: list[dict[str, float]] = []
    for j in range(n):
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
        if k is None and model is not None:
            k = model.k_raw[j]
        k_stages.append(k or {cid: 1.0 for cid in col.comps})

    weights = {
        cid: sum(k_stages[j].get(cid, 0.0) * prof.x[j].get(cid, 0.0) for j in range(n)) for cid in col.comps
    }
    ref_comp = max(weights, key=lambda cid: weights[cid])
    kb = [max(k_stages[j].get(ref_comp, 1.0), 1e-12) for j in range(n)]
    alpha = [{cid: max(k_stages[j].get(cid, 1.0) / kb[j], 1e-12) for cid in col.comps} for j in range(n)]

    s_xx = sum(1.0 / (t * t) for t in prof.T)
    s_x = sum(1.0 / t for t in prof.T)
    s_y = sum(math.log(k) for k in kb)
    s_xy = sum(math.log(k) / t for k, t in zip(kb, prof.T, strict=True))
    det = n * s_xx - s_x * s_x
    if abs(det) < 1e-300:
        corr_a, corr_b = s_y / n, 0.0
    else:
        corr_b = (n * s_xy - s_x * s_y) / det
        corr_a = (s_y - corr_b * s_x) / n

    w = _OUTER_DAMP
    if model is not None:
        # Feedback damping (Boston-Sullivan): blend the refreshed correlation and
        # relative volatility with the previous sweep's values. Without it the
        # K/T/V coupling develops a two-cycle around the solution.
        corr_a = w * corr_a + (1.0 - w) * model.corr_a
        corr_b = w * corr_b + (1.0 - w) * model.corr_b
        alpha = [
            {cid: w * alpha[j][cid] + (1.0 - w) * model.alpha[j].get(cid, alpha[j][cid]) for cid in col.comps}
            for j in range(n)
        ]

    # Refit the enthalpy anchors every sweep: near convergence temperatures
    # barely move, so a refit-on-temperature-drift rule left the lines anchored
    # at stale compositions while x kept sharpening - the exact energy recheck
    # then never closed above the anchor floor. Both lines read the phases of
    # the same memoized flash the K chain used (one flash per stage state): the
    # equilibrium vapour/liquid of the flashed liquid candidate, with the
    # per-phase build (``phase_enthalpy_model``) as the single-phase fallback.
    h_vap: list[tuple[float, float, float]] = []
    h_liq: list[tuple[float, float, float]] = []
    for j in range(n):
        pair = tb.phase_enthalpy_pair(
            tb.pt(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j]),
            prof.T[j],
        )
        if pair is None:
            pair = (
                tb.phase_enthalpy_model(
                    _flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j], True
                ),
                tb.phase_enthalpy_model(
                    _flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j], False
                ),
            )
        h_vap.append(pair[0])
        h_liq.append(pair[1])
    h_cond = (
        tb.phase_enthalpy_model(_flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0], False)
        if col.condenser == "total"
        else None
    )
    return _InnerModel(
        k_raw=k_stages,
        alpha=alpha,
        ref_comp=ref_comp,
        corr_a=corr_a,
        corr_b=corr_b,
        h_vap=h_vap,
        h_liq=h_liq,
        h_cond=h_cond,
        fit_T=list(prof.T),
    )


def _enthalpy_at(line: tuple[float, float, float], t: float) -> float:
    h0, cp, t_ref = line
    return h0 + cp * (t - t_ref)


def _mesh_x(col: _Column, model: _InnerModel, prof: _Profile, kb: list[float]) -> list[list[float]]:
    """M-equations: one tridiagonal solve per component for the liquid compositions.

    Returns x[component_index][stage_index].

    Stage j balance, component i, with y = K x and K_ij = alpha_ij * Kb_j:
        L_{j-1} x_{j-1} + V_{j+1} K_{j+1} x_{j+1} + F^L x^F + F^V y^F
        - (L_j + S^L_j) x_j - (V_j + S^V_j) K_j x_j = 0
    For a total condenser the reflux L_0 enters stage 1 at the condensate
    composition y_1 = K_1 x_1, folding L_0 K_1 into the stage-1 diagonal.
    """
    n = col.n
    k = [{cid: model.alpha[j].get(cid, 1.0) * kb[j] for cid in col.comps} for j in range(n)]
    liquid = _l_profile(col, prof.l0, prof.V)
    out: list[list[float]] = []
    for cid in col.comps:
        sub = [0.0] * n
        diag = [0.0] * n
        up = [0.0] * n
        rhs = [0.0] * n
        for j in range(n):
            part = col.feeds[j]
            if j > 0:
                sub[j] = liquid[j - 1]
            diag[j] = -((liquid[j] + col.draw_l[j]) + (prof.V[j] + col.draw_v[j]) * k[j].get(cid, 1.0))
            if j == 0 and col.condenser == "total":
                diag[j] += prof.l0 * k[j].get(cid, 1.0)
            if j < n - 1:
                up[j] = prof.V[j + 1] * k[j + 1].get(cid, 1.0)
            rhs[j] = -(part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0))
        sol = _thomas(sub, diag, up, rhs)
        out.append([max(v, 0.0) for v in sol])
    return out


def _h_equation_stages(col: _Column) -> list[int]:
    """Stages whose energy balance closes with the profile (duty-output stages drop out)."""
    n = col.n
    stages = list(range(n))
    if col.condenser == "partial":
        stages = [j for j in stages if j != 0]
    if col.reboiler == "kettle":
        stages = [j for j in stages if j != n - 1]
    return stages


def _v_free_indices(col: _Column) -> list[int]:
    """Vapour flows the enthalpy system may correct (tears and V_1-outcome excluded)."""
    n = col.n
    free = list(range(n))
    if col.condenser == "partial":
        free = [j for j in free if j != 0]  # V_1 = D is the top tear
    if col.reboiler == "kettle":
        free = [j for j in free if j != n - 1]  # V_N = boilup is the bottom tear
    return free


def _mesh_v(col: _Column, model: _InnerModel, prof: _Profile, t_bot_tear: float | None) -> list[float]:
    """H-equations: exact one-shot solve for the vapour profile.

    Stage j energy balance (Q_j = heat added to the stage):
        V_{j+1} H^V_{j+1} + L_{j-1} H^L_{j-1} + F_j H^F - (V_j + S^V_j) H^V_j
        - (L_j + S^L_j) H^L_j - Q_j = 0
    With the enthalpy lines and temperatures frozen, every term is affine in the
    free vapour flows (the L recursion is linear in V), so one Jacobian
    evaluation plus one linear solve is exact - no iteration, no line search.
    """
    n = col.n
    equation_stages = _h_equation_stages(col)
    free = _v_free_indices(col)

    def residuals(v: list[float]) -> list[float]:
        liquid = _l_profile(col, prof.l0, v)
        out = []
        for j in equation_stages:
            h_in = (
                (v[j + 1] * _enthalpy_at(model.h_vap[j + 1], prof.T[j + 1]) if j + 1 < n else 0.0)
                + (liquid[j - 1] * _enthalpy_at(model.h_liq[j - 1], prof.T[j - 1]) if j > 0 else 0.0)
                + (
                    prof.l0 * _enthalpy_at(model.h_cond, prof.T[0])
                    if j == 0 and model.h_cond is not None
                    else 0.0
                )
                + col.feeds[j].h_flow
            )
            h_out = (v[j] + col.draw_v[j]) * _enthalpy_at(model.h_vap[j], prof.T[j]) + (
                liquid[j] + col.draw_l[j]
            ) * _enthalpy_at(model.h_liq[j], prof.T[j])
            out.append(h_in - h_out)
        return out

    v_work = list(prof.V)
    if t_bot_tear is not None:
        v_work[n - 1] = t_bot_tear
    r0 = residuals(v_work)
    jac_cols = []
    for vk in free:
        perturbed = list(v_work)
        perturbed[vk] = v_work[vk] * (1.0 + 1e-6) + 1e-9
        r1 = residuals(perturbed)
        jac_cols.append([(r1[row] - r0[row]) / (perturbed[vk] - v_work[vk]) for row in range(len(r0))])
    jac = [[jac_cols[c][r] for c in range(len(free))] for r in range(len(r0))]
    try:
        step = _gauss(jac, [-r for r in r0])
    except ColumnConvergenceError:
        return v_work  # singular H system: keep the incoming profile, the exact
        # residual test will reject it and the NS fallback takes over
    candidate = list(v_work)
    for idx, vk in enumerate(free):
        candidate[vk] = max(v_work[vk] + step[idx], _FLOW_FLOOR)
    if t_bot_tear is not None:
        candidate[n - 1] = t_bot_tear
    # One safeguarded refinement pass guards against conditioning loss; the
    # system is affine, so this lands on the solution to round-off.
    for _ in range(2):
        r1 = residuals(candidate)
        if max(abs(r) for r in r1) <= max(abs(r) for r in r0):
            break
        jac_cols = []
        for vk in free:
            perturbed = list(candidate)
            perturbed[vk] = candidate[vk] * (1.0 + 1e-6) + 1e-9
            r2 = residuals(perturbed)
            jac_cols.append([(r2[row] - r1[row]) / (perturbed[vk] - candidate[vk]) for row in range(len(r1))])
        jac = [[jac_cols[c][r] for c in range(len(free))] for r in range(len(r1))]
        try:
            step = _gauss(jac, [-r for r in r1])
        except ColumnConvergenceError:
            break
        refined = list(candidate)
        for idx, vk in enumerate(free):
            refined[vk] = max(candidate[vk] + step[idx], _FLOW_FLOOR)
        if t_bot_tear is not None:
            refined[n - 1] = t_bot_tear
        candidate = refined
    return candidate


def _inner_solve(col: _Column, model: _InnerModel, prof: _Profile, t_bot_tear: float | None) -> int:
    """The inside-out inner loop: M -> bubble (Kb) -> T (correlation) -> H (Newton).

    With alpha, the Kb correlation and the enthalpy lines frozen, the loop
    iterates until flows and temperatures stop moving. No thermo calls.
    """
    n = col.n
    kb = [1.0] * n
    iterations = 0
    for i in range(1, _INNER_MAX + 1):
        iterations = i
        x_sets = _mesh_x(col, model, prof, kb)
        x_new: list[dict[str, float]] = []
        for j in range(n):
            s = sum(x_sets[i_c][j] for i_c in range(len(col.comps)))
            if s <= 0.0:
                x_new.append(dict(col.feed_comp))
            else:
                x_new.append({cid: x_sets[i_c][j] / s for i_c, cid in enumerate(col.comps)})
        kb = [
            max(1.0 / sum(model.alpha[j].get(cid, 1.0) * x_new[j].get(cid, 0.0) for cid in col.comps), 1e-12)
            for j in range(n)
        ]
        t_old = prof.T
        v_old = prof.V
        t_new = []
        for j in range(n):
            denom = math.log(kb[j]) - model.corr_a
            t_corr = model.corr_b / denom if abs(denom) > 1e-12 else t_old[j]
            t_corr = min(max(t_corr, col.t_band_lo), col.t_band_hi)  # two-phase operating window
            step = 0.7 * (t_corr - t_old[j])
            step = max(min(step, 30.0), -30.0)  # bounded walk, one sweep at a time
            t_new.append(t_old[j] + step)
        prof.T = t_new  # the V-solve must see the temperatures it will be judged at
        v_new = _mesh_v(col, model, prof, t_bot_tear)
        delta_t = max(abs(t_new[j] - t_old[j]) / max(t_old[j], 1.0) for j in range(n))
        delta_v = max(abs(v_new[j] - v_old[j]) / max(v_old[j], 1.0) for j in range(n))
        prof.V = v_new
        prof.x = x_new
        prof.L = _l_profile(col, prof.l0, prof.V)
        if delta_t < _INNER_TOL and delta_v < _INNER_TOL:
            break
    prof.y = []
    for j in range(n):
        y_j = {cid: model.alpha[j].get(cid, 1.0) * kb[j] * prof.x[j].get(cid, 0.0) for cid in col.comps}
        s = sum(y_j.values())
        prof.y.append({cid: v / s for cid, v in y_j.items()} if s > 0.0 else dict(col.feed_comp))
    prof.inner += iterations
    return iterations


def _exact_residuals(col: _Column, tb: _ThermoBox, prof: _Profile) -> tuple[float, float]:
    """Max relative MESH residuals with real thermo K-values and phase enthalpies.

    The honest convergence measure: the frozen inner models closed the equations,
    and the refreshed thermo values must still close them.
    """
    n = col.n
    max_m = 0.0
    max_h = 0.0
    liquid = _l_profile(col, prof.l0, prof.V)
    h_scale = max(col.f_total * 2e4, 1.0)
    h_stages = set(_h_equation_stages(col))
    for j in range(n):
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
            # A stage whose equilibrium cannot be evaluated is NOT converged.
            # Skipping it let degenerate all-liquid profiles read as exact.
            max_m = max(max_m, 1.0)
            max_h = max(max_h, 1.0)
            continue
        part = col.feeds[j]
        for cid in col.comps:
            inflow = liquid[j - 1] * prof.x[j - 1].get(cid, 0.0) if j > 0 else 0.0
            if j == 0 and col.condenser == "total":
                inflow = prof.l0 * prof.y[0].get(cid, 0.0)
            inflow += prof.V[j + 1] * prof.y[j + 1].get(cid, 0.0) if j + 1 < n else 0.0
            inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
            outflow = (liquid[j] + col.draw_l[j]) * prof.x[j].get(cid, 0.0) + (
                prof.V[j] + col.draw_v[j]
            ) * prof.y[j].get(cid, 0.0)
            scale = max(abs(inflow), abs(outflow), col.f_total * 1e-6)
            max_m = max(max_m, abs(inflow - outflow) / scale)
        if j not in h_stages:
            continue  # duty-output stage: its balance defines the duty (qc/qr);
            # counting it here would report the duty magnitude as a residual
        h_in = (
            (
                prof.V[j + 1]
                * tb.h_vapor(_flash_ready(prof.y[j + 1], col.feed_comp), prof.T[j + 1], col.pressures[j + 1])
                if j + 1 < n
                else 0.0
            )
            + (
                liquid[j - 1]
                * tb.h_liquid(_flash_ready(prof.x[j - 1], col.feed_comp), prof.T[j - 1], col.pressures[j - 1])
                if j > 0
                else 0.0
            )
            + part.h_flow
        )
        if j == 0 and col.condenser == "total":
            h_in += prof.l0 * tb.h_liquid(_flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0])
        h_out = (prof.V[j] + col.draw_v[j]) * tb.h_vapor(
            _flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j]
        ) + (liquid[j] + col.draw_l[j]) * tb.h_liquid(
            _flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j]
        )
        max_h = max(max_h, abs(h_in - h_out) / h_scale)
    return max_m, max_h


# --------------------------------------------------------------------------------------
# Duties and overall energy closure
# --------------------------------------------------------------------------------------


def _finalize_duties(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Duties from the converged profile.

    Condenser duty from its own balance; reboiler duty from the stage balance,
    then closed exactly on the overall energy balance over the real boundary
    streams (see module docstring). Draws leave at their stage conditions.
    """
    # Converged states satisfy the summation rows only to solver tolerance;
    # normalize every stage composition in place so the duties and the outlet
    # boundary streams built from this profile pass the thermo's validation.
    for j in range(col.n):
        for comp in (prof.x[j], prof.y[j]):
            total = sum(comp.values())
            if total > _FLOW_FLOOR and abs(total - 1.0) > 1e-12:
                for cid in comp:
                    comp[cid] /= total
    liquid = _l_profile(col, prof.l0, prof.V)
    prof.d, prof.b = _d_and_b(col, prof.l0, prof.V, liquid)
    if col.condenser == "total":
        y0 = _flash_ready(prof.y[0], col.feed_comp)
        prof.qc = max(
            prof.V[0]
            * (tb.h_vapor(y0, prof.T[0], col.pressures[0]) - tb.h_liquid(y0, prof.T[0], col.pressures[0])),
            0.0,
        )
    elif col.condenser == "partial":
        y1 = _flash_ready(prof.y[1], col.feed_comp) if col.n > 1 else col.feed_comp
        h_in = (prof.V[1] * tb.h_vapor(y1, prof.T[1], col.pressures[1]) if col.n > 1 else 0.0) + col.feeds[
            0
        ].h_flow
        h_out = prof.V[0] * tb.h_vapor(
            _flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0]
        ) + (liquid[0] + col.draw_l[0]) * tb.h_liquid(
            _flash_ready(prof.x[0], col.feed_comp), prof.T[0], col.pressures[0]
        )
        prof.qc = max(h_in - h_out, 0.0)
    else:
        prof.qc = 0.0
    if col.reboiler == "kettle":
        h_in = (
            liquid[col.n - 2]
            * tb.h_liquid(
                _flash_ready(prof.x[col.n - 2], col.feed_comp),
                prof.T[col.n - 2],
                col.pressures[col.n - 2],
            )
            if col.n > 1
            else 0.0
        ) + col.feeds[col.n - 1].h_flow
        h_out = prof.V[col.n - 1] * tb.h_vapor(
            _flash_ready(prof.y[col.n - 1], col.feed_comp),
            prof.T[col.n - 1],
            col.pressures[col.n - 1],
        ) + (liquid[col.n - 1] + col.draw_l[col.n - 1]) * tb.h_liquid(
            _flash_ready(prof.x[col.n - 1], col.feed_comp),
            prof.T[col.n - 1],
            col.pressures[col.n - 1],
        )
        prof.qr = max(h_in - h_out, 0.0)
    else:
        prof.qr = 0.0


def _close_energy_balance(
    col: _Column,
    tb: _ThermoBox,
    prof: _Profile,
    feed_states: list[StreamState],
    out_states: list[StreamState],
) -> None:
    """Exact overall closure: qr = sum(H_out) - sum(H_in) + qc, over the real streams.

    This makes UnitResult.duty_W = qr - qc close the stream enthalpy table to
    machine precision; the deviation from the stage-balance reboiler duty is the
    converged MESH residual, far below the duty magnitudes.
    """
    h_in = sum(s.enthalpy * s.molar_flow for s in feed_states)
    h_out = sum(s.enthalpy * s.molar_flow for s in out_states)
    prof.qr = h_out - h_in + prof.qc
