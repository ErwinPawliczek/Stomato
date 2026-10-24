"""Stream calculator unit plugin (spec U-A).

One inlet, one outlet: multiply the flow by ``scale``, apply ``set`` overrides
of T, P or molar_flow, then a PT flash at the final (T, P). A composition
override is renormalised and refused when any entry is negative. The reported
duty is the enthalpy change, ``n_out*h_out - n_in*h_in`` (J/s).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class StreamCalculator:
    """Copies, scales and overrides a stream (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        scale = float(params.get("scale", 1.0))
        if scale < 0.0:
            raise ValueError(f"scale must be >= 0, got {scale}")
        overrides = params.get("set") or {}
        if not isinstance(overrides, dict):
            raise ValueError("set must be a map with optional T, P, molar_flow, composition keys")

        flow = inlet.molar_flow * scale
        composition = dict(inlet.composition)
        if "composition" in overrides:
            requested = overrides["composition"]
            if any(float(x) < 0.0 for x in requested.values()):
                negative = [cid for cid, x in requested.items() if float(x) < 0.0]
                raise ValueError(f"composition override has negative entries: {negative}")
            total = sum(float(x) for x in requested.values())
            if total <= 0.0:
                raise ValueError("composition override sums to zero; nothing to renormalise")
            composition = {cid: float(x) / total for cid, x in requested.items()}

        T = float(overrides["T"]) if "T" in overrides else inlet.T
        P = float(overrides["P"]) if "P" in overrides else inlet.P
        for name, value in (("T", T), ("P", P)):
            if value <= 0.0:
                raise ValueError(f"set.{name} must be > 0, got {value}")

        flow = float(overrides["molar_flow"]) if "molar_flow" in overrides else flow
        if flow < 0.0:
            raise ValueError(f"set.molar_flow must be >= 0, got {flow}")

        if flow <= 0.0:
            outlet = inlet.model_copy(
                update={"T": T, "P": P, "molar_flow": 0.0, "composition": composition}
            )
        else:
            outlet = thermo.flash_pt(composition, T, P, flow)
        duty = outlet.molar_flow * outlet.enthalpy - inlet.molar_flow * inlet.enthalpy
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty, power_W=0.0, info={})

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Set the dry-gas example temperature (scale 1 keeps the balance closed;
        the locked V0 property test requires the example case to conserve moles)."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return (
            {"inlet": dry_gas_feed(322.15, 7.0e6)},
            {"scale": 1.0, "set": {"T": 300.0}},
        )
