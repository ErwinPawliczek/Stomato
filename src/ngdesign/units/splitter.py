"""Splitter unit plugin (spec S-28).

Plugin kind "unit", name "splitter".

Method (spec): ports inlet -> outlet_1, outlet_2; param fractions [f1, f2]
summing to 1. Both outlets share the inlet's T, P and composition at their
scaled flows. No flash, no duty, no power.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register

_FRACTION_TOL = 1e-9


@register("unit", "splitter")
class Splitter:
    """Splits a stream into two by mole fraction (spec S-28)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet_1", "outlet_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del thermo  # no flash needed; kept for the UnitModel signature
        inlet = inlets["inlet"]
        fractions = params["fractions"]
        if len(fractions) != 2:
            raise ValueError(f"fractions must have 2 entries, got {len(fractions)}")
        f1, f2 = (float(f) for f in fractions)
        if not all(0.0 <= f <= 1.0 for f in (f1, f2)):
            raise ValueError(f"fractions {fractions} outside [0, 1]")
        if abs(f1 + f2 - 1.0) > _FRACTION_TOL:
            raise ValueError(f"fractions {fractions} do not sum to 1")

        outlets = {
            "outlet_1": inlet.model_copy(update={"molar_flow": inlet.molar_flow * f1}),
            "outlet_2": inlet.model_copy(
                update={"molar_flow": inlet.molar_flow * f2, "composition": dict(inlet.composition)}
            ),
        }
        return UnitResult(outlets=outlets, duty_W=0.0, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Slice gas split 60/40; state is copied, so any feed works."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return {"inlet": dry_gas_feed(322.15, 7.0e6)}, {"fractions": [0.6, 0.4]}
