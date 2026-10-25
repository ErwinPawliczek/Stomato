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
    _V_TRAFFIC_CAP,
    ColumnConvergenceError,
    ColumnSpecError,
    _DrawSpec,
    _is_reactive_package,
    _Params,
    _Pumparound,
)
from .thermo_adapter import _flash_ready, _ThermoBox

#: Default slope of a stage's ln Kb = A + B/T line (K). K falls with T, so the
#: slope is negative; the magnitude is the Clausius-Clapeyron scale of the
#: light-hydrocarbon reference components (the thermo adapter's own CC fallback
#: uses the same 2500 K). Used until a stage's history has two distinct
#: temperatures to fit a slope from.
_KB_SLOPE_DEFAULT = -2500.0
#: (T, ln Kb) history points kept per stage for its correlation fit.
_KB_HIST_MAX = 4

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
    t: float = 0.0  # feed temperature, flow-weighted over the stage's feeds (K)


@dataclass
class _Column:
    """All static problem data for one solve. Stage index 0 = stage 1 (top)."""

    n: int
    condenser: str
    reboiler: str
    #: Number of column tears (boundary degrees of freedom): 0 for a
    #: feed-determined absorber, 1 for a reboiled stripper or a rectifier
    #: without reboiler, 2 for a condenser + kettle column.
    n_tears: int
    pressures: list[float]
    feeds: list[_StageFeed]
    draw_l: list[float]
    draw_v: list[float]
    draws: list[_DrawSpec]
    comps: list[str]
    f_total: float
    z_total: dict[str, float]
    feed_comp: dict[str, float]
    #: S0-1 pumparound loops (empty = none); pa_flows is the live flow per loop,
    #: in list order (it moves in feature 4's tear vector, fixed before that).
    pumparounds: list[_Pumparound] = field(default_factory=list)
    pa_flows: list[float] = field(default_factory=list)
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
    #: Reboiler duty added, W — the PHYSICAL reboiler duty. The overall energy
    #: balance is closed by folding the pumparound cooler duties in separately
    #: (``_close_energy_balance`` subtracts them), so this key never carries
    #: pumparound heat (review item 1, PR #238).
    qr: float = 0.0
    #: S0-1: one dict per pumparound loop (in spec order): flow, duty, draw and
    #: return temperatures. Empty without pumparounds.
    pa_report: list[dict[str, float]] = field(default_factory=list)
    outer: int = 0
    inner: int = 0
    ns_used: bool = False
    ns_passes: int = 0
    #: Per-pass Naphtali-Sandholm controller trace (P1-11 step 4): one line per
    #: pass - exact residuals, linear-model prediction, cap hits, damping and
    #: achieved reduction. Diagnostics only; never read for control flow.
    ns_trace: list[str] = field(default_factory=list)


def _flash_stage_feeds(col_params: _Params, tb: _ThermoBox) -> list[_StageFeed]:
    """Flash every feed and split it into the vapour/liquid parts entering its stage."""
    stage_feeds = [_StageFeed() for _ in range(col_params.n_stages)]
    for f in col_params.feeds:
        state = tb.pt(f.comp, f.T, f.P, f.flow)
        part = stage_feeds[f.stage - 1]
        part.total += f.flow
        part.t += f.T * f.flow
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
        if part.total > _FLOW_FLOOR:
            part.t /= part.total
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
        n_tears=(1 if col_params.condenser != "none" else 0) + (1 if col_params.reboiler != "none" else 0),
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
    col.pumparounds = list(col_params.pumparounds)
    pa_flows: list[float] = []
    for pa in col.pumparounds:
        # A free pumparound tear (S0-1 feature 4) carries no flow until the
        # generalized driver injects it; seed builds only read mass totals.
        pa_flows.append(pa.flow_mol_s if pa.flow_mol_s is not None else 0.0)
    col.pa_flows = pa_flows
    col.draw_l, col.draw_v = _draw_flows(col)
    # Clamp the inner temperature walk to a window around the physical operating
    # range: the seed estimates the distillate/bottoms temperatures, and stages
    # wandering far outside that range sit in single-phase states where the
    # equilibrium correlation degenerates and the profile collapses.
    if col.n_tears < 2:
        # Zero/one-tear columns take the band from the FEED temperatures: the
        # distillation seed's mixed-feed flash is not even evaluable on a
        # reactive package (gas + amine mixed overalls), and an absorber's
        # operating window is its feeds' window. The +80 K top headroom carries
        # the absorption exotherm (spec C). Only stages that carry feed enter
        # the window: feed-less stages keep part.t at its 0.0 default and would
        # otherwise drag the floor to -30 K.
        feed_ts = [part.t for part in feeds if part.total > _FLOW_FLOOR]
        col.t_band_lo = min(feed_ts) - 30.0
        col.t_band_hi = max(feed_ts) + 80.0
        if col.reboiler == "kettle":
            # A reboiled stripper's bottom stage sits at the kettle's bubble
            # point of the bottoms (spec P1-10) - for a top-fed nC4-rich
            # stripper at 2 MPa that is ~375-385 K, ABOVE the feed-based
            # ceiling of max(feed T) + 80 (300 + 80 = 380 K here). A ceiling
            # below the kettle's own operating point clamps the physical
            # profile at the band limit and the band-limit guard then rejects
            # it (measured: the boilup-ratio 0.8 physical root carries a
            # bottoms 4-5 K above 380 K). Extend the ceiling to cover the
            # estimated kettle temperature; the floor stays feed-based (the
            # band-floor branch is the failure mode, never the solution).
            xb = _nearest_feed_phase(col, col.n - 1, vapor=False)
            t_kettle = tb.bubble_temperature(_flash_ready(xb, col.feed_comp), col.pressures[-1])
            if t_kettle is not None:
                col.t_band_hi = max(col.t_band_hi, t_kettle + 15.0)
        return col
    t_top, t_bot = _temperature_seed(col, tb)
    if t_bot > t_top + 20.0:
        col.t_band_lo = max(t_top - 30.0, 150.0)
        col.t_band_hi = min(t_bot + 30.0, 600.0)
    return col


def _draw_flows(col: _Column) -> tuple[list[float], list[float]]:
    draw_l = [0.0] * col.n
    draw_v = [0.0] * col.n
    for d in col.draws:
        if d.flow is None:
            continue  # free tear (S0-1): its flow lives in col.draw_flows, not here
        if d.vapor:
            draw_v[d.stage - 1] += d.flow
        else:
            draw_l[d.stage - 1] += d.flow
    return draw_l, draw_v


