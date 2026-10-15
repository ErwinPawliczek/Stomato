"""Turbo-expander acceptance tests: isentropic efficiency (wave-2 spec).

Oracles are computed per state point against CoolProp independently of the
compressor tests and of the plugin's own thermo chain.
"""

from __future__ import annotations

from typing import Any

import pytest
from CoolProp.CoolProp import PropsSI

from ngdesign import registry
from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo, UnitModel
from ngdesign.units.expander import Expander
from tests.conftest import flash_feed


def _solve(thermo: Thermo, feed: dict[str, Any], params: dict[str, Any]) -> UnitResult:
    unit = registry.create("unit", "expander")
    inlets = {port: flash_feed(thermo, f) for port, f in {"gas_in": feed}.items()}
    result: UnitResult = unit.solve(inlets, params, thermo)
    return result


#: Pure methane, single-phase vapor across the whole expansion range.
METHANE_FEED: dict[str, Any] = {
    "T": 300.0,
    "P": 5.0e6,
    "molar_flow": 10.0,
    "composition": {"C1": 1.0},
}


def test_plugin_satisfies_unit_protocol() -> None:
    assert "expander" in registry.available("unit")
    assert isinstance(Expander(), UnitModel)


def test_eta_one_outlet_temperature_matches_coolprop_oracle(thermo: Thermo) -> None:
    """eta = 1 must reproduce the independent CoolProp isentropic outlet T."""
    result = _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 1.0})
    s_in = PropsSI("S", "T", 300.0, "P", 5.0e6, "Methane")
    t_oracle = PropsSI("T", "P", 1.0e6, "S", s_in, "Methane")
    assert result.outlets["gas_out"].T == pytest.approx(t_oracle, rel=0.02)
    assert result.info["T_out_isentropic"] == pytest.approx(t_oracle, rel=0.02)


def test_recovered_power_matches_coolprop_oracle(thermo: Thermo) -> None:
    """eta = 1: recovered power = molar flow * molar isentropic enthalpy drop."""
    result = _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 1.0})
    molar_mass = PropsSI("M", "Methane")  # kg/mol
    h_in = PropsSI("H", "T", 300.0, "P", 5.0e6, "Methane")  # J/kg
    s_in = PropsSI("S", "T", 300.0, "P", 5.0e6, "Methane")
    h_is = PropsSI("H", "P", 1.0e6, "S", s_in, "Methane")
    oracle_w = 10.0 * molar_mass * (h_in - h_is)
    assert result.info["power_recovered_w"] == pytest.approx(oracle_w, rel=0.05)
    assert result.power_W < 0.0  # shaft power leaves the process


def test_eta_below_one_outlet_temperature_matches_coolprop_oracle(thermo: Thermo) -> None:
    """eta = 0.75: real outlet enthalpy = h_in - eta * (h_in - h_is), T from CoolProp."""
    eta = 0.75
    result = _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": eta})
    h_in = PropsSI("H", "T", 300.0, "P", 5.0e6, "Methane")
    s_in = PropsSI("S", "T", 300.0, "P", 5.0e6, "Methane")
    h_is = PropsSI("H", "P", 1.0e6, "S", s_in, "Methane")
    t_oracle = PropsSI("T", "P", 1.0e6, "H", h_in - eta * (h_in - h_is), "Methane")
    assert result.outlets["gas_out"].T == pytest.approx(t_oracle, rel=0.02)


def test_lower_eta_recovers_less_power_and_gives_warmer_outlet(thermo: Thermo) -> None:
    best = _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 0.90})
    worst = _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 0.60})
    assert worst.outlets["gas_out"].T > best.outlets["gas_out"].T
    assert worst.info["power_recovered_w"] < best.info["power_recovered_w"]


def test_liquid_outlet_phase_split(thermo: Thermo) -> None:
    """Rich gas expanded to 0.3 MPa condenses: 3-phase thermo path, split reported."""
    feed: dict[str, Any] = {
        "T": 320.0,
        "P": 8.0e6,
        "molar_flow": 10.0,
        "composition": {"C1": 0.85, "C3": 0.10, "nC5": 0.05},
    }
    result = _solve(thermo, feed, {"P_out": 0.3e6, "eta_isentropic": 0.80})
    outlet = result.outlets["gas_out"]
    assert 0.0 < outlet.vapor_fraction < 1.0
    kinds = [p.kind for p in outlet.phases]
    assert "vapor" in kinds and "hc_liquid" in kinds
    # info reports the same split it returns on the outlet state
    split_sum = sum(result.info[f"{p.kind}_mole_fraction"] for p in outlet.phases)
    assert split_sum == pytest.approx(1.0, abs=1e-9)
    assert result.info["vapor_mole_fraction"] == pytest.approx(outlet.vapor_fraction, rel=1e-9)


def test_determinism_double_run(thermo: Thermo) -> None:
    unit = registry.create("unit", "expander")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    first = unit.solve(inlets, params, thermo)
    second = unit.solve(inlets, params, thermo)
    assert first.outlets["gas_out"] == second.outlets["gas_out"]
    assert first.info == second.info
    assert first.power_W == second.power_W


def test_rejects_pressure_increase(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="expander"):
        _solve(thermo, METHANE_FEED, {"P_out": 6.0e6, "eta_isentropic": 0.8})


def test_rejects_eta_out_of_range(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="eta_isentropic"):
        _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 0.0})
    with pytest.raises(ValueError, match="eta_isentropic"):
        _solve(thermo, METHANE_FEED, {"P_out": 1.0e6, "eta_isentropic": 1.2})


def test_rejects_liquid_inlet(thermo: Thermo) -> None:
    # Rich gas below its dew point: the PR flash returns a two-phase inlet.
    feed = {"T": 240.0, "P": 8.0e6, "molar_flow": 10.0, "composition": {"C1": 0.85, "C3": 0.10, "nC5": 0.05}}
    state = flash_feed(thermo, feed)
    assert state.vapor_fraction < 0.999  # precondition: the feed really is two-phase
    with pytest.raises(ValueError, match="liquid"):
        _solve(thermo, feed, {"P_out": 0.3e6, "eta_isentropic": 0.8})
