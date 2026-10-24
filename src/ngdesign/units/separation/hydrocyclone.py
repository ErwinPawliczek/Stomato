"""Hydrocyclone / cyclone (plan §2 U-D 6, spec U-D).

Plugin kind "unit", name "hydrocyclone" — registered from the catalogue YAML;
no decorator (round-1 conventions).

R0 method (spec): ``splitting.split_by_component`` with per-component
``underflow_fractions`` (the fraction of each component's molar flow sent to
the underflow; components missing from the map go entirely to the overflow)
and ``dP`` applied to the overflow outlet (the underflow leaves at the inlet
pressure). Deoiling example: ``underflow_fractions = {"H2O": 0.95}`` sends
95 % of the water to the coarse underflow while the oil reports to the
overflow. Closed-form only at R0: the Perry Sect. 18 cut-size example is an
R1 oracle (spec U-D).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.splitting import split_by_component


class HydrocycloneSpecError(ValueError):
    """The hydrocyclone spec is bad; the message names the parameter."""


class Hydrocyclone:
    """Per-component split spec between overflow and underflow."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("overflow", "underflow")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        underflow_fractions = params.get("underflow_fractions")
        if not isinstance(underflow_fractions, dict) or not underflow_fractions:
            raise HydrocycloneSpecError(
                "underflow_fractions is required: a non-empty map of component id to underflow fraction"
            )
        unknown = [cid for cid in underflow_fractions if cid not in inlet.composition]
        if unknown:
            raise HydrocycloneSpecError(f"underflow_fractions names component(s) {unknown} not in the feed")
        bad = {cid: f for cid, f in underflow_fractions.items() if not 0.0 <= float(f) <= 1.0}
        if bad:
            raise HydrocycloneSpecError(f"underflow_fractions entries {bad} outside [0, 1]")
        dP = float(params.get("dP", 0.0))
        if dP < 0:
            raise HydrocycloneSpecError(f"dP {dP} must be >= 0")
        if inlet.P - dP <= 0:
            raise HydrocycloneSpecError(f"dP {dP} leaves a non-positive overflow pressure")

        # The helper sends each component's ``fractions`` share to the first
        # (top) outlet and unnamed components entirely to the second, so the
        # underflow spec enters as 1 - u for every feed component (unnamed =
        # 0 to the underflow, i.e. the whole flow on the overflow).
        top_fractions = {cid: 1.0 - float(underflow_fractions.get(cid, 0.0)) for cid in inlet.composition}
        overflow, underflow = split_by_component(
            inlet,
            top_fractions,
            thermo,
            outlet_P={"top": inlet.P - dP, "bottom": inlet.P},
        )
        outlets = {"overflow": overflow, "underflow": underflow}
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(outlets=outlets, duty_W=h_out_W - h_in_W, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Deoiling produced water: 95 % of the water to the underflow.

        A 50 °C / 0.5 MPa water-continuous feed with 5 % oil (as nC5);
        ``underflow_fractions = {"H2O": 0.95}`` is the spec, not a correlation
        constant — Perry's cut-size correlation is R1 (spec U-D).
        """
        return {
            "inlet": {
                "T": 323.15,
                "P": 5.0e5,
                "molar_flow": 500.0,
                "composition": {"H2O": 0.95, "nC5": 0.05},
            }
        }, {"underflow_fractions": {"H2O": 0.95}, "dP": 2.0e4}
