"""Parse NIST WebBook pages and NIST-JANAF tables into plain records (text only).

Pages are untrusted input: they are read as text and matched against a fixed set
of quantity labels; a value that does not parse as a number is dropped, never
guessed. Units are converted by :mod:`ngdesign.uom` from the unit the page states.
"""

from __future__ import annotations

import html
import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from ngdesign.uom.dimension import UomError
from ngdesign.uom.quantity import convert

#: WebBook label -> (canonical property, SI unit stored).
QUANTITY_MAP: dict[str, tuple[str, str]] = {
    "ΔfH°gas": ("Hf_gas", "J/mol"),
    "S°gas": ("S0_gas", "J/(mol K)"),
    "S°gas,1 bar": ("S0_gas", "J/(mol K)"),
    "S°liquid,1 bar": ("S0_liquid", "J/(mol K)"),
    "ΔfH°liquid": ("Hf_liquid", "J/mol"),
    "S°liquid": ("S0_liquid", "J/(mol K)"),
    "ΔfH°solid": ("Hf_solid", "J/mol"),
    "S°solid": ("S0_solid", "J/(mol K)"),
    "S°solid,1 bar": ("S0_solid", "J/(mol K)"),
    "ΔcH°gas": ("Hc_gas", "J/mol"),
    "ΔcH°liquid": ("Hc_liquid", "J/mol"),
    "ΔcH°solid": ("Hc_solid", "J/mol"),
    "Tboil": ("Tb", "K"),
    "Tfus": ("Tm", "K"),
    "Ttriple": ("Tt", "K"),
    "Ptriple": ("Pt", "Pa"),
    "Tc": ("Tc", "K"),
    "Pc": ("Pc", "Pa"),
    "Vc": ("Vc", "m3/mol"),
    "ρc": ("Vc", "m3/mol"),  # stored as the reciprocal, see _quantities
    "ΔvapH°": ("Hvap_298", "J/mol"),
    "ΔsubH°": ("Hsub_298", "J/mol"),
    "ΔfusH": ("Hfus", "J/mol"),
    "ΔfusH°": ("Hfus", "J/mol"),
}

#: WebBook spells molar entropy ``J/mol*K``, meaning J/(mol K).
_UNIT_SPELLINGS = {"J/mol*K": "J/(mol K)", "J/mol K": "J/(mol K)", "l/mol": "L/mol", "mol/l": "mol/L"}

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_TABLE = re.compile(r'<table class="data"[^>]*aria-label="([^"]+)"[^>]*>(.*?)</table>', re.S)
_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
_VALUE = re.compile(rf"^({_NUMBER})(?:\s*±\s*({_NUMBER}))?$")
_RANGE = re.compile(rf"^({_NUMBER})\s*to\s*({_NUMBER})$")


