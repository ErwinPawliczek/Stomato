"""Adapter tests: the cooling tower (spec U-C 8).

The model method: the WATER OUTLET is fixed at the inlet air's wet bulb
plus the required approach_K input, and the exit air - saturated at a
temperature solved from the overall energy balance (bisection upward from
the wet bulb) - carries the heat and the evaporation the material balance
fixes. The wet bulb itself solves the adiabatic-saturation balance
f(T) = h1 + (w2 - w1)*hw - h2 over dry air by bisection; a saturated inlet
(f(T_dry_bulb) >= 0) returns the dry bulb immediately.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.heat.cooling_tower import wet_bulb

P = 1.01325e5


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _feeds(
    thermo: Thermo,
    water_T: float = 313.15,
    water_n: float = 555.0,
    air_n: float = 2700.0,
    y: float = 0.01726592,
    air_T: float = 299.817,
) -> dict[str, StreamState]:
    return {
        "water_in": thermo.flash_pt({"H2O": 1.0}, water_T, P, water_n),
        "air_in": thermo.flash_pt({"N2": 1.0 - y, "H2O": y}, air_T, P, air_n),
    }


def _params(approach: float = 5.0) -> dict[str, float]:
    return {"cycles_of_concentration": 3.0, "approach_K": approach}


# ---------------------------------------------------------------------------
# Wet bulb
# ---------------------------------------------------------------------------


def test_saturated_inlet_wet_bulb_is_dry_bulb() -> None:
    """A saturated inlet returns T_dry_bulb immediately (no empty bracket).

    y = 0.04 at 299.817 K pins p_H2O at 4,053 Pa, well above p_sat
    3,498.9 Pa (supersaturated): f(T_dry_bulb) >= 0, so the solver must
    return the dry bulb.
    """
    thermo = _thermo()
    air = thermo.flash_pt({"N2": 0.96, "H2O": 0.04}, 299.817, P, 600.0)
    assert wet_bulb(thermo, air) == pytest.approx(299.817, abs=0.05)


def test_wet_bulb_matches_chart_anchor() -> None:
    """50% RH at 299.817 K: the solver's 292.312 K matches the chart anchor.

    Psychrometric-chart cross-check: wet bulb about 19.2 C at 26.67 C / 50%.
    """
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), _params(), thermo)
    assert result.info["wet_bulb_K"] == pytest.approx(292.3121357841492, abs=0.02)
    assert result.info["wet_bulb_K"] < 299.817


def test_wet_bulb_ashrae_example_1_anchor() -> None:
    """ASHRAE Fundamentals 2021 SI Ch. 1 Example 1: 40 C db / 20 C twb air.

    The printed chart humidity ratio W = 6.5 g_w/kg_da pins y = 0.010343;
    the model wet bulb lands -0.16 K on the printed 293.15 K (the V2085
    assessed note carries the package-vs-LibHuAirProp cause).
    """
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    y = 0.0065 / (0.0065 + 0.621945)
    result = unit.solve(
        _feeds(thermo, air_T=313.15, y=y, air_n=1100.0),
        _params(),
        thermo,
    )
    assert result.info["wet_bulb_K"] == pytest.approx(293.15, abs=0.5)


# ---------------------------------------------------------------------------
# Model method: water outlet = wet bulb + approach_K
# ---------------------------------------------------------------------------


def test_water_outlet_is_wet_bulb_plus_approach() -> None:
    """The model identity: water_out.T == wet_bulb_K + approach_K, exactly."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), _params(6.0), thermo)
    assert result.outlets["water_out"].T == pytest.approx(result.info["wet_bulb_K"] + 6.0, rel=1e-9)
    assert result.info["approach_K"] == pytest.approx(6.0, abs=1e-12)


