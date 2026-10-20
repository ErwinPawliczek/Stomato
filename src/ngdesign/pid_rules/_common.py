"""Helpers shared by the P&ID rules (spec P0-05)."""

from __future__ import annotations

from ngdesign.contracts import Nozzle, PidEquipment

__all__ = ["psv_nozzle"]


def psv_nozzle(eq: PidEquipment) -> Nozzle | None:
    """The vessel's psv nozzle, or None (nozzles are owned by the sizers)."""
    return next((n for n in eq.nozzles if n.service == "psv"), None)
