"""Hydrocyclone R1: Lapple cut size and grade efficiency, Shepherd-Lapple dP.

Spec ``specs/backend/units/hydrocyclone.md``. R1 computes the split that R0
takes as a spec. The row names "Lapple / Barth cut size"; R1 implements
**Lapple**, the standard textbook cyclone model (Lapple, C. E. (1951), in
*Fluid and Particle Mechanics*; Shepherd & Lapple, Ind. Eng. Chem. 31:972
(1939) and 32:1246 (1940); both reproduced in Cooper & Alley, *Air Pollution
Control: A Design Approach*, Ch. 4, and Perry's 8th ed. Sect. 17) for both gas
cyclones and liquid hydrocyclones: the same residence-time derivation with the
fluid's viscosity and the density difference. Barth's static-particle model is
not part of R1.

Slurry approximation (spec step 2): ``Q`` is the inlet's *total* mass flow
over the continuous fluid's density — the particle mass is carried by the
continuous fluid in the residence-time derivation.
"""

from __future__ import annotations

from math import log, pi, sqrt
from typing import Any

from numpy.polynomial.legendre import leggauss

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.hydrocyclone import Hydrocyclone

#: Gauss-Legendre node count for the Rosin-Rammler overall efficiency (H5).
_GL64_POINTS = 64

#: Shepherd-Lapple inlet constant for a tangential inlet (H6), the R1 default.
DEFAULT_K_INLET = 16.0


class HydrocycloneR1SpecError(ValueError):
    """The hydrocyclone R1 spec is bad; the message names the parameter."""


def inlet_velocity(q_m3_s: float, inlet_width_m: float, inlet_height_m: float) -> float:
    """H1: ``v_i = Q/(W*H)`` (Lapple; Cooper & Alley Ch. 4)."""
    return q_m3_s / (inlet_width_m * inlet_height_m)


def effective_turns(body_length_m: float, cone_length_m: float, inlet_height_m: float) -> float:
    """H2: ``N_e = (L_b + L_c/2)/H`` (Lapple; Cooper & Alley Ch. 4)."""
    return (body_length_m + cone_length_m / 2.0) / inlet_height_m


def lapple_cut_diameter(
    mu_Pa_s: float,
    inlet_width_m: float,
    N_e: float,
    v_inlet_m_s: float,
    rho_particle_kg_m3: float,
    rho_fluid_kg_m3: float,
) -> float:
    """H3: ``d50 = sqrt(9*mu*W / (2*pi*N_e*v_i*|rho_p - rho_f|))`` (Lapple, 1951)."""
    return sqrt(
        9.0
        * mu_Pa_s
        * inlet_width_m
        / (2.0 * pi * N_e * v_inlet_m_s * abs(rho_particle_kg_m3 - rho_fluid_kg_m3))
    )


def grade_efficiency(d50_m: float, d_m: float) -> float:
    """H4: ``eta(d) = 1/(1 + (d50/d)**2)`` (Lapple grade-efficiency curve)."""
    return 1.0 / (1.0 + (d50_m / d_m) ** 2)


def rosin_rammler_diameter(d_rr_m: float, n_rr: float, F: float) -> float:
    """H5 inverse mass distribution: ``d(F) = d_RR * (-ln(1-F))**(1/n)``."""
    return d_rr_m * (-log(1.0 - F)) ** (1.0 / n_rr)


def overall_efficiency(d50_m: float, d_rr_m: float, n_rr: float) -> float:
    """H5: ``E = integral_0^1 eta(d(F)) dF`` by 64-point Gauss-Legendre.

    Nodes map ``F = (x + 1)/2`` with weights ``w/2`` on F in [0, 1]; the
    ``leggauss`` nodes are strictly interior so ``1 - F`` stays positive.
    """
    nodes, weights = leggauss(_GL64_POINTS)
    return float(
        sum(
            0.5 * w * grade_efficiency(d50_m, rosin_rammler_diameter(d_rr_m, n_rr, 0.5 * (x + 1.0)))
            for x, w in zip(nodes, weights, strict=True)
        )
    )


def shepherd_lapple_number(
    inlet_height_m: float,
    inlet_width_m: float,
    outlet_diameter_m: float,
    K_inlet: float = DEFAULT_K_INLET,
) -> float:
    """H6: ``N_H = K*H*W/D_e**2`` (Shepherd & Lapple 1939/1940; K = 16 tangential)."""
    return K_inlet * inlet_height_m * inlet_width_m / outlet_diameter_m**2


