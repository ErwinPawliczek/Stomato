"""Catalogue tests: the 83-row palette loads and matches the registry (U-00).

The catalogue is data, so most tests walk every row. The palette counts and
the registry equivalence are the load-bearing invariants: a family file edited
without updating the palette, or an adapter registered outside the catalogue,
fails here.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from ngdesign import registry
from ngdesign.units import catalogue
from ngdesign.units.catalogue import PALETTE_COUNTS, UnitRow, load_rows
from ngdesign.units.levels import (
    LEVEL_ORDER,
    UnitLevelNotImplemented,
    implemented_levels,
    resolve_level,
)

_SLUG_RE = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")
_VALIDATION_ID_RE = re.compile(r"V\d+")


@pytest.fixture(name="rows", scope="module")
def rows_fixture() -> dict[str, UnitRow]:
    """The loaded catalogue. Module-scoped: load_rows() caches anyway."""
    registry.discover()
    # Annotated assignment: functools.cache erases the return type for mypy.
    rows: dict[str, UnitRow] = load_rows()
    return rows


def _implemented(rows: dict[str, UnitRow]) -> tuple[UnitRow, ...]:
    """Rows with at least one implemented level."""
    return tuple(row for row in rows.values() if implemented_levels(row))


def test_family_counts_match_palette(rows: dict[str, UnitRow]) -> None:
    assert Counter(row.family for row in rows.values()) == Counter(PALETTE_COUNTS)


def test_implemented_rows_registered(rows: dict[str, UnitRow]) -> None:
    """Every implemented row's adapter is registered under the row's id."""
    registered = set(registry.available("unit"))
    for row in _implemented(rows):
        assert row.id in registered, f"implemented row {row.id!r} is not registered"


def test_registered_units_catalogued(rows: dict[str, UnitRow]) -> None:
    """Every registered unit id is an implemented catalogue row."""
    registered = set(registry.available("unit"))
    catalogued = {row.id for row in _implemented(rows)}
    assert registered == catalogued


def test_ids_slug_case(rows: dict[str, UnitRow]) -> None:
    for row_id in rows:
        assert _SLUG_RE.fullmatch(row_id), f"unit id {row_id!r} is not slug-case"


def test_ids_unique(rows: dict[str, UnitRow]) -> None:
    ids = [row.id for row in rows.values()]
    assert len(ids) == len(set(ids))


def test_validated_levels_carry_validation_ids(rows: dict[str, UnitRow]) -> None:
    """A validated level must name its V-prefixed validation cases."""
    for row in rows.values():
        for level, spec in row.levels.items():
            if spec.status != "validated":
                continue
            assert spec.validation, f"{row.id}/{level}: validated without validation cases"
            for case_id in spec.validation:
                assert _VALIDATION_ID_RE.fullmatch(case_id), (
                    f"{row.id}/{level}: validation id {case_id!r} is not V-prefixed"
                )


def test_planned_levels_have_no_adapter(rows: dict[str, UnitRow]) -> None:
    for row in rows.values():
        for level, spec in row.levels.items():
            if spec.planned:
                assert spec.adapter is None, f"{row.id}/{level}: planned level carries an adapter"


def test_level_keys_in_canonical_order(rows: dict[str, UnitRow]) -> None:
    """A row's declared levels follow the rigour ladder order."""
    order: dict[str, int] = {level: index for index, level in enumerate(LEVEL_ORDER)}
    for row in rows.values():
        declared = list(row.levels)
        assert [order[level] for level in declared] == sorted(order[level] for level in declared), (
            f"{row.id}: level keys {declared} are not in canonical order"
        )


def test_sizers_point_at_registered_plugins(rows: dict[str, UnitRow]) -> None:
    registered = set(registry.available("sizer"))
    for row in rows.values():
        if row.sizer is not None:
            assert row.sizer in registered, f"{row.id}: sizer {row.sizer!r} is not registered"


def test_every_row_has_levels(rows: dict[str, UnitRow]) -> None:
    for row in rows.values():
        assert row.levels, f"{row.id}: no levels declared"


def test_roadmap_rows_refuse(rows: dict[str, UnitRow]) -> None:
    """Roadmap-only rows refuse the default selection, naming themselves."""
    for row in rows.values():
        if implemented_levels(row):
            continue
        with pytest.raises(UnitLevelNotImplemented, match=row.id):
            resolve_level(row, {})


def test_v1_case_files_exist_for_every_family(rows: dict[str, UnitRow]) -> None:
    for family in PALETTE_COUNTS:
        path = Path("data") / "validation_units" / family / "cases.yaml"
        assert path.is_file(), f"missing V1 case file for family {family!r}"


def test_duplicate_id_across_files_raises_catalogue_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same id in two family files is a load error, not a silent overwrite."""
    schema = Path("data") / "unit_models" / "_schema.yaml"
    logical = Path("data") / "unit_models" / "logical.yaml"
    (tmp_path / schema.name).write_text(schema.read_text())
    (tmp_path / "a.yaml").write_text(logical.read_text())
    (tmp_path / "b.yaml").write_text(logical.read_text())

    monkeypatch.setenv(catalogue.MODELS_DIR_ENV, str(tmp_path))
    catalogue.load_rows.cache_clear()
    try:
        with pytest.raises(catalogue.CatalogueError, match="duplicate unit id"):
            load_rows()
    finally:
        catalogue.load_rows.cache_clear()
