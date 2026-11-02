"""Build the cited chemical database under ``data/chemdb/`` from source documents.

Inputs are the raw pages cached by ``fetch.py`` plus the primary-source tables
that ship inside the pinned ``chemicals`` package. Nothing here estimates a
value: a row is a number some named source states, converted to SI. Every source
stays in ``properties.csv``; the ``selected`` flag marks the value the engine
uses, by the ranking in :data:`SOURCE_RANK`.

    python -I scripts/chemdb/build.py seed   <cache-dir>            # species -> PubChem CIDs
    python -I scripts/chemdb/fetch.py pubchem <cache-dir>/cids.tsv <cache-dir>
    python -I scripts/chemdb/build.py tables <cache-dir> data/chemdb
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import chemicals
import CoolProp.CoolProp as CP
import scipy.constants as sc
import thermo
from chemicals.elements import charge_from_formula
from chemicals.identifiers import search_chemical

from ngdesign.data import chemdb, vapour_pressure  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_nist import (  # noqa: E402
    Page,
    parse_henry,
    parse_janaf_index,
    parse_janaf_table,
    parse_page,
    reference_phase_298,
)

BANK = Path(chemicals.__file__).resolve().parent

#: Lower rank wins when several sources state one property. Evaluated/critically
#: reviewed sources first, handbook compilations next, unreferenced collections last.
SOURCE_RANK: dict[str, int] = {
    "coolprop": 0,  # states only Tc and Pc, of fluids with a reference equation of state
    "atct": 0,
    "janaf": 1,
    "iupac_critical": 2,
    "nist_review": 3,
    "crc_critical": 4,
    "crc_thermo": 5,
    "crc_hvap": 6,
    "crc_hfus": 6,
    "crc_constants": 7,
    "poling": 8,
    "nist": 9,
    "nist_snapshot": 10,
    "yaws": 11,
    "crc_aqueous": 5,
    "nist_henry": 9,
    "psrk": 5,
    "dippr_pina": 5,
    "passut_danner": 8,
    "mathews": 8,
    "omega_definition": 9,
}

GRADES: dict[str, str] = {
    "coolprop": "A",
    "atct": "A",
    "janaf": "A",
    "iupac_critical": "A",
    "nist_review": "A",
    "crc_critical": "B",
    "crc_thermo": "B",
    "crc_hvap": "B",
    "crc_hfus": "B",
    "crc_constants": "B",
    "poling": "B",
    "nist": "B",
    "nist_snapshot": "B",
    "yaws": "C",
    "crc_aqueous": "B",
    "nist_henry": "B",
    "psrk": "B",
    "dippr_pina": "B",
    "passut_danner": "B",
    "mathews": "B",
    "omega_definition": "B",
}

UNITS = {
    "Hf": "J/mol",
    "Hc": "J/mol",
    "Gf": "J/mol",
    "S0": "J/(mol K)",
    "Cp": "J/(mol K)",
    "Hv": "J/mol",
    "Hs": "J/mol",
    "om": "1",
    "Tb": "K",
    "Tm": "K",
    "Tt": "K",
    "Tc": "K",
    "Pt": "Pa",
    "Pc": "Pa",
    "Vc": "m3/mol",
    "rh": "kg/m3",
}

_CAS = re.compile(r"^\d{2,7}-\d{2}-\d$")


def _unit(prop: str) -> str:
    return UNITS.get(prop[:2], UNITS.get(prop, ""))


def _tsv(relative: str, delimiter: str = "\t") -> Iterator[dict[str, str]]:
    with (BANK / relative).open(encoding="utf8", errors="replace") as handle:
        yield from csv.DictReader(handle, delimiter=delimiter)


def _num(text: str | None) -> float | None:
    if text is None or text.strip() == "":
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _cas_dashed(raw: str) -> str:
    raw = raw.strip()
    if "-" in raw:
        return raw
    return f"{raw[:-3]}-{raw[-3:-1]}-{raw[-1]}"


class Rows:
    """Accumulates one long-format table of cited values."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(
        self,
        cas: str,
        prop: str,
        value: float | None,
        source: str,
        *,
        uncertainty: float | None = None,
        T: float | None = None,
        reference: str = "",
    ) -> None:
        if value is None or not _CAS.match(cas):
            return
        if value <= 0.0 and (prop in POSITIVE or prop.startswith(("Cp_", "S0_"))):
            DROPPED[f"nonpositive_{prop}"] += 1
            return
        self.rows.append(
            {
                "cas": cas,
                "property": prop,
                "value": value,
                "unit": _unit(prop),
                "uncertainty": uncertainty,
                "T_K": T,
                "source": source,
                "grade": GRADES[source],
                "reference": reference.replace(",", ";")[:80],
            }
        )


def _year(reference: str) -> int:
    found = re.findall(r"(?:19|20)\d\d", reference)
    return int(found[-1]) if found else 0


def _nist_pages(cache: Path) -> list[Page]:
    pages: list[Page] = []
    for path in sorted((cache / "nist").glob("*.html")):
        pages.append(parse_page(path.stem, path.read_text(encoding="utf8", errors="replace")))
    return pages


