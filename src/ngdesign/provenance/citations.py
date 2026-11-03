"""Citations for the pure-component constants a property package consumed.

The EOS constants come from ``chemicals`` (``ChemicalConstantsPackage.from_IDs``),
which picks one of several bundled data sets per property. To cite the number
the EOS actually used, each available ``chemicals`` method is re-evaluated and the
first one reproducing the value bit-for-bit names the source; that method key
maps to a citation in ``data/provenance/sources.yaml`` (or the chemdb source it
points at), and the matching ``data/chemdb/properties.csv`` row - same CAS,
property, source and value to 1e-6 relative - supplies the row reference.
Nothing is guessed: a value no method reproduces is ``uncited``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any

from ngdesign.provenance import catalogue
from ngdesign.provenance.model import Citation

_REL = 1e-6


def _method_tables() -> dict[str, tuple[Callable[..., Any], Callable[[str], list[str]]]]:
    from chemicals.acentric import omega, omega_methods
    from chemicals.critical import Pc, Pc_methods, Tc, Tc_methods

    return {"Tc": (Tc, Tc_methods), "Pc": (Pc, Pc_methods), "omega": (omega, omega_methods)}


@cache
def _identify_method(cas: str, prop: str, value: float) -> str | None:
    fn, lister = _method_tables()[prop]
    for m in lister(cas):
        try:
            if fn(cas, method=m) == value:
                return str(m)
        except Exception:  # a method listed but failing to evaluate is simply not the source
            continue
    return None


def _chemdb_reference(cas: str, prop: str, value: float, chemdb_source: str) -> str | None:
    from ngdesign.data import chemdb

    try:
        rows = chemdb.values(cas, prop)
    except chemdb.ChemDbError:
        return None
    for row in rows:
        if row.source == chemdb_source and abs(row.value - value) <= _REL * max(abs(value), 1e-30):
            return row.reference or f"chemdb {prop} row ({row.source})"
    return None


@cache
def cite_constant(cas: str | None, prop: str, value: float) -> tuple[Citation | None, str, str | None]:
    """(citation, quality, chemicals method key) for one EOS constant.

    ``prop`` is ``Tc``, ``Pc`` or ``omega``. ``cas=None`` (pseudo-components) is
    handled by the caller from the component record's own provenance.
    """
    if cas is None or prop not in ("Tc", "Pc", "omega"):
        return None, "uncited", None
    key = _identify_method(cas, prop, value)
    if key is None:
        return None, "uncited", None
    cit, quality = catalogue.method_key_citation("constants", key)
    if cit is None:
        return None, "uncited", key
    from ngdesign.provenance.catalogue import _method_sources

    entry = _method_sources()["constants"].get(key, {})
    chemdb_src = entry.get("chemdb") or ("coolprop" if key == "HEOS" else None)
    if chemdb_src is not None:
        ref = _chemdb_reference(cas, prop, value, str(chemdb_src))
        if ref is not None:
            cit = cit.model_copy(update={"reference": f"cross-checked with chemdb: {ref}"})
    return cit, quality, key


def cite_correlation(family: str, method_key: str | None) -> tuple[Citation | None, str]:
    """(citation, quality) for a thermo T-dependent correlation's selected method."""
    if not method_key:
        return None, "uncited"
    return catalogue.method_key_citation(family, method_key)


def cite_mw() -> Citation | None:
    return catalogue.source_citation("openbabel_elements")
