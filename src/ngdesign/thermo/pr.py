"""Peng-Robinson thermo package (spec S-01). Catalogue id "pr" (spec T-01).

A registration of the shared CubicEOS base (spec P0-04): Peng-Robinson cubic EOS
(Peng & Robinson 1976, "A New Equation of State and Its Application to Binary
Mixtures", Ind. Eng. Chem. Fundam. 15(1), 59-64) via PRMIX, with 'ChemSep PR'
kijs (IPDB), 0 where the table has no pair. Flash surface, stability re-check
and StreamState mapping live in thermo.cubic / thermo._state. SI units: K, Pa,
kg/m3, Pa.s, J/mol, J/(mol K).

Spec T-01: registered through the thermo catalogue
(data/thermo_models/cubic.yaml) as a factory — the class stays as the adapter,
there is no @register decorator here any more.
"""

from __future__ import annotations

from thermo import PRMIX

from ngdesign.thermo.cubic import CubicEOS


class PengRobinsonThermo(CubicEOS):
    """Peng-Robinson package over the `thermo` library (spec S-01)."""

    eos = PRMIX
