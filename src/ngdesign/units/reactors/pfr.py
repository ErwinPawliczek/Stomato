"""Plug-flow reactor adapters (spec U-R2 wave, unit ``pfr``).

``PfrR1`` is the kinetic plug-flow reactor of the shared
:func:`plug_flow.integrate_plug_flow` integrator: single phase, no pressure
drop.  ``PfrR2`` adds tube geometry, the Ergun bed pressure drop and wall heat
transfer to a fixed coolant temperature, q_V = U*a_w*(T_c - T) with
a_w = 4/D_t (Fogler, *Elements of CRE*, ch. 11).  ``PfrR3`` adds the
generalized Thiele effectiveness and power-law catalyst decay.

R3 equations (Aris shape-normalized form; Fogler ch. 15; Froment, Bischoff &
De Wilde ch. 3).  For a power law of order n in the base component,
phi_j = L_p*sqrt(((n+1)/2)*r_p,j/(D_e*C_s,j)) with L_p = R_p/3 for a sphere,
r_p,j = s_j*r_j/(1 - eps_b) the rate per pellet volume and C_s,j the bulk
base-component concentration; eta_j = tanh(phi_j)/phi_j, and 1 - phi_j**2/3
below phi_j = 1e-4.  Activity is separable and uniform along the bed
(Fogler ch. 10): da/dt = -k_d*a**m gives a = [1 + (m-1)*k_d*t]**(1/(1-m))
for m != 1 and a = exp(-k_d*t) for m = 1, frozen at the time on stream.

The outlet state is closed exactly on the formation-enthalpy basis (spec
algorithm step 4); the ODE's end temperature is reported next to it as
``T_closure_gap_K``.  All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw, Reaction, ReactionSet
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import R, apply_extents, enthalpy_with_formation, rate
from ngdesign.units.reactors._shared import _solve_outlet_T, reaction_set_param, thermal_outlet, z_from
from ngdesign.units.reactors.plug_flow import (
    ErgunBed,
    HeatModel,
    PlugFlowError,
    PlugFlowProfile,
    integrate_plug_flow,
    rate_basis_scale,
)

#: Thermal modes R1 accepts (spec params table). ``{"T_out": K}`` is a
#: conversion-reactor mode, not a kinetic one: a PFR cannot hold a stated
#: outlet temperature, so it is refused here rather than silently mapped.
_THERMAL_MODES = ("isothermal", "adiabatic")


class PfrR1:
    """Kinetic plug-flow reactor, rigour level R1 (spec U-R2 wave)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if "bed" in params:
            raise PlugFlowError("a packed bed needs the Ergun pressure drop: use level R2 (param bed)")
        rset = reaction_set_param(params["reaction_set"])
        volume = float(params["volume_m3"])
        thermal = params.get("thermal", "isothermal")
        if isinstance(thermal, str):
            if thermal not in _THERMAL_MODES:
                raise PlugFlowError(
                    f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic' or {{\"duty_W\": W}}"
                )
            energy: str = thermal
            duty = 0.0
        elif isinstance(thermal, dict) and isinstance(thermal.get("duty_W"), (int, float)):
            energy = "uniform_duty"
            duty = float(thermal["duty_W"])
        else:
            raise PlugFlowError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic' or {{\"duty_W\": W}}"
            )
        bulk = params.get("bulk_density_kg_m3")
        phase: str = params.get("reacting_phase", "vapor")

        profile: PlugFlowProfile = integrate_plug_flow(
            inlet,
            rset,
            thermo,
            volume_m3=volume,
            energy=energy,  # type: ignore[arg-type]
            duty_W=duty,
            reacting_phase=phase,  # type: ignore[arg-type]
            bulk_density_kg_m3=None if bulk is None else float(bulk),
        )

        xi_end = list(profile.extents[-1])
        n_out = apply_extents(inlet.component_flows(), rset, xi_end)
        outlet, duty_out = thermal_outlet(inlet, n_out, thermal, thermo)

        t_profile_out = profile.T_K[-1]
        t_max = max(profile.T_K)
        v_at_t_max = profile.V_m3[list(profile.T_K).index(t_max)]
        info: dict[str, float] = {}
        for reaction, xi in zip(rset.reactions, xi_end, strict=True):
            info[f"extent_{reaction.id}_mol_s"] = float(xi)
        info["T_profile_out_K"] = float(t_profile_out)
        info["T_closure_gap_K"] = float(outlet.T) - float(t_profile_out)
        info["T_max_K"] = float(t_max)
        info["V_at_T_max_m3"] = float(v_at_t_max)
        info["n_rhs"] = float(profile.n_rhs)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty_out, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R1-A closed-form case (spec tests): nC4 -> iC4 isomerisation.

        Pure nC4, 1.0 mol/s at 500 K and 2.0e5 Pa, V = 2.0 m3, isothermal.
        First order in nC4 (basis ``concentration``, per unit reactor volume):
        Da = k*(P/(R*T))*V/F0 = 0.575299226 and X = 1 - exp(-Da) =
        0.437463482 (exact because delta n = 0).  Fed to the property
        harness and the bench as the unit's example basis.
        """
        feed = {
            "T": 500.0,
            "P": 2.0e5,
            "molar_flow": 1.0,
            "composition": {"nC4": 1.0},
        }
        params = {
            "reaction_set": {
                "id": "nc4_isom",
                "components": ["nC4", "iC4"],
                "reactions": [
                    {
                        "id": "isom",
                        "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                        "base_component": "nC4",
                        "provenance": "PFR R1-A closed-form worked case (spec pfr.md)",
                        "kinetics": {
                            "rate_units": "mol/(m3·s)",
                            "k0": 1.0e3,
                            "Ea": 5.0e4,
                            "orders": {"nC4": 1.0},
                            "basis": "concentration",
                        },
                    }
                ],
            },
            "volume_m3": 2.0,
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params


def wall_heat_model(coolant_T_K: float, U_W_m2K: float, tube_diameter_m: float) -> HeatModel:
    """Wall heat transfer to a fixed coolant temperature (spec equation 7)."""
    a_w = 4.0 / tube_diameter_m
    return HeatModel(
        n_extra=0,
        y0_extra=(),
        q_V=lambda _v, t, _extra: U_W_m2K * a_w * (coolant_T_K - t),
        d_extra=lambda _v, _t, _extra: (),
    )


def outlet_at_pressure(
    inlet: StreamState, n_out: Mapping[str, float], P_out: float, heat_W: float, thermo: Thermo
) -> StreamState:
    """The outlet at P_out closing H_in + heat_W = H_out on the formation basis.

    ``thermal_outlet`` holds the inlet pressure; a bed with pressure drop
    needs the same root at P_out (spec algorithm step 4), and the root stays
    with its one owner, ``_solve_outlet_T``.
    """
    z = z_from(n_out)
    total = math.fsum(n_out.values())
    h_in = enthalpy_with_formation(inlet)
    t_out = _solve_outlet_T(thermo, z, total, P_out, float(inlet.T), h_in + heat_W)
    return thermo.flash_pt(z, t_out, P_out, total)


def _positive(params: Mapping[str, Any], key: str) -> float:
    if key not in params:
        raise PlugFlowError(f"{key} is required")
    value = float(params[key])
    if value <= 0.0:
        raise PlugFlowError(f"{key} must be > 0")
    return value


def _tube_volume(params: Mapping[str, Any]) -> tuple[float, int, float]:
    """Tube inside diameter, tube count and total reacting volume n_t*A_c*L."""
    if "volume_m3" in params:
        raise PlugFlowError("volume_m3 is R1: R2 and R3 take tube_diameter_m, length_m and n_tubes")
    diameter = _positive(params, "tube_diameter_m")
    length = _positive(params, "length_m")
    n_tubes = int(params.get("n_tubes", 1))
    if n_tubes < 1:
        raise PlugFlowError("n_tubes must be >= 1")
    return diameter, n_tubes, n_tubes * math.pi * diameter**2 / 4.0 * length


def ergun_bed(params: Mapping[str, Any], diameter: float, n_tubes: int) -> ErgunBed | None:
    """The ``bed`` param as an ErgunBed; None for an empty tube."""
    bed = params.get("bed")
    viscosity = params.get("viscosity_Pa_s")
    if bed is None:
        return None
    if not isinstance(bed, Mapping) or {"particle_diameter_m", "voidage"} - set(bed):
        raise PlugFlowError("bed takes {particle_diameter_m, voidage}")
    return ErgunBed(
        tube_diameter_m=diameter,
        particle_diameter_m=float(bed["particle_diameter_m"]),
        voidage=float(bed["voidage"]),
        n_tubes=n_tubes,
        viscosity_Pa_s=None if viscosity is None else float(viscosity),
    )


def plug_flow_info(
    rset: ReactionSet, xi_end: Sequence[float], profile: PlugFlowProfile, outlet: StreamState, p_in: float
) -> dict[str, float]:
    """The common profile info of the tube-geometry levels (spec algorithm step 5)."""
    t_profile_out = profile.T_K[-1]
    t_max = max(profile.T_K)
    info: dict[str, float] = {}
    for reaction, xi in zip(rset.reactions, xi_end, strict=True):
        info[f"extent_{reaction.id}_mol_s"] = float(xi)
    info["T_profile_out_K"] = float(t_profile_out)
    info["T_closure_gap_K"] = float(outlet.T) - float(t_profile_out)
    info["T_max_K"] = float(t_max)
    info["V_at_T_max_m3"] = float(profile.V_m3[list(profile.T_K).index(t_max)])
    info["P_out_Pa"] = float(profile.P_Pa[-1])
    info["dP_Pa"] = p_in - float(profile.P_Pa[-1])
    info["n_rhs"] = float(profile.n_rhs)
    return info


class PfrR2:
    """Plug-flow reactor along a tube: Ergun pressure drop, wall heat, rigour level R2.

    With no bed, no coolant and the same volume this is the R1 integrator
    path exactly; the coolant mode is ``{"coolant_T_K": K, "U_W_m2K": W/m2K}``.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def _multiplier(
        self, params: Mapping[str, Any], rset: ReactionSet, bulk_density: float | None
    ) -> tuple[Callable[[int, float, float, Mapping[str, float]], float] | None, dict[str, float]]:
        """The level's rate multiplier a*eta_j and its info; R2 has none."""
        return None, {}

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        rset = reaction_set_param(params["reaction_set"])
        diameter, n_tubes, volume = _tube_volume(params)
        bed = ergun_bed(params, diameter, n_tubes)
        thermal = params.get("thermal", "isothermal")
        energy: str
        heat: HeatModel | None = None
        duty = 0.0
        if thermal in ("isothermal", "adiabatic"):
            energy = thermal
        elif isinstance(thermal, Mapping) and set(thermal) == {"duty_W"}:
            energy, duty = "uniform_duty", float(thermal["duty_W"])
        elif isinstance(thermal, Mapping) and set(thermal) == {"coolant_T_K", "U_W_m2K"}:
            energy = "heat_model"
            heat = wall_heat_model(_positive(thermal, "coolant_T_K"), _positive(thermal, "U_W_m2K"), diameter)
        else:
            raise PlugFlowError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
                '{"duty_W": W} or {"coolant_T_K": K, "U_W_m2K": W/m2K}'
            )
        bulk = params.get("bulk_density_kg_m3")
        bulk_density = None if bulk is None else float(bulk)
        multiplier, extra_info = self._multiplier(params, rset, bulk_density)
        profile = integrate_plug_flow(
            inlet,
            rset,
            thermo,
            volume_m3=volume,
            energy=energy,  # type: ignore[arg-type]
            duty_W=duty,
            heat=heat,
            reacting_phase=params.get("reacting_phase", "vapor"),
            bulk_density_kg_m3=bulk_density,
            ergun=bed,
            rate_multiplier=multiplier,
        )
        xi_end = list(profile.extents[-1])
        n_out = apply_extents(inlet.component_flows(), rset, xi_end)
        p_out = profile.P_Pa[-1]
        if energy == "isothermal":
            outlet = thermo.flash_pt(z_from(n_out), float(inlet.T), p_out, math.fsum(n_out.values()))
            duty_out = enthalpy_with_formation(outlet) - enthalpy_with_formation(inlet)
        else:
            duty_out = profile.Q_W
            outlet = outlet_at_pressure(inlet, n_out, p_out, duty_out, thermo)
        info = plug_flow_info(rset, xi_end, profile, outlet, float(inlet.P))
        info.update(extra_info)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty_out, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R1 isomerisation in 10 tubes, cooled, in a packed bed.

        Same volume as the R1 example (2 m3 from 10 tubes, D 0.1 m, about
        25.5 m).  The geometry, U and coolant T are illustrative test inputs,
        not package defaults: the rigorous parameters have no default.
        """
        feeds, base = PfrR1.example_case()
        params = {
            "reaction_set": base["reaction_set"],
            "tube_diameter_m": 0.1,
            "length_m": 2.0 / (10 * math.pi * 0.1**2 / 4.0),
            "n_tubes": 10,
            "thermal": {"coolant_T_K": 490.0, "U_W_m2K": 50.0},
            "bed": {"particle_diameter_m": 0.005, "voidage": 0.4},
            "viscosity_Pa_s": 1.2e-5,
        }
        return feeds, params


def activity(params: Mapping[str, Any]) -> float:
    """Catalyst activity a(t) at the time on stream (spec equation 10)."""
    spec = params.get("deactivation")
    if spec is None:
        return 1.0
    if not isinstance(spec, Mapping):
        raise PlugFlowError("deactivation takes {order, k_d_per_s, time_on_stream_s}")
    for key in ("order", "k_d_per_s", "time_on_stream_s"):
        if key not in spec:
            raise PlugFlowError(f"deactivation needs {key}")
        if float(spec[key]) < 0.0:
            raise PlugFlowError(f"deactivation {key} must be >= 0")
    m, k_d, t = float(spec["order"]), float(spec["k_d_per_s"]), float(spec["time_on_stream_s"])
    if m == 1.0:
        return math.exp(-k_d * t)
    base = 1.0 + (m - 1.0) * k_d * t
    if base <= 0.0:
        # m < 1: the activity reaches zero in finite time on stream.
        return 0.0
    return float(base ** (1.0 / (1.0 - m)))


def thiele_effectiveness(phi: float) -> float:
    """eta = tanh(phi)/phi, with the series 1 - phi**2/3 below 1e-4 (spec equation 9)."""
    return 1.0 - phi**2 / 3.0 if phi < 1.0e-4 else math.tanh(phi) / phi


def _base_order(reaction: Reaction) -> float | None:
    """The reaction's order when it is a single-base-order power law, else None."""
    kinetics = reaction.kinetics
    if (
        isinstance(kinetics, PowerLaw)
        and kinetics.reverse is None
        and reaction.equilibrium is None
        and set(kinetics.orders) == {reaction.base_component}
    ):
        return float(kinetics.orders[reaction.base_component])
    return None


