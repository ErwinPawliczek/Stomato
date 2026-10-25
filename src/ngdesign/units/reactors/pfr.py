"""Plug-flow reactor adapters (spec U-R2 wave, unit ``pfr``).

``PfrR1`` is the R1 adapter: the kinetic plug-flow reactor of the shared
:func:`plug_flow.integrate_plug_flow` integrator, single phase, no pressure
drop.  R2 (Ergun + wall heat) and R3 (effectiveness + deactivation) extend
this module in their own steps.

The outlet state is closed exactly on the formation-enthalpy basis through
``_shared.thermal_outlet`` (spec algorithm step 4); the ODE's end
temperature is reported next to it as ``T_closure_gap_K``.  All SI: J, mol,
K, Pa, s.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import apply_extents
from ngdesign.units.reactors._shared import reaction_set_param, thermal_outlet
from ngdesign.units.reactors.plug_flow import PlugFlowError, PlugFlowProfile, integrate_plug_flow

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
