"""Filter (plan §2 U-D 7, spec U-D).

Plugin kind "unit", name "filter" — registered from the catalogue YAML; no
decorator (round-1 conventions).

R0 method (spec): ``splitting.split_by_component`` with ``cake_fractions``
(the fraction of each solid-like component's molar flow sent to the cake;
components missing from the map go entirely to the filtrate) and ``dP``
applied to the filtrate outlet (the cake leaves at the inlet pressure — the
cake sits on the feed side of the medium). Closed-form only at R0 per spec
U-D; cake-resistance physics is R1.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.splitting import split_by_component


class FilterSpecError(ValueError):
    """The filter spec is bad; the message names the parameter."""


class Filter:
    """Per-component split spec between cake and filtrate."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("filtrate", "cake")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        cake_fractions = params.get("cake_fractions")
        if not isinstance(cake_fractions, dict) or not cake_fractions:
            raise FilterSpecError(
                "cake_fractions is required: a non-empty map of component id to cake fraction"
            )
        unknown = [cid for cid in cake_fractions if cid not in inlet.composition]
        if unknown:
            raise FilterSpecError(f"cake_fractions names component(s) {unknown} not in the feed")
        bad = {cid: f for cid, f in cake_fractions.items() if not 0.0 <= float(f) <= 1.0}
        if bad:
            raise FilterSpecError(f"cake_fractions entries {bad} outside [0, 1]")
        dP = float(params.get("dP", 0.0))
        if dP < 0:
            raise FilterSpecError(f"dP {dP} must be >= 0")
        if inlet.P - dP <= 0:
            raise FilterSpecError(f"dP {dP} leaves a non-positive filtrate pressure")

        # The helper sends each component's ``fractions`` share to the first
        # (top) outlet: the cake. Unnamed components pass to the filtrate.
        cake, filtrate = split_by_component(
            inlet,
            {cid: float(f) for cid, f in cake_fractions.items()},
            thermo,
            outlet_P={"top": inlet.P, "bottom": inlet.P - dP},
        )
        outlets = {"filtrate": filtrate, "cake": cake}
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(outlets=outlets, duty_W=h_out_W - h_in_W, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slurry of water with 2 mol % silica: all solids to the cake.

        SiO2 is the solid-like component (``cake_fractions = {"SiO2": 1.0}``);
        the 3e4 Pa dP is the example's filtrate-side spec, not a correlation
        constant.
        """
        return {
            "inlet": {
                "T": 298.15,
                "P": 3.0e5,
                "molar_flow": 200.0,
                "composition": {"H2O": 0.98, "SiO2": 0.02},
            }
        }, {"cake_fractions": {"SiO2": 1.0}, "dP": 3.0e4}
