"""Amine-treatment chemistry modules (electrolyte models).

Chemistry lives in plain modules here; the registered amine unit plugins
(``mdea_absorber`` / ``mdea_regenerator``) import from it.
Ionic species never leave these modules: stream ``z`` stays molecular.

The reactive property packages (``amine_ke`` / ``amine_enrtl``) register
themselves from ``ngdesign.amine.package``; this re-export keeps that
registration deterministic whenever any amine module is imported (the layers
contract forbids thermo-side shims importing back up into this package).
"""

from ngdesign.amine.package import (
    AmineENRTLPackage,
    AmineKEPackage,
    AmineReactivePackage,
)

__all__ = [
    "AmineENRTLPackage",
    "AmineKEPackage",
    "AmineReactivePackage",
]
