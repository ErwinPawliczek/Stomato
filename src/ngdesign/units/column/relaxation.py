"""Relaxation cold start for wide-boiling columns (``initialization: relaxation``).

The standard cold start hands the inside-out sweeps a feed-flash profile. On a
wide-boiling feed (crude and vacuum pseudo-component slates) the inside-out
temperature walk overshoots between the band edges and Newton starts from a
state it cannot reach (measured: the 6-stage vacuum column on the 19-pseudo
example feed - the sweeps pin stages on the band, M ~ 1.0 throughout).

This module builds the starting profile by the relaxation method: every stage
is an equilibrium flash of what flows into it, and the stages are flashed in
alternating Gauss-Seidel sweeps until the profile stops moving (Rose, Sweeny &
Schrodt 1958, "Continuous distillation calculations by relaxation method",
Ind. Eng. Chem. 50, 737; used as the global start of a Newton method by
Ketchum 1979, "A combined relaxation-Newton method as a new global approach to
the computation of thermal separation processes", Chem. Eng. Sci. 34, 387).
Each relaxation state is physical (non-negative flows, compositions on the
simplex, stage temperatures from a stage flash), which is what makes it a
global start; the Newton machinery then converges it on the exact gate.

The stage flashes run on frozen local models refreshed once per outer pass
(the inside-out idea applied to the relaxation): per stage, ln K_i(T) =
ln K_i(T_0) + b_i (1/T - 1/T_0) from the package's fugacity coefficients at
the stage's own liquid and vapour, phi_i^L(x) / phi_i^V(y) (the E equation of
Naphtali & Sandholm 1971), with the slope b_i from a second evaluation 2 K
above, and per-phase enthalpies split as the inside-out methods split them
(Boston & Sullivan 1974, Can. J. Chem. Eng. 52, 52; Russell 1983): the
mixture's ideal-gas enthalpy sum_i c_i h_i^ig(T), exact in the composition c,
plus a departure line h^R(T) = h^R_0 + c_p^R (T - T_0) frozen at the stage's
own phase. A composition-blind line h_0 + c_p (T - T_0) fails where a phase's
composition swings within a pass: on a steam-stripped crude column the
stripper vapour is near-pure steam one pass (h ~ 7 kJ/mol) and heavy
hydrocarbon the next (h^ig ~ 100x steam's per mole), so the stage reads
vaporising the hydrocarbon as nearly free, flashes to the band top, and the
relaxation locks into a limit cycle (measured on the crude_column R2 example:
130 K swings on the AGO stripper for all 80 passes, the Newton then starting
at M ~ 1). An adiabatic stage solves the Rachford-Rice equation (Rachford & Rice 1952,
J. Pet. Technol. 4(10), 19) inside a bracketed search on the stage enthalpy
balance; a stage whose vapour flow is a column tear (partial condenser,
kettle) solves Rachford-Rice at that vapour fraction for its temperature, its
duty being the outcome. The sweep runs over the stage graph (S0-1c): side
strippers are cascades of their own, linked by the liquid draw (derived from
the section's total balance, as the graph Newton derives it) and the vapour
return.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .graph_ns import _graph_model, _GraphModel
from .inside_out import _Column, _live_pumparounds, _Profile, _reflux_state, _RefluxState, _vapour_tear_stages
from .spec import _FLOW_FLOOR
from .thermo_adapter import _ThermoBox

#: Temperature step (K) of the second fugacity evaluation that gives each
#: component's ln K slope against 1/T.
_SLOPE_DT = 2.0
#: Shallowest admissible slope: ln K must rise with T (b < 0); a fitted slope
#: above this (noise at a trace component) is replaced by it (K).
_SLOPE_MAX = -50.0
#: Trace floor for the fugacity builds of a stage composition.
_TRACE = 1e-20
#: Outer passes (model refreshes), and the alternating down/up sweeps run on
#: each pass's frozen models: three pairs carry the pass's model change
#: through the column, while many sweeps on stale models only drift (measured
#: on the vacuum column: 400 sweeps per pass ran 60 s without settling).
_OUTER_MAX = 80
_INNER_SWEEPS = 6
#: Under-relaxation of the state between passes (see ``_relaxation_profile``).
_STATE_DAMP = 0.5
#: Converged when no stage temperature moves more than this (K) and no flow
#: more than this fraction of the total feed, pass to pass.
_OUTER_TOL_T = 1e-3
_OUTER_TOL_F = 1e-6
#: Iterations and bracket width (K) of one stage flash's temperature search.
_FLASH_ITER = 60
_FLASH_TOL_T = 1e-8
#: Rachford-Rice convergence on the vapour fraction.
_RR_TOL = 1e-13
#: Largest ln K the model evaluates (overflow guard on far extrapolation).
_LN_K_CAP = 300.0
#: Pressure (Pa) of the pure-component vapour builds that stand for the ideal
#: gas: Z = 1.000 to four figures for the heaviest crude pseudo up to 700 K.
_IG_P = 1.0


@dataclass
class _IdealGas:
    """Per-component ideal-gas enthalpies h_i^ig(T) over the column's
    temperature band: cubic Hermite through each pure component's ideal-gas
    enthalpy and cp at the band ends (pure vapour builds at ``_IG_P``). All
    zero when the package refuses a build: the stage enthalpy lines are then
    the composition-blind ones, departure = the whole phase enthalpy."""

    lo: float
    width: float
    h_lo: np.ndarray
    h_hi: np.ndarray
    cp_lo: np.ndarray
    cp_hi: np.ndarray

    def h(self, t: float) -> np.ndarray:
        s = (t - self.lo) / self.width
        s2, s3 = s * s, s * s * s
        out: np.ndarray = (
            (2.0 * s3 - 3.0 * s2 + 1.0) * self.h_lo
            + (s3 - 2.0 * s2 + s) * self.width * self.cp_lo
            + (-2.0 * s3 + 3.0 * s2) * self.h_hi
            + (s3 - s2) * self.width * self.cp_hi
        )
        return out

    def cp(self, t: float) -> np.ndarray:
        s = (t - self.lo) / self.width
        s2 = s * s
        out: np.ndarray = (
            (6.0 * s2 - 6.0 * s) * (self.h_lo - self.h_hi) / self.width
            + (3.0 * s2 - 4.0 * s + 1.0) * self.cp_lo
            + (3.0 * s2 - 2.0 * s) * self.cp_hi
        )
        return out


def _ideal_gas(col: _Column, tb: _ThermoBox) -> _IdealGas:
    """The column's per-component ideal-gas enthalpy table (see ``_IdealGas``)."""
    lo, hi = col.t_band_lo, col.t_band_hi
    nc = len(col.comps)
    rows: list[tuple[float, float, float, float]] = []
    try:
        for cid in col.comps:
            a = tb.phase_state({cid: 1.0}, lo, _IG_P, vapor=True)
            b = tb.phase_state({cid: 1.0}, hi, _IG_P, vapor=True)
            rows.append((a.enthalpy, b.enthalpy, a.cp, b.cp))
    except ValueError:
        zero = np.zeros(nc)
        return _IdealGas(lo, hi - lo, zero, zero, zero, zero)
    h_lo, h_hi, cp_lo, cp_hi = (np.array(col_) for col_ in zip(*rows, strict=True))
    return _IdealGas(lo, hi - lo, h_lo, h_hi, cp_lo, cp_hi)