def shepherd_lapple_pressure_drop(rho_fluid_kg_m3: float, v_inlet_m_s: float, N_H: float) -> float:
    """H6: ``dP = 0.5*rho_f*v_i**2*N_H`` (Shepherd & Lapple 1939/1940)."""
    return 0.5 * rho_fluid_kg_m3 * v_inlet_m_s**2 * N_H


def underflow_fraction(overall_eff: float, fluid_underflow_fraction: float, light_particle: bool) -> float:
    """H7 split of one particle component to the underflow.

    Heavy particles (``rho_p > rho_f``) report to the underflow with
    ``E + (1 - E)*R_f``; light particles (droplets, ``rho_p < rho_f``) report
    to the overflow, so their underflow fraction is ``(1 - E)*R_f``.
    """
    if light_particle:
        return (1.0 - overall_eff) * fluid_underflow_fraction
    return overall_eff + (1.0 - overall_eff) * fluid_underflow_fraction


def _select_fluid_phase(inlet: StreamState, particle_components: list[str]) -> Any:
    """The continuous fluid: largest volume fraction (``x*MW/rho``) among
    phases with no particle component above 0.5 mole fraction (spec step 2).
    If every phase carries a particle component above 0.5, the largest-volume
    phase overall is used."""
    candidates = [
        p for p in inlet.phases if not any(p.composition.get(cid, 0.0) > 0.5 for cid in particle_components)
    ]
    if not candidates:
        candidates = list(inlet.phases)
    return max(candidates, key=lambda p: p.mole_fraction * p.molecular_weight / p.density)


