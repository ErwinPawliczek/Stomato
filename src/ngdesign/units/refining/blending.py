"""``blender`` adapter (spec U-H1).

Product blender at rigour R0: an isothermal, no-pressure-drop component mixer.
All ``n`` inlets are pooled into one ``blend_out`` stream at ``T`` (default:
the first inlet's temperature) and the inlet pressure. This is the R0 shape of
Gary et al. §12 blending: volume-weighted property reporting rather than any
correlation-based RON/octane model. ``info`` carries each inlet's contribution
as a percentage of the blend's reference volume.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float
from ngdesign.units.refining.slate import reference_volume


@register("unit", "blending")
class Blender:
    """Pool product streams into one blend stream isothermally."""

    inlet_ports: tuple[str, ...] = (
        "component_in_1",
        "component_in_2",
        "component_in_3",
    )
    outlet_ports: tuple[str, ...] = ("blend_out",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Naphtha, kerosene and gas oil drawn from the example crude-column cut."""
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        feeds = {
            "component_in_1": {
                "T": 288.15,
                "P": 1.0e5,
                "molar_flow": 300.0,
                "composition": dict(mole),
            },
            "component_in_2": {
                "T": 288.15,
                "P": 1.0e5,
                "molar_flow": 200.0,
                "composition": dict(mole),
            },
            "component_in_3": {
                "T": 288.15,
                "P": 1.0e5,
                "molar_flow": 100.0,
                "composition": dict(mole),
            },
        }
        return feeds, {"T": 288.15}

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Pool all inlets into one stream, flashed isothermally at (T, P)."""
        if not inlets:
            raise RefiningSpecError("blend_in_*: at least one inlet stream is required")
        first = next(iter(inlets.values()))
        t_out = optional_float(params, "T", first.T)
        p_out = optional_float(params, "P", first.P)
        if p_out <= 0.0:
            raise RefiningSpecError("P: must be positive")

        # Component mole flows pooled across every inlet.
        flows: dict[str, float] = {}
        total = 0.0
        for port, stream in inlets.items():
            if port not in self.inlet_ports:
                raise RefiningSpecError(f"{port}: not a declared blender inlet port")
            for cid, x in stream.composition.items():
                n = x * stream.molar_flow
                flows[cid] = flows.get(cid, 0.0) + n
            total += stream.molar_flow
        composition = {cid: n / total for cid, n in flows.items() if n > 0.0}
        blend = thermo.flash_pt(composition, t_out, p_out, total)

        blend_vol = reference_volume(blend)
        info: dict[str, float] = {}
        for port, stream in inlets.items():
            stream_vol = reference_volume(stream)
            info[f"{port}_vol_pct"] = 100.0 * stream_vol / blend_vol if blend_vol else 0.0
        info["volume_m3_s"] = blend_vol
        duty = blend.enthalpy * blend.molar_flow - sum(s.enthalpy * s.molar_flow for s in inlets.values())
        return UnitResult(outlets={"blend_out": blend}, duty_W=duty, power_W=0.0, info=info)
