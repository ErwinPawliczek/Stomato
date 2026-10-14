"""Heat-exchange unit plugins to a specified outlet condition (spec S-26).

Plugin kind "unit", names "heater", "cooler", "air_cooler", "shell_tube" —
one class, four registrations (the physics is identical; the name selects the
equipment type downstream).

Method (spec): ports inlet -> outlet. Params T_out (K) and dP (Pa, default 0):
outlet = flash_pt(z, T_out, P_in - dP), duty_W = F*(h_out - h_in). Alternatively
a `duty_W` param instead of T_out gives outlet = flash_ph at h_in + duty/F.
info: duty_kW.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets.slice import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.registry import register


@register("unit", "heater")
@register("unit", "cooler")
@register("unit", "air_cooler")
@register("unit", "shell_tube")
class HeatExchanger:
    """Heat exchange to a specified outlet temperature or duty (spec S-26)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        dP = float(params.get("dP", 0.0))
        if dP < 0:
            raise ValueError("dP must be >= 0")
        P_out = inlet.P - dP
        if P_out <= 0:
            raise ValueError(f"dP {dP} leaves a non-positive outlet pressure")

        z, flow, h_in = inlet.composition, inlet.molar_flow, inlet.enthalpy
        has_T = "T_out" in params
        has_duty = "duty_W" in params
        if has_T == has_duty:
            raise ValueError("specify exactly one of T_out (K) or duty_W (W)")

        if has_T:
            T_out = float(params["T_out"])
            if T_out <= 0:
                raise ValueError(f"T_out {T_out} K must be > 0")
            outlet = thermo.flash_pt(z, T_out, P_out, flow)
        else:
            duty_spec = float(params["duty_W"])
            if flow <= 0:
                raise ValueError("duty_W spec needs a positive inlet flow")
            outlet = thermo.flash_ph(z, P_out, h_in + duty_spec / flow, flow)

        duty_W = flow * (outlet.enthalpy - h_in)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=duty_W,
            power_W=0.0,
            info={"duty_kW": duty_W / 1000.0},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slice air cooler E-101 basis: dry separator gas cooled 322.15 -> 313.15 K.

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
        return {"inlet": feed}, {"T_out": 313.15, "dP": 35e3}
