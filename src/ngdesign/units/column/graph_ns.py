"""Stage-graph Naphtali-Sandholm: simultaneous damped Newton over the stage graph.

S0-1c step 2 (issue #235). The dense fallback in ``naphtali_sandholm.py`` keeps
the linear columns byte-identical and is untouched; this module carries the same
unknown packing (x, T, V per stage, with the kettle boilup pinned by the tear)
extended over the whole graph (``col.n_graph`` stages), with NO draw block:
stripper draw flows are derived from their sections' total balances (draw =
section-top vapour + product - section feeds; the product-rate spec pins
each exactly). Rows are the same live residual algebra
per stage - one M balance per component, the canonical NS summation row, an H
row on every duty-bearing stage - with the interlink terms added: the draw
leaves the main stage as an extra liquid outflow at the draw stage's
composition and enthalpy and enters the section's top stage as its liquid
inflow; the section's whole top-stage vapour returns to the main return stage
as a feed-like vapour inflow at the top stage's composition and enthalpy.

The Jacobian is a stage-coloured finite-difference approximation: for one
variable index (a component's x slot, the stage temperature, the stage vapour
flow) the stages whose affected residual rows are pairwise disjoint are grouped
into a colour, and one residual evaluation perturbs that index across a whole
colour group at once. Within a cascade a stage's rows depend on its own and its
neighbours' x and T, so stages three or more cascade links apart share a colour;
interlink adjacency (draw stage, section top, return stage) is honoured the same
way. Vapour-flow perturbations reach one stage further through the liquid
recursion and are coloured separately, and a section top's vapour flow
carries its section's DERIVED draw with it (the draw is a function of that
vapour flow), so its perturbation reach includes every row the draw feeds.
The count of residual
evaluations per Jacobian is therefore bounded by the colour count times the
variables per stage - not by the unknown count. The step solves with a
``scipy.sparse`` LU factorisation of the (block-sparse) Jacobian.

The linear-column path of this module is exercised only through tests (the
public solve dispatches nothing here until step 3): on a column without
sections the graph residual is the dense residual's algebra, and the graph solve
converges to the same root.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.sparse
import scipy.sparse.linalg

from ngdesign.contracts import PhaseKind

from .decant import decant_split
from .inside_out import (
    _Column,
    _exact_residuals,
    _Interlink,
    _live_pumparounds,
    _pa_return_terms,
    _pa_stage_flows,
    _Profile,
    _stage_k_values,
    _StageFeed,
    _WallSection,
)
from .naphtali_sandholm import _ns_controller, _refresh_y
from .spec import (
    _FLOW_FLOOR,
    _MESH_H_TOL,
    _MESH_M_TOL,
    _MESH_M_TOL_ZERO_ONE_TEAR,
    _NS_MAX,
    _NS_MAX_ZERO_ONE_TEAR,
    ColumnConvergenceError,
)
from .thermo_adapter import _flash_ready, _ThermoBox

#: Per-pass Newton temperature step bound (K). The unpack's band clamp is far
#: too wide to stop a bad Jacobian from shooting a section bottom 100+ K in one
#: accepted step (measured: T drifting to 480 K on a steam-stripper bottom,
#: from which the line search never recovered). Real simulators bound dT per
#: NS pass for the same reason. Applied ONLY on columns with stripper sections
#: (the graph engine's cap_step): a linear column has no sections, the bound
#: is inactive there, and the shared controller's steps reach the dense
#: engine untouched.
_NS_MAX_DT = 25.0
#: Per-pass Newton step bound on a dividing wall's vapour split fraction, and
#: the split's distance from 0 and 1 (each wall side keeps some vapour).
_NS_MAX_DBETA = 0.05
_BETA_MIN = 1e-4


@dataclass(frozen=True)
class _GraphLayout:
    """Unknown-vector layout of the graph solve (S0-1c step 2).

    ``[x: n_graph * nc][T: n_graph][V: len(v_free)]`` - the x/T/V blocks
    mirror the dense packing over ``n_graph`` stages. The kettle boilup (and a
    partial-condenser top vapour) are column tears: their stages are absent
    from ``v_free`` and the boilup enters through ``t_bot_tear`` exactly as in
    the dense path. Stripper draw flows are NOT unknowns: each is derived from
    its section's total balance (draw = returned vapour + product - section
    feeds), so the product-rate spec pins the draw exactly and no redundant
    balance row is needed in the residual set.
    """

    n_graph: int
    nc: int
    #: Graph stage indices whose vapour flow is a solve unknown (0-based).
    v_free: list[int]
    #: Liquid interlinks in record order (the draw flows are DERIVED, not
    #: unknowns - no draw block exists).
    draw_links: list[_Interlink]
    t_base: int
    v_base: int
    d_base: int
    n_unk: int
    #: Dividing wall: the slot of the vapour split fraction beta when it is a
    #: Newton unknown (the equal pressure-drop row closes it), else None.
    beta_index: int | None = None

    @property
    def variables_per_stage(self) -> int:
        """Variables per stage: one x per component, one T, one V when free."""
        return self.nc + 1 + (1 if self.v_free else 0)


@dataclass(frozen=True)
class _GraphModel:
    """Static per-solve graph structure derived once from the column."""

    col: _Column
    layout: _GraphLayout
    #: Feeds padded over the whole graph (section stages without feeds carry
    #: the empty default).
    feeds: list[_StageFeed]
    #: Per graph stage: the cascade liquid donor above (None at a cascade top)
    #: and the cascade vapour donor below (None at a cascade bottom). Sections
    #: are separate cascades - the numbering is global, the cascades are not.
    liquid_donor: list[int | None]
    vapour_donor: list[int | None]
    #: Main stage index (0-based) of each liquid interlink, in record order.
    draw_stage_of_link: list[int]
    #: Section top stage (0-based) that each liquid interlink feeds.
    section_top_of_link: list[int]
    #: Main return stage (0-based) -> section top stages (0-based) whose vapour
    #: lands there (several strippers may return to one stage).
    vapour_return_at: dict[int, tuple[int, ...]]
    #: Main draw stage (0-based) -> liquid interlink position.
    draw_link_at_stage: dict[int, int]
    #: Section top stage (0-based) -> liquid interlink position.
    link_at_top: dict[int, int]
    #: Reboiler duty (W) carried by a section bottom stage. The static duty
    #: enters that stage's H row; the spec'd driver wiring is step 3.
    section_duty_at: dict[int, float]
    #: Pumparound net flows over the MAIN stages (S0-1 algebra, unchanged).
    pa_out: list[float]
    pa_in: list[float]
    #: Per liquid interlink: (link position, section top stage, section bottom
    #: stage, product rate mol/s). Each draw flow is DERIVED from its section's
    #: total balance: draw = vs[top] + product - section feeds - the product
    #: rate spec pins the draw exactly, so it is not a Newton unknown.
    section_total_rows: list[tuple[int, int, int, float]]
    #: Stages carrying an H row: every graph stage except the main tear stages
    #: (a partial condenser's and a kettle's balances define qc/qr instead).
    h_stages: frozenset[int]
    #: A partial condenser's pinned top vapour (the top tear), None otherwise.
    v_top_pin: float | None = None
    #: A dividing wall's prefractionator (None without a wall).
    wall: _WallSection | None = None


def _graph_model(col: _Column, kettle_free: bool = False, v_top_pin: float | None = None) -> _GraphModel:
    """Build the static graph structure and unknown layout for one solve.

    ``kettle_free`` (standalone mode): with no caller tear the kettle boilup
    is a Newton unknown - its M rows pin the flow and its summation row pins
    the temperature, so the graph solve converges the boilup itself. Strategy
    mode (default) keeps it pinned by ``t_bot_tear`` exactly as in the dense
    path. A partial condenser's top vapour stays pinned either way (not yet
    routed through a standalone solve).
    """
    g = col.n_graph
    nc = len(col.comps)
    tears = {
        j
        for j in range(col.n)
        if (col.condenser == "partial" and j == 0) or (col.reboiler == "kettle" and j == col.n - 1)
    }
    if kettle_free:
        tears.discard(col.n - 1)
    # Stages whose balance defines a duty (no H row): the tear stages, except
    # in the total condenser's top-vapour mode below.
    duty_stages = set(tears)
    if v_top_pin is not None and col.condenser == "total":
        # Top-vapour mode (S0-1c): V_1 = L_0 + D is pinned - the distillate
        # fixed exactly, as a partial condenser's top tear fixes it - and the
        # kettle boilup is a Newton unknown. Stage 1 keeps its H row (a
        # total condenser's stage 1 is an ordinary tray) and the kettle's
        # balance still defines qr.
        tears = {0}
        duty_stages = {col.n - 1} if col.reboiler == "kettle" else set()
    v_free = [j for j in range(g) if j not in tears]
    draw_links = [lk for lk in col.interlinks if lk.phase == "liquid"]
    t_base = g * nc
    v_base = t_base + g
    d_base = v_base + len(v_free)
    wall = col.wall
    beta_free = wall is not None and wall.vapour_split is None
    layout = _GraphLayout(
        n_graph=g,
        nc=nc,
        v_free=v_free,
        draw_links=draw_links,
        t_base=t_base,
        v_base=v_base,
        d_base=d_base,
        n_unk=d_base + (1 if beta_free else 0),
        beta_index=d_base if beta_free else None,
    )

    feeds = list(col.feeds) + [_StageFeed() for _ in range(g - len(col.feeds))]
    liquid_donor: list[int | None] = []
    vapour_donor: list[int | None] = []
    section_of: dict[int, tuple[int, ...]] = {}
    for sec in col.sections:
        for s in sec.stages:
            section_of[s - 1] = tuple(j - 1 for j in sec.stages)
    if wall is not None:
        # The prefractionator is its own cascade: its top takes the split
        # liquid and its bottom the split vapour (wall terms in the residual).
        for s in wall.stages:
            section_of[s] = wall.stages
    for s in range(g):
        if s in section_of:
            chain = section_of[s]
            pos = chain.index(s)
            liquid_donor.append(chain[pos - 1] if pos > 0 else None)
            vapour_donor.append(chain[pos + 1] if pos + 1 < len(chain) else None)
        else:  # main cascade
            liquid_donor.append(s - 1 if s > 0 else None)
            vapour_donor.append(s + 1 if s + 1 < col.n else None)

    draw_stage_of_link = [lk.from_stage for lk in draw_links]
    section_top_of_link = [lk.to_stage for lk in draw_links]
    vapour_return_at: dict[int, tuple[int, ...]] = {}
    for lk in col.interlinks:
        if lk.phase == "vapour":
            vapour_return_at[lk.to_stage] = (*vapour_return_at.get(lk.to_stage, ()), lk.from_stage)
    if wall is not None:
        # The prefractionator's whole top vapour returns above the wall,
        # exactly like a stripper's overhead return.
        vapour_return_at[wall.above] = (*vapour_return_at.get(wall.above, ()), wall.stages[0])
    draw_link_at_stage = {lk.from_stage: k for k, lk in enumerate(draw_links)}
    link_at_top = {lk.to_stage: k for k, lk in enumerate(draw_links)}
    section_duty_at: dict[int, float] = {}
    for sec in col.sections:
        if sec.bottom_stage is not None and sec.stripper.reboiler_duty_W is not None:
            section_duty_at[sec.bottom_stage - 1] = sec.stripper.reboiler_duty_W
    pa_out, pa_in = _pa_stage_flows(col)
    section_total_rows: list[tuple[int, int, int, float]] = []
    for k, link in enumerate(draw_links):
        sec_hit = next((sc for sc in col.sections if sc.draw_stage - 1 == link.from_stage), None)
        assert sec_hit is not None and sec_hit.bottom_stage is not None
        rate = sec_hit.stripper.product_rate
        assert rate is not None  # the parser requires a product rate per section
        section_total_rows.append((k, link.to_stage, sec_hit.bottom_stage - 1, rate))
    h_stages = frozenset(j for j in range(g) if j not in duty_stages)
    return _GraphModel(
        col=col,
        layout=layout,
        feeds=feeds,
        liquid_donor=liquid_donor,
        vapour_donor=vapour_donor,
        draw_stage_of_link=draw_stage_of_link,
        section_top_of_link=section_top_of_link,
        vapour_return_at=vapour_return_at,
        draw_link_at_stage=draw_link_at_stage,
        link_at_top=link_at_top,
        section_duty_at=section_duty_at,
        pa_out=pa_out,
        pa_in=pa_in,
        section_total_rows=section_total_rows,
        h_stages=h_stages,
        v_top_pin=v_top_pin if col.condenser in ("partial", "total") else None,
        wall=wall,
    )


def _graph_liquid_profile(
    model: _GraphModel, l0: float, vs: list[float], draw_flows: list[float]
) -> list[float]:
    """Liquid flows over the whole graph from the stage total balances
    (``_graph_flows`` without the wall's liquid split)."""
    return _graph_flows(model, l0, vs, draw_flows)[0]


def _graph_flows(
    model: _GraphModel, l0: float, vs: list[float], draw_flows: list[float]
) -> tuple[list[float], float]:
    """(liquid flows over the whole graph, the wall's split liquid flow).

    Main stages: the dense telescoped recursion (``_l_profile``) with the
    stripper draws subtracted like any side draw. Each section restarts the
    cascade at its draw flow (the interlink IS the section's liquid inflow) and
    telescopes over its own stages; the section's top-stage vapour leaves
    entirely (the return link), the bottom stage's liquid is the product.

    Dividing wall (``model.wall``; the split vapour flow is the trailing
    ``draw_flows`` entry): the liquid leaving stage ``above`` is
    ``L_tot = l0 + cum + V_in - V_1`` from the envelope over the stages above
    it, of which ``liquid_split * L_tot`` enters the prefractionator top and
    the rest stays in the main cascade. The main side's bottom stage receives
    only the unsplit vapour ``V_below - V_split``. Stage ``below`` gains the
    prefractionator bottom liquid less the split vapour, which by the
    prefractionator's total balance is ``L_wall + F_pre - V_pre,top``. The
    prefractionator telescopes from its top like a section, its bottom stage
    fed from below by ``V_split``. Without a wall the split flow is 0.0.
    """
    col = model.col
    wall = model.wall
    n_links = len(model.draw_stage_of_link)
    draw_out = {model.draw_stage_of_link[k]: draw_flows[k] for k in range(n_links)}
    v_split = draw_flows[-1] if wall is not None else 0.0
    l_wall = 0.0
    out: list[float] = []
    cum = 0.0
    for j in range(col.n):
        cum += model.feeds[j].total - col.draw_l[j] - col.draw_v[j] - draw_out.get(j, 0.0)
        if j in model.vapour_return_at:
            # The section's returned top vapour is an inflow to the return
            # stage's total balance like a feed: without it every main liquid
            # at and below the return stage misses that vapour and the return
            # stage's M rows cannot close (S0-1c step 3).
            cum += sum(vs[top] for top in model.vapour_return_at[j])
        if col.pumparounds:
            cum += model.pa_in[j] - model.pa_out[j]
        v_above = vs[j + 1] if j + 1 < col.n else 0.0
        if wall is None:
            out.append(max(l0 + cum + v_above - vs[0], _FLOW_FLOOR))
            continue
        if j == wall.below:
            cum += l_wall + sum(model.feeds[s].total for s in wall.stages) - vs[wall.stages[0]]
        if j == wall.below - 1:
            v_above = vs[wall.below] - v_split
        liquid = l0 + cum + v_above - vs[0]
        if j == wall.above:
            l_wall = wall.liquid_split * max(liquid, 0.0)
            cum -= l_wall
            liquid -= l_wall
        out.append(max(liquid, _FLOW_FLOOR))
    for sec in col.sections:
        chain = [s - 1 for s in sec.stages]
        if not chain:
            continue  # degenerate n_stages = 0: plain draw, no section cascade
        link = model.draw_link_at_stage[sec.draw_stage - 1]
        cum_s = 0.0
        top = chain[0]
        for pos, s in enumerate(chain):
            cum_s += model.feeds[s].total
            v_below = vs[s + 1] if pos + 1 < len(chain) else 0.0
            out.append(max(draw_flows[link] + cum_s + v_below - vs[top], _FLOW_FLOOR))
    if wall is not None:
        top = wall.stages[0]
        cum_s = 0.0
        for pos, s in enumerate(wall.stages):
            cum_s += model.feeds[s].total
            v_below = vs[s + 1] if pos + 1 < len(wall.stages) else v_split
            out.append(max(l_wall + cum_s + v_below - vs[top], _FLOW_FLOOR))
    return out, l_wall


def _reflux_split(
    col: _Column, tb: _ThermoBox, y0: dict[str, float], t0: float
) -> tuple[dict[str, float], float]:
    """The total condenser's (reflux liquid composition, free-water fraction
    of V_1) - the decant split (``decant.decant_split``) when the column
    decants, else (y_1, 0) exactly. Memoized per solve on (y_1, T_1, P_1)."""
    if not col.water_decant:
        return y0, 0.0
    key = (tuple(sorted(y0.items())), t0, col.pressures[0])
    hit = col.decant_memo.get(key)
    if hit is None:
        # The split is taken at the stage-1 temperature, the state the total
        # condenser returns its reflux at (see ``decant``).
        hit = decant_split(tb, _flash_ready(y0, col.feed_comp), t0, col.pressures[0])
        col.decant_memo[key] = hit
    return hit


def _graph_k_args(model: _GraphModel, s: int) -> tuple[_StageFeed, float]:
    """The graph-aware `_stage_k_values` arguments for graph stage s (S0-1c
    step 2): the padded feed part, and the main-column draw total - zero past
    the main column, where a stripper draw is cascade liquid already excluded
    from the section cascade."""
    col = model.col
    return model.feeds[s], ((col.draw_l[s] + col.draw_v[s]) if s < col.n else 0.0)


def _graph_y_eq(k: dict[str, float], x_s: dict[str, float]) -> dict[str, float]:
    """Vapour composition y = K*x, normalized (the live residual's convention)."""
    y = {cid: k.get(cid, 1.0) * x_s.get(cid, 0.0) for cid in x_s}
    total = sum(y.values())
    if total > _FLOW_FLOOR:
        y = {cid: v / total for cid, v in y.items()}
    return y


def _graph_interlink_terms(
    model: _GraphModel, xs: list[dict[str, float]], draw_flows: list[float]
) -> list[dict[str, dict[str, float]]]:
    """Per liquid interlink: the component flows leaving the draw stage and
    entering the section's top stage (S0-1c step 2 acceptance: both ends read
    the ONE shared term, so the assembled residuals balance exactly)."""
    terms: list[dict[str, dict[str, float]]] = []
    for k, link in enumerate(model.layout.draw_links):
        comp = {cid: draw_flows[k] * xs[link.from_stage].get(cid, 0.0) for cid in model.col.comps}
        terms.append({"from_stage": dict(comp), "to_stage": dict(comp)})
    return terms


def _graph_residual_vector(
    model: _GraphModel,
    tb: _ThermoBox,
    l0: float,
    xs: list[dict[str, float]],
    ts: list[float],
    vs: list[float],
    draw_flows: list[float],
    k_fallbacks: list[dict[str, float]] | None = None,
    k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] | None = None,
    k_misses: list[int] | None = None,
    h_evals: list[int] | None = None,
    scales: list[float] | None = None,
    flow_mags: list[float] | None = None,
    k_out: list[dict[str, float] | None] | None = None,
    y_seeds: list[dict[str, float]] | None = None,
) -> list[float]:
    """The live MESH residual over the whole graph, interlinks included.

    ``y_seeds``: the pass-frozen stage vapours, for a K that reads the vapour's
    fugacity (P1-13); None keeps the empty seed of the flash surface.

    Row order per stage (as in the dense `_live_residual_vector`): one M
    balance per component, the canonical NS summation row, and one H row on
    every duty-bearing stage (all graph stages except the main tear stages).
    M rows are scaled per row by ``max(|inflow|, |outflow|, f_total * 1e-6)``
    (frozen from the pass's reference state via ``scales``) and H rows by
    ``max(f_total * 2e4, 1.0)``. An unevaluable stage reads 1.0 on all its
    rows - the gate's "not evaluable is NOT converged" semantics.
    """
    col = model.col
    g = model.layout.n_graph
    nc = model.layout.nc
    liquid, l_wall = _graph_flows(model, l0, vs, draw_flows)
    wall = model.wall
    h_scale = max(col.f_total * 2e4, 1.0)
    links = _graph_interlink_terms(model, xs, draw_flows)

    k_stages: list[dict[str, float] | None] = []
    y_eq: list[dict[str, float]] = []
    for s in range(g):
        k = None
        if k_cache is not None:
            key = (tuple(sorted(xs[s].items())), round(ts[s], 12), col.pressures[s])
            k = k_cache.get(key)
        if k is None:
            if k_misses is not None:
                k_misses[0] += 1
            feed_part, draw_total = _graph_k_args(model, s)
            k = (
                _stage_k_values(
                    col,
                    tb,
                    s,
                    xs[s],
                    y_seeds[s] if y_seeds is not None else {},
                    ts[s],
                    liquid[s],
                    vs[s],
                    feed_part=feed_part,
                    draw_total=draw_total,
                )
                or tb.k_estimate(_flash_ready(xs[s], col.feed_comp), ts[s], col.pressures[s])
                or (k_fallbacks[s] if k_fallbacks is not None else None)
            )
            if k_cache is not None and k is not None:
                k_cache[(tuple(sorted(xs[s].items())), round(ts[s], 12), col.pressures[s])] = k
        k_stages.append(k)
        y_eq.append(_graph_y_eq(k, xs[s]) if k is not None else {})

    # Pumparound couplings over the main stages (S0-1 algebra): the return is a
    # feed-like liquid inflow at the draw-stage composition.
    pa_ret = _pa_return_terms(col)

    out: list[float] = []
    for s in range(g):
        k = k_stages[s]
        part = model.feeds[s]
        if k is None:
            for _ in range(nc):
                out.append(1.0)
                if flow_mags is not None:
                    flow_mags.append(1.0)
            out.append(1.0)
            if flow_mags is not None:
                flow_mags.append(1.0)
            if s in model.h_stages:
                out.append(1.0)
                if flow_mags is not None:
                    flow_mags.append(1.0)
            continue
        donor = model.liquid_donor[s]
        vap_donor = model.vapour_donor[s]
        link_in = model.link_at_top.get(s)
        x_reflux = y_eq[0]
        if s == 0 and col.condenser == "total" and col.water_decant:
            # S0-1c step 4: the reflux is the decanted hydrocarbon liquid.
            x_reflux, _phi = _reflux_split(col, tb, y_eq[0], ts[0])
        for i, cid in enumerate(col.comps):
            inflow = 0.0
            if s == 0 and col.condenser == "total":
                inflow = l0 * x_reflux.get(cid, 0.0)
            elif donor is not None:
                inflow = liquid[donor] * xs[donor].get(cid, 0.0)
            if link_in is not None:
                inflow = links[link_in]["to_stage"][cid]
            if vap_donor is not None:
                inflow += _vapour_in(model, vs, draw_flows, s, vap_donor) * y_eq[vap_donor].get(cid, 0.0)
            if wall is not None:
                inflow += _wall_m_in(wall, liquid, l_wall, xs, y_eq, draw_flows, s, cid)
            for ret_top in model.vapour_return_at.get(s, ()):
                inflow += vs[ret_top] * y_eq[ret_top].get(cid, 0.0)
            inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
            for ret_j, draw_j, pa_flow in pa_ret:
                if ret_j == s:
                    inflow += pa_flow * xs[draw_j].get(cid, 0.0)
            own_draw = draw_flows[model.draw_link_at_stage[s]] if s in model.draw_link_at_stage else 0.0
            if wall is not None and s == wall.above:
                own_draw = l_wall
            outflow = (
                liquid[s]
                + (col.draw_l[s] if s < col.n else 0.0)
                + own_draw
                + (model.pa_out[s] if col.pumparounds and s < col.n else 0.0)
            ) * xs[s].get(cid, 0.0)
            outflow += (vs[s] + (col.draw_v[s] if s < col.n else 0.0)) * y_eq[s].get(cid, 0.0)
            if scales is not None:
                scale = scales[s * nc + i]
            else:
                scale = max(abs(inflow), abs(outflow), col.f_total * 1e-6)
            if flow_mags is not None:
                flow_mags.append(scale)
            out.append((inflow - outflow) / scale)
        # Canonical NS summation row (as in the dense residual).
        out.append(sum(xs[s].values()) - sum(k.get(cid, 1.0) * xs[s].get(cid, 0.0) for cid in col.comps))
        if flow_mags is not None:
            flow_mags.append(1.0)
        if s not in model.h_stages:
            continue
        h_in = 0.0
        if vap_donor is not None:
            h_in += _vapour_in(model, vs, draw_flows, s, vap_donor) * tb.h_vapor(
                _flash_ready(y_eq[vap_donor], col.feed_comp), ts[vap_donor], col.pressures[vap_donor]
            )
        if donor is not None and link_in is None:
            h_in += liquid[donor] * tb.h_liquid(
                _flash_ready(xs[donor], col.feed_comp), ts[donor], col.pressures[donor]
            )
        if link_in is not None:
            d = model.layout.draw_links[link_in].from_stage
            h_in += draw_flows[link_in] * tb.h_liquid(
                _flash_ready(xs[d], col.feed_comp), ts[d], col.pressures[d]
            )
        for ret_top in model.vapour_return_at.get(s, ()):
            h_in += vs[ret_top] * tb.h_vapor(
                _flash_ready(y_eq[ret_top], col.feed_comp), ts[ret_top], col.pressures[ret_top]
            )
        if wall is not None:
            h_in += _wall_h_in(model, tb, liquid, l_wall, xs, ts, y_eq, draw_flows, s)
        h_in += part.h_flow
        if s == 0 and col.condenser == "total":
            h_in += l0 * tb.h_liquid(_flash_ready(x_reflux, col.feed_comp), ts[0], col.pressures[0])
        h_in += model.section_duty_at.get(s, 0.0)
        if col.pumparounds:
            # The dense residual's pumparound algebra: the return carries the
            # draw liquid's enthalpy shifted by the cooler duty (or taken at
            # the fixed return temperature), at the draw-stage pressure.
            for idx, pa in _live_pumparounds(col):
                if pa.return_stage - 1 != s:
                    continue
                d_idx = pa.draw_stage - 1
                x_d = _flash_ready(xs[d_idx], col.feed_comp)
                flow = col.pa_flows[idx]
                if pa.return_T_K is not None:
                    h_ret = tb.h_liquid(x_d, pa.return_T_K, col.pressures[d_idx])
                else:
                    h_ret = (
                        tb.h_liquid(x_d, ts[d_idx], col.pressures[d_idx])
                        + (pa.duty_W if pa.duty_W is not None else 0.0) / flow
                    )
                h_in += flow * h_ret
        if col.stage_q and s < col.n:
            h_in += col.stage_q[s]
        own_draw = draw_flows[model.draw_link_at_stage[s]] if s in model.draw_link_at_stage else 0.0
        if wall is not None and s == wall.above:
            own_draw = l_wall
        h_out = (vs[s] + (col.draw_v[s] if s < col.n else 0.0)) * tb.h_vapor(
            _flash_ready(y_eq[s], col.feed_comp), ts[s], col.pressures[s]
        ) + (
            liquid[s]
            + (col.draw_l[s] if s < col.n else 0.0)
            + own_draw
            + (model.pa_out[s] if col.pumparounds and s < col.n else 0.0)
        ) * tb.h_liquid(_flash_ready(xs[s], col.feed_comp), ts[s], col.pressures[s])
        if h_evals is not None:
            h_evals[0] += 4
        if flow_mags is not None:
            flow_mags.append(h_scale)
        out.append((h_in - h_out) / h_scale)
    if model.layout.beta_index is not None:
        if flow_mags is not None:
            flow_mags.append(1.0)
        out.append(_wall_dp_residual(model, tb, ts, vs, y_eq))
    return out


