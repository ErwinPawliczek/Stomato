"""Gibbs reactor: species-set equilibrium by Gibbs minimisation (spec U-F, R0).

Plugin kind "unit", name "gibbs_reactor".

Method (spec): ports inlet -> outlet. Params ``species`` (every component
allowed to react), ``inerts`` (fixed-amount spectators), and ``thermal``:
``isothermal`` (T_out = inlet T), ``adiabatic`` (duty 0), ``{"duty_W": q}``
(fixed duty) or ``{"T_out": K}`` (fixed outlet temperature). Every feed
component must be listed in exactly one of the two; the overlap refusal and the
unlisted-component refusal are both hard. The amounts come from
:func:`ngdesign.units._physics.gibbs.gibbs_minimum` on the same standard-state
potentials the equilibrium reactor's ln K uses (V2 cross-check, 1e-6). Adiabatic
and duty modes solve the outlet temperature around the minimisation
(composition re-equilibrates at every trial T).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.provenance.recorder import ValueRef, active
from ngdesign.units._physics.gibbs import gibbs_minimum_result
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors._shared import (
    close_thermal,
    trace_component_flows,
    trace_formation_enthalpy,
    trace_model_hf298,
    trace_reaction_duty,
    trace_species_shape,
    trace_standard_pressure,
    z_from,
)


class GibbsReactor:
    """Reactor relaxing its species set to the Gibbs minimum (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        species = list(params["species"])
        inerts = list(params.get("inerts", []))
        overlap = sorted(set(species) & set(inerts))
        if overlap:
            raise ValueError(f"{overlap} are both species and inerts")
        unlisted = sorted(set(inlet.composition) - set(species) - set(inerts))
        if unlisted:
            raise ValueError(f"feed components {unlisted} are not listed in species or inerts")
        n_in = inlet.component_flows()
        thermal = params.get("thermal", "isothermal")
        h_in_W = enthalpy_with_formation(inlet)
        rec = active()
        h_in_ref: ValueRef | None = None
        n_in_ref: ValueRef | None = None
        if rec is not None:
            n_in_ref = trace_component_flows(rec, inlet, n_in)
            h_in_ref = trace_formation_enthalpy(rec, "H_in", h_in_W, inlet)

        def state_at(T: float, T_ref: Any = None) -> StreamState:
            """Outlet state with the minimisation re-solved at temperature T.

            ``T_ref`` (the final evaluation only, tracing on) traces the minimisation.
            """
            result = gibbs_minimum_result(species, inerts, n_in, T, inlet.P)
            n_out = {cid: result.gas.get(cid, 0.0) for cid in species}
            amounts = {**n_out, **{cid: n_in[cid] for cid in inerts}}
            z, total = z_from(amounts), sum(amounts.values())
            if T_ref is not None and rec is not None and n_in_ref is not None:
                inputs: dict[str, Any] = {"n_in": n_in_ref, "T": T_ref, "P": (inlet, "P")}
                inputs["P°"] = trace_standard_pressure(rec)
                for cid in species:
                    inputs[f"ΔfH°[{cid}]"] = trace_model_hf298(rec, cid)
                    inputs[f"H°,S°[{cid}]"] = trace_species_shape(rec, cid)
                rec.equation(
                    "n_out",
                    amounts,
                    "mol/s",
                    "gibbs_minimization",
                    inputs,
                    iterations=result.iterations,
                    note=f"ideal-gas species {species}; inerts {inerts} pass at their feed amounts",
                )
                rec.equation("z_out", z, "1", "mole_fractions", {"n": amounts})
                rec.equation("F_out", total, "mol/s", "mole_fractions", {"n": amounts})
            return thermo.flash_pt(z, T, inlet.P, total)

        T_out, duty = close_thermal(lambda T: enthalpy_with_formation(state_at(T)), inlet.T, h_in_W, thermal)
        T_ref: Any = T_out
        solved_T = thermal == "adiabatic" or (isinstance(thermal, Mapping) and set(thermal) == {"duty_W"})
        if rec is not None and h_in_ref is not None and n_in_ref is not None:
            if solved_T:
                inputs = {"H_in": h_in_ref, "n_in": n_in_ref, "P": (inlet, "P")}
                if duty != 0.0:
                    inputs["Q"] = duty
                T_ref = rec.equation(
                    "T_out",
                    T_out,
                    "K",
                    "reactor_outlet_temperature",
                    inputs,
                    note="the outlet composition is re-minimised at every trial temperature",
                )
            elif isinstance(thermal, str) and thermal == "isothermal":
                T_ref = (inlet, "T")
        outlet = state_at(T_out, T_ref)
        if rec is not None and h_in_ref is not None and not solved_T:
            trace_reaction_duty(rec, duty, outlet, h_in_ref)  # isothermal / fixed T_out: duty closes
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Water-gas shift at 1100 K — the equilibrium example's Gibbs twin.

        Both reactors solve the same physics by different routes and agree to
        1e-6 in the mole fractions (spec U-F V2).
        """
        feed = {
            "T": 1100.0,
            "P": 1013250.0,
            "molar_flow": 2.0,
            "composition": {"CO": 0.5, "H2O": 0.5},
        }
        params = {
            "species": ["CO", "H2O", "CO2", "H2"],
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params