def _pa_is_noop(pa: _Pumparound) -> bool:
    """A zero-duty loop returning where it drew is an exact no-op (spec identity).

    Skipping it keeps the solve bit-identical to the column without the loop:
    the terms cancel algebraically but not in floating point, and the ulp-level
    perturbation moves the inside-out path off the 1e-10 identity gate.
    """
    return pa.duty_W == 0.0 and pa.draw_stage == pa.return_stage


def _live_pumparounds(col: _Column) -> list[tuple[int, _Pumparound]]:
    return [(i, pa) for i, pa in enumerate(col.pumparounds) if not _pa_is_noop(pa)]


def _pa_return_terms(col: _Column) -> list[tuple[int, int, float]]:
    """Per live pumparound: (return stage idx, draw stage idx, flow), 0-based.

    Empty without pumparounds; no-op loops (zero duty, draw = return) skipped.
    """
    return [(pa.return_stage - 1, pa.draw_stage - 1, col.pa_flows[idx]) for idx, pa in _live_pumparounds(col)]


def _pa_stage_flows(col: _Column) -> tuple[list[float], list[float]]:
    """Per-stage pumparound net liquid outflow (at the draw) and inflow (at the return).

    Zeros everywhere without pumparounds. A pumparound with draw = return and
    zero duty contributes equal in/out at one stage: an exact no-op.
    """
    pa_out = [0.0] * col.n
    pa_in = [0.0] * col.n
    for idx, pa in _live_pumparounds(col):
        pa_out[pa.draw_stage - 1] += col.pa_flows[idx]
        pa_in[pa.return_stage - 1] += col.pa_flows[idx]
    return pa_out, pa_in


def _l_profile(col: _Column, l0: float, v: list[float]) -> list[float]:
    """Liquid profile from the stage-wise total balances, closed form:

    L_j = L_0 + sum_{m<=j}(F_m - S_m) + V_{j+1} - V_1  (V_{N+1} = 0),
    the telescoped sum of the stage total material balances.

    Pumparounds (S0-1) enter as extra liquid outflow at the draw stage and
    inflow at the return stage; the return is a feed, not cascade liquid, so
    both terms sit in the telescoped sum exactly like a feed and a draw.
    """
    out = []
    cum = 0.0
    v1 = v[0]
    if col.pumparounds:
        pa_out, pa_in = _pa_stage_flows(col)
        for j in range(col.n):
            cum += col.feeds[j].total - col.draw_l[j] - col.draw_v[j]
            cum += pa_in[j] - pa_out[j]
            v_above = v[j + 1] if j + 1 < col.n else 0.0
            out.append(max(l0 + cum + v_above - v1, _FLOW_FLOOR))
        return out
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

    Zero/one-tear columns skip the flash work entirely: their profile is linear
    between the topmost and bottommost feed temperatures (a single feed's T
    +/- 10 K). The mixed-feed flash the distillation estimates need is not even
    evaluable there - an absorber's mixed gas + amine composition is a state a
    reactive package cannot flash as a liquid.

    Two estimates for two-tear columns. (1) Pure-component extremes: coldest and hottest component
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
    if col.n_tears < 2:
        fed = [part for part in col.feeds if part.total > _FLOW_FLOOR]
        if len(fed) == 1:
            return fed[0].t - 10.0, fed[0].t + 10.0
        return fed[0].t, fed[-1].t
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


