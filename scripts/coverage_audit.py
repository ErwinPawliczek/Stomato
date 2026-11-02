"""Write docs/coverage-gaps.md: what the project lists against what is implemented.

Lists read: ``docs/thermo-catalogue-plan.md`` (168 property methods) and the unit
catalogue ``data/unit_models/`` (83 rows and their rigour ladders). Implementation
read: the plugin registry and the thermo catalogue rows. A plan method counts as
closed only when it maps to a registered row that is not a refusal row, so an
unmapped name shows up as a gap instead of passing quietly.

    python scripts/coverage_audit.py          # rewrite the document
    python scripts/coverage_audit.py --check  # exit 1 when it is stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from ngdesign import registry

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "coverage-gaps.md"

#: Rows that register but refuse at first use: listed, not implemented.
REFUSAL_ROWS = {"eos_cg", "soft_saft"}

#: Plan names that are not a normalised form of a row name or id.
PLAN_TO_ID = {
    "PR volume-translated (Peneloux)": "pr-peneloux",
    "SRK volume-translated (Peneloux)": "srk-peneloux",
    "PR-BM (Aspen PR-BM)": "pr-bm",
    "RKS-BM (Aspen RKS-BM)": "rks-bm",
    "IAPWS-95 steam": "iapws95",
    "IAPWS-IF97 steam": "iapws_if97",
    "ASME/NBS steam": "asme_steam",
    "CoolProp pure Helmholtz (Span-Wagner family)": "coolprop_heos",
    "MBWR (methane, nitrogen...)": "mbwr",
    "BWR-Lee-Starling": "bwr_ls",
    "Lee-Kesler-Plöcker": "lee-kesler-ploecker",
    "Henry's law (Sander) ideal liquid": "henry-sander",
    "Ideal gas / ideal liquid with Lee-Kesler departures": "ideal-lk",
    "multi-fluid Helmholtz via teqp": "multifluid",
    "GERG via teqp (cross-check of D)": "gerg2008_teqp",
    "Kent-Eisenberg amines (done)": "amine_ke",
    "electrolyte-NRTL amines (done)": "amine_enrtl",
    "general electrolyte NRTL": "enrtl_nacl_water",
    "Pitzer": "pitzer_nacl_water",
    "extended UNIQUAC": "ext_uniquac_nacl_water",
    "sour water (API)": "sour_water",
    "Solids (ideal solid + solubility product)": "ideal_solid",
    "Hayden-O'Connell carboxylic acid dimerisation": "hoc_dimer",
    "HF hexamerisation model": "hf_hexamer",
    "Polymer UNIFAC-FV": "unifac_fv",
    "PR with Boston-Mathias extrapolation above Tc": "pr-boston-mathias",
    "SRK with Boston-Mathias extrapolation above Tc": "srk-boston-mathias",
    "Ideal + Henry for dilute gases in water": "henry-sander",
}
_VAPOUR = {
    "ideal gas": "ig",
    "virial Hayden-O'Connell": "hoc",
    "virial Nothnagel": "nothnagel",
    "RK vapour": "rk",
    "PR vapour": "pr",
}
_LIQUID = {
    "NRTL": "nrtl",
    "UNIQUAC": "uniquac",
    "Wilson": "wilson",
    "van Laar": "vanlaar",
    "Margules": "margules",
    "Regular Solution": "regular_solution",
    "UNIFAC": "unifac",
    "UNIFAC-Dortmund": "unifac_dortmund",
    "UNIFAC-PSRK": "unifac_psrk",
    "UNIFAC-NIST": "unifac_nist",
    "UNIFAC-LLE": "unifac_lle",
    "UNIFAC-Lyngby": "unifac_lyngby",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _yaml_rows(folder: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((ROOT / "data" / folder).glob("*.yaml")):
        if not path.name.startswith("_"):
            rows.extend(yaml.safe_load(path.read_text()))
    return rows


def plan_methods() -> list[tuple[str, str]]:
    """(section, method) for every row of the thermo plan's catalogue tables."""
    out: list[tuple[str, str]] = []
    section = ""
    for line in (ROOT / "docs" / "thermo-catalogue-plan.md").read_text().splitlines():
        heading = re.match(r"### (.*)", line)
        if heading:
            section = heading.group(1).split(" — ")[0].split(" (")[0]
        row = re.match(r"\| (\d+) \| ([^|]+) \|", line)
        if row and section:
            out.append((section, row.group(2).strip()))
    return out


