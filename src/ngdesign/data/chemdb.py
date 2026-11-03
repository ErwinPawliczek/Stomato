"""The cited chemical database in ``data/chemdb/`` (read-only, lazily loaded).

Every value is a number a named source states, converted to SI by
``scripts/chemdb/build.py``; nothing is estimated here. All sources are kept: for
each (species, property) one row is flagged selected, by the source ranking in
the build script, and :func:`values` returns the rest so a caller can see the
spread. Species are keyed by CAS and found by CAS, curated slate id, name, IUPAC
name, InChIKey or unambiguous formula, then by the ``chemicals`` synonym bank.

Grades: **A** evaluated (ATcT, NIST-JANAF, IUPAC, WebBook "Review" rows), **B**
handbook compilation or a referenced measurement, **C** compilation without a
per-value reference (Yaws); see ``data/chemdb/README.md`` and ``sources.yaml``.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml
from chemicals.elements import atoms_to_Hill, nested_formula_parser
from chemicals.identifiers import CAS_from_any

from ngdesign.data import DATA_DIR, _curated_table
from ngdesign.data.formula import FormulaError, parse_formula

_DIR = DATA_DIR / "chemdb"


class ChemDbError(ValueError):
    """Base class of database refusals."""


class UnknownSpeciesError(ChemDbError):
    """No species in the database matches the query."""


class AmbiguousSpeciesError(ChemDbError):
    """A query (usually a formula with isomers) matches several species."""


class MissingPropertyError(ChemDbError):
    """The species exists but no source states the requested property."""


@dataclass(frozen=True, slots=True)
class Species:
    """Identity of one database species."""

    cas: str
    name: str
    iupac_name: str
    formula: str
    mw: float | None  # g/mol
    charge: int
    inchikey: str
    smiles: str
    pubchem_cid: int | None
    identity_source: str
    live_nist: bool


@dataclass(frozen=True, slots=True)
class PropertyValue:
    """One cited value in SI, with the temperature it applies at when it has one."""

    cas: str
    property: str
    value: float
    unit: str
    uncertainty: float | None
    T_K: float | None
    source: str
    grade: str
    reference: str
    selected: bool


def _optional(text: str) -> float | None:
    return float(text) if text else None


def _rows(name: str) -> list[dict[str, str]]:
    with (_DIR / name).open(encoding="utf8", newline="") as handle:
        return list(csv.DictReader(handle))


@cache
def _species() -> dict[str, Species]:
    table: dict[str, Species] = {}
    for row in _rows("species.csv"):
        table[row["cas"]] = Species(
            cas=row["cas"],
            name=row["name"],
            iupac_name=row["iupac_name"],
            formula=row["formula"],
            mw=_optional(row["mw"]),
            charge=int(row["charge"] or 0),
            inchikey=row["inchikey"],
            smiles=row["smiles"],
            pubchem_cid=int(row["pubchem_cid"]) if row["pubchem_cid"] else None,
            identity_source=row["identity_source"],
            live_nist=row["live_nist"] == "1",
        )
    return table


@cache
def _properties() -> dict[str, dict[str, list[PropertyValue]]]:
    table: dict[str, dict[str, list[PropertyValue]]] = defaultdict(lambda: defaultdict(list))
    for row in _rows("properties.csv"):
        table[row["cas"]][row["property"]].append(
            PropertyValue(
                cas=row["cas"],
                property=row["property"],
                value=float(row["value"]),
                unit=row["unit"],
                uncertainty=_optional(row["uncertainty"]),
                T_K=_optional(row["T_K"]),
                source=row["source"],
                grade=row["grade"],
                reference=row["reference"],
                selected=row["selected"] == "1",
            )
        )
    return table


@cache
def _name_index() -> dict[str, str]:
    """Lower-cased identifiers to CAS. A name several records share goes to the neutral
    species with the most data: "iron" is the metal, not an ion with one entropy."""
    index: dict[str, str] = {}
    for species in sorted(_species().values(), key=lambda s: (s.charge != 0, -_data_rows(s.cas), s.cas)):
        for key in (species.inchikey, species.iupac_name, species.name):
            if key:
                index.setdefault(key.lower(), species.cas)
    return index


@cache
def _formula_index() -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = defaultdict(list)
    for species in _species().values():
        index[species.formula].append(species.cas)
    return {formula: tuple(sorted(cases)) for formula, cases in index.items()}


def all_species() -> tuple[Species, ...]:
    """Every species, in CAS-sorted file order."""
    return tuple(_species().values())


def by_formula(formula: str) -> tuple[Species, ...]:
    """Every species carrying exactly this Hill-order formula (isomers included)."""
    return tuple(_species()[cas] for cas in _formula_index().get(formula, ()))


def _data_rows(cas: str) -> int:
    return sum(len(rows) for rows in _properties().get(cas, {}).values())


def _hill(formula: str) -> str | None:
    """Hill-order form of a formula-shaped string, None when it is not one."""
    if not formula[:1].isupper():
        return None
    try:
        atoms = nested_formula_parser(formula)
    except Exception:
        return None
    if not atoms:
        return None
    try:
        return str(atoms_to_Hill(atoms))
    except Exception:
        return None


@cache
def _ion_index() -> dict[tuple[str, int], str]:
    """(Hill formula of the atoms, charge) -> CAS."""
    index: dict[tuple[str, int], str] = {}
    ions = (s for s in _species().values() if s.charge != 0)
    for species in sorted(
        ions, key=lambda s: (s.identity_source != "crc_aqueous", -_data_rows(s.cas), s.cas)
    ):
        try:
            index.setdefault((parse_formula(species.formula).hill, species.charge), species.cas)
        except FormulaError:
            continue
    return index


def _ion(query: str) -> Species | None:
    """The ion a charged formula names; a charge is never dropped to reach a neutral."""
    try:
        parsed = parse_formula(query)
    except FormulaError:
        return None
    if parsed.charge == 0:
        return None
    cas = _ion_index().get((parsed.hill, parsed.charge))
    if cas is None:
        raise UnknownSpeciesError(f"no aqueous ion matches {query!r}")
    return _species()[cas]


def find(query: str) -> Species:
    """Resolve a query to one species.

    Order: exact CAS, curated slate id, name / IUPAC name / InChIKey, formula in any
    atom order (``NH3``, ``CH3OH``), then the ``chemicals`` synonym bank. A formula
    shared by several species raises :class:`AmbiguousSpeciesError` naming them, the
    best-documented first. The formula step runs before the synonym bank because that
    bank answers a formula with one isomer without saying so (``C2H5OH`` gives
    dimethyl ether), and an unnoticed isomer swap changes every downstream number.
    """
    table = _species()
    if query in table:
        return table[query]
    curated = _curated_table().get(query)
    if curated is not None and str(curated["cas"]) in table:
        return table[str(curated["cas"])]
    named = _name_index().get(query.lower())
    if named is not None:
        return table[named]
    ion = _ion(query)
    if ion is not None:
        return ion
    hill = _hill(query)
    matches = _formula_index().get(hill, ()) if hill is not None else ()
    neutral = tuple(c for c in matches if table[c].charge == 0)
    matches = neutral or matches
    if len(matches) == 1:
        return table[matches[0]]
    if matches:
        ranked = sorted(matches, key=lambda c: (-_data_rows(c), c))
        keys = {table[c].inchikey for c in ranked}
        if len(keys) == 1 and "" not in keys:  # one molecule under two registry numbers
            return table[ranked[0]]
        names = ", ".join(f"{table[c].name} ({c})" for c in ranked[:8])
        more = f" and {len(ranked) - 8} more" if len(ranked) > 8 else ""
        raise AmbiguousSpeciesError(f"formula {query!r} matches {len(ranked)} species: {names}{more}")
    try:
        cas = str(CAS_from_any(query))
    except Exception:
        raise UnknownSpeciesError(f"no species matches {query!r}") from None
    if cas in table:
        return table[cas]
    raise UnknownSpeciesError(f"{query!r} resolves to CAS {cas}, which is not in the chemical database")


def composition(query: str) -> dict[str, int]:
    """Element counts of a species' formula; a fractional formula is refused."""
    formula = find(query).formula
    atoms = nested_formula_parser(formula)  # the parser reads past a charge
    if any(float(count) != int(count) for count in atoms.values()):
        raise ChemDbError(f"{formula} is non-stoichiometric")
    return {element: int(count) for element, count in atoms.items()}


