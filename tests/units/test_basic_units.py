"""Spec S-28 acceptance tests: JT valve, mixer, splitter."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed


def _solve(thermo: Thermo, name: str, params: dict[str, Any]):
    unit = registry.create("unit", name)
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return inlets, unit.solve(inlets, params, thermo)


def test_jt_expansion_of_slice_gas_cools(thermo) -> None:
    """Spec acceptance: JT of the slice gas from 7 MPa to 3 MPa cools it."""
    _inlets, result = _solve(thermo, "jt_valve", {"P_out": 3.0e6})
    assert result.info["dT_K"] < 0
    assert result.outlets["outlet"].P == pytest.approx(3.0e6)


def test_jt_is_isenthalpic(thermo) -> None:
    inlets, result = _solve(thermo, "jt_valve", {"P_out": 3.0e6})
    assert result.outlets["outlet"].enthalpy == pytest.approx(inlets["inlet"].enthalpy, rel=1e-6)


def test_mixer_outlet_at_min_pressure_and_conserving(thermo) -> None:
    inlets, result = _solve(thermo, "mixer", {})
    outlet = result.outlets["outlet"]
    assert outlet.P == pytest.approx(min(s.P for s in inlets.values()))
    assert outlet.molar_flow == pytest.approx(sum(s.molar_flow for s in inlets.values()), rel=1e-9)
    total_in = sum(s.molar_flow for s in inlets.values())
    for cid, n in outlet.component_flows().items():
        expected = sum(s.composition[cid] * s.molar_flow for s in inlets.values())
        assert n == pytest.approx(expected, abs=1e-6 * total_in)


def test_mixer_ignores_zero_flow_port(thermo) -> None:
    """inlet_3 is zero-flow in the example case; the outlet carries only 1 + 2."""
    inlets, result = _solve(thermo, "mixer", {})
    active_flow = sum(s.molar_flow for s in inlets.values() if s.molar_flow > 0)
    assert result.outlets["outlet"].molar_flow == pytest.approx(active_flow, rel=1e-9)


def test_splitter_scales_flows_keeping_state(thermo) -> None:
    inlets, result = _solve(thermo, "splitter", {"fractions": [0.6, 0.4]})
    inlet = inlets["inlet"]
    for port, f in (("outlet_1", 0.6), ("outlet_2", 0.4)):
        out = result.outlets[port]
        assert out.molar_flow == pytest.approx(inlet.molar_flow * f, rel=1e-9)
        assert out.T == pytest.approx(inlet.T)
        assert out.P == pytest.approx(inlet.P)
        assert out.composition == inlet.composition


def test_splitter_rejects_fractions_not_summing_to_one(thermo) -> None:
    unit = registry.create("unit", "splitter")
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="sum to 1"):
        unit.solve(inlets, {"fractions": [0.5, 0.4]}, thermo)
