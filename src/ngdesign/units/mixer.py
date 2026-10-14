"""Mixer unit plugin (spec S-28).

Plugin kind "unit", name "mixer".

Method (spec): ports inlet_1..inlet_3 (unused ports may be zero-flow) -> outlet
at the minimum inlet pressure, with the flow-weighted composition and the
enthalpy-weighted flash_ph. No duty, no power.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units.jt_valve import dry_gas_feed


@register("unit", "mixer")
class Mixer:
    """Combines up to three inlet streams at the lowest inlet pressure (spec S-28)."""

    inlet_ports = ("inlet_1", "inlet_2", "inlet_3")
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del params  # mixer has no params; kept for the UnitModel signature
        active = [s for s in inlets.values() if s.molar_flow > 0.0]
        if not active:  # all ports zero-flow: no flash possible or needed
            reference = next(iter(inlets.values()))
            zero = reference.model_copy(
                update={"molar_flow": 0.0, "composition": dict(reference.composition)}
            )
            return UnitResult(outlets={"outlet": zero}, duty_W=0.0, power_W=0.0, info={})

        total = sum(s.molar_flow for s in active)
        P_out = min(s.P for s in active)
        z: dict[str, float] = {}
        for s in active:
            for cid, x in s.composition.items():
                z[cid] = z.get(cid, 0.0) + x * s.molar_flow
        composition = {cid: n / total for cid, n in z.items()}
        h_mix = sum(s.enthalpy * s.molar_flow for s in active) / total

        outlet = thermo.flash_ph(composition, P_out, h_mix, total)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Two dry-gas streams at different states merged; inlet_3 zero-flow.

        Zero flow on inlet_3 exercises the spec's "unused ports may be
        zero-flow" rule.
        """
        feeds = {
            "inlet_1": dry_gas_feed(322.15, 7.0e6),
            "inlet_2": dry_gas_feed(293.15, 5.0e6),
            "inlet_3": {**dry_gas_feed(293.15, 5.0e6), "molar_flow": 0.0},
        }
        return feeds, {}
