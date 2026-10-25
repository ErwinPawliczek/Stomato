"""Filter, R1: Ruth constant-pressure cake filtration — pure sizing functions.

Spec: ``specs/backend/units/filter.md`` (unit ``filter``, level R1); the
adapter (``FilterR1``) lives here too and delegates the material split to the
R0 :class:`ngdesign.units.separation.filter.Filter`.

Equations (SI; Ruth 1935; McCabe, Smith & Harriott, *Unit Operations of
Chemical Engineering*, 7th ed., ch. 29; Geankoplis, 4th ed., §14.2):

- **F1** constant-pressure Ruth equation ``t_f = a*v^2 + b*v`` with
  ``v = V/A`` the filtrate volume per area in one cycle, ``a = mu*alpha*c/(2*dP)``
  and ``b = mu*R_m/dP`` (alpha specific cake resistance m/kg, R_m medium
  resistance 1/m, mu filtrate viscosity Pa*s, dP filtration pressure
  difference Pa, c dry-cake mass per filtrate volume kg/m3).
- **F2** per-area volume from the positive quadratic root
  ``v = (-b + sqrt(b^2 + 4*a*t_f))/(2*a)``.
- **F3** required area ``A_req = V_cycle/v`` with ``V_cycle = Q_f*(t_f + t_d)``.
- **F4** cake thickness ``L = c*V_cycle/(A*rho_s*(1 - eps))``.
- **F5** cake-moisture retained liquid ``q_ret = eps/(1 - eps) * mdot_s/rho_s``.
- **F6** dry-cake concentration ``c = mdot_s/Q_f``.
- **F7** capacity ratio ``area/A_req``; below 1 means undersized — reported,
  never refused.

The R1 level at ``cake_porosity = 0`` gives ``f_m = 0`` and reduces exactly to
the R0 split with the user's ``cake_fractions``.
"""

from __future__ import annotations

import math

__all__ = [
    "FilterR1SpecError",
    "cake_thickness",
    "capacity_ratio",
    "concentration",
    "retained_liquid_rate",
    "ruth_area",
    "ruth_constants",
    "ruth_time",
    "ruth_volume_per_area",
]


class FilterR1SpecError(ValueError):
    """The filter R1 spec is bad; the message names the parameter."""


def ruth_constants(mu: float, alpha: float, c: float, dP: float, Rm: float) -> tuple[float, float]:
    """The Ruth coefficients (F1): ``(a, b)`` in s/m^2 and s/m."""
    a = mu * alpha * c / (2.0 * dP)
    b = mu * Rm / dP
    return a, b


def ruth_time(v: float, a: float, b: float) -> float:
    """Filtration time (s) for per-area volume ``v`` (m): F1, ``t = a*v^2 + b*v``."""
    return a * v * v + b * v


def ruth_volume_per_area(t_f: float, a: float, b: float) -> float:
    """Per-area filtrate volume (m) after ``t_f`` (s): F2, the positive root.

    The negative root gives negative volume, so the positive one is the
    physical solution (spec review checklist).
    """
    return (-b + math.sqrt(b * b + 4.0 * a * t_f)) / (2.0 * a)


def ruth_area(
    mu: float,
    alpha: float,
    c: float,
    dP: float,
    Rm: float,
    t_f: float,
    V_cycle: float,
) -> float:
    """Required filtration area (m^2): F2 then F3, ``A_req = V_cycle/v``."""
    a, b = ruth_constants(mu, alpha, c, dP, Rm)
    v = ruth_volume_per_area(t_f, a, b)
    return V_cycle / v


def concentration(mdot_s: float, Q_f: float) -> float:
    """F6: dry-cake mass per filtrate volume (kg/m3), ``c = mdot_s/Q_f``.

    ``Q_f`` is the volumetric flow of the R1 filtrate, after moisture
    retention, not the R0 filtrate.
    """
    return mdot_s / Q_f


def cake_thickness(c: float, V_cycle: float, area: float, rho_s: float, porosity: float) -> float:
    """F4: cake thickness (m), ``L = c*V_cycle/(A*rho_s*(1 - eps))``.

    ``c`` in kg/m3, ``V_cycle`` in m3, ``area`` in m2, ``rho_s`` in kg/m3,
    ``porosity`` the cake void fraction epsilon.
    """
    return c * V_cycle / (area * rho_s * (1.0 - porosity))


def retained_liquid_rate(mdot_s: float, rho_s: float, porosity: float) -> float:
    """F5: liquid held in the cake voids (m3/s), ``q_ret = eps/(1-eps) * mdot_s/rho_s``."""
    return porosity / (1.0 - porosity) * mdot_s / rho_s


def capacity_ratio(area_m2: float, area_required: float) -> float:
    """F7: installed over required area; below 1 means undersized (reported)."""
    return area_m2 / area_required