def plan_id(method: str, ids: dict[str, str]) -> str | None:
    """The catalogue row a plan method maps to, or None."""
    if method in PLAN_TO_ID:
        return PLAN_TO_ID[method]
    parts = [p.strip() for p in method.split(" / ")]
    if len(parts) == 2 and parts[0] in _LIQUID and parts[1] in _VAPOUR:
        row = f"{_LIQUID[parts[0]]}_{_VAPOUR[parts[1]]}"
        if row == "nrtl_pr":
            row = "nrtl"  # the original row is NRTL liquid + PR vapour
        return row
    return ids.get(_norm(method))


def build() -> str:
    registry.discover()
    registered_units = set(registry.available("unit"))
    registered_thermo = set(registry.available("thermo"))
    unit_rows = _yaml_rows("unit_models")
    thermo_rows = _yaml_rows("thermo_models")
    ids = {_norm(r["name"]): r["id"] for r in thermo_rows} | {_norm(r["id"]): r["id"] for r in thermo_rows}

    missing_units = [r for r in unit_rows if r["id"] not in registered_units]
    planned = [
        (r["id"], level, str(spec.get("note", "")))
        for r in unit_rows
        if r["id"] in registered_units
        for level, spec in r["levels"].items()
        if spec["status"] == "planned"
    ]
    methods = plan_methods()
    open_methods: list[tuple[str, str, str]] = []
    for section, method in methods:
        row = plan_id(method, ids)
        if row is None or row not in registered_thermo:
            open_methods.append((section, method, "no catalogue row"))
        elif row in REFUSAL_ROWS:
            open_methods.append((section, method, f"`{row}` is a refusal row"))
    statuses: dict[str, int] = {}
    for row in thermo_rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    experimental = [
        r["id"] for r in thermo_rows if r["status"] == "experimental" and r["id"] not in REFUSAL_ROWS
    ]

    lines = [
        "# Coverage gaps",
        "",
        "GENERATED by `scripts/coverage_audit.py`; edit the catalogues, not this file. It compares what",
        "the project lists (`data/unit_models/`, `docs/thermo-catalogue-plan.md`) with what the plugin",
        "registry implements. A level or method listed here is listed but not implemented.",
        "",
        "## Summary",
        "",
        "| | listed | implemented | open |",
        "|---|---|---|---|",
        f"| Unit rows | {len(unit_rows)} | {len(unit_rows) - len(missing_units)} | {len(missing_units)} |",
        f"| Planned rigour levels on implemented units | | | {len(planned)} |",
        f"| Property methods in the plan | {len(methods)} | {len(methods) - len(open_methods)} "
        f"| {len(open_methods)} |",
        "",
        f"Catalogue rows by status: {', '.join(f'{v} {k}' for k, v in sorted(statuses.items()))}.",
        "",
        "## Unit rows with no implementation",
        "",
    ]
    if missing_units:
        lines += ["| unit | family | level | note |", "|---|---|---|---|"]
        for row in missing_units:
            for level, spec in row["levels"].items():
                lines.append(f"| `{row['id']}` | {row['family']} | {level} | {spec.get('note', '')} |")
    else:
        lines.append("None.")
    lines += ["", "## Planned levels on implemented units", ""]
    if planned:
        lines += ["| unit | level | note |", "|---|---|---|"]
        lines += [f"| `{unit}` | {level} | {note} |" for unit, level, note in planned]
    else:
        lines.append("None.")
    lines += ["", "## Property methods listed but not closed", ""]
    if open_methods:
        lines += ["| plan section | method | state |", "|---|---|---|"]
        lines += [f"| {section} | {method} | {state} |" for section, method, state in open_methods]
    else:
        lines.append("None.")
    lines += [
        "",
        "## Implemented but still experimental",
        "",
        "These rows run but have not met the validation gate; `data/thermo_models/` says why.",
        "",
        ", ".join(f"`{row}`" for row in experimental) or "None.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = build()
    if args.check:
        if not TARGET.exists() or TARGET.read_text() != text:
            print("docs/coverage-gaps.md is stale: run scripts/coverage_audit.py")
            return 1
        return 0
    TARGET.write_text(text)
    print(text.split("## Unit rows")[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
