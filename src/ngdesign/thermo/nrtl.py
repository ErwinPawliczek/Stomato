"""NRTL thermo package (expansion spec: selectable thermodynamics). Plugin kind
"thermo", name "nrtl".

Wraps Caleb Bell's `thermo` library:
- NRTL activity-coefficient liquid phase (Renon & Prausnitz 1968, "Local
  Compositions in Thermodynamic Excess Functions for Liquid Mixtures", AIChE J.
  14(1), 135-144), binary parameters from the embedded 'ChemSep NRTL' table
  (thermo.interaction_parameters.IPDB) in the databank's "NRTL original T"
  form: tau_ij(T) = bij/T, alpha_ij = alphaij,
- Peng-Robinson vapour phase (the standard gamma/phi pairing - DWSIM ships
  NRTL the same way) with 'ChemSep PR' kijs, zero-filled where that table has
  no pair; a vapour kij of 0 is pr.py's existing convention and does not
  affect liquid non-ideality,
- FlashVLN with two NRTL liquid phases so liquid-liquid splits remain
  expressible, and a Michelsen-style stability re-test for single-phase results
  (shared helpers: ngdesign.thermo._state, spec P0-04),
- a construction-time provenance check: every component pair of a flash's
  support must carry fitted bij values in the databank. ChemSep NRTL rows
  always store bij and alphaij together, and no fitted bij is exactly 0
  (verified against thermo 0.6.1), so a bij of 0 means the pair is absent -
  the IPDB getters zero-fill it silently. Flashing such a pair would silently
  return ideal behaviour, so the flasher is never built: the check raises,
  naming the pair.

Component ids map to CAS via ngdesign.data.components() (C6+ = n-hexane per the
reference-data note). SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from functools import cache
from typing import Any

from thermo import PRMIX, CEOSGas, ChemicalConstantsPackage, FlashVL, FlashVLN, GibbsExcessLiquid
from thermo.interaction_parameters import IPDB
from thermo.nrtl import NRTL

from ngdesign.registry import register
from ngdesign.thermo import _state
from ngdesign.thermo.cubic import ThermoSurfaceMixin

_CHEMSEP_NRTL_TABLE = "ChemSep NRTL"
_CHEMSEP_PR_TABLE = "ChemSep PR"


def _require_databanked_pairs(ids: tuple[str, ...], cas_list: list[str], tau_bs: list[list[float]]) -> None:
    """Raise naming the pair unless every off-diagonal bij is a fitted, non-zero value.

    The IPDB getters replace a databank-missing pair with the table's declared
    default (bij 0, alphaij 0.3) without any signal, and alphaij's default is a
    plausible value - so bij == 0 for an ordered pair is the one reliable marker
    that the pair was never fitted. chemsep rows store bij and alphaij together,
    hence a fitted pair always has both directions of bij non-zero.
    """
    n = len(ids)
    for i in range(n):
        for j in range(i + 1, n):
            if tau_bs[i][j] == 0.0 or tau_bs[j][i] == 0.0:
                raise ValueError(
                    f"ChemSep NRTL databank has no fitted binary parameters for pair "
                    f"{ids[i]} ({cas_list[i]}) / {ids[j]} ({cas_list[j]}); refusing to "
                    "flash a zero-filled (ideal) pair matrix - select a thermo model "
                    "whose databank covers this component support"
                )


@cache
def _flasher_for(ids: tuple[str, ...]) -> Any:
    """Build (and cache) a FlashVLN flasher over exactly this sorted component set.

    Zero-fraction components are dropped by the caller before this is reached, so
    the cache key is the reduced, sorted support of the feed composition. The
    provenance check runs at flasher construction, before any flash exists, so a
    support with a databank-missing pair cannot produce a silently ideal result.
    """
    return _build_flasher_inner(ids, three_phase=True)


@cache
def _flasher_vl_for(ids: tuple[str, ...]) -> Any:
    """Build (and cache) the two-phase FlashVL saturation fast path (spec P1-01)."""
    return _build_flasher_inner(ids, three_phase=False)


def _build_flasher_inner(ids: tuple[str, ...], three_phase: bool) -> Any:
    """Build an NRTL/PR flasher over exactly this sorted component set.

    The provenance check runs at flasher construction, before any flash exists,
    so a support with a databank-missing pair cannot produce a silently ideal
    result - whichever flasher the caller asks for.
    """
    records = _state._records(ids)
    pseudos = [r.id for r in records if r.cas is None]
    if pseudos:
        raise ValueError(
            f"NRTL has no fitted binary parameters for pseudo-components {pseudos} "
            "(the ChemSep NRTL databank is keyed by CAS); refusing to flash an "
            "ideal pseudo pair matrix - register no pseudos or select an EOS model"
        )
    cas_list = [str(r.cas) for r in records]
    constants, correlations = ChemicalConstantsPackage.from_IDs(cas_list)
    tau_bs = IPDB.get_ip_asymmetric_matrix(name=_CHEMSEP_NRTL_TABLE, CASs=cas_list, ip="bij")
    alpha_cs = IPDB.get_ip_asymmetric_matrix(name=_CHEMSEP_NRTL_TABLE, CASs=cas_list, ip="alphaij")
    _require_databanked_pairs(ids, cas_list, tau_bs)

    heat_caps = correlations.HeatCapacityGases
    kijs = IPDB.get_ip_symmetric_matrix(name=_CHEMSEP_PR_TABLE, CASs=cas_list, ip="kij")
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }

    def ge_liquid() -> Any:
        """One NRTL liquid phase.

        Each liquid phase gets its own NRTL instance: the model object carries
        (T, xs) state that two evolving phases would alias.
        """
        model = NRTL(xs=[1.0 / len(ids)] * len(ids), T=298.15, tau_bs=tau_bs, alpha_cs=alpha_cs)
        return GibbsExcessLiquid(
            VaporPressures=correlations.VaporPressures,
            HeatCapacityGases=heat_caps,
            HeatCapacityLiquids=correlations.HeatCapacityLiquids,
            EnthalpyVaporizations=correlations.EnthalpyVaporizations,
            VolumeLiquids=correlations.VolumeLiquids,
            GibbsExcessModel=model,
        )

    gas = CEOSGas(PRMIX, eos_kwargs, HeatCapacityGases=heat_caps)
    if three_phase:
        return FlashVLN(constants, correlations, gas=gas, liquids=[ge_liquid(), ge_liquid()])
    return FlashVL(constants, correlations, gas=gas, liquid=ge_liquid())


@register("thermo", "nrtl")
class NrtlThermo(ThermoSurfaceMixin):
    """NRTL liquid + Peng-Robinson vapour package over the `thermo` library."""

    def __init__(self, components: tuple[str, ...] | None = None) -> None:
        """Build the plugin; `components` forces the databank provenance check eagerly.

        The registry/API path constructs with no argument, because the solver's
        component support is only known at flash time; the check then runs inside
        the cached flasher factory before that support's first flash. Either way a
        pair missing from the ChemSep NRTL databank raises before any state is
        returned - never silently as ideal.
        """
        super().__init__()
        if components:
            _flasher_for(tuple(sorted(components)))

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        return _flasher_for(ids)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        return _flasher_vl_for(ids)
