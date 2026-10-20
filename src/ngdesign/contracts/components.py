"""Open component registry records (spec P1-02).

``Component`` is the one provenance-graded identity for anything a stream can
carry: a curated slate species, any ``chemicals``-databank species (CAS or name
keyed), or a user pseudo-component characterized by Tb + sg. ``ComponentSet`` is
an ordered, id-unique collection - the per-flowsheet slate the solver indexes
tear vectors by and the thermo packages build EOS constants from.

The resolution engine (curated yaml -> chemicals databank -> registered
pseudo-components, with the Lee-Kesler / Riazi-Daubert correlations) lives in
``ngdesign.data`` - the lowest import layer, which may not import contracts. The
typed adapters ``resolve`` / ``resolve_set`` live here, next to the records they
build (contracts over data is the established direction).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import model_validator

from ngdesign.data import component_record

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


class ComponentSet(Model):
    """An ordered collection of Components with unique ids (a flowsheet's slate)."""

    components: list[Component]

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


def resolve(id_or_cas_or_name: str) -> Component:
    """Resolve a curated id, CAS number, databank name, or registered pseudo id."""
    return Component(**component_record(id_or_cas_or_name))


def resolve_set(ids: Iterable[str]) -> ComponentSet:
    """Resolve an ordered component slate; duplicates and unresolvable ids raise."""
    return ComponentSet(components=[resolve(id_) for id_ in ids])
