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
from ngdesign.data.formula import FormulaError, parse_formula  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_cea import parse_thermo_inp  # noqa: E402
from parse_nist import (  # noqa: E402
    Page,
    parse_henry,
    parse_janaf_index,
    parse_janaf_table,
    parse_page,
    reference_phase_298,
)
from parse_thermoml import iter_archive  # noqa: E402

BANK = Path(chemicals.__file__).resolve().parent
THERMO = Path(thermo.__file__).resolve().parent

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
    "sander": 10,
    "nasa_cea": 4,
    "coolprop_ig": 4,  # ideal-gas Cp0 of reference EOS (cp0_eos.csv; ranks no property row)
    "thermoml": 9,  # ideal-gas Cp(T) points (cp_gas_points.csv; ranks no property row)
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
    "sander": "B",
    "nasa_cea": "B",
    "coolprop_ig": "B",
    "thermoml": "B",
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


SANDER_TABLE = "Interaction Parameters/Sander_henry_T_dep.json"
WATER_KG_PER_MOL = 0.018015268  # IAPWS-95 molar mass of water


def _collect_sander(rows: Rows) -> None:
    """Dissolved-gas standard states from Sander's compilation, as shipped in ``thermo``.

    H in Pa on the mole-fraction scale, ln H = A + B/T + C ln T + D T + E/T² + F T²
    (``chemicals.solubility.Henry_pressure``). For dilute solute, k°H = 1e5/(H·M_w) in
    mol/(kg bar); ΔG°soln = −RT ln k°H and ΔH°soln = R·d ln H/d(1/T) at 298.15 K, then
    added to the gas's selected values as for the WebBook Henry data. Only the
    temperature-dependent sets are used: a solution enthalpy is needed for S°.
    """
    table = json.loads((THERMO / SANDER_TABLE).read_text())["data"]
    gas_rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows.rows:
        if row["property"] in ("Hf_gas", "S0_gas"):
            gas_rows[(row["cas"], row["property"])].append(row)
    T = 298.15
    for pair, p in sorted(table.items()):
        cas, solvent = pair.split()
        if solvent != "7732-18-5":
            continue
        hf_rows, s_rows = gas_rows.get((cas, "Hf_gas")), gas_rows.get((cas, "S0_gas"))
        if not hf_rows or not s_rows:
            continue
        ln_h = p["A"] + p["B"] / T + p["C"] * math.log(T) + p["D"] * T + p["E"] / T**2 + p["F"] * T**2
        # d ln H / d(1/T) at T, from the same expression
        slope = p["B"] - p["C"] * T - p["D"] * T**2 - 2.0 * p["E"] / T + 2.0 * p["F"] * T**3
        k = 1e5 / (math.exp(ln_h) * WATER_KG_PER_MOL)
        dh = sc.R * slope
        dg = -sc.R * T * math.log(k)
        hf = min(hf_rows, key=lambda r: SOURCE_RANK[r["source"]])["value"]
        s0 = min(s_rows, key=lambda r: SOURCE_RANK[r["source"]])["value"]
        note = f"gas + Sander (k {k:.4g} mol/(kg bar); dlnH/d(1/T) {slope:.4g} K)"
        rows.add(cas, "Hf_aq", hf + dh, "sander", reference=note)
        rows.add(cas, "S0_aq", s0 + (dh - dg) / T, "sander", reference=note)


SHOMATE_SNAPSHOT = "Heat Capacity/webbook_shomate_coefficients.json"


