"""Stage-graph Naphtali-Sandholm: simultaneous damped Newton over the stage graph.

S0-1c step 2 (issue #235). The dense fallback in ``naphtali_sandholm.py`` keeps
the linear columns byte-identical and is untouched; this module carries the same
unknown packing (x, T, V per stage, with the kettle boilup pinned by the tear)
extended over the whole graph (``col.n_graph`` stages) plus one draw-flow
unknown per stripper section, whose slot each liquid interlink record
(``_Interlink.flow_index``) points at. Rows are the same live residual algebra
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
recursion and are coloured separately. The draw-flow unknowns act on every row
at and below their draw stage, so each is perturbed alone. The count of residual
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

import numpy as np
import scipy.sparse
import scipy.sparse.linalg

from .inside_out import (
    _Column,
    _Interlink,
    _Profile,
    _StageFeed,
    _pa_return_terms,
    _pa_stage_flows,
)
from .naphtali_sandholm import _NS_LM_TRIES
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

#: Polish target for the graph solve: below the mesh gate, so a linear column
#: routed through the graph solver and the same column through the dense solver
#: (which stops at the mesh gate) agree on the converged profile to 1e-10.
#: Tightening - never widening - is allowed; the pass budget still caps it.
_GRAPH_POLISH_TARGET = 1e-12

#: Line-search halvings per pass (as in the dense fallback).
_GRAPH_LINE_SEARCH_TRIES = 10

#: Per-pass Newton temperature step bound (K). The unpack's band clamp is far
#: too wide to stop a bad Jacobian from shooting a section bottom 100+ K in one
#: accepted step (measured: T drifting to 480 K on a steam-stripper bottom,
#: from which the line search never recovered). Real simulators bound dT per
#: NS pass for the same reason.
_NS_MAX_DT = 25.0


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
    #: Liquid interlinks in record order (the draw-flow unknown block).
    draw_links: list[_Interlink]
    t_base: int
    v_base: int
    d_base: int
    n_unk: int

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
    #: Main return stage (0-based) -> section top stage (0-based) whose vapour
    #: lands there.
    vapour_return_at: dict[int, int]
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


def _graph_model(col: _Column, kettle_free: bool = False) -> _GraphModel:
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
    v_free = [j for j in range(g) if j not in tears]
    draw_links = [lk for lk in col.interlinks if lk.phase == "liquid" and lk.flow_index is not None]
    t_base = g * nc
    v_base = t_base + g
    d_base = v_base + len(v_free)
    layout = _GraphLayout(
        n_graph=g,
        nc=nc,
        v_free=v_free,
        draw_links=draw_links,
        t_base=t_base,
        v_base=v_base,
        d_base=d_base,
        n_unk=d_base,
    )

    feeds = list(col.feeds) + [_StageFeed() for _ in range(g - len(col.feeds))]
    liquid_donor: list[int | None] = []
    vapour_donor: list[int | None] = []
    section_of: dict[int, tuple[int, ...]] = {}
    for sec in col.sections:
        for s in sec.stages:
            section_of[s - 1] = tuple(j - 1 for j in sec.stages)
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
    vapour_return_at = {
        lk.to_stage: lk.from_stage for lk in col.interlinks if lk.phase == "vapour"
    }
    draw_link_at_stage = {lk.from_stage: k for k, lk in enumerate(draw_links)}
    link_at_top = {lk.to_stage: k for k, lk in enumerate(draw_links)}
    section_duty_at: dict[int, float] = {}
    for sec in col.sections:
        if sec.bottom_stage is not None and sec.stripper.reboiler_duty_W is not None:
            section_duty_at[sec.bottom_stage - 1] = sec.stripper.reboiler_duty_W
    pa_out, pa_in = _pa_stage_flows(col)
    section_total_rows: list[tuple[int, int, int, float]] = []
    for k, link in enumerate(draw_links):
        sec = next((sc for sc in col.sections if sc.draw_stage - 1 == link.from_stage), None)
        assert sec is not None and sec.bottom_stage is not None
        rate = sec.stripper.product_rate
        assert rate is not None  # the parser requires a product rate per section
        section_total_rows.append((k, link.to_stage, sec.bottom_stage - 1, rate))
    h_stages = frozenset(j for j in range(g) if j not in tears)
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
    )


def _graph_liquid_profile(
    model: _GraphModel, l0: float, vs: list[float], draw_flows: list[float]
) -> list[float]:
    """Liquid flows over the whole graph from the stage total balances.

    Main stages: the dense telescoped recursion (``_l_profile``) with the
    stripper draws subtracted like any side draw. Each section restarts the
    cascade at its draw flow (the interlink IS the section's liquid inflow) and
    telescopes over its own stages; the section's top-stage vapour leaves
    entirely (the return link), the bottom stage's liquid is the product.
    """
    col = model.col
    draw_out = {model.draw_stage_of_link[k]: draw_flows[k] for k in range(len(draw_flows))}
    out: list[float] = []
    cum = 0.0
    for j in range(col.n):
        cum += model.feeds[j].total - col.draw_l[j] - col.draw_v[j] - draw_out.get(j, 0.0)
        if col.pumparounds:
            cum += model.pa_in[j] - model.pa_out[j]
        v_above = vs[j + 1] if j + 1 < col.n else 0.0
        out.append(max(l0 + cum + v_above - vs[0], _FLOW_FLOOR))
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
    return out


def _graph_stage_overall(
    model: _GraphModel,
    s: int,
    x_s: dict[str, float],
    y_s: dict[str, float],
    l_flow: float,
    v_flow: float,
) -> dict[str, float]:
    """Stage overall composition (the `_stage_overall_from_flows` algebra, graph-aware).

    Same four sources in the same order - the stage's own liquid and vapour and
    the flashed feed parts - with the stage's main-column side draws subtracted
    from the total (a stripper draw is cascade liquid, already excluded here).
    """
    col = model.col
    part = model.feeds[s]
    total = l_flow + v_flow + part.total - (col.draw_l[s] + col.draw_v[s] if s < col.n else 0.0)
    if total <= _FLOW_FLOOR:
        return col.feed_comp
    acc: dict[str, float] = {}
    for src_comp, src_flow in (
        (x_s, l_flow),
        (y_s, v_flow),
        (part.x, part.l_flow),
        (part.y, part.v_flow),
    ):
        for cid, frac in src_comp.items():
            acc[cid] = acc.get(cid, 0.0) + frac * src_flow
    return {cid: v / total for cid, v in acc.items() if v > 0.0} or col.feed_comp


def _graph_stage_k(
    model: _GraphModel,
    tb: _ThermoBox,
    s: int,
    x_s: dict[str, float],
    t_s: float,
    l_flow: float,
    v_flow: float,
) -> dict[str, float] | None:
    """The stage-K evaluation for a graph stage (the `_stage_k_values` chain).

    Same candidate chain - flashed liquid x, flashed stage overall, feed
    composition - at the stage's pressure; None when none is evaluable.
    """
    col = model.col
    return tb.k_values(
        [
            _flash_ready(x_s, col.feed_comp),
            _flash_ready(_graph_stage_overall(model, s, x_s, {}, l_flow, v_flow), col.feed_comp),
            col.feed_comp,
        ],
        t_s,
        col.pressures[s],
    )


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
) -> list[float]:
    """The live MESH residual over the whole graph, interlinks included.

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
    layout = model.layout
    liquid = _graph_liquid_profile(model, l0, vs, draw_flows)
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
            k = (
                _graph_stage_k(model, tb, s, xs[s], ts[s], liquid[s], vs[s])
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
        for i, cid in enumerate(col.comps):
            inflow = 0.0
            if s == 0 and col.condenser == "total":
                inflow = l0 * y_eq[0].get(cid, 0.0)
            elif donor is not None:
                inflow = liquid[donor] * xs[donor].get(cid, 0.0)
            if link_in is not None:
                inflow = links[link_in]["to_stage"][cid]
            if vap_donor is not None:
                inflow += vs[vap_donor] * y_eq[vap_donor].get(cid, 0.0)
            if s in model.vapour_return_at:
                ret_top = model.vapour_return_at[s]
                inflow += vs[ret_top] * y_eq[ret_top].get(cid, 0.0)
            inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
            for ret_j, draw_j, pa_flow in pa_ret:
                if ret_j == s:
                    inflow += pa_flow * xs[draw_j].get(cid, 0.0)
            own_draw = draw_flows[model.draw_link_at_stage[s]] if s in model.draw_link_at_stage else 0.0
            outflow = (
                liquid[s]
                + (col.draw_l[s] if s < col.n else 0.0)
                + own_draw
                + (model.pa_out[s] if col.pumparounds else 0.0)
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
            h_in += vs[vap_donor] * tb.h_vapor(
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
        if s in model.vapour_return_at:
            ret_top = model.vapour_return_at[s]
            h_in += vs[ret_top] * tb.h_vapor(
                _flash_ready(y_eq[ret_top], col.feed_comp), ts[ret_top], col.pressures[ret_top]
            )
        h_in += part.h_flow
        if s == 0 and col.condenser == "total":
            h_in += l0 * tb.h_liquid(_flash_ready(y_eq[0], col.feed_comp), ts[0], col.pressures[0])
        h_in += model.section_duty_at.get(s, 0.0)
        if col.pumparounds:
            for ret_j, draw_j, pa_flow in pa_ret:
                if ret_j == s:
                    h_in += pa_flow * tb.h_liquid(
                        _flash_ready(xs[draw_j], col.feed_comp),
                        ts[draw_j],
                        col.pressures[draw_j],
                    )
        own_draw = draw_flows[model.draw_link_at_stage[s]] if s in model.draw_link_at_stage else 0.0
        h_out = (vs[s] + (col.draw_v[s] if s < col.n else 0.0)) * tb.h_vapor(
            _flash_ready(y_eq[s], col.feed_comp), ts[s], col.pressures[s]
        ) + (
            liquid[s]
            + (col.draw_l[s] if s < col.n else 0.0)
            + own_draw
            + (model.pa_out[s] if col.pumparounds else 0.0)
        ) * tb.h_liquid(_flash_ready(xs[s], col.feed_comp), ts[s], col.pressures[s])
        if h_evals is not None:
            h_evals[0] += 4
        if flow_mags is not None:
            flow_mags.append(h_scale)
        out.append((h_in - h_out) / h_scale)
    return out


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
    # Stripper draw flows are derived, not unknowns: each section's total
    # balance pins its draw to the returned vapour, the product rate and the
    # section feeds (the product-rate spec is exact by construction).
    draw_flows = [
        max(
            _FLOW_FLOOR,
            vs[top]
            + rate
            - sum(model.feeds[s].total for s in range(top, bottom + 1)),
        )
        for _k, top, bottom, rate in model.section_total_rows
    ]
    return xs, ts, vs, draw_flows


def _graph_apply_state(
    prof: _Profile, u: list[float], model: _GraphModel, t_bot_tear: float | None
) -> None:
    """Write a trial state back into the profile (dense `_apply_state` semantics)."""
    col = model.col
    xs, ts, vs, draw_flows = _graph_unpack(model, u, t_bot_tear)
    prof.x = [_flash_ready({cid: max(v, 0.0) for cid, v in x_s.items()}, col.feed_comp) for x_s in xs]
    prof.T = ts
    prof.V = vs
    prof.draw_flows = draw_flows
    prof.L = _graph_liquid_profile(model, prof.l0, vs, draw_flows)


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
    return_of_top = {top: ret for ret, top in model.vapour_return_at.items()}
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
        if s in model.vapour_return_at:
            nx |= block(model.vapour_return_at[s])
            nv |= block(model.vapour_return_at[s])
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
    for k in range(len(model.layout.draw_links)):
        top = model.section_top_of_link[k]
        draw_stage = model.draw_stage_of_link[k]
        for q in range(draw_stage, g):
            rows_v[top] = rows_v[top] | block(q)
    return rows_x, rows_v


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
    links = [lk for lk in col.interlinks if lk.phase == "liquid" and lk.flow_index is not None]
    prof.draw_flows = [max(_FLOW_FLOOR, prof.L[lk.from_stage]) for lk in links]


def _graph_naphtali_sandholm(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
    """Graph Naphtali-Sandholm: damped Newton over the whole stage graph.

    Same unknown packing and residual algebra as the dense fallback, extended
    over the graph with the interlink terms and the per-section draw flows.
    The Jacobian is stage-coloured (see module docstring) and the step solves
    with scipy.sparse LU. Rows gate at the same mesh tolerance as the dense
    path, then the solve polishes toward the 1e-12 target within the pass
    budget - which is what makes a linear column routed through this solver
    comparable to the dense result at 1e-10. Duties are NOT finalized here:
    whole-unit boundary accounting over the graph is step 3.
    """
    model = _graph_model(col, kettle_free=t_bot_tear is None and col.reboiler == "kettle")
    _extend_profile_to_graph(col, prof)
    layout = model.layout
    l0 = prof.l0
    # Vapour tears are NOT Newton unknowns in strategy mode - dense NS pins
    # them from the outer strategy loop. Standalone mode (no caller tear)
    # instead frees the kettle boilup in the model above. Note: a partial
    # condenser's top tear needs the same treatment in _graph_unpack - not
    # exercised until that configuration is routed here.
    m_tol = _MESH_M_TOL if col.n_tears >= 2 else _MESH_M_TOL_ZERO_ONE_TEAR
    ns_max = _NS_MAX if col.n_tears >= 2 else _NS_MAX_ZERO_ONE_TEAR

    def m_norm_of(r: list[float]) -> float:
        nc = layout.nc
        vals = []
        pos = 0
        for s in range(layout.n_graph):
            for _ in range(nc):
                vals.append(abs(r[pos]))
                pos += 1
            pos += 1
            if s in model.h_stages:
                pos += 1
        return max(vals, default=0.0)

    def h_norm_of(r: list[float]) -> float:
        nc = layout.nc
        vals = []
        pos = 0
        for s in range(layout.n_graph):
            pos += nc + 1
            if s in model.h_stages:
                vals.append(abs(r[pos]))
                pos += 1
        return max(vals, default=0.0)

    ever_converged = False
    # Last known-good per-stage K, persisted across passes. A stage whose flash
    # fails mid-solve (section bottoms drift far from the seed first) must fall
    # back to its last REAL K: a neutral K=1.0 fallback makes the summation row
    # sum x (1 - K) identically zero, which is a zero Jacobian row - a singular
    # solve (measured: MatrixRankWarning and a stalled Newton on the
    # two-stripper case).
    k_last: list[dict[str, float] | None] = [None] * layout.n_graph
    for _pass in range(ns_max):
        prof.ns_passes += 1
        k_fallbacks: list[dict[str, float]] = []
        for s in range(layout.n_graph):
            k = _graph_stage_k(model, tb, s, prof.x[s], prof.T[s], prof.L[s], prof.V[s])
            if k is None:
                k = tb.k_estimate(_flash_ready(prof.x[s], col.feed_comp), prof.T[s], col.pressures[s])
            if k is None:
                k = k_last[s]
            k_fallbacks.append(k or {cid: 1.0 for cid in col.comps})

        u = _graph_pack(prof, model)
        k_cache: dict[tuple[tuple[tuple[str, float], ...], float, float], dict[str, float]] = {}
        k_misses = [0]
        h_evals = [0]
        k_harvest: list[dict[str, float] | None] = [None] * layout.n_graph
        scales = _graph_residual_scales(model, tb, l0, u, t_bot_tear)

        def residuals(u_try: list[float]) -> list[float]:
            xs, ts, vs, draw_flows = _graph_unpack(model, u_try, t_bot_tear)
            return _graph_residual_vector(
                model,
                tb,
                l0,
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
            )

        r0 = residuals(u)
        # Persist this pass's last-evaluated real K values for later passes.
        for s in range(layout.n_graph):
            if k_harvest[s] is not None:
                k_last[s] = k_harvest[s]
        m_current = m_norm_of(r0)
        h_current = h_norm_of(r0)
        if max(m_current, h_current) < _GRAPH_POLISH_TARGET:
            break
        if max(m_current, h_current) < m_tol:
            ever_converged = True

        evals_counter = [0]
        jac_bundle = _graph_fd_jacobian(model, residuals, r0, u, evals_counter)
        if jac_bundle is None:
            prof.ns_trace.append(
                f"pass {prof.ns_passes}: M={m_current:.3e} H={h_current:.3e} | FD unavailable"
            )
            break
        jac, colour_count, n_evals = jac_bundle
        try:
            sol = scipy.sparse.linalg.spsolve(jac.tocsc(), -np.asarray(r0))
            if not np.all(np.isfinite(sol)):
                raise ColumnConvergenceError("singular graph Newton system")
        except Exception:  # noqa: BLE001 - singular sparse system ends the pass like the dense path
            prof.ns_trace.append(
                f"pass {prof.ns_passes}: M={m_current:.3e} H={h_current:.3e} | sparse LU singular"
            )
            break
        step = [float(v) for v in sol]

        # Per-pass temperature step bound (spec D's band clamp is too wide to
        # stop a bad Jacobian from shooting a section 100+ K in one accepted
        # step - measured: T drifting to 480 K on a steam-stripper bottom,
        # from which the line search never recovered). Real simulators bound
        # dT per NS pass for the same reason.
        for s in range(layout.n_graph):
            step[layout.t_base + s] = max(-_NS_MAX_DT, min(_NS_MAX_DT, step[layout.t_base + s]))

        accepted = False
        lam = 1.0
        for _try in range(_GRAPH_LINE_SEARCH_TRIES):
            svec = [lam * v for v in step]
            u_try = [u[i] + svec[i] for i in range(layout.n_unk)]
            try:
                r_try = residuals(u_try)
                trial_m = m_norm_of(r_try)
                trial_h = h_norm_of(r_try)
            except (ColumnConvergenceError, ValueError):
                lam *= 0.5
                continue
            if max(trial_m, trial_h) < max(m_current, h_current):
                _graph_apply_state(prof, u_try, model, t_bot_tear)
                accepted = True
                break
            lam *= 0.5
        if not accepted:
            lam_lm = 1.0
            for _lm in range(_NS_LM_TRIES):
                d_step = _lm_damped_step_sparse(jac, r0, lam_lm)
                if d_step is None:
                    break
                u_try = [u[i] + d_step[i] for i in range(layout.n_unk)]
                try:
                    r_try = residuals(u_try)
                    trial_m = m_norm_of(r_try)
                    trial_h = h_norm_of(r_try)
                except (ColumnConvergenceError, ValueError):
                    lam_lm *= 4.0
                    continue
                if max(trial_m, trial_h) < max(m_current, h_current):
                    _graph_apply_state(prof, u_try, model, t_bot_tear)
                    accepted = True
                    break
                lam_lm *= 4.0
        prof.ns_trace.append(
            f"pass {prof.ns_passes}: M={m_current:.3e} H={h_current:.3e} | colours={colour_count} "
            f"jac_evals={n_evals} lam={lam:.3g} accepted={accepted}"
        )
        if not accepted:
            break
    else:
        if not ever_converged:
            raise ColumnConvergenceError("graph Naphtali-Sandholm fallback did not converge within budget")

    # Final acceptance at the mesh gate on the graph's own rows.
    u = _graph_pack(prof, model)
    scales = _graph_residual_scales(model, tb, l0, u, t_bot_tear)
    xs, ts, vs, draw_flows = _graph_unpack(model, u, t_bot_tear)
    r_final = _graph_residual_vector(
        model, tb, l0, xs, ts, vs, draw_flows, scales=scales
    )
    m_final = m_norm_of(r_final)
    h_final = h_norm_of(r_final)
    prof.ns_used = True
    if m_final > m_tol or h_final > _MESH_H_TOL:
        raise ColumnConvergenceError(
            f"graph Naphtali-Sandholm stalled: max residuals M={m_final:.2e}, H={h_final:.2e}"
            + (f" | {'; '.join(prof.ns_trace)}" if prof.ns_trace else "")
        )
    return prof
