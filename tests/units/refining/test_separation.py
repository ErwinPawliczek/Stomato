"""Refining unit adapter tests (spec U-H1): ports, splits, balances, refusals."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.data import component_record
from ngdesign.units.refining._cuts import RefiningSpecError, cut_fractions
from ngdesign.units.refining.slate import assay_slate, register_slate
from tests.conftest import flash_feed

ASSAY_ID = "bagajewicz_ji_2001_light"


def _slate() -> dict[str, float]:
    register_slate(ASSAY_ID)
    _, mole = assay_slate(ASSAY_ID)
    return dict(mole)


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> dict[str, StreamState]:
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
    # Swap one slate component for a foreign one (sum stays 1): keys mismatch.
    composition = dict(_slate())
    dropped = composition.pop(next(iter(composition)))
    composition["N2"] = dropped
    feeds["assay_in"]["composition"] = composition
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
        crude_in.composition["H2O"] * crude_in.molar_flow + wash_in.composition["H2O"] * wash_in.molar_flow
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
    # Wauquier: desalted crude carries below ~0.2 vol% water.
    assert result.info["bsw_vol_pct"] < 0.25


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
    # The assay's light ends (C2 upwards) report to the overhead; the stored
    # slate carries no C1 and no water, so assert on the light ends it has.
    assert overhead.composition.get("C2", 0.0) > 0.0
    assert overhead.composition.get("C3", 0.0) > 0.0
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


# The preflash solve is thermo-bound: the composed separator's per-phase
# re-flashes take minutes on the 48-component crude (profiled on issue #213),
# so lift the suite-wide 120 s per-test timeout here, as in
# tests/e2e/test_amine_loop.py.
@pytest.mark.timeout(600)
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
    # Composition is the flow-weighted pool of the example's three cuts.
    pooled: dict[str, float] = {}
    for stream in inlets.values():
        for cid, x in stream.composition.items():
            pooled[cid] = pooled.get(cid, 0.0) + x * stream.molar_flow
    for cid, n in pooled.items():
        assert blend.composition[cid] == pytest.approx(n / total_in, abs=1e-12)
    # Volume shares of the ports sum to 100 %.
    share = sum(v for k, v in result.info.items() if k.endswith("_vol_pct"))
    assert math.isclose(share, 100.0, rel_tol=1e-6)


def test_blender_refuses_an_undeclared_port(thermo: Thermo) -> None:
    unit = registry.create("unit", "blending")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    inlets["surprise_in"] = inlets["component_in_1"]
    with pytest.raises(RefiningSpecError, match="undeclared inlet port"):
        unit.solve(inlets, params, thermo)


# ------------------------------------------------------------------- catalogue


# Re-review on 6f1a44b, item 3: V2102/V2103/V2105/V2106 echoed their own
# inputs, echoed default params, or pinned model output, so they moved here
# from data/validation_units/refining/cases.yaml as closed-form checks
# recomputed independently of the adapters (data-bank MW/sg, the published
# example feeds, the input params). The rows carry the documented V1 gaps.
_WATER_60F_KG_M3 = 999.0  # water density at 60 degF, the slate bank's basis


def _independent_volume(composition: dict[str, float], molar_flow: float) -> float:
    """Reference liquid volume recomputed from data-bank MW/sg (slate basis)."""
    volume = 0.0
    for cid, x in composition.items():
        record = component_record(cid)
        mass_kg_s = x * molar_flow * record["mw"] / 1000.0
        volume += mass_kg_s / (record["sg"] * _WATER_60F_KG_M3)
    return volume


def test_desalter_bsw_and_salt_removal_are_the_declared_split(thermo: Thermo) -> None:
    """Former V2102: BS&W is the carryover split the params declare, salt removal
    the declared fraction — recomputed here from the outlet composition, not
    echoed from an input."""
    unit = registry.create("unit", "desalter")
    feeds, params = unit.example_case()
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    crude_out = result.outlets["crude_out"]
    # BS&W: water reference volume over the desalted-crude reference volume.
    water_vol = _independent_volume({"H2O": crude_out.composition.get("H2O", 0.0)}, crude_out.molar_flow)
    total_vol = _independent_volume(crude_out.composition, crude_out.molar_flow)
    assert result.info["bsw_vol_pct"] == pytest.approx(100.0 * water_vol / total_vol, rel=1e-9)
    # Salt removal: the declared fraction, observed on the tracked component.
    crude_in = flash_feed(thermo, feeds["crude_in"])
    wash_in = flash_feed(thermo, feeds["wash_in"])
    salt_in = crude_in.composition["NaCl"] * crude_in.molar_flow
    assert result.info["salt_removed_frac"] == pytest.approx(params["salt_removal"], abs=1e-12)
    removed = 1.0 - crude_out.composition["NaCl"] * crude_out.molar_flow / salt_in
    assert removed == pytest.approx(params["salt_removal"], rel=1e-9)
    # Water split: exactly carryover of the inlet water to the crude.
    water_in = (
        crude_in.composition["H2O"] * crude_in.molar_flow + wash_in.composition["H2O"] * wash_in.molar_flow
    )
    assert crude_out.composition["H2O"] * crude_out.molar_flow == pytest.approx(
        params["water_carryover_frac"] * water_in, rel=1e-9
    )


def test_crude_column_product_shares_recomputed_from_the_slate(thermo: Thermo) -> None:
    """Former V2103: the five product volume shares, recomputed independently of
    the adapter as a sharp-cut assignment of the slate pseudos by Tb (the
    example runs overlap_K = 0.0), volumed on data-bank MW/sg."""
    unit = registry.create("unit", "crude_column")
    feeds, params = unit.example_case()
    assert params["overlap_K"] == 0.0
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    cuts = params["cut_points_K"]
    ports = list(unit.outlet_ports)
    feed_flow = feeds["crude_in"]["molar_flow"]
    vols = {port: 0.0 for port in ports}
    for cid, x in _slate().items():
        tb = component_record(cid)["Tb"]
        index = sum(1 for cut in cuts if tb >= cut)
        vols[ports[index]] += _independent_volume({cid: x}, feed_flow)
    total = sum(vols.values())
    for port in ports:
        assert result.info[f"{port}_vol_pct"] == pytest.approx(100.0 * vols[port] / total, rel=1e-6)
    assert math.isclose(sum(result.info[f"{p}_vol_pct"] for p in ports), 100.0, rel_tol=1e-9)


@pytest.mark.timeout(600)  # thermo-bound solve; see issue #213
def test_preflash_vapor_fraction_is_the_flash_at_the_published_conditions(thermo: Thermo) -> None:
    """Former V2105: the drum runs the published conditions (Gary et al. p. 66);
    the vapour fraction must equal the thermo package's flash of the same feed
    at those conditions and the outlets must split accordingly. No open source
    prints a vapour yield for this basis (documented V1 gap on the row)."""
    unit = registry.create("unit", "preflash")
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    result = unit.solve(inlets, params, thermo)
    feed = inlets["feed_in"]
    independent = thermo.flash_pt(feed.composition, params["T"], params["P"], feed.molar_flow)
    assert result.info["vapor_frac"] == pytest.approx(independent.vapor_fraction, rel=1e-9)
    vapour = result.outlets["vapor_out"]
    liquid = result.outlets["liquid_out"]
    assert vapour.molar_flow == pytest.approx(independent.vapor_fraction * feed.molar_flow, rel=1e-6)
    assert liquid.molar_flow == pytest.approx((1.0 - independent.vapor_fraction) * feed.molar_flow, rel=1e-6)
    assert vapour.P == pytest.approx(params["P"])
    assert liquid.P == pytest.approx(params["P"])


def test_blender_indices_recomputed_from_the_inputs(thermo: Thermo) -> None:
    """Former V2106: the GHK/Chevron RVP^1.25 volume index, the mass-basis sulfur
    and the volume-linear RON recomputed from the declared params and the
    data-bank reference volumes."""
    unit = registry.create("unit", "blending")
    feeds, params = unit.example_case()
    result = unit.solve(_inlets(thermo, feeds), params, thermo)
    props = params["properties"]
    volumes: dict[str, float] = {}
    masses: dict[str, float] = {}
    for port, feed in feeds.items():
        volumes[port] = _independent_volume(feed["composition"], feed["molar_flow"])
        masses[port] = sum(
            x * feed["molar_flow"] * component_record(cid)["mw"] / 1000.0
            for cid, x in feed["composition"].items()
        )
    vol_total = sum(volumes.values())
    mass_total = sum(masses.values())
    rvp_index = sum(volumes[p] * props[p]["rvp_psi"] ** 1.25 for p in volumes) / vol_total
    assert result.info["rvp_psi"] == pytest.approx(rvp_index ** (1.0 / 1.25), rel=1e-9)
    assert result.info["sulfur_wt_ppm"] == pytest.approx(
        sum(masses[p] * props[p]["sulfur_wt_ppm"] for p in masses) / mass_total, rel=1e-9
    )
    assert result.info["ron"] == pytest.approx(
        sum(volumes[p] * props[p]["ron"] for p in volumes) / vol_total, rel=1e-9
    )
    # Adiabatic: the mixer adds no heat.
    assert result.duty_W == pytest.approx(0.0, abs=1e-6)


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
