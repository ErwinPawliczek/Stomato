"""JT (Joule-Thomson) valve unit plugin (spec S-28).

Plugin kind "unit", name "jt_valve".

Method (spec): ports inlet -> outlet, param P_out (Pa). Isenthalpic expansion:
outlet = flash_ph(z, P_out, h_in); info dT_K = T_out - T_in. No duty, no power.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S


def dry_gas_feed(T: float, P: float) -> dict[str, Any]:
    """The slice gas composition without its free water (the separator has
    removed it), renormalized; single-phase vapor at 322.15 K."""
    dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
    total = sum(dry.values())
    return {
        "T": T,
        "P": P,
        "molar_flow": 50 * MMSCFD_TO_MOL_S,
        "composition": {cid: x / total for cid, x in dry.items()},
    }


@register("unit", "jt_valve")
class JTValve:
    """Isenthalpic pressure letdown across a JT valve (spec S-28)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        P_out = float(params["P_out"])
        if P_out <= 0:
            raise ValueError(f"P_out {P_out} Pa must be > 0")

        z, flow, h_in = inlet.composition, inlet.molar_flow, inlet.enthalpy
        outlet = thermo.flash_ph(z, P_out, h_in, flow)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={"dT_K": outlet.T - inlet.T},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slice gas letdown basis: dry separator gas, 7.0 -> 3.0 MPa."""
        return {"inlet": dry_gas_feed(322.15, 7.0e6)}, {"P_out": 3.0e6}