def _collect_nist(rows: Rows, pages: Iterable[Page]) -> None:
    for page in pages:
        by_property: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for value in page.values:
            by_property[value["property"]].append(value)
        for prop, entries in by_property.items():
            # "Review" rows are evaluations; "AVG" rows are TRC means, often rounded to
            # the nearest kelvin, so they rank with the individual measurements.
            reviewed = [e for e in entries if e["method"] in ("Review", "AVG")]
            others = sorted(
                (e for e in entries if e["method"] not in ("Review", "AVG")),
                key=lambda e: -_year(e["reference"]),
            )
            for entry in reviewed + others[:2]:
                source = "nist_review" if entry["method"] == "Review" else "nist"
                rows.add(
                    page.cas,
                    prop,
                    entry["value"],
                    source,
                    uncertainty=entry["uncertainty"],
                    reference=entry["reference"] or entry["method"],
                )
        for point in sorted(page.hvap_t, key=lambda e: -_year(e["reference"]))[:3]:
            rows.add(page.cas, "Hvap", point["value"], "nist", T=point["T"], reference=point["reference"])
        for point in page.cp_points:
            if abs(point["T"] - 298.15) <= 2.0:
                prop = f"Cp_{point['phase']}"
                rows.add(page.cas, prop, point["value"], "nist", T=point["T"], reference=point["reference"])
        for point in sorted(page.hfus_t, key=lambda e: -_year(e["reference"]))[:2]:
            rows.add(page.cas, "Hfus", point["value"], "nist", T=point["T"], reference=point["reference"])


_JANAF_PHASE = {"g": "gas", "l": "liquid", "cr": "solid"}

#: What the build refused and why; reported in MANIFEST.json.
DROPPED: Counter[str] = Counter()

#: Quantities that cannot be zero or negative: source tables use 0 as "no value" here.
POSITIVE = {"Tb", "Tm", "Tt", "Tc", "Pt", "Pc", "Vc", "Hfus", "Hvap", "Hvap_298", "rho_liquid"}


def _janaf_formula_matches(cas: str, formula: str) -> bool:
    """JANAF indexes oligomers under the monomer's CAS (the HF hexamer sits on 7664-39-3)."""
    try:
        bank = search_chemical(cas).formula
    except Exception:
        return True
    return not (_hill(formula) and _hill(bank)) or _hill(formula) == _hill(bank)


