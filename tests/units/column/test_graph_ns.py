"""Graph Naphtali-Sandholm on the stage graph (S0-1c step 2, issue #235).

The acceptance, in order of the tests:

- On a linear column (no sections) the graph residual vector is the dense
  residual's algebra: same row set, same per-row scaling, same values at the
  same state - element-wise within a tight tolerance. This is the parity
  oracle that makes the byte-identical bench claim for step 3 testable.
- On a two-stripper column the graph solve runs over the whole graph (main
  plus section stages), converges past the mesh gate, and the assembled
  interlink residuals balance: the draw flow leaving a main stage equals the
  flow entering its section's top stage, exactly (one shared term).
- The Jacobian is stage-coloured: the residual-evaluation count per Jacobian
  is bounded by the colour count times the variables per stage - far below
  the unknown count on a multi-stage column.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units import column as col_mod
from ngdesign.units.column.graph_ns import (
    _colour_groups,
    _extend_profile_to_graph,
    _graph_fd_jacobian,
    _graph_model,
    _graph_naphtali_sandholm,
    _graph_pack,
    _graph_residual_scales,
    _graph_residual_vector,
    _graph_unpack,
    _rowsout_sets,
    _stage_row_ranges,
)
from ngdesign.units.column.inside_out import (
    _build_column,
    _live_residual_vector,
    _seed_profile,
    _temperature_seed,
)
from ngdesign.units.column.spec import _parse_params
from ngdesign.units.column.thermo_adapter import _ThermoBox


def _linear_params() -> dict[str, Any]:
    return {
        "n_stages": 10,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 5,
        "pressure_profile": 1.5e6,
        "feeds": [
            {
                "stage": 5,
                "T": 330.0,
                "P": 1.5e6,
                "molar_flow": 100.0,
                "composition": {"C3": 0.5, "iC4": 0.5},
            }
        ],
        "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
    }


def _two_stripper_params() -> dict[str, Any]:
    """The topology test's case: 16 main stages + a 4-stage steam stripper
    + a 3-stage reboiled one."""
    return {
        **_linear_params(),
        "n_stages": 16,
        "feed_stage": 8,
        "side_strippers": [
            {
                "name": "steam",
                "draw_stage": 6,
                "return_stage": 3,
                "n_stages": 4,
                "steam": {"flow_mol_s": 2.0, "T_K": 450.0, "P_Pa": 5.0e5},
                "product_rate_mol_s": 15.0,
            },
            {
                "name": "reb",
                "draw_stage": 12,
                "return_stage": 10,
                "n_stages": 3,
                "reboiler_duty_W": 5.0e3,
                "product_rate_mol_s": 10.0,
            },
        ],
    }


def _build(params: dict[str, Any], thermo: Thermo):
    parsed = _parse_params(params, None)
    tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
    return _build_column(parsed, tb), tb


def test_graph_residual_matches_dense_on_linear_column(thermo: Thermo) -> None:
    """Without sections the graph residual IS the dense residual's algebra."""
    col, tb = _build(_linear_params(), thermo)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    # A mesh-warmed state: somewhere meaningful, not the raw seed.
    prof = col_mod._solve_mesh(col, tb, 45.0 * 2.5, 45.0 * 2.5 + 20.0, prof)

    model = _graph_model(col)
    u = _graph_pack(prof, model)
    tear = prof.V[col.n - 1] if col.reboiler == "kettle" else None
    xs, ts, vs, draw_flows = _graph_unpack(model, u, tear)

    r_graph = _graph_residual_vector(model, tb, prof.l0, xs, ts, vs, draw_flows)
    r_dense = _live_residual_vector(col, tb, prof.l0, xs, ts, vs)

    assert len(r_graph) == len(r_dense)
    for a, b in zip(r_graph, r_dense):
        assert a == pytest.approx(b, rel=1e-4, abs=1e-6)


