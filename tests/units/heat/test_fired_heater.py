"""Adapter tests: the fired heater (spec U-C 7).

The fuel LHV comes from formation enthalpies with water as VAPOUR: the repo
databank gives methane 802,584 J/mol against GPSA's 802,300 J/mol
(+0.036%, a source-data difference).
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.heat.fired_heater import fuel_lhv

P = 1.01325e5


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _n2(thermo: Thermo, T: float, n: float) -> StreamState:
    return thermo.flash_pt({"N2": 1.0}, T, P, n)


# ---------------------------------------------------------------------------
# LHV arithmetic (formation enthalpies, water vapour)
# ---------------------------------------------------------------------------


def test_methane_lhv_formation_arithmetic() -> None:
    """CH4 + 2 O2 -> CO2 + 2 H2O(g): -dHf(reaction) per mol fuel.

    Hand value from the databank's gas-phase standard-state formation
    enthalpies; GPSA's 802.3 kJ/mol sits 0.036% below it.
    """
    lhv = fuel_lhv({"CH4": 1.0})
    assert lhv == pytest.approx(802_584.0, rel=1e-6)
    assert lhv == pytest.approx(802_300.0, rel=5e-4)


def test_lhv_linear_in_fuel_composition() -> None:
    """A 50/50 methane/ethane blend is the mole-fraction-weighted LHV."""
    ch4 = fuel_lhv({"CH4": 1.0})
    c2h6 = fuel_lhv({"C2H6": 1.0})
    blend = fuel_lhv({"CH4": 0.5, "C2H6": 0.5})
    assert blend == pytest.approx(0.5 * ch4 + 0.5 * c2h6, rel=1e-9)


def test_unknown_fuel_component_refused() -> None:
    with pytest.raises(Exception, match="no formation data for fuel component"):
        fuel_lhv({"UNOBTANIUM": 1.0})


# ---------------------------------------------------------------------------
# Duty / outlet-temperature solving
# ---------------------------------------------------------------------------


def test_t_out_spec_fuel_flow_arithmetic() -> None:
    """20 mol/s N2 heated 293.15 -> 573.15 K at 0.9 efficiency.

    fuel = duty / (eff * LHV); measured on this tree as 0.228171 mol/s.
    """
    thermo = _thermo()
    h_in = _n2(thermo, 293.15, 1.0).enthalpy
    unit = registry.create("unit", "fired_heater")
    result = unit.solve(
        {"inlet": _n2(thermo, 293.15, 20.0)},
        {"T_out": 573.15, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
        thermo,
    )
    expected_duty = 20.0 * (result.outlets["outlet"].enthalpy - h_in)
    assert result.outlets["outlet"].T == pytest.approx(573.15, abs=0.1)
    assert result.info["fuel_LHV_J_per_mol"] == pytest.approx(802_584.0, rel=1e-6)
    assert result.info["fuel_molar_flow"] == pytest.approx(expected_duty / (0.9 * 802_584.0), rel=1e-9)
    assert result.info["fuel_molar_flow"] == pytest.approx(0.22817102771387845, rel=1e-5)
    assert result.info["Q_fired_W"] == pytest.approx(expected_duty / 0.9, rel=1e-9)


def test_duty_spec_matches_T_out_spec() -> None:
    """The same basis spec'd via duty_W: identical fuel flow and outlet."""
    thermo = _thermo()
    h_in = _n2(thermo, 293.15, 1.0).enthalpy
    h_out = thermo.flash_pt({"N2": 1.0}, 573.15, P, 1.0).enthalpy
    duty = 20.0 * (h_out - h_in)
    unit = registry.create("unit", "fired_heater")
    result = unit.solve(
        {"inlet": _n2(thermo, 293.15, 20.0)},
        {"duty_W": duty, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
        thermo,
    )
    assert result.info["fuel_molar_flow"] == pytest.approx(duty / (0.9 * 802_584.0), rel=1e-9)
    assert result.outlets["outlet"].T == pytest.approx(573.15, abs=0.1)


def test_duty_W_is_process_absorption() -> None:
    """Unit duty_W is the process-stream absorption; Q_fired_W = duty / efficiency."""
    thermo = _thermo()
    unit = registry.create("unit", "fired_heater")
    result = unit.solve(
        {"inlet": _n2(thermo, 293.15, 20.0)},
        {"T_out": 573.15, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
        thermo,
    )
    h_in = _n2(thermo, 293.15, 1.0).enthalpy
    assert result.duty_W == pytest.approx(20.0 * (result.outlets["outlet"].enthalpy - h_in), rel=1e-12)
    assert result.info["Q_fired_W"] == pytest.approx(result.duty_W / 0.9, rel=1e-12)


# ---------------------------------------------------------------------------
# Refusals (wording locked)
# ---------------------------------------------------------------------------


def test_cooling_spec_refused_with_clear_text() -> None:
    """A spec the heater cannot satisfy (cooling) is refused with clear text."""
    thermo = _thermo()
    unit = registry.create("unit", "fired_heater")
    with pytest.raises(Exception, match="cannot be satisfied by firing"):
        unit.solve(
            {"inlet": _n2(thermo, 573.15, 20.0)},
            {"T_out": 293.15, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )
    with pytest.raises(Exception, match="cannot be satisfied by firing"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"duty_W": -1.0e5, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )


def test_efficiency_guard() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "fired_heater")
    with pytest.raises(Exception, match="must be > 0 and <= 1"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"T_out": 573.15, "efficiency": 1.1, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )
    with pytest.raises(Exception, match="must be > 0 and <= 1"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"T_out": 573.15, "efficiency": 0.0, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )


def test_spec_mutex() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "fired_heater")
    with pytest.raises(Exception, match="exactly one"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"T_out": 573.15, "duty_W": 1.0e5, "efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )
    with pytest.raises(Exception, match="specify exactly one"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"efficiency": 0.9, "fuel_composition": {"CH4": 1.0}},
            thermo,
        )


def test_missing_fuel_data_refused() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "fired_heater")
    with pytest.raises(Exception, match="no formation data for fuel component"):
        unit.solve(
            {"inlet": _n2(thermo, 293.15, 20.0)},
            {"T_out": 573.15, "efficiency": 0.9, "fuel_composition": {"UNOBTANIUM": 1.0}},
            thermo,
        )
