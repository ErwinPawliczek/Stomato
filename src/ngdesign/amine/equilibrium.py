"""Equilibrium-model selection for the amine treatment units.

The absorber and regenerator read ``params["equilibrium_model"]`` and
dispatch here (wave-3 spec, PR B). ``kent_eisenberg`` stays the default --
it is the sour-gas-capable model the units were validated against (PRs
#59/#60/#65). ``enrtl`` is the opt-in electrolyte-NRTL alternative, valid
only for CO2-only service on MDEA and MEA: no citable electrolyte-NRTL
parameter set exists for H2S amine chemistry, and the module rejects DEA
(also evidence-based -- the published sets cover MDEA and MEA only).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ngdesign.amine import enrtl
from ngdesign.units.mdea_equilibrium import (
    equilibrium_loadings as _ke_loadings,
)
from ngdesign.units.mdea_equilibrium import (
    equilibrium_partial_pressures as _ke_pressures,
)

KENT_EISENBERG = "kent_eisenberg"
ENRTL = "enrtl"

_MODELS = (KENT_EISENBERG, ENRTL)


def select_model(params: Mapping[str, Any]) -> str:
    """Return the validated equilibrium-model name for a unit solve."""
    model = str(params.get("equilibrium_model", KENT_EISENBERG))
    if model not in _MODELS:
        raise ValueError(
            f"equilibrium_model={model!r} is not one of {_MODELS}; "
            f"omit the field for the default ({KENT_EISENBERG})"
        )
    return model


def equilibrium_partial_pressures(
    params: Mapping[str, Any],
    T: float,
    amine_molarity_mol_m3: float,
    co2_loading: float,
    h2s_loading: float,
    amine: str,
) -> tuple[float, float]:
    """Dispatch (p_CO2, p_H2S) in Pa to the selected equilibrium model."""
    if select_model(params) == ENRTL:
        return enrtl.equilibrium_partial_pressures(T, amine_molarity_mol_m3, co2_loading, h2s_loading, amine)
    return _ke_pressures(T, amine_molarity_mol_m3, co2_loading, h2s_loading, amine)


def equilibrium_loadings(
    params: Mapping[str, Any],
    T: float,
    amine_molarity_mol_m3: float,
    p_co2: float,
    p_h2s: float,
    amine: str,
) -> tuple[float, float]:
    """Dispatch equilibrium (CO2, H2S) loadings to the selected model."""
    if select_model(params) == ENRTL:
        return enrtl.equilibrium_loadings(T, amine_molarity_mol_m3, p_co2, p_h2s, amine)
    return _ke_loadings(T, amine_molarity_mol_m3, p_co2, p_h2s, amine)
