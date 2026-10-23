"""Catalogue tests: the 83-row palette loads and matches the registry (U-00).

The catalogue is data, so most tests walk every row. The palette counts and
the registry equivalence are the load-bearing invariants: a family file edited
without updating the palette, or an adapter registered outside the catalogue,
fails here.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from ngdesign import registry
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.plugins import Thermo
from ngdesign.units import catalogue
from ngdesign.units.catalogue import (
    PALETTE_COUNTS,
    UnitRow,
    _row_adapters,
    load_rows,
)
from ngdesign.units.levels import (
    LEVEL_ORDER,
    UnitLevelNotImplemented,
    implemented_levels,
    resolve_level,
)
from tests.conftest import flash_feed

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


# --- solve-time level dispatch (review round 2, item 1) ----------------------


def test_implemented_rows_register_a_dispatch(rows: dict[str, UnitRow]) -> None:
    """Every implemented row's registry entry is a per-row LevelDispatch whose
    example case and ports are the default (lowest implemented) level's."""
    for row in _implemented(rows):
        entry = registry.get("unit", row.id)
        assert issubclass(entry, catalogue.LevelDispatch), f"{row.id}: registry entry is not a LevelDispatch"
        adapters: dict[str, Any] = dict(_row_adapters(row))
        default = next(iter(adapters))
        assert entry.inlet_ports == adapters[default].inlet_ports
        assert entry.outlet_ports == adapters[default].outlet_ports
        assert entry().example_case() == adapters[default].example_case()


def test_planned_level_refuses_through_a_flowsheet_solve(thermo: Thermo) -> None:
    """params={"model": "R1"} on pump (R1 planned) refuses in the solve path,
    not only through resolve_level: the solver records the typed error."""
    fs = Flowsheet(
        name="pump-R1-refusal",
        units=[UnitSpec(tag="P-100", kind="pump", params={"model": "R1"})],
        streams=[
            StreamSpec(
                id="F-001",
                target=PortRef(unit="P-100", port="inlet"),
                service="PL",
                feed=FeedSpec(T=293.15, P=1.0e6, molar_flow=10.0, composition={"H2O": 1.0}),
            )
        ],
    )
    solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)
    unit_errors = [e for e in solved.errors if e.tag == "P-100"]
    assert unit_errors, "the planned-level refusal never reached the solve path"
    error = unit_errors[0]
    assert error.error_type == "UnitLevelNotImplemented"
    assert error.stage == "solve"
    assert "R0" in error.message  # names the levels the unit CAN do


def _fixture_catalogue(tmp_path: Path) -> Path:
    """A copy of the catalogue with pump R1 implemented on a second adapter."""
    dst = tmp_path / "unit_models"
    shutil.copytree(Path("data") / "unit_models", dst)
    flow = yaml.safe_load((dst / "flow.yaml").read_text())
    for row in flow:
        if row["id"] == "pump":
            row["levels"]["R1"] = {
                "status": "experimental",
                "adapter": "ngdesign.units.mixer:Mixer",
                "params": {},
                "note": "test fixture: stand-in second adapter",
                "end_state": True,
            }
    (dst / "flow.yaml").write_text(yaml.safe_dump(flow, sort_keys=False))
    return dst


def test_two_implemented_levels_dispatch_to_their_adapters(
    thermo: Thermo, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row with two implemented levels solves each level's own adapter through
    the registry entry (test-only fixture catalogue via STOMATO_UNIT_MODELS_DIR)."""
    monkeypatch.setenv(catalogue.MODELS_DIR_ENV, str(_fixture_catalogue(tmp_path)))
    catalogue.load_rows.cache_clear()
    try:
        catalogue.register_all()  # rebuild the dispatch classes from the fixture
        dispatch = registry.get("unit", "pump")
        assert issubclass(dispatch, catalogue.LevelDispatch)
        row = load_rows()["pump"]
        adapters: dict[str, Any] = dict(_row_adapters(row))
        assert set(adapters) == {"R0", "R1"}

        unit = dispatch()
        feeds, params = unit.example_case()
        assert params == adapters["R0"].example_case()[1]  # default = lowest level
        inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}

        r0 = unit.solve(inlets, {**params, "model": "R0"}, thermo)
        r1 = unit.solve(inlets, {"model": "R1"}, thermo)
        assert r0.outlets["outlet"].P > inlets["inlet"].P  # the pump raised pressure
        assert r1.outlets["outlet"].P == inlets["inlet"].P  # the mixer held it
    finally:
        catalogue.load_rows.cache_clear()
        catalogue.register_all()  # restore the real dispatch classes
        catalogue.load_rows.cache_clear()


def test_legacy_mode_params_reach_the_same_code_paths(thermo: Thermo) -> None:
    """Legacy mode strings pass through the dispatch unchanged: solving through
    the registry entry is byte-identical to solving the bare adapter class
    directly (main's path) for every mapped mode."""
    row = load_rows()["column"]
    dispatch: Any = registry.get("unit", "column")
    feeds, params = dispatch.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    for mode, level in row.mode_map.items():
        mode_params: dict[str, Any] = {**params, "mode": mode}
        via_dispatch = dispatch().solve(inlets, dict(mode_params), thermo)
        direct = _row_adapters(row)[level]().solve(inlets, dict(mode_params), thermo)
        assert _dump_result(via_dispatch) == _dump_result(direct), f"mode {mode!r} drifted"


# --- bench flowsheets through the dispatcher (review round 2, item 3) --------


def _dump_stream(s: Any) -> dict[str, Any]:
    """Full float-exact state dump: repr strings round-trip byte-identically."""
    return {
        "T": repr(s.T),
        "P": repr(s.P),
        "molar_flow": repr(s.molar_flow),
        "vapor_fraction": repr(s.vapor_fraction),
        "enthalpy": repr(s.enthalpy),
        "entropy": repr(s.entropy),
        "composition": {c: repr(v) for c, v in sorted(s.composition.items())},
    }


def _dump_result(result: Any) -> dict[str, Any]:
    """SolvedFlowsheet or bare UnitResult, byte-identically serialised."""
    if hasattr(result, "streams"):
        return {
            "converged": result.converged,
            "iterations": result.iterations,
            "streams": {sid: _dump_stream(st) for sid, st in sorted(result.streams.items())},
            "units": {
                tag: {"duty_W": repr(r.duty_W), "power_W": repr(r.power_W)}
                for tag, r in sorted(result.units.items())
            },
        }
    return {
        "duty_W": repr(result.duty_W),
        "power_W": repr(result.power_W),
        "outlets": {port: _dump_stream(s) for port, s in sorted(result.outlets.items())},
    }


def test_bench_flowsheets_byte_identical_through_dispatch(thermo: Thermo) -> None:
    """The dispatcher sits in the bench solve path (registry.create -> dispatch
    -> adapter); every bench case reproduces main's results byte-identically.

    The golden (tests/units/bench_dispatch_golden.json) was generated on
    origin/main — the same commit this branch is based on — by solving
    scripts.bench_baseline.CASES and dumping _dump_result() JSON.
    """
    from scripts.bench_baseline import CASES

    golden = json.loads((Path(__file__).parent / "bench_dispatch_golden.json").read_text())
    assert set(golden) == set(CASES)
    for name in sorted(CASES):
        result = CASES[name](thermo)
        assert _dump_result(result) == golden[name], f"{name} drifted from main's results"