def _vapour_in(model: _GraphModel, vs: list[float], draw_flows: list[float], s: int, donor: int) -> float:
    """The cascade vapour flow entering stage s from its donor below: all of
    the donor's vapour, except on the main side's bottom stage of a dividing
    wall, which receives what the prefractionator does not take."""
    wall = model.wall
    if wall is not None and s == wall.below - 1:
        return vs[donor] - draw_flows[-1]
    return vs[donor]


def _wall_m_in(
    wall: _WallSection,
    liquid: list[float],
    l_wall: float,
    xs: list[dict[str, float]],
    y_eq: list[dict[str, float]],
    draw_flows: list[float],
    s: int,
    cid: str,
) -> float:
    """Component inflow over the wall links into stage s (mol/s): the split
    liquid into the prefractionator top (at the composition of the stage
    above the wall), the split vapour into its bottom (at the composition of
    the stage below), and its bottom liquid into the stage below the wall.
    The prefractionator top vapour's return is a ``vapour_return_at`` term."""
    flow = 0.0
    if s == wall.stages[0]:
        flow += l_wall * xs[wall.above].get(cid, 0.0)
    if s == wall.stages[-1]:
        flow += draw_flows[-1] * y_eq[wall.below].get(cid, 0.0)
    if s == wall.below:
        bottom = wall.stages[-1]
        flow += liquid[bottom] * xs[bottom].get(cid, 0.0)
    return flow