def _janaf(cache: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """Every neutral-species JANAF table: long rows + the identity found on the index."""
    root = cache / "janaf"
    index: dict[str, dict[str, str]] = {}
    for path in sorted(root.glob("*-index.html")):
        for row in parse_janaf_index(path.read_text(encoding="utf8", errors="replace")):
            index[row["table"]] = row
    table_rows: list[dict[str, Any]] = []
    identity: dict[str, dict[str, str]] = {}
    for table, row in sorted(index.items()):
        path = root / f"{table}.txt"
        if not path.exists():
            continue
        if not _CAS.match(row["cas"]) or re.search(r"[-+]$", row["formula"]) or "Ion" in row["name"]:
            continue
        if row["phase"] not in ("g", "l", "cr", "cr,l", "ref"):
            continue  # the fixed-pressure water tables are not standard-state tables
        if not _janaf_formula_matches(row["cas"], row["formula"]):
            DROPPED["janaf_table_formula_differs_from_cas"] += 1
            continue
        text = path.read_text(encoding="utf8", errors="replace")
        parsed_rows = parse_janaf_table(text)
        phase_298 = (
            reference_phase_298(parsed_rows) if row["phase"] == "ref" else _JANAF_PHASE.get(row["phase"], "")
        )
        for parsed in parsed_rows:
            table_rows.append(
                {
                    "cas": row["cas"],
                    "formula": row["formula"],
                    "phase": row["phase"],
                    "phase_298": phase_298,
                    "table": table,
                    **parsed,
                }
            )
        identity.setdefault(row["cas"], {"name": row["name"], "formula": row["formula"]})
    return table_rows, identity


def _collect_janaf(rows: Rows, table_rows: list[dict[str, Any]]) -> None:
    """Standard values at 298.15 K: per phase, of the table with the lowest G°298.

    Polymorphs share a CAS (Al2O3 alpha, delta, kappa). Only the stable one can speak
    for "the solid", and its enthalpy must come from the table its Cp(T) comes from.
    """
    stable: dict[tuple[str, str], dict[str, Any]] = {}
    for row in table_rows:
        phase = row["phase_298"]
        if row["T"] != 298.15 or not phase or row.get("Hf") is None:
            continue
        gibbs = float(row["Hf"]) - 298.15 * float(row["S"])
        held = stable.get((row["cas"], phase))
        if held is None or gibbs < held["_gibbs"]:
            stable[(row["cas"], phase)] = {**row, "_gibbs": gibbs}
    for (_, phase), row in sorted(stable.items()):
        reference = f"JANAF table {row['table']}"
        rows.add(row["cas"], f"Hf_{phase}", row.get("Hf"), "janaf", reference=reference)
        rows.add(row["cas"], f"Gf_{phase}", row.get("Gf"), "janaf", reference=reference)
        rows.add(row["cas"], f"S0_{phase}", row["S"], "janaf", reference=reference)
        rows.add(row["cas"], f"Cp_{phase}", row["Cp"], "janaf", T=298.15, reference=reference)


ION_TABLE = "Electrolytes/CRC Thermodynamic Properties of Aqueous Ions.tsv"


def _collect_ions(rows: Rows) -> dict[str, dict[str, Any]]:
    """CRC aqueous-ion values (H+ = 0 convention) and the ions' identities."""
    identity: dict[str, dict[str, Any]] = {}
    for row in _tsv(ION_TABLE):
        cas = row["CAS"]
        for head, prop in (("Hf(aq)", "Hf_aq"), ("Gf(aq)", "Gf_aq"), ("S(aq)", "S0_aq"), ("Cp(aq)", "Cp_aq")):
            value = _num(row[head])
            if value is not None:
                rows.rows.append(
                    {
                        "cas": cas,
                        "property": prop,
                        "value": value,
                        "unit": _unit(prop),
                        "uncertainty": None,
                        "T_K": 298.15 if prop == "Cp_aq" else None,
                        "source": "crc_aqueous",
                        "grade": GRADES["crc_aqueous"],
                        "reference": "",
                    }
                )
        identity[cas] = {
            "cas": cas,
            "name": row["Name"],
            "formula": row["Formula"],
            "mw": _num(row["MW"]),
            "inchikey": "",
            "smiles": "",
            "pubchem_cid": None,
            "charge": _ion_charge(row["Formula"]),
        }
    return identity


def _ion_charge(formula: str) -> int:
    return int(charge_from_formula(formula))


def _best(rows: list[dict[str, Any]], cas: str, prop: str) -> float | None:
    found = [r for r in rows if r["cas"] == cas and r["property"] == prop]
    return min(found, key=lambda r: SOURCE_RANK[r["source"]])["value"] if found else None


def _collect_henry(rows: Rows, cache: Path) -> None:
    """Aqueous standard states of dissolved gases, from WebBook Henry's-law data.

    For X(g) = X(aq) with k°H in mol/(kg bar), the 1 molal, 1 bar equilibrium constant
    is k°H itself: ΔG°soln = −RT ln k°H and ΔH°soln = −R·d ln kH/d(1/T). The aqueous
    values are those added to the gas's selected ΔfH°, ΔfG° and S°, so these are stated
    numbers combined by definition, and each row's reference says so.
    """
    index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows.rows:
        if row["property"] in ("Hf_gas", "S0_gas"):
            index[(row["cas"], row["property"])].append(row)
    for path in sorted((cache / "henry").glob("*.html")):
        parsed = parse_henry(path.read_text(encoding="utf8", errors="replace"))
        cas = path.stem
        hf_rows, s_rows = index.get((cas, "Hf_gas")), index.get((cas, "S0_gas"))
        if parsed is None or not hf_rows or not s_rows:
            continue
        k, slope, entries = parsed
        hf = min(hf_rows, key=lambda r: SOURCE_RANK[r["source"]])["value"]
        s0 = min(s_rows, key=lambda r: SOURCE_RANK[r["source"]])["value"]
        dh = -sc.R * slope
        dg = -sc.R * 298.15 * math.log(k)
        note = f"gas + Henry median of {entries} (k {k:.4g}; slope {slope:.4g} K)"
        rows.add(cas, "Hf_aq", hf + dh, "nist_henry", reference=note)
        rows.add(cas, "S0_aq", s0 + (dh - dg) / 298.15, "nist_henry", reference=note)


def _collect_coolprop(rows: Rows) -> None:
    """Critical points of the reference equations of state in CoolProp."""
    for fluid in CP.get_global_param_string("fluids_list").split(","):
        cas = CP.get_fluid_param_string(fluid, "CAS")
        reference = f"CoolProp {fluid}"
        rows.add(cas, "Tc", float(CP.PropsSI("Tcrit", fluid)), "coolprop", reference=reference)
        rows.add(cas, "Pc", float(CP.PropsSI("pcrit", fluid)), "coolprop", reference=reference)
        omega = float(CP.PropsSI("acentric", fluid))
        if math.isfinite(omega) and abs(omega) < 5.0:
            rows.add(cas, "omega", omega, "coolprop", reference=reference)


def _collect_critical(rows: Rows, names: dict[str, str]) -> None:
    """The critical-property collections beyond the IUPAC and CRC tables."""
    for relative, source, keys in (
        ("Critical Properties/Appendix to PSRK Revision 4.tsv", "psrk", ("Tc", "Pc", "Vc", "omega")),
        ("Critical Properties/PassutDanner1973.tsv", "passut_danner", ("Tc", "Pc", "omega")),
        ("Critical Properties/DIPPRPinaMartines.tsv", "dippr_pina", ("Tc", "Pc", "Vc")),
        ("Critical Properties/Mathews1972InorganicCriticalProps.tsv", "mathews", ("Tc", "Pc", "Vc")),
        ("Critical Properties/Yaws Collection.tsv", "yaws", ("Tc", "Pc", "Vc", "omega")),
    ):
        for row in _tsv(relative):
            if row.get("Chemical"):
                names.setdefault(row["CAS"], row["Chemical"].strip())
            for key in keys:
                rows.add(row["CAS"], key, _num(row[key]), source)


def _collect_bundled(rows: Rows) -> dict[str, str]:
    """The primary tables shipped in ``chemicals``; returns cas -> name when stated."""
    names: dict[str, str] = {}
    _collect_critical(rows, names)
    for row in _tsv("Reactions/ATcT 1.112 (g).tsv"):
        rows.add(
            row["CAS"],
            "Hf_gas",
            _num(row["Hfg"]),
            "atct",
            uncertainty=_num(row["uncertainty"]),
            reference="ATcT 1.112",
        )
    for row in _tsv("Reactions/ATcT 1.112 (l).tsv"):
        rows.add(
            row["CAS"],
            "Hf_liquid",
            _num(row["Hfl"]),
            "atct",
            uncertainty=_num(row.get("uncertainty")),
            reference="ATcT 1.112",
        )
    crc = "Heat Capacity/CRC Standard Thermodynamic Properties of Chemical Substances.tsv"
    for row in _tsv(crc):
        names.setdefault(row["CAS"], row["Chemical"])
        for suffix, phase in (("s", "solid"), ("l", "liquid"), ("g", "gas")):
            for head in ("Hf", "Gf"):
                rows.add(row["CAS"], f"{head}_{phase}", _num(row[f"{head}{suffix}"]), "crc_thermo")
            rows.add(row["CAS"], f"S0_{phase}", _num(row[f"S0{suffix}"]), "crc_thermo")
            rows.add(row["CAS"], f"Cp_{phase}", _num(row[f"Cp{suffix}"]), "crc_thermo", T=298.15)
    for row in _tsv("Reactions/Yaws Hf S0 (g).tsv"):
        rows.add(row["CAS"], "Hf_gas", _num(row["Hfg"]), "yaws")
        rows.add(row["CAS"], "S0_gas", _num(row["S0g"]), "yaws")
    for row in _tsv("Critical Properties/IUPACOrganicCriticalProps.tsv"):
        names.setdefault(row["CAS"], row["Chemical"])
        for key in ("Tc", "Pc", "Vc"):
            rows.add(
                row["CAS"], key, _num(row[key]), "iupac_critical", reference=f"IUPAC ref {row['Reference']}"
            )
    for row in _tsv("Critical Properties/CRCCriticalOrganics.tsv"):
        names.setdefault(row["CAS"], row["Chemical"])
        for key in ("Tc", "Pc", "Vc"):
            rows.add(row["CAS"], key, _num(row[key]), "crc_critical", uncertainty=_num(row[f"{key}_error"]))
    for row in _tsv("Phase Change/CRC Handbook Heat of Vaporization.tsv"):
        names.setdefault(row["CAS"], row["Chemical"])
        rows.add(row["CAS"], "Hvap", _num(row["HvapTb"]), "crc_hvap", T=_num(row["Tb"]))
        rows.add(row["CAS"], "Hvap_298", _num(row["Hvap298"]), "crc_hvap", T=298.15)
    for row in _tsv("Phase Change/CRC Handbook Heat of Fusion.tsv"):
        names.setdefault(row["CAS"], row["Chemical"])
        rows.add(row["CAS"], "Hfus", _num(row["Hfus"]), "crc_hfus")
    for row in _tsv("Heat Capacity/PolingDatabank.tsv"):
        names.setdefault(row["CAS"], row["Chemical"].strip())
        rows.add(row["CAS"], "Cp_gas", _num(row["Cpg"]), "poling", T=298.15)
        rows.add(row["CAS"], "Cp_liquid", _num(row["Cpl"]), "poling", T=298.15)
    for row in _tsv("Misc/webbook_constants.tsv"):
        cas = _cas_dashed(row["CAS"])
        useful = any(row[k] for k in ("Tb", "Tc", "Hfg", "Hfl", "Hfs", "S0g", "Hvap"))
        if not useful:
            continue
        for key, prop in (
            ("Tt", "Tt"),
            ("Tm", "Tm"),
            ("Tb", "Tb"),
            ("Tc", "Tc"),
            ("Pt", "Pt"),
            ("Pc", "Pc"),
            ("Vc", "Vc"),
            ("Hfs", "Hf_solid"),
            ("Hfl", "Hf_liquid"),
            ("Hfg", "Hf_gas"),
            ("S0s", "S0_solid"),
            ("S0l", "S0_liquid"),
            ("S0g", "S0_gas"),
            ("Hsub", "Hsub_298"),
            ("Hfus", "Hfus"),
            ("Hvap", "Hvap_298"),
        ):
            rows.add(cas, prop, _num(row[key]), "nist_snapshot")
    return names


def _constants(rows: Rows) -> None:
    """CRC physical constants: melting and boiling points, and liquid density."""
    for relative in (
        "Misc/Physical Constants of Organic Compounds.csv",
        "Misc/Physical Constants of Inorganic Compounds.csv",
    ):
        for row in _tsv(relative):
            cas = row.get("CAS", "")
            rows.add(cas, "Tm", _num(row.get("Tm")), "crc_constants")
            rows.add(cas, "Tb", _num(row.get("Tb")), "crc_constants")
            rows.add(cas, "rho_liquid", _num(row.get("rho")), "crc_constants")


#: Relative distance from the sources' median beyond which a value is set aside.
CONSENSUS_LIMIT = {"Tc": 0.03, "Pc": 0.10}
NON_VOTING = ("nist_snapshot", "yaws")
#: Lines describing every top-ranked value that lost to the other sources.
OUTVOTED: list[str] = []


def _consensus_choice(group: list[dict[str, Any]], prop: str) -> dict[str, Any]:
    """The best-ranked row within reach of the median of at least three sources.

    Source rank decides alone unless the sources outvote it: the bundled IUPAC table
    swaps cyclohexane and methylcyclopentane, so grade A does not make a row right.
    The reference EOS is not put to a vote: it is the check on the others. The WebBook
    snapshot gets no vote and cannot win one, since it restates (and sometimes averages)
    rows of the same pages, and neither does Yaws, which mixes in estimates. Tb and Tm
    stay out of this: three thin sources outvoted good CRC values there (R22, anisole).
    """
    limit = CONSENSUS_LIMIT.get(prop)
    if limit is None or group[0]["source"] == "coolprop":
        return group[0]
    per_source: dict[str, list[float]] = defaultdict(list)
    for row in group:
        if row["source"] not in NON_VOTING:
            per_source[row["source"]].append(float(row["value"]))
    if len(per_source) < 3:
        return group[0]
    medians = sorted(statistics.median(values) for values in per_source.values())
    centre = statistics.median(medians)
    for row in group:
        if row["source"] not in NON_VOTING and abs(float(row["value"]) - centre) <= limit * centre:
            return row
    return group[0]


def _select(rows: list[dict[str, Any]]) -> None:
    """Mark the winning row per (cas, property), and sort deterministically."""
    OUTVOTED.clear()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["cas"], row["property"])].append(row)
    for (cas, prop), group in groups.items():
        group.sort(
            key=lambda r: (
                SOURCE_RANK[r["source"]],
                r["uncertainty"] is None,
                r["uncertainty"] or 0.0,
                -_year(r["reference"]),
            )
        )
        chosen = _consensus_choice(group, prop)
        if chosen is not group[0]:
            OUTVOTED.append(
                f"outvoted {prop} {cas}: {group[0]['source']} {group[0]['value']:.6g} set aside for "
                f"{chosen['source']} {chosen['value']:.6g} {chosen['unit']}"
            )
        for row in group:
            row["selected"] = 1 if row is chosen else 0
    rows.sort(key=lambda r: (r["cas"], r["property"], -r["selected"], SOURCE_RANK[r["source"]]))


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_fmt(row.get(c)) for c in columns])
            count += 1
    return count