@dataclass
class _StageModel:
    """Frozen local thermodynamics of one stage (see module docstring).

    A phase of composition c at T has the enthalpy ``ig.h(T) . c`` plus its
    departure line; the departure lines are (h^R_0, c_p^R) at t0."""

    t0: float
    ln_k0: np.ndarray
    slope: np.ndarray
    ig: _IdealGas
    h_liq: tuple[float, float]  # departure line of the stage liquid at t0
    h_vap: tuple[float, float]  # departure line of the stage vapour at t0
    h_cond: tuple[float, float] | None = None  # total-condenser reflux liquid at t0 + cond_dt
    cond_dt: float = 0.0  # reflux temperature less t0 (the condenser's bubble-dew gap)

    def k(self, t: float) -> np.ndarray:
        return np.exp(np.minimum(self.ln_k0 + self.slope * (1.0 / t - 1.0 / self.t0), _LN_K_CAP))

    def dl(self, t: float) -> float:
        return self.h_liq[0] + self.h_liq[1] * (t - self.t0)

    def dv(self, t: float) -> float:
        return self.h_vap[0] + self.h_vap[1] * (t - self.t0)

    def hl(self, t: float, x: np.ndarray) -> float:
        return float(self.ig.h(t) @ x) + self.dl(t)

    def hv(self, t: float, y: np.ndarray) -> float:
        return float(self.ig.h(t) @ y) + self.dv(t)

    def hc(self, t: float, x: np.ndarray) -> float:
        """The reflux liquid's enthalpy when stage 1 sits at t: the condenser
        returns it at t + cond_dt (its bubble point, ``_reflux_state``)."""
        if self.h_cond is None:
            return self.hl(t, x)
        return float(self.ig.h(t + self.cond_dt) @ x) + self.h_cond[0] + self.h_cond[1] * (t - self.t0)


