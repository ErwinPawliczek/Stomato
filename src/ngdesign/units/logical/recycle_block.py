"""Recycle block unit plugin (spec U-A).

A pass-through identity at R0. Its declarative meaning — mark the tear stream
and set its acceleration options — is applied by
``ngdesign.solver.lowering.lower_logical_nodes`` before the solve; the unit
itself changes nothing.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class RecycleBlock:
    """Identity pass-through with per-block tear options (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del thermo, params  # identity: options are consumed by the lowering hook
        inlet = inlets["inlet"]
        return UnitResult(
            outlets={"outlet": inlet.model_copy(composition=dict(inlet.composition))},
            duty_W=0.0,
            power_W=0.0,
            info={},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Identity: the dry-gas example passes through untouched."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return {"inlet": dry_gas_feed(322.15, 7.0e6)}, {"acceleration": "wegstein"}
