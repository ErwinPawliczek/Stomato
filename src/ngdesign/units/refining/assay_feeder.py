"""``assay_feeder`` adapter (spec U-H1).

Feeds a stored crude assay as a stream: the inlet composition must be exactly
the declared assay's A-01 slate, and the outlet is that slate re-flashed at
the requested ``T`` and ``P``. ``info`` carries the reference-volume flow, the
API gravity and the light-ends / pseudo volume splits.

The API gravity is the volume-weighted ``sg`` of the whole slate from the
component data bank (light ends plus pseudos); the light-ends volume split
uses the same reference-volume basis.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.registry import register
from ngdesign.units.refining._cuts import RefiningSpecError, require_float
from ngdesign.units.refining.slate import (
    WATER_60F_KG_M3,
    api_gravity,
    assay_slate,
    component_volume,
    reference_volume,
    register_slate,
)

#: Light ends the A-01 cutter recognises (Table 2 ids of the stored assays).
_LIGHT_ENDS = frozenset({"H2O", "C2", "C3", "iC4", "nC4", "iC5", "nC5"})

#: Tolerance on the inlet-vs-slate mole fraction comparison (mol/mol).
_COMPOSITION_TOL = 1e-9

_EXAMPLE_ASSAY = "bagajewicz_ji_2001_light"


class AssayFeeder:
    """Convert a declared assay slate into a stream (one inlet, one outlet)."""

    inlet_ports: tuple[str, ...] = ("assay_in",)
    outlet_ports: tuple[str, ...] = ("cuts_out",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The stored Bagajewicz & Ji (2001) light crude at 15 degC, 1 bar."""
        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        feeds = {
            "assay_in": {
                "T": 288.15,
                "P": 101325.0,
                "molar_flow": 1000.0,
                "composition": dict(mole),
            }
        }
        return feeds, {"assay_id": _EXAMPLE_ASSAY, "T": 288.15, "P": 101325.0}

    def solve(
        self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo
    ) -> UnitResult:
        """Flash the slate at ``(T, P)``; duty is the enthalpy change of the slate."""
        assay_id = params.get("assay_id")
        if not isinstance(assay_id, str):
            raise RefiningSpecError("assay_id: a string assay id is required")
        t_out = require_float(params, "T")
        p_out = require_float(params, "P")
        _, mole = assay_slate(assay_id)
        feed = inlets.get("assay_in")
        if feed is None:
            raise RefiningSpecError("assay_in: the assay inlet stream is required")
        if set(feed.composition) != set(mole):
            raise RefiningSpecError(
                f"assay_in: composition keys do not match the {assay_id!r} slate"
            )
        for cid, x in mole.items():
            if abs(feed.composition.get(cid, 0.0) - x) > _COMPOSITION_TOL:
                raise RefiningSpecError(
                    f"assay_in: mole fraction of {cid} does not match the "
                    f"{assay_id!r} slate"
                )
        outlet = thermo.flash_pt(mole, t_out, p_out, feed.molar_flow)
        return UnitResult(
            outlets={"cuts_out": outlet},
            duty_W=outlet.enthalpy * outlet.molar_flow - feed.enthalpy * feed.molar_flow,
            power_W=0.0,
            info=self._info(outlet, mole),
        )

    def _info(self, outlet: StreamState, mole: dict[str, float]) -> dict[str, float]:
        """Reference volume flow, API gravity and light-ends split of the slate."""
        total_vol = reference_volume(outlet)
        light_ends_vol = sum(
            component_volume(outlet, cid) for cid in mole if cid in _LIGHT_ENDS
        )
        # Mixture sg on the additive reference-volume basis: the weight-fraction
        # harmonic mean of the component sg values.
        weight = 0.0
        volume = 0.0
        for cid, x in mole.items():
            record = component_record(cid)
            w = x * record["mw"]
            weight += w
            volume += w / record["sg"]
        sg = weight / volume if volume else 1.0
        return {
            "volume_m3_s": total_vol,
            "api_gravity": api_gravity(sg),
            "light_ends_vol_pct": 100.0 * light_ends_vol / total_vol,
            "pseudos_vol_pct": 100.0 * (1.0 - light_ends_vol / total_vol),
        }