def _full(comps: list[str], vec: np.ndarray) -> dict[str, float]:
    """A composition vector as a normalized dict with every component at least trace."""
    floored = np.maximum(vec, _TRACE)
    floored = floored / floored.sum()
    return {cid: float(v) for cid, v in zip(comps, floored, strict=True)}


def _vec(comps: list[str], comp: dict[str, float]) -> np.ndarray:
    return np.array([comp.get(c, 0.0) for c in comps])


def _refresh(
    col: _Column,
    tb: _ThermoBox,
    s: int,
    t: float,
    x: np.ndarray,
    y: np.ndarray,
    old: _StageModel | None,
    ig: _IdealGas,
    reflux: _RefluxState | None = None,
) -> _StageModel:
    """Stage model at (T, x, y): fugacity K and its 1/T slope, both departure lines.

    Each departure line is the built phase's enthalpy and cp less the ideal-gas
    mixture's at the same composition. Stage 1 under a total condenser also
    carries the reflux's liquid departure line at the condenser's outlet
    state (``reflux``: composition and bubble-point temperature, from
    ``_reflux_state``). A package that refuses a phase build keeps the
    stage's previous model.
    """
    p = col.pressures[s]
    xd, yd = _full(col.comps, x), _full(col.comps, y)
    cd = _full(col.comps, _vec(col.comps, reflux.x)) if reflux is not None else yd
    t_cond = reflux.T if reflux is not None else t
    try:
        liq = tb.phase_state(xd, t, p, vapor=False)
        vap = tb.phase_state(yd, t, p, vapor=True)
        liq2 = tb.phase_state(xd, t + _SLOPE_DT, p, vapor=False)
        vap2 = tb.phase_state(yd, t + _SLOPE_DT, p, vapor=True)
        cond = None
        if s == 0 and col.condenser == "total":
            cond = tb.phase_state(cd, t_cond, p, vapor=False)
    except ValueError:
        if old is not None:
            return old
        raise
    inv = 1.0 / (t + _SLOPE_DT) - 1.0 / t
    a = np.array([liq.ln_phi[c] - vap.ln_phi[c] for c in col.comps])
    a2 = np.array([liq2.ln_phi[c] - vap2.ln_phi[c] for c in col.comps])
    h_ig, cp_ig = ig.h(t), ig.cp(t)

    def departure(
        h: float, cp: float, comp: dict[str, float], h_at: np.ndarray = h_ig, cp_at: np.ndarray = cp_ig
    ) -> tuple[float, float]:
        c = _vec(col.comps, comp)
        return h - float(h_at @ c), cp - float(cp_at @ c)

    return _StageModel(
        t0=t,
        ln_k0=a,
        slope=np.minimum((a2 - a) / inv, _SLOPE_MAX),
        ig=ig,
        h_liq=departure(liq.enthalpy, liq.cp, xd),
        h_vap=departure(vap.enthalpy, vap.cp, yd),
        h_cond=(
            departure(cond.enthalpy, cond.cp, cd, ig.h(t_cond), ig.cp(t_cond)) if cond is not None else None
        ),
        cond_dt=t_cond - t,
    )


