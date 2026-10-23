"""The unit catalogue: unit operations as data (spec U-00).

Rows live in ``data/unit_models/*.yaml`` (schema and vocabularies in
``data/unit_models/_schema.yaml``). One row per unit of the 83-unit palette
(plan ``docs/unit-catalogue-plan.md`` §2): id, human name, family, ports, the
rigour-level ladder (R0..R3 with status, adapter, params, validation ids,
end-state flag), the legacy mode→level map, sizer, P&ID symbol and references.

``registry.discover()`` calls :func:`register_all` after the decorator-based
plugins import: every row with an implemented level registers its adapter
under the row's id. The existing ``@register("unit", ...)`` decorators stay
where they are; a test asserts the YAML implemented set equals the registered
set so the two can never drift. Roadmap-only rows (every level planned) are
allowed and skipped by registration — the palette includes future units
without adapters.

Load errors are fatal and name the file and row: duplicate ids, unknown
families/statuses, level keys off the canonical ladder order, planned levels
carrying an adapter, adapter strings that do not import, and sizer names that
do not resolve to a registered sizer plugin (``ngdesign.sizing``).
"""

from __future__ import annotations

import importlib
import os
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from ngdesign import registry
from ngdesign.units.levels import LEVEL_ORDER, resolve_level

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODELS_DIR = REPO_ROOT / "data" / "unit_models"
MODELS_DIR_ENV = "STOMATO_UNIT_MODELS_DIR"

#: The eight palette families (plan §2 U-A..U-H), fixed order for docs/tables.
FAMILIES: tuple[str, ...] = (
    "logical",
    "flow",
    "heat",
    "separation",
    "column",
    "reactors",
    "treating",
    "refining",
)

#: Implemented-level statuses, ordered experimental < provisional < validated
#: (plan §4: provisional ships with V0+V2 green; validated needs V0-V2 green).
STATUS_ORDER: tuple[str, ...] = ("experimental", "provisional", "validated")

#: Registry ids are slug-case snake_case.
_SLUG_RE = re.compile(r"[a-z0-9]+(_[a-z0-9]+)*")

#: Validation case ids are V-prefixed (data/validation_units/<family>/cases.yaml).
_VALIDATION_ID_RE = re.compile(r"V\d+")

#: Palette counts per family (plan §2); the counts test holds the catalogue to it.
PALETTE_COUNTS: dict[str, int] = {
    "logical": 9,
    "flow": 12,
    "heat": 10,
    "separation": 10,
    "column": 12,
    "reactors": 9,
    "treating": 9,
    "refining": 12,
}


class CatalogueError(ValueError):
    """A catalogue row failed to load; the message names file and row."""


class Port(BaseModel):
    """One named port of a unit's interface."""

    model_config = ConfigDict(extra="forbid")

    name: str
    required: bool = True
    description: str = ""


class Ports(BaseModel):
    """The unit's inlet and outlet port names (required/optional)."""

    model_config = ConfigDict(extra="forbid")

    inlet: tuple[Port, ...]
    outlet: tuple[Port, ...]

    @property
    def inlet_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.inlet)

    @property
    def outlet_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.outlet)


class LevelSpec(BaseModel):
    """One rigour level of a unit's ladder (plan §1)."""

    model_config = ConfigDict(extra="forbid")

    #: implemented_status: validated | provisional | experimental | planned.
    status: Literal["validated", "provisional", "experimental", "planned"]
    adapter: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    validation: tuple[str, ...] = Field(default_factory=tuple)
    end_state: bool = False
    note: str = ""

    @property
    def planned(self) -> bool:
        return self.status == "planned"


