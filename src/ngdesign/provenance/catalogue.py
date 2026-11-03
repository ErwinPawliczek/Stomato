"""Method catalogue and method-key citations (data/provenance/*.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml

from ngdesign.data import DATA_DIR
from ngdesign.provenance.model import Citation

_DIR = DATA_DIR / "provenance"


@dataclass(frozen=True, slots=True)
class MethodEntry:
    key: str
    name: str
    latex: str | None
    references: tuple[Citation, ...]
    structural: bool


@cache
def methods() -> dict[str, MethodEntry]:
    """Every catalogue entry by key."""
    raw: dict[str, dict[str, Any]] = yaml.safe_load((_DIR / "methods.yaml").read_text(encoding="utf8"))
    return {
        key: MethodEntry(
            key=key,
            name=str(entry["name"]),
            latex=entry.get("latex"),
            references=tuple(Citation(**ref) for ref in entry.get("references") or ()),
            structural=bool(entry.get("structural", False)),
        )
        for key, entry in raw.items()
    }


def method(key: str) -> MethodEntry | None:
    """One catalogue entry, or None for an unknown key (the audit flags those)."""
    return methods().get(key)


@cache
def _method_sources() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((_DIR / "sources.yaml").read_text(encoding="utf8"))
    return raw


@cache
def _chemdb_sources() -> dict[str, dict[str, str]]:
    from ngdesign.data import chemdb

    return chemdb.sources()


def source_citation(key: str, *, table: str | None = None, reference: str | None = None) -> Citation | None:
    """A citation by source key: data/provenance/sources.yaml first, then chemdb's."""
    own = _method_sources()["sources"].get(key)
    rec = own if own is not None else _chemdb_sources().get(key)
    if rec is None:
        return None
    return Citation(
        source=key,
        citation=str(rec["citation"]),
        doi=str(rec["doi"]) if rec.get("doi") else None,
        url=str(rec["url"]) if rec.get("url") else None,
        table=table,
        reference=reference,
        grade=str(rec["grade"]) if rec.get("grade") else None,
    )


def method_key_citation(family: str, key: str) -> tuple[Citation | None, str]:
    """(citation, quality) for a ``chemicals``/``thermo`` method key of one family.

    ``family`` is ``constants``, ``heat_capacity_gas`` or ``vapor_pressure``.
    Unknown keys are (None, "uncited").
    """
    entry = _method_sources().get(family, {}).get(key)
    if entry is None:
        return None, "uncited"
    src = entry.get("chemdb") or entry.get("source")
    cit = source_citation(str(src), table=entry.get("table"))
    if cit is None:
        return None, "uncited"
    return cit, str(entry.get("quality", "cited"))
