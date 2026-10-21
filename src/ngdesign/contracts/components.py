"""Open component registry records (specs P1-02, P1-07).

``Component`` is the one provenance-graded identity for anything a stream can
carry: a curated slate species, any ``chemicals``-databank species (CAS or name
keyed), or a user pseudo-component characterized by Tb + sg. ``PseudoDefinition``
is the flowsheet-owned pseudo characterization (spec P1-07): a slate entry may be
a plain id or a full definition, so the flowsheet is the unit of ownership and a
saved project carries its own pseudo definitions. ``ComponentSet`` is an ordered,
id-unique collection - the per-flowsheet slate the solver indexes tear vectors by
and the thermo packages build EOS constants from - and keeps the definitions that
produced its pseudo records so the packages never re-resolve them globally.

The resolution engine (curated yaml -> chemicals databank -> pseudo-components,
with the Lee-Kesler / Riazi-Daubert correlations) lives in ``ngdesign.data`` -
the lowest import layer, which may not import contracts. The typed adapters
``resolve`` / ``resolve_set`` live here, next to the records they build
(contracts over data is the established direction).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Literal

from pydantic import model_validator

import ngdesign.data as data
from ngdesign.data import PseudoDefinition as DataPseudoDefinition

from .common import Model


class Component(Model):
    """One simulatable species with its constants (SI) and per-property provenance."""

    id: str  # user-facing short id, e.g. "C1", "n-heptane", "C7+"
    name: str
    cas: str | None  # None for pseudo-components
    formula: str | None
    mw: float  # g/mol
    Tc: float  # K
    Pc: float  # Pa
    omega: float  # acentric factor, -
    Tb: float | None  # K, normal boiling point
    sg: float | None  # specific gravity, water = 1
    kind: Literal["databank", "curated", "pseudo"]
    provenance: dict[str, str]  # property -> source string, e.g. {"Tc": "chemicals"}


class PseudoDefinition(Model):
    """A flowsheet-owned pseudo-component characterization (spec P1-07).

    The Tb + sg pair drives the Lee-Kesler / Riazi-Daubert correlations; each of
    ``mw`` / ``Tc`` / ``Pc`` / ``omega`` may be overridden explicitly, and every
    override carries its own provenance note in ``provenance``. A pseudo id may
    not shadow a curated id (the Flowsheet validator rejects it).
    """

    id: str
    name: str
    Tb: float  # K, normal boiling point
    sg: float  # specific gravity, water = 1
    mw: float | None = None  # g/mol override
    Tc: float | None = None  # K override
    Pc: float | None = None  # Pa override
    omega: float | None = None  # acentric factor override
    provenance: dict[str, str] = {}  # per-override note, e.g. {"Tc": "lab PVT cell"}

    @model_validator(mode="after")
    def _overrides(self) -> PseudoDefinition:
        if self.Tb <= 0.0 or self.sg <= 0.0:
            raise ValueError(f"pseudo-component {self.id!r} needs positive Tb and sg")
        for prop in ("mw", "Tc", "Pc", "omega"):
            if getattr(self, prop) is not None and prop not in self.provenance:
                raise ValueError(f"pseudo-component {self.id!r}: override {prop!r} needs a provenance note")
        return self


#: One slate entry: a plain component id (curated, databank or registered pseudo)
#: or a pseudo-component the flowsheet owns and carries with itself.
ComponentRef = str | PseudoDefinition


class ComponentSet(Model):
    """An ordered collection of Components with unique ids (a flowsheet's slate).

    ``pseudo_definitions`` keeps the flowsheet-owned definitions (spec P1-07)
    that produced the ``pseudo`` records, so the thermo packages build flasher
    constants from the slate's own characterizations instead of re-resolving
    them through the module-level register_pseudo default.
    """

    components: list[Component]
    pseudo_definitions: tuple[PseudoDefinition, ...] = ()

    @model_validator(mode="after")
    def _unique_ids(self) -> ComponentSet:
        ids = [c.id for c in self.components]
        if len(ids) != len(set(ids)):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate component ids {duplicates}")
        return self

    @property
    def ids(self) -> tuple[str, ...]:
        """The component ids, in slate order (tear-vector indexing uses this order)."""
        return tuple(c.id for c in self.components)

    def index(self, cid: str) -> int:
        """Position of one component id in the slate; KeyError when absent."""
        for i, component in enumerate(self.components):
            if component.id == cid:
                return i
        raise KeyError(cid)


def data_definition(definition: PseudoDefinition) -> DataPseudoDefinition:
    """Convert a contract pseudo definition into its data-layer record (hashable)."""
    return DataPseudoDefinition(
        id=definition.id,
        name=definition.name,
        Tb=definition.Tb,
        sg=definition.sg,
        mw=definition.mw,
        Tc=definition.Tc,
        Pc=definition.Pc,
        omega=definition.omega,
        provenance=tuple(sorted(definition.provenance.items())),
    )


def data_definitions(definitions: Iterable[PseudoDefinition]) -> tuple[DataPseudoDefinition, ...]:
    """The data-layer forms of flowsheet-owned definitions, id-sorted (cache-key order)."""
    return tuple(sorted((data_definition(d) for d in definitions), key=lambda d: d.id))


def pseudo_definitions(refs: Iterable[ComponentRef]) -> tuple[PseudoDefinition, ...]:
    """The flowsheet-owned pseudo definitions among slate refs, id-sorted."""
    return tuple(sorted((r for r in refs if isinstance(r, PseudoDefinition)), key=lambda d: d.id))


def resolve(
    id_or_cas_or_name: str, *, pseudos: Mapping[str, DataPseudoDefinition] | None = None
) -> Component:
    """Resolve a curated id, CAS number, databank name, or pseudo id.

    ``pseudos`` is the flowsheet's own slate context (spec P1-07); without it,
    resolution consults the module-level register_pseudo default.
    """
    return Component(**data.component_record(id_or_cas_or_name, pseudos=pseudos))


def resolve_set(refs: Iterable[ComponentRef]) -> ComponentSet:
    """Resolve an ordered component slate; duplicates and unresolvable ids raise.

    Pseudo-definition entries resolve through the flowsheet's own definitions
    (spec P1-07); string entries keep the spec P1-02 resolution order - a
    slate-owned definition shadows the registered default for its id, while
    pseudo ids the slate does not own read the module-level register_pseudo
    default.
    """
    refs = list(refs)
    owned = {d.id: d for d in pseudo_definitions(refs)}
    pseudo_context = {pid: data_definition(d) for pid, d in owned.items()} or None
    return ComponentSet(
        components=[resolve(ref if isinstance(ref, str) else ref.id, pseudos=pseudo_context) for ref in refs],
        pseudo_definitions=tuple(owned.values()),
    )
