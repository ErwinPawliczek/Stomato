"""The thermo catalogue: property methods as data (spec T-01).

Rows live in ``data/thermo_models/*.yaml`` (schema and vocabularies in
``data/thermo_models/_schema.yaml``). Each row names an adapter class
(``module:ClassName``), typed options, parameters provenance, an applicability
window, a status, the P1-05 case ids that validate it, and the L0
self-consistency parameters the validation harness runs
(``scripts/validate_properties.py``).

``registry.discover()`` calls :func:`register_all` after the decorator-based
plugins import: every row becomes a ``thermo`` plugin factory keyed by its id.
The dynamic import in the registry is the only seam — a static
``registry -> thermo.catalogue`` import would violate the layer contract
(``.importlinter``), and ignore_imports lines are not allowed.

Load errors are fatal and name the file and row: duplicate ids, unknown
families/statuses/component classes/phases, unknown adapters, and option
values outside the typed declarations (``ngdesign.thermo.options``). A row
declaring a non-default cubic option loads (the vocabulary admits it) but
:func:`build` raises :class:`NotImplementedError` naming the option until
T-02 lands the implementation.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping
from functools import cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.thermo.options import AlphaFunction, EnthalpyMethod, VolumeTranslation

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODELS_DIR = REPO_ROOT / "data" / "thermo_models"
MODELS_DIR_ENV = "STOMATO_THERMO_MODELS_DIR"


class CatalogueError(ValueError):
    """A catalogue row failed to load; the message names file and row."""


class CubicOptions(BaseModel):
    """Typed options for family ``cubic`` (values declared in thermo.options)."""

    model_config = ConfigDict(extra="forbid")

    eos: str
    kij_table: str
    alpha: AlphaFunction = AlphaFunction.DEFAULT
    translation: VolumeTranslation = VolumeTranslation.NONE
    enthalpy: EnthalpyMethod = EnthalpyMethod.EOS


class HelmholtzOptions(BaseModel):
    """Typed options for family ``helmholtz`` (spec T-04)."""

    model_config = ConfigDict(extra="forbid")

    #: IAPWSPackage steam-table formulation (iapws_if97 row selects "IF97").
    formulation: Literal["IAPWS95", "IF97"] = "IAPWS95"


class Applicability(BaseModel):
    """Model-validity window (Carlson, Chem. Eng. Prog. 92(10), 35, 1996)."""

    component_classes: list[str]
    polar: bool
    electrolyte: bool
    T_K: tuple[float, float]
    P_Pa: tuple[float, float]
    phases: list[str]


class ModelRow(BaseModel):
    """One property method as data (spec T-01)."""

    id: str
    name: str
    family: str
    adapter: str
    options: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    applicability: Applicability
    status: str
    validation: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    l0: dict[str, Any] = Field(default_factory=dict)
    l0_excluded: dict[str, str] = Field(default_factory=dict)
    l0_note: str = ""
    source_file: str = ""
    source_row: int = 0


def models_dir() -> Path:
    """Directory the catalogue loads from (overridable for tests)."""
    return Path(os.environ.get(MODELS_DIR_ENV, str(DEFAULT_MODELS_DIR)))


def _import_adapter(row: ModelRow, where: str) -> type:
    """Resolve ``row.adapter`` ("module:ClassName") to a class."""
    module_name, _, attr = row.adapter.partition(":")
    if not module_name or not attr:
        raise CatalogueError(f"{where}: adapter {row.adapter!r} must be 'module:ClassName'")
    try:
        module = importlib.import_module(module_name)
        adapter = getattr(module, attr)
    except (ImportError, AttributeError) as exc:
        raise CatalogueError(f"{where}: unknown adapter {row.adapter!r}: {exc}") from exc
    if not isinstance(adapter, type):
        raise CatalogueError(f"{where}: adapter {row.adapter!r} is not a class")
    return adapter


def _validate_options(row: ModelRow, where: str) -> None:
    """Validate options against the typed declarations; cross-check pinned eos."""
    try:
        if row.family == "cubic":
            opts = CubicOptions(**row.options)
            adapter = _import_adapter(row, where)
            pinned = getattr(adapter, "eos", None)
            eos_name = getattr(pinned, "__name__", None)
            if eos_name != opts.eos:
                raise CatalogueError(
                    f"{where}: options.eos {opts.eos!r} does not match adapter "
                    f"{row.adapter!r} (pins {eos_name!r})"
                )
        elif row.family == "helmholtz":
            HelmholtzOptions(**row.options)
        elif row.options:
            raise CatalogueError(
                f"{where}: no typed options are declared for family {row.family!r} yet "
                f"(T-02/T-03 add them); got {sorted(row.options)}"
            )
    except ValidationError as exc:
        raise CatalogueError(f"{where}: unknown or invalid option value: {exc}") from exc


def _validate_vocab(row: ModelRow, where: str, schema: dict[str, Any]) -> None:
    """Check row vocabulary against _schema.yaml."""
    for field, key in (
        ("family", "families"),
        ("status", "statuses"),
    ):
        if getattr(row, field) not in set(schema[key]):
            raise CatalogueError(
                f"{where}: unknown {field} {getattr(row, field)!r}; have {sorted(schema[key])}"
            )
    bad_classes = sorted(set(row.applicability.component_classes) - set(schema["component_classes"]))
    if bad_classes:
        raise CatalogueError(
            f"{where}: unknown component classes {bad_classes}; have {sorted(schema['component_classes'])}"
        )
    bad_phases = sorted(set(row.applicability.phases) - set(schema["phases"]))
    if bad_phases:
        raise CatalogueError(f"{where}: unknown phases {bad_phases}; have {sorted(schema['phases'])}")


@cache
def _load_dir(dir_path: str) -> dict[str, ModelRow]:
    """Load and validate every row under ``dir_path``; key is the stringified path."""
    root = Path(dir_path)
    schema_path = root / "_schema.yaml"
    if not schema_path.exists():
        raise CatalogueError(f"missing thermo catalogue schema: {schema_path}")
    schema = cast(dict[str, Any], yaml.safe_load(schema_path.read_text()))
    rows: dict[str, ModelRow] = {}
    for path in sorted(root.glob("*.yaml")):
        if path.name == "_schema.yaml":
            continue
        entries = yaml.safe_load(path.read_text()) or []
        for index, entry in enumerate(entries):
            where = f"{path.name} row {index}"
            try:
                row = ModelRow(**entry, source_file=path.name, source_row=index)
            except ValidationError as exc:
                raise CatalogueError(f"invalid thermo catalogue row at {where}: {exc}") from exc
            if row.id in rows:
                raise CatalogueError(
                    f"{where}: duplicate thermo catalogue id {row.id!r} "
                    f"(already defined in {rows[row.id].source_file} row {rows[row.id].source_row})"
                )
            # L0 parameters are owned per FAMILY (``l0_defaults`` in _schema.yaml); a row
            # lists only what differs. Merging here means every consumer (the harness,
            # describe()) sees the full check set without 25 cubic rows repeating it.
            family_l0 = dict(schema.get("l0_defaults", {}).get(row.family, {}))
            row = row.model_copy(update={"l0": {**family_l0, **row.l0}})
            _validate_vocab(row, where, schema)
            _validate_options(row, where)
            rows[row.id] = row
    return rows


def load_catalogue() -> dict[str, ModelRow]:
    """Load every row from the models dir (cached per directory)."""
    return _load_dir(str(models_dir()))


def describe(model_id: str) -> ModelRow:
    """Return the row for ``model_id`` or raise a KeyError naming the catalogue."""
    rows = load_catalogue()
    try:
        return rows[model_id]
    except KeyError:
        raise KeyError(f"no thermo catalogue row {model_id!r}; have {sorted(rows)}") from None


def build(row: ModelRow, *args: Any, **kwargs: Any) -> Thermo:
    """Construct the row's package, enforcing non-default option declarations."""
    adapter = _import_adapter(row, f"catalogue row {row.id!r}")
    if row.family == "cubic":
        opts = CubicOptions(**row.options)
        pending = [
            f"{field}={getattr(opts, field).value}"
            for field in ("alpha", "translation", "enthalpy")
            if getattr(opts, field) != _CUBIC_DEFAULTS[field]
        ]
        if pending:
            raise NotImplementedError(
                f"catalogue row {row.id!r} declares non-default cubic options "
                f"[{', '.join(pending)}]; the implementations land with T-02"
            )
    elif row.family == "helmholtz":
        hopts = HelmholtzOptions(**row.options)
        if hopts.formulation != _HELMHOLTZ_DEFAULTS["formulation"]:
            kwargs = {**kwargs, "formulation": hopts.formulation}
    return cast(Thermo, adapter(*args, **kwargs))


