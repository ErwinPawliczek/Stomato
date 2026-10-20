"""Unit-side adapter for the amine Kent-Eisenberg equilibrium.

The chemistry lives in ``ngdesign.amine.kent_eisenberg`` (the Brent root
finder in ``ngdesign.amine.roots``): amine chemistry is a property model,
and unit operations consume it -- ``units -> amine``, never ``amine ->
units``.  This module keeps the historical import path working for the
amine units and their tests by re-exporting every name it used to define
plus ``amine_molarity``, which stays unit-side (it converts a flashed
phase composition to molarity at the unit boundary).
"""

from __future__ import annotations

from ngdesign.amine.kent_eisenberg import (
    AMINES as AMINES,
)
from ngdesign.amine.kent_eisenberg import (
    DEA_CHEMISTRY as DEA_CHEMISTRY,
)
from ngdesign.amine.kent_eisenberg import (
    MDEA_CHEMISTRY as MDEA_CHEMISTRY,
)
from ngdesign.amine.kent_eisenberg import (
    MEA_CHEMISTRY as MEA_CHEMISTRY,
)
from ngdesign.amine.kent_eisenberg import (
    AmineChemistry as AmineChemistry,
)
from ngdesign.amine.kent_eisenberg import (
    Speciation as Speciation,
)
from ngdesign.amine.kent_eisenberg import (
    _carbon_balance_at_h as _carbon_balance_at_h,
)
from ngdesign.amine.kent_eisenberg import (
    _charge_residual_ln_h as _charge_residual_ln_h,
)
from ngdesign.amine.kent_eisenberg import (
    _co2_k1 as _co2_k1,
)
from ngdesign.amine.kent_eisenberg import (
    _co2_k2 as _co2_k2,
)
from ngdesign.amine.kent_eisenberg import (
    _h2s_k3 as _h2s_k3,
)
from ngdesign.amine.kent_eisenberg import (
    _h2s_k4 as _h2s_k4,
)
from ngdesign.amine.kent_eisenberg import (
    _henry_co2 as _henry_co2,
)
from ngdesign.amine.kent_eisenberg import (
    _pressure_residual_ln_h as _pressure_residual_ln_h,
)
from ngdesign.amine.kent_eisenberg import (
    _speciate_from_loadings as _speciate_from_loadings,
)
from ngdesign.amine.kent_eisenberg import (
    _speciate_from_pressures as _speciate_from_pressures,
)
from ngdesign.amine.kent_eisenberg import (
    _water_kw as _water_kw,
)
from ngdesign.amine.kent_eisenberg import (
    equilibrium_loadings as equilibrium_loadings,
)
from ngdesign.amine.kent_eisenberg import (
    equilibrium_partial_pressures as equilibrium_partial_pressures,
)
from ngdesign.amine.roots import brent_root

# Historical private alias, kept for the existing tests.
_brent_root = brent_root

__all__ = [
    "AMINES",
    "AmineChemistry",
    "Speciation",
    "amine_molarity",
    "equilibrium_loadings",
    "equilibrium_partial_pressures",
]


def amine_molarity(x_amine: float, phase_mw_g_mol: float, phase_density_kg_m3: float) -> float:
    """Amine molarity of a liquid phase, mol/m3, from its flashed composition.

    Args:
        x_amine: amine mole fraction within the liquid phase.
        phase_mw_g_mol: mole-fraction-weighted molecular weight of the phase, g/mol.
        phase_density_kg_m3: mass density of the phase, kg/m3.
    """
    if x_amine <= 0.0:
        raise ValueError(f"no amine in the liquid phase (x_amine={x_amine}); not an amine solvent")
    if phase_density_kg_m3 <= 0.0 or phase_mw_g_mol <= 0.0:
        raise ValueError(
            f"non-positive phase density ({phase_density_kg_m3} kg/m3) or MW ({phase_mw_g_mol} g/mol)"
        )
    return x_amine * phase_density_kg_m3 / phase_mw_g_mol * 1000.0
