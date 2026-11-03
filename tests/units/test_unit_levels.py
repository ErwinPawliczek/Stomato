"""Level-dispatch tests: model/mode selection and honest refusals (U-00).

``resolve_level`` is the dispatch contract every flowsheet solve goes through:
``params["model"]`` names a declared level, ``params["mode"]`` translates via
the row's mode map, and an absent selection falls back to the lowest
implemented level so existing flowsheets keep their behaviour unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from ngdesign.units.levels import (
    LEVEL_ORDER,
    LevelName,
    UnitLevelNotImplemented,
    implemented_levels,
    resolve_level,
)

if TYPE_CHECKING:
    from ngdesign.units.catalogue import UnitRow


@pytest.fixture(name="rows", scope="module")
def rows_fixture() -> dict[str, UnitRow]:
    from ngdesign.units.catalogue import load_rows

    # Annotated assignment: functools.cache erases the return type for mypy.
    rows: dict[str, UnitRow] = load_rows()
    return rows


def test_model_param_selects_the_level(rows: dict[str, UnitRow]) -> None:
    assert resolve_level(rows["pump"], {"model": "R0"}) == "R0"
    assert resolve_level(rows["column"], {"model": "R2"}) == "R2"


def test_missing_model_falls_back_to_lowest_implemented(rows: dict[str, UnitRow]) -> None:
    for row in rows.values():
        levels = implemented_levels(row)
        if not levels:
            continue
        assert resolve_level(row, {}) == levels[0]


def test_unknown_model_raises_value_error(rows: dict[str, UnitRow]) -> None:
    with pytest.raises(ValueError, match="unknown rigour level"):
        resolve_level(rows["pump"], {"model": "R9"})


def test_planned_level_refuses_and_names_the_implemented_levels(
    rows: dict[str, UnitRow],
) -> None:
    # any row with both kinds of level, so closing a level cannot break this test;
    # once every such row is implemented, a live row with two implemented levels
    # has its top level re-declared planned (resolve_level reads only the levels).
    row = next(
        (
            r
            for r in rows.values()
            if any(spec.planned for spec in r.levels.values())
            and not all(s.planned for s in r.levels.values())
        ),
        None,
    )
    if row is None:
        base = next(r for r in rows.values() if len(implemented_levels(r)) >= 2)
        top = implemented_levels(base)[-1]
        levels = dict(base.levels)
        levels[top] = levels[top].model_copy(update={"status": "planned", "adapter": None})
        row = base.model_copy(update={"levels": levels})
    planned = next(level for level, spec in row.levels.items() if spec.planned)
    implemented = tuple(level for level, spec in row.levels.items() if not spec.planned)
    with pytest.raises(UnitLevelNotImplemented) as excinfo:
        resolve_level(row, {"model": planned})
    error = excinfo.value
    assert error.unit_id == row.id
    assert error.requested == planned
    assert error.implemented == implemented
    assert implemented[0] in str(error)


def test_end_state_only_on_the_highest_declared_level(rows: dict[str, UnitRow]) -> None:
    order: dict[str, int] = {level: index for index, level in enumerate(LEVEL_ORDER)}
    for row in rows.values():
        highest = max(order[level] for level in row.levels)
        for level, spec in row.levels.items():
            if spec.end_state:
                assert order[level] == highest, f"{row.id}/{level}: end_state below the top level"


def test_implemented_levels_ordered_lowest_first(rows: dict[str, UnitRow]) -> None:
    order = {level: index for index, level in enumerate(LEVEL_ORDER)}
    for row in rows.values():
        levels = implemented_levels(row)
        assert [order[level] for level in levels] == sorted(order[level] for level in levels)


def test_mode_translates_via_mode_map(rows: dict[str, UnitRow]) -> None:
    """The legacy P1-06/column mode strings reach the same level as model=."""
    level: LevelName = resolve_level(rows["column"], {"mode": "distillation"})
    assert level == "R2"
    assert level == resolve_level(rows["column"], {"model": "R2"})


def test_unmapped_mode_raises_value_error(rows: dict[str, UnitRow]) -> None:
    with pytest.raises(ValueError, match="not mapped"):
        resolve_level(rows["column"], {"mode": "bogus"})


@pytest.mark.xfail(
    reason="staged amine/TEG models land with P1-11 and S1; the planned R2 refuses today",
    strict=False,
)
@pytest.mark.parametrize("unit_id", ["mdea_absorber", "mdea_regenerator", "teg_contactor"])
def test_future_staged_dispatch(rows: dict[str, UnitRow], unit_id: str) -> None:
    assert resolve_level(rows[unit_id], {"model": "R2"}) == "R2"
