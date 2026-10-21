"""NRTL thermo package (expansion spec: selectable thermodynamics). Plugin kind
"thermo", name "nrtl".

The T-03 generalization moved the flasher construction into the gamma-phi
adapter (ngdesign.thermo.gamma_phi, liquid="nrtl", vapour="pr"); this module
keeps the adapter alias the catalogue row and tests import. Behaviour is
unchanged from T-01:

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
- construction-time provenance checks: every component pair of a flash's
  support must carry fitted bij values in the databank, pseudo-components are
  refused (the databank is keyed by CAS), and no pair ever silently falls back
  to ideal behaviour - see the adapter's provenance checks.

Component ids map to CAS via ngdesign.data.components() (C6+ = n-hexane per the
reference-data note). SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from ngdesign.thermo.gamma_phi import GammaPhiPackage

__all__ = ["NrtlThermo"]


class NrtlThermo(GammaPhiPackage):
    """NRTL liquid + Peng-Robinson vapour package over the `thermo` library.

    Registered through the thermo catalogue (data/thermo_models/gamma_phi.yaml)
    as a factory - the catalogue row's typed options pin liquid="nrtl",
    vapour="pr" through the shared adapter.
    """

    def __init__(self, components: tuple[str, ...] | None = None) -> None:
        """Build the plugin; `components` runs the provenance checks eagerly.

        The registry/API path constructs with no argument, because the solver's
        component support is only known at flash time; the checks then run inside
        the cached flasher factory before that support's first flash. Either way a
        pair missing from the ChemSep NRTL databank raises before any state is
        returned - never silently as ideal.
        """
        super().__init__(liquid="nrtl", vapour="pr", components=components)
