"""Shared helpers for the separation-family R0 adapters (spec U-D).

Pure functions over the ``Thermo`` protocol; nothing here registers a plugin.
The outlet-construction helpers follow the existing separator pattern
(``ngdesign.units.separator``): every phase outlet is produced with
``thermo.flash_pt`` on its own composition and flow; an absent phase gives a
zero-flow outlet carrying the reference composition (a ``StreamState`` needs a
valid composition).
"""

from __future__ import annotations

from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo


def zero_flow_outlet(reference: StreamState, T: float, P: float) -> StreamState:
    """A zero-flow outlet at (T, P) carrying the reference composition."""
    return StreamState(
        T=T,
        P=P,
        molar_flow=0.0,
        composition=dict(reference.composition),
        vapor_fraction=0.0,
        enthalpy=reference.enthalpy,
        entropy=reference.entropy,
        phases=[],
    )


def phase_outlet(
    thermo: Thermo,
    reference: StreamState,
    T: float,
    P: float,
    phase: Phase | None,
) -> StreamState:
    """Re-flash one phase at (T, P) with its own composition and flow.

    An absent (or zero-fraction) phase gives a zero-flow outlet at (T, P).
    """
    if phase is None or phase.mole_fraction <= 0.0:
        return zero_flow_outlet(reference, T, P)
    return thermo.flash_pt(phase.composition, T, P, phase.mole_fraction * reference.molar_flow)


def combined_liquid(phases: list[Phase]) -> Phase | None:
    """Flow-weighted combined liquid from the non-vapour phases (or None)."""
    liquids = [p for p in phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        return None
    total = sum(p.mole_fraction for p in liquids)
    composition = {
        cid: sum(p.mole_fraction * p.composition[cid] for p in liquids) / total
        for cid in liquids[0].composition
    }
    return liquids[0].model_copy(update={"mole_fraction": total, "composition": composition})


def stream_molar_mass(composition: dict[str, float]) -> float:
    """Mean molar mass of a composition, g/mol, from the component database."""
    from ngdesign.data import components

    db = components()
    return sum(x * float(db[cid]["mw"]) for cid, x in composition.items())