def test_exit_air_solves_between_wet_bulb_and_water_inlet() -> None:
    """The solved exit-air state is saturated, warmer than the wet bulb and
    colder than the water inlet, and leaves humidified."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    feeds = _feeds(thermo)
    result = unit.solve(feeds, _params(6.0), thermo)
    T_exit = result.info["exit_air_T_K"]
    assert result.info["wet_bulb_K"] < T_exit < feeds["water_in"].T
    y1 = feeds["air_in"].composition["H2O"]
    y2 = result.info["exit_air_y_H2O"]
    assert y2 == pytest.approx(result.outlets["air_out"].composition["H2O"], rel=1e-9)
    assert y2 > y1
    assert result.info["evaporation_mol_s"] > 0.0
    # Exit air is saturated at the solved temperature: p_H2O = p_sat(T_exit).
    psat = thermo.pure_psat("H2O", T_exit)
    assert psat is not None
    assert y2 * P == pytest.approx(psat, rel=1e-6)


def test_material_and_blowdown_closure() -> None:
    """Makeup = evaporation + blowdown; blowdown = E/(cycles - 1)."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), _params(), thermo)
    evap = result.info["evaporation_mol_s"]
    blowdown = result.info["blowdown_mol_s"]
    makeup = result.info["makeup_mol_s"]
    assert blowdown == pytest.approx(evap / (3.0 - 1.0), rel=1e-9)
    assert makeup == pytest.approx(evap + blowdown, rel=1e-9)
    assert result.outlets["water_out"].molar_flow == pytest.approx(555.0 - evap, rel=1e-9)


def test_energy_closure_zero_net_duty() -> None:
    """The unit closes: sum n*h in == sum n*h out (the balance pins the exit)."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    feeds = _feeds(thermo)
    result = unit.solve(feeds, _params(), thermo)
    h_in = sum(s.enthalpy * s.molar_flow for s in feeds.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    assert h_out == pytest.approx(h_in, rel=1e-9)
    assert abs(result.duty_W) <= 0.05  # closure residual: bisection to 1e-9 K


def test_exit_air_humidified_dry_air_conserved() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    feeds = _feeds(thermo)
    result = unit.solve(feeds, _params(), thermo)
    air_out = result.outlets["air_out"]
    dry_in = feeds["air_in"].molar_flow * (1.0 - 0.01726592)
    dry_out = air_out.molar_flow * (1.0 - air_out.composition["H2O"])
    assert dry_out == pytest.approx(dry_in, rel=1e-9)  # dry air passes through
    assert air_out.composition["H2O"] > 0.01726592  # and leaves humidified


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_approach_required_and_positive() -> None:
    """approach_K is a required input and must be > 0."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="approach_K is required"):
        unit.solve(_feeds(thermo), {"cycles_of_concentration": 3.0}, thermo)
    with pytest.raises(Exception, match="approach_K .* must be > 0"):
        unit.solve(_feeds(thermo), _params(0.0), thermo)
    with pytest.raises(Exception, match="approach_K .* must be > 0"):
        unit.solve(_feeds(thermo), _params(-1.0), thermo)


def test_approach_at_or_above_inlet_refused() -> None:
    """An approach that puts the water outlet at/above the inlet cannot cool."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    # Wet bulb about 292.3 K: an approach of 25 K puts the outlet at ~317 K,
    # above the 313.15 K water inlet.
    with pytest.raises(Exception, match="the tower cannot cool"):
        unit.solve(_feeds(thermo), _params(25.0), thermo)


def test_over_evaporation_refused() -> None:
    """A trickle of water against a torrent of hot air cannot close by evaporating."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="evaporates more water than"):
        unit.solve(
            _feeds(thermo, water_n=1.0, air_n=10_000.0, water_T=320.0, air_T=303.15, y=0.005),
            _params(2.0),
            thermo,
        )


def test_cycles_guard() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="must be >= 1"):
        unit.solve(_feeds(thermo), {"cycles_of_concentration": 0.5, "approach_K": 5.0}, thermo)