def _mixed_feed_seed(col: _Column, tb: _ThermoBox) -> tuple[float, dict[str, float], dict[str, float]] | None:
    """Adiabatic mixed-feed flash seed for zero/one-tear columns.

    The stage feeds already carry each feed's inlet enthalpy flow (flashed at
    its own T/P, which conserves enthalpy), so the mixed inlet state is
    sum(h_flow)/f_total J/mol over col.feed_comp. Bisect the mixed-feed
    composition's flash temperature until the flashed enthalpy matches - the
    single-stage adiabatic equilibrium the column's bulk operates near.
    Returns (T_ad, liquid-x, vapour-y) from that two-phase flash, or None when
    the mixed state is single-phase (no separation information to seed from).
    """
    f_tot = col.f_total
    if f_tot <= _FLOW_FLOOR:
        return None
    h_mix = sum(part.h_flow for part in col.feeds) / f_tot
    z = col.feed_comp
    p_mid = col.pressures[len(col.pressures) // 2]
    lo, hi = 150.0, 600.0
    t_ad = 0.5 * (lo + hi)
    for _ in range(40):
        t_ad = 0.5 * (lo + hi)
        h = tb.pt(z, t_ad, p_mid, f_tot).enthalpy
        if h > h_mix:
            hi = t_ad
        else:
            lo = t_ad
    state = tb.pt(z, t_ad, p_mid, f_tot)
    if not 1e-6 < state.vapor_fraction < 1.0 - 1e-6:
        return None
    vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
    liq = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
    if vap is None or liq is None:
        return None
    return t_ad, dict(liq.composition), dict(vap.composition)


def _nearest_feed_phase(col: _Column, j: int, vapor: bool) -> dict[str, float]:
    """Composition of the nearest feed's flashed phase (vapour or liquid).

    Nearest by stage distance; falls back to the mixed feed composition when no
    feed carries the wanted phase (a rectifier's only feed is vapour - the
    mixed composition is physical there, unlike a reactive absorber's).
    """
    best: tuple[int, dict[str, float]] | None = None
    for k, part in enumerate(col.feeds):
        flow = part.v_flow if vapor else part.l_flow
        comp = part.y if vapor else part.x
        if flow > _FLOW_FLOOR and comp and (best is None or abs(k - j) < abs(best[0] - j)):
            best = (k, comp)
    return dict(best[1]) if best is not None else dict(col.feed_comp)


def _seed_profile(
    col: _Column, tb: _ThermoBox, t_top: float, t_bot: float, v_bot_tear: float | None = None
) -> _Profile:
    """Starting profile: feed-traffic seed for zero/one-tear columns (spec C),
    the distillation-shaped seed for two-tear columns (unchanged).

    ``v_bot_tear`` is the pinned kettle boilup (None when there is no bottom
    tear): the vapour enters the bottom stage from below and rises through
    every stage, so it belongs in every stage's vapour-traffic sum - without it
    the stages above the kettle seed at the flow floor and the first sweeps
    solve from a degenerate column.
    """
    n = col.n
    if col.n_tears < 2:
        # V_j = vapour feed flow entering at or below stage j (vapour rises);
        # L_j = liquid feed flow entering at or above stage j (liquid falls).
        # Both floored so degenerate stages stay solvable.
        boilup = v_bot_tear if v_bot_tear is not None else 0.0
        vapour = [max(sum(part.v_flow for part in col.feeds[j:]) + boilup, _FLOW_FLOOR) for j in range(n)]
        liquid = [max(sum(part.l_flow for part in col.feeds[: j + 1]), _FLOW_FLOOR) for j in range(n)]
        l0 = max(0.5 * vapour[0], _FLOW_FLOOR) if col.condenser == "total" else 0.0
        temps = [t_top + (t_bot - t_top) * (j / max(n - 1, 1)) for j in range(n)]
        mixed = None
        if not _is_reactive_package(tb):
            # Multi-feed columns seed each stage's x from the nearest feed's
            # flashed phase. When those phases bracket the band - a lean
            # solvent flashing as near-pure liquid (bubble point above the
            # band ceiling) against a gas feed whose condensate bubbles below
            # the floor - the first inner solve pins stages to the band edges
            # and the fixed point never reaches the physical root (measured
            # P1-09 absorber, N=8/20: Tmin=270.0/Tmax=380.0 from sweep 1, then
            # stagnation at M ~ 5e-1 or convergence onto the spurious floor
            # root). The adiabatic mixed-feed flash gives the composition and
            # temperature the bulk of the column actually operates near
            # (measured absorber: T_ad = 293.1 K, x from its liquid phase -
            # squarely inside the band), so it replaces the nearest-feed
            # phases when it yields a two-phase state. Reactive packages
            # cannot flash a mixed gas + amine composition as a liquid and
            # keep the nearest-feed seed.
            try:
                mixed = _mixed_feed_seed(col, tb)
            except Exception:
                mixed = None
        if mixed is not None:
            t_ad, x_liq, y_vap = mixed
            temps = [t_ad] * n
            x = [dict(x_liq) for _ in range(n)]
            y = [dict(y_vap) for _ in range(n)]
        else:
            # x/y from the nearest feed's flashed phase - NEVER the mixed feed
            # composition, which a reactive package cannot evaluate as a liquid.
            x = [_nearest_feed_phase(col, j, vapor=False) for j in range(n)]
            y = [_nearest_feed_phase(col, j, vapor=True) for j in range(n)]
        if col.reboiler == "kettle":
            # A reboiled stripper's bottom stage sits at the kettle's bubble
            # point of the bottoms estimate, not the feed or mixed-feed
            # temperature (spec P1-10): the kettle supplies vapour at the
            # BOTTOM. The mixed/linear seeds put every stage at ~the feed
            # temperature, and the inside-out walk from a cold bottom stage
            # descended to the t_band_lo floor branch (measured P1-10 C1/nC4
            # stripper, 2 MPa, feed 300 K: cold solves at kettle V=26-40
            # landed on 270 K - the branch the band-limit guard rejects;
            # the physical branch runs 300-377 K). The bottoms estimate is
            # the liquid phase of the nearest feed to the bottom stage - for
            # a top-fed stripper, the feed's own flashed liquid. Ramp every
            # stage linearly up to it so the walk starts on the physical
            # side. Reactive packages (amine regenerators, spec P1-06) are
            # out of scope here: their chemistry is seeded by P1-06.
            xb = _nearest_feed_phase(col, n - 1, vapor=False)
            t_kettle = tb.bubble_temperature(_flash_ready(xb, col.feed_comp), col.pressures[-1])
            if t_kettle is not None and t_kettle > temps[-1]:
                temps = [temps[j] + (t_kettle - temps[-1]) * (j / max(n - 1, 1)) for j in range(n)]
        return _Profile(T=temps, V=vapour, L=liquid, x=x, y=y, l0=l0)
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
    """Frozen per-sweep models: raw K, alpha_ij, the ln Kb = A + B/T fit, enthalpy lines.

    Zero/one-tear columns additionally carry per-stage correlation lines
    (``corr_a_s``/``corr_b_s``) anchored on each stage's own (T, ln Kb) history
    (``kb_hist``) - the Boston-Sullivan scheme - instead of the column-wide fit.
    """

    k_raw: list[dict[str, float]]
    alpha: list[dict[str, float]]
    ref_comp: str
    corr_a: float
    corr_b: float
    h_vap: list[tuple[float, float, float]]  # (h0, cp, T_ref) per stage, vapour
    h_liq: list[tuple[float, float, float]]  # per stage, liquid
    h_cond: tuple[float, float, float] | None  # condensate (total-condenser reflux) line
    fit_T: list[float]  # temperatures the enthalpy lines were fitted at
    corr_a_s: list[float] = field(default_factory=list)  # per-stage intercepts (n_tears < 2)
    corr_b_s: list[float] = field(default_factory=list)  # per-stage slopes (n_tears < 2)
    kb_hist: tuple[tuple[tuple[float, float], ...], ...] = ()  # per-stage (T, ln Kb) points


def _fit_ln_kb(hist: tuple[tuple[float, float], ...], b_default: float) -> tuple[float, float]:
    """Least-squares ln Kb = A + B/T over one stage's (T, ln Kb) history points.

    Fewer than two distinct temperatures, a singular normal matrix, or a
    non-physical slope (K rises with T, so B must be negative) fall back to the
    given default slope anchored on the latest history point - the line passes
    exactly through the stage's freshest equilibrium state.
    """
    latest_t, latest_ln = hist[-1]
    if len(hist) >= 2:
        s_xx = sum(1.0 / (t * t) for t, _ in hist)
        s_x = sum(1.0 / t for t, _ in hist)
        s_y = sum(y for _, y in hist)
        s_xy = sum(y / t for t, y in hist)
        det = len(hist) * s_xx - s_x * s_x
        if abs(det) > 1e-300:
            b = (len(hist) * s_xy - s_x * s_y) / det
            a = (s_y - b * s_x) / len(hist)
            if math.isfinite(a) and math.isfinite(b) and b < 0.0:
                return a, b
    return latest_ln - b_default / latest_t, b_default


def _stage_overall_from_flows(
    col: _Column, j: int, x_j: dict[str, float], y_j: dict[str, float], l_flow: float, v_flow: float
) -> dict[str, float]:
    """Overall composition sitting on stage j: flows-weighted liquid, vapour and feed.

    The one overall construction behind ``_stage_overall`` and the stage-K
    evaluation - every caller weights the SAME four sources in the SAME order,
    so the gate and the Newton linearisation hand the package one composition.
    """
    part = col.feeds[j]
    total = l_flow + v_flow + part.total - col.draw_l[j] - col.draw_v[j]
    if total <= _FLOW_FLOOR:
        return col.feed_comp
    acc: dict[str, float] = {}
    for src_comp, src_flow in (
        (x_j, l_flow),
        (y_j, v_flow),
        (part.x, part.l_flow),
        (part.y, part.v_flow),
    ):
        for cid, frac in src_comp.items():
            acc[cid] = acc.get(cid, 0.0) + frac * src_flow
    return {cid: v / total for cid, v in acc.items() if v > 0.0} or col.feed_comp


def _stage_overall(col: _Column, prof: _Profile, j: int) -> dict[str, float]:
    """Overall composition sitting on stage j, from the profile's stage state."""
    return _stage_overall_from_flows(col, j, prof.x[j], prof.y[j], prof.L[j], prof.V[j])


def _stage_k_values(
    col: _Column,
    tb: _ThermoBox,
    j: int,
    x_j: dict[str, float],
    y_j: dict[str, float],
    t_j: float,
    l_flow: float,
    v_flow: float,
) -> dict[str, float] | None:
    """THE stage-K evaluation (P1-11 ruling on issue #153): one owner, one surface.

    The exact gate (``_exact_residuals``), the inside-out model refresh
    (``_refresh_model``), the y refresh (``_refresh_y``) and the
    Naphtali-Sandholm residual (``_live_k``) all evaluate THIS function, so the
    FD-Jacobian linearisation and the gate read the same K surface by
    construction - the ruling's two-K-surfaces mechanism (the NS residual built
    its stage overall without the stage's own vapour term while the gate
    weighted the stored y in) is closed by having every caller evaluate the
    same function with the same candidate chain and fallbacks.

    ``y_j`` is the caller's current estimate of the stage vapour: the profile's
    refreshed y = K*x on the mesh side, an empty dict from the NS trial (whose
    outgoing vapour is what that solve is computing - the M rows derive it as
    K*x from the live K themselves). Returns None when the stage's equilibrium
    is not evaluable from any candidate (liquid x, stage overall, feed);
    callers apply their documented fallbacks.
    """
    return tb.k_values(
        [
            _flash_ready(x_j, col.feed_comp),
            _flash_ready(_stage_overall_from_flows(col, j, x_j, y_j, l_flow, v_flow), col.feed_comp),
            col.feed_comp,
        ],
        t_j,
        col.pressures[j],
    )


def _refresh_model(col: _Column, tb: _ThermoBox, prof: _Profile, model: _InnerModel | None) -> _InnerModel:
    """One outer sweep: real K-values per stage, alpha against a column-wide reference
    component, the ln Kb = A + B/T correlation (least squares over the stage points),
    and per-stage linear enthalpy models (refitted only when temperatures moved)."""
    n = col.n
    k_stages: list[dict[str, float]] = []
    for j in range(n):
        k = _stage_k_values(col, tb, j, prof.x[j], prof.y[j], prof.T[j], prof.L[j], prof.V[j])
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None and model is not None:
            k = model.k_raw[j]
        k_stages.append(k or {cid: 1.0 for cid in col.comps})

    weights = {
        cid: sum(k_stages[j].get(cid, 0.0) * prof.x[j].get(cid, 0.0) for j in range(n)) for cid in col.comps
    }
    if model is not None and col.n_tears < 2:
        # Boston-Sullivan: the reference component is FIXED for the whole solve.
        # Re-picking it every sweep from the x-weighted K sums flips Kb between
        # components as the compositions sharpen (measured P1-09 C1/nC4 absorber:
        # nC4 at sweep 1, C1 from sweep 2, because K_C1 ~ 8.5 >> K_nC4 ~ 0.15
        # wins the weights as soon as x_C1 ~ 0.1). The flip drops a different
        # component's (T, ln Kb) points into each stage's history, the fitted
        # line stops passing through the stage's own equilibrium state, and the
        # inner temperature walk marches to the band floor (measured: every
        # stage pinned at t_band_lo = 270 K with 5e-2 component-balance errors).
        ref_comp = model.ref_comp
    else:
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

    # Per-stage ln Kb = A + B/T lines (zero/one-tear columns, spec D): Boston-
    # Sullivan anchors each stage's reference-K correlation on the stage's OWN
    # (T, ln Kb) history instead of one column-wide least-squares fit. At the
    # isothermal start every stage sits at the same T, the column-wide fit is
    # degenerate (no slope information), and its noise walks the stages out of
    # the two-phase window (measured on the 8/20-stage absorber: the walk never
    # recovers). Gated on the configuration - the two-tear path is unchanged.
    corr_a_s: list[float] = []
    corr_b_s: list[float] = []
    kb_hist_new: list[tuple[tuple[float, float], ...]] = []
    if col.n_tears < 2:
        for j in range(n):
            ln_kb = math.log(kb[j])
            prev_hist = model.kb_hist[j] if model is not None and j < len(model.kb_hist) else ()
            hist = ((*prev_hist, (prof.T[j], ln_kb)))[-_KB_HIST_MAX:]
            b_prev = model.corr_b_s[j] if model is not None and j < len(model.corr_b_s) else _KB_SLOPE_DEFAULT
            a_fit, b_fit = _fit_ln_kb(hist, b_prev)
            if model is not None and j < len(model.corr_b_s):
                # Boston-Sullivan feedback damping on the fitted SLOPE only: the
                # history's (T, ln Kb) points come from different composition
                # states, so an undamped refit drifts. Blending the intercept as
                # well drags the line OFF the stage's current equilibrium point
                # (measured P1-09 absorber, sweep 2: line(T) = 0.19 against a
                # true thermo ln Kb of 2.16 at the same T) and the temperature
                # walk then aims at a bogus temperature - the march to the band
                # floor. The intercept is therefore re-anchored instead:
                a_fit = ln_kb - b_fit / prof.T[j]
                # the line passes exactly through the stage's freshest
                # equilibrium state (T_j, ln Kb_j) every sweep - the property
                # that makes the inner T update a consistent Newton step along
                # the correlation (measured: the absorber closes at machine
                # precision when the line is anchored, in <= 8 sweeps).
            corr_a_s.append(a_fit)
            corr_b_s.append(b_fit)
            kb_hist_new.append(hist)

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
        corr_a_s=corr_a_s,
        corr_b_s=corr_b_s,
        kb_hist=tuple(kb_hist_new),
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
    # S0-1: pumparound draws widen the stage diagonal, returns widen the rhs.
    pa_out, _ = _pa_stage_flows(col)
    pa_return_terms = _pa_return_terms(col)
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
            if pa_out[j]:
                diag[j] -= pa_out[j]
            if j < n - 1:
                up[j] = prof.V[j + 1] * k[j + 1].get(cid, 1.0)
            rhs[j] = -(part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0))
            for ret_j, draw_j, flow in pa_return_terms:
                if ret_j == j:
                    rhs[j] -= flow * prof.x[draw_j].get(cid, 0.0)
        sol = _thomas(sub, diag, up, rhs)
        out.append([max(v, 0.0) for v in sol])
    return out


