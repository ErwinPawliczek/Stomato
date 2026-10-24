"""Three-phase separator and scrubber unit plugins (spec S-24).

Plugin kind "unit", names "separator_3phase" and "scrubber".

Splits a feed at inlet conditions (spec-outlet pressure drop dP applied):
PT flash at (T_in, P_in - dP), then each outlet carries its equilibrium
phase(s) from that flash as they are (no re-flash at the same state). An absent phase gives a
zero-flow outlet carrying the inlet composition (StreamState requires a valid
composition). duty_W = sum(H_out * F) - H_in * F_in, ~0 for dP = 0.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Phase, PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S


def _phase_outlet(
    inlet: StreamState,
    T: float,
    P: float,
    phases: list[Phase],
) -> StreamState:
    """One outlet built from the parent flash's equilibrium phase(s) at (T, P).

    The phases are already the package's equilibrium result at this (T, P), so
    the outlet carries them as they are (mole fractions renormalised to the
    outlet, enthalpy and entropy flow-weighted), instead of re-flashing each
    phase's composition: a re-flash at the same state is redundant and, for a
    phase sitting on its own dew or bubble point, slow and liable to split off
    a spurious trace phase. The scrubber's liquid outlet carries both liquids.
    An absent phase gives a zero-flow outlet with the inlet composition.
    """
    total = sum(p.mole_fraction for p in phases)
    if total <= 0.0:
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
    own = [
        p.model_copy(update={"mole_fraction": p.mole_fraction / total})
        for p in phases
        if p.mole_fraction > 0.0
    ]
    cids = {cid for p in own for cid in p.composition}
    composition = {cid: sum(p.mole_fraction * p.composition.get(cid, 0.0) for p in own) for cid in cids}
    return StreamState(
        T=T,
        P=P,
        molar_flow=total * inlet.molar_flow,
        composition=composition,
        vapor_fraction=sum(p.mole_fraction for p in own if p.kind is PhaseKind.VAPOR),
        enthalpy=sum(p.mole_fraction * p.enthalpy for p in own),
        entropy=sum(p.mole_fraction * p.entropy for p in own),
        phases=own,
    )


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
                phases = [p for p in flashed.phases if p.kind is not PhaseKind.VAPOR]
            else:
                phases = [p for p in flashed.phases if p.kind is kind]
            outlets[port] = _phase_outlet(inlet, T, P, phases)

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