def _wall_h_in(
    model: _GraphModel,
    tb: _ThermoBox,
    liquid: list[float],
    l_wall: float,
    xs: list[dict[str, float]],
    ts: list[float],
    y_eq: list[dict[str, float]],
    draw_flows: list[float],
    s: int,
) -> float:
    """Enthalpy inflow over the wall links into stage s (W), the energy
    counterpart of ``_wall_m_in``: each stream at its source stage's state."""
    wall = model.wall
    assert wall is not None
    col = model.col
    h = 0.0
    if s == wall.stages[0]:
        a = wall.above
        h += l_wall * tb.h_liquid(_flash_ready(xs[a], col.feed_comp), ts[a], col.pressures[a])
    if s == wall.stages[-1]:
        b = wall.below
        h += draw_flows[-1] * tb.h_vapor(_flash_ready(y_eq[b], col.feed_comp), ts[b], col.pressures[b])
    if s == wall.below:
        q = wall.stages[-1]
        h += liquid[q] * tb.h_liquid(_flash_ready(xs[q], col.feed_comp), ts[q], col.pressures[q])
    return h


def _wall_side_stages(wall: _WallSection) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """(prefractionator stages, main-side wall stages), 0-based graph indices."""
    return wall.stages, tuple(range(wall.above + 1, wall.below))