def _vapour_tear_stages(col: _Column) -> frozenset[int]:
    """Stage indices (0-based) whose vapour flow is a column tear, not an outcome.

    THE one definition of the vapour-tear rule, shared by every solver module
    (inside-out H stages, free-vapour indices, tear application, NS packing):
    V_1 (stage 0) is the top tear for a partial condenser - the distillate
    leaves as stage-1 vapour - and V_N (stage n-1) is the bottom tear for a
    kettle reboiler (the boilup). A total condenser's tear is the reflux L_0,
    a liquid flow above stage 1; a configuration without the hardware has no
    tear there at all, and the stage vapour is an enthalpy-balance outcome.
    """
    tears: set[int] = set()
    if col.condenser == "partial":
        tears.add(0)
    if col.reboiler == "kettle":
        tears.add(col.n - 1)
    return frozenset(tears)


def _h_equation_stages(col: _Column) -> list[int]:
    """Stages whose energy balance closes with the profile (duty-output stages drop out).

    The duty-output stages are exactly the vapour-tear stages: a partial
    condenser's and a kettle reboiler's own balances define qc/qr instead.
    """
    tears = _vapour_tear_stages(col)
    return [j for j in range(col.n) if j not in tears]


def _v_free_indices(col: _Column) -> list[int]:
    """Vapour flows the enthalpy system may correct: every non-tear stage's V."""
    tears = _vapour_tear_stages(col)
    return [j for j in range(col.n) if j not in tears]


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

    # S0-1: pumparound enthalpy couplings are v-independent here (temperatures
    # and enthalpy lines are frozen), so they are constants of the H solve.
    # Live loops only: a no-op loop (zero duty, draw = return) contributes
    # flow*h_draw to BOTH dicts at one stage and cancels algebraically but not
    # bit-exactly - skipping it keeps the solve identical to the plain column.
    # The return enthalpy is evaluated at the DRAW-stage pressure: a subcooled
    # liquid's enthalpy is pressure-insensitive, and the return stage sits at
    # the (higher) draw-side pressure to within the column's dP (S0-1).
    pa_h_in: dict[int, float] = {}
    pa_h_out: dict[int, float] = {}
    for idx, pa in _live_pumparounds(col):
        flow = col.pa_flows[idx]
        d_idx = pa.draw_stage - 1
        h_draw = _enthalpy_at(model.h_liq[d_idx], prof.T[d_idx])
        if pa.return_T_K is not None:
            h_return = _enthalpy_at(model.h_liq[d_idx], pa.return_T_K)
        else:
            h_return = h_draw + (pa.duty_W if pa.duty_W is not None else 0.0) / flow
        pa_h_out[d_idx] = pa_h_out.get(d_idx, 0.0) + flow * h_draw
        pa_h_in[pa.return_stage - 1] = pa_h_in.get(pa.return_stage - 1, 0.0) + flow * h_return

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
            if pa_h_in or pa_h_out:
                h_in += pa_h_in.get(j, 0.0)
                h_out += pa_h_out.get(j, 0.0)
            out.append(h_in - h_out)
        return out

    v_work = list(prof.V)
    if t_bot_tear is not None:
        v_work[n - 1] = t_bot_tear
    # Degenerate subcooled-band walks drove free vapour past 1e9 mol/s and
    # singularized the tridiagonal M system; cap the traffic the H solve may
    # demand (spec D). No physical column approaches the cap (measured on the
    # two-tear bench column: untouched).
    v_cap = _V_TRAFFIC_CAP * max(col.f_total, 1.0)
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
        candidate[vk] = min(max(v_work[vk] + step[idx], _FLOW_FLOOR), v_cap)
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
            refined[vk] = min(max(candidate[vk] + step[idx], _FLOW_FLOOR), v_cap)
        if t_bot_tear is not None:
            refined[n - 1] = t_bot_tear
        candidate = refined
    return candidate


