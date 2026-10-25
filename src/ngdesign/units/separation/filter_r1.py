"""Filter, R1: Ruth constant-pressure cake filtration.

Spec: ``specs/backend/units/filter.md`` (unit ``filter``, level R1).

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

The adapter (:class:`FilterR1`) delegates the material split to the R0
:class:`ngdesign.units.separation.filter.Filter`: first with the user's
``cake_fractions`` (the dry split), then with the moisture-adjusted
fractions. The level reduces exactly to R0 at ``cake_porosity = 0``.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.filter import Filter

__all__ = [
    "FilterR1",
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


def _filtrate_liquid(filtrate: StreamState) -> tuple[float, float | None]:
    """The R0 filtrate's largest-volume liquid phase: ``(density, viscosity)``.

    Volume of a phase is its mass over its density; the molar flow is common,
    so the comparison uses ``x*MW/density``.
    """
    best: tuple[float, float, float | None] | None = None
    for phase in filtrate.phases:
        if phase.kind is PhaseKind.VAPOR or phase.mole_fraction <= 0.0:
            continue
        metric = phase.mole_fraction * phase.molecular_weight / phase.density
        if best is None or metric > best[0]:
            best = (metric, phase.density, phase.viscosity)
    if best is None:
        raise FilterR1SpecError(
            "filtrate_viscosity_Pa_s: the R0 filtrate has no liquid phase, so the "
            "filtrate viscosity is unavailable"
        )
    return best[1], best[2]


class FilterR1:
    """Ruth constant-pressure cake filtration over the R0 split (level R1).

    The material split is delegated to the R0 :class:`Filter` — first with the
    user's ``cake_fractions`` (the dry split), then with the moisture-adjusted
    fractions. Sizing (F1-F7) is reported in ``info``; a ``capacity_ratio``
    below 1 is reported, never refused.
    """

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("filtrate", "cake")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]

        dP = params.get("dP")
        if dP is None or float(dP) <= 0.0:
            raise FilterR1SpecError(f"dP {dP} is required and must be > 0 (Pa)")
        dP_f = float(dP)

        alpha = params.get("specific_cake_resistance_m_kg")
        if alpha is None or float(alpha) <= 0.0:
            raise FilterR1SpecError(
                f"specific_cake_resistance_m_kg {alpha} is required and must be > 0 (m/kg)"
            )
        alpha_f = float(alpha)

        Rm = params.get("medium_resistance_1_m", 0.0)
        if float(Rm) < 0.0:
            raise FilterR1SpecError(f"medium_resistance_1_m {Rm} must be >= 0 (1/m)")
        Rm_f = float(Rm)

        t_f = params.get("t_filtration_s")
        if t_f is None or float(t_f) <= 0.0:
            raise FilterR1SpecError(f"t_filtration_s {t_f} is required and must be > 0 (s per cycle)")
        t_f_f = float(t_f)

        t_down = params.get("t_down_s", 0.0)
        if float(t_down) < 0.0:
            raise FilterR1SpecError(f"t_down_s {t_down} must be >= 0 (s per cycle)")
        t_down_f = float(t_down)

        rho_s = params.get("solid_density_kg_m3")
        if rho_s is None or float(rho_s) <= 0.0:
            raise FilterR1SpecError(
                f"solid_density_kg_m3 {rho_s} is required and must be > 0 (kg/m3); "
                "the solid density is a parameter, never a phase value"
            )
        rho_s_f = float(rho_s)

        porosity = float(params.get("cake_porosity", 0.0))
        if not 0.0 <= porosity < 1.0:
            raise FilterR1SpecError(f"cake_porosity {porosity} must be in [0, 1) (cake void fraction)")

        area = params.get("area_m2")
        if area is not None and float(area) <= 0.0:
            raise FilterR1SpecError(f"area_m2 {area} must be > 0 when given (m2)")
        area_f = float(area) if area is not None else None

        cake_fractions = params.get("cake_fractions")
        if not isinstance(cake_fractions, dict) or not cake_fractions:
            raise FilterR1SpecError(
                "cake_fractions is required: a non-empty map of component id to "
                "the fraction of its molar flow sent to the cake (the solids)"
            )
        dry_fractions = {str(cid): float(f) for cid, f in cake_fractions.items()}

        # Dry split (R0): the cake's mass flow is the dry-solids rate, because
        # only cake components enter it. Unknown cake components are refused
        # by R0 itself (spec: delegate, don't duplicate).
        r0 = Filter().solve(inlets, {"cake_fractions": dry_fractions, "dP": dP_f}, thermo)
        mdot_s = r0.outlets["cake"].mass_flow
        if mdot_s <= 0.0:
            raise FilterR1SpecError(
                "cake_fractions: no cake component has positive flow, so there "
                f"are no solids to form a cake (dry-solids rate {mdot_s} kg/s)"
            )
        rho_L, mu_phase = _filtrate_liquid(r0.outlets["filtrate"])
        mu = params.get("filtrate_viscosity_Pa_s")
        if mu is None:
            mu = mu_phase
        if mu is None:
            raise FilterR1SpecError(
                "filtrate_viscosity_Pa_s: the filtrate liquid phase carries no "
                "viscosity; give the override (Pa s)"
            )
        mu_f = float(mu)

        # Moisture (F5): filtrate-composition liquid held in the cake voids.
        q_ret = retained_liquid_rate(mdot_s, rho_s_f, porosity)
        # Stream molar mass from the phases: the component database has no
        # entry for solid-only components, so composition-based helpers miss.
        mw_filtrate = sum(
            p.mole_fraction * p.molecular_weight for p in r0.outlets["filtrate"].phases
        )  # g/mol
        n_ret = q_ret * rho_L / (mw_filtrate / 1000.0)  # mol/s
        n_filtrate_r0 = r0.outlets["filtrate"].molar_flow
        f_m = n_ret / n_filtrate_r0
        if f_m > 1.0:
            raise FilterR1SpecError(f"moisture: the cake cannot hold the retained liquid, f_m = {f_m} > 1")

        # R1 split: the user's cake_fractions for the cake components, the same
        # moisture fraction f_m for every other component (shared composition).
        fractions = dict(dry_fractions)
        for cid in inlet.composition:
            if cid not in fractions:
                fractions[cid] = f_m
        r1 = Filter().solve(inlets, {"cake_fractions": fractions, "dP": dP_f}, thermo)

        Q_f = r1.outlets["filtrate"].mass_flow / rho_L  # m3/s
        c = concentration(mdot_s, Q_f)  # F6, R1 filtrate volume
        V_cycle = Q_f * (t_f_f + t_down_f)  # F3
        area_required = ruth_area(mu_f, alpha_f, c, dP_f, Rm_f, t_f_f, V_cycle)
        installed = area_f if area_f is not None else area_required
        info: dict[str, float] = {
            "c_kg_m3": c,
            "V_cycle_m3": V_cycle,
            "v_per_area_m": V_cycle / area_required,
            "A_required_m2": area_required,
            "cake_thickness_m": cake_thickness(c, V_cycle, installed, rho_s_f, porosity),
            "retained_liquid_m3_s": q_ret,
            "moisture_fraction": f_m,
        }
        if area_f is not None:
            info["capacity_ratio"] = capacity_ratio(area_f, area_required)
        return UnitResult(outlets=r1.outlets, duty_W=r1.duty_W, power_W=r1.power_W, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 slurry (water with 2 mol % silica) with full sizing params.

        The R0 split spec is unchanged; the sizing constants are the CF test
        set (alpha 1e11 m/kg, R_m 1e10 1/m, t_f 600 s, t_d 300 s, rho_s
        2650 kg/m3, porosity 0.4) and the printed water viscosity override.
        """
        return {
            "inlet": {
                "T": 298.15,
                "P": 3.0e5,
                "molar_flow": 200.0,
                "composition": {"H2O": 0.98, "SiO2": 0.02},
            }
        }, {
            "cake_fractions": {"SiO2": 1.0},
            "dP": 3.0e4,
            "specific_cake_resistance_m_kg": 1e11,
            "medium_resistance_1_m": 1e10,
            "t_filtration_s": 600.0,
            "t_down_s": 300.0,
            "solid_density_kg_m3": 2650.0,
            "cake_porosity": 0.4,
            "filtrate_viscosity_Pa_s": 8.937e-4,
        }
