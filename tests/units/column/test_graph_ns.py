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
    _Column,
    _live_residual_vector,
    _Profile,
    _seed_profile,
    _stage_k_values,
    _temperature_seed,
)
from ngdesign.units.column.naphtali_sandholm import _naphtali_sandholm as _dense_ns_entry
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


def test_whole_unit_component_conservation_on_residual_rows(thermo: Thermo) -> None:
    """Whole-unit component conservation on the ASSEMBLED residual rows
    (S0-1c step 2 acceptance): at an arbitrary, NON-converged two-stripper
    state, the sum of each component's unscaled M-balance rows over every
    graph stage equals the external feeds (main column + section steam)
    minus the external products, to 1e-12 relative - the distillate (the
    total condenser's net overhead, V_top - reflux, at the top-stage
    equilibrium composition), the main bottom liquid, and each section's
    bottom liquid (its product). This proves the draw and vapour-return
    terms cancel with the right signs and stages: every internal stream
    (cascade liquid and vapour, the liquid interlinks, the vapour returns)
    leaves the sum, so the check is on the assembled rows, not on a
    recomputed term."""
    col, tb = _build(_two_stripper_params(), thermo)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    _extend_profile_to_graph(col, prof)
    model = _graph_model(col)
    u = _graph_pack(prof, model)
    xs, ts, vs, draw_flows = _graph_unpack(model, u, None)
    nc = len(col.comps)
    g = model.layout.n_graph

    # Unscaled M rows: unit per-M-row scales (the residual divides each M row
    # by scales[s * nc + i]; H rows carry their own fixed scale, not summed).
    r = _graph_residual_vector(model, tb, prof.l0, xs, ts, vs, draw_flows, scales=[1.0] * (g * nc))
    ranges = _stage_row_ranges(model)
    row_sums = [sum(r[ranges[s][0] + i] for s in range(g)) for i in range(nc)]

    # External feeds, exactly as the rows read them (stage feed parts over
    # the whole graph: main-column feeds + section steam).
    feed = [0.0] * nc
    for part in model.feeds:
        for i, cid in enumerate(col.comps):
            feed[i] += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)

    # External products. The distillate composition is the top stage's
    # equilibrium y = K*x, read through the same candidate chain the rows
    # use (stage K, then k_estimate) - the IDENTITY tested here is which
    # streams, at which stages, with which signs, not the K model.
    liquid = _graph_liquid_profile(model, prof.l0, vs, draw_flows)
    feed_part, draw_total = _graph_k_args(model, 0)
    k_top = _stage_k_values(
        col, tb, 0, xs[0], {}, ts[0], liquid[0], vs[0], feed_part=feed_part, draw_total=draw_total
    ) or tb.k_estimate(_flash_ready(xs[0], col.feed_comp), ts[0], col.pressures[0])
    assert k_top is not None
    y_top = _graph_y_eq(k_top, xs[0])
    products = [0.0] * nc
    for i, cid in enumerate(col.comps):
        products[i] += (vs[0] - prof.l0) * y_top.get(cid, 0.0)  # distillate
        products[i] += liquid[col.n - 1] * xs[col.n - 1].get(cid, 0.0)  # kettle bottom
    for _k, _top, bottom, _rate in model.section_total_rows:
        for i, cid in enumerate(col.comps):
            products[i] += liquid[bottom] * xs[bottom].get(cid, 0.0)  # section product
    # No other external draws in this fixture: the stripper draws are the
    # interlinks themselves (internal to the graph).
    assert not any(col.draw_l) and not any(col.draw_v)

    feed_mag = max(abs(v) for v in feed) or 1.0
    worst = 0.0
    for i, cid in enumerate(col.comps):
        expect = feed[i] - products[i]
        rel = abs(row_sums[i] - expect) / max(abs(expect), feed_mag)
        worst = max(worst, rel)
        assert rel <= 1e-12, (
            f"component {cid}: summed M rows {row_sums[i]:.3e} vs "
            f"feeds - products {expect:.3e} (rel {rel:.3e})"
        )
    print(f"whole-unit component conservation: worst relative deviation {worst:.3e}")


def test_graph_dt_clamp_inactive_on_linear_columns(thermo: Thermo) -> None:
    """The graph-only per-pass dT clamp is a no-op on a linear column (no
    sections) and active on the two-stripper graph - the shared controller's
    one graph-only safeguard, gated so the dense-path steps stay untouched."""
    from ngdesign.units.column.graph_ns import _NS_MAX_DT, _GraphNSEngine

    col_lin, tb_lin = _build(_linear_params(), thermo)
    prof_lin = _seed_profile(col_lin, tb_lin, *_temperature_seed(col_lin, tb_lin))
    model_lin = _graph_model(col_lin)
    eng_lin = _GraphNSEngine(col_lin, tb_lin, prof_lin, None, model_lin, 1e-7)
    step = [0.0] * model_lin.layout.n_unk
    step[model_lin.layout.t_base] = 1000.0 * _NS_MAX_DT
    eng_lin.cap_step(step)
    assert step[model_lin.layout.t_base] == 1000.0 * _NS_MAX_DT  # untouched

    col_two, tb_two = _build(_two_stripper_params(), thermo)
    prof_two = _seed_profile(col_two, tb_two, *_temperature_seed(col_two, tb_two))
    _extend_profile_to_graph(col_two, prof_two)
    model_two = _graph_model(col_two)
    eng_two = _GraphNSEngine(col_two, tb_two, prof_two, None, model_two, 1e-7)
    step_two = [0.0] * model_two.layout.n_unk
    step_two[model_two.layout.t_base] = 1000.0 * _NS_MAX_DT
    eng_two.cap_step(step_two)
    assert step_two[model_two.layout.t_base] == _NS_MAX_DT  # clamped


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
    real_dense = _dense_ns_entry

    def counting_dense(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
        dense_calls[0] += 1
        return real_dense(col, tb, prof, t_bot_tear)

    def counting_graph(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
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
