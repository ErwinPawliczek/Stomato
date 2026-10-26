"""Plug-flow reactor adapters (spec U-R2 wave, unit ``pfr``).

``PfrR1`` is the R1 adapter: the kinetic plug-flow reactor of the shared
:func:`plug_flow.integrate_plug_flow` integrator, single phase, no pressure
drop.  ``PfrR2`` adds tube geometry with the Ergun packed-bed pressure drop
and the fixed-coolant wall heat transfer; R3 (effectiveness + deactivation)
extends this module in its own step.

The outlet state is closed exactly on the formation-enthalpy basis through
``_shared.thermal_outlet`` (spec algorithm step 4); the ODE's end
temperature is reported next to it as ``T_closure_gap_K``.  All SI: J, mol,
K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import apply_extents, enthalpy_with_formation
from ngdesign.units.reactors._shared import (
    _solve_outlet_T,
    reaction_set_param,
    thermal_outlet,
    z_from,
)
from ngdesign.units.reactors.plug_flow import (
    ErgunBed,
    HeatModel,
    PlugFlowError,
    PlugFlowProfile,
    integrate_plug_flow,
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


class PfrR2:
    """Kinetic plug-flow reactor with tube geometry: Ergun dP and wall heat (R2).

    The R1 kinetics integrator over the total volume ``n_tubes·A_c·L`` plus
    the R2 physics: the Ergun pressure drop of a packed bed (spec equation 8)
    and wall heat transfer to a coolant at fixed temperature (spec equation 7).
    The outlet closes on the formation-enthalpy basis at ``P_out = P(V_end)``:
    isothermal re-flashes at ``(T_in, P_out)`` with the duty carried;
    adiabatic and coolant modes solve ``T_out`` from
    ``H_in + Q = H_out(T_out, P_out)`` through
    ``_shared._solve_outlet_T`` (spec algorithm step 4, R2 branch).
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        rset = reaction_set_param(params["reaction_set"])
        tube_diameter = float(params["tube_diameter_m"])
        length = float(params["length_m"])
        n_tubes = int(params.get("n_tubes", 1))
        thermal = params.get("thermal", "isothermal")
        bulk = params.get("bulk_density_kg_m3")
        phase: str = params.get("reacting_phase", "vapor")
        if tube_diameter <= 0.0:
            raise PlugFlowError("tube_diameter_m must be > 0")
        if length <= 0.0:
            raise PlugFlowError("length_m must be > 0")
        if n_tubes < 1:
            raise PlugFlowError("n_tubes must be >= 1")

        bed: ErgunBed | None = None
        if params.get("bed") is not None:
            bed_spec = params["bed"]
            if bed_spec.get("particle_diameter_m") is None:
                raise PlugFlowError("bed requires particle_diameter_m")
            if bed_spec.get("voidage") is None:
                raise PlugFlowError("bed requires voidage")
            bed = ErgunBed(
                particle_diameter_m=float(bed_spec["particle_diameter_m"]),
                voidage=float(bed_spec["voidage"]),
            )
        visc = params.get("viscosity_Pa_s")

        energy: str
        duty = 0.0
        heat_model: HeatModel | None = None
        if isinstance(thermal, str):
            if thermal not in _THERMAL_MODES:
                raise PlugFlowError(
                    f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
                    '{"duty_W": W} or {"coolant_T_K": K, "U_W_m2K": W}'
                )
            energy = thermal
        elif (
            isinstance(thermal, Mapping)
            and set(thermal) == {"duty_W"}
            and isinstance(thermal["duty_W"], (int, float))
        ):
            energy = "uniform_duty"
            duty = float(thermal["duty_W"])
        else:
            raise PlugFlowError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
                '{"duty_W": W} or {"coolant_T_K": K, "U_W_m2K": W}'
            )

        a_cross = math.pi * tube_diameter**2 / 4.0
        volume = n_tubes * a_cross * length

        profile: PlugFlowProfile = integrate_plug_flow(
            inlet,
            rset,
            thermo,
            volume_m3=volume,
            energy=energy,  # type: ignore[arg-type]
            duty_W=duty,
            heat=heat_model,
            reacting_phase=phase,  # type: ignore[arg-type]
            bulk_density_kg_m3=None if bulk is None else float(bulk),
            tube_diameter_m=tube_diameter,
            length_m=length,
            n_tubes=n_tubes,
            viscosity_Pa_s=None if visc is None else float(visc),
            ergun=bed,
        )

        xi_end = list(profile.extents[-1])
        n_out = apply_extents(inlet.component_flows(), rset, xi_end)
        p_out = profile.P_Pa[-1]
        z_out = z_from(n_out)
        total_out = math.fsum(n_out.values())
        t_in = float(inlet.T)
        h_in = enthalpy_with_formation(inlet)
        if energy == "isothermal":
            outlet = thermo.flash_pt(dict(z_out), t_in, p_out, total_out)
            duty_out = enthalpy_with_formation(outlet) - h_in
        elif energy == "uniform_duty":
            t_out = _solve_outlet_T(thermo, z_out, total_out, p_out, t_in, h_in + duty)
            outlet = thermo.flash_pt(dict(z_out), t_out, p_out, total_out)
            duty_out = duty
        else:  # adiabatic: Q = 0
            t_out = _solve_outlet_T(thermo, z_out, total_out, p_out, t_in, h_in)
            outlet = thermo.flash_pt(dict(z_out), t_out, p_out, total_out)
            duty_out = 0.0

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
        info["P_out_Pa"] = float(p_out)
        info["dP_Pa"] = float(inlet.P) - float(p_out)
        info["n_rhs"] = float(profile.n_rhs)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty_out, info=info)