def _rachford_rice(z: np.ndarray, k: np.ndarray) -> float:
    """Vapour fraction beta in [0, 1] of z at K (Rachford & Rice 1952).

    0 for a subcooled liquid (sum z K <= 1), 1 for a superheated vapour
    (sum z / K <= 1); otherwise the root of sum z (K - 1) / (1 + beta (K - 1)),
    by Newton safeguarded with bisection on its bracket.
    """
    km1 = k - 1.0
    if float(np.dot(z, km1)) <= 0.0:
        return 0.0
    if float(np.dot(z, km1 / k)) >= 0.0:
        return 1.0
    lo, hi = 0.0, 1.0
    beta = 0.5
    for _ in range(100):
        ratio = km1 / (1.0 + beta * km1)
        val = float(np.dot(z, ratio))
        if val > 0.0:
            lo = beta
        else:
            hi = beta
        deriv = -float(np.dot(z, ratio * ratio))
        step = beta - val / deriv if deriv < 0.0 else 0.5 * (lo + hi)
        if not lo < step < hi:
            step = 0.5 * (lo + hi)
        if abs(step - beta) <= _RR_TOL:
            return step
        beta = step
    return beta


def _phase_split(z: np.ndarray, k: np.ndarray, beta: float) -> tuple[np.ndarray, np.ndarray]:
    """Liquid and vapour compositions of z at K and vapour fraction beta."""
    x = z / (1.0 + beta * (k - 1.0))
    x = x / x.sum()
    y = k * x
    return x, y / y.sum()


def _illinois(fn: Callable[[float], float], lo: float, hi: float) -> float:
    """Root of the increasing function fn on [lo, hi] (Illinois false position);
    the nearer bracket end when fn does not change sign there."""
    g_lo = fn(lo)
    if g_lo >= 0.0:
        return lo
    g_hi = fn(hi)
    if g_hi <= 0.0:
        return hi
    side = 0
    t = lo
    for _ in range(_FLASH_ITER):
        t = (lo * g_hi - hi * g_lo) / (g_hi - g_lo)
        if not lo < t < hi:
            t = 0.5 * (lo + hi)
        g_t = fn(t)
        if g_t > 0.0:
            hi, g_hi = t, g_t
            if side == 1:
                g_lo *= 0.5
            side = 1
        else:
            lo, g_lo = t, g_t
            if side == -1:
                g_hi *= 0.5
            side = -1
        if hi - lo <= _FLASH_TOL_T:
            break
    return t


def _stage_flash(
    model: _StageModel, z: np.ndarray, h_in: float, v_fixed: float | None, lo: float, hi: float
) -> tuple[float, float]:
    """(T, beta) of one stage on its frozen model.

    ``v_fixed`` is the tear vapour fraction (partial condenser, kettle); None
    solves the adiabatic stage on the molar enthalpy ``h_in``. Both residuals
    rise with T (K and the flash enthalpy do), so a bracketed search on the
    column's temperature band is safe.
    """
    if v_fixed is not None:
        beta_t = v_fixed

        def residual(t: float) -> float:
            km1 = model.k(t) - 1.0
            return float(np.dot(z, km1 / (1.0 + beta_t * km1)))

        return _illinois(residual, lo, hi), beta_t

    def energy(t: float) -> float:
        # beta h_V(y) + (1 - beta) h_L(x): the ideal-gas parts sum to z's
        # (beta y + (1 - beta) x = z at the Rachford-Rice root).
        beta = _rachford_rice(z, model.k(t))
        return float(model.ig.h(t) @ z) + beta * model.dv(t) + (1.0 - beta) * model.dl(t) - h_in

    t = _illinois(energy, lo, hi)
    return t, _rachford_rice(z, model.k(t))


@dataclass
class _State:
    """Relaxation state over the stage graph: per stage T, the vapour and
    liquid leaving to the cascade, x, y; the stripper draw flows; the total
    condenser's outlet state (None: no total condenser)."""

    t: list[float]
    v: list[float]
    liq: list[float]
    x: list[np.ndarray]
    y: list[np.ndarray]
    draws: list[float]
    reflux: _RefluxState | None = None


