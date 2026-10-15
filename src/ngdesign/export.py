"""Sheet export (B-07 addendum): the engineering sheet as CSV or HTML.

Stream-table cells come from the CLI demo's own formatter (``cli._cell`` and
``cli._port``, imported — not re-implemented) so unit conversion lives in
exactly one place and the export can never drift from ``index.html``. The only
value-level deviation is deliberate: CSV has no markup, so the CLI's
``&mdash;`` missing-value placeholder becomes an empty cell — the B-07
addendum's parity rule is value parity, and ``&mdash;`` is markup.

The B-07 sheet engine (``ngdesign.variables``, addressed formula cells) has
not merged; the export degrades gracefully to streams + datasheets. When the
engine lands it can add an addressed-cells section without touching these
serializers' callers.

The export is a pure function of :class:`SolvedFlowsheet` — no I/O, no
timestamps, no ordering beyond the flowsheet's own — so two solves of the
same flowsheet produce byte-identical files.
"""

from __future__ import annotations

import csv
import html
from io import StringIO
from typing import Literal

from ngdesign.cli import _cell, _port
from ngdesign.contracts import SolvedFlowsheet

#: Sections the export can include, and the ``scope`` query values that pick them.
Scope = Literal["streams", "datasheets", "all"]
SCOPES: tuple[Scope, ...] = ("streams", "datasheets", "all")

#: Exact columns of the CLI demo's ``index.html`` stream table, in order.
STREAM_HEADERS: list[str] = [
    "Stream",
    "Service",
    "From",
    "To",
    "T [°C]",
    "P [kPa g]",
    "F [kmol/h]",
    "W [kg/h]",
    "Vapour frac.",
]

#: ``Datasheet`` contract field names kept as headers, so the export is
#: checkable against the ``POST /api/solve`` payload for the same tag.
DATASHEET_HEADERS: list[str] = [
    "tag",
    "kind",
    "design_pressure_Pa",
    "design_temperature_K",
    "dimensions",
    "nozzle_count",
    "notes",
]

#: The CLI formatter's missing-value placeholder (an HTML entity — markup).
_MDASH = "&mdash;"

#: Separator for joined multi-value cells (dimensions, notes).
_JOIN = "; "


def coerce_scope(scope: str) -> Scope:
    """Validate a raw scope string against SCOPES; raises ValueError with the allowed values."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(SCOPES)}")
    return scope


def _clean(cell: str) -> str:
    """CSV/HTML export cell: the CLI's ``&mdash;`` placeholder becomes empty."""
    return "" if cell == _MDASH else cell


def _num(value: float) -> str:
    """Round-trippable text for a contract float (``str`` of a float parses back equal)."""
    return str(value)


def stream_rows(solved: SolvedFlowsheet) -> list[list[str]]:
    """One row per stream spec, in flowsheet order, cells byte-equal to ``cli._cell``."""
    rows: list[list[str]] = []
    for spec in solved.flowsheet.streams:
        state = solved.streams.get(spec.id)
        rows.append(
            [
                spec.id,
                spec.service,
                _port(spec.source),
                _port(spec.target),
                *(_clean(_cell(state, column)) for column in ("T", "P", "F", "W", "VF")),
            ]
        )
    return rows


def datasheet_rows(solved: SolvedFlowsheet) -> list[list[str]]:
    """One row per entry in ``SolvedFlowsheet.datasheets``, sorted by tag for determinism."""
    rows: list[list[str]] = []
    for tag in sorted(solved.datasheets):
        sheet = solved.datasheets[tag]
        rows.append(
            [
                sheet.tag,
                sheet.kind,
                _num(sheet.design_pressure_Pa),
                _num(sheet.design_temperature_K),
                _JOIN.join(f"{k}={_num(v)}" for k, v in sorted(sheet.dimensions.items())),
                str(len(sheet.nozzles)),
                _JOIN.join(sheet.notes),
            ]
        )
    return rows


def sheet_csv(solved: SolvedFlowsheet, scope: Scope = "all") -> str:
    """RFC 4180 CSV: one row-group per included section (title, headers, data)."""
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    first = True
    if scope in ("streams", "all"):
        writer.writerow(["Streams"])
        writer.writerow(STREAM_HEADERS)
        writer.writerows(stream_rows(solved))
        first = False
    if scope in ("datasheets", "all"):
        if not first:
            writer.writerow([])
        writer.writerow(["Datasheets"])
        writer.writerow(DATASHEET_HEADERS)
        writer.writerows(datasheet_rows(solved))
    return buf.getvalue()


def _table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """One semantic ``<table>`` with a heading — the ``index.html`` table's structure."""
    e = html.escape
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "\n".join(f"        <tr>{''.join(f'<td>{e(c)}</td>' for c in row)}</tr>" for row in rows)
    return (
        f"    <section>\n"
        f"      <h2>{e(title)}</h2>\n"
        f"      <table>\n"
        f"        <thead>\n          <tr>{head}</tr>\n        </thead>\n"
        f"        <tbody>\n{body}\n        </tbody>\n"
        f"      </table>\n"
        f"    </section>"
    )


def sheet_html(solved: SolvedFlowsheet, scope: Scope = "all") -> str:
    """Semantic HTML: one ``<table>`` per included section, no inline styling."""
    sections: list[str] = []
    if scope in ("streams", "all"):
        sections.append(_table("Streams", STREAM_HEADERS, stream_rows(solved)))
    if scope in ("datasheets", "all"):
        sections.append(_table("Datasheets", DATASHEET_HEADERS, datasheet_rows(solved)))
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        "    <title>Engineering sheet</title>\n"
        "  </head>\n"
        "  <body>\n" + "\n".join(sections) + "\n  </body>\n</html>\n"
    )