class PfrR3(PfrR2):
    """Plug-flow reactor with pellet effectiveness and catalyst decay, rigour level R3.

    The rate is a*eta_j*r_j along the tube.  ``effectiveness`` {reaction_id:
    eta} overrides the Thiele modulus; ``pellet`` {radius_m,
    effective_diffusivity_m2_s} computes it and requires ``bed.voidage``.
    Without either a reaction is unlimited (eta = 1), so absent pellet data
    never invents a diffusion limit; a pellet on a reaction that is not a
    single-base-order power law without an ``effectiveness`` entry is refused.
    """

    def _multiplier(
        self, params: Mapping[str, Any], rset: ReactionSet, bulk_density: float | None
    ) -> tuple[Callable[[int, float, float, Mapping[str, float]], float] | None, dict[str, float]]:
        a = activity(params)
        reactions = rset.reactions
        fixed = {str(k): float(v) for k, v in (params.get("effectiveness") or {}).items()}
        unknown = sorted(set(fixed) - {r.id for r in reactions})
        if unknown:
            raise PlugFlowError(f"effectiveness names unknown reactions {unknown}")
        for rid, eta in fixed.items():
            if not 0.0 < eta <= 1.0:
                raise PlugFlowError(f"effectiveness[{rid!r}] = {eta} must lie in (0, 1]")
        pellet = params.get("pellet")
        scales = [rate_basis_scale(r, bulk_density) for r in reactions]
        orders = [_base_order(r) for r in reactions]
        radius = diffusivity = voidage = 0.0
        if pellet is not None:
            if not isinstance(pellet, Mapping) or {"radius_m", "effective_diffusivity_m2_s"} - set(pellet):
                raise PlugFlowError("pellet takes {radius_m, effective_diffusivity_m2_s}")
            radius = float(pellet["radius_m"])
            diffusivity = float(pellet["effective_diffusivity_m2_s"])
            if radius <= 0.0 or diffusivity <= 0.0:
                raise PlugFlowError("pellet radius_m and effective_diffusivity_m2_s must be > 0")
            bed = params.get("bed")
            if not isinstance(bed, Mapping) or "voidage" not in bed:
                raise PlugFlowError("pellet requires bed.voidage (rate per pellet volume)")
            voidage = float(bed["voidage"])
            for reaction, order in zip(reactions, orders, strict=True):
                if order is None and reaction.id not in fixed:
                    raise PlugFlowError(
                        f"reaction {reaction.id!r} is not a single-base-order power law: "
                        "give its effectiveness explicitly"
                    )

        def multiplier(j: int, t: float, p: float, z: Mapping[str, float]) -> float:
            reaction = reactions[j]
            if reaction.id in fixed:
                return a * fixed[reaction.id]
            order = orders[j]
            if pellet is None or order is None:
                return a
            c_s = float(z.get(reaction.base_component, 0.0)) * p / (R * t)
            r_j = rate(reaction, t, p, z)
            if c_s <= 0.0 or r_j <= 0.0:
                return a
            r_p = scales[j] * r_j / (1.0 - voidage)
            phi = (radius / 3.0) * math.sqrt((order + 1.0) / 2.0 * r_p / (diffusivity * c_s))
            return a * thiele_effectiveness(phi)

        return multiplier, {"activity": a}

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R2 example with an illustrative pellet and second-order decay.

        Test inputs, not package defaults.
        """
        feeds, params = PfrR2.example_case()
        return feeds, {
            **params,
            "pellet": {"radius_m": 1.5e-3, "effective_diffusivity_m2_s": 1.0e-6},
            "deactivation": {"order": 2.0, "k_d_per_s": 1.0e-6, "time_on_stream_s": 2.592e5},
        }
