"""Display unit sets: which unit each quantity kind is shown in at the edges.

Three sets mirror the engineering conventions a simulator is read in: pure SI,
metric engineering, and US field units. Every entry is checked against its kind's
dimension by the tests, so a typo cannot ship.
"""

from __future__ import annotations

from typing import Any

from .dimension import UomError
from .quantity import Quantity, coerce

UNIT_SETS: dict[str, dict[str, str]] = {
    "SI": {
        "temperature": "K",
        "temperature_difference": "K",
        "pressure": "Pa",
        "mass_flow": "kg/s",
        "molar_flow": "mol/s",
        "volume_flow": "m3/s",
        "molar_energy": "J/mol",
        "specific_energy": "J/kg",
        "molar_entropy": "J/(mol K)",
        "molar_heat_capacity": "J/(mol K)",
        "specific_heat_capacity": "J/(kg K)",
        "density": "kg/m3",
        "molar_volume": "m3/mol",
        "dynamic_viscosity": "Pa s",
        "kinematic_viscosity": "m2/s",
        "thermal_conductivity": "W/(m K)",
        "heat_transfer_coefficient": "W/(m2 K)",
        "surface_tension": "N/m",
        "power": "W",
        "energy": "J",
        "length": "m",
        "area": "m2",
        "volume": "m3",
        "velocity": "m/s",
        "concentration": "mol/m3",
        "reaction_rate": "mol/(m3 s)",
        "time": "s",
        "mass": "kg",
        "amount": "mol",
    },
    "METRIC": {
        "temperature": "degC",
        "temperature_difference": "delta_degC",
        "pressure": "bara",
        "mass_flow": "kg/h",
        "molar_flow": "kmol/h",
        "volume_flow": "m3/h",
        "molar_energy": "kJ/mol",
        "specific_energy": "kJ/kg",
        "molar_entropy": "J/(mol K)",
        "molar_heat_capacity": "J/(mol K)",
        "specific_heat_capacity": "kJ/(kg K)",
        "density": "kg/m3",
        "molar_volume": "L/mol",
        "dynamic_viscosity": "cP",
        "kinematic_viscosity": "cSt",
        "thermal_conductivity": "W/(m K)",
        "heat_transfer_coefficient": "W/(m2 K)",
        "surface_tension": "mN/m",
        "power": "kW",
        "energy": "MJ",
        "length": "m",
        "area": "m2",
        "volume": "m3",
        "velocity": "m/s",
        "concentration": "mol/L",
        "reaction_rate": "mol/(L s)",
        "time": "h",
        "mass": "kg",
        "amount": "kmol",
    },
    "FIELD": {
        "temperature": "degF",
        "temperature_difference": "delta_degF",
        "pressure": "psia",
        "mass_flow": "lb/h",
        "molar_flow": "lbmol/h",
        "volume_flow": "ft3/h",
        "molar_energy": "Btu/lbmol",
        "specific_energy": "Btu/lb",
        "molar_entropy": "Btu/(lbmol degR)",
        "molar_heat_capacity": "Btu/(lbmol degR)",
        "specific_heat_capacity": "Btu/(lb degR)",
        "density": "lb/ft3",
        "molar_volume": "ft3/lbmol",
        "dynamic_viscosity": "cP",
        "kinematic_viscosity": "cSt",
        "thermal_conductivity": "Btu/(h ft degR)",
        "heat_transfer_coefficient": "Btu/(h ft2 degR)",
        "surface_tension": "dyn/cm",
        "power": "hp",
        "energy": "MMBtu",
        "length": "ft",
        "area": "ft2",
        "volume": "ft3",
        "velocity": "ft/s",
        "concentration": "lbmol/ft3",
        "reaction_rate": "lbmol/(ft3 h)",
        "time": "h",
        "mass": "lb",
        "amount": "lbmol",
    },
}


def display(value: Any, kind: str, unit_set: str = "SI") -> Quantity:
    """An SI value (or Quantity) of ``kind`` shown in the chosen set's unit."""
    try:
        table = UNIT_SETS[unit_set]
    except KeyError:
        raise UomError(f"unknown unit set {unit_set!r}; known: {sorted(UNIT_SETS)}") from None
    if kind not in table:
        raise UomError(f"unit set {unit_set!r} has no display unit for {kind!r}")
    return Quantity.from_si(coerce(value, kind), kind).to(table[kind])
