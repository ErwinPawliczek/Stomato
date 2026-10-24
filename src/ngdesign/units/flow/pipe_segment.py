"""Pipe segment, R0 (spec U-B, plan §2 U-B 7).

Method (spec): the segment is a fixed-dP isenthalpic letdown — the user
supplies ``dP`` (drop, >= 0) or ``P_out``; the outlet is a PH flash at the
inlet enthalpy. This is definitional at R0: the pressure drop itself is
claimed, not computed (Crane TP-410-style; the U-B Darcy line
``units/_physics/pressure_drop.py`` is a later round). An ``elevation_m``
rise contributes a ``rho * g * dz`` hydrostatic term evaluated with the
inlet's dominant phase density and reported in info — it does **not** move
the outlet state at R0.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

#: Standard gravity, m/s2 (ISO 80000).
G_STD = 9.80665


class PipeSegmentSpecError(ValueError):
    """Typed refusal naming the parameter of a bad pipe-segment spec."""


class PipeSegment:
    """Fixed-dP isenthalpic pipe segment with a reported hydrostatic term (R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        has_P_out = "P_out" in params
        has_dP = "dP" in params
        if has_P_out == has_dP:
            raise PipeSegmentSpecError("exactly one of P_out / dP must be given")
        elevation_m = float(params.get("elevation_m", 0.0))

        if has_dP:
            dP = float(params["dP"])
            if dP < 0:
                raise PipeSegmentSpecError(f"dP {dP} Pa must be >= 0 (flow loses pressure)")
            P_out = inlet.P - dP
        else:
            P_out = float(params["P_out"])
            if P_out >= inlet.P:
                raise PipeSegmentSpecError(f"P_out {P_out} Pa must be below the inlet pressure {inlet.P} Pa")
        dominant = max(inlet.phases, key=lambda p: p.mole_fraction)
        hydrostatic_Pa = dominant.density * G_STD * elevation_m
        if has_dP:
            # An elevation rise costs rho*g*z on top of the frictional dP.
            P_out -= hydrostatic_Pa
        if P_out <= 0:
            raise PipeSegmentSpecError(f"outlet pressure {P_out} Pa must be > 0")

        outlet = thermo.flash_ph(inlet.composition, P_out, inlet.enthalpy, inlet.molar_flow)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={"dT_K": outlet.T - inlet.T, "hydrostatic_Pa": hydrostatic_Pa},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Condensate letdown basis: the pump-discharge blend, 1 bar drop, 10 m rise."""
        feed = {
            "T": 293.15,
            "P": 1.0e6,
            "molar_flow": 50.0,
            "composition": {"iC4": 0.392, "nC4": 0.248, "iC5": 0.157, "nC5": 0.203},
        }
        return {"inlet": feed}, {"dP": 1.0e5, "elevation_m": 10.0}
