"""B-07 addendum acceptance: export values match the live CLI/API surfaces
exactly — cells are compared against direct ``cli._cell`` calls and the
``Datasheet`` contract values, never recorded fixtures."""

from __future__ import annotations

import pytest

from ngdesign import cli, export
from ngdesign.contracts import SolvedFlowsheet


def _solved() -> SolvedFlowsheet:
    """One full CLI-stage solve: solver + sizers, the state the demo exports."""
    solved = cli._solve_slice()
    return cli._run_sizers(solved)


def test_stream_rows_match_cli_cell() -> None:
    """Every exported stream cell is byte-equal to cli._cell for the same state."""
    solved = _solved()
    rows = export.stream_rows(solved)
    assert len(rows) == len(solved.flowsheet.streams)
    for spec, row in zip(solved.flowsheet.streams, rows, strict=True):
        state = solved.streams.get(spec.id)
        assert row == [
            spec.id,
            spec.service,
            cli._port(spec.source),
            cli._port(spec.target),
            *(cli._cell(state, c).replace("&mdash;", "") for c in ("T", "P", "F", "W", "VF")),
        ]


def test_datasheet_rows_match_solve_payload() -> None:
    """Every datasheet row field equals the Datasheet contract value that
    POST /api/solve would return for that tag (model_dump is its wire form)."""
    solved = _solved()
    assert solved.datasheets, "sample slice must carry datasheets for the parity check"
    rows = export.datasheet_rows(solved)
    assert [row[0] for row in rows] == sorted(solved.datasheets)
    by_tag = {row[0]: row for row in rows}
    for tag, sheet in solved.datasheets.items():
        payload = sheet.model_dump()  # the JSON POST /api/solve returns for this tag
        row = by_tag[tag]
        assert row[1] == payload["kind"]
        assert float(row[2]) == payload["design_pressure_Pa"]
        assert float(row[3]) == payload["design_temperature_K"]
        assert dict(cell.split("=", 1) for cell in row[4].split("; ")) == {
            k: str(v) for k, v in payload["dimensions"].items()
        }
        assert int(row[5]) == len(payload["nozzles"])
        assert row[6] == "; ".join(payload["notes"])


def test_export_is_deterministic() -> None:
    """Two solves of the same flowsheet export byte-identical files (mirrors
    tests/e2e/test_cli.py::test_cli_is_deterministic)."""
    a, b = _solved(), _solved()
    assert export.sheet_csv(a, "all").encode() == export.sheet_csv(b, "all").encode()
    assert export.sheet_html(a, "all").encode() == export.sheet_html(b, "all").encode()


def test_export_degrades_without_sheet_engine() -> None:
    """Degrade clause: the B-07 sheet engine (ngdesign.variables) is not merged,
    and the export still produces both sections — no import error, no empty file.
    When the engine merges, formula cells carry their API-evaluated values and
    this test simply exercises the same serializers over the richer sheet."""
    solved = _solved()
    for text in (export.sheet_csv(solved, "all"), export.sheet_html(solved, "all")):
        assert text.strip() != ""
        assert "Streams" in text
        assert "Datasheets" in text


@pytest.mark.parametrize("scope", ["streams", "datasheets", "all"])
def test_scope_selects_sections(scope: str) -> None:
    """scope narrows the export to its named sections."""
    solved = _solved()
    scope_arg = export.coerce_scope(scope)
    csv_text = export.sheet_csv(solved, scope_arg)
    html_text = export.sheet_html(solved, scope_arg)
    if scope in ("streams", "all"):
        assert "Streams" in csv_text and "Streams" in html_text
    else:
        assert "Streams" not in csv_text and "Streams" not in html_text
    if scope in ("datasheets", "all"):
        assert "Datasheets" in csv_text and "Datasheets" in html_text
    else:
        assert "Datasheets" not in csv_text and "Datasheets" not in html_text