class UnitRow(BaseModel):
    """One unit operation as data (spec U-00)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    family: Literal["logical", "flow", "heat", "separation", "column", "reactors", "treating", "refining"]
    ports: Ports
    levels: dict[str, LevelSpec]
    mode_map: dict[str, str] = Field(default_factory=dict)
    sizer: str | None = None
    pid_symbol: str | None = None
    references: tuple[str, ...] = Field(default_factory=tuple)
    notes: str = ""
    source_file: str = ""
    source_row: int = 0


def _schema(dir_path: Path) -> dict[str, Any]:
    """The schema doc: families and status vocabularies the rows must use."""
    path = dir_path / "_schema.yaml"
    doc = yaml.safe_load(path.read_text())
    if not isinstance(doc, dict):
        raise CatalogueError(f"{path}: schema must be a mapping")
    return doc


def _check_adapter(adapter: str, where: str) -> type:
    """An adapter string ``module:ClassName`` must import to a class."""
    module_name, _, class_name = adapter.partition(":")
    if not module_name or not class_name:
        raise CatalogueError(f"{where}: adapter {adapter!r} must be 'module:ClassName'")
    try:
        module = importlib.import_module(module_name)
        adapter_cls = getattr(module, class_name)
    except (ImportError, AttributeError) as exc:
        raise CatalogueError(f"{where}: adapter {adapter!r} does not import: {exc}") from exc
    if not isinstance(adapter_cls, type):
        raise CatalogueError(f"{where}: adapter {adapter!r} is not a class")
    return adapter_cls


def _check_row(row: UnitRow, schema: dict[str, Any], where: str) -> None:
    """Structural rules the pydantic model cannot express positionally."""
    if not _SLUG_RE.fullmatch(row.id):
        raise CatalogueError(f"{where}: id {row.id!r} is not slug-case (lower_snake_case)")
    families = schema.get("families", [])
    if row.family not in families:
        raise CatalogueError(f"{where}: unknown family {row.family!r}; declared: {families}")
    if not row.levels:
        raise CatalogueError(f"{where}: row has no levels")
    declared = tuple(row.levels)
    canonical = tuple(level for level in LEVEL_ORDER if level in row.levels)
    if declared != canonical:
        raise CatalogueError(
            f"{where}: level keys {declared} are not in canonical order {canonical} "
            f"(ladder order: {', '.join(LEVEL_ORDER)})"
        )
    highest = declared[-1]
    for level, spec in row.levels.items():
        level_where = f"{where} level {level}"
        if spec.status == "planned":
            if spec.adapter is not None:
                raise CatalogueError(f"{level_where}: a planned level carries no adapter")
        else:
            if spec.adapter is None:
                raise CatalogueError(f"{level_where}: a {spec.status} level names an adapter")
            _check_adapter(spec.adapter, level_where)
        for case_id in spec.validation:
            if not _VALIDATION_ID_RE.match(case_id):
                raise CatalogueError(f"{level_where}: validation id {case_id!r} is not V-prefixed")
        if spec.status == "validated" and not spec.validation:
            raise CatalogueError(
                f"{level_where}: a validated level carries at least one V-prefixed validation case id"
            )
        if spec.end_state and level != highest:
            raise CatalogueError(
                f"{level_where}: end_state is only allowed on the highest declared level ({highest})"
            )
    for mode, level in row.mode_map.items():
        if level not in row.levels:
            raise CatalogueError(f"{where}: mode_map {mode!r} -> {level!r} names an undeclared level")
    if row.sizer is not None and row.sizer not in registry.available("sizer"):
        raise CatalogueError(
            f"{where}: sizer {row.sizer!r} is not a registered sizer plugin "
            f"(registered: {registry.available('sizer')})"
        )


def _load_dir(dir_path: Path) -> dict[str, UnitRow]:
    """Every ``<family>.yaml`` row file; ``_*.yaml`` files are schema/docs."""
    schema = _schema(dir_path)
    rows: dict[str, UnitRow] = {}
    for path in sorted(dir_path.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        entries = yaml.safe_load(path.read_text()) or []
        for index, entry in enumerate(entries):
            where = f"{path.name} row {index} ({entry.get('id', '?')})"
            entry = dict(entry)
            entry["source_file"] = path.name
            entry["source_row"] = index
            try:
                row = UnitRow(**entry)
            except Exception as exc:
                raise CatalogueError(f"{where}: {exc}") from exc
            _check_row(row, schema, where)
            prior = rows.get(row.id)
            if prior is not None:
                raise CatalogueError(
                    f"duplicate unit id {row.id!r}: {path.name} row {index} and "
                    f"{prior.source_file} row {prior.source_row}"
                )
            rows[row.id] = row
    return rows


def _models_dir() -> Path:
    override = os.environ.get(MODELS_DIR_ENV)
    return Path(override) if override else DEFAULT_MODELS_DIR


@cache
def load_rows() -> dict[str, UnitRow]:
    """Load and validate every catalogue row, keyed by unit id.

    Cached: tests that override :data:`MODELS_DIR_ENV` must call
    ``load_rows.cache_clear()`` around the override (try/finally).
    """
    rows = _load_dir(_models_dir())
    if not rows:
        raise CatalogueError(f"{_models_dir()}: no unit rows loaded")
    return rows


def units_catalogue() -> tuple[UnitRow, ...]:
    """Every catalogue row in palette order (family, then id) — the API/agent/
    frontend surface reads this."""
    rows = load_rows()
    family_rank = {family: rank for rank, family in enumerate(FAMILIES)}
    return tuple(sorted(rows.values(), key=lambda r: (family_rank[r.family], r.id)))


def _row_adapters(row: UnitRow) -> Mapping[str, type]:
    """Adapter class per implemented level, in canonical level order.

    Review round 2 (solve-time dispatch): a row may name a different adapter on
    each implemented level — that is the point of the rigour ladder. The
    lowest implemented level is the row's default.
    """
    adapters: dict[str, type] = {}
    where = f"catalogue row {row.id!r} ({row.source_file} row {row.source_row})"
    for level in LEVEL_ORDER:
        spec = row.levels[level] if level in row.levels else None
        if spec is not None and spec.adapter is not None:
            adapters[level] = _check_adapter(spec.adapter, f"{where}, level {level}")
    return adapters


class LevelDispatch:
    """Base class for per-row solve-time dispatch (spec U-00, review round 2).

    ``_dispatch_class`` builds one concrete subclass per implemented row. The
    registered surface is unchanged from a bare adapter: ``inlet_ports``,
    ``outlet_ports`` and ``example_case()`` come from the default (lowest
    implemented) adapter. ``solve`` resolves the level from params via
    :func:`ngdesign.units.levels.resolve_level` (``model`` key, legacy
    ``mode`` map, or the default) and delegates to that level's adapter —
    params pass through unchanged, so single-adapter rows behave exactly as
    on main.
    """

    _adapters: Mapping[str, type]
    _row_id: str
    inlet_ports: tuple[str, ...]
    outlet_ports: tuple[str, ...]

    def example_case(self) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        """The default level's example case."""
        raise NotImplementedError

    def solve(self, inlets: Mapping[str, Any], params: Mapping[str, Any], thermo: Any) -> Any:
        """Resolve the level from params and delegate to its adapter."""
        raise NotImplementedError


