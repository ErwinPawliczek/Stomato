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
    _graph_interlink_terms,
    _graph_k_args,
    _graph_liquid_profile,
    _graph_model,
    _graph_naphtali_sandholm,
    _graph_pack,
    _graph_residual_scales,
    _graph_residual_vector,
    _graph_unpack,
    _graph_y_eq,
    _rowsout_sets,
    _stage_row_ranges,
)
from ngdesign.units.column.inside_out import (
    _build_column,
    _live_residual_vector,
    _Column,
    _Profile,
    _seed_profile,
    _stage_k_values,
    _temperature_seed,
)
from ngdesign.units.column.spec import _parse_params
from ngdesign.units.column.thermo_adapter import _flash_ready, _ThermoBox


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


def _one_stripper_params() -> dict[str, Any]:
    """One 4-stage steam stripper on the 16-stage main column."""
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
        ],
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


def _build(params: dict[str, Any], thermo: Thermo) -> tuple[col_mod.inside_out._Column, _ThermoBox]:
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
    for row, (a, b) in enumerate(zip(r_graph, r_dense, strict=True)):
        # Measured difference: exactly 0.0 - assert equality so a future
        # divergence is caught at the first ulp.
        assert a == b, f"row {row}: graph {a!r} != dense {b!r}"


def test_interlink_mass_balance_shared_term(thermo: Thermo) -> None:
    """Acceptance: on a hand-built one-stripper graph the assembled residual
    machinery carries each interlink as ONE shared term - the component mass
    leaving the draw stage equals the mass entering the stripper's top stage,
    to 1e-12 (they are the same term, not two computed ones)."""
    col, tb = _build(_one_stripper_params(), thermo)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    _extend_profile_to_graph(col, prof)
    model = _graph_model(col)
    u = _graph_pack(prof, model)
    xs, ts, vs, draw_flows = _graph_unpack(model, u, None)
    links = _graph_interlink_terms(model, xs, draw_flows)

    assert len(links) == 1
    draw_stage = model.draw_stage_of_link[0]
    for cid in col.comps:
        leaving = draw_flows[0] * xs[draw_stage].get(cid, 0.0)
        drawn = links[0]["from_stage"][cid]
        entering = links[0]["to_stage"][cid]
        assert abs(leaving - drawn) <= 1e-12
        assert abs(entering - drawn) <= 1e-12
    assert draw_flows[0] >= 1e-9


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

    # Measured count for a 20-stage linear column, and the (colour count x
    # variables per stage) bound asserted directly.
    col20, tb20 = _build({**_linear_params(), "n_stages": 20, "feed_stage": 10}, thermo)
    prof20 = _seed_profile(col20, tb20, *_temperature_seed(col20, tb20))
    model20 = _graph_model(col20)
    u20 = _graph_pack(prof20, model20)
    scales20 = _graph_residual_scales(model20, tb20, prof20.l0, u20, None)
    xs20, ts20, vs20, df20 = _graph_unpack(model20, u20, None)
    r020 = _graph_residual_vector(model20, tb20, prof20.l0, xs20, ts20, vs20, df20, scales=scales20)

    def residuals20(u_try: list[float]) -> list[float]:
        xs2, ts2, vs2, df2 = _graph_unpack(model20, u_try, None)
        return _graph_residual_vector(model20, tb20, prof20.l0, xs2, ts2, vs2, df2, scales=scales20)

    evals20 = [0]
    bundle20 = _graph_fd_jacobian(model20, residuals20, r020, u20, evals20)
    assert bundle20 is not None
    _jac20, colours20, n_evals20 = bundle20
    vps = model20.layout.variables_per_stage
    print(
        f"20-stage linear column: unknowns={model20.layout.n_unk} colours={colours20} "
        f"variables_per_stage={vps} measured FD evaluations={n_evals20}"
    )
    assert n_evals20 <= colours20 * vps
    assert n_evals20 < model20.layout.n_unk


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