def _hill(formula: str) -> str:
    """Hill-ordered formula; '' for what the element parser cannot read."""
    from chemicals.elements import atoms_to_Hill, nested_formula_parser

    try:
        return str(atoms_to_Hill(nested_formula_parser(formula)))
    except Exception:
        return ""


def _identity(
    cas: str, nist: dict[str, Page], janaf: dict[str, dict[str, str]], names: dict[str, str]
) -> dict[str, Any] | None:
    """Identity from the identifier bank, else from the page or table that names it."""
    page = nist.get(cas)
    try:
        meta = search_chemical(cas)
        return {
            "cas": cas,
            "name": meta.common_name or (page.name if page else ""),
            "formula": meta.formula,
            "mw": meta.MW,
            "inchikey": meta.InChI_key,
            "smiles": meta.smiles,
            "pubchem_cid": meta.pubchemid,
        }
    except Exception:
        pass
    if page is not None and page.formula:
        return {
            "cas": cas,
            "name": page.name,
            "formula": _hill(page.formula) or page.formula,
            "mw": page.mw,
            "inchikey": page.inchikey,
            "smiles": "",
            "pubchem_cid": None,
        }
    entry = janaf.get(cas)
    if entry is not None:
        return {
            "cas": cas,
            "name": entry["name"],
            "formula": _hill(entry["formula"]) or entry["formula"],
            "mw": None,
            "inchikey": "",
            "smiles": "",
            "pubchem_cid": None,
        }
    return None


