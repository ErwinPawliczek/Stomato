"""Adapter tests: the cooling tower (spec U-C 8).

The wet bulb solves the adiabatic-saturation balance
f(T) = h1 + (w2 - w1)*hw - h2 over dry air by bisection; a saturated inlet
(f(T_dry_bulb) >= 0) returns the dry bulb immediately (the pre-fix scan
collapsed to an empty bracket there). The exit air is a fog-free ideal
saturated mixture, and the water outlet closes the energy balance at the
exit pin (mean water temperature).
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo

P = 1.01325e5


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _feeds(
    thermo: Thermo,
    water_T: float = 305.372,
    water_n: float = 555.0,
    air_n: float = 604.738,
    y: float = 0.01726592,
    air_T: float = 299.817,
) -> dict[str, StreamState]:
    return {
        "water_in": thermo.flash_pt({"H2O": 1.0}, water_T, P, water_n),
        "air_in": thermo.flash_pt({"N2": 1.0 - y, "H2O": y}, air_T, P, air_n),
    }


# ---------------------------------------------------------------------------
# Wet bulb
# ---------------------------------------------------------------------------


def test_saturated_inlet_wet_bulb_is_dry_bulb() -> None:
    """A saturated inlet returns T_dry_bulb immediately (no empty bracket).

    y = 0.04 at 299.817 K pins p_H2O at 4,053 Pa, well above p_sat
    3,498.9 Pa (supersaturated): f(T_dry_bulb) >= 0, so the solver must
    return the dry bulb. At y = 0.0345 (RH 99.9%) the root sits just below
    and bisects.
    """
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    saturated = {
        "water_in": thermo.flash_pt({"H2O": 1.0}, 305.372, P, 555.0),
        "air_in": thermo.flash_pt({"N2": 0.96, "H2O": 0.04}, 299.817, P, 600.0),
    }
    result = unit.solve(saturated, {"cycles_of_concentration": 3.0}, thermo)
    assert result.info["wet_bulb_K"] == pytest.approx(299.817, abs=0.05)


def test_wet_bulb_matches_chart_anchor() -> None:
    """50% RH at 299.817 K: the solver's 292.312 K matches the chart anchor.

    Psychrometric-chart cross-check: wet bulb about 19.2 C at 26.67 C / 50%.
    """
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), {"cycles_of_concentration": 3.0}, thermo)
    assert result.info["wet_bulb_K"] == pytest.approx(292.3121357841492, abs=0.02)
    assert result.info["wet_bulb_K"] < 299.817


# ---------------------------------------------------------------------------
# Water-side closure
# ---------------------------------------------------------------------------


def test_perry_water_basis_cools_to_70f() -> None:
    """Perry 8th ed. basis: 305.372 K water cools to 294.28 K (70 F)."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), {"cycles_of_concentration": 3.0}, thermo)
    assert result.outlets["water_out"].T == pytest.approx(294.28, abs=0.3)
    assert result.info["evaporation_mol_s"] == pytest.approx(10.826477185626702, rel=0.001)
    assert result.info["approach_K"] == pytest.approx(294.28 - 292.3121, abs=0.35)
    # Blowdown is taken downstream of the tower: the water outlet only loses
    # what evaporated into the air.
    assert result.outlets["water_out"].molar_flow == pytest.approx(
        555.0 - result.info["evaporation_mol_s"], rel=1e-9
    )


def test_material_and_blowdown_closure() -> None:
    """Makeup = evaporation + blowdown; blowdown = E/(cycles - 1)."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    result = unit.solve(_feeds(thermo), {"cycles_of_concentration": 3.0}, thermo)
    evap = result.info["evaporation_mol_s"]
    blowdown = result.info["blowdown_mol_s"]
    makeup = result.info["makeup_mol_s"]
    assert blowdown == pytest.approx(evap / (3.0 - 1.0), rel=1e-9)
    assert makeup == pytest.approx(evap + blowdown, rel=1e-9)
    assert result.outlets["water_out"].molar_flow == pytest.approx(555.0 - evap, rel=1e-9)


def test_energy_closure_zero_net_duty() -> None:
    """The unit closes: sum n*h in == sum n*h out (the exit pin absorbs nothing)."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    feeds = _feeds(thermo)
    result = unit.solve(feeds, {"cycles_of_concentration": 3.0}, thermo)
    h_in = sum(s.enthalpy * s.molar_flow for s in feeds.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    assert h_out == pytest.approx(h_in, rel=1e-9)
    assert abs(result.duty_W) <= 0.05  # closure residual: bisection to 1e-9 K


def test_exit_air_humidified_dry_air_conserved() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    feeds = _feeds(thermo)
    result = unit.solve(feeds, {"cycles_of_concentration": 3.0}, thermo)
    air_out = result.outlets["air_out"]
    dry_in = feeds["air_in"].molar_flow * (1.0 - 0.01726592)
    dry_out = air_out.molar_flow * (1.0 - air_out.composition["H2O"])
    assert dry_out == pytest.approx(dry_in, rel=1e-9)  # dry air passes through
    assert air_out.composition["H2O"] > 0.01726592  # and leaves humidified


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_no_capacity_refused() -> None:
    """Cold water against hot humid air has no evaporative capacity."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="no evaporative capacity"):
        unit.solve(
            _feeds(thermo, water_T=290.0, y=0.03, air_T=303.15),
            {"cycles_of_concentration": 3.0},
            thermo,
        )


def test_over_evaporation_refused() -> None:
    """A trickle of water against a torrent of hot air cannot close by evaporating."""
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="evaporates more water than"):
        unit.solve(
            _feeds(thermo, water_n=1.0, air_n=10_000.0, water_T=320.0, air_T=303.15, y=0.005),
            {"cycles_of_concentration": 3.0},
            thermo,
        )


def test_cycles_guard() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "cooling_tower")
    with pytest.raises(Exception, match="must be >= 1"):
        unit.solve(_feeds(thermo), {"cycles_of_concentration": 0.5}, thermo)