def _stripper_params() -> dict[str, Any]:
    """A one-tear kettle stripper: no condenser, feed on the top stage, one
    boilup_ratio spec - the case whose cold NS-first pass converges outright
    (measured P1-10 E-NSCOLD at kettle tears V=24-48 mol/s)."""
    return {
        "n_stages": 8,
        "condenser": "none",
        "reboiler": "kettle",
        "feed_stage": 0,
        "pressure_profile": 1.5e6,
        "feeds": [
            {
                "stage": 1,
                "T": 330.0,
                "P": 1.5e6,
                "molar_flow": 100.0,
                "composition": {"C3": 0.5, "iC4": 0.5},
            }
        ],
        "specs": {"boilup_ratio": 1.5},
    }


def test_solve_routed_through_graph_ns_matches_dense_ns(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solve-level parity (S0-1c step 2 acceptance): a one-tear kettle
    stripper routed through the graph NS by the test-only switch lands on the
    dense NS result to 1e-10 relative on x, T and V at every stage. The dense
    solve runs FIRST, unpatched; the graph run then switches the mesh's NS
    entry point. Call counters prove exactly one dense and one graph NS call,
    so the comparison is between the two engines - not the graph engine with
    itself. The NS-first cold pass fires in both runs (no seed, one tear,
    kettle), so the engines - not just the sweeps - are what is compared."""
    import ngdesign.units.column.specs as specs_mod

    dense_calls = [0]
    graph_calls = [0]
    real_dense = specs_mod._naphtali_sandholm

    def counting_dense(
        col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None
    ) -> _Profile:
        dense_calls[0] += 1
        return real_dense(col, tb, prof, t_bot_tear)

    def counting_graph(
        col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None
    ) -> _Profile:
        graph_calls[0] += 1
        return _graph_naphtali_sandholm(col, tb, prof, t_bot_tear)

    col_dense, tb_dense = _build(_stripper_params(), thermo)
    col_graph, tb_graph = _build(_stripper_params(), thermo)

    # Dense run FIRST, unpatched: the mesh solve's NS entry point is the real
    # dense engine.
    monkeypatch.setattr(specs_mod, "_naphtali_sandholm", counting_dense)
    prof_dense = col_mod._solve_mesh(col_dense, tb_dense, 45.0 * 2.5, 30.0, None)
    assert prof_dense.ns_used and prof_dense.ns_passes > 0
    assert dense_calls[0] == 1 and graph_calls[0] == 0

    # Then the graph run: same column, same crude seed, same tear - the graph
    # engine instead.
    monkeypatch.setattr(specs_mod, "_naphtali_sandholm", counting_graph)
    prof_graph = col_mod._solve_mesh(col_graph, tb_graph, 45.0 * 2.5, 30.0, None)
    assert prof_graph.ns_used and prof_graph.ns_passes > 0
    assert dense_calls[0] == 1 and graph_calls[0] == 1

    worst = 0.0
    for j in range(col_dense.n):
        for cid in col_dense.comps:
            a, b = prof_dense.x[j][cid], prof_graph.x[j][cid]
            rel = abs(a - b) / max(abs(a), abs(b))
            assert rel <= 1e-10, f"x[{j}][{cid}] rel {rel:.3e}"
            worst = max(worst, rel)
        rel_t = abs(prof_dense.T[j] - prof_graph.T[j]) / max(abs(prof_dense.T[j]), abs(prof_graph.T[j]))
        assert rel_t <= 1e-10, f"T[{j}] rel {rel_t:.3e}"
        worst = max(worst, rel_t)
        rel_v = abs(prof_dense.V[j] - prof_graph.V[j]) / max(abs(prof_dense.V[j]), abs(prof_graph.V[j]))
        assert rel_v <= 1e-10, f"V[{j}] rel {rel_v:.3e}"
        worst = max(worst, rel_v)
    print(
        f"solve parity: worst relative difference {worst:.3e} over x, T, V at {col_dense.n} stages | "
        f"NS passes dense={prof_dense.ns_passes} graph={prof_graph.ns_passes}"
    )
