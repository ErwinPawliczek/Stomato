"""Refining unit adapter tests (spec U-H1): ports, splits, balances, refusals."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.units.refining._cuts import RefiningSpecError, cut_fractions
from ngdesign.units.refining.slate import assay_slate, register_slate
from tests.conftest import flash_feed

ASSAY_ID = "bagajewicz_ji_2001_light"


def _slate() -> dict[str, float]:
    register_slate(ASSAY_ID)
    _, mole = assay_slate(ASSAY_ID)
    return dict(mole)


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]):
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


# ---------------------------------------------------------------- cut fractions


def test_cut_fractions_sum_to_one_inside_and_outside_bands() -> None:
    cuts = [500.0, 600.0]
    for nbp in (450.0, 499.0, 500.0, 530.0, 550.0, 610.0, 700.0):
        fractions = cut_fractions(nbp, cuts, 10.0)
        assert math.isclose(sum(fractions), 1.0, abs_tol=1e-12), nbp
        assert len(fractions) == 3


def test_cut_fractions_reject_overlapping_bands() -> None:
    with pytest.raises(RefiningSpecError, match="overlap"):
        cut_fractions(500.0, [500.0, 510.0], 10.0)


def test_cut_fractions_reject_negative_overlap() -> None:
    with pytest.raises(RefiningSpecError, match="overlap_K"):
        cut_fractions(500.0, [500.0], -1.0)


# ----------------------------------------------------------------- assay feeder


def test_assay_feeder_returns_the_slate(thermo: Thermo) -> None:
    unit = registry.create("unit", "assay_feeder")
    feeds, params = unit.example_case()
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    (outlet,) = result.outlets.values()
    assert math.isclose(outlet.molar_flow, 1000.0, rel_tol=1e-12)
    for cid, x in _slate().items():
        assert math.isclose(outlet.composition[cid], x, abs_tol=1e-12)
    assert result.info["api_gravity"] > 0.0
    assert result.info["volume_m3_s"] > 0.0
    assert math.isclose(
        result.info["light_ends_vol_pct"] + result.info["pseudos_vol_pct"],
        100.0,
        rel_tol=1e-9,
    )


def test_assay_feeder_refuses_a_foreign_inlet_composition(thermo: Thermo) -> None:
    unit = registry.create("unit", "assay_feeder")
    feeds, params = unit.example_case()
    feeds["assay_in"]["composition"] = {**_slate(), "C6": 0.001}
    with pytest.raises(RefiningSpecError, match="keys do not match"):
        unit.solve(_inlets(thermo, feeds), params, thermo)


# --------------------------------------------------------------------- desalter


def test_desalter_splits_water_and_salt(thermo: Thermo) -> None:
    unit = registry.create("unit", "desalter")
    feeds, params = unit.example_case()
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    crude_out = result.outlets["crude_out"]
    water_out = result.outlets["water_out"]
    crude_in = flash_feed(thermo, feeds["crude_in"])
    wash_in = flash_feed(thermo, feeds["wash_in"])
    salt_in = crude_in.composition["NaCl"] * crude_in.molar_flow
    water_in = (
        crude_in.composition["H2O"] * crude_in.molar_flow
        + wash_in.composition["H2O"] * wash_in.molar_flow
    )
    assert math.isclose(
        water_out.composition["H2O"] * water_out.molar_flow,
        (1.0 - params["water_carryover_frac"]) * water_in,
        rel_tol=1e-9,
    )
    assert math.isclose(
        water_out.composition["NaCl"] * water_out.molar_flow,
        params["salt_removal"] * salt_in,
        rel_tol=1e-9,
    )
    assert math.isclose(
        crude_out.composition["NaCl"] * crude_out.molar_flow,
        (1.0 - params["salt_removal"]) * salt_in,
        rel_tol=1e-9,
    )
    assert result.info["salt_tracked"] == 1.0
    assert math.isclose(result.info["bsw_vol_pct"], 4.0, rel_tol=0.05)


def test_desalter_refuses_out_of_range_fractions(thermo: Thermo) -> None:
    unit = registry.create("unit", "desalter")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    with pytest.raises(RefiningSpecError, match="water_carryover_frac"):
        unit.solve(inlets, {**params, "water_carryover_frac": 1.5}, thermo)
    with pytest.raises(RefiningSpecError, match="salt_removal"):
        unit.solve(inlets, {**params, "salt_removal": -0.1}, thermo)
    with pytest.raises(RefiningSpecError, match="dP"):
        unit.solve(inlets, {**params, "dP": -1.0}, thermo)


# ----------------------------------------------------------------- crude column


def test_crude_column_routes_light_ends_overhead_and_closes(thermo: Thermo) -> None:
    unit = registry.create("unit", "crude_column")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    result = unit.solve(inlets, params, thermo)
    assert set(result.outlets) == set(unit.outlet_ports)
    overhead = result.outlets["overhead"]
    bottoms = result.outlets["bottoms"]
    assert overhead.composition.get("C1", 0.0) > 0.0
    assert overhead.composition.get("H2O", 0.0) > 0.0
    # Every non-overhead product carries no light ends and no water.
    light = {"C1", "C2", "C3", "iC4", "nC4", "H2O"}
    for port, state in result.outlets.items():
        if port == "overhead":
            continue
        assert not (set(state.composition) & light), port
    # Molar inventory closes.
    flow_in = inlets["crude_in"].molar_flow
    flow_out = sum(s.molar_flow for s in result.outlets.values())
    assert math.isclose(flow_out, flow_in, rel_tol=1e-9)
    # The heaviest pseudo reports to the bottoms.
    heaviest = max(_slate(), key=lambda cid: component_record(cid)["Tb"])
    assert bottoms.composition.get(heaviest, 0.0) > 0.0
    # Product reference volumes are reported.
    for port in unit.outlet_ports:
        assert f"{port}_vol_pct" in result.info
        assert f"{port}_vol_m3_s" in result.info


def test_crude_column_refuses_wrong_cut_count(thermo: Thermo) -> None:
    unit = registry.create("unit", "crude_column")
    feeds, params = unit.example_case()
    with pytest.raises(RefiningSpecError, match="cut_points_K"):
        unit.solve(_inlets(thermo, feeds), {**params, "cut_points_K": [500.0]}, thermo)


def test_crude_column_refuses_non_ascending_cuts(thermo: Thermo) -> None:
    unit = registry.create("unit", "crude_column")
    feeds, params = unit.example_case()
    with pytest.raises(RefiningSpecError, match="ascending"):
        unit.solve(
            _inlets(thermo, feeds),
            {**params, "cut_points_K": [700.0, 500.0, 600.0, 650.0]},
            thermo,
        )


def test_crude_column_overlap_shifts_material_to_the_lighter_cut(thermo: Thermo) -> None:
    unit = registry.create("unit", "crude_column")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    sharp = unit.solve(inlets, params, thermo)
    overlap = unit.solve(inlets, {**params, "overlap_K": 15.0}, thermo)
    total_sharp = sum(s.molar_flow for s in sharp.outlets.values())
    total_overlap = sum(s.molar_flow for s in overlap.outlets.values())
    assert math.isclose(total_sharp, total_overlap, rel_tol=1e-9)
    # With overlap, kerosene gains diesel-range material at the boundary.
    assert overlap.outlets["kero_out"].molar_flow >= sharp.outlets["kero_out"].molar_flow


# --------------------------------------------------------------- vacuum column


def test_vacuum_column_cuts_residue_into_three_products(thermo: Thermo) -> None:
    unit = registry.create("unit", "vacuum_column")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    result = unit.solve(inlets, params, thermo)
    assert set(result.outlets) == {"overhead", "vgo_out", "bottoms"}
    flow_in = inlets["feed_in"].molar_flow
    flow_out = sum(s.molar_flow for s in result.outlets.values())
    assert math.isclose(flow_out, flow_in, rel_tol=1e-9)
    for port in ("overhead", "vgo_out", "bottoms"):
        assert result.outlets[port].molar_flow > 0.0, port


# -------------------------------------------------------------------- preflash


def test_preflash_splits_vapour_from_liquid(thermo: Thermo) -> None:
    unit = registry.create("unit", "preflash")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    result = unit.solve(inlets, params, thermo)
    vapour = result.outlets["vapor_out"]
    liquid = result.outlets["liquid_out"]
    flow_in = inlets["feed_in"].molar_flow
    assert math.isclose(vapour.molar_flow + liquid.molar_flow, flow_in, rel_tol=1e-6)
    assert 0.0 < result.info["vapor_frac"] < 1.0
    for state in (vapour, liquid):
        assert state.T == pytest.approx(params["T"])
        assert state.P == pytest.approx(params["P"])


def test_preflash_requires_a_temperature(thermo: Thermo) -> None:
    unit = registry.create("unit", "preflash")
    feeds, params = unit.example_case()
    with pytest.raises(RefiningSpecError, match="T"):
        unit.solve(_inlets(thermo, feeds), {}, thermo)


# --------------------------------------------------------------------- blender


def test_blender_pools_component_flows(thermo: Thermo) -> None:
    unit = registry.create("unit", "blending")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    result = unit.solve(inlets, params, thermo)
    blend = result.outlets["blend_out"]
    total_in = sum(s.molar_flow for s in inlets.values())
    assert math.isclose(blend.molar_flow, total_in, rel_tol=1e-9)
    # Composition is the flow-weighted pool (all example inlets share it).
    for cid, x in _slate().items():
        assert blend.composition[cid] == pytest.approx(x, abs=1e-12)
    # Volume shares of the ports sum to 100 %.
    share = sum(v for k, v in result.info.items() if k.endswith("_vol_pct"))
    assert math.isclose(share, 100.0, rel_tol=1e-6)


def test_blender_refuses_an_undeclared_port(thermo: Thermo) -> None:
    unit = registry.create("unit", "blending")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    inlets["surprise_in"] = inlets["component_in_1"]
    with pytest.raises(RefiningSpecError, match="not a declared blender inlet"):
        unit.solve(inlets, params, thermo)


# ------------------------------------------------------------------- catalogue


def test_refining_rows_register_their_adapters() -> None:
    for unit_id in (
        "assay_feeder",
        "desalter",
        "crude_column",
        "vacuum_column",
        "preflash",
        "blending",
    ):
        unit = registry.create("unit", unit_id)
        assert unit.inlet_ports and unit.outlet_ports, unit_id
