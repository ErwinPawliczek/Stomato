"""Closed-form tests for the logical-family R0 adapters (spec U-A, U-R1 item 4).

The logical units have no textbook worked example (V1 gap recorded in the
catalogue rows), so each unit gets a hand-computed result instead of a balance
check: a closed-form answer, not just conservation.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.logical.balance import Balance
from ngdesign.units.logical.component_splitter import ComponentSplitter
from ngdesign.units.logical.recycle_block import RecycleBlock
from ngdesign.units.logical.stream_calculator import StreamCalculator
from ngdesign.units.logical.stream_duplicator import StreamDuplicator
from ngdesign.units.logical.utility_stream import UtilityStream
from tests.conftest import flash_feed


def _thermo() -> Thermo:
    names = registry.available("thermo")
    thermo: Thermo = registry.create("thermo", "pr" if "pr" in names else names[0])
    return thermo


def _feed() -> dict[str, Any]:
    """100 mol/s of 60/40 methane/n-butane at 322.15 K, 7 MPa."""
    return {
        "T": 322.15,
        "P": 7.0e6,
        "molar_flow": 100.0,
        "composition": {"C1": 0.6, "nC4": 0.4},
    }


def test_component_splitter_sends_each_component_by_its_fraction() -> None:
    unit = ComponentSplitter()
    inlet = flash_feed(_thermo(), _feed())
    outlets = unit.solve({"inlet": inlet}, {"fractions": {"C1": 0.5}}, _thermo()).outlets
    top, bottom = outlets["outlet_1"], outlets["outlet_2"]
    # C1 60 mol/s -> 30/30; nC4 40 mol/s -> all bottom: top 30, bottom 70
    assert top.molar_flow == pytest.approx(30.0, abs=1e-8)
    assert bottom.molar_flow == pytest.approx(70.0, abs=1e-8)
    assert top.composition == {"C1": 1.0, "nC4": 0.0}
    assert bottom.composition["C1"] == pytest.approx(30.0 / 70.0, abs=1e-8)


def test_component_splitter_reports_the_flash_duty() -> None:
    unit = ComponentSplitter()
    inlet = flash_feed(_thermo(), _feed())
    res = unit.solve(
        {"inlet": inlet},
        {"fractions": {"C1": 0.5}, "outlet_T": {"outlet_2": 350.0}},
        _thermo(),
    )
    outlets = list(res.outlets.values())
    expected = sum(o.molar_flow * o.enthalpy for o in outlets) - inlet.molar_flow * inlet.enthalpy
    assert res.duty_W == pytest.approx(expected, rel=1e-12)
    assert res.duty_W > 0.0  # the 350 K bottom outlet carries the added enthalpy


def test_component_splitter_refuses_fractions_out_of_band() -> None:
    unit = ComponentSplitter()
    inlet = flash_feed(_thermo(), _feed())
    with pytest.raises(ValueError, match="fraction"):
        unit.solve({"inlet": inlet}, {"fractions": {"C1": 1.5}}, _thermo())
    with pytest.raises(ValueError, match="not in the feed"):
        unit.solve({"inlet": inlet}, {"fractions": {"CO2": 0.5}}, _thermo())


def test_stream_calculator_scales_and_sets() -> None:
    unit = StreamCalculator()
    inlet = flash_feed(_thermo(), _feed())
    out = unit.solve(
        {"inlet": inlet},
        {"scale": 0.5, "set": {"T": 300.0, "molar_flow": 80.0}},
        _thermo(),
    ).outlets["outlet"]
    assert out.molar_flow == pytest.approx(80.0, abs=1e-10)
    assert out.T == pytest.approx(300.0, abs=1e-8)
    assert out.P == pytest.approx(inlet.P, abs=1e-6)
    assert out.composition == {"C1": 0.6, "nC4": 0.4}


def test_stream_calculator_renormalises_composition_and_refuses_negatives() -> None:
    unit = StreamCalculator()
    inlet = flash_feed(_thermo(), _feed())
    out = unit.solve(
        {"inlet": inlet},
        {"set": {"composition": {"C1": 3.0, "nC4": 1.0}}},
        _thermo(),
    ).outlets["outlet"]
    assert out.composition == {"C1": 0.75, "nC4": 0.25}
    with pytest.raises(ValueError, match="negative"):
        unit.solve({"inlet": inlet}, {"set": {"composition": {"C1": -1.0}}}, _thermo())


def test_stream_calculator_duty_is_the_enthalpy_change() -> None:
    unit = StreamCalculator()
    inlet = flash_feed(_thermo(), _feed())
    res = unit.solve({"inlet": inlet}, {"set": {"T": 400.0}}, _thermo())
    out = res.outlets["outlet"]
    assert res.duty_W == pytest.approx(
        out.molar_flow * out.enthalpy - inlet.molar_flow * inlet.enthalpy, rel=1e-12
    )
    assert res.duty_W > 0.0


def test_stream_duplicator_copies_close_the_balance() -> None:
    unit = StreamDuplicator()
    inlet = flash_feed(_thermo(), _feed())
    res = unit.solve({"inlet": inlet}, {}, _thermo())
    copy0, copy1 = res.outlets["copy_0"], res.outlets["copy_1"]
    assert copy0.molar_flow == pytest.approx(inlet.molar_flow, abs=1e-12)
    assert copy1.molar_flow == pytest.approx(0.0, abs=1e-12)
    # reference copies share the intensive state
    assert copy1.T == pytest.approx(copy0.T, abs=1e-12)
    assert copy1.composition == pytest.approx(copy0.composition)
    total = sum(o.molar_flow for o in res.outlets.values())
    assert total == pytest.approx(inlet.molar_flow, abs=1e-8)


def test_stream_duplicator_full_flow_mirror_needs_the_explicit_flag() -> None:
    unit = StreamDuplicator()
    inlet = flash_feed(_thermo(), _feed())
    with pytest.raises(ValueError, match="allow_unbalanced"):
        unit.solve({"inlet": inlet}, {"copy_flow_scale": 1.0}, _thermo())
    res = unit.solve({"inlet": inlet}, {"copy_flow_scale": 1.0, "allow_unbalanced": True}, _thermo())
    for out in res.outlets.values():
        assert out.molar_flow == pytest.approx(inlet.molar_flow, abs=1e-12)


def test_stream_duplicator_n_copies_and_refusals() -> None:
    unit = StreamDuplicator()
    inlet = flash_feed(_thermo(), _feed())
    res = unit.solve({"inlet": inlet}, {"n_copies": 3}, _thermo())
    assert set(res.outlets) == {"copy_0", "copy_1", "copy_2"}
    with pytest.raises(ValueError, match="n_copies"):
        unit.solve({"inlet": inlet}, {"n_copies": 1}, _thermo())


def test_balance_closes_the_unknown_outlet_per_component() -> None:
    unit = Balance()
    inlet = flash_feed(_thermo(), _feed())
    # a known 30 mol/s pure-C1 outlet: the unknown is 30 C1 + 40 nC4 = 70
    known = {
        "T": 322.15,
        "P": 7.0e6,
        "molar_flow": 30.0,
        "composition": {"C1": 1.0},
    }
    out = unit.solve({"inlet": inlet}, {"known_outlets": [known], "P": 7.0e6}, _thermo()).outlets["outlet"]
    assert out.molar_flow == pytest.approx(70.0, abs=1e-8)
    assert out.composition["C1"] == pytest.approx(30.0 / 70.0, abs=1e-8)
    assert out.composition["nC4"] == pytest.approx(40.0 / 70.0, abs=1e-8)
    # energy closes across ALL streams: the unknown's enthalpy flow is whatever
    # the inlet minus the (PT-flashed) known outlets carry
    known_state = _thermo().flash_pt({"C1": 1.0}, 322.15, 7.0e6, 30.0)
    assert out.molar_flow * out.enthalpy == pytest.approx(
        inlet.molar_flow * inlet.enthalpy - known_state.molar_flow * known_state.enthalpy, rel=1e-6
    )


def test_balance_refuses_negative_component_flows_by_name() -> None:
    unit = Balance()
    inlet = flash_feed(_thermo(), _feed())
    known = {
        "T": 322.15,
        "P": 7.0e6,
        "molar_flow": 70.0,
        "composition": {"nC4": 1.0},  # only 40 mol/s of nC4 exists
    }
    with pytest.raises(ValueError, match="nC4"):
        unit.solve({"inlet": inlet}, {"known_outlets": [known]}, _thermo())


def test_recycle_block_is_an_identity() -> None:
    unit = RecycleBlock()
    inlet = flash_feed(_thermo(), _feed())
    out = unit.solve({"inlet": inlet}, {"acceleration": "wegstein", "tolerance": 1e-9}, _thermo()).outlets[
        "outlet"
    ]
    assert out == inlet


def test_utility_stream_meters_and_passes_through() -> None:
    unit = UtilityStream()
    inlet = flash_feed(_thermo(), _feed())
    res = unit.solve({"inlet": inlet}, {"kind": "steam_lp", "price": 12.5}, _thermo())
    assert res.outlets["outlet"] == inlet
    assert res.info["utility_cost_rate"] == pytest.approx(12.5)
    assert res.duty_W == 0.0 and res.power_W == 0.0


def test_utility_stream_refuses_unknown_kinds_and_missing_inlet() -> None:
    unit = UtilityStream()
    inlet = flash_feed(_thermo(), _feed())
    with pytest.raises(ValueError, match="kind"):
        unit.solve({"inlet": inlet}, {"kind": "chilled_water"}, _thermo())
    with pytest.raises(ValueError, match="inlet"):
        unit.solve({}, {"kind": "steam_lp"}, _thermo())