def _check_digit_valid(cas: str) -> bool:
    digits = cas.replace("-", "")
    return sum((i + 1) * int(d) for i, d in enumerate(reversed(digits[:-1]))) % 10 == int(digits[-1])


def _species_cas(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({r["cas"] for r in rows})


def _page_matches_identity(page: Page) -> bool:
    """A page whose formula contradicts the identifier bank is about something else.

    The bank maps some polymer and mixture CAS numbers to their monomer (polyethylene
    to ethene), and a page's data must not attach to that identity.
    """
    try:
        bank = _hill(str(search_chemical(page.cas).formula))
    except Exception:
        return True
    if page.formula and _hill(page.formula) and bank and _hill(page.formula) != bank:
        DROPPED["nist_page_formula_differs_from_cas"] += 1
        return False
    return True


def _collect_all(cache: Path) -> dict[str, Any]:
    rows = Rows()
    pages = [page for page in _nist_pages(cache) if _page_matches_identity(page)]
    _collect_nist(rows, pages)
    janaf_rows, janaf_identity = _janaf(cache)
    _collect_janaf(rows, janaf_rows)
    names = _collect_bundled(rows)
    _collect_coolprop(rows)
    _constants(rows)
    _collect_henry(rows, cache)
    ions = _collect_ions(rows)
    nist = {p.cas: p for p in pages}
    species: dict[str, dict[str, Any]] = {}
    for cas in _species_cas(rows.rows):
        if not _check_digit_valid(cas):
            DROPPED["species_with_invalid_cas"] += 1  # placeholder ids, none of them real registry numbers
            continue
        record = ions.get(cas) or _identity(cas, nist, janaf_identity, names)
        if record is not None and record.get("formula"):
            species[cas] = record
    return {"rows": rows.rows, "pages": pages, "janaf": janaf_rows, "species": species}


def seed(cache: Path) -> int:
    collected = _collect_all(cache)
    lines = [
        f"{cas}\t{record['pubchem_cid']}"
        for cas, record in collected["species"].items()
        if record.get("pubchem_cid")
    ]
    (cache / "cids.tsv").write_text("\n".join(lines) + "\n")
    print(len(collected["species"]), "species", len(lines), "with CIDs")
    return 0


def _pubchem(cache: Path) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for path in sorted((cache / "pubchem").glob("batch_*.json")):
        for record in json.loads(path.read_text())["PropertyTable"]["Properties"]:
            out[int(record["CID"])] = record
    return out


def _correlations(collected: dict[str, Any], kept: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Fit tables as published: Shomate, Antoine (log10 bar, K), Wagner, gas Cp."""
    shomate: list[dict[str, Any]] = []
    antoine: list[dict[str, Any]] = []
    for page in collected["pages"]:
        if page.cas not in kept:
            continue
        for row in page.shomate:
            shomate.append({"cas": page.cas, "source": "nist", **row})
        for row in page.antoine:
            antoine.append({"cas": page.cas, "source": "nist", **row})
    for row in _tsv("Vapor Pressure/Landolt_antoine_V20.tsv"):
        if row["CAS"] in kept:
            a, b, c = _num(row["A"]), _num(row["B"]), _num(row["C"])
            if a is None or b is None or c is None:
                continue
            antoine.append(
                {
                    "cas": row["CAS"],
                    "source": "landolt",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    "A": a / math.log(10.0) - 5.0,
                    "B": b / math.log(10.0),
                    "C": c,
                    "reference": "Landolt-Bornstein IV/20 (from ln Pa to log10 bar)",
                }
            )
    for row in _tsv("Vapor Pressure/Antoine Collection Poling.tsv"):
        if row["CAS"] in kept:
            a, b, c = _num(row["A"]), _num(row["B"]), _num(row["C"])
            if a is None or b is None or c is None:
                continue
            antoine.append(
                {
                    "cas": row["CAS"],
                    "source": "poling",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    "A": a - 5.0,
                    "B": b,
                    "C": c,
                    "reference": "Poling 5th ed. (A shifted from log10 Pa to bar)",
                }
            )
    wagner: list[dict[str, Any]] = []
    for row in _tsv("Vapor Pressure/Wagner Collection Poling.tsv"):
        if row["CAS"] in kept:
            wagner.append(
                {
                    "cas": row["CAS"],
                    "source": "poling",
                    "form": "2.5-5",
                    "A": _num(row["A"]),
                    "B": _num(row["B"]),
                    "C": _num(row["C"]),
                    "D": _num(row["D"]),
                    "Tc": _num(row["Tc"]),
                    "Pc": _num(row["Pc"]),
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                }
            )
    for row in _tsv("Vapor Pressure/Wagner Original McGarry.tsv"):
        if row["CAS"] in kept:
            wagner.append(
                {
                    "cas": row["CAS"],
                    "source": "mcgarry",
                    "form": "1.5-3-6",
                    "A": _num(row["A"]),
                    "B": _num(row["B"]),
                    "C": _num(row["C"]),
                    "D": _num(row["D"]),
                    "Tc": _num(row["Tc"]),
                    "Pc": _num(row["Pc"]),
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tc"]),
                }
            )
    for row in _tsv("Vapor Pressure/VDI PPDS Boiling temperatures at different pressures.tsv"):
        if row["CAS"] in kept and row["A"].strip():
            wagner.append(
                {
                    "cas": row["CAS"],
                    "source": "vdi",
                    "form": "2.5-5",
                    "A": _num(row["A"]),
                    "B": _num(row["B"]),
                    "C": _num(row["C"]),
                    "D": _num(row["D"]),
                    "Tc": _num(row["Tc"]),
                    "Pc": _num(row["Pc"]),
                    "Tmin": _num(row["Tm"]),
                    "Tmax": _num(row["Tc"]),
                }
            )
    dippr: list[dict[str, Any]] = []
    for relative, source, labels in (
        (
            "Vapor Pressure/Table 2-8 Vapor Pressure of Inorganic and Organic Liquids.tsv",
            "perry",
            ("C1", "C2", "C3", "C4", "C5"),
        ),
        ("Vapor Pressure/Alcock_Itkin_Horrigan_metalic_elements.tsv", "alcock", ("A", "B", "C", "D", "E")),
    ):
        for row in _tsv(relative):
            if row["CAS"] in kept:
                dippr.append(
                    {
                        "cas": row["CAS"],
                        "source": source,
                        "Tmin": _num(row["Tmin"]),
                        "Tmax": _num(row["Tmax"]),
                        **{f"a{i}": _num(row[label]) for i, label in enumerate(labels)},
                    }
                )
    cp_liquid: list[dict[str, Any]] = []
    for row in _tsv("Heat Capacity/Perry_Table_2-153_DIPPR_100.tsv"):
        if row["CAS"] in kept:
            cp_liquid.append(
                {
                    "cas": row["CAS"],
                    "form": "dippr100",
                    "source": "perry",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    **{f"a{i}": _num(row[label]) for i, label in enumerate("ABCDE")},
                }
            )
    for row in _tsv("Heat Capacity/Zabransky.tsv"):
        spline = [_num(row[f"A{i}-spline"]) for i in (1, 2, 3, 4)]
        if row["CASRN"] in kept and row["Data Type"] in ("p", "sat") and any(spline):
            cp_liquid.append(
                {
                    "cas": row["CASRN"],
                    "form": f"zabransky_{row['Data Type']}",
                    "source": "zabransky",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    **{f"a{i}": value for i, value in enumerate(spline)},
                }
            )
    poly: list[dict[str, Any]] = []
    for row in _tsv("Heat Capacity/PolingDatabank.tsv"):
        if row["CAS"] in kept and row["a0"].strip():
            poly.append(
                {
                    "cas": row["CAS"],
                    "form": "poling",
                    "source": "poling",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    **{f"a{i}": _num(row[f"a{i}"]) for i in range(5)},
                }
            )
    for row in _tsv("Heat Capacity/TRC Thermodynamics of Organic Compounds in the Gas State.tsv"):
        if row["CAS"] in kept:
            poly.append(
                {
                    "cas": row["CAS"],
                    "form": "trc",
                    "source": "trc",
                    "Tmin": _num(row["Tmin"]),
                    "Tmax": _num(row["Tmax"]),
                    **{f"a{i}": _num(row[f"a{i}"]) for i in range(8)},
                }
            )
    # a fit whose window has no width states nothing
    antoine = [r for r in antoine if r["Tmin"] is None or r["Tmax"] is None or r["Tmin"] < r["Tmax"]]
    return {
        "shomate": shomate,
        "antoine": antoine,
        "wagner": wagner,
        "cp_gas": poly,
        "dippr101": dippr,
        "cp_liquid": cp_liquid,
    }


def _audit(
    rows: list[dict[str, Any]],
    species: dict[str, dict[str, Any]],
    pubchem: dict[int, dict[str, Any]],
    pages: list[Page],
) -> tuple[list[str], Counter[str]]:
    """Cross-source conflicts: the honest list of where sources disagree."""
    lines: list[str] = []
    counts: Counter[str] = Counter()
    for cas, record in species.items():
        cid = record.get("pubchem_cid")
        if cid and int(cid) in pubchem:
            remote = pubchem[int(cid)]
            isotopologue = re.search(r"[DT]|\[\d", str(record["formula"])) is not None
            mismatch = _hill(remote["MolecularFormula"]) != _hill(str(record["formula"]))
            if mismatch and not isotopologue and int(remote.get("Charge", 0)) == 0:
                counts["formula_conflict_pubchem"] += 1
                lines.append(
                    f"formula {cas}: bank {record['formula']} vs PubChem {remote['MolecularFormula']}"
                )
    for page in pages:
        record = species.get(page.cas)
        if (
            record
            and page.formula
            and _hill(page.formula)
            and _hill(page.formula) != _hill(str(record["formula"]))
        ):
            counts["formula_conflict_nist"] += 1
            lines.append(f"formula {page.cas}: bank {record['formula']} vs NIST {page.formula}")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["cas"], row["property"])].append(row)
    limits = {"Tb": 5.0, "Tc": 5.0, "Pc": 2e5, "Tm": 5.0}
    for (cas, prop), group in sorted(groups.items()):
        chosen = next((r for r in group if r["selected"]), None)
        if chosen is None or chosen["T_K"] is not None:
            continue
        limit = limits.get(prop)
        if limit is None and prop.startswith(("Hf_", "Gf_")):
            limit = 5000.0
        if limit is None:
            continue
        for row in group:
            if row is chosen or row["grade"] == "C":
                continue
            if abs(float(row["value"]) - float(chosen["value"])) > limit:
                counts[f"conflict_{prop}"] += 1
                lines.append(
                    f"{prop} {cas}: {chosen['source']} {chosen['value']:.6g} vs {row['source']} "
                    f"{row['value']:.6g} {row['unit']}"
                )
                break
    return lines, counts


def _write_properties(out: Path, rows: list[dict[str, Any]]) -> int:
    return _write_csv(
        out / "properties.csv",
        [
            "cas",
            "property",
            "value",
            "unit",
            "uncertainty",
            "T_K",
            "source",
            "grade",
            "reference",
            "selected",
        ],
        rows,
    )


#: Past this gap below the gas, J/mol, a condensed ΔfH° is looked at for a sign slip.
SIGN_SLIP_GAP = 300_000.0
#: Agreement required of a stated Tb with the vapour-pressure fits, K.
TB_FIT_LIMIT = 5.0


def _reselect(group: list[dict[str, Any]], chosen: dict[str, Any], why: str) -> None:
    held = next(r for r in group if r["selected"])
    OUTVOTED.append(
        f"outvoted {held['property']} {held['cas']}: {held['source']} {held['value']:.6g} set aside for "
        f"{chosen['source']} {chosen['value']:.6g} {chosen['unit']} ({why})"
    )
    for row in group:
        row["selected"] = 1 if row is chosen else 0


def _physical_checks(rows: list[dict[str, Any]], out: Path) -> None:
    """Move a selection that fails a check no source rank can see.

    Selection by rank cannot notice a value its source got wrong: the CRC table prints
    CI4(s) and CHI3(s) with the wrong sign. Two tests are independent of the rows they
    judge. A condensed phase lies below the gas, by an amount a sign slip cannot explain
    away. And a stated Tb agrees with the saturation temperature of a vapour-pressure fit at 1 atm.
    A failing selection moves to the best-ranked row that passes; with none, it stays
    and the audit shows it.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["cas"], row["property"])].append(row)
    for (cas, prop), group in groups.items():
        if prop not in ("Hf_liquid", "Hf_solid"):
            continue
        gas = next((float(r["value"]) for r in groups.get((cas, "Hf_gas"), []) if r["selected"]), None)
        if gas is None:
            continue
        held = next(r for r in group if r["selected"])
        value = float(held["value"])
        if gas - value <= 0.0:  # a condensed phase above its own gas
            passes = [r for r in group if gas - float(r["value"]) > 0.0]
            if passes:
                _reselect(group, passes[0], "below-the-gas test")
        elif gas - value >= SIGN_SLIP_GAP:
            # Ionic solids really do sit this far below their gas (MgO: 660 kJ), so the gap
            # alone proves nothing. It takes a row of the same size and opposite sign.
            twin = [r for r in group if abs(float(r["value"]) + value) < 0.02 * abs(value)]
            if twin:
                _reselect(group, twin[0], "sign slip against the gas")
    if out.resolve() != (chemdb.DATA_DIR / "chemdb").resolve():
        return
    for (cas, prop), group in groups.items():
        if prop != "Tb":
            continue
        held = next(r for r in group if r["selected"])
        predicted = next(
            (
                t
                for t in (vapour_pressure.temperature_at(f, 101325.0) for f in vapour_pressure.fits(cas))
                if t
            ),
            None,
        )
        if predicted is None or abs(float(held["value"]) - predicted) <= TB_FIT_LIMIT:
            continue
        passes = [r for r in group if abs(float(r["value"]) - predicted) <= TB_FIT_LIMIT]
        if passes:
            _reselect(group, passes[0], "vapour-pressure test")