def _wall_side_loads(
    model: _GraphModel, tb: _ThermoBox, ts: list[float], vs: list[float], y_eq: list[dict[str, float]]
) -> tuple[float, float] | None:
    """(prefractionator, main side) hydraulic loads of the wall sections:
    each side's sum over its stages of m_V^2 / rho_V divided by its
    cross-section squared (relative areas: ``area_fraction`` and its
    complement). That is each side's pressure drop up to one common factor
    (see ``_wall_dp_residual``). None when a stage vapour is not evaluable."""
    wall = model.wall
    assert wall is not None
    col = model.col
    loads: list[float] = []
    areas = (wall.area_fraction, 1.0 - wall.area_fraction)
    for side, area in zip(_wall_side_stages(wall), areas, strict=True):
        total = 0.0
        for s in side:
            if not y_eq[s]:
                return None
            try:
                props = tb._thermo.phase_props(
                    _flash_ready(y_eq[s], col.feed_comp), ts[s], col.pressures[s], PhaseKind.VAPOR
                )
            except ValueError:
                return None
            mass = vs[s] * props.molecular_weight / 1000.0  # kg/s
            total += mass * mass / props.density
        loads.append(total / (area * area))
    return loads[0], loads[1]


def _wall_dp_residual(
    model: _GraphModel, tb: _ThermoBox, ts: list[float], vs: list[float], y_eq: list[dict[str, float]]
) -> float:
    """The vapour-split row: equal pressure drop across the two wall sides.

    Both sides of the wall run between the same two stages (above and below
    the wall), so in operation the vapour divides until their pressure drops
    are equal; the split is set by the wall position, not controlled
    (Dejanovic, Matijasevic & Olujic, Chem. Eng. Process. 49 (2010) 559-580,
    sect. 4). Each stage's pressure drop is taken in the turbulent dry-bed
    form dP = xi rho_V u^2 / 2 (the high-Reynolds limit f0 -> C3 of
    Stichlmair, Bravo & Fair, Gas Sep. Purif. 3 (1989) 19-28, dry bed), with
    u = m_V / (rho_V A): with the same internals and stage height on both
    sides, xi and the stage height cancel and

        sum_pre m_V^2 / (rho_V A_pre^2) = sum_main m_V^2 / (rho_V A_main^2).

    The vapour leaving each wall stage is the load through its segment, at
    the stage's real-gas density from the package. The row is that
    difference over the sum (dimensionless, in [-1, 1]); an unevaluable
    vapour reads 1.0 (not converged). The liquid load's contribution to the
    irrigated pressure drop is neglected (the dry-bed approximation).
    """
    loads = _wall_side_loads(model, tb, ts, vs, y_eq)
    if loads is None:
        return 1.0
    pre, main = loads
    return (pre - main) / max(pre + main, 1e-300)


