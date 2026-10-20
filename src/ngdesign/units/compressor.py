"""Compressor unit plugin, isentropic efficiency (spec S-25).

Plugin kind "unit", name "compressor".

Method (spec): s_in from the inlet; isentropic outlet h_is = flash_ps(z, P_out,
s_in).enthalpy; actual h_out = h_in + (h_is - h_in) / eta_isentropic; outlet =
flash_ph(z, P_out, h_out). power_W = F * (h_out - h_in).

info also carries T_out_isentropic, pressure_ratio and polytropic_head_J_kg via
the Schultz-style average-Z approximation: head = Z_avg * R * T_avg * ln(ratio)
/ MW (J/kg) - the spec allows the average-Z form.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

#: CODATA 2018 molar gas constant, J/(mol.K) (same reference as thermo.pr).
R_IDEAL = 8.31446261815324


def _vapor_mw(state: StreamState) -> float:
    """Mixture molar mass (kg/mol) of the vapor phase; raises if absent."""
    for p in state.phases:
        if p.kind == "vapor":
            return p.molecular_weight / 1000.0
    raise ValueError("compressor outlet has no vapor phase")


def _vapor_z(state: StreamState) -> float:
    for p in state.phases:
        if p.kind == "vapor" and p.z_factor is not None:
            return p.z_factor
    raise ValueError("compressor state has no vapor z-factor")


def _polytropic_head(inlet: StreamState, outlet: StreamState) -> float:
    """Schultz-style average-Z polytropic head approximation, J/kg."""
    z_avg = 0.5 * (_vapor_z(inlet) + _vapor_z(outlet))
    t_avg = 0.5 * (inlet.T + outlet.T)
    mw = 0.5 * (_vapor_mw(inlet) + _vapor_mw(outlet))
    return z_avg * R_IDEAL * t_avg * math.log(outlet.P / inlet.P) / mw


@register("unit", "compressor")
class Compressor:
    """Single-stage gas compressor to a set discharge pressure (spec S-25)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction < 0.999:
            raise ValueError(f"compressor inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f})")
        P_out = float(params["P_out"])
        eta = float(params.get("eta_isentropic", 0.75))
        if P_out <= inlet.P:
            raise ValueError(f"P_out {P_out} Pa must exceed P_in {inlet.P} Pa")
        if not 0.0 < eta <= 1.0:
            raise ValueError(f"eta_isentropic {eta} outside (0, 1]")

        z, flow = inlet.composition, inlet.molar_flow
        isentropic = thermo.flash_ps(z, P_out, inlet.entropy, flow)
        h_out = inlet.enthalpy + (isentropic.enthalpy - inlet.enthalpy) / eta
        outlet = thermo.flash_ph(z, P_out, h_out, flow)

        power_W = flow * (outlet.enthalpy - inlet.enthalpy)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=power_W,
            info={
                "T_out_isentropic": isentropic.T,
                "pressure_ratio": P_out / inlet.P,
                "polytropic_head_J_kg": _polytropic_head(inlet, outlet),
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slice compressor K-101 basis: dry separator gas, 3.447 -> 7.0 MPa.

        The slice gas composition without its free water (the separator has
        removed it), renormalized; fed at 322.15 K so it is single-phase vapor.
        """
        dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 3.447e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        return {"inlet": feed}, {"P_out": 7.0e6, "eta_isentropic": 0.75}