def _derive_omega(rows: list[dict[str, Any]], out: Path) -> None:
    """Pitzer's acentric factor from its definition, ω = −log10(Psat(0.7 Tc)/Pc) − 1.

    Run on the tables just written, so it reads the selected Tc and Pc and the same
    vapour-pressure fits the engine uses. Only a fit whose window holds 0.7 Tc counts.
    """
    if out.resolve() != (chemdb.DATA_DIR / "chemdb").resolve():
        return
    selected = {(r["cas"], r["property"]): r["value"] for r in rows if r["selected"]}
    for (cas, prop), Tc in list(selected.items()):
        Pc = selected.get((cas, "Pc"))
        if prop != "Tc" or Pc is None:
            continue
        fit = vapour_pressure.fit_at(cas, 0.7 * float(Tc))
        if fit is None:
            continue
        omega = -math.log10(fit.pressure(0.7 * float(Tc)) / float(Pc)) - 1.0
        if -1.0 < omega < 3.0:
            rows.append(
                {
                    "cas": cas,
                    "property": "omega",
                    "value": omega,
                    "unit": "1",
                    "uncertainty": None,
                    "T_K": None,
                    "source": "omega_definition",
                    "grade": GRADES["omega_definition"],
                    "reference": f"{fit.form} {fit.source} at 0.7 Tc",
                }
            )
    _select(rows)