def _sweep(graph: _GraphModel, models: list[_StageModel], st: _State, l0: float, order: list[int]) -> None:
    """One Gauss-Seidel pass of stage flashes in ``order``.

    The stage graph's own topology (``_graph_model``): cascade donors, the
    stripper draws (each derived from its section's total balance, draw =
    returned vapour + product - section feeds, as the graph Newton derives
    it) and the vapour returns; a plain column is the graph without sections.
    """
    col = graph.col
    comps = col.comps
    tears = _vapour_tear_stages(col)
    returns = [
        (pa.return_stage - 1, pa.draw_stage - 1, col.pa_flows[idx], pa) for idx, pa in _live_pumparounds(col)
    ]
    for k, top, bottom, rate in graph.section_total_rows:
        steam = sum(graph.feeds[s].total for s in range(top, bottom + 1))
        st.draws[k] = max(st.v[top] + rate - steam, rate)
    draw_out = {graph.draw_stage_of_link[k]: st.draws[k] for k in range(len(st.draws))}
    for s in order:
        part = graph.feeds[s]
        f = np.array([part.l_flow * part.x.get(c, 0.0) + part.v_flow * part.y.get(c, 0.0) for c in comps])
        h = part.h_flow
        above = graph.liquid_donor[s]
        if above is not None:
            f = f + st.liq[above] * st.x[above]
            h += st.liq[above] * models[above].hl(st.t[above], st.x[above])
        elif s in graph.link_at_top:
            link = graph.link_at_top[s]
            d = graph.draw_stage_of_link[link]
            f = f + st.draws[link] * st.x[d]
            h += st.draws[link] * models[d].hl(st.t[d], st.x[d])
        below = graph.vapour_donor[s]
        if below is not None:
            f = f + st.v[below] * st.y[below]
            h += st.v[below] * models[below].hv(st.t[below], st.y[below])
        for top in graph.vapour_return_at.get(s, ()):
            f = f + st.v[top] * st.y[top]
            h += st.v[top] * models[top].hv(st.t[top], st.y[top])
        if s == 0 and col.condenser == "total":
            # The decanted liquid is frozen per pass with its state; a plain
            # condenser returns the current stage-1 vapour, condensed.
            reflux = _vec(comps, st.reflux.x) if (st.reflux is not None and col.water_decant) else st.y[0]
            f = f + l0 * reflux
            h += l0 * models[0].hc(st.t[0], reflux)
        for ret_j, draw_j, flow, pa in returns:
            if ret_j != s:
                continue
            f = f + flow * st.x[draw_j]
            if pa.return_T_K is not None:
                h += flow * models[draw_j].hl(pa.return_T_K, st.x[draw_j])
            else:
                h += flow * models[draw_j].hl(st.t[draw_j], st.x[draw_j]) + (pa.duty_W or 0.0)
        if col.stage_q and s < col.n:
            h += col.stage_q[s]
        h += graph.section_duty_at.get(s, 0.0)
        total = float(f.sum())
        if total <= _FLOW_FLOOR:
            continue
        z = f / total
        main = s < col.n
        v_side = col.draw_v[s] if main else 0.0
        l_side = (col.draw_l[s] + graph.pa_out[s] + draw_out.get(s, 0.0)) if main else 0.0
        v_fixed: float | None = None
        if main and s in tears:
            v_fixed = min(max((st.v[s] + v_side) / total, 1e-9), 1.0 - 1e-9)
        t, beta = _stage_flash(models[s], z, h / total, v_fixed, col.t_band_lo, col.t_band_hi)
        x, y = _phase_split(z, models[s].k(t), beta)
        if v_fixed is None:
            st.v[s] = max(beta * total - v_side, _FLOW_FLOOR)
        st.liq[s] = max((1.0 - beta) * total - l_side, _FLOW_FLOOR)
        st.t[s], st.x[s], st.y[s] = t, x, y


