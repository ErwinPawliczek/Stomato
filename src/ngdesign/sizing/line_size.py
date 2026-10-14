"""Line sizing by service velocity limits (spec S-20).

Chooses the smallest NPS (schedule 40) whose actual velocity satisfies the
service's velocity limits, from a candidate NPS list. Pipe geometry comes from
``ngdesign.data`` (ASME B36.10M); limits live in one swappable module-level
table. Gas service additionally honours a fraction of the API RP 14E erosional
velocity (see :mod:`ngdesign.sizing.erosional`).

Out of scope (v1): two-phase lines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ngdesign.data import pipe
from ngdesign.registry import register
from ngdesign.sizing.erosional import erosional_api14e

__all__ = [
    "CANDIDATE_NPS_IN",
    "SCHEDULE",
    "SERVICE_LIMITS",
    "SUCTION_LIMITS",
    "LineSize",
    "line_size",
]

SCHEDULE = "40"
CANDIDATE_NPS_IN: tuple[float, ...] = (1, 1.5, 2, 3, 4, 6, 8, 10, 12, 14, 16, 18, 20, 24)

_ROLES = ("line", "suction", "discharge")


@dataclass(frozen=True)
class VelocityLimits:
    """Velocity limits for one service.

    A ``None`` field means the limit does not apply. Selection uses the max
    limits only; ``v_min_m_s`` is recorded for review and downstream checks.
    """

    v_min_m_s: float | None = None
    v_max_m_s: float | None = None
    rho_v2_max_pa: float | None = None
    erosional_fraction: float | None = None  # v <= fraction * API 14E v_e


# Initial values -- VERIFY with process engineer.
SERVICE_LIMITS: dict[str, VelocityLimits] = {
    "PG": VelocityLimits(v_max_m_s=18.0, rho_v2_max_pa=6000.0, erosional_fraction=0.8),
    "PL": VelocityLimits(v_min_m_s=1.0, v_max_m_s=3.0),
    "W": VelocityLimits(v_min_m_s=1.0, v_max_m_s=3.0),
    "GL": VelocityLimits(v_max_m_s=1.5),
}

# Liquid pump suction -- VERIFY with process engineer.
SUCTION_LIMITS = VelocityLimits(v_min_m_s=0.6, v_max_m_s=1.5)

# API RP 14E continuous-service C factor (see ngdesign.sizing.erosional).
EROSIONAL_C_CONTINUOUS = 100.0


def _pipe_area_m2(nps_in: float) -> float:
    """Flow area [m2] of one candidate NPS, schedule 40, from reference data."""
    row = pipe(nps_in, SCHEDULE)
    id_m = float(row["id_mm"]) / 1000.0
    return math.pi * id_m**2 / 4.0


def line_size(
    service: str,
    flow_m3_s: float,
    rho_kg_m3: float,
    role: str = "line",
    C: float = EROSIONAL_C_CONTINUOUS,
) -> dict[str, Any]:
    """Smallest schedule-40 NPS whose velocity satisfies the service limits.

    Args:
        service: Service code, a key of ``SERVICE_LIMITS`` (PG gas, PL process
            liquid, W water, GL glycol).
        flow_m3_s: Actual volumetric flow [m3/s].
        rho_kg_m3: Flowing density [kg/m3]; for gas service, the mixture
            density used by the API 14E erosional check.
        role: ``"line"``/``"discharge"`` or ``"suction"``; ``"suction"`` applies
            the tighter pump-suction limits to liquid services (ignored for gas).
        C: API 14E constant for the erosional check (gas service only).

    Returns:
        dict with ``nps_in``, ``velocity_m_s``, ``rho_v2`` and ``limit_hit``
        (name of the binding max limit at the selected size).

    Raises:
        ValueError: on unknown service/role, non-physical inputs, or a flow no
            candidate NPS can carry within the limits.
    """
    if service not in SERVICE_LIMITS:
        raise ValueError(f"unknown service {service!r}; have {sorted(SERVICE_LIMITS)}")
    if role not in _ROLES:
        raise ValueError(f"unknown role {role!r}; have {_ROLES}")
    if flow_m3_s <= 0:
        raise ValueError(f"flow must be positive, got {flow_m3_s}")
    if rho_kg_m3 <= 0:
        raise ValueError(f"density must be positive, got {rho_kg_m3}")
    if C <= 0:
        raise ValueError(f"C must be positive, got {C}")

    limits = SUCTION_LIMITS if role == "suction" and service != "PG" else SERVICE_LIMITS[service]

    # Locals so mypy can narrow both Optional fields together.
    frac = limits.erosional_fraction
    v_erosional: float | None = None
    if frac is not None:
        v_erosional = erosional_api14e(rho_mix_kg_m3=rho_kg_m3, C=C)["v_erosional_m_s"]

    def _violations(velocity_m_s: float) -> list[str]:
        """Max limits the given velocity violates, by name."""
        bad = []
        if limits.v_max_m_s is not None and velocity_m_s > limits.v_max_m_s:
            bad.append("v_max")
        if limits.rho_v2_max_pa is not None and rho_kg_m3 * velocity_m_s**2 > limits.rho_v2_max_pa:
            bad.append("rho_v2")
        if v_erosional is not None and frac is not None and velocity_m_s > frac * v_erosional:
            bad.append("erosional_api14e")
        return bad

    chosen: tuple[float, float] | None = None  # (nps_in, velocity)
    for nps_in in CANDIDATE_NPS_IN:
        velocity_m_s = flow_m3_s / _pipe_area_m2(nps_in)
        if not _violations(velocity_m_s):
            chosen = (nps_in, velocity_m_s)
            break
    if chosen is None:
        raise ValueError(
            f"no candidate NPS up to {CANDIDATE_NPS_IN[-1]} in carries {flow_m3_s} m3/s "
            f"within {service} velocity limits"
        )

    nps_in, velocity_m_s = chosen
    rho_v2 = rho_kg_m3 * velocity_m_s**2

    # The binding limit is the one closest to being violated at the chosen size.
    margins: list[tuple[float, str]] = []
    if limits.v_max_m_s is not None:
        margins.append((velocity_m_s / limits.v_max_m_s, "v_max"))
    if limits.rho_v2_max_pa is not None:
        margins.append((rho_v2 / limits.rho_v2_max_pa, "rho_v2"))
    if v_erosional is not None and limits.erosional_fraction is not None:
        margins.append((velocity_m_s / (limits.erosional_fraction * v_erosional), "erosional_api14e"))
    limit_hit = max(margins)[1]

    return {"nps_in": nps_in, "velocity_m_s": velocity_m_s, "rho_v2": rho_v2, "limit_hit": limit_hit}


@register("correlation", "line_size")
class LineSize:
    """Correlation plugin adapter; see :func:`line_size`."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return line_size(**inputs)
