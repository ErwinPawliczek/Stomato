"""Peng-Robinson thermo package (spec S-01). Plugin kind "thermo", name "pr".

A registration of the shared CubicEOS base (spec P0-04): Peng-Robinson cubic EOS
(Peng & Robinson 1976, "A New Equation of State and Its Application to Binary
Mixtures", Ind. Eng. Chem. Fundam. 15(1), 59-64) via PRMIX, with 'ChemSep PR'
kijs (IPDB), 0 where the table has no pair. Flash surface, stability re-check
and StreamState mapping live in thermo.cubic / thermo._state. SI units: K, Pa,
kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

from thermo import PRMIX

from ngdesign.registry import register
from ngdesign.thermo.cubic import CubicEOS


@register("thermo", "pr")
class PengRobinsonThermo(CubicEOS):
    """Peng-Robinson package over the `thermo` library (spec S-01)."""

    eos = PRMIX
