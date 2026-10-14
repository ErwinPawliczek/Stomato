"""Three-phase separator and scrubber unit plugins (spec S-24).

Plugin kind "unit", names "separator_3phase" and "scrubber".

Splits a feed at inlet conditions (spec-outlet pressure drop dP applied):
PT flash at (T_in, P_in - dP), then each outlet is its phase re-flashed at the
same T and P with its own composition and molar flow. An absent phase gives a
zero-flow outlet carrying the inlet composition (StreamState requires a valid
composition). duty_W = sum(H_out * F) - H_in * F_in, ~0 for dP = 0.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Phase, PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets.slice import INLET_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.registry import register


def _combined_liquid(phases: list[Phase]) -> Phase | None:
    """Flow-weighted combined liquid (hc_liquid + aqueous) for the scrubber variant."""
    liquids = [p for p in phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        return None
    total = sum(p.mole_fraction for p in liquids)
    composition = {
        cid: sum(p.mole_fraction * p.composition[cid] for p in liquids) / total
        for cid in liquids[0].composition
    }
    return liquids[0].model_copy(update={"mole_fraction": total, "composition": composition})


def _phase_outlet(
    thermo: Thermo,
    inlet: StreamState,
    T: float,
    P: float,
    phase: Phase | None,
) -> StreamState:
    """Re-flash one phase at (T, P) with its own composition and flow.

    An absent phase gives a zero-flow outlet with the inlet composition.
    """
    if phase is None or phase.mole_fraction <= 0.0:
        return StreamState(
            T=T,
            P=P,
            molar_flow=0.0,
            composition=dict(inlet.composition),
            vapor_fraction=0.0,
            enthalpy=inlet.enthalpy,
            entropy=inlet.entropy,
            phases=[],
        )
    return thermo.flash_pt(phase.composition, T, P, phase.mole_fraction * inlet.molar_flow)


class _SeparatorBase:
    """Shared PT-flash phase-split logic; subclasses map phases to ports."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ()
    _kind_by_port: dict[str, PhaseKind | None] = {}

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        dP = float(params.get("dP", 0.0))
        if dP < 0:
            raise ValueError("dP must be >= 0")
        T, P = inlet.T, inlet.P - dP
        if P <= 0:
            raise ValueError(f"dP {dP} leaves a non-positive outlet pressure")

        flashed = thermo.flash_pt(inlet.composition, T, P, inlet.molar_flow)

        outlets: dict[str, StreamState] = {}
        for port, kind in self._kind_by_port.items():
            if kind is None:  # scrubber: combined liquid
                phase = _combined_liquid(flashed.phases)
            else:
                phase = next((p for p in flashed.phases if p.kind is kind), None)
            outlets[port] = _phase_outlet(thermo, inlet, T, P, phase)

        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info={},
        )


@register("unit", "separator_3phase")
class Separator3Phase(_SeparatorBase):
    """Three-phase separator: gas, hydrocarbon liquid and free water (spec S-24)."""

    outlet_ports = ("gas_out", "hc_out", "water_out")
    _kind_by_port = {
        "gas_out": PhaseKind.VAPOR,
        "hc_out": PhaseKind.HC_LIQUID,
        "water_out": PhaseKind.AQUEOUS,
    }

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        feed = {
            "T": 293.15,
            "P": 3.447e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": dict(INLET_COMPOSITION),
        }
        return {"inlet": feed}, {}  # slice inlet feed, dP = 0


@register("unit", "scrubber")
class Scrubber(_SeparatorBase):
    """Two-phase scrubber variant: gas out, combined liquid out (spec S-24)."""

    outlet_ports = ("gas_out", "liquid_out")
    _kind_by_port = {
        "gas_out": PhaseKind.VAPOR,
        "liquid_out": None,
    }

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        return Separator3Phase.example_case()
