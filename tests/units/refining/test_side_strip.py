"""``side_strip`` closed-form tests (spec U-H1, U-R1 conventions item 4).

No open V1 worked example exists for a steam side stripper (the Watkins
*Petroleum Refinery Distillation* side-stripper example is access-controlled;
the gap is recorded on the ``side_strip`` row notes). The checks here are
therefore closed-form: the adapter's split is recomputed independently of the
adapter from the same shared oracle physics (``kremser_fraction`` and the
thermo protocol's ``k_values``), plus the N -> large and N = 0 limits, the
steam passthrough, and typed refusals.

Constant checks (U-R1 item 4): the only constants typed in the adapter are
unit conversions — 0.45359237 kg/lb (the exact definition of the pound),
1 bbl = 42 US gal x 3.785411784e-3 m3/gal (exact), and water molar mass
0.01801528 kg/mol, checked against the data bank in
``test_steam_rate_constant_matches_the_databank``.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.data import component_record
from ngdesign.units._physics.shortcut import kremser_fraction
from ngdesign.units.refining._cuts import RefiningSpecError
from ngdesign.units.refining.slate import assay_slate, register_slate
from tests.conftest import flash_feed

ASSAY_ID = "bagajewicz_ji_2001_light"


def _slate() -> dict[str, float]:
    register_slate(ASSAY_ID)
    _, mole = assay_slate(ASSAY_ID)
    return dict(mole)


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> dict[str, StreamState]:
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _example(thermo: Thermo) -> tuple[dict[str, StreamState], dict[str, Any]]:
    unit = registry.create("unit", "side_strip")
    feeds, params = unit.example_case()
    return _inlets(thermo, feeds), params


def _combined_k_values(
    thermo: Thermo, draw: StreamState, steam: StreamState, t_out: float, p_out: float
) -> dict[str, float]:
    """K_i on the combined (draw + steam) composition at (T, P), as the adapter uses it."""
    draw_flows = {cid: x * draw.molar_flow for cid, x in draw.composition.items()}
    steam_flows = {cid: x * steam.molar_flow for cid, x in steam.composition.items()}
    total = draw.molar_flow + steam.molar_flow
    combined = {
        cid: (draw_flows.get(cid, 0.0) + steam_flows.get(cid, 0.0)) / total
        for cid in (*draw.composition, *steam.composition)
    }
    k = thermo.k_values(combined, t_out, p_out)
    assert k is not None, "the example must be two-phase at the stripper conditions"
    return k


# ------------------------------------------------------------------ closed form


def test_split_matches_an_independent_kremser_fixed_point(thermo: Thermo) -> None:
    """The adapter's outlet split, recomputed independently of the adapter:
    K from the thermo protocol on the combined feed at (T, P), the vapour-rate
    fixed point re-run here on ``kremser_fraction`` (the shared oracle), the
    steam passed through untouched."""
    unit = registry.create("unit", "side_strip")
    inlets, params = _example(thermo)
    result = unit.solve(inlets, params, thermo)
    draw, steam = inlets["draw_in"], inlets["steam_in"]
    draw_flows = {cid: x * draw.molar_flow for cid, x in draw.composition.items()}
    steam_flow = steam.molar_flow
    k = _combined_k_values(thermo, draw, steam, params["T"], params["P"])

    # Independent fixed point on V = steam + stripped.
    v = steam_flow
    for _ in range(200):
        stripped = {
            cid: kremser_fraction(k.get(cid, 0.0) * v / draw.molar_flow, params["N"]) for cid in draw_flows
        }
        v_next = steam_flow + sum(stripped[cid] * n for cid, n in draw_flows.items())
        if math.isclose(v_next, v, rel_tol=1e-12):
            break
        v = v_next

    overhead, bottoms = result.outlets["overhead_out"], result.outlets["bottoms_out"]
    for cid, n in draw_flows.items():
        assert overhead.composition.get(cid, 0.0) * overhead.molar_flow == pytest.approx(
            stripped[cid] * n, rel=1e-9
        ), cid
        assert bottoms.composition.get(cid, 0.0) * bottoms.molar_flow == pytest.approx(
            (1.0 - stripped[cid]) * n, rel=1e-9
        ), cid
    # All of the steam reports to the vapour return.
    assert overhead.composition.get("H2O", 0.0) * overhead.molar_flow == pytest.approx(steam_flow, rel=1e-9)
    assert bottoms.composition.get("H2O", 0.0) == pytest.approx(0.0, abs=1e-15)


def test_limit_behaviour_in_n(thermo: Thermo) -> None:
    """The analytic limits in the stage count: at large N every component with
    S_i = K_i V/L > 2 already at the steam seed is essentially fully stripped
    (the fixed point only raises V, and phi -> 1 for S > 1 as N grows), a
    non-volatile component (K = 0) cannot strip at all."""
    unit = registry.create("unit", "side_strip")
    feeds, params = unit.example_case()
    params = {**params, "N": 60.0}
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    draw, steam = flash_feed(thermo, feeds["draw_in"]), flash_feed(thermo, feeds["steam_in"])
    draw_flows = {cid: x * draw.molar_flow for cid, x in draw.composition.items()}
    k = _combined_k_values(thermo, draw, steam, params["T"], params["P"])
    overhead, bottoms = result.outlets["overhead_out"], result.outlets["bottoms_out"]
    for cid, n in draw_flows.items():
        overhead_c = overhead.composition.get(cid, 0.0) * overhead.molar_flow
        bottoms_c = bottoms.composition.get(cid, 0.0) * bottoms.molar_flow
        if k.get(cid, 0.0) * steam.molar_flow / draw.molar_flow > 2.0:
            assert overhead_c > 0.99 * n, cid
            assert bottoms_c < 0.01 * n, cid
        elif k.get(cid, 0.0) <= 0.0:
            assert overhead_c == pytest.approx(0.0, abs=1e-15), cid
            assert bottoms_c == pytest.approx(n, rel=1e-12), cid
        assert math.isclose(overhead_c + bottoms_c, n, rel_tol=1e-9), cid


def test_zero_stages_move_nothing_but_the_steam(thermo: Thermo) -> None:
    """N = 0: kremser_fraction(S, 0) = 0, so the draw leaves as bottoms and
    only the steam crosses to the vapour return."""
    unit = registry.create("unit", "side_strip")
    feeds, params = unit.example_case()
    params = {**params, "N": 0.0}
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    draw, steam = flash_feed(thermo, feeds["draw_in"]), flash_feed(thermo, feeds["steam_in"])
    overhead, bottoms = result.outlets["overhead_out"], result.outlets["bottoms_out"]
    assert bottoms.molar_flow == pytest.approx(draw.molar_flow, rel=1e-12)
    assert overhead.molar_flow == pytest.approx(steam.molar_flow, rel=1e-12)
    for cid, x in draw.composition.items():
        assert bottoms.composition[cid] == pytest.approx(x, abs=1e-15), cid
    assert result.info["stripped_mol_s"] == pytest.approx(0.0, abs=1e-15)


def test_molar_and_energy_balances_close(thermo: Thermo) -> None:
    unit = registry.create("unit", "side_strip")
    inlets, params = _example(thermo)
    result = unit.solve(inlets, params, thermo)
    flow_in = sum(s.molar_flow for s in inlets.values())
    flow_out = sum(s.molar_flow for s in result.outlets.values())
    assert math.isclose(flow_out, flow_in, rel_tol=1e-9)
    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    assert math.isclose(h_in + result.duty_W, h_out, rel_tol=1e-9, abs_tol=1e-6)
    for state in result.outlets.values():
        assert state.T == pytest.approx(params["T"])
        assert state.P == pytest.approx(params["P"])


def test_steam_rate_constant_matches_the_databank() -> None:
    """The example's lb->mol conversion uses the data-bank water molar mass,
    and the example steam rate is the Watkins (1969) 10 lb/bbl on the draw."""
    feeds, _ = registry.create("unit", "side_strip").example_case()
    steam = feeds["steam_in"]
    steam_lb_s = steam["molar_flow"] * component_record("H2O")["mw"] / 1000.0
    # Independent draw volume on the data-bank sg basis (the example draw: 500 mol/s).
    slate = feeds["draw_in"]["composition"]
    draw_volume_m3_s = 500.0 * sum(
        x * component_record(cid)["mw"] / (component_record(cid)["sg"] * 999.0) / 1000.0
        for cid, x in slate.items()
    )
    bbl = draw_volume_m3_s / (42.0 * 3.785411784e-3)
    assert steam_lb_s / bbl == pytest.approx(10.0 * 0.45359237, rel=1e-9)
    assert 0.01801528 == component_record("H2O")["mw"] / 1000.0


# --------------------------------------------------------------------- refusals


def test_refuses_missing_params_and_inlets(thermo: Thermo) -> None:
    unit = registry.create("unit", "side_strip")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    with pytest.raises(RefiningSpecError, match=r"\bT\b"):
        unit.solve(inlets, {"P": params["P"], "N": params["N"]}, thermo)
    with pytest.raises(RefiningSpecError, match=r"\bN\b"):
        unit.solve(inlets, {"T": params["T"], "N": -1.0}, thermo)
    with pytest.raises(RefiningSpecError, match=r"\bP\b"):
        unit.solve(inlets, {**params, "P": -1.0}, thermo)
    with pytest.raises(RefiningSpecError, match="draw_in"):
        unit.solve({"steam_in": inlets["steam_in"]}, params, thermo)
    with pytest.raises(RefiningSpecError, match="steam_in"):
        unit.solve({"draw_in": inlets["draw_in"]}, params, thermo)


def test_refuses_a_single_phase_stripper_state(thermo: Thermo) -> None:
    """No two-phase state at the stripper (T, P) means no equilibrium K-values:
    refuse with the condition named, never clamp."""
    unit = registry.create("unit", "side_strip")
    feeds, _ = unit.example_case()
    # A subcooled heavy draw with a whisper of steam stays single phase.
    feeds["draw_in"] = {"T": 300.0, "P": 1.0e5, "molar_flow": 100.0, "composition": _slate()}
    feeds["steam_in"] = {"T": 300.0, "P": 1.0e5, "molar_flow": 0.001, "composition": {"H2O": 1.0}}
    inlets = _inlets(thermo, feeds)
    with pytest.raises(RefiningSpecError, match="single phase"):
        unit.solve(inlets, {"T": 300.0, "P": 1.0e5, "N": 5.0}, thermo)


# ------------------------------------------------------------------- catalogue


def test_side_strip_row_registers_its_adapter() -> None:
    unit = registry.create("unit", "side_strip")
    assert unit.inlet_ports == ("draw_in", "steam_in")
    assert unit.outlet_ports == ("overhead_out", "bottoms_out")


def test_zero_steam_strips_nothing() -> None:
    """No stripping vapour: V stays 0, every fraction is 0 (no ValueError)."""
    from ngdesign.units.refining.side_strip import _stripped_amounts

    flows = {"a": 3.0, "b": 2.0}
    stripped, phi = _stripped_amounts(flows, {"a": 2.5, "b": 0.4}, l_flow=5.0, steam_flow=0.0, n_stages=4.0)
    assert stripped == 0.0
    assert phi == {"a": 0.0, "b": 0.0}