_CUBIC_DEFAULTS: dict[str, AlphaFunction | VolumeTranslation | EnthalpyMethod] = {
    "alpha": AlphaFunction.DEFAULT,
    "translation": VolumeTranslation.NONE,
    "enthalpy": EnthalpyMethod.EOS,
}

_HELMHOLTZ_DEFAULTS: dict[str, str] = {"formulation": "IAPWS95"}


def _has_nondefault_options(row: ModelRow) -> bool:
    """True when the row declares options other than the T-02/T-04 defaults."""
    if row.family == "cubic":
        opts = CubicOptions(**row.options)
        return any(
            getattr(opts, field) != _CUBIC_DEFAULTS[field] for field in ("alpha", "translation", "enthalpy")
        )
    if row.family == "helmholtz":
        hopts = HelmholtzOptions(**row.options)
        return bool(hopts.formulation != _HELMHOLTZ_DEFAULTS["formulation"])
    return False


def _factory(row: ModelRow) -> Callable[..., Thermo]:
    """Factory registered under the row's id; validates options on each build."""

    def make(*args: Any, **kwargs: Any) -> Thermo:
        return build(row, *args, **kwargs)

    make.__name__ = f"catalogue_factory_{row.id}"
    make.__qualname__ = make.__name__
    make.__doc__ = f"Factory for thermo catalogue row {row.id!r} ({row.name})."
    return make


def register_all(existing: Mapping[str, type] | None = None) -> None:
    """Register every catalogue row as a ``thermo`` plugin factory.

    Called from ``registry.discover()`` after decorator-based plugins import.
    Rows whose id a decorator already registered with the SAME class (the amine
    packages, until P1-09/#125 lands) are tolerated: the class registration
    stays and the catalogue row carries the metadata. TODO(#125): once PR #125
    merges, move the amine ``@register`` decorators into catalogue rows here,
    exactly like pr/srk/pr78/nrtl.
    """
    current = dict(existing or {})
    for row in load_catalogue().values():
        adapter = _import_adapter(row, f"catalogue row {row.id!r}")
        prior = current.get(row.id)
        if prior is not None:
            if prior is not adapter:
                raise ValueError(
                    f"duplicate thermo plugin {row.id!r}: the registry holds {prior!r} "
                    f"but catalogue {row.source_file} row {row.source_row} points at {adapter!r}"
                )
            continue
        # All-default rows register the adapter class itself: a class is a callable
        # factory that builds the package, and registry.get(id) must return the same
        # object the pre-catalogue decorators registered (locked contract tests assert
        # identity). Only rows declaring non-default options get a validating closure.
        factory = adapter if not _has_nondefault_options(row) else cast(type, _factory(row))
        registry.register("thermo", row.id)(factory)