def search(text: str, limit: int = 20) -> list[Species]:
    """Species whose name, IUPAC name or formula contains ``text`` (case-insensitive)."""
    needle = text.lower()
    hits = [
        s
        for s in _species().values()
        if needle in s.name.lower() or needle in s.iupac_name.lower() or needle == s.formula.lower()
    ]
    hits.sort(key=lambda s: (len(s.name), s.name))
    return hits[:limit]


def values(query: str, prop: str) -> list[PropertyValue]:
    """Every cited value of one property, selected first; [] when no source states it."""
    return list(_properties().get(find(query).cas, {}).get(prop, ()))


def value(query: str, prop: str) -> PropertyValue:
    """The selected value of one property, or :class:`MissingPropertyError`."""
    rows = values(query, prop)
    for row in rows:
        if row.selected:
            return row
    raise MissingPropertyError(f"no source states {prop!r} for {query!r}")


def maybe(query: str, prop: str) -> float | None:
    """The selected value as a float, or None when no source states it."""
    rows = values(query, prop)
    return next((row.value for row in rows if row.selected), None)


def properties_of(query: str) -> dict[str, PropertyValue]:
    """Selected value of every property the species has."""
    return {
        prop: next(row for row in rows if row.selected)
        for prop, rows in _properties().get(find(query).cas, {}).items()
    }


