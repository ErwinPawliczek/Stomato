"""Component splitter unit plugin (spec U-A).

R0 method: ``units._physics.splitting.split_by_component`` — per-component
split fractions, each outlet flashed at its own (outlet_T, outlet_P), which
default to the inlet's T and P. The duty is reported:
``sum(n*h) over outlets - n_in*h_in`` (J/s).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.splitting import OutletSpec, split_by_component


def _to_top_bottom(spec: OutletSpec) -> OutletSpec:
    """Map port-named outlet specs onto the helper's top/bottom keys."""
    if isinstance(spec, Mapping):
        out: dict[str, float] = {}
        for key, value in spec.items():
            mapped = {"outlet_1": "top", "outlet_2": "bottom"}.get(key, key)
            if mapped not in ("top", "bottom"):
                raise ValueError(f"outlet spec key {key!r}: expected 'outlet_1' or 'outlet_2'")
            out[mapped] = float(value)
        return out
    return spec


class ComponentSplitter:
    """Sends each component to outlet_1 by its own fraction; the rest go to
    outlet_2 (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet_1", "outlet_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        fractions = params["fractions"]
        if not isinstance(fractions, Mapping) or not fractions:
            raise ValueError("fractions: a non-empty map of cid -> fraction is required")
        top, bottom = split_by_component(
            inlet,
            fractions,
            thermo,
            _to_top_bottom(params.get("outlet_T")),
            _to_top_bottom(params.get("outlet_P")),
        )
        duty = top.molar_flow * top.enthalpy + bottom.molar_flow * bottom.enthalpy
        duty -= inlet.molar_flow * inlet.enthalpy
        return UnitResult(outlets={"outlet_1": top, "outlet_2": bottom}, duty_W=duty, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Feed split: methane to outlet_1, the C4s to outlet_2."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return (
            {"inlet": dry_gas_feed(322.15, 7.0e6)},
            {"fractions": {"C1": 1.0, "nC4": 0.0}},
        )