def tables(cache: Path, out: Path) -> int:
    collected = _collect_all(cache)
    species: dict[str, dict[str, Any]] = collected["species"]
    pubchem = _pubchem(cache)
    pages: dict[str, Page] = {p.cas: p for p in collected["pages"]}
    for cas, record in species.items():
        cid = record.get("pubchem_cid")
        if int(record.get("charge") or 0) != 0:
            record["identity_source"] = "crc_aqueous"
            record["live_nist"] = 0
            continue
        remote = pubchem.get(int(cid)) if cid else None
        isotopologue = re.search(r"[DT]|\[\d", str(record["formula"])) is not None
        if (
            remote is not None
            and not isotopologue
            and _hill(remote["MolecularFormula"]) != _hill(str(record["formula"]))
        ):
            DROPPED["pubchem_record_is_another_formula"] += 1  # e.g. sulfur's CID carries implicit H
            record["pubchem_cid"] = None
            remote = None
        if remote is not None:
            record["inchikey"] = remote.get("InChIKey") or record.get("inchikey")
            record["smiles"] = remote.get("ConnectivitySMILES") or record.get("smiles")
            record["iupac_name"] = remote.get("IUPACName", "")
            record["charge"] = remote.get("Charge", 0)
            record["identity_source"] = "pubchem"
        else:
            record["identity_source"] = "chemicals_bank"
            page = pages.get(cas)
            if page is not None and page.inchikey and not record.get("inchikey"):
                record["inchikey"] = page.inchikey
                record["identity_source"] = "nist"
        record["live_nist"] = 1 if cas in pages else 0
    kept = set(species)
    rows = [r for r in collected["rows"] if r["cas"] in kept]
    _select(rows)
    out.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    counts["species"] = _write_csv(
        out / "species.csv",
        [
            "cas",
            "name",
            "iupac_name",
            "formula",
            "mw",
            "charge",
            "inchikey",
            "smiles",
            "pubchem_cid",
            "identity_source",
            "live_nist",
        ],
        (species[c] for c in sorted(species)),
    )
    counts["properties"] = _write_properties(out, rows)
    correlations = _correlations(collected, kept)
    counts["shomate"] = _write_csv(
        out / "shomate.csv",
        ["cas", "phase", "Tmin", "Tmax", "A", "B", "C", "D", "E", "F", "G", "H", "source", "reference"],
        sorted(correlations["shomate"], key=lambda r: (r["cas"], r["phase"], r["Tmin"])),
    )
    counts["antoine"] = _write_csv(
        out / "antoine.csv",
        ["cas", "Tmin", "Tmax", "A", "B", "C", "source", "reference"],
        sorted(correlations["antoine"], key=lambda r: (r["cas"], r["source"], r["Tmin"] or 0.0, r["A"])),
    )
    counts["wagner"] = _write_csv(
        out / "wagner.csv",
        ["cas", "form", "A", "B", "C", "D", "Tc", "Pc", "Tmin", "Tmax", "source"],
        sorted(correlations["wagner"], key=lambda r: (r["cas"], r["form"])),
    )
    counts["dippr101"] = _write_csv(
        out / "dippr101.csv",
        ["cas", "Tmin", "Tmax", "a0", "a1", "a2", "a3", "a4", "source"],
        sorted(correlations["dippr101"], key=lambda r: (r["cas"], r["source"])),
    )
    counts["cp_liquid"] = _write_csv(
        out / "cp_liquid.csv",
        ["cas", "form", "Tmin", "Tmax", "a0", "a1", "a2", "a3", "a4", "source"],
        sorted(correlations["cp_liquid"], key=lambda r: (r["cas"], r["form"], r["Tmin"])),
    )
    counts["cp_gas"] = _write_csv(
        out / "cp_gas.csv",
        ["cas", "form", "Tmin", "Tmax", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "source"],
        sorted(correlations["cp_gas"], key=lambda r: (r["cas"], r["form"])),
    )
    counts["janaf"] = _write_csv(
        out / "janaf.csv",
        ["cas", "phase", "phase_298", "table", "T", "Cp", "S", "H_H298", "Hf", "Gf", "logKf", "note"],
        sorted(
            (r for r in collected["janaf"] if r["cas"] in kept), key=lambda r: (r["cas"], r["table"], r["T"])
        ),
    )
    _derive_omega(rows, out)  # first: it re-selects, and the checks below must stand last
    _physical_checks(rows, out)
    counts["properties"] = _write_properties(out, rows)
    audit_lines, audit_counts = _audit(rows, species, pubchem, collected["pages"])
    (out / "AUDIT.txt").write_text(
        "Cross-source disagreements found at build time (grade C sources excluded).\n"
        "A line here is not an error in the database: it names a property where two\n"
        "non-estimated sources differ by more than the audit limit; the selected value\n"
        "is the first one listed. Limits: 5 kJ/mol (Hf, Gf), 5 K (Tb, Tm, Tc), 2 bar (Pc).\n\n"
        + "\n".join(OUTVOTED + audit_lines)
        + "\n"
    )
    selected = Counter(r["property"] for r in rows if r["selected"])
    manifest = {
        "built": dt.date.today().isoformat(),
        "chemicals_version": chemicals.__version__,
        "thermo_version": thermo.__version__,
        "nist_pages_parsed": len(collected["pages"]),
        "pubchem_records": len(pubchem),
        "row_counts": counts,
        "species_with_property": dict(sorted(selected.items())),
        "rows_by_source": dict(sorted(Counter(r["source"] for r in rows).items())),
        "rows_by_grade": dict(sorted(Counter(r["grade"] for r in rows).items())),
        "audit": dict(sorted(audit_counts.items())),
        "dropped_at_build": dict(sorted(DROPPED.items())),
        "selections_outvoted": len(OUTVOTED),
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("seed", "tables"))
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    if args.step == "seed":
        return seed(args.paths[0])
    return tables(args.paths[0], args.paths[1])


if __name__ == "__main__":
    sys.exit(main())