def _text(cell: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", "", cell))
    return re.sub(r"\s+", " ", plain).replace("−", "-").strip()


def _rows(body: str) -> list[list[str]]:
    return [[_text(c) for c in _CELL.findall(row)] for row in _ROW.findall(body)]


@dataclass
class Page:
    """Everything extracted from one WebBook page."""

    cas: str
    name: str = ""
    formula: str = ""
    mw: float | None = None
    inchikey: str = ""
    values: list[dict[str, Any]] = field(default_factory=list)
    shomate: list[dict[str, Any]] = field(default_factory=list)
    antoine: list[dict[str, Any]] = field(default_factory=list)
    hvap_t: list[dict[str, Any]] = field(default_factory=list)
    cp_points: list[dict[str, Any]] = field(default_factory=list)
    hfus_t: list[dict[str, Any]] = field(default_factory=list)


def _section(page: str, anchor: str) -> str:
    start = page.find(f'id="{anchor}"')
    if start < 0:
        return ""
    end = page.find('<h2 id="', start + 10)
    return page[start:] if end < 0 else page[start:end]


def _quantities(out: Page, body: str) -> None:
    rows = _rows(body)
    if not rows:
        return
    header = rows[0]
    if header[:3] != ["Quantity", "Value", "Units"]:
        return
    method_i = header.index("Method") if "Method" in header else None
    ref_i = header.index("Reference") if "Reference" in header else None
    comment_i = header.index("Comment") if "Comment" in header else None
    for row in rows[1:]:
        if len(row) < 3:
            continue
        mapped = QUANTITY_MAP.get(row[0])
        if mapped is None:
            continue
        match = _VALUE.match(row[1].replace(" ", " "))
        if match is None:
            continue
        prop, unit = mapped
        stated = _UNIT_SPELLINGS.get(row[2], row[2])
        try:
            uncertainty = None
            if row[0] == "ρc":
                density = float(convert(float(match.group(1)), stated, "mol/m3"))
                if density <= 0.0:
                    continue
                value = 1.0 / density
                if match.group(2) is not None:
                    uncertainty = value * float(match.group(2)) / float(match.group(1))
            else:
                value = convert(float(match.group(1)), stated, unit)
                if match.group(2) is not None:
                    uncertainty = abs(float(convert(float(match.group(2)), _interval(stated), unit)))
        except (UomError, ZeroDivisionError):
            continue
        method = row[method_i] if method_i is not None and method_i < len(row) else ""
        reference = row[ref_i] if ref_i is not None and ref_i < len(row) else ""
        comment = row[comment_i] if comment_i is not None and comment_i < len(row) else ""
        out.values.append(
            {
                "property": prop,
                "value": float(value),
                "unit": unit,
                "uncertainty": uncertainty,
                "method": method,
                "reference": reference if reference != "N/A" else "",
                "comment": comment[:120],
            }
        )


def _interval(unit: str) -> str:
    """Uncertainties are intervals, never points on an offset scale."""
    return "delta_degC" if unit == "degC" else unit


def _shomate(out: Page, label: str, body: str) -> None:
    phase = label.split()[0].lower()
    rows = _rows(body)
    if not rows or not rows[0] or not rows[0][0].startswith("Temperature"):
        return
    ranges = rows[0][1:]
    table = {r[0]: r[1:] for r in rows[1:] if r}
    for i, window in enumerate(ranges):
        match = _RANGE.match(window)
        if match is None:
            continue
        try:
            coeffs = {k: float(table[k][i]) for k in "ABCDEFGH"}
        except (KeyError, ValueError, IndexError):
            continue
        reference = table.get("Reference", [""] * (i + 1))
        out.shomate.append(
            {
                "phase": {"gas": "gas", "liquid": "liquid", "solid": "solid"}.get(phase, phase),
                "Tmin": float(match.group(1)),
                "Tmax": float(match.group(2)),
                **coeffs,
                "reference": reference[i] if i < len(reference) else "",
            }
        )


def _antoine(out: Page, body: str) -> None:
    rows = _rows(body)
    for row in rows[1:]:
        if len(row) < 5:
            continue
        match = _RANGE.match(row[0])
        if match is None:
            continue
        try:
            a, b, c = float(row[1]), float(row[2]), float(row[3])
        except ValueError:
            continue
        out.antoine.append(
            {
                "Tmin": float(match.group(1)),
                "Tmax": float(match.group(2)),
                "A": a,
                "B": b,
                "C": c,
                "reference": row[4],
            }
        )


def _hvap(out: Page, body: str) -> None:
    rows = _rows(body)
    if not rows or not rows[0] or not rows[0][0].startswith("ΔvapH (kJ/mol)"):
        return
    for row in rows[1:]:
        if len(row) < 4:
            continue
        match = _VALUE.match(row[0])
        temperature = _VALUE.match(row[1])
        if match is None or temperature is None:
            continue
        out.hvap_t.append(
            {"value": float(match.group(1)) * 1000.0, "T": float(temperature.group(1)), "reference": row[3]}
        )


def _cp_points(out: Page, phase: str, body: str) -> None:
    """Tabulated Cp(T) points of one phase: value in J/(mol K) at a stated T."""
    rows = _rows(body)
    if not rows or not rows[0] or not rows[0][0].startswith(f"Cp,{phase} (J/mol*K)"):
        return
    reference = ""
    for row in rows[1:]:
        if len(row) < 2:
            continue
        match = _VALUE.match(row[0])
        temperature = _VALUE.match(row[1])
        if len(row) > 2 and row[2]:
            reference = row[2]
        if match is None or temperature is None:
            continue
        out.cp_points.append(
            {
                "phase": phase,
                "value": float(match.group(1)),
                "T": float(temperature.group(1)),
                "reference": reference,
            }
        )


def _hfus(out: Page, body: str) -> None:
    rows = _rows(body)
    if not rows or not rows[0] or not rows[0][0].startswith("ΔfusH (kJ/mol)"):
        return
    for row in rows[1:]:
        if len(row) < 3:
            continue
        match = _VALUE.match(row[0])
        temperature = _VALUE.match(row[1])
        if match is None or temperature is None:
            continue
        out.hfus_t.append(
            {
                "value": float(match.group(1)) * 1000.0,
                "T": float(temperature.group(1)),
                "reference": row[2] if len(row) == 3 else row[-2],
            }
        )


def parse_page(cas: str, page: str) -> Page:
    """Extract one WebBook page."""
    out = Page(cas=cas)
    title = re.search(r'<h1 id="Top">([^<]+)', page)
    out.name = html.unescape(title.group(1)).strip() if title else ""
    formula = re.search(r"Formula</a>:</strong>\s*(.*?)</li>", page, re.S)
    out.formula = _text(formula.group(1)).replace(" ", "") if formula else ""
    weight = re.search(r"Molecular weight</a>:</strong>\s*([\d.]+)", page)
    out.mw = float(weight.group(1)) if weight else None
    key = re.search(r'InChIKey:</strong>\s*<span class="inchi-text">([A-Z-]+)<', page)
    out.inchikey = key.group(1) if key else ""
    for label, body in _TABLE.findall(page):
        if label == "One dimensional data":
            _quantities(out, body)
        elif "(Shomate Equation)" in label:
            _shomate(out, label, body)
        elif label == "Antoine Equation Parameters":
            _antoine(out, body)
        elif label == "Enthalpy of vaporization":
            _hvap(out, body)
        elif label == "Constant pressure heat capacity of gas":
            _cp_points(out, "gas", body)
        elif label == "Constant pressure heat capacity of liquid":
            _cp_points(out, "liquid", body)
        elif label == "Constant pressure heat capacity of solid":
            _cp_points(out, "solid", body)
        elif label == "Enthalpy of fusion":
            _hfus(out, body)
    return out


def parse_henry(page: str) -> tuple[float, float, int] | None:
    """(k°H in mol/(kg bar), d ln kH/d(1/T) in K, entries used) from a WebBook page.

    The medians over the rows that state both; the page lists several evaluations
    and none is marked preferred. None when no row states both.
    """
    pairs: list[tuple[float, float]] = []
    for label, body in _TABLE.findall(page):
        if not label.startswith("Henry's Law constant"):
            continue
        for row in _rows(body)[1:]:
            if len(row) < 2:
                continue
            k = _VALUE.match(row[0])
            slope = _VALUE.match(row[1])
            if k is not None and slope is not None and float(k.group(1)) > 0.0:
                pairs.append((float(k.group(1)), float(slope.group(1))))
    if not pairs:
        return None
    return statistics.median(p[0] for p in pairs), statistics.median(p[1] for p in pairs), len(pairs)


_JANAF_INDEX = re.compile(
    r"<tr><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
    r'<td><a href="([A-Za-z]+-\d{3})\.html">',
)


def parse_janaf_index(text: str) -> list[dict[str, str]]:
    """Rows of one element index page: cas, formula, name, phase, table id."""
    return [
        {
            "cas": m[0].strip(),
            "formula": m[1].strip(),
            "name": html.unescape(m[2]).strip(),
            "phase": m[3].strip(),
            "table": m[4],
        }
        for m in _JANAF_INDEX.findall(text)
    ]


def parse_janaf_table(text: str) -> list[dict[str, Any]]:
    """Numeric rows of one JANAF table, kJ columns converted to J.

    Columns: T, Cp, S, -[G-H(Tr)]/T, H-H(Tr), ΔfH, ΔfG, log Kf. A row needs T, Cp,
    S and H-H(Tr). A phase transition appears as two rows at one T; the transition
    label JANAF prints there ("CRYSTAL <--> LIQUID") is kept in ``note``.
    """
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[2:]:
        cells = line.split("\t")
        if len(cells) < 5:
            continue
        try:
            T, cp, s, hh = float(cells[0]), float(cells[1]), float(cells[2]), float(cells[4])
        except ValueError:
            continue
        if T < 100.0:
            continue
        row: dict[str, Any] = {"T": T, "Cp": cp, "S": s, "H_H298": hh * 1000.0, "note": ""}
        for key, index, scale in (("Hf", 5, 1000.0), ("Gf", 6, 1000.0), ("logKf", 7, 1.0)):
            if index < len(cells):
                try:
                    row[key] = float(cells[index]) * scale
                except ValueError:
                    if "<-->" in cells[index]:
                        row["note"] = cells[index].strip()
        rows.append(row)
    return rows


def reference_phase_298(rows: list[dict[str, Any]]) -> str:
    """Phase of a JANAF reference-state table at 298.15 K, read from its transitions.

    The first transition above 298.15 K names the phase it leaves. With no transition
    the table is one phase throughout: a gas, unless Cp at 298.15 K lies below the
    monatomic ideal-gas floor 5R/2 (20.8 J/(mol K)), as graphite's does.
    """
    for row in rows:
        if row["T"] > 298.15 and "<-->" in row["note"]:
            left = row["note"].split("<-->")[0].strip().upper()
            if left.startswith("LIQUID"):
                return "liquid"
            if left.startswith("IDEAL GAS"):
                return "gas"
            return "solid"
    at_298 = next((row for row in rows if row["T"] == 298.15), None)
    return "solid" if at_298 is not None and at_298["Cp"] < 20.0 else "gas"