def _inner_solve(col: _Column, model: _InnerModel, prof: _Profile, t_bot_tear: float | None) -> int:
    """The inside-out inner loop: M -> bubble (Kb) -> T (correlation) -> H (Newton).

    With alpha, the Kb correlation and the enthalpy lines frozen, the loop
    iterates until flows and temperatures stop moving. No thermo calls: every
    flash lives in the outer refresh, keeping the inner loop flash-free (a
    live per-iteration bubble solve was measured at unbounded flash cost on
    degenerate states and abandoned, P1-09).
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
            corr_a_j, corr_b_j = (
                (model.corr_a_s[j], model.corr_b_s[j]) if col.n_tears < 2 else (model.corr_a, model.corr_b)
            )
            denom = math.log(kb[j]) - corr_a_j
            t_corr = corr_b_j / denom if abs(denom) > 1e-12 else t_old[j]
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


def _stage_equilibrium(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    xs: list[dict[str, float]],
    ts: list[float],
    vs: list[float],
    y_estimates: list[dict[str, float]] | None = None,
    k_fallbacks: list[dict[str, float]] | None = None,
    k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] | None = None,
    k_misses: list[int] | None = None,
) -> tuple[list[dict[str, float] | None], list[dict[str, float]]]:
    """Per-stage live K dictionaries and the equilibrium vapour y = K*x they imply.

    One owner of the stage-K candidate chain (live `_stage_k_values`, then the
    k_estimate fallback, then the caller's pass-frozen K models) and of the
    y = K*x construction read from it - shared by `_live_residual_vector` and
    `_residual_scales` so a residual row and its scale are always derived from
    the same K surface by construction (P1-11 ruling (c) on #153).
    """
    liquid = _l_profile(col, l0, vs)
    k_stages: list[dict[str, float] | None] = []
    for j in range(col.n):
        k: dict[str, float] | None = None
        if k_cache is not None:
            key = (tuple(sorted(xs[j].items())), round(ts[j], 12), col.pressures[j])
            k = k_cache.get(key)
        if k is None:
            if k_misses is not None:
                k_misses[0] += 1
            y_est = y_estimates[j] if y_estimates is not None else {}
            k = (
                _stage_k_values(col, tb, j, xs[j], y_est, ts[j], liquid[j], vs[j])
                or tb.k_estimate(_flash_ready(xs[j], col.feed_comp), ts[j], col.pressures[j])
                or (k_fallbacks[j] if k_fallbacks is not None else None)
            )
            if k_cache is not None and k is not None:
                k_cache[key] = k
        k_stages.append(k)
    y_eq: list[dict[str, float]] = []
    for j in range(col.n):
        k = k_stages[j]
        if k is None:
            y_eq.append({})
            continue
        y_j = {cid: k.get(cid, 1.0) * xs[j].get(cid, 0.0) for cid in col.comps}
        total = sum(y_j.values())
        y_eq.append({cid: v / total for cid, v in y_j.items()} if total > _FLOW_FLOOR else y_j)
    return k_stages, y_eq


def _m_row_flows(
    col: _Column,
    l0: float,
    xs: list[dict[str, float]],
    vs: list[float],
    y_eq: list[dict[str, float]],
) -> list[tuple[float, float]]:
    """Per (stage, component) in vector order: the M balance row's (inflow, outflow).

    One owner of the M balance algebra: `_live_residual_vector` divides these
    by their scales to form the rows and `_residual_scales` applies the scale
    rule to them - so a row and its scale come from the same numbers by
    construction (P1-11 ruling (c) on #153).
    """
    liquid = _l_profile(col, l0, vs)
    n = col.n
    pa_out, _pa_in = _pa_stage_flows(col)
    pa_return_terms = _pa_return_terms(col)
    flows: list[tuple[float, float]] = []
    for j in range(n):
        part = col.feeds[j]
        pa_ret = [(draw_j, flow) for ret_j, draw_j, flow in pa_return_terms if ret_j == j]
        for cid in col.comps:
            inflow = liquid[j - 1] * xs[j - 1].get(cid, 0.0) if j > 0 else 0.0
            if j == 0 and col.condenser == "total":
                inflow = l0 * y_eq[0].get(cid, 0.0)
            inflow += vs[j + 1] * y_eq[j + 1].get(cid, 0.0) if j + 1 < n else 0.0
            inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
            for draw_j, flow in pa_ret:
                inflow += flow * xs[draw_j].get(cid, 0.0)
            outflow = (liquid[j] + col.draw_l[j]) * xs[j].get(cid, 0.0) + (vs[j] + col.draw_v[j]) * y_eq[
                j
            ].get(cid, 0.0)
            if pa_out[j]:
                outflow += pa_out[j] * xs[j].get(cid, 0.0)
            flows.append((inflow, outflow))
    return flows


def _residual_scales(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    xs: list[dict[str, float]],
    ts: list[float],
    vs: list[float],
    y_estimates: list[dict[str, float]] | None = None,
    k_fallbacks: list[dict[str, float]] | None = None,
    k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] | None = None,
    k_misses: list[int] | None = None,
) -> list[float]:
    """The per-M-row scale vector of `_live_residual_vector`, evaluated at a reference state.

    P1-11 ruling (c) on issue #153: the scale rule is the gate's own
    ``max(|inflow|, |outflow|, col.f_total * 1e-6)`` - but evaluated HERE,
    once, at the reference state the caller hands in (for NS: the iterate the
    Jacobian is built from), never inside the residual evaluation itself. A
    scale derived per evaluation from the state being evaluated makes a row
    ``(in - out)/max(|in|, |out|)`` bounded in [-1, 1] and identical (-1)
    for every step in which the outflow dominates: not a smooth function of
    the unknowns, so Newton's linear model of it is meaningless exactly there
    and a max-norm descent test on it rejects the very full steps that reduce
    the true imbalance (measured: the N4-r0.8 stripper's bottom-stage
    light-key row, every line-search trial rejected, the 30-pass budget
    exhausted while a 0.5x-per-pass crawl was accepted). Frozen once per NS
    pass, the residual is linear in the flows within the pass, the linear
    model's predicted reduction is comparable to the achieved one, and no row
    can saturate. The exact gate keeps the frozen-from-the-gated-state
    semantics by passing no scales. Used on the NS live-norm (zero/one-tear)
    path only: the warm two-tear path keeps per-evaluation scales - measured
    regression there (see `_naphtali_sandholm`).
    """
    k_stages, y_eq = _stage_equilibrium(col, tb, l0, xs, ts, vs, y_estimates, k_fallbacks, k_cache, k_misses)
    flows = _m_row_flows(col, l0, xs, vs, y_eq)
    return [max(abs(inflow), abs(outflow), col.f_total * 1e-6) for inflow, outflow in flows]


def _live_residual_vector(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    xs: list[dict[str, float]],
    ts: list[float],
    vs: list[float],
    y_estimates: list[dict[str, float]] | None = None,
    k_fallbacks: list[dict[str, float]] | None = None,
    k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] | None = None,
    k_misses: list[int] | None = None,
    h_evals: list[int] | None = None,
    scales: list[float] | None = None,
) -> list[float]:
    """The ONE MESH residual vector, evaluated live (P1-11 step 2, ruling on #153).

    Row set per stage j, in this order: one M balance per component, the
    canonical NS summation row sum_i x_ij (1 - K_ij) = 0, and an H row on
    every duty-bearing stage. One convention throughout: y_ij = K_ij(T_j,
    x_j) * x_ij read from the live package (the gate's equilibrium-consistent
    reading), M rows scaled per row by max(|inflow|, |outflow|,
    col.f_total * 1e-6) and H rows by max(col.f_total * 2e4, 1.0) - the
    exact gate's own scaling.

    ``_exact_residuals`` reads its max-norms from this vector, and the
    Naphtali-Sandholm fallback builds its FD Jacobian, its LM damping and its
    line-search norms on the same vector - the gate, the Newton linearisation
    and the acceptance norm are one residual by construction (the ruling's
    step-2 rule: no frozen enthalpy models and no absolute rows remain in NS).

    ``y_estimates``: the caller's current vapour estimates handed to the shared
    stage-K evaluation (the profile's refreshed y = K*x from the gate; empty
    dicts from NS, whose outgoing vapour the M rows derive as K*x themselves -
    the measured variant-A choice, P1-11 step 1). ``k_fallbacks``: per-stage
    last-resort K dictionaries (the NS pass's frozen K models) used when
    neither the live evaluation nor the k_estimate fallback is evaluable; the
    gate passes None and treats a still-unevaluable stage as unconverged (each
    of its rows reads 1.0). ``k_cache``: an optional per-stage K cache keyed by
    (composition, T, P) so a finite-difference Jacobian over the packed
    unknowns flashes only the perturbed stage. ``k_misses``/``h_evals``:
    optional one-element counters (K evaluations beyond the cache, live
    enthalpy evaluations) for the flash-cost measurement the ruling requires.
    ``scales`` (P1-11 ruling (c) on #153): an explicit frozen per-row M scale
    vector from `_residual_scales` - computed once per NS pass from the pass's
    reference state and held fixed for the FD Jacobian, every line-search
    trial and the acceptance test of that pass. When None (the exact gate),
    the scale is derived from the state being evaluated - the gate freezes the
    scale from the state it gates, the only place a frozen quantity differs.
    """
    n = col.n
    liquid = _l_profile(col, l0, vs)
    h_scale = max(col.f_total * 2e4, 1.0)
    h_stage_set = set(_h_equation_stages(col))
    k_stages, y_eq = _stage_equilibrium(col, tb, l0, xs, ts, vs, y_estimates, k_fallbacks, k_cache, k_misses)
    flows = _m_row_flows(col, l0, xs, vs, y_eq)
    # S0-1: live pumparound enthalpy couplings (real package enthalpies at the
    # draw-stage composition; the return is that liquid subcooled by the duty
    # or fixed at return_T_K).
    pa_h_in: dict[int, float] = {}
    pa_h_out: dict[int, float] = {}
    live_pas = _live_pumparounds(col)
    if live_pas:
        for idx, pa in live_pas:
            flow = col.pa_flows[idx]
            d_idx = pa.draw_stage - 1
            x_d = _flash_ready(xs[d_idx], col.feed_comp)
            h_draw = tb.h_liquid(x_d, ts[d_idx], col.pressures[d_idx])
            if pa.return_T_K is not None:
                h_ret = tb.h_liquid(x_d, pa.return_T_K, col.pressures[d_idx])
            else:
                h_ret = h_draw + (pa.duty_W if pa.duty_W is not None else 0.0) / flow
            pa_h_out[d_idx] = pa_h_out.get(d_idx, 0.0) + flow * h_draw
            pa_h_in[pa.return_stage - 1] = pa_h_in.get(pa.return_stage - 1, 0.0) + flow * h_ret
    out: list[float] = []
    flow_pos = 0
    for j in range(n):
        k = k_stages[j]
        part = col.feeds[j]
        if k is None:
            flow_pos += len(col.comps)
            # The gate's "not evaluable is NOT converged" semantics: each row
            # of the stage reads 1.0 (same number the gate's max-norm saw).
            for _ in col.comps:
                out.append(1.0)
            out.append(1.0)
            if j in h_stage_set:
                out.append(1.0)
            continue
        for _cid in col.comps:
            inflow, outflow = flows[flow_pos]
            flow_pos += 1
            if scales is not None:
                scale = scales[flow_pos - 1]
            else:
                scale = max(abs(inflow), abs(outflow), col.f_total * 1e-6)
            out.append((inflow - outflow) / scale)
        # Canonical NS summation row (Naphtali & Sandholm 1971): sum_i x_ij
        # = sum_i K_ij x_ij, i.e. the bubble condition sum_i x_ij (1 - K_ij)
        # = 0. The former sum(x) - 1 form made the row vanish whenever K was
        # near 1 for every component (wide absorber mid-stages), so the row
        # carried no temperature information exactly where the walk needed
        # it; this form scales with the local volatility spread.
        out.append(sum(xs[j].values()) - sum(k.get(cid, 1.0) * xs[j].get(cid, 0.0) for cid in col.comps))
        if j not in h_stage_set:
            continue  # duty-output stage: its balance defines the duty (qc/qr)
        h_in = (
            (
                vs[j + 1]
                * tb.h_vapor(_flash_ready(y_eq[j + 1], col.feed_comp), ts[j + 1], col.pressures[j + 1])
                if j + 1 < n
                else 0.0
            )
            + (
                liquid[j - 1]
                * tb.h_liquid(_flash_ready(xs[j - 1], col.feed_comp), ts[j - 1], col.pressures[j - 1])
                if j > 0
                else 0.0
            )
            + part.h_flow
        )
        if j == 0 and col.condenser == "total":
            h_in += l0 * tb.h_liquid(_flash_ready(y_eq[0], col.feed_comp), ts[0], col.pressures[0])
        h_out = (vs[j] + col.draw_v[j]) * tb.h_vapor(
            _flash_ready(y_eq[j], col.feed_comp), ts[j], col.pressures[j]
        ) + (liquid[j] + col.draw_l[j]) * tb.h_liquid(
            _flash_ready(xs[j], col.feed_comp), ts[j], col.pressures[j]
        )
        if col.pumparounds:
            h_in += pa_h_in.get(j, 0.0)
            h_out += pa_h_out.get(j, 0.0)
        if h_evals is not None:
            h_evals[0] += 4
        out.append((h_in - h_out) / h_scale)
    return out


def _residual_row_blocks(col: _Column, h_stages: list[int]) -> tuple[list[int], list[int]]:
    """Indices of the M rows and of the H rows in `_live_residual_vector`'s output.

    The layout is fixed by construction (per stage: one M row per component,
    one summation row, then one H row on duty-bearing stages - including the
    unevaluable-stage placeholder rows), so the block indices are computable
    without evaluating the residual.
    """
    m_idx: list[int] = []
    h_idx: list[int] = []
    pos = 0
    nc = len(col.comps)
    h_set = set(h_stages)
    for j in range(col.n):
        m_idx.extend(range(pos, pos + nc))
        pos += nc + 1
        if j in h_set:
            h_idx.append(pos)
            pos += 1
    return m_idx, h_idx


def _exact_residuals(col: _Column, tb: _ThermoBox, prof: _Profile) -> tuple[float, float]:
    """Max relative MESH residuals with real thermo K-values and phase enthalpies.

    The honest convergence measure: the frozen inner models closed the equations,
    and the refreshed thermo values must still close them.

    The gate IS the shared live residual: it reads its max-norms from
    `_live_residual_vector` (the one residual the Naphtali-Sandholm fallback
    linearises and tests - P1-11 step 2, ruling on #153), evaluated at the
    profile state with the profile's refreshed y = K*x as the stage-K vapour
    estimates. The balances and enthalpy residuals read y_ij = K_ij(T_j, x_j) *
    x_ij from the live package, not the profile's STORED y (built as alpha*Kb*x
    from the inside-out anchor). On the reactive package the anchor tracks the
    acid-gas K-values' temperature dependence but not their composition
    (loading) dependence: an anchor-consistent state read M = 5.2e-3 on stored y
    while the same state read M = 0.49 on y = K*x (measured 20-stage MDEA
    absorber at the accepted inside-out state) - the stored-y gate was a gate
    hole, not a solver floor.

    Non-reactive cost (measured, bench-column trace on the step-3 branch: the two
    readings agree to a factor <= 5 mid-walk and reach the same < 1e-8 floor -
    outer sweep 28: stored-y M = 8.1e-10 vs K*x M = 6.8e-9), so the honest gate
    crosses 1e-8 one to three sweeps later per solve and the bench `column` case
    moves 4959 -> 6508 flash-equivalents with byte-identical products; the
    baseline moved with that trace per the ruling. The k = None guard is
    preserved: a stage whose equilibrium cannot be evaluated is NOT converged
    (skipping it let degenerate all-liquid profiles read as exact).
    """
    vec = _live_residual_vector(col, tb, prof.l0, prof.x, prof.T, prof.V, y_estimates=list(prof.y))
    m_idx, h_idx = _residual_row_blocks(col, _h_equation_stages(col))
    max_m = max((abs(vec[i]) for i in m_idx), default=0.0)
    max_h = max((abs(vec[i]) for i in h_idx), default=0.0)
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
    prof.pa_report = _pa_reports(col, tb, prof)


def _pa_return_temperature(
    tb: _ThermoBox,
    comp: dict[str, float],
    p: float,
    target_h: float,
    t_draw: float,
    t_lo: float,
    t_hi: float,
    name: str,
) -> float:
    """Liquid temperature whose enthalpy is ``target_h`` (deterministic bisection).

    h_liquid rises monotonically with T for any real package. A target outside
    the bracket [h(t_lo), h(t_hi)] is a specification the column cannot reach
    (the cooled return would leave the two-phase operating band): refused with
    a typed error, never papered over with a fallback temperature — a fallback
    would report return_T = draw_T together with a non-zero fixed duty, an
    inconsistent pair (review item 5, PR #238).
    """
    h_lo = tb.h_liquid(comp, t_lo, p)
    h_hi = tb.h_liquid(comp, t_hi, p)
    if not (h_lo < target_h < h_hi):
        raise ColumnSpecError(
            f"pumparound '{name}': return enthalpy {target_h:.6g} J/mol is outside the "
            f"achievable bracket [h({t_lo:.1f} K) = {h_lo:.6g}, h({t_hi:.1f} K) = {h_hi:.6g}] "
            f"at {p:.3g} Pa — the fixed duty is not reachable by cooling in this column's "
            f"operating window"
        )
    for _ in range(80):
        mid = 0.5 * (t_lo + t_hi)
        if tb.h_liquid(comp, mid, p) < target_h:
            t_lo = mid
        else:
            t_hi = mid
    return 0.5 * (t_lo + t_hi)


def _pa_reports(col: _Column, tb: _ThermoBox, prof: _Profile) -> list[dict[str, float]]:
    """Per-pumparound converged operating state (S0-1), reported in ``info``.

    Keys per loop: flow (mol/s), the cooler duty (W, negative = heat removed),
    the draw temperature and the return temperature (K). With a fixed
    ``return_T_K`` the duty follows from the draw enthalpy; with a fixed duty
    the return temperature is bisected on the package's liquid enthalpy.
    """
    reports: list[dict[str, float]] = []
    for idx, pa in enumerate(col.pumparounds):
        flow = col.pa_flows[idx]
        d_idx = pa.draw_stage - 1
        comp = _flash_ready(prof.x[d_idx], col.feed_comp)
        t_draw = prof.T[d_idx]
        # The return enthalpy is evaluated at the DRAW-stage pressure: fine for
        # a subcooled liquid, whose enthalpy is pressure-insensitive, and the
        # return stage sits above the draw at near-identical pressure (S0-1).
        p = col.pressures[d_idx]
        h_draw = tb.h_liquid(comp, t_draw, p)
        if pa.return_T_K is not None:
            t_return = pa.return_T_K
            h_return = tb.h_liquid(comp, t_return, p)
        else:
            h_return = h_draw + (pa.duty_W if pa.duty_W is not None else 0.0) / flow
            t_return = _pa_return_temperature(
                tb, comp, p, h_return, t_draw, col.t_band_lo, col.t_band_hi, pa.name
            )
        reports.append(
            {
                "flow_mol_s": flow,
                "duty_W": flow * (h_return - h_draw),
                "draw_T_K": t_draw,
                "return_T_K": t_return,
            }
        )
    return reports


def _close_energy_balance(
    col: _Column,
    tb: _ThermoBox,
    prof: _Profile,
    feed_states: list[StreamState],
    out_states: list[StreamState],
    stripper_reboiler_duty_W: float = 0.0,
) -> None:
    """Exact overall closure over the real boundary streams.

    ``prof.qr`` becomes the PHYSICAL reboiler duty of the MAIN column: with
    pumparounds the cooler duties fold in separately, ``ΣH_in + Q_reb +
    ΣQ_PA + ΣQ_stripper_reb = ΣH_out + Q_cond``, so ``Q_reb = ΣH_out −
    ΣH_in + qc − Σ pa_duty − ΣQ_stripper_reb`` (review item 1, PR #238;
    whole-unit boundary with strippers, review item 2, PR #239). The
    pumparound duties stay visible per loop in ``info``
    (``pa_<name>_duty_W``) and each reboiled stripper's duty under
    ``stripper_<name>_reboiler_duty_W``; ``UnitResult.duty_W = qr − qc +
    Σ pa_duty + ΣQ_stripper_reb`` is the net unit duty closing the stream
    table to machine precision; the deviation of ``qr`` from the
    stage-balance reboiler duty is the converged MESH residual, far below
    the duty magnitudes.
    """
    h_in = sum(s.enthalpy * s.molar_flow for s in feed_states)
    h_out = sum(s.enthalpy * s.molar_flow for s in out_states)
    prof.qr = h_out - h_in + prof.qc - sum(rep["duty_W"] for rep in prof.pa_report) - stripper_reboiler_duty_W


def _check_pumparounds(col: _Column, prof: _Profile) -> None:
    """Post-solve pumparound feasibility gate (review item 5, PR #238).

    Runs ONCE on the final converged profile — never mid-secant, where a
    transient state must be free to fail and retry. Raises ``ColumnSpecError``:
    a reported duty > 0 means the loop's return temperature sits above its
    draw temperature — a heater, not a pumparound cooler.

    The round-1 flow-vs-internal-liquid gate (review item 4) is gone: no input
    reaches it. The raw cascade between the return and the draw carries the
    loop flow (``raw = base + flow``), so only the draw stage itself could dip
    to the flow floor, and there the raw cascade equals the loop-free cascade
    of a converged column — measured unreachable on every oversized-flow case
    tried (flows 100-800 mol/s at return temperatures 300-341 K, plus
    starved-draw specs at distillate 1e-8 and 5 mol/s: all raise
    ``ColumnConvergenceError`` from the exact-residual gate first). The
    protection that gate intended is that convergence failure itself: a flow
    the internals cannot carry never returns a silently floored profile
    (tested in ``test_pumparound_flow_exceeding_internal_liquid_refused``).
    """
    if not col.pumparounds:
        return
    for idx, pa in _live_pumparounds(col):
        rep = prof.pa_report[idx]
        if rep["duty_W"] > 0.0:
            raise ColumnSpecError(
                f"pumparound '{pa.name}': reported duty {rep['duty_W']:.6g} W > 0 — the "
                f"return temperature {rep['return_T_K']:.1f} K is above the draw "
                f"temperature {rep['draw_T_K']:.1f} K; a pumparound may only remove heat"
            )
