"""Peng-Robinson 1978 thermo package. Catalogue id "pr78" (spec T-01).

A registration of the shared CubicEOS base (spec P0-04): Peng-Robinson cubic
EOS, 1978 variant (Robinson, Peng & Ng, "Applications of the Peng-Robinson
Equation of State", GPA Research Report RR-28, 1978) via PR78MIX — the modified
alpha correlation is the usual choice for cryogenic/liquid-density-sensitive
work — with 'ChemSep PR' kijs (IPDB), the standard fitted cubic-EOS interaction
parameters used with PR78MIX as well. Flash surface and StreamState mapping live
in thermo.cubic / thermo._state. SI units: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).

Spec T-01: registered through the thermo catalogue
(data/thermo_models/cubic.yaml) as a factory — the class stays as the adapter,
there is no @register decorator here any more.
"""

from __future__ import annotations

from thermo import PR78MIX

from ngdesign.thermo.cubic import CubicEOS


class PengRobinson78Thermo(CubicEOS):
    """Peng-Robinson 1978 package over the `thermo` library (expansion spec)."""

    eos = PR78MIX
