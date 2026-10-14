"""Kremser absorber stage count (spec S-05).

Kremser equation for a countercurrent absorber with linear equilibrium
``y = m * x`` and absorption factor ``A = L / (m * G)`` (Treybal, "Mass-Transfer
Operations", 3rd ed., Sec. 5):

    N = ln[ ((y_in - m*x_top) / (y_out - m*x_top)) * (1 - 1/A) + 1/A ] / ln(A)

with the limit ``N = (y_in - y_out) / (y_out - m*x_top)`` as ``A -> 1``.

Concentrations are in consistent mole-fraction-like units; ``x_top`` is the
solute fraction in the entering (lean) solvent.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.registry import register

__all__ = ["Kremser", "kremser"]

_A_LIMIT_BAND = 1e-6


def kremser(A: float, y_in: float, y_out: float, m: float, x_top: float) -> dict[str, float]:
    """Ideal-stage count for a countercurrent absorber (Kremser equation).

    Args:
        A: Absorption factor ``L / (m * G)`` [dimensionless].
        y_in: Solute fraction in the entering gas (bottom) [mole fraction-like].
        y_out: Solute fraction in the leaving gas (top) [mole fraction-like].
        m: Equilibrium-line slope ``y = m * x`` [dimensionless].
        x_top: Solute fraction in the entering lean solvent [mole fraction-like].

    Returns:
        dict with ``N_stages`` (ideal stages, fractional).

    Raises:
        ValueError: on non-physical inputs or an infeasible specification.
    """
    if A <= 0:
        raise ValueError(f"absorption factor A must be positive, got {A}")
    if m <= 0:
        raise ValueError(f"equilibrium slope m must be positive, got {m}")
    if x_top < 0 or y_in < 0 or y_out < 0:
        raise ValueError(
            f"concentrations must be non-negative, got y_in={y_in}, y_out={y_out}, x_top={x_top}"
        )
    if y_out <= m * x_top:
        raise ValueError(
            f"infeasible spec: y_out ({y_out}) must exceed m*x_top ({m * x_top}); "
            "the lean solvent already reaches the outlet spec"
        )
    if y_in < y_out:
        raise ValueError(f"infeasible spec: y_in ({y_in}) is below y_out ({y_out}) in an absorber")

    y_star = m * x_top
    if abs(A - 1.0) < _A_LIMIT_BAND:
        return {"N_stages": (y_in - y_out) / (y_out - y_star)}

    ratio = (y_in - y_star) / (y_out - y_star)
    log_arg = ratio * (1.0 - 1.0 / A) + 1.0 / A
    if log_arg <= 0:
        raise ValueError(f"infeasible spec: Kremser argument {log_arg} is not positive (A={A})")
    return {"N_stages": math.log(log_arg) / math.log(A)}


@register("correlation", "kremser")
class Kremser:
    """Correlation plugin adapter; see :func:`kremser`."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return kremser(**inputs)