def _graph_residual_scales(
    model: _GraphModel, tb: _ThermoBox, l0: float, u: list[float], t_bot_tear: float | None
) -> list[float]:
    """The frozen per-M-row scale vector, from the pass's reference state.

    Dense P1-11 ruling on issue #153, applied to the graph rows: each M row is
    scaled by ``max(|inflow|, |outflow|, f_total * 1e-6)`` evaluated once HERE
    at the reference state, never per evaluation - a per-evaluation scale makes
    a row ``(in - out)/max(|in|, |out|)`` saturated and non-smooth, and a
    residual-probe-derived scale collapses to the ``f_total * 1e-6`` floor on
    rows the seed balances coincidentally, demanding machine-precision balance
    there (measured: the two-stripper mesh stalled at M ~ 1e2 on rows whose
    raw imbalance was ~1e-2 mol/s).
    """
    xs, ts, vs, draw_flows = _graph_unpack(model, u, t_bot_tear)
    flow_mags: list[float] = []
    _graph_residual_vector(model, tb, l0, xs, ts, vs, draw_flows, flow_mags=flow_mags)
    return flow_mags


def _graph_pack(prof: _Profile, model: _GraphModel) -> list[float]:
    """Pack a graph profile into the unknown vector (dense `_pack_state`
    semantics; the draw flows round-trip through ``prof.draw_flows``)."""
    col = model.col
    layout = model.layout
    u = [prof.x[s].get(cid, 0.0) for s in range(layout.n_graph) for cid in col.comps]
    u.extend(prof.T)
    u.extend(prof.V[j] for j in layout.v_free)
    if layout.beta_index is not None:
        assert model.wall is not None
        u.append(prof.draw_flows[-1] / max(prof.V[model.wall.below], _FLOW_FLOOR))
    return u


def _graph_unpack(
    model: _GraphModel, u: list[float], t_bot_tear: float | None
) -> tuple[list[dict[str, float]], list[float], list[float], list[float]]:
    """Split the unknown vector into (xs, ts, vs, draw_flows) - dense semantics:
    x clamped at 0, T clamped to the operating band, flows floored."""
    col = model.col
    layout = model.layout
    xs = [
        {cid: max(u[s * layout.nc + i], 0.0) for i, cid in enumerate(col.comps)}
        for s in range(layout.n_graph)
    ]
    ts = [min(max(u[layout.t_base + s], col.t_band_lo), col.t_band_hi) for s in range(layout.n_graph)]
    vs = [_FLOW_FLOOR] * layout.n_graph
    for pos, s in enumerate(layout.v_free):
        vs[s] = max(_FLOW_FLOOR, u[layout.v_base + pos])
    if t_bot_tear is not None:
        vs[col.n - 1] = t_bot_tear
    if model.v_top_pin is not None:
        vs[0] = model.v_top_pin
    # Stripper draw flows are derived, not unknowns: each section's total
    # balance pins its draw to the returned vapour, the product rate and the
    # section feeds (the product-rate spec is exact by construction).
    draw_flows = [
        max(
            _FLOW_FLOOR,
            vs[top] + rate - sum(model.feeds[s].total for s in range(top, bottom + 1)),
        )
        for _k, top, bottom, rate in model.section_total_rows
    ]
    wall = model.wall
    if wall is not None:
        # The wall's split vapour flow rides as the trailing entry: the
        # specified fraction, or the Newton unknown beta, of V_below.
        beta = wall.vapour_split
        if layout.beta_index is not None:
            beta = min(max(u[layout.beta_index], _BETA_MIN), 1.0 - _BETA_MIN)
        assert beta is not None
        draw_flows.append(beta * vs[wall.below])
    return xs, ts, vs, draw_flows


def _graph_apply_state(prof: _Profile, u: list[float], model: _GraphModel, t_bot_tear: float | None) -> None:
    """Write a trial state back into the profile (dense `_apply_state` semantics)."""
    col = model.col
    xs, ts, vs, draw_flows = _graph_unpack(model, u, t_bot_tear)
    prof.x = [_flash_ready({cid: max(v, 0.0) for cid, v in x_s.items()}, col.feed_comp) for x_s in xs]
    prof.T = ts
    prof.V = vs
    prof.draw_flows = draw_flows
    prof.L = _graph_liquid_profile(model, prof.l0, vs, draw_flows)


def _graph_gate_model(col: _Column, prof: _Profile) -> _GraphModel:
    """The graph model the exact gate reads: every column tear pinned at the
    profile's own value (kettle boilup and a partial condenser's top vapour),
    so the gate checks exactly the state the profile holds."""
    return _graph_model(col, v_top_pin=prof.V[0] if col.condenser == "partial" else None)


def _graph_state(
    col: _Column, prof: _Profile
) -> tuple[_GraphModel, list[dict[str, float]], list[float], list[float], list[float]]:
    """(model, xs, ts, vs, draw_flows) of a graph profile, through the solve's
    own pack/unpack - the draw flows DERIVED from the section balances, so
    the product-rate specs hold exactly in every gated state."""
    model = _graph_gate_model(col, prof)
    u = _graph_pack(prof, model)
    t_bot = prof.V[col.n - 1] if col.reboiler == "kettle" else None
    xs, ts, vs, draw_flows = _graph_unpack(model, u, t_bot)
    return model, xs, ts, vs, draw_flows


def _graph_exact_residuals(col: _Column, tb: _ThermoBox, prof: _Profile) -> tuple[float, float]:
    """The exact gate over the whole stage graph (S0-1c step 3).

    `_exact_residuals`' semantics extended over the graph: the live
    residual `_graph_residual_vector` - interlink terms included - at the
    profile state, with the profile's refreshed y as the stage-K vapour
    estimates and NO frozen fallbacks (an unevaluable stage reads 1.0, not
    converged), per-row scales derived from the gated state. M is the max
    over the component balances AND the summation rows (the bubble-point
    condition), H the max over the enthalpy rows. The dense gate only sees
    the main stages and none of the draw/return terms, so a graph column
    must never be gated by it.
    """
    model, xs, ts, vs, draw_flows = _graph_state(col, prof)
    r = _graph_residual_vector(model, tb, prof.l0, xs, ts, vs, draw_flows, y_seeds=[dict(y) for y in prof.y])
    nc = model.layout.nc
    max_m = 0.0
    max_h = 0.0
    for s, (start, stop) in enumerate(_stage_row_ranges(model)):
        for row in range(start, start + nc + 1):  # M rows and the summation row
            max_m = max(max_m, abs(r[row]))
        if s in model.h_stages:
            max_h = max(max_h, abs(r[stop - 1]))
    if model.layout.beta_index is not None:
        max_m = max(max_m, abs(r[-1]))  # the wall's pressure-drop row
    return max_m, max_h


def _graph_refresh_y(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """y = K(T, P) x on every graph stage (the dense `_refresh_y` over the
    graph, with the graph stage-K arguments for section stages)."""
    model = _graph_gate_model(col, prof)
    for s in range(col.n_graph):
        feed_part, draw_total = _graph_k_args(model, s)
        k = _stage_k_values(
            col,
            tb,
            s,
            prof.x[s],
            prof.y[s],
            prof.T[s],
            prof.L[s],
            prof.V[s],
            feed_part=feed_part,
            draw_total=draw_total,
        )
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[s], col.feed_comp), prof.T[s], col.pressures[s])
        if k is None:
            k = {cid: 1.0 for cid in col.comps}
        prof.y[s] = _graph_y_eq(k, prof.x[s])


