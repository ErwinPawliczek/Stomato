"""Darcy-Weisbach line pressure drop with Colebrook friction (spec S-06).

Method: v = Q/A, Re = rho*v*D/mu; Darcy friction factor from Colebrook
(1/sqrt(f) = -2*log10(eps/(3.7*D) + 2.51/(Re*sqrt(f))), via fluids.friction.Colebrook)
for Re >= 2300, f = 64/Re for laminar Re < 2300; dP = f*(L/D)*rho*v^2/2.
"""

from __future__ import annotations

import math
from typing import Any

from fluids.friction import Colebrook

from ngdesign.registry import register

_LAMINAR_RE = 2300.0


def darcy_colebrook(
    Q_m3_s: float, D_m: float, rho: float, mu: float, roughness_m: float, L_m: float
) -> dict[str, float]:
    """Darcy-Weisbach pressure drop for incompressible single-phase flow in a pipe.

    Returns velocity (m/s), Reynolds number, Darcy friction factor and dP (Pa).
    """
    if Q_m3_s <= 0:
        raise ValueError(f"Q_m3_s must be > 0, got {Q_m3_s!r}")
    if D_m <= 0:
        raise ValueError(f"D_m must be > 0, got {D_m!r}")
    if rho <= 0:
        raise ValueError(f"rho must be > 0, got {rho!r}")
    if mu <= 0:
        raise ValueError(f"mu must be > 0, got {mu!r}")
    if roughness_m < 0:
        raise ValueError(f"roughness_m must be >= 0, got {roughness_m!r}")
    if L_m <= 0:
        raise ValueError(f"L_m must be > 0, got {L_m!r}")

    area = math.pi * D_m**2 / 4
    v = Q_m3_s / area
    Re = rho * v * D_m / mu
    if Re < _LAMINAR_RE:
        f = 64.0 / Re
    else:
        f = Colebrook(Re=Re, eD=roughness_m / D_m)
    dP = f * (L_m / D_m) * rho * v**2 / 2
    return {"velocity_m_s": v, "Re": Re, "darcy_f": f, "dP_Pa": dP}


@register("correlation", "darcy_colebrook")
class DarcyColebrook:
    """Correlation plugin named `darcy_colebrook` (matches data/golden/darcy_colebrook.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return darcy_colebrook(
            Q_m3_s=inputs["Q_m3_s"],
            D_m=inputs["D_m"],
            rho=inputs["rho"],
            mu=inputs["mu"],
            roughness_m=inputs["roughness_m"],
            L_m=inputs["L_m"],
        )
