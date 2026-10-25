"""Claus sulfur-recovery unit, R2 adapter (spec ``specs/backend/units/sulfur_recovery.md``).

Level R2 of catalogue row ``sulfur_recovery``: **Gibbs equilibrium per catalytic
converter** — each catalytic stage solves the full Gibbs minimum over its
species set (ideal gas at ``P``) instead of R0's single Claus extent, so S6 and
S8 (and optionally COS, CS2, CO, H2) compete in the equilibrium. The thermal
stage and the condensers stay exactly R0's.

Scope limits carried over from the spec (measured there, cited here):

- **No Gibbs furnace.** S2 — the dominant sulfur species above about 1000 K —
  has no formation enthalpy and no critical constants in the databank, so a
  Gibbs furnace without S2 would be physically wrong. The furnace keeps R0's
  burn-one-third + given-``thermal_conversion`` rule unchanged.
- **No adiabatic converters.** ``kinetics.enthalpy_with_formation`` adds
  ``formation_enthalpy(cid, T)`` on top of a package enthalpy that already
  carries the sensible heat (the U-01b energy-basis defect: SO2 at 500 K reads
  17560.6 J/mol where about 8800 is right). Converters are therefore
  **isothermal** at the given stage ``T`` and their heat release shows in the
  unit duty. Adiabatic beds are a follow-up once the basis is fixed.
- **Complete sulfur condensation** (R0's shortcut): the package S8 saturation
  pressure is unusable (``pure_psat("S8", 717.8 K)`` = 5.29e5 Pa against a
  1.013e5 Pa normal boiling point), so the condenser removes all S6 and S8.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ngdesign.data.formation import MissingFormationData, formation_enthalpy_298
from ngdesign.units._physics.gibbs import gibbs_minimum
from ngdesign.units.treating.sulfur_recovery import SulfurRecoveryError

#: Condensed sulfur species at R2: both databank sulfur allotropes join the
#: converter equilibria and are condensed completely at the condenser (R0
#: condenses S8 only).
_SULFUR_SPECIES_R2 = ("S6", "S8")

#: Extra species a converter's Gibbs set may carry (the spec's enum).
_EXTRA_SPECIES = frozenset({"COS", "CS2", "CO", "H2"})


def _converter_species(gas: Mapping[str, float], extra_species: Sequence[str]) -> list[str]:
    """Species set of one converter's Gibbs minimum: every gas component with a
    positive flow (inerts included -- N2 and CO2 ride as ordinary species; see
    the module docstring for why ``inerts`` stays empty), plus the condensed
    sulfur allotropes S6 and S8, plus the requested extras, sorted."""
    species = {cid for cid, n in gas.items() if n > 0.0}
    species |= set(_SULFUR_SPECIES_R2)
    species |= set(extra_species)
    return sorted(species)


def _converter_equilibrium(
    gas: Mapping[str, float],
    T: float,
    P: float,
    species: Sequence[str],
) -> dict[str, float]:
    """Gibbs minimum of one catalytic converter, mol/s.

    Minimises G/RT over ``species`` at (T, P) subject to the element budgets
    of the incoming gas (``ngdesign.units._physics.gibbs.gibbs_minimum``;
    JANAF-basis ideal-gas standard state at 1 bar). Raises
    ``SulfurRecoveryError`` naming the species when formation data is missing,
    and lets ``GibbsError`` propagate for the caller to wrap with the stage
    number.
    """
    for cid in species:
        try:
            formation_enthalpy_298(cid)
        except MissingFormationData as exc:
            raise SulfurRecoveryError(
                f"converter species {cid!r} has no formation data in the databank: {exc}"
            ) from exc
    return gibbs_minimum(species, [], gas, T, P)