def _reflux(col: _Column, tb: _ThermoBox, st: _State) -> _RefluxState | None:
    """The total condenser's outlet state at the current stage-1 vapour
    (``_reflux_state``); None without a total condenser."""
    if col.condenser != "total":
        return None
    return _reflux_state(col, tb, _full(col.comps, st.y[0]), st.t[0])


def _relaxation_profile(col: _Column, tb: _ThermoBox, prof: _Profile) -> _Profile:
    """Relax ``prof`` (a seeded, tear-applied profile) to the stage-flash fixed point.

    Non-reactive, one-liquid columns (the parser's guard), plain or on the
    stage graph. The tears already written into ``prof`` (V_1 of a partial
    condenser, V_N of a kettle, the reflux L_0 of a total condenser) stay
    fixed; every other flow, every temperature and composition, and each
    stripper draw are the relaxation's. Each outer pass refreshes the stage
    models, runs ``_INNER_SWEEPS`` alternating sweeps on them, and
    under-relaxes the new state toward the pass's start by ``_STATE_DAMP``
    (undamped, the passes settle into a two-cycle: measured on the 6-stage
    vacuum column, the top stage alternating 611/630 K for 40 passes; damped
    by 0.5 the same column settles to M = 8.7e-6 in 27 passes). Returns a new
    profile; ``prof`` is not modified.
    """
    graph = _graph_model(col)
    g = col.n_graph
    comps = col.comps
    st = _State(
        t=[min(max(t, col.t_band_lo + 1.0), col.t_band_hi - 1.0) for t in prof.T[:g]],
        v=list(prof.V[:g]),
        liq=list(prof.L[:g]),
        x=[_vec(comps, prof.x[s]) for s in range(g)],
        y=[_vec(comps, prof.y[s]) for s in range(g)],
        draws=list(prof.draw_flows) or [0.0] * len(graph.section_total_rows),
    )
    st.reflux = _reflux(col, tb, st)
    ig = _ideal_gas(col, tb)
    models = [_refresh(col, tb, s, st.t[s], st.x[s], st.y[s], None, ig, st.reflux) for s in range(g)]
    scale = max(col.f_total, 1.0)
    down = list(range(g))
    up = down[::-1]
    for outer in range(_OUTER_MAX):
        t_prev, v_prev, l_prev = list(st.t), list(st.v), list(st.liq)
        x_prev, y_prev = list(st.x), list(st.y)
        for sweep in range(_INNER_SWEEPS):
            _sweep(graph, models, st, prof.l0, down if sweep % 2 == 0 else up)
        if outer > 0:
            w = _STATE_DAMP
            for s in range(g):
                st.t[s] = t_prev[s] + w * (st.t[s] - t_prev[s])
                st.v[s] = v_prev[s] + w * (st.v[s] - v_prev[s])
                st.liq[s] = l_prev[s] + w * (st.liq[s] - l_prev[s])
                xb = x_prev[s] + w * (st.x[s] - x_prev[s])
                yb = y_prev[s] + w * (st.y[s] - y_prev[s])
                st.x[s], st.y[s] = xb / xb.sum(), yb / yb.sum()
        moved_t = max(abs(a - b) for a, b in zip(st.t, t_prev, strict=True))
        moved_f = max(
            max(abs(a - b) for a, b in zip(st.v, v_prev, strict=True)),
            max(abs(a - b) for a, b in zip(st.liq, l_prev, strict=True)),
        )
        if outer > 0 and moved_t < _OUTER_TOL_T and moved_f < _OUTER_TOL_F * scale:
            break
        st.reflux = _reflux(col, tb, st)
        models = [_refresh(col, tb, s, st.t[s], st.x[s], st.y[s], models[s], ig, st.reflux) for s in range(g)]
    return _Profile(
        T=list(st.t),
        V=list(st.v),
        L=list(st.liq),
        x=[{c: float(v) for c, v in zip(comps, row, strict=True)} for row in st.x],
        y=[{c: float(v) for c, v in zip(comps, row, strict=True)} for row in st.y],
        l0=prof.l0,
        draw_flows=list(st.draws),
    )