class HydrocycloneR1:
    """Lapple cut size and grade efficiency over the R0 per-component split."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("overflow", "underflow")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]

        particle_components = params.get("particle_components")
        if not isinstance(particle_components, list) or not particle_components:
            raise HydrocycloneR1SpecError(
                "particle_components is required: a non-empty list of component ids"
                " forming the particles/droplets"
            )
        particle_components = [str(c) for c in particle_components]
        unknown = [cid for cid in particle_components if cid not in inlet.composition]
        if unknown:
            raise HydrocycloneR1SpecError(f"particle_components names component(s) {unknown} not in the feed")

        raw_rho_p = params.get("particle_density_kg_m3")
        if raw_rho_p is None or float(raw_rho_p) <= 0.0:
            raise HydrocycloneR1SpecError("particle_density_kg_m3 is required and must be > 0")
        rho_p = float(raw_rho_p)

        fluid_phase = _select_fluid_phase(inlet, particle_components)
        rho_f = float(fluid_phase.density)
        if rho_p == rho_f:
            raise HydrocycloneR1SpecError(
                f"density difference is zero: particle_density_kg_m3 == fluid density {rho_f} kg/m3"
            )

        # --- geometry (refusal table: any geometry value <= 0, missing W or H,
        # missing both (body_length_m, cone_length_m) and N_e) ---
        W = params.get("inlet_width_m")
        H = params.get("inlet_height_m")
        if W is None or float(W) <= 0.0:
            raise HydrocycloneR1SpecError("inlet_width_m is required and must be > 0")
        if H is None or float(H) <= 0.0:
            raise HydrocycloneR1SpecError("inlet_height_m is required and must be > 0")
        W, H = float(W), float(H)
        L_b = params.get("body_length_m")
        L_c = params.get("cone_length_m")
        N_e_param = params.get("N_e")
        for name, value in (
            ("body_length_m", L_b),
            ("cone_length_m", L_c),
            ("N_e", N_e_param),
            ("outlet_diameter_m", params.get("outlet_diameter_m")),
            ("K_inlet", params.get("K_inlet")),
        ):
            if value is not None and float(value) <= 0.0:
                raise HydrocycloneR1SpecError(f"{name} must be > 0")
        if N_e_param is not None:
            N_e = float(N_e_param)
        elif L_b is not None and L_c is not None:
            N_e = effective_turns(float(L_b), float(L_c), H)
        else:
            raise HydrocycloneR1SpecError("either body_length_m and cone_length_m, or N_e, is required")

        # --- particle size form: exactly one of monodisperse / Rosin-Rammler ---
        d_mono = params.get("particle_diameter_m")
        d_rr = params.get("d_rr_m")
        n_rr = params.get("n_rr")
        if d_mono is not None and (d_rr is not None or n_rr is not None):
            raise HydrocycloneR1SpecError(
                "particle_diameter_m and (d_rr_m, n_rr) are alternative forms: give exactly one"
            )
        if d_mono is None and (d_rr is None or n_rr is None):
            raise HydrocycloneR1SpecError(
                "particle_diameter_m (monodisperse) or the pair (d_rr_m, n_rr) is required"
            )

        R_f_raw = params.get("fluid_underflow_fraction", 0.0)
        R_f = float(R_f_raw)
        if not 0.0 <= R_f < 1.0:
            raise HydrocycloneR1SpecError(f"fluid_underflow_fraction {R_f} outside [0, 1)")

        dP_param = params.get("dP")
        d_e = params.get("outlet_diameter_m")
        if dP_param is None and d_e is None:
            raise HydrocycloneR1SpecError("outlet_diameter_m is required when dP is not given")

        mu_override = params.get("fluid_viscosity_Pa_s")
        mu_f = float(fluid_phase.viscosity) if fluid_phase.viscosity is not None else None
        if mu_override is not None:
            mu_f = float(mu_override)
        if mu_f is None or mu_f <= 0.0:
            raise HydrocycloneR1SpecError(
                "fluid_viscosity_Pa_s is required: the continuous phase reports no viscosity"
            )

        # --- H1-H5, H7 ---
        Q = inlet.mass_flow / rho_f  # slurry approximation (module docstring)
        v_i = inlet_velocity(Q, W, H)
        d50 = lapple_cut_diameter(mu_f, W, N_e, v_i, rho_p, rho_f)
        if d_mono is not None:
            E = grade_efficiency(d50, float(d_mono))
        elif d_rr is not None and n_rr is not None:
            E = overall_efficiency(d50, float(d_rr), float(n_rr))
        else:  # unreachable: the exactly-one-form check above refuses this
            raise HydrocycloneR1SpecError(
                "particle_diameter_m (monodisperse) or the pair (d_rr_m, n_rr) is required"
            )

        light = rho_p < rho_f
        fractions: dict[str, float] = {}
        for cid in inlet.composition:
            if cid in particle_components:
                fractions[cid] = underflow_fraction(E, R_f, light)
            else:
                fractions[cid] = R_f

        # --- dP: the param if given, else H6 (N_H reported when computable) ---
        N_H = None
        if dP_param is not None:
            dP = float(dP_param)
        else:
            d_e_val = float(d_e)
            K = float(params.get("K_inlet", DEFAULT_K_INLET))
            N_H = shepherd_lapple_number(H, W, d_e_val, K)
            dP = shepherd_lapple_pressure_drop(rho_f, v_i, N_H)

        result = Hydrocyclone().solve(inlets, {"underflow_fractions": fractions, "dP": dP}, thermo)
        info: dict[str, Any] = {
            "v_inlet_m_s": v_i,
            "N_e": N_e,
            "d50_m": d50,
            "overall_efficiency": E,
            "dP_Pa": dP,
            "rho_fluid_kg_m3": rho_f,
            "mu_fluid_Pa_s": mu_f,
            "Q_m3_s": Q,
        }
        if N_H is not None:
            info["N_H"] = N_H
        for cid, u in fractions.items():
            info[f"underflow_fraction_{cid}"] = u
        return UnitResult(outlets=result.outlets, duty_W=result.duty_W, power_W=result.power_W, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Deoiling produced water on the R0 example basis: oil (nC5) droplets,
        lighter than the water-continuous phase, reporting to the overflow."""
        return {
            "inlet": {
                "T": 323.15,
                "P": 5.0e5,
                "molar_flow": 500.0,
                "composition": {"H2O": 0.95, "nC5": 0.05},
            }
        }, {
            "particle_components": ["nC5"],
            "particle_density_kg_m3": 700.0,
            "particle_diameter_m": 50.0e-6,
            "inlet_width_m": 0.06,
            "inlet_height_m": 0.06,
            "body_length_m": 0.20,
            "cone_length_m": 0.40,
            "outlet_diameter_m": 0.04,
            "fluid_underflow_fraction": 0.9,
        }


__all__ = [
    "DEFAULT_K_INLET",
    "HydrocycloneR1",
    "HydrocycloneR1SpecError",
    "effective_turns",
    "grade_efficiency",
    "inlet_velocity",
    "lapple_cut_diameter",
    "overall_efficiency",
    "rosin_rammler_diameter",
    "shepherd_lapple_number",
    "shepherd_lapple_pressure_drop",
    "underflow_fraction",
]