def _dispatch_class(row: UnitRow, adapters: Mapping[str, type]) -> type:
    """The per-row dispatch class: one registry entry, solve-time levels.

    The class SUBCLASSES the default (lowest implemented) adapter, so every
    registered instance is still an instance of that adapter class: ports,
    ``example_case()``, adapter-specific attributes (``.amine`` …) and any
    protocol ``isinstance`` checks are inherited untouched. Only ``solve``
    is overridden to resolve the level and delegate.
    """
    default = next(iter(adapters))
    adapter_cls: Any = adapters[default]

    def solve(self: Any, inlets: Mapping[str, Any], params: Mapping[str, Any], thermo: Any) -> Any:
        level = resolve_level(row, params)
        return adapters[level]().solve(inlets, params, thermo)

    return type(
        f"LevelDispatch_{row.id}",
        (adapter_cls, LevelDispatch),
        {
            "solve": solve,
            "_adapters": dict(adapters),
            "_row_id": row.id,
        },
    )


def register_all(existing: Mapping[str, type] | None = None) -> None:
    """Register every implemented catalogue row as a ``unit`` plugin.

    Called from ``registry.discover()`` after the decorator-based plugins
    import. Roadmap-only rows (all levels planned) are skipped: the 83-row
    palette includes future units without adapters. Review round 2: every
    implemented row replaces its registry entry with a per-row
    :class:`LevelDispatch` — the id stays the same, the default adapter's
    ports and example case keep the registered surface byte-identical, and
    the level resolves at solve time. Where a decorator already registered
    the same id, the dispatch still fronts it (the decorator class remains
    the default level's adapter); the registry surface is unchanged, so
    existing flowsheets and bench counts stay byte-identical.
    """
    current = dict(existing or {})
    for row in load_rows().values():
        adapters = _row_adapters(row)
        if not adapters:
            continue
        default = next(iter(adapters))
        prior = current.get(row.id)
        if prior is not None and prior is not adapters[default]:
            raise ValueError(
                f"duplicate unit plugin {row.id!r}: the registry holds {prior!r} but "
                f"catalogue {row.source_file} row {row.source_row} points at {adapters[default]!r}"
            )
        registry.replace("unit", row.id, _dispatch_class(row, adapters))
