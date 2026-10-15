"""Turbo-expander unit plugin, isentropic efficiency (wave-2 spec).

Plugin kind "unit", name "expander".

Method (spec): the mirror of the compressor. s_in from the inlet; isentropic
reference h_is = flash_ps(z, P_out, s_in).enthalpy; the real outlet recovers
only eta of the isentropic enthalpy drop: h_out = h_in - eta * (h_in - h_is);
outlet = flash_ph(z, P_out, h_out) -- a cryogenic outlet may condense, which
the thermo layer's 3-phase flash handles. power_recovered_W = F * (h_in -
h_out) (power leaves the process, so UnitResult.power_W is negative).

info also carries T_out and the outlet phase split (one mole-fraction key per
present phase kind).

Accuracy note: the locked databank maps C6+ to n-hexane, so absolute dew-point
temperatures at cryogenic outlets are indicative only; the phase split is
directionally right, the exact liquid fraction is not a design number.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets.slice import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.registry import register


@register("unit", "expander")
class Expander:
    """Gas turbo-expander expanding to a set outlet pressure, recovering shaft power."""

    inlet_ports = ("gas_in",)
    outlet_ports = ("gas_out",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["gas_in"]
        if inlet.vapor_fraction < 0.999:
            raise ValueError(f"expander inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f})")
        P_out = float(params["P_out"])
        eta = float(params.get("eta_isentropic", 0.80))
        if P_out >= inlet.P:
            raise ValueError(f"P_out {P_out} Pa must be below P_in {inlet.P} Pa (this is an expander)")
        if P_out <= 0:
            raise ValueError(f"P_out {P_out} Pa must be > 0")
        if not 0.0 < eta <= 1.0:
            raise ValueError(f"eta_isentropic {eta} outside (0, 1]")

        z, flow = inlet.composition, inlet.molar_flow
        isentropic = thermo.flash_ps(z, P_out, inlet.entropy, flow)
        h_out = inlet.enthalpy - eta * (inlet.enthalpy - isentropic.enthalpy)
        outlet = thermo.flash_ph(z, P_out, h_out, flow)

        power_W = flow * (outlet.enthalpy - inlet.enthalpy)  # negative: shaft power out
        info: dict[str, float] = {
            "power_recovered_w": -power_W,
            "T_out": outlet.T,
            "T_out_isentropic": isentropic.T,
        }
        for phase in outlet.phases:
            info[f"{phase.kind}_mole_fraction"] = phase.mole_fraction
        return UnitResult(
            outlets={"gas_out": outlet},
            duty_W=0.0,
            power_W=power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Expander-plant basis: dry separator gas let down 7.0 -> 2.0 MPa.

        The slice gas composition without its free water (the separator has
        removed it), renormalized; fed at 322.15 K so it is single-phase vapor.
        """
        dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        return {"gas_in": feed}, {"P_out": 2.0e6, "eta_isentropic": 0.80}
