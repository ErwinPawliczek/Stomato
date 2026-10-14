"""Centrifugal pump unit plugin (spec S-27).

Plugin kind "unit", name "pump".

Method (spec): ports inlet -> outlet. Params P_out (Pa) and eta (default 0.65).
Volumetric flow Q from the liquid density (stream mass flow / liquid phase
density); shaft power = Q * dP / eta (inlined here - the S-08 correlation plugin
is not merged yet). h_out = h_in + shaft/F; outlet = flash_ph(z, P_out, h_out).
power_W = shaft power. info: head_m, Q_m3_s. Raises ValueError when the inlet
carries vapor (vapor_fraction > 0.001).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register

#: Standard gravity used for head, m (ISO 80000).
G_STD = 9.80665


def _liquid_density(state: StreamState) -> float:
    """Density of the dominant (largest phase fraction) liquid phase, kg/m3."""
    liquids = [p for p in state.phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        raise ValueError("pump inlet has no liquid phase data")
    return max(liquids, key=lambda p: p.mole_fraction).density


@register("unit", "pump")
class Pump:
    """Centrifugal pump raising a liquid to a set discharge pressure (spec S-27)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction > 0.001:
            raise ValueError(f"pump inlet has vapor (vapor_fraction={inlet.vapor_fraction:.4f})")
        P_out = float(params["P_out"])
        eta = float(params.get("eta", 0.65))
        if not 0.0 < eta <= 1.0:
            raise ValueError(f"eta {eta} outside (0, 1]")

        rho = _liquid_density(inlet)
        Q = inlet.mass_flow / rho  # m3/s
        dP = P_out - inlet.P
        shaft_W = Q * dP / eta

        z, flow = inlet.composition, inlet.molar_flow
        outlet = thermo.flash_ph(z, P_out, inlet.enthalpy + shaft_W / flow, flow)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=shaft_W,
            info={
                "head_m": dP / (rho * G_STD),
                "Q_m3_s": Q,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slice pump P-101 basis: condensate stand-in for the HC liquid, 1.0 -> 1.5 MPa.

        The slice HC liquid composition is only known after V-101 solves, so the
        example uses a defined condensate blend (single-phase liquid at 293.15 K /
        1.0 MPa) at the slice's pressure levels.
        """
        feed = {
            "T": 293.15,
            "P": 1.0e6,
            "molar_flow": 5.0,
            "composition": {
                "C3": 0.35,
                "iC4": 0.15,
                "nC4": 0.25,
                "iC5": 0.10,
                "nC5": 0.10,
                "C6+": 0.05,
            },
        }
        return {"inlet": feed}, {"P_out": 1.5e6, "eta": 0.65}
