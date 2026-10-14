"""API 520 Part I gas relief area at critical flow (spec S-09).

Method (USC units per data/golden/psv_api520_gas.yaml):
C = 520*sqrt(k*(2/(k+1))^((k+1)/(k-1)));
A[in2] = W/(C*Kd*P1*Kb*Kc)*sqrt(T*Z/M), with P1 the relieving pressure in psia.
Source: API 520 Part I, eq. 9 (critical flow).
"""

from __future__ import annotations

import math
from typing import Any

from fluids.safety_valve import API526_A, API526_letters

from ngdesign.registry import register


def psv_api520_gas(
    W_lb_h: float,
    T_R: float,
    Z: float,
    M: float,
    k: float,
    P1_psia: float,
    Kd: float,
    Kb: float,
    Kc: float,
) -> dict[str, float]:
    """Required orifice area, in2, and the gas-flow coefficient C, for critical flow.

    W is the required relieving rate (lb/h), T the relieving temperature (R),
    Z the compressibility, M the molar mass (lb/lbmol), k the heat-capacity ratio,
    P1 the relieving pressure (psia), Kd the discharge coefficient, Kb the
    back-pressure correction and Kc the combination correction.
    """
    if W_lb_h <= 0:
        raise ValueError(f"W_lb_h must be > 0, got {W_lb_h!r}")
    if T_R <= 0:
        raise ValueError(f"T_R must be > 0, got {T_R!r}")
    if Z <= 0:
        raise ValueError(f"Z must be > 0, got {Z!r}")
    if M <= 0:
        raise ValueError(f"M must be > 0, got {M!r}")
    if k <= 1:
        raise ValueError(f"k must be > 1 for critical flow, got {k!r}")
    if P1_psia <= 0:
        raise ValueError(f"P1_psia must be > 0, got {P1_psia!r}")
    if not 0 < Kd <= 1:
        raise ValueError(f"Kd must be in (0, 1], got {Kd!r}")
    if Kb <= 0:
        raise ValueError(f"Kb must be > 0, got {Kb!r}")
    if Kc <= 0:
        raise ValueError(f"Kc must be > 0, got {Kc!r}")

    C = 520.0 * math.sqrt(k * (2.0 / (k + 1.0)) ** ((k + 1.0) / (k - 1.0)))
    area_in2 = W_lb_h / (C * Kd * P1_psia * Kb * Kc) * math.sqrt(T_R * Z / M)
    return {"C": C, "area_in2": area_in2}


def api526_orifice(area_in2: float) -> str:
    """Smallest standard API 526 letter orifice (D..T) whose area >= required.

    Areas come from fluids (`API526_A`, m^2, converted to in2) paired with
    `API526_letters`; this function never hard-codes the table.
    """
    if area_in2 <= 0:
        raise ValueError(f"area_in2 must be > 0, got {area_in2!r}")
    IN2_PER_M2 = 1.0 / (0.0254**2)
    for letter, area_m2 in zip(API526_letters, API526_A, strict=True):
        if area_m2 * IN2_PER_M2 >= area_in2:
            return letter
    raise ValueError(f"required area {area_in2!r} in2 exceeds the largest API 526 orifice (T)")


@register("correlation", "psv_api520_gas")
class PsvApi520Gas:
    """Correlation plugin named `psv_api520_gas` (matches data/golden/psv_api520_gas.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return psv_api520_gas(
            W_lb_h=inputs["W_lb_h"],
            T_R=inputs["T_R"],
            Z=inputs["Z"],
            M=inputs["M"],
            k=inputs["k"],
            P1_psia=inputs["P1_psia"],
            Kd=inputs["Kd"],
            Kb=inputs["Kb"],
            Kc=inputs["Kc"],
        )
