"""Fired heater R0 (spec U-C 7).

Plugin kind "unit", name "fired_heater", registered from the catalogue row.
One process port (inlet -> outlet) heated by fuel combustion: the process
duty comes from a PH/PT flash at ``P - dP``, the fuel demand from the
mixture LHV with water as VAPOUR (the databank formation enthalpies are
gas-phase standard states, so no condensation correction applies - the
computed methane LHV lands +0.036% on GPSA's 802.3 kJ/mol, a source-data
difference, not a calculation choice). Exactly one process spec of ``T_out``
(K) or ``duty_W`` (W); ``efficiency`` (LHV basis, (0, 1]) and the optional
``fuel_composition`` (component-id map) are required/optional params. Cases
the unit cannot satisfy - cooling specs, non-positive duty, efficiencies
outside (0, 1], missing or element-unsupported fuel data - are refused with
clear text.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data.formation import (
    MissingFormationData,
    atomic_composition,
    formation_enthalpy_298,
)


def fuel_lhv(fuel_composition: dict[str, float]) -> float:
    """Lower heating value of a fuel mixture, J per mol of fuel mixture.

    Water as VAPOUR: the reaction products are CO2 and H2O(g) (plus SO2 for
    sulfur), and the databank formation enthalpies are gas-phase, so the LHV
    falls straight out of the product minus reactant formation enthalpies -
    no latent-heat correction. Elements (graphite, hydrogen) and O2 carry
    their zero standard states; a fuel component made of N2 only is inert and
    contributes zero. Raises ValueError for components whose elements the R0
    combustion set (C, H, O, S) does not cover or whose formation data is
    missing.
    """
    lhv = 0.0
    for cid, y in sorted(fuel_composition.items()):
        if y == 0.0:
            continue
        try:
            atoms = atomic_composition(cid)
            hf_fuel = formation_enthalpy_298(cid)
        except MissingFormationData as exc:
            raise ValueError(
                f"fired_heater: no formation data for fuel component {cid!r}; "
                "the fuel LHV is unavailable"
            ) from exc
        unsupported = sorted(set(atoms) - {"C", "H", "O", "S", "N"})
        if unsupported or (atoms.get("N", 0) and set(atoms) != {"N"}):
            raise ValueError(
                f"fired_heater: fuel component {cid!r} contains elements the R0 "
                f"combustion set (C, H, O, S, inert N2) does not cover: "
                f"{', '.join(unsupported or ['bound nitrogen'])}"
            )
        # Complete combustion per mol of component: C -> CO2, H -> H2O(g), S -> SO2.
        dHf_co2 = formation_enthalpy_298("CO2")
        dHf_h2o = formation_enthalpy_298("H2O")
        dHf_so2 = formation_enthalpy_298("SO2") if atoms.get("S") else 0.0
        dH_reaction = (
            atoms.get("C", 0) * dHf_co2
            + atoms.get("H", 0) / 2.0 * dHf_h2o
            + atoms.get("S", 0) * dHf_so2
            - hf_fuel
        )
        lhv += y * (-dH_reaction)  # O2 and elemental standard states: zero by definition
    return lhv


class FiredHeater:
    """Process-side heater with fuel demand from the LHV (spec U-C 7)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.molar_flow <= 0.0:
            raise ValueError("fired_heater needs a process stream with positive flow")
        efficiency = params.get("efficiency")
        if efficiency is None:
            raise ValueError("fired_heater: efficiency (LHV basis) is required")
        efficiency = float(efficiency)
        if not 0.0 < efficiency <= 1.0:
            raise ValueError(f"fired_heater: efficiency {efficiency} must be > 0 and <= 1 (LHV basis)")

        P_out = inlet.P - float(params.get("dP", 0.0))
        if P_out <= 0:
            raise ValueError(f"fired_heater: dP {params.get('dP')} leaves a non-positive outlet pressure")
        T_out = params.get("T_out")
        duty_spec = params.get("duty_W")
        if (T_out is None) == (duty_spec is None):
            raise ValueError("fired_heater: specify exactly one of T_out (K) or duty_W (W)")

        if T_out is not None:
            T_out = float(T_out)
            if T_out <= 0:
                raise ValueError(f"fired_heater: T_out {T_out} K must be > 0")
            out = thermo.flash_pt(inlet.composition, T_out, P_out, inlet.molar_flow)
        else:
            duty_spec = float(duty_spec)  # type: ignore[assignment]
            out = thermo.flash_ph(inlet.composition, P_out, inlet.enthalpy + duty_spec / inlet.molar_flow, inlet.molar_flow)
        duty = inlet.molar_flow * (out.enthalpy - inlet.enthalpy)
        if duty <= 0.0:
            raise ValueError(
                "fired_heater heats the process stream; the spec gives duty "
                f"{duty:.4f} W <= 0 and cannot be satisfied by firing"
            )

        q_fired = duty / efficiency
        info: dict[str, Any] = {"Q_fired_W": q_fired}
        fuel_composition = params.get("fuel_composition")
        if fuel_composition:
            lhv = fuel_lhv({str(cid): float(y) for cid, y in fuel_composition.items()})
            if lhv <= 0.0:
                raise ValueError("fired_heater: the fuel mixture has no heating value (LHV <= 0)")
            info["fuel_LHV_J_per_mol"] = lhv
            info["fuel_molar_flow"] = q_fired / lhv

        h_out_total = out.enthalpy * out.molar_flow
        return UnitResult(
            outlets={"outlet": out},
            duty_W=h_out_total - inlet.enthalpy * inlet.molar_flow,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Methane fuel at 90% LHV efficiency heating natural gas 300 -> 600 K."""
        inlet = {"T": 300.0, "P": 5.0e5, "molar_flow": 100.0, "composition": {"C1": 1.0}}
        params = {"T_out": 600.0, "efficiency": 0.9, "fuel_composition": {"C1": 1.0}, "dP": 1.0e4}
        return {"inlet": inlet}, params