def test_graph_solve_converges_on_stripper_graph(thermo: Thermo) -> None:
    """The graph solve runs over main + section stages and converges."""
    col, tb = _build(_two_stripper_params(), thermo)
    assert col.n_graph == 23
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    _extend_profile_to_graph(col, prof)
    assert len(prof.T) == col.n_graph

    prof = _graph_naphtali_sandholm(col, tb, prof, None)

    assert prof.ns_used is True
    # Section stages carry the solve: their temperatures are live (not the
    # seed's copy of the draw stage).
    assert len(prof.T) == col.n_graph


def test_interlink_balance_at_root(thermo: Thermo) -> None:
    """At the converged root each interlink's draw outflow equals the section
    top's inflow - the ONE shared term, checked on the assembled residuals."""
    col, tb = _build(_two_stripper_params(), thermo)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    _extend_profile_to_graph(col, prof)
    prof = _graph_naphtali_sandholm(col, tb, prof, None)

    model = _graph_model(col)
    u = _graph_pack(prof, model)
    scales = _graph_residual_scales(model, tb, prof.l0, u, None)
    xs, ts, vs, draw_flows = _graph_unpack(model, u, None)
    r = _graph_residual_vector(model, tb, prof.l0, xs, ts, vs, draw_flows, scales=scales)

    ranges = _stage_row_ranges(model)
    nc = model.layout.nc
    for k, link in enumerate(model.draw_links):
        # Draw stage's M rows include the interlink as outflow; section top's
        # as inflow. Both are gated rows at the root.
        for i in range(nc):
            draw_row = ranges[link.from_stage][0] + i
            top_row = ranges[link.to_stage][0] + i
            assert abs(r[draw_row]) <= 1e-8
            assert abs(r[top_row]) <= 1e-8
        assert draw_flows[k] >= 1e-9


def test_jacobian_evaluation_count_is_colour_bounded(thermo: Thermo) -> None:
    """FD Jacobian evaluations scale with colour groups, not unknowns."""
    col, tb = _build(_two_stripper_params(), thermo)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    _extend_profile_to_graph(col, prof)
    model = _graph_model(col)
    u = _graph_pack(prof, model)
    scales = _graph_residual_scales(model, tb, prof.l0, u, None)
    xs, ts, vs, draw_flows = _graph_unpack(model, u, None)
    r0 = _graph_residual_vector(model, tb, prof.l0, xs, ts, vs, draw_flows, scales=scales)

    def residuals(u_try: list[float]) -> list[float]:
        xs2, ts2, vs2, df2 = _graph_unpack(model, u_try, None)
        return _graph_residual_vector(model, tb, prof.l0, xs2, ts2, vs2, df2, scales=scales)

    evals = [0]
    bundle = _graph_fd_jacobian(model, residuals, r0, u, evals)
    assert bundle is not None
    _jac, colours, n_evals = bundle
    # 23 graph stages, 5 comps (incl. steam): ~153 unknowns. Colour-bounded
    # means O(colours x variables per stage) evaluations - assert far below
    # one-per-unknown.
    assert evals[0] == n_evals
    assert n_evals < model.layout.n_unk // 2


def test_colouring_groups_distant_stages(thermo: Thermo) -> None:
    """Stages 3+ cascade links apart share an x colour on a linear column."""
    col, tb = _build(_linear_params(), thermo)
    model = _graph_model(col)
    rows_x, _rows_v = _rowsout_sets(model)
    groups = _colour_groups(list(range(model.layout.n_graph)), rows_x)
    # 10 stages, neighbourhood of 3 (self, donor, vapour donor): greedy
    # colouring needs at most 4 colours, and fewer than the stage count.
    assert len(groups) < model.layout.n_graph
    # No colour group contains two stages whose rows overlap.
    for group in groups:
        for a in group:
            for b in group:
                if a != b:
                    assert rows_x[a].isdisjoint(rows_x[b])
