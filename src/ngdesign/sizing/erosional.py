"""API RP 14E erosional velocity (spec S-07).

API RP 14E erosional velocity correlation:

    v_e [ft/s] = C / sqrt(rho_m [lb/ft3])

Inputs and outputs are SI; conversions use 1 kg/m3 = 0.0624279606 lb/ft3 and
1 ft = 0.3048 m. C is the empirical constant: 100 for continuous service,
125 for intermittent service (API RP 14E, eq. 2.6).
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.registry import register

__all__ = ["ErosionalApi14e", "erosional_api14e"]

KG_M3_TO_LB_FT3 = 0.0624279606
FT_TO_M = 0.3048


def erosional_api14e(rho_mix_kg_m3: float, C: float) -> dict[str, float]:
    """API RP 14E erosional velocity.

    Args:
        rho_mix_kg_m3: Mixture density at flowing conditions [kg/m3].
        C: API 14E empirical constant (100 continuous, 125 intermittent) [dimensionless].

    Returns:
        dict with ``v_erosional_m_s``.

    Raises:
        ValueError: on non-physical inputs.
    """
    if rho_mix_kg_m3 <= 0:
        raise ValueError(f"mixture density must be positive, got {rho_mix_kg_m3}")
    if C <= 0:
        raise ValueError(f"C must be positive, got {C}")

    rho_mix_lb_ft3 = rho_mix_kg_m3 * KG_M3_TO_LB_FT3
    v_erosional_ft_s = C / math.sqrt(rho_mix_lb_ft3)
    return {"v_erosional_m_s": v_erosional_ft_s * FT_TO_M}


@register("correlation", "erosional_api14e")
class ErosionalApi14e:
    """Correlation plugin adapter; see :func:`erosional_api14e`."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return erosional_api14e(**inputs)
