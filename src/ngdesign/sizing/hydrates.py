"""Hydrate-suppression screening correlations (spec S-13, expansion items 4).

Two screening-grade correlations for gas hydrate management:

1. Hammerschmidt (1934) hydrate-formation temperature from gas specific
   gravity and pressure (Hammerschmidt, "Natural Gas Hydrates", Ind. Eng.
   Chem. 26 (1934) / GPSA Engineering Data Book):

       T_hyd [degF] = 8.9 * P_psia**0.285 / (SG**0.249 - 0.28)

2. Nielsen-Bucklin (1983) suppression for methanol, in terms of the methanol
   mole fraction x_M in the aqueous liquid phase (Nyvlt et al., "Solid-Liquid
   Phase Equilibria", 2001, p. 229, citing Nielsen & Bucklin):

       dT [degC] = -72 * ln(1 - x_M),   valid for x_M <= 0.8

The correlations are screening tools for sweet natural-gas systems; they do
not model gas composition rigorously, salts, or partitioning into hydrocarbon.
USC-to-SI conversions are done inside this module and are stated constants.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.registry import register

__all__ = [
    "HammerschmidtFormation",
    "NielsenBucklinSuppression",
    "hammerschmidt_formation",
    "nielsen_bucklin_suppression",
]

_PSIA_PER_PA = 1.0 / 6894.757293168  # NIST exact definition of the pound-force psi (6894.757293168 Pa)
_F_TO_K_OFFSET_RANKINE = 459.67  # degF -> Rankine offset; exact
_DEGF_PER_C = 1.8  # exact size of the degree interval since 1954 (kelvin/degree Celsius)
_NIELSEN_BUCKLIN_C_C = 72.0  # degC-family Nielsen-Bucklin coefficient for methanol
_WATER_MOLAR_MASS = 18.015  # g/mol, mean isotopic composition (IUPAC)
_MAX_VALID_X_M = 0.8  # Nielsen-Bucklin stated validity limit


def hammerschmidt_formation(P_Pa: float, gas_specific_gravity: float) -> dict[str, float]:
    """Hydrate-formation temperature, in kelvin, from pressure and gas gravity.

    Args:
        P_Pa: Absolute pressure [Pa].
        gas_specific_gravity: Specific gravity of the gas relative to air
            (ratio of molecular weights) [dimensionless].

    Returns:
        dict with ``T_hydrate_K``.

    Raises:
        ValueError: on non-physical inputs.
    """
    if P_Pa <= 0:
        raise ValueError(f"P_Pa must be positive, got {P_Pa}")
    if gas_specific_gravity <= 0:
        raise ValueError(f"gas_specific_gravity must be positive, got {gas_specific_gravity}")

    P_psia = P_Pa * _PSIA_PER_PA
    denom = gas_specific_gravity**0.249 - 0.28
    if denom <= 0:
        raise ValueError(
            f"correlation undefined for gas_specific_gravity={gas_specific_gravity}: "
            f"SG**0.249 - 0.28 = {denom} is not positive"
        )
    T_hydrate_F = 8.9 * P_psia**0.285 / denom
    T_hydrate_K = (T_hydrate_F + _F_TO_K_OFFSET_RANKINE) / (9.0 / 5.0)
    return {"T_hydrate_K": T_hydrate_K}


def nielsen_bucklin_suppression(
    inhibitor_mass_fraction: float, inhibitor_molar_mass: float
) -> dict[str, float]:
    """Nielsen-Bucklin (methanol) suppression from inhibitor mass fraction.

    Converts the aqueous-phase mass fraction to the methanol mole fraction
    ``x_M`` used by the published equation:

        x_M = (w/M_i) / (w/M_i + (1-w)/M_w),  M_w = 18.015 g/mol

    then applies

        dT [degC] = -72 * ln(1 - x_M).

    Args:
        inhibitor_mass_fraction: Inhibitor mass fraction in the aqueous phase
            (water + inhibitor) [dimensionless, 0 < w < 1].
        inhibitor_molar_mass: Inhibitor molar mass [g/mol]; the published
            equation is calibrated for methanol (32.04 g/mol).

    Returns:
        dict with ``x_M`` and ``dT_suppression_K`` (positive, in kelvin).

    Raises:
        ValueError: on non-physical inputs or x_M outside the published
            validity limit (x_M <= 0.8).
    """
    if not 0 < inhibitor_mass_fraction < 1:
        raise ValueError(f"inhibitor_mass_fraction must be in (0, 1), got {inhibitor_mass_fraction}")
    if inhibitor_molar_mass <= 0:
        raise ValueError(f"inhibitor_molar_mass must be positive, got {inhibitor_molar_mass}")

    w_moles = inhibitor_mass_fraction / inhibitor_molar_mass
    water_moles = (1.0 - inhibitor_mass_fraction) / _WATER_MOLAR_MASS
    x_M = w_moles / (w_moles + water_moles)
    if x_M > _MAX_VALID_X_M:
        raise ValueError(
            f"aqueous methanol mole fraction x_M={x_M} exceeds the stated validity limit "
            f"x_M <= {_MAX_VALID_X_M}"
        )
    dT_C = -_NIELSEN_BUCKLIN_C_C * math.log(1.0 - x_M)
    return {"x_M": x_M, "dT_suppression_K": dT_C}


@register("correlation", "hammerschmidt_formation")
class HammerschmidtFormation:
    """Correlation plugin named ``hammerschmidt_formation``
    (matches data/golden/hammerschmidt_formation.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return hammerschmidt_formation(**inputs)


@register("correlation", "nielsen_bucklin_suppression")
class NielsenBucklinSuppression:
    """Correlation plugin named ``nielsen_bucklin_suppression``
    (matches data/golden/nielsen_bucklin_suppression.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return nielsen_bucklin_suppression(**inputs)
