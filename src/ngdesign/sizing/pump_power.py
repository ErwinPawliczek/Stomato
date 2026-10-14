"""Pump hydraulic and shaft power, and NPSH available (spec S-08).

Method: P_hyd = Q*dP; P_shaft = P_hyd/eta with 0 < eta <= 1.
NPSH available: (P_suction - P_vapor)/(rho*g) + z - h_f with g = 9.80665 m/s^2.
"""

from __future__ import annotations

from typing import Any

from ngdesign.registry import register

G = 9.80665


def pump_power(Q_m3_s: float, dP_Pa: float, eta: float) -> dict[str, float]:
    """Hydraulic (fluid) power and shaft (brake) power of a pump, in W.

    P_hyd = Q*dP (volumetric flow times pressure rise);
    P_shaft = P_hyd/eta with the pump efficiency eta in (0, 1].
    """
    if Q_m3_s <= 0:
        raise ValueError(f"Q_m3_s must be > 0, got {Q_m3_s!r}")
    if dP_Pa <= 0:
        raise ValueError(f"dP_Pa must be > 0, got {dP_Pa!r}")
    if not 0 < eta <= 1:
        raise ValueError(f"eta must be in (0, 1], got {eta!r}")
    hydraulic_power_W = Q_m3_s * dP_Pa
    shaft_power_W = hydraulic_power_W / eta
    return {"hydraulic_power_W": hydraulic_power_W, "shaft_power_W": shaft_power_W}


def npsh_available(
    P_suction_Pa: float, P_vapor_Pa: float, rho: float, static_head_m: float, friction_head_m: float
) -> float:
    """Net positive suction head available, in m of liquid.

    NPSHa = (P_suction - P_vapor)/(rho*g) + z - h_f, where z is the static head
    (positive when the liquid level sits above the pump) and h_f the suction-line
    friction head loss. g = 9.80665 m/s^2.
    """
    if rho <= 0:
        raise ValueError(f"rho must be > 0, got {rho!r}")
    if P_vapor_Pa < 0:
        raise ValueError(f"P_vapor_Pa must be >= 0, got {P_vapor_Pa!r}")
    if friction_head_m < 0:
        raise ValueError(f"friction_head_m must be >= 0, got {friction_head_m!r}")
    return (P_suction_Pa - P_vapor_Pa) / (rho * G) + static_head_m - friction_head_m


@register("correlation", "pump_power")
class PumpPower:
    """Correlation plugin named `pump_power` (matches data/golden/pump_power.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return pump_power(Q_m3_s=inputs["Q_m3_s"], dP_Pa=inputs["dP_Pa"], eta=inputs["eta"])
