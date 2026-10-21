"""Soave-Redlich-Kwong thermo package. Catalogue id "srk" (spec T-01).

A registration of the shared CubicEOS base (spec P0-04): Soave-Redlich-Kwong
cubic EOS (Soave, G., "Equilibrium Constants from a Modified Redlich-Kwong
Equation of State", Chem. Eng. Sci. 27(6), 1197-1203, 1972) via SRKMIX, with
'ChemSep PR' kijs (IPDB) — the IPDB ships no SRK-specific table; those are the
standard fitted cubic-EOS interaction parameters used with SRKMIX as well. Flash
surface and StreamState mapping live in thermo.cubic / thermo._state. SI units:
K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).

Spec T-01: registered through the thermo catalogue
(data/thermo_models/cubic.yaml) as a factory — the class stays as the adapter,
there is no @register decorator here any more.
"""

from __future__ import annotations

from thermo import SRKMIX

from ngdesign.thermo.cubic import CubicEOS


class SoaveRedlichKwongThermo(CubicEOS):
    """Soave-Redlich-Kwong package over the `thermo` library (expansion spec)."""

    eos = SRKMIX
