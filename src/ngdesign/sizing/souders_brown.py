"""Souders-Brown gas capacity sizing (spec S-03).

Souders-Brown equation (GPSA Engineering Data Book, Sec. 7):

    v_max = K * sqrt((rho_L - rho_G) / rho_G)

Minimum vertical vessel diameter with the full cross-sectional area available
to the gas:

    D_min = sqrt(4 * Q / (pi * v_max))

SI throughout: K in m/s, densities in kg/m3, gas flow in m3/s (actual).
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.registry import register

__all__ = ["SoudersBrown", "souders_brown"]


def souders_brown(K_m_s: float, rho_liquid: float, rho_gas: float, gas_flow_m3_s: float) -> dict[str, float]:
    """Souders-Brown maximum gas velocity and minimum vertical vessel diameter.

    Args:
        K_m_s: Souders-Brown design velocity constant [m/s].
        rho_liquid: Liquid density [kg/m3].
        rho_gas: Gas density [kg/m3].
        gas_flow_m3_s: Actual volumetric gas flow [m3/s].

    Returns:
        dict with ``v_max_m_s`` and ``min_diameter_m``.

    Raises:
        ValueError: on non-physical inputs.
    """
    if K_m_s <= 0:
        raise ValueError(f"K must be positive, got {K_m_s}")
    if rho_liquid <= 0 or rho_gas <= 0:
        raise ValueError(f"densities must be positive, got rho_liquid={rho_liquid}, rho_gas={rho_gas}")
    if rho_liquid <= rho_gas:
        raise ValueError(
            f"liquid density must exceed gas density for separation, "
            f"got rho_liquid={rho_liquid} <= rho_gas={rho_gas}"
        )
    if gas_flow_m3_s < 0:
        raise ValueError(f"gas flow must be non-negative, got {gas_flow_m3_s}")

    v_max = K_m_s * math.sqrt((rho_liquid - rho_gas) / rho_gas)
    min_diameter = math.sqrt(4.0 * gas_flow_m3_s / (math.pi * v_max))
    return {"v_max_m_s": v_max, "min_diameter_m": min_diameter}


@register("correlation", "souders_brown")
class SoudersBrown:
    """Correlation plugin adapter; see :func:`souders_brown`."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return souders_brown(**inputs)
