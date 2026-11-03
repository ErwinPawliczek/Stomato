"""Side strippers solved simultaneously with the main column (S0-1c steps 3-4).

The stage graph (``inside_out._build_column``) appends every side stripper's
stages after the main stages and links them by two interlinks: the liquid draw
from the main draw stage to the section's top stage, and the section's whole
top-stage vapour back to the main return stage. ``graph_ns`` holds the graph
residual and its Newton engine; this module holds the pieces around it:

- the sequential-section initializer (the main column with a plain liquid side
  draw, then each section seeded from that draw) that gives the graph Newton
  its starting profile;
- whole-graph duty finalization (distillate, bottoms, stripper products,
  condenser and reboiler duties over the graph balances);
- the free-water gate: a stage whose water fugacity exceeds that of pure
  liquid water at the stage (T, P) would split a free-water phase, which the
  one-liquid MESH model cannot carry - the column refuses with a typed error
  naming the stage instead of reporting a hydrocarbon liquid loaded with
  dissolved water;
- the condenser free-water decant (step 4).

Free-water criterion (tangent-plane test with a pure-water trial phase,
Michelsen 1982, Fluid Phase Equilib. 9, 1-19, eq. 8): a pure liquid water
phase is more stable than the stage liquid when its tangent-plane distance is
negative, ln f_w,pure(T, P) < ln f_w(x, T, P), i.e. when the stage's water
fugacity exceeds the pure-liquid fugacity. A stage below that bound carries
its water dissolved and the one-liquid model holds.

All SI. Pure functions over the column/profile records; no I/O.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable

from ngdesign.contracts import PhaseKind, StreamState

from .graph_ns import (
    _graph_liquid_profile,
    _graph_naphtali_sandholm,
    _graph_residual_vector,
    _graph_state,
    _reflux_split,
    _stage_row_ranges,
)
from .inside_out import _Column, _l_profile, _pa_reports, _Profile, _StageFeed, _temperature_seed
from .spec import _FLOW_FLOOR, STEAM_COMPONENT, ColumnConvergenceError, ColumnSpecError
from .thermo_adapter import _flash_ready, _ThermoBox

#: Relative margin on the free-water fugacity test: a stage whose water
#: fugacity exceeds the pure-liquid fugacity by more than this splits a water
#: phase. It is a numerical margin for a state that sits exactly ON the water
#: dew line (the test is otherwise sharp), far below any physical excess.
_FREE_WATER_MARGIN = 1e-6

#: Seed draw: the section's initial liquid draw as a multiple of its product
#: rate (the stripped vapour is a fraction of the draw in every practical
#: stripper; the graph Newton moves the draw through the top vapour).
_SEED_DRAW_FACTOR = 1.25


def _main_only_column(col: _Column) -> _Column:
    """The main column alone, each stripper replaced by a plain liquid side
    draw of its product rate (the sequential initializer's first section)."""
    n = col.n
    draw_l = list(col.draw_l)
    for sec in col.sections:
        if not sec.stages:
            continue  # a 0-stage stripper is already a plain draw in draw_l
        rate = sec.stripper.product_rate
        assert rate is not None  # the parser requires a product rate per stripper
        draw_l[sec.draw_stage - 1] += rate
    feeds = list(col.feeds[:n])
    return dataclasses.replace(
        col,
        pressures=list(col.pressures[:n]),
        feeds=feeds,
        draw_l=draw_l,
        f_total=sum(part.total for part in feeds),
        strippers=[],
        sections=[],
        interlinks=[],
        water_decant=False,
    )


def _sequential_seed(
    col: _Column,
    tb: _ThermoBox,
    t_top: float | None,
    t_bot: float | None,
    solve_main: Callable[[_Column, _ThermoBox, float | None, float | None], _Profile],
) -> _Profile:
    """Sequential-section initializer (S0-1c step 3).

    1. The main column with each stripper as a plain liquid side draw of its
       product rate, converged at the caller's tears by ``solve_main`` (the
       ordinary linear-column mesh).
    2. Each section seeded from its draw: every stage at the draw stage's
       temperature and liquid, the draw at ``_SEED_DRAW_FACTOR`` times the
       product rate, the top vapour carrying the difference plus the
       stripping agent, the vapour falling linearly to the stripping agent
       at the bottom.

    The graph Newton converges the coupled system from here; this profile
    only has to be in its basin.
    """
    main = _main_only_column(col)
    try:
        prof = solve_main(main, tb, t_top, t_bot)
    except (ColumnConvergenceError, ValueError):
        # The plain mesh's own cold seed (a feed-composition, linear-T
        # profile) is outside its basin on wide-boiling feeds. Start the main
        # column from the Fenske-shaped profile instead and let the graph
        # Newton (which handles a linear column too) converge it; its best
        # iterate seeds the coupled solve even if it stops short.
        prof = _fenske_profile(main, tb, t_top, t_bot)
        try:
            _graph_naphtali_sandholm(main, tb, prof, t_bot if main.reboiler == "kettle" else None)
        except ColumnConvergenceError:
            pass
    n = col.n
    prof.x = [dict(prof.x[j]) for j in range(n)]
    prof.y = [dict(prof.y[j]) for j in range(n)]
    prof.T = list(prof.T[:n])
    prof.V = list(prof.V[:n])
    prof.L = list(prof.L[:n])
    for sec in col.sections:
        if not sec.stages:
            continue
        st = sec.stripper
        d = sec.draw_stage - 1
        rate = st.product_rate
        assert rate is not None
        steam = st.steam_flow or 0.0
        draw = _SEED_DRAW_FACTOR * rate
        v_top = draw - rate + steam
        v_bot = steam if st.steam_flow is not None else max(v_top, _FLOW_FLOOR)
        m = len(sec.stages)
        for pos in range(m):
            frac = pos / (m - 1) if m > 1 else 0.0
            prof.x.append(dict(prof.x[d]))
            prof.y.append(dict(prof.y[d]))
            prof.T.append(prof.T[d])
            prof.V.append(max(v_top + frac * (v_bot - v_top), _FLOW_FLOOR))
            prof.L.append(max(draw, _FLOW_FLOOR))
    model, _xs, _ts, vs, draw_flows = _graph_state(col, prof)
    prof.draw_flows = draw_flows
    prof.L = _graph_liquid_profile(model, prof.l0, vs, draw_flows)
    return prof


def _section_feed(col: _Column, s: int) -> _StageFeed:
    """The feed part on graph stage s (section stages beyond the main feeds
    carry the empty default)."""
    return col.feeds[s] if s < len(col.feeds) else _StageFeed()


def _free_water_excess(tb: _ThermoBox, x: dict[str, float], t: float, p: float) -> float | None:
    """ln f_w(x) - ln f_w,pure-liquid at (T, P); None without water or ln phi.

    Positive means a pure-water liquid phase is more stable than the stage
    liquid carrying that water (Michelsen's tangent-plane test with a
    pure-water trial phase).
    """
    x_w = x.get(STEAM_COMPONENT, 0.0)
    if x_w <= 0.0:
        return None
    thermo = tb._thermo
    try:
        mix = thermo.phase_props(x, t, p, PhaseKind.HC_LIQUID).ln_phi
        pure = thermo.phase_props({STEAM_COMPONENT: 1.0}, t, p, PhaseKind.AQUEOUS).ln_phi
    except ValueError:
        return None
    if not mix or not pure or STEAM_COMPONENT not in mix or STEAM_COMPONENT not in pure:
        return None
    return math.log(x_w) + mix[STEAM_COMPONENT] - pure[STEAM_COMPONENT]


def _check_free_water(
    col: _Column, tb: _ThermoBox, prof: _Profile, skip_condenser: bool, where: str = ""
) -> None:
    """Refuse a converged profile that carries free water on any stage.

    Every graph stage's liquid is tested (the stage is at equilibrium, so its
    vapour reads the same water fugacity). A total condenser's condensate is
    tested too, at its own bubble temperature, unless ``skip_condenser``
    (the decant is on and takes that water out as its own product).
    """
    if STEAM_COMPONENT not in col.comps:
        return
    for s in range(col.n_graph):
        x = _flash_ready(prof.x[s], col.feed_comp)
        excess = _free_water_excess(tb, x, prof.T[s], col.pressures[s])
        if excess is not None and excess > _FREE_WATER_MARGIN:
            raise ColumnSpecError(
                f"free water on stage {s + 1}: the stage liquid's water fugacity exceeds that of pure "
                f"liquid water at {prof.T[s]:.2f} K, {col.pressures[s]:.4g} Pa by "
                f"{100.0 * math.expm1(excess):.3g} % - a water phase would separate, which the "
                f"one-liquid stage model cannot carry{where}"
            )
    if col.condenser == "total" and not skip_condenser:
        y0 = _flash_ready(prof.y[0], col.feed_comp)
        t_cond = tb.bubble_temperature(y0, col.pressures[0])
        if t_cond is None:
            return
        excess = _free_water_excess(tb, y0, t_cond, col.pressures[0])
        if excess is not None and excess > _FREE_WATER_MARGIN:
            raise ColumnSpecError(
                f"free water in the total condenser: the condensate's water fugacity exceeds that of "
                f"pure liquid water at its bubble point {t_cond:.2f} K by "
                f"{100.0 * math.expm1(excess):.3g} % - turn condenser_water_decant on to draw the "
                f"aqueous phase off, or raise the condenser temperature{where}"
            )


def _graph_stage_heat_imbalance(col: _Column, tb: _ThermoBox, prof: _Profile, stage: int) -> float:
    """Enthalpy in minus enthalpy out of one graph stage, W, at the profile.

    Read off the graph residual's own H row (the one energy algebra of the
    solve: cascade, interlink, feed, pumparound and heater terms), with the
    row switched on for the duty stages and its fixed scale undone.
    """
    model, xs, ts, vs, draw_flows = _graph_state(col, prof)
    full = dataclasses.replace(model, h_stages=frozenset(range(col.n_graph)))
    r = _graph_residual_vector(full, tb, prof.l0, xs, ts, vs, draw_flows, y_seeds=[dict(y) for y in prof.y])
    _start, stop = _stage_row_ranges(full)[stage]
    return r[stop - 1] * max(col.f_total * 2e4, 1.0)


def _finalize_graph_duties(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Duties and product rates of a converged graph profile (S0-1c step 3).

    The graph counterpart of ``_finalize_duties``: stage compositions are
    normalized over every graph stage, the liquid profile and the derived
    stripper draws are rebuilt from the graph balances, the distillate is the
    top vapour (less the reflux for a total condenser) and the bottoms the
    main bottom liquid. The condenser duty follows the dense convention
    (total: the condensation of V_1 at the stage-1 state; partial: the
    stage-1 balance) and the reboiler duty the kettle stage balance; the
    reported reboiler duty is then closed exactly over the boundary streams by
    ``_close_energy_balance``.
    """
    for s in range(col.n_graph):
        for comp in (prof.x[s], prof.y[s]):
            total = sum(comp.values())
            if total > _FLOW_FLOOR and abs(total - 1.0) > 1e-12:
                for cid in comp:
                    comp[cid] /= total
    model, _xs, _ts, vs, draw_flows = _graph_state(col, prof)
    prof.draw_flows = draw_flows
    prof.L = _graph_liquid_profile(model, prof.l0, vs, draw_flows)
    prof.d = prof.V[0] - prof.l0 if col.condenser == "total" else prof.V[0]
    prof.b = prof.L[col.n - 1]
    prof.reflux_x, prof.decant = {}, 0.0
    if col.condenser == "total" and col.water_decant:
        # S0-1c step 4: V_1 condenses into the decanted hydrocarbon liquid
        # (reflux + distillate) and the free water; the condenser duty is the
        # enthalpy V_1 gives up to leave as those liquids at the stage-1 state.
        x_ref, phi = _reflux_split(col, tb, prof.y[0], prof.T[0])
        prof.decant = phi * prof.V[0]
        prof.reflux_x = dict(x_ref)
        prof.d = prof.V[0] - prof.l0 - prof.decant
        y0 = _flash_ready(prof.y[0], col.feed_comp)
        t0, p0 = prof.T[0], col.pressures[0]
        h_hc = tb.h_liquid(_flash_ready(x_ref, col.feed_comp), t0, p0)
        h_w = tb.h_liquid({STEAM_COMPONENT: 1.0}, t0, p0) if prof.decant > 0.0 else 0.0
        prof.qc = max(
            prof.V[0] * tb.h_vapor(y0, t0, p0) - (prof.V[0] - prof.decant) * h_hc - prof.decant * h_w,
            0.0,
        )
    elif col.condenser == "total":
        y0 = _flash_ready(prof.y[0], col.feed_comp)
        prof.qc = max(
            prof.V[0]
            * (tb.h_vapor(y0, prof.T[0], col.pressures[0]) - tb.h_liquid(y0, prof.T[0], col.pressures[0])),
            0.0,
        )
    elif col.condenser == "partial":
        prof.qc = max(_graph_stage_heat_imbalance(col, tb, prof, 0), 0.0)
    else:
        prof.qc = 0.0
    if col.reboiler == "kettle":
        prof.qr = max(-_graph_stage_heat_imbalance(col, tb, prof, col.n - 1), 0.0)
    else:
        prof.qr = 0.0
    prof.pa_report = _pa_reports(col, tb, prof)


def _steam_states(col: _Column, tb: _ThermoBox) -> list[StreamState]:
    """The stripping-steam boundary streams (pure water at the parsed T, P)."""
    out: list[StreamState] = []
    for sec in col.sections:
        st = sec.stripper
        if sec.stages and st.steam_flow is not None and st.steam_flow > _FLOW_FLOOR:
            out.append(tb.pt({STEAM_COMPONENT: 1.0}, st.steam_T, st.steam_P, st.steam_flow))
    return out


def _stripper_products(
    col: _Column, tb: _ThermoBox, prof: _Profile
) -> tuple[dict[str, StreamState], dict[str, float]]:
    """Each stripper's bottoms product as a boundary stream, plus its info keys.

    A section's product is its bottom stage's liquid at that stage's state; a
    0-stage stripper's product is the plain liquid draw at the draw stage.
    Info keys per stripper ``<name>``: ``stripper_<name>_product_mol_s``,
    ``_draw_mol_s``, ``_vapour_return_mol_s``, ``_steam_mol_s``,
    ``_reboiler_duty_W``, ``_top_T_K``, ``_bottom_T_K`` and the product
    composition ``_x_<cid>``.
    """
    states: dict[str, StreamState] = {}
    info: dict[str, float] = {}
    link = 0
    for sec in col.sections:
        st = sec.stripper
        key = f"stripper_{st.name}"
        if sec.stages:
            top, bottom = sec.stages[0] - 1, sec.stages[-1] - 1
            flow = prof.L[bottom]
            draw = prof.draw_flows[link]
            link += 1
            v_ret = prof.V[top]
        else:
            top = bottom = sec.draw_stage - 1
            flow = st.product_rate or 0.0
            draw = flow
            v_ret = 0.0
        comp = _flash_ready(prof.x[bottom], col.feed_comp)
        states[st.name] = tb.pt(comp, prof.T[bottom], col.pressures[bottom], max(flow, _FLOW_FLOOR))
        info[f"{key}_product_mol_s"] = flow
        info[f"{key}_draw_mol_s"] = draw
        info[f"{key}_vapour_return_mol_s"] = v_ret
        info[f"{key}_steam_mol_s"] = st.steam_flow or 0.0
        info[f"{key}_reboiler_duty_W"] = st.reboiler_duty_W or 0.0
        info[f"{key}_top_T_K"] = prof.T[top]
        info[f"{key}_bottom_T_K"] = prof.T[bottom]
        for cid, frac in comp.items():
            info[f"{key}_x_{cid}"] = frac
    return states, info


def _decant_state(tb: _ThermoBox, distillate: StreamState, flow: float) -> StreamState:
    """The free-water decant as a boundary stream: pure liquid water at the
    distillate's (decanter drum) temperature and pressure."""
    state = tb.pt({STEAM_COMPONENT: 1.0}, distillate.T, distillate.P, 1.0)
    return state.model_copy(update={"molar_flow": max(flow, 0.0)})


#: Effective stage count of the Fenske split, as a fraction of the column's
#: stages: a finite-reflux column separates like roughly half its stages at
#: total reflux (the Gilliland correlation's working region), and the seed only
#: has to be on the right side of the split, not exact.
_FENSKE_STAGE_FRACTION = 0.5
#: Trace floor of a seeded mole fraction (keeps logs and K x finite).
_SEED_TRACE = 1e-12


def _fenske_profile(col: _Column, tb: _ThermoBox, t_top: float | None, t_bot: float | None) -> _Profile:
    """A total-reflux (Fenske) shaped starting profile for a linear column at
    the given tears - the graph path's cold start when the plain mesh's own
    seed does not converge (wide-boiling feeds).

    Flows: constant molar overflow from the tears - the boilup rises through
    every stage, each feed's vapour joins the vapour leaving its stage, a
    partial condenser's top vapour is its tear - and the liquids follow from
    the stage total balances (``_l_profile``). Compositions: the distillate
    and bottoms split d_i/b_i = theta alpha_i^m (Fenske 1932, Ind. Eng.
    Chem. 24, 482), m the effective stage count and theta set so the
    distillate total matches the tears, with alpha from the Clausius-
    Clapeyron K estimate at the mid-column temperature; the stage liquids
    interpolate ln x between the bottoms and the top-stage liquid in
    equilibrium with the distillate (the total-reflux profile shape), each
    stage at its bubble temperature and its vapour y = K x.
    """
    n = col.n
    nc_ids = list(col.comps)
    boil = t_bot if (col.reboiler == "kettle" and t_bot is not None) else 0.0
    vapour = [0.0] * n
    for j in range(n):
        if col.reboiler == "kettle" and j == n - 1:
            vapour[j] = boil
        else:
            stop = n - 1 if col.reboiler == "kettle" else n
            vapour[j] = boil + sum(col.feeds[m].v_flow for m in range(j, stop))
    if col.condenser == "partial" and t_top is not None:
        vapour[0] = t_top
    vapour = [max(v, _FLOW_FLOOR) for v in vapour]
    l0 = t_top if (col.condenser == "total" and t_top is not None) else 0.0
    liquid = _l_profile(col, l0, vapour)
    d = vapour[0] - l0 if col.condenser == "total" else vapour[0]
    feed_moles = dict.fromkeys(nc_ids, 0.0)
    for part in col.feeds[:n]:
        for cid in nc_ids:
            feed_moles[cid] += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
    f_main = sum(feed_moles.values())
    d = min(max(d, 1e-6 * f_main), (1.0 - 1e-6) * f_main)
    t_hi, t_lo = _temperature_seed(col, tb)[::-1]
    p_mid = col.pressures[n // 2]
    z = {cid: max(v / f_main, _SEED_TRACE) for cid, v in feed_moles.items()}
    k_mid = tb.k_estimate(_flash_ready(z, col.feed_comp), 0.5 * (t_lo + t_hi), p_mid)
    ref = math.exp(sum(math.log(max(k_mid.get(c, 1.0), _SEED_TRACE)) for c in nc_ids) / len(nc_ids))
    m_eff = max(_FENSKE_STAGE_FRACTION * n, 1.0)
    ln_pw = {c: m_eff * math.log(max(k_mid.get(c, 1.0), _SEED_TRACE) / ref) for c in nc_ids}

    def recovered(ln_theta: float, c: str) -> float:
        """d_i / f_i = theta a^m / (1 + theta a^m), overflow-free."""
        arg = ln_theta + ln_pw[c]
        return 1.0 / (1.0 + math.exp(-arg)) if arg > -700.0 else 0.0

    lo, hi = -1400.0, 1400.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if sum(feed_moles[c] * recovered(mid, c) for c in nc_ids) < d:
            lo = mid
        else:
            hi = mid
    dist = {c: feed_moles[c] * recovered(0.5 * (lo + hi), c) for c in nc_ids}
    bott = {c: feed_moles[c] - dist[c] for c in nc_ids}
    y_d = {c: max(v / max(sum(dist.values()), _FLOW_FLOOR), _SEED_TRACE) for c, v in dist.items()}
    x_b = {c: max(v / max(sum(bott.values()), _FLOW_FLOOR), _SEED_TRACE) for c, v in bott.items()}
    k_top = tb.k_estimate(_flash_ready(y_d, col.feed_comp), t_lo, col.pressures[0])
    x_top_raw = {c: y_d[c] / max(k_top.get(c, 1.0), _SEED_TRACE) for c in nc_ids}
    s_top = sum(x_top_raw.values())
    x_top = {c: max(v / s_top, _SEED_TRACE) for c, v in x_top_raw.items()}
    xs: list[dict[str, float]] = []
    ys: list[dict[str, float]] = []
    ts: list[float] = []
    for j in range(n):
        w = j / max(n - 1, 1)
        raw = {c: math.exp((1.0 - w) * math.log(x_top[c]) + w * math.log(x_b[c])) for c in nc_ids}
        s = sum(raw.values())
        x_j = {c: v / s for c, v in raw.items()}
        t_j = tb.bubble_temperature(_flash_ready(x_j, col.feed_comp), col.pressures[j])
        if t_j is None:
            t_j = t_lo + (t_hi - t_lo) * w
        t_j = min(max(t_j, col.t_band_lo + 1.0), col.t_band_hi - 1.0)
        k_j = tb.k_estimate(_flash_ready(x_j, col.feed_comp), t_j, col.pressures[j])
        y_raw = {c: k_j.get(c, 1.0) * x_j[c] for c in nc_ids}
        sy = sum(y_raw.values())
        xs.append(x_j)
        ys.append({c: v / sy for c, v in y_raw.items()})
        ts.append(t_j)
    return _Profile(T=ts, V=vapour, L=liquid, x=xs, y=ys, l0=l0)
