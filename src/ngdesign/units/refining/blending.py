"""``blender`` adapter (spec U-H1).

Product blender at rigour R0: an **adiabatic** component mixer plus property
indices from per-inlet params. All ``n`` inlets are pooled into one
``blend_out`` stream at the blend pressure ``P``; the outlet temperature comes
from a PH flash of the pooled enthalpy (``thermo.flash_ph``), so ``duty_W`` is
0 and the mixer adds no heat (the mixer convention: one owner of mixing
physics, no isothermal re-set of T).

Property indices (inlet streams carry no octane/RVP — they come in as params,
keyed by inlet port under ``properties``):

- **RVP** — the Chevron/GHK blending index ``RVP_mix**1.25 = Σ v_i·RVP_i**1.25``
  on a reference-volume basis (Gary, Handwerk & Kaiser, *Petroleum Refining:
  Technology and Economics*, 5th ed., CRC 2007, ch. 12 "Product Blending",
  Reid vapor pressure section; method and component values cross-read from
  Jechura, "Product Blending & Optimization Considerations", CBEN 409,
  Colorado School of Mines, 2019).
- **Sulfur** — linear on a **mass** basis (same source: sulfur blends by
  wt% / ppm on mass).
- **Octane (RON)** — linear by **volume**: the documented R0 simplification.
  Real octane blending is interactive (blending values differ per pool); the
  linear-by-volume rule is the book's simple first cut and is reported as-is.
- **Cetane index** — linear by volume (same R0 simplification).
- **D86 point** — volume-average temperature of the inlets that declare one
  (R0 simplification per spec U-H1; no D86 distillation back-blending).

An index is reported only when every nonzero-volume inlet declares it.
``info`` also carries each inlet's contribution as a percentage of the blend's
reference volume.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float
from ngdesign.units.refining.slate import reference_volume

#: Exponent of the GHK/Chevron RVP blending index.
_RVP_EXPONENT = 1.25


class Blender:
    """Pool product streams into one blend stream adiabatically, with indices."""

    inlet_ports: tuple[str, ...] = (
        "component_in_1",
        "component_in_2",
        "component_in_3",
    )
    outlet_ports: tuple[str, ...] = ("blend_out",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Naphtha, kerosene and gas-oil cuts of the example crude column.

        Draw temperatures are the paper's product withdrawal temperatures
        (Bagajewicz & Ji 2001, Table 6, one-pump-around column: condenser
        43.3 degC, kerosene 237.1 degC, gas oil 338.7 degC). Property params:
        the naphtha cut carries the published LSR values of Gary, Handwerk &
        Kaiser Table 12.1 (RVP 11.1 psi, RON 66.4, via Jechura's CBEN 409
        notes); the kerosene/gas-oil entries are illustrative scenario inputs,
        with gas-oil D86 at the paper's Table 4 gas-oil spec point (377 degC).
        """
        from ngdesign.data import component_record
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        light: dict[str, float] = {}
        middle: dict[str, float] = {}
        heavy: dict[str, float] = {}
        for cid, x in mole.items():
            tb = float(component_record(cid).get("Tb", 0.0))
            if tb < 462.5:
                light[cid] = light.get(cid, 0.0) + x
            elif tb < 614.5:
                middle[cid] = middle.get(cid, 0.0) + x
            else:
                heavy[cid] = heavy.get(cid, 0.0) + x

        def _normalized(cuts: dict[str, float]) -> dict[str, float]:
            total = sum(cuts.values())
            return {cid: x / total for cid, x in cuts.items()}

        feeds = {
            "component_in_1": {
                "T": 316.45,
                "P": 4.0e5,
                "molar_flow": 300.0,
                "composition": _normalized(light),
            },
            "component_in_2": {
                "T": 510.25,
                "P": 4.0e5,
                "molar_flow": 200.0,
                "composition": _normalized(middle),
            },
            "component_in_3": {
                "T": 611.85,
                "P": 4.0e5,
                "molar_flow": 100.0,
                "composition": _normalized(heavy),
            },
        }
        params = {
            "P": 4.0e5,
            "properties": {
                "component_in_1": {
                    "rvp_psi": 11.1,
                    "ron": 66.4,
                    "sulfur_wt_ppm": 150.0,
                    "d86_point_k": 455.15,
                },
                "component_in_2": {
                    "rvp_psi": 1.0,
                    "ron": 50.0,
                    "sulfur_wt_ppm": 50.0,
                    "d86_point_k": 544.15,
                },
                "component_in_3": {
                    "rvp_psi": 0.0,
                    "ron": 30.0,
                    "sulfur_wt_ppm": 500.0,
                    "d86_point_k": 650.15,
                },
            },
        }
        return feeds, params

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Pool all inlets with a PH flash (duty 0) and blend the property indices."""
        if not inlets:
            raise RefiningSpecError("blend_in_*: at least one inlet stream is required")
        undeclared = set(inlets) - set(self.inlet_ports)
        if undeclared:
            raise RefiningSpecError(f"blending: undeclared inlet port(s) {sorted(undeclared)}")
        first = next(iter(inlets.values()))
        p_out = optional_float(params, "P", first.P)
        if p_out <= 0.0:
            raise RefiningSpecError("P: must be positive")
        properties = params.get("properties", {})
        if not isinstance(properties, dict):
            raise RefiningSpecError("properties: must be a mapping of inlet port to property values")

        # Component mole flows pooled across every inlet.
        flows: dict[str, float] = {}
        total = 0.0
        enthalpy_total = 0.0
        for stream in inlets.values():
            for cid, x in stream.composition.items():
                flows[cid] = flows.get(cid, 0.0) + x * stream.molar_flow
            total += stream.molar_flow
            enthalpy_total += stream.enthalpy * stream.molar_flow
        if total <= 0.0:
            raise RefiningSpecError("blending: at least one inlet must carry flow")
        composition = {cid: n / total for cid, n in flows.items() if n > 0.0}
        # Adiabatic mixing: the pooled molar enthalpy sets the outlet temperature.
        blend = thermo.flash_ph(composition, p_out, enthalpy_total / total, total)

        blend_vol = reference_volume(blend)
        info: dict[str, float] = {}
        for port, stream in inlets.items():
            stream_vol = reference_volume(stream)
            info[f"{port}_vol_pct"] = 100.0 * stream_vol / blend_vol if blend_vol else 0.0
        info["volume_m3_s"] = blend_vol
        info.update(self._indices(inlets, properties))
        return UnitResult(outlets={"blend_out": blend}, duty_W=0.0, power_W=0.0, info=info)

    def _indices(self, inlets: dict[str, StreamState], properties: dict[str, Any]) -> dict[str, float]:
        """RVP (GHK index), sulfur (mass), RON/cetane (volume), D86 (volume T)."""
        volumes: dict[str, float] = {}
        masses: dict[str, float] = {}
        for port, stream in inlets.items():
            volumes[port] = reference_volume(stream)
            masses[port] = sum(
                x * stream.molar_flow * component_mw(cid) for cid, x in stream.composition.items()
            )
        out: dict[str, float] = {}
        # RVP: (Σ v_i RVP_i^1.25 / Σ v_i)^(1/1.25) over every flowing inlet.
        rvp_values = _per_port(properties, "rvp_psi", volumes)
        if rvp_values is not None:
            vol = sum(volumes[p] for p in rvp_values)
            index = sum(volumes[p] * rvp_values[p] ** _RVP_EXPONENT for p in rvp_values) / vol if vol else 0.0
            out["rvp_psi"] = index ** (1.0 / _RVP_EXPONENT)
        # Sulfur: mass-weighted.
        sulfur = _per_port(properties, "sulfur_wt_ppm", masses)
        if sulfur is not None:
            mass = sum(masses[p] for p in sulfur)
            out["sulfur_wt_ppm"] = sum(masses[p] * sulfur[p] for p in sulfur) / mass if mass else 0.0
        # RON / cetane: volume-weighted (documented R0 simplification).
        for name in ("ron", "cetane_index"):
            values = _per_port(properties, name, volumes)
            if values is not None:
                vol = sum(volumes[p] for p in values)
                out[name] = sum(volumes[p] * values[p] for p in values) / vol if vol else 0.0
        # D86 point: volume-average temperature (documented R0 simplification).
        d86 = _per_port(properties, "d86_point_k", volumes)
        if d86 is not None:
            vol = sum(volumes[p] for p in d86)
            out["d86_point_k"] = sum(volumes[p] * d86[p] for p in d86) / vol if vol else 0.0
        return out


def _per_port(
    properties: dict[str, Any],
    key: str,
    weights: dict[str, float],
) -> dict[str, float] | None:
    """Values of one property for every flowing inlet that declares it.

    ``None`` when any flowing inlet omits the property (the index is then not
    reported) or when no inlet flows.
    """
    values: dict[str, float] = {}
    for port, weight in weights.items():
        if weight <= 0.0:
            continue
        entry = properties.get(port, {})
        if not isinstance(entry, dict) or key not in entry:
            return None
        value = entry[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RefiningSpecError(f"properties[{port!r}][{key}]: a number is required")
        values[port] = float(value)
    return values or None


def component_mw(cid: str) -> float:
    """Molecular weight of ``cid`` through the component record (g/mol)."""
    from ngdesign.data import component_record

    return float(component_record(cid)["mw"])