def _stage_row_ranges(model: _GraphModel) -> list[tuple[int, int]]:
    """(first row, one past last row) of each stage's residual block."""
    nc = model.layout.nc
    ranges: list[tuple[int, int]] = []
    pos = 0
    for s in range(model.layout.n_graph):
        start = pos
        pos += nc + 1
        if s in model.h_stages:
            pos += 1
        ranges.append((start, pos))
    return ranges


def _rowsout_sets(model: _GraphModel) -> tuple[list[frozenset[int]], list[frozenset[int]]]:
    """Per stage: the residual rows affected by its x (or T) and by its V.

    x/T of stage s enter its own rows, its cascade neighbours' rows (the liquid
    donor above reads the composition and enthalpy; the vapour donor below reads
    y = K(T, x) x), and - over the interlinks - the section top's rows (a draw
    stage's composition and enthalpy) and the return stage's rows (the section
    top's composition and enthalpy). V of stage s enters its own and its liquid
    donor's rows through the cascade flows. The top stage of a cascade is
    special: its vapour flow sits in every liquid flow of that cascade (the
    telescoped recursion), so its V reaches the whole cascade - and over the
    interlinks, the return stage's rows.
    """
    g = model.layout.n_graph
    rows = _stage_row_ranges(model)

    def block(s: int) -> frozenset[int]:
        return frozenset(range(rows[s][0], rows[s][1]))

    rows_x: list[frozenset[int]] = []
    rows_v: list[frozenset[int]] = []
    return_of_top = {top: ret for ret, tops in model.vapour_return_at.items() for top in tops}
    for s in range(g):
        nx = set(block(s))
        nv = set(block(s))
        donor = model.liquid_donor[s]
        vap = model.vapour_donor[s]
        if donor is not None:
            nx |= block(donor)
            nv |= block(donor)  # liquid[s-1] carries V_s
        if vap is not None:
            nx |= block(vap)
        if s in model.draw_link_at_stage:
            nx |= block(model.section_top_of_link[model.draw_link_at_stage[s]])
        for ret_top in model.vapour_return_at.get(s, ()):
            nx |= block(ret_top)
            nv |= block(ret_top)
        if s in model.link_at_top:
            nx |= block(return_of_top[s])  # its x/T ride the return link out
            nv |= block(return_of_top[s])  # the return stage's rows read vs[s]
            # its V sits in every section liquid below it (-V_top telescoped term)
            q = s
            while True:
                nxt = model.vapour_donor[q]
                if nxt is None:
                    break
                nv |= block(nxt)
                q = nxt
        if s == 0 and model.col.condenser != "partial":
            # V_1 sits in every main-stage liquid flow (telescoped recursion).
            for q in range(model.col.n):
                nv |= block(q)
        rows_x.append(frozenset(nx))
        rows_v.append(frozenset(nv))
    # A section top's V now carries its DERIVED draw flow with it: the draw
    # feeds the main column's liquid cascade at and below the draw stage and
    # the section's own cascade, so one perturbation reaches all of it.
    # Its V also enters the main cascade's total balance at the return stage
    # (the returned vapour), so every main liquid from there down moves too.
    for k in range(len(model.layout.draw_links)):
        top = model.section_top_of_link[k]
        draw_stage = model.draw_stage_of_link[k]
        for q in range(min(draw_stage, return_of_top[top]), g):
            rows_v[top] = rows_v[top] | block(q)
    if model.wall is not None:
        _wall_rowsout(model, block, rows_x, rows_v)
    return rows_x, rows_v


def _wall_rowsout(
    model: _GraphModel,
    block: Callable[[int], frozenset[int]],
    rows_x: list[frozenset[int]],
    rows_v: list[frozenset[int]],
) -> None:
    """Add a dividing wall's couplings to the per-stage affected-row sets.

    x/T: the prefractionator top's vapour returns above the wall, the stage
    below the wall sends vapour to the prefractionator bottom, whose liquid
    comes back to it. V: the split liquid is a share of the liquid leaving
    the stage above the wall, which carries V_1, V_above+1 and the
    prefractionator top vapour - those reach every main stage from there down
    and the whole prefractionator; V_below carries the split vapour into the
    prefractionator bottom. Every wall-side stage's x, T and V enter the
    pressure-drop row (when beta is an unknown).
    """
    wall = model.wall
    assert wall is not None
    col = model.col
    a, b, top, bottom = wall.above, wall.below, wall.stages[0], wall.stages[-1]
    pre = frozenset().union(*(block(s) for s in wall.stages))
    down = frozenset().union(*(block(q) for q in range(a, col.n))) | pre
    rows_x[top] = rows_x[top] | block(a)
    rows_x[b] = rows_x[b] | block(bottom)
    rows_x[bottom] = rows_x[bottom] | block(b)
    rows_v[b] = rows_v[b] | block(bottom) | block(b - 1)
    for s in (0, a + 1, top):
        rows_v[s] = rows_v[s] | down | block(a)
    if model.layout.beta_index is not None:
        dp_row = frozenset({_stage_row_ranges(model)[-1][1]})
        for s in (*wall.stages, *range(a + 1, b)):
            rows_x[s] = rows_x[s] | dp_row
            rows_v[s] = rows_v[s] | dp_row


def _rowsout_block(model: _GraphModel, stages: tuple[int, ...]) -> frozenset[int]:
    """Every residual row of the given stages."""
    rows = _stage_row_ranges(model)
    return frozenset(r for s in stages for r in range(rows[s][0], rows[s][1]))


def _colour_groups(domain: list[int], rowsout: list[frozenset[int]]) -> list[list[int]]:
    """Greedy stage colouring: stages whose affected rows are disjoint share a
    colour (cascade distance >= 3 for the x/T indices, >= 2 for V)."""
    groups: list[list[int]] = []
    for s in domain:
        for g in groups:
            if all(rowsout[s].isdisjoint(rowsout[q]) for q in g):
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def _graph_fd_jacobian(
    model: _GraphModel,
    residuals: Callable[[list[float]], list[float]],
    r0: list[float],
    u: list[float],
    evals_counter: list[int],
) -> tuple[scipy.sparse.csr_matrix, int, int] | None:
    """Stage-coloured FD Jacobian as a scipy.sparse CSR matrix.

    Returns (J, colour_count, evaluation_count), or None when a perturbed trial
    state is unevaluable (the caller ends the pass like the dense fallback).
    One residual evaluation per (variable position, colour group): the position
    is perturbed across the whole group at once, so the evaluation count is
    bounded by the colour count times the variables per stage, not by the
    unknown count.
    """
    layout = model.layout
    nc = layout.nc
    n_rows = len(r0)
    rows_x, rows_v = _rowsout_sets(model)
    stages = list(range(layout.n_graph))
    groups_x = _colour_groups(stages, rows_x)
    groups_v = _colour_groups(layout.v_free, rows_v) if layout.v_free else []
    colour_count = len(groups_x)

    entries: list[tuple[int, int, float]] = []

    def perturb(indices: list[tuple[int, float]]) -> list[float] | None:
        u2 = list(u)
        for idx, delta in indices:
            u2[idx] += delta
        try:
            r1 = residuals(u2)
        except (ColumnConvergenceError, ValueError):
            return None
        evals_counter[0] += 1
        return r1

    def record(s: int, idx: int, delta: float, r1: list[float], rows: frozenset[int]) -> None:
        for row in rows:
            entries.append((row, idx, (r1[row] - r0[row]) / delta))

    # x component slots and the temperature slot: identical colouring.
    for p in range(nc + 1):
        for group in groups_x:
            idxs = []
            for s in group:
                idx = s * nc + p if p < nc else layout.t_base + s
                idxs.append((idx, max(abs(u[idx]) * 1e-7, 1e-9)))
            r1 = perturb(idxs)
            if r1 is None:
                return None
            for s in group:
                idx = s * nc + p if p < nc else layout.t_base + s
                delta = max(abs(u[idx]) * 1e-7, 1e-9)
                record(s, idx, delta, r1, rows_x[s])

    # Vapour slots: their own colouring (V reaches one stage further through
    # the liquid recursion).
    for group in groups_v:
        idxs = []
        for s in group:
            idx = layout.v_base + layout.v_free.index(s)
            idxs.append((idx, max(abs(u[idx]) * 1e-7, 1e-9)))
        r1 = perturb(idxs)
        if r1 is None:
            return None
        for s in group:
            idx = layout.v_base + layout.v_free.index(s)
            delta = max(abs(u[idx]) * 1e-7, 1e-9)
            record(s, idx, delta, r1, rows_v[s])

    if layout.beta_index is not None and model.wall is not None:
        # The wall's vapour split: one column of its own. It moves the
        # vapour into both wall-side bottoms and the liquids around them.
        idx = layout.beta_index
        delta = max(abs(u[idx]) * 1e-7, 1e-9)
        r1 = perturb([(idx, delta)])
        if r1 is None:
            return None
        wall = model.wall
        rows = _rowsout_block(model, (wall.below - 1, wall.below, wall.stages[-1]))
        record(wall.below, idx, delta, r1, rows | {n_rows - 1})

    if not entries:
        return None
    n_evals = evals_counter[0]
    jac = scipy.sparse.coo_matrix(
        ([e[2] for e in entries], ([e[0] for e in entries], [e[1] for e in entries])),
        shape=(n_rows, layout.n_unk),
    ).tocsr()
    return jac, colour_count, n_evals


