"""Rigour-level dispatch for catalogue units (spec U-00).

Every catalogue unit carries a ladder of rigour levels (plan
``docs/unit-catalogue-plan.md`` §1): R0 base, R1 rating, R2 rigorous, R3
advanced. The level is selected by ``params["model"]`` (the P1-06
``mode="shortcut"|"staged"`` pattern generalised); legacy mode strings and the
column configurations translate through the row's ``mode_map`` without
renaming any existing parameter. A level that is not implemented refuses with
:class:`UnitLevelNotImplemented`, naming the levels that are, so callers (and
the agent) see what the unit CAN do.

Pure functions over the catalogue row; no I/O, no global state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ngdesign.units.catalogue import UnitRow

#: The rigour ladder, lowest first. The canonical order of a row's ``levels``
#: map is exactly this order.
LevelName = Literal["R0", "R1", "R2", "R3"]

LEVEL_ORDER: tuple[LevelName, ...] = ("R0", "R1", "R2", "R3")

#: Params key selecting a level by name.
MODEL_KEY = "model"

#: Legacy params key (P1-06 ``mode="shortcut"|"staged"``, column
#: configurations) translated through the row's ``mode_map``.
MODE_KEY = "mode"


class UnitLevelNotImplemented(ValueError):
    """A requested rigour level is not implemented for the unit.

    Carries the unit id, the requested level name and the implemented levels
    (lowest first). The message names the implemented levels so callers see
    what the unit can do.
    """

    def __init__(self, unit_id: str, requested: str, implemented: tuple[LevelName, ...]) -> None:
        self.unit_id = unit_id
        self.requested = requested
        self.implemented = implemented
        names = ", ".join(implemented) if implemented else "none"
        super().__init__(
            f"unit {unit_id!r}: rigour level {requested!r} is not implemented (implemented levels: {names})"
        )


def implemented_levels(row: UnitRow) -> tuple[LevelName, ...]:
    """The row's implemented levels, lowest first (``planned`` excluded)."""
    return tuple(level for level in LEVEL_ORDER if level in row.levels and not row.levels[level].planned)


def _declared(row: UnitRow) -> tuple[str, ...]:
    """The row's declared level keys, in the order declared (canonical)."""
    return tuple(row.levels)


def _select(row: UnitRow, level: str) -> LevelName:
    """A declared level that must be implemented; typed refusal otherwise."""
    spec = row.levels.get(level)
    if spec is None:
        raise ValueError(
            f"unit {row.id!r}: unknown rigour level {level!r} (declared levels: {', '.join(_declared(row))})"
        )
    if spec.planned:
        raise UnitLevelNotImplemented(row.id, level, implemented_levels(row))
    return level  # type: ignore[return-value]  # non-planned keys are LevelName by schema


def _resolve_model(row: UnitRow, params: Mapping[str, Any]) -> LevelName:
    """``params["model"]`` names a declared level directly."""
    requested = str(params[MODEL_KEY])
    return _select(row, requested)


def _resolve_mode(row: UnitRow, params: Mapping[str, Any]) -> LevelName:
    """``params["mode"]`` translates through the row's ``mode_map``.

    The legacy P1-06 ``mode="shortcut"|"staged"`` strings and the column
    configuration names map onto levels without renaming any existing
    parameter; an unmapped mode string is a ValueError naming the mapped ones.
    """
    requested = str(params[MODE_KEY])
    level = row.mode_map.get(requested)
    if level is None:
        mapped = ", ".join(row.mode_map) if row.mode_map else "none declared"
        raise ValueError(
            f"unit {row.id!r}: mode {requested!r} is not mapped to a rigour level (mode_map keys: {mapped})"
        )
    return _select(row, level)


def resolve_level(row: UnitRow, params: Mapping[str, Any]) -> LevelName:
    """The rigour level the unit solves at for these params.

    ``params["model"]`` names a declared level; ``params["mode"]`` translates
    through the row's ``mode_map``; when neither is present the unit's lowest
    implemented level is used, so every existing flowsheet keeps its current
    behaviour unchanged. A declared-but-planned selection refuses with
    :class:`UnitLevelNotImplemented` naming the implemented levels.
    """
    if MODEL_KEY in params:
        return _resolve_model(row, params)
    if MODE_KEY in params:
        return _resolve_mode(row, params)
    implemented = implemented_levels(row)
    if not implemented:
        raise UnitLevelNotImplemented(row.id, "default", implemented)
    return implemented[0]
