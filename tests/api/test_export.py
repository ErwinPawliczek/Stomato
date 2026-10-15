"""B-07 addendum acceptance, API level: the CSV the route serves parses to the
same stream values the CLI's index.html shows for the same solve, unknown
formats answer 422 (never 500), scope selects sections, and response headers
match the contract."""

from __future__ import annotations

import csv
import html
import io
from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from ngdesign import cli
from ngdesign.api.app import app

c = TestClient(app)


class _TableRows(HTMLParser):
    """Collects raw cell text per <tr> from the CLI's index.html, keeping entities
    literal (convert_charrefs=False) so '&mdash;' and '&deg;' stay as written."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.header: list[str] = []
        self.rows: list[list[str]] = []
        self._row_is_header = False
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("td", "th"):
            self._in_cell = True
            self._cell_buf = []
            if tag == "th":
                self._row_is_header = True
        elif tag == "tr":
            self._row = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._in_cell:
            self._row.append("".join(self._cell_buf))
            self._in_cell = False
        elif tag == "tr" and self._row:
            if self._row_is_header:
                self.header = self._row  # the thead row, th cells only
                self._row_is_header = False
            else:
                self.rows.append(self._row)
            self._row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._in_cell:
            self._cell_buf.append(f"&{name};")


def _reset() -> None:
    assert c.post("/api/project/reset").status_code == 200


def _csv_groups(text: str) -> dict[str, list[list[str]]]:
    """Parse the row-grouped CSV into {section title: rows under its header}."""
    groups: dict[str, list[list[str]]] = {}
    title = ""
    for row in csv.reader(io.StringIO(text, newline="")):
        if not row:
            continue
        if row[0] in ("Streams", "Datasheets"):
            title = row[0]
            groups[title] = []  # the next row is the group's header
        else:
            groups[title].append(row)
    return groups


def test_api_csv_matches_cli_index(tmp_path: Path) -> None:
    """Parity anchor: API CSV stream values == the CLI demo's index.html table."""
    _reset()
    assert cli.main(["slice", "--out", str(tmp_path)]) == 0

    parser = _TableRows()
    parser.feed((tmp_path / "index.html").read_text(encoding="utf-8"))
    assert parser.header, "index.html must contain the stream table header"
    assert parser.rows, "index.html must contain the stream table rows"

    r = c.get("/api/export/sheet", params={"format": "csv"})
    assert r.status_code == 200
    groups = _csv_groups(r.text)
    header, *api_rows = groups["Streams"]
    # The CLI's <th> cells carry markup entities (&deg;); the export's headers are plain text.
    assert header == [html.unescape(cell) for cell in parser.header]
    # CSV replaces the CLI's &mdash; placeholder with an empty cell — value parity.
    assert api_rows == [[v if v != "&mdash;" else "" for v in row] for row in parser.rows]


def test_unknown_format_422() -> None:
    _reset()
    r = c.get("/api/export/sheet", params={"format": "pdf"})
    assert r.status_code == 422
    assert "csv" in r.json()["detail"] and "html" in r.json()["detail"]
    assert set(r.json()) == {"detail"}  # JSON error body, no traceback


def test_scope_selects_sections() -> None:
    _reset()
    for scope, present in (
        ("streams", ("Streams",)),
        ("datasheets", ("Datasheets",)),
        ("all", ("Streams", "Datasheets")),
    ):
        r = c.get("/api/export/sheet", params={"format": "csv", "scope": scope})
        assert r.status_code == 200
        groups = _csv_groups(r.text)
        assert set(groups) == set(present), f"scope={scope} must include exactly {present}"
    r = c.get("/api/export/sheet", params={"format": "csv", "scope": "bogus"})
    assert r.status_code == 422
    assert "streams" in r.json()["detail"]


def test_response_headers_and_html_tables() -> None:
    _reset()
    csv_r = c.get("/api/export/sheet", params={"format": "csv"})
    assert csv_r.status_code == 200
    assert csv_r.headers["content-type"] == "text/csv; charset=utf-8"
    assert csv_r.headers["content-disposition"] == 'attachment; filename="sheet.csv"'

    html_r = c.get("/api/export/sheet", params={"format": "html"})
    assert html_r.status_code == 200
    assert html_r.headers["content-type"] == "text/html; charset=utf-8"
    assert html_r.text.count("<table>") == 2  # one per included section
    assert html_r.text.count("<table>") == c.get(
        "/api/export/sheet", params={"format": "html", "scope": "all"}
    ).text.count("<table>")
    streams_only = c.get("/api/export/sheet", params={"format": "html", "scope": "streams"})
    assert streams_only.text.count("<table>") == 1
    assert "Streams" in streams_only.text and "Datasheets" not in streams_only.text