def _lm_damped_step_sparse(jac: scipy.sparse.csr_matrix, r0: list[float], lam: float) -> list[float] | None:
    """Levenberg-Marquardt step for the sparse Jacobian (dense `_lm_damped_step`
    semantics: Marquardt scaling by diag(J'J)). None when singular."""
    try:
        jtj = (jac.T @ jac).tocsc()
        damping = scipy.sparse.diags(jtj.diagonal()).tocsc()
        a = (jtj + lam * damping).tocsc()
        rhs = -(jac.T @ np.asarray(r0))
        sol = scipy.sparse.linalg.spsolve(a, rhs)
    except Exception:  # noqa: BLE001 - a singular damped system abandons the pass
        return None
    if not np.all(np.isfinite(sol)):
        return None
    return [float(v) for v in sol]


def _extend_profile_to_graph(col: _Column, prof: _Profile) -> None:
    """Seed the section stages from the draw stage's state, and the draw flows
    from the draw stages' liquid (step 3 owns the sequential-section
    initializer; this keeps step-2 callers runnable)."""
    g = col.n_graph
    if len(prof.T) >= g:
        return
    for sec in col.sections:
        if not sec.stages:
            continue
        d = sec.draw_stage - 1
        for _s in sec.stages:
            prof.x.append(dict(prof.x[d]))
            prof.T.append(prof.T[d])
            prof.V.append(max(_FLOW_FLOOR, 0.3 * prof.V[d]))
            prof.L.append(max(_FLOW_FLOOR, prof.L[d]))
            prof.y.append(dict(prof.y[d]))
    links = [lk for lk in col.interlinks if lk.phase == "liquid"]
    prof.draw_flows = [max(_FLOW_FLOOR, prof.L[lk.from_stage]) for lk in links]