def _snapshot_shomate(kept: set[str]) -> list[dict[str, Any]]:
    """Shomate Cp pieces of the WebBook snapshot: A-E only, in [solid, liquid, gas] order.

    ``chemicals`` stores them converted to T in kelvin (``chemicals.heat_capacity.Shomate``),
    not in the WebBook's t = T/1000, so they evaluate through that function.

    The snapshot keeps no F, G, H, so H and S are anchored at runtime on the selected
    S°298 by integrating Cp, the way the liquid Cp fits are.
    """
    out: list[dict[str, Any]] = []
    for cas, phases in json.loads((BANK / SHOMATE_SNAPSHOT).read_text()).items():
        if cas not in kept:
            continue
        for phase, pieces in zip(("solid", "liquid", "gas"), phases, strict=True):
            for piece in pieces or []:
                Tmin, Tmax, A, B, C, D, E = piece
                out.append(
                    {
                        "cas": cas,
                        "phase": phase,
                        "Tmin": Tmin,
                        "Tmax": Tmax,
                        "A": A,
                        "B": B,
                        "C": C,
                        "D": D,
                        "E": E,
                        "F": None,
                        "G": None,
                        "H": None,
                        "source": "nist_snapshot",
                        "reference": "WebBook Shomate Cp (snapshot)",
                    }
                )
    return out


_CEA_PHASE_TAG = re.compile(r"^(.*?)(\([^()]*\))?$")