@cache
def _grouped(name: str) -> dict[str, list[dict[str, Any]]]:
    table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _rows(name):
        parsed: dict[str, Any] = {}
        for key, text in row.items():
            if key in ("cas", "phase", "phase_298", "source", "reference", "form", "table", "note", "term"):
                parsed[key] = text
            else:
                parsed[key] = _optional(text)
        table[row["cas"]].append(parsed)
    return table


def shomate(query: str, phase: str = "gas") -> list[dict[str, Any]]:
    """NIST Shomate pieces of one phase, ascending in T (kJ-basis coefficients)."""
    return [row for row in _grouped("shomate.csv").get(find(query).cas, []) if row["phase"] == phase]


def antoine(query: str) -> list[dict[str, Any]]:
    """Antoine fits: log10(P/bar) = A - B/(T/K + C), with their validity windows."""
    return list(_grouped("antoine.csv").get(find(query).cas, []))


def wagner(query: str) -> list[dict[str, Any]]:
    """Wagner vapour-pressure fits (``form`` "2.5-5" or "1.5-3-6")."""
    return list(_grouped("wagner.csv").get(find(query).cas, []))


def nasa9(query: str, phase: str = "gas") -> list[dict[str, Any]]:
    """NASA 9-coefficient pieces (McBride et al. 2002) of one phase, ascending in T."""
    rows = [row for row in _grouped("nasa9.csv").get(find(query).cas, []) if row["phase"] == phase]
    return sorted(rows, key=lambda row: float(row["Tmin"]))


def dippr101(query: str) -> list[dict[str, Any]]:
    """DIPPR 101 vapour-pressure fits: ln(P/Pa) = a0 + a1/T + a2 ln T + a3 T^a4."""
    return list(_grouped("dippr101.csv").get(find(query).cas, []))


def cp_liquid(query: str) -> list[dict[str, Any]]:
    """Liquid Cp fits: ``dippr100`` polynomial in J/(kmol K), ``zabransky_*`` cubic splines."""
    return list(_grouped("cp_liquid.csv").get(find(query).cas, []))


def cp_gas(query: str) -> list[dict[str, Any]]:
    """Ideal-gas Cp fits (``form`` "poling": Cp/R polynomial; "trc": TRC eight-term)."""
    return list(_grouped("cp_gas.csv").get(find(query).cas, []))


def cp0_eos(query: str) -> list[dict[str, Any]]:
    """Ideal-gas Cp0 of a reference equation of state, one row per term (``cp0_eos.csv``).

    cp0/R = sum(const a) + sum(pe: a y^2 e^y/(e^y-1)^2) + sum(cosh: a (y/cosh y)^2)
    + sum(power: a T^b), with y = b/T; ``R`` is the EOS's own gas constant.
    """
    return list(_grouped("cp0_eos.csv").get(find(query).cas, []))


def cp_gas_points(query: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Tabulated ideal-gas Cp(T) points (``cp_gas_points.csv``) by (source, reference), ascending in T.

    Each group is one stated table: a WebBook gas Cp table or one ThermoML data set.
    """
    tables: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _grouped("cp_gas_points.csv").get(find(query).cas, []):
        tables[(row["source"], row["reference"])].append(row)
    return {key: sorted(rows, key=lambda r: float(r["T"])) for key, rows in tables.items()}


def janaf(query: str) -> dict[str, list[dict[str, Any]]]:
    """NIST-JANAF rows of one species by table id, ascending in T."""
    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _grouped("janaf.csv").get(find(query).cas, []):
        tables[row["table"]].append(row)
    return dict(tables)


@cache
def sources() -> dict[str, dict[str, str]]:
    """Source key -> citation record (``sources.yaml``)."""
    raw = yaml.safe_load((_DIR / "sources.yaml").read_text(encoding="utf8"))
    table: dict[str, dict[str, str]] = raw["sources"]
    return table