class _GraphNSEngine:
    """The graph engine's injected pieces for the shared NS controller.

    The residual closure is the stage-graph residual
    (`_graph_residual_vector`, interlinks included), the Jacobian the
    stage-coloured FD approximation as a scipy.sparse matrix
    (`_graph_fd_jacobian`), and the linear solve a ``scipy.sparse`` LU of the
    block-sparse system. The pass loop, the pass gate (refreshed y = K*x,
    the exact refreshed-thermo norms at the mesh tolerances, best-iterate
    tracking - the dense engine's own gate, shared in `_ns_controller`),
    the line search and acceptance (``_ns_try_accept``, live-norm on the
    zero/one-tear path like the dense engine) and the rho-based LM damping
    adaptation are the shared controller's.

    The one graph-only safeguard is the per-pass temperature clamp
    (``cap_step``): active ONLY on columns with stripper sections - a bad
    Jacobian can shoot a section bottom 100+ K in one accepted step
    (measured: T drifting to 480 K on a steam-stripper bottom, from which
    the line search never recovered). A linear column has no sections, so
    the clamp is a no-op there (asserted by the targeted test) and the graph
    run lands on the dense result through the identical controller.
    """

    prof: _Profile
    live_norm: bool
    ex_m: float
    ex_h: float

    def __init__(
        self,
        col: _Column,
        tb: _ThermoBox,
        prof: _Profile,
        t_bot_tear: float | None,
        model: _GraphModel,
        m_tol: float,
    ) -> None:
        self._col = col
        self._tb = tb
        self.prof = prof
        self._t_bot_tear = t_bot_tear
        self._model = model
        self.m_tol = m_tol
        self.live_norm = True  # P1-13 change 2: every tear count
        self.ex_m = float("inf")
        self.ex_h = float("inf")
        self._k_last: list[dict[str, float] | None] = [None] * model.layout.n_graph
        self.best_u: list[float] | None = None
        self.best_m = float("inf")
        self.best_h = float("inf")
        self._k_harvest: list[dict[str, float] | None] = []
        self._colours = 0
        self._n_evals = 0

    def begin_pass(self) -> tuple[list[float], Callable[[list[float]], list[float]]]:
        """One pass's reference state, residual closure and frozen quantities.

        Per-stage K fallbacks frozen from the pass's reference state, with
        the last REAL K per stage persisted across passes: a stage whose
        flash fails mid-solve (section bottoms drift far from the seed
        first) must fall back to its last REAL K - a neutral K=1.0 fallback
        makes the summation row sum x (1 - K) identically zero, a zero
        Jacobian row and a singular solve (measured: MatrixRankWarning and a
        stalled Newton on the two-stripper case).
        """
        col, tb, prof, model = self._col, self._tb, self.prof, self._model
        layout = model.layout
        # Persist the previous pass's real K evaluations (the harvest the old
        # graph-row checkpoint applied): a stage whose flash fails mid-solve
        # falls back to its last REAL K in the freeze below.
        for s, k in enumerate(self._k_harvest):
            if k is not None:
                self._k_last[s] = k
        k_fallbacks: list[dict[str, float]] = []
        for s in range(layout.n_graph):
            feed_part, draw_total = _graph_k_args(model, s)
            k = _stage_k_values(
                col,
                tb,
                s,
                prof.x[s],
                prof.y[s],
                prof.T[s],
                prof.L[s],
                prof.V[s],
                feed_part=feed_part,
                draw_total=draw_total,
            )
            if k is None:
                k = tb.k_estimate(_flash_ready(prof.x[s], col.feed_comp), prof.T[s], col.pressures[s])
            if k is None:
                k = self._k_last[s]
            k_fallbacks.append(k or {cid: 1.0 for cid in col.comps})

        u = _graph_pack(prof, model)
        k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] = {}
        k_misses = [0]
        h_evals = [0]
        self._k_harvest = [None] * layout.n_graph
        k_harvest = self._k_harvest
        scales = _graph_residual_scales(model, tb, prof.l0, u, self._t_bot_tear)
        y_seeds: list[dict[str, float]] | None = None
        if tb.exact_surface:
            if col.is_graph:
                _graph_refresh_y(col, tb, prof)
            else:
                _refresh_y(col, tb, prof)
            y_seeds = [dict(y) for y in prof.y]

        def residuals(
            u_try: list[float],
            k_fallbacks: list[dict[str, float]] = k_fallbacks,
            k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] = k_cache,
            k_misses: list[int] = k_misses,
            h_evals: list[int] = h_evals,
            scales: list[float] = scales,
            k_harvest: list[dict[str, float] | None] = k_harvest,
        ) -> list[float]:
            xs, ts, vs, draw_flows = _graph_unpack(model, u_try, self._t_bot_tear)
            return _graph_residual_vector(
                model,
                tb,
                prof.l0,
                xs,
                ts,
                vs,
                draw_flows,
                k_fallbacks=k_fallbacks,
                k_cache=k_cache,
                k_misses=k_misses,
                h_evals=h_evals,
                scales=scales,
                k_out=k_harvest,
                y_seeds=y_seeds,
            )

        return u, residuals

    def m_norm_of(self, r: list[float]) -> float:
        """Max scaled residual over the graph's M rows (per stage block)."""
        nc = self._model.layout.nc
        vals = []
        pos = 0
        for s in range(self._model.layout.n_graph):
            for _ in range(nc):
                vals.append(abs(r[pos]))
                pos += 1
            pos += 1
            if s in self._model.h_stages:
                pos += 1
        if self._model.layout.beta_index is not None:
            vals.append(abs(r[-1]))  # the wall's pressure-drop row
        return max(vals, default=0.0)

    def h_norm_of(self, r: list[float]) -> float:
        """Max scaled residual over the graph's H rows."""
        nc = self._model.layout.nc
        vals = []
        pos = 0
        for s in range(self._model.layout.n_graph):
            pos += nc + 1
            if s in self._model.h_stages:
                vals.append(abs(r[pos]))
                pos += 1
        return max(vals, default=0.0)

    def norms(self, r: list[float]) -> tuple[float, float]:
        return (self.m_norm_of(r), self.h_norm_of(r))

    def jacobian(
        self, residuals: Callable[[list[float]], list[float]], r0: list[float], u: list[float]
    ) -> Any:
        evals_counter = [0]
        bundle = _graph_fd_jacobian(self._model, residuals, r0, u, evals_counter)
        if bundle is None:
            return None
        jac, colour_count, n_evals = bundle
        self._colours, self._n_evals = colour_count, n_evals
        return jac

    def solve_linear(self, jac: Any, r0: list[float]) -> list[float] | None:
        try:
            sol = scipy.sparse.linalg.spsolve(jac.tocsc(), -np.asarray(r0))
            if not np.all(np.isfinite(sol)):
                return None
        except Exception:  # noqa: BLE001 - a singular sparse system ends the pass like the dense path
            return None
        return [float(v) for v in sol]

    def lm_step(self, jac: Any, r0: list[float], lam: float) -> list[float] | None:
        return _lm_damped_step_sparse(jac, r0, lam)

    def linear_prediction(self, jac: Any, r0: list[float], step: list[float]) -> list[float]:
        lin = np.asarray(r0) + jac @ np.asarray(step)
        return [float(v) for v in lin]

    def cap_step(self, step: list[float]) -> None:
        """Per-pass temperature step bound (K) - stripper sections only.

        The unpack's band clamp is far too wide to stop a bad Jacobian from
        shooting a section bottom 100+ K in one accepted step (measured: T
        drifting to 480 K on a steam-stripper bottom, from which the line
        search never recovered). Real simulators bound dT per NS pass for
        the same reason. A linear column has no sections, so the bound is
        INACTIVE there - the targeted test asserts the no-op, and the
        solve-level parity test shows the shared controller reproducing the
        dense result on a linear column with the clamp present but not
        firing.
        """
        if not self._model.col.is_graph:
            return
        layout = self._model.layout
        for s in range(layout.n_graph):
            step[layout.t_base + s] = max(-_NS_MAX_DT, min(_NS_MAX_DT, step[layout.t_base + s]))
        if layout.beta_index is not None:
            k = layout.beta_index
            step[k] = max(-_NS_MAX_DBETA, min(_NS_MAX_DBETA, step[k]))

    def apply(self, prof: _Profile, u: list[float]) -> None:
        _graph_apply_state(prof, u, self._model, self._t_bot_tear)

    def exact_norms(self, prof: _Profile) -> tuple[float, float]:
        """The exact refreshed-thermo norms - the shared gate's own surface.

        Refreshes y = K*x first: the NS rows derive vapour compositions as
        K*x, so a state whose STORED y lags the iterate reads as converged
        internally while the exact residual - which uses the stored y - is
        wide open (measured, review round 2: the two runs' stored y differed
        by 0.219 at pass 2). The dense engine's exact_norms, verbatim."""
        if self._col.is_graph:
            _graph_refresh_y(self._col, self._tb, prof)
            return _graph_exact_residuals(self._col, self._tb, prof)
        _refresh_y(self._col, self._tb, prof)
        return _exact_residuals(self._col, self._tb, prof)

    def trace_jacobian_failed(self) -> None:
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} | FD unavailable"
        )

    def trace_solve_failed(self) -> None:
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} | LU singular"
        )

    def trace_pass(
        self,
        r0: list[float],
        jac: Any,
        step: list[float],
        lam: float,
        lam_lm: float,
        ach_m: float,
        ach_h: float,
        via: str,
        accepted: bool,
    ) -> None:
        _ = r0, jac, step, lam_lm, ach_m, ach_h, via
        self.prof.ns_trace.append(
            f"pass {self.prof.ns_passes}: exact M={self.ex_m:.3e} H={self.ex_h:.3e} "
            f"| colours={self._colours} jac_evals={self._n_evals} lam={lam:.3g} accepted={accepted}"
        )

    def exhausted(self) -> None:
        # Budget exhausted: restore the best iterate and let the final gate
        # decide - a state that reached the mesh gate at any pass must not be
        # discarded by later passes.
        if self.live_norm and self.best_u is not None:
            self.apply(self.prof, self.best_u)

    def finish(self) -> None:
        """Final acceptance on the exact refreshed-thermo norms at the mesh
        tolerances - the shared gate's own surface, on the best iterate
        across passes. Identical semantics to the dense engine's finish."""
        if self.live_norm and self.best_u is not None:
            self.apply(self.prof, self.best_u)
        prof = self.prof
        m_res, h_res = self.exact_norms(prof)
        prof.ns_used = True
        if m_res > self.m_tol or h_res > _MESH_H_TOL:
            raise ColumnConvergenceError(
                f"graph Naphtali-Sandholm stalled: max residuals M={m_res:.2e}, H={h_res:.2e}"
                + (f" | {'; '.join(prof.ns_trace)}" if prof.ns_trace else "")
            )


def _graph_naphtali_sandholm(
    col: _Column,
    tb: _ThermoBox,
    prof: _Profile,
    t_bot_tear: float | None,
    top_vapour: float | None = None,
    ns_max: int | None = None,
) -> _Profile:
    """Graph Naphtali-Sandholm: damped Newton over the whole stage graph.

    Same unknown packing and residual algebra as the dense fallback, extended
    over the graph with the interlink terms and the derived per-section draw
    flows. The Jacobian is stage-coloured (see module docstring) and the step
    solves with scipy.sparse LU; the pass loop, the pass gate, the line
    search and acceptance, the LM damping adaptation and the final gate are
    the shared controller's (`_ns_controller`) - this engine differs only in
    the injected residual and Jacobian builders and the sparse linear solve.
    Both engines gate on the exact refreshed-thermo norms at the same mesh
    tolerances. Duties are NOT finalized here: whole-unit boundary
    accounting over the graph is step 3. ``ns_max`` overrides the pass
    budget (None = the column's own, by tear count).
    """
    if top_vapour is not None and col.condenser == "total":
        # Top-vapour mode: V_1 pinned, the kettle boilup an unknown.
        t_bot_tear = None
        prof.V[0] = top_vapour
        model = _graph_model(col, v_top_pin=top_vapour)
    else:
        model = _graph_model(
            col,
            kettle_free=t_bot_tear is None and col.reboiler == "kettle",
            v_top_pin=prof.V[0] if col.condenser == "partial" else None,
        )
    _extend_profile_to_graph(col, prof)
    # Vapour tears are NOT Newton unknowns in strategy mode - dense NS pins
    # them from the outer strategy loop. Standalone mode (no caller tear)
    # instead frees the kettle boilup in the model above. Note: a partial
    # condenser's top tear needs the same treatment in _graph_unpack - not
    # exercised until that configuration is routed here.
    m_tol = _MESH_M_TOL if col.n_tears >= 2 else _MESH_M_TOL_ZERO_ONE_TEAR
    if ns_max is None:
        ns_max = _NS_MAX if col.n_tears >= 2 else _NS_MAX_ZERO_ONE_TEAR
    _ns_controller(_GraphNSEngine(col, tb, prof, t_bot_tear, model, m_tol), ns_max)
    return prof