def _cea_records(cache: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """NASA CEA 9-coefficient records mapped to a CAS and a phase.

    A record is named by formula, with an isomer name after a comma
    ("C4H10,n-butane"). The isomer name is tried first, then the formula, and the match
    must have the record's formula. An ambiguous formula is skipped, never guessed, and
    so are ions and the "Inert" copies.
    """
    path = cache / "cea" / "thermo.inp"
    if not path.exists():
        return {}
    mapped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in parse_thermo_inp(path.read_text(encoding="utf8", errors="replace")):
        name = record["name"]
        base, _, alias = name.partition(",")
        match = _CEA_PHASE_TAG.match(base)
        formula = match.group(1) if match else base
        if name.startswith("Inert") or re.search(r"[+-]$", formula) or name == "e-":
            continue
        phase = "gas" if record["phase_flag"] == 0 else ("liquid" if "(L)" in base else "solid")
        species = None
        if alias:
            try:
                species = chemdb.find(alias)
            except chemdb.ChemDbError:
                species = None
        try:
            if species is None:
                species = chemdb.find(formula)
            if parse_formula(species.formula).hill != parse_formula(formula).hill:
                DROPPED["cea_formula_differs"] += 1
                continue
        except (chemdb.ChemDbError, FormulaError):
            DROPPED["cea_unmatched"] += 1
            continue
        held = mapped.get((species.cas, phase))
        if held is None:
            mapped[(species.cas, phase)] = {**record, "pieces": list(record["pieces"])}
        elif abs(held["pieces"][-1]["Tmax"] - record["pieces"][0]["Tmin"]) < 1e-6:
            # one phase split across records at a transition (iron's lambda point): join them
            held["pieces"] += record["pieces"]
    return mapped


#: The latest opening temperature at which a CEA record still speaks for 298.15 K.
CEA_LOWEST_START = 300.0


def _covers_298(record: dict[str, Any]) -> bool:
    """Whether a record's polynomials reach 298.15 K.

    Only then is its header enthalpy ΔfH°298. For a phase that cannot exist at 298.15 K
    the header holds an assigned value instead: ice (200-273.15 K) carries -299.1 kJ/mol
    while its polynomial gives -293.7 kJ/mol at 273.15 K, liquid water less the enthalpy
    of fusion.
    """
    # Most records open at 300 K, not 298.15 K, yet define the header as ΔfH°298; their
    # 1.85 K extrapolation is negligible. A record that ends below 298.15 K cannot.
    return bool(record["pieces"][0]["Tmin"] <= CEA_LOWEST_START and record["pieces"][-1]["Tmax"] >= 298.15)


def _collect_cea(rows: Rows, cea: dict[tuple[str, str], dict[str, Any]]) -> None:
    """ΔfH°298 as CEA states it, with its reference text, where the record reaches 298.15 K."""
    for (cas, phase), record in cea.items():
        if _covers_298(record):
            rows.add(cas, f"Hf_{phase}", record["hf298"], "nasa_cea", reference=record["reference"])
        else:
            DROPPED["cea_record_not_at_298"] += 1


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


#: CoolProp's BibTeX library, shipped in the installed package: resolves the EOS keys.
COOLPROP_BIB = Path(CP.__file__).resolve().parent / "CoolPropBibTeXLibrary.bib"
_BIB_FIELD = re.compile(r"^\s*(\w+)\s*=\s*\{(.*)\},?\s*$")


def _coolprop_bib() -> dict[str, dict[str, str]]:
    """BibTeX entries of the CoolProp library, key -> lower-case field map."""
    entries: dict[str, dict[str, str]] = {}
    key: str | None = None
    for line in COOLPROP_BIB.read_text(encoding="utf-8", errors="replace").splitlines():
        head = re.match(r"^@\w+\{([^,]+),", line)
        if head:
            key = head.group(1).strip()
            entries[key] = {}
            continue
        field = _BIB_FIELD.match(line)
        if key is not None and field:
            entries[key][field.group(1).lower()] = field.group(2).replace("{", "").replace("}", "")
    return entries


def _citation(entry: dict[str, str], key: str) -> str:
    """One-line citation of a CoolProp BibTeX entry, keeping its key."""
    venue = entry.get("journal", "") or entry.get("school", "")
    year = f"({entry['year']})" if "year" in entry else ""
    tail = " ".join(x for x in (entry.get("volume", ""), year) if x)
    text = ", ".join(
        x for x in (entry.get("author", ""), entry.get("title", ""), venue, tail, entry.get("pages", "")) if x
    )
    if entry.get("doi"):
        text += f", doi:{entry['doi']}"
    return f"{text} [CoolProp key {key}]" if text else f"CoolProp key {key}"


def _cp0_terms(alpha0: list[dict[str, Any]], t_red: float) -> list[tuple[str, float, float]] | None:
    """Ideal-gas Cp0/R terms of one CoolProp alpha0 list, or None for an unhandled term type.

    cp0/R = sum(const a) + sum(pe: a y^2 e^y/(e^y-1)^2, y = b/T)
            + sum(cosh: a (y/cosh y)^2, y = b/T) + sum(power: a T^b).
    The ln(delta) term of the ideal-gas Helmholtz energy gives the constant 1;
    a*ln(tau) gives cv0/R = a.
    """
    terms: list[tuple[str, float, float]] = [("const", 1.0, 0.0)]
    for term in alpha0:
        kind = term["type"]
        if kind in ("IdealGasHelmholtzLead", "IdealGasHelmholtzEnthalpyEntropyOffset"):
            continue
        if kind == "IdealGasHelmholtzLogTau":
            terms.append(("const", float(term["a"]), 0.0))
        elif kind == "IdealGasHelmholtzPlanckEinstein":
            terms += [("pe", float(n), float(t) * t_red) for n, t in zip(term["n"], term["t"], strict=True)]
        elif kind == "IdealGasHelmholtzPlanckEinsteinFunctionT":
            terms += [("pe", float(n), float(v)) for n, v in zip(term["n"], term["v"], strict=True)]
        elif kind == "IdealGasHelmholtzPower":
            # n tau^t, tau = Tr/T: cv0/R = -tau^2 d2/dtau2 = -n t (t - 1) Tr^t T^-t
            for n, t in zip(term["n"], term["t"], strict=True):
                coeff = -float(n) * float(t) * (float(t) - 1.0) * t_red ** float(t)
                if coeff != 0.0:
                    terms.append(("power", coeff, -float(t)))
        elif kind == "IdealGasHelmholtzCP0Constant":
            terms.append(("const", float(term["cp_over_R"]), 0.0))
        elif kind == "IdealGasHelmholtzCP0PolyT":
            for c, t in zip(term["c"], term["t"], strict=True):
                terms.append(("const", float(c), 0.0) if float(t) == 0.0 else ("power", float(c), float(t)))
        elif kind == "IdealGasHelmholtzCP0AlyLee":
            # Aly & Lee (1981): A + B ((C/T)/sinh(C/T))^2 + D ((E/T)/cosh(E/T))^2; the sinh
            # term is a Planck-Einstein term of characteristic temperature 2C.
            a, b, c, d, e = (float(x) for x in term["c"])
            terms += [("const", a, 0.0), ("pe", b, 2.0 * c), ("cosh", d, e)]
        else:
            return None
    return terms


def _cp0_over_r(terms: list[tuple[str, float, float]], T: float) -> float:
    """cp0/R of a term list at T (the form in :func:`_cp0_terms`)."""
    total = 0.0
    for kind, a, b in terms:
        if kind == "const":
            total += a
        elif kind == "pe":
            y = b / T
            total += a * y * y * math.exp(-y) / (1.0 - math.exp(-y)) ** 2
        elif kind == "cosh":
            y = b / T
            total += a * (y / math.cosh(y)) ** 2
        else:
            total += a * T**b
    return total


def _coolprop_cp0(kept: set[str]) -> list[dict[str, Any]]:
    """Ideal-gas Cp0(T) of CoolProp's reference equations of state, one row per term.

    Each EOS's ideal-gas part is the Cp0 correlation its paper publishes (cited per
    row through CoolProp's BibTeX library). Every reconstruction is checked against
    CoolProp's own Cp0 at up to five temperatures before it is kept.
    """
    bib = _coolprop_bib()
    out: list[dict[str, Any]] = []
    for fluid in sorted(CP.get_global_param_string("fluids_list").split(",")):
        cas = CP.get_fluid_param_string(fluid, "CAS")
        if cas not in kept:
            continue
        eos = json.loads(CP.get_fluid_param_string(fluid, "JSON"))[0]["EOS"][0]
        terms = _cp0_terms(eos["alpha0"], float(eos["STATES"]["reducing"]["T"]))
        if terms is None:
            DROPPED["coolprop_cp0_unhandled_term"] += 1
            continue
        tmin, tmax = float(eos["Ttriple"]), float(eos["T_max"])
        gas_constant = float(eos["gas_constant"])
        ok = True
        state = CP.AbstractState("HEOS", fluid)
        for T in (tmin, 298.15, 0.5 * (tmin + tmax), 0.25 * tmin + 0.75 * tmax, tmax):
            if not tmin <= T <= tmax:
                continue
            state.update(CP.DmolarT_INPUTS, 1e-6, T)  # dilute gas: no phase or melting checks
            ref = float(state.cp0molar())
            if abs(gas_constant * _cp0_over_r(terms, T) / ref - 1.0) > 1e-9:
                ok = False
        if not ok:
            DROPPED["coolprop_cp0_check_failed"] += 1
            continue
        key = eos.get("BibTeX_CP0") or eos.get("BibTeX_EOS")
        version = CP.get_global_param_string("version")
        reference = f"CoolProp {version} {fluid}: " + _citation(bib.get(key, {}), key)
        for kind, a, b in terms:
            out.append(
                {
                    "cas": cas,
                    "term": kind,
                    "a": a,
                    "b": b,
                    "R": gas_constant,
                    "Tmin": tmin,
                    "Tmax": tmax,
                    "source": "coolprop_ig",
                    "reference": reference,
                }
            )
    return out


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
    cea = _cea_records(cache)
    _collect_cea(rows, cea)
    names = _collect_bundled(rows)
    _collect_coolprop(rows)
    _constants(rows)
    _collect_henry(rows, cache)
    _collect_sander(rows)
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
    return {"rows": rows.rows, "pages": pages, "janaf": janaf_rows, "species": species, "cea": cea}


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
    crawled = {(row["cas"], row["phase"]) for row in shomate}
    shomate += [row for row in _snapshot_shomate(kept) if (row["cas"], row["phase"]) not in crawled]
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


THERMOML_ARCHIVE = "thermoml/ThermoML.v2020-09-30.tgz"


def _cp_gas_points(
    cache: Path, pages: list[Page], species: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Tabulated ideal-gas Cp(T): WebBook gas tables and ThermoML ideal-gas points.

    One row per stated point. WebBook rows keep the page's reference for the table;
    ThermoML rows are matched to a species by standard InChIKey and cite the article
    (first author, year, DOI) and the method the archive records.
    """
    points: list[dict[str, Any]] = []
    for page in pages:
        if page.cas not in species:
            continue
        for point in page.cp_points:
            if point["phase"] == "gas":
                points.append(
                    {
                        "cas": page.cas,
                        "T": point["T"],
                        "Cp": point["value"],
                        "source": "nist",
                        "reference": point["reference"],
                    }
                )
    archive = cache / THERMOML_ARCHIVE
    if archive.exists():
        by_key: dict[str, list[str]] = defaultdict(list)
        for cas, record in species.items():
            if record.get("inchikey"):
                by_key[str(record["inchikey"])].append(cas)
        for point in iter_archive(archive):
            matches = by_key.get(point["inchikey"], [])
            if not matches:
                DROPPED["thermoml_point_without_species"] += 1
            for cas in matches:
                points.append(
                    {
                        "cas": cas,
                        "T": point["T"],
                        "Cp": point["Cp"],
                        "uncertainty": point["uncertainty"],
                        "source": "thermoml",
                        "reference": f"{point['first_author']} {point['year']}; doi:{point['doi']}; "
                        f"{point['method']} (ThermoML)",
                    }
                )
    return sorted(points, key=lambda r: (r["cas"], r["source"], r["reference"], r["T"]))


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


def _cea_rows(cea: dict[tuple[str, str], dict[str, Any]], kept: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for (cas, phase), record in sorted(cea.items()):
        if cas not in kept or not _covers_298(record):
            continue
        for piece in record["pieces"]:
            a, b = piece["a"], piece["b"]
            out.append(
                {
                    "cas": cas,
                    "phase": phase,
                    "Tmin": piece["Tmin"],
                    "Tmax": piece["Tmax"],
                    **{f"a{i + 1}": a[i] for i in range(7)},
                    "b1": b[0],
                    "b2": b[1],
                    "hf298": record["hf298"],
                    "reference": record["reference"].replace(",", ";")[:80],
                }
            )
    return out


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


#: Relative Cp0 disagreement above which a reference-EOS ideal-gas part is listed in AUDIT.txt.
CP0_AUDIT_LIMIT = 0.02


def _audit_cp0(out: Path) -> tuple[list[str], Counter[str]]:
    """Reference-EOS Cp0 (cp0_eos.csv) against the gas model's own Cp(T) source.

    Run on the tables just written (like :func:`_derive_omega`). The EOS term set is
    only the fallback shape, so a disagreement never changes a selection; it is
    listed so the conflict stays visible. Compared at 300, 400 and 500 K inside both
    windows; species without a gas model (no stated enthalpy of formation) are skipped.
    """
    lines: list[str] = []
    counts: Counter[str] = Counter()
    if out.resolve() != (chemdb.DATA_DIR / "chemdb").resolve():
        return lines, counts
    for cached in (chemdb._grouped, chemdb._properties, chemdb._species):  # noqa: SLF001
        cached.cache_clear()
    from ngdesign.data import species_models  # noqa: PLC0415 - reads the tables just written

    for cas in sorted({r["cas"] for r in chemdb._rows("cp0_eos.csv")}):  # noqa: SLF001
        terms = chemdb.cp0_eos(cas)
        eos_curve = species_models._Cp0EosCurve(terms, 0.0)  # noqa: SLF001
        try:
            model = species_models.species_thermo(cas, "gas")
        except chemdb.MissingPropertyError:
            continue
        if model.curve.name.startswith("cp0_eos"):
            continue
        counts["cp0_compared"] += 1
        for T in (300.0, 400.0, 500.0):
            lo = max(model.curve.tmin, eos_curve.tmin)
            hi = min(model.curve.tmax, eos_curve.tmax)
            if lo <= T <= hi:
                ratio = eos_curve.cp(T) / model.curve.cp(T) - 1.0
                if abs(ratio) > CP0_AUDIT_LIMIT:
                    counts["conflict_Cp0"] += 1
                    lines.append(
                        f"Cp_gas(T) {cas}: {model.curve.name} {model.curve.cp(T):.4g} vs coolprop_ig "
                        f"{eos_curve.cp(T):.4g} J/(mol K) at {T:g} K ({100.0 * ratio:+.1f} %)"
                    )
                    break
    return lines, counts


#: Window in which a tabulated gas Cp(T) is held against the gas model's own source:
#: the range every fit in this database is made for (TRC fits misbehave below it).
CP_TABLE_AUDIT_WINDOW = (298.15, 1000.0)


def _audit_cp_tables(out: Path) -> tuple[list[str], Counter[str]]:
    """Each tabulated gas Cp(T) (cp_gas_points.csv) against the species' selected gas model.

    Run on the tables just written, like :func:`_audit_cp0`. A table is the gas shape only
    where no other Cp source exists, so a disagreement changes no selection. Every node
    inside :data:`CP_TABLE_AUDIT_WINDOW` and the model's range is compared; the worst one
    beyond :data:`CP0_AUDIT_LIMIT` is listed. Species whose model is the table itself, or
    that have no gas model, are skipped.
    """
    lines: list[str] = []
    counts: Counter[str] = Counter()
    if out.resolve() != (chemdb.DATA_DIR / "chemdb").resolve():
        return lines, counts
    for cached in (chemdb._grouped, chemdb._properties, chemdb._species):  # noqa: SLF001
        cached.cache_clear()
    from ngdesign.data import species_models  # noqa: PLC0415 - reads the tables just written

    for cas in sorted({r["cas"] for r in chemdb._rows("cp_gas_points.csv")}):  # noqa: SLF001
        try:
            model = species_models.species_thermo(cas, "gas")
        except chemdb.MissingPropertyError:
            continue
        if model.curve.name.startswith("cp_table") or model.curve.name == "constant_cp":
            continue
        lo = max(model.curve.tmin, CP_TABLE_AUDIT_WINDOW[0])
        hi = min(model.curve.tmax, CP_TABLE_AUDIT_WINDOW[1])
        for (source, reference), points in chemdb.cp_gas_points(cas).items():
            compared = [(float(p["T"]), float(p["Cp"])) for p in points if lo <= float(p["T"]) <= hi]
            if not compared:
                continue
            counts["cp_table_compared"] += 1
            T, cp = max(compared, key=lambda tc: abs(tc[1] / model.curve.cp(tc[0]) - 1.0))
            ratio = cp / model.curve.cp(T) - 1.0
            if abs(ratio) > CP0_AUDIT_LIMIT:
                counts["conflict_Cp_table"] += 1
                lines.append(
                    f"Cp_gas(T) {cas}: {model.curve.name} {model.curve.cp(T):.4g} vs {source} table "
                    f"({reference}) {cp:.4g} J/(mol K) at {T:g} K ({100.0 * ratio:+.1f} %)"
                )
    return lines, counts


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
    counts["nasa9"] = _write_csv(
        out / "nasa9.csv",
        [
            "cas",
            "phase",
            "Tmin",
            "Tmax",
            "a1",
            "a2",
            "a3",
            "a4",
            "a5",
            "a6",
            "a7",
            "b1",
            "b2",
            "hf298",
            "reference",
        ],
        _cea_rows(collected["cea"], kept),
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
    counts["cp_gas_points"] = _write_csv(
        out / "cp_gas_points.csv",
        ["cas", "T", "Cp", "uncertainty", "source", "reference"],
        _cp_gas_points(cache, collected["pages"], species),
    )
    counts["cp0_eos"] = _write_csv(
        out / "cp0_eos.csv",
        ["cas", "term", "a", "b", "R", "Tmin", "Tmax", "source", "reference"],
        _coolprop_cp0(kept),
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
    cp0_lines, cp0_counts = _audit_cp0(out)
    audit_lines += cp0_lines
    audit_counts.update(cp0_counts)
    table_lines, table_counts = _audit_cp_tables(out)
    audit_lines += table_lines
    audit_counts.update(table_counts)
    (out / "AUDIT.txt").write_text(
        "Cross-source disagreements found at build time (grade C sources excluded).\n"
        "A line here is not an error in the database: it names a property where two\n"
        "non-estimated sources differ by more than the audit limit; the selected value\n"
        "is the first one listed. Limits: 5 kJ/mol (Hf, Gf), 5 K (Tb, Tm, Tc), 2 bar (Pc),\n"
        "2 % (reference-EOS ideal-gas Cp0, and tabulated gas Cp(T) between 298.15 and\n"
        "1000 K, against the gas model's own Cp source, which stays the selected shape).\n\n"
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
