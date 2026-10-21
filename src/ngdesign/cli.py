"""End-to-end slice demo CLI (spec S-35).

``python -m ngdesign.cli slice --out out/`` runs the full chain on the
locked sample flowsheet: PR thermo -> sequential-modular solve -> sizers ->
P&ID build -> P&ID rules to a fixed point (max 5 passes; rules create work
for each other, e.g. a new PSV line needs isolation) -> PFD and P&ID SVG ->
router -> one isometric SVG per routed line (plus DXF when a DXF iso
renderer is registered) -> index.html linking every drawing with the
stream table.

The chain itself lives in :mod:`ngdesign.pipeline` (P0-03): this module is
the wiring that runs it once and writes the drawings. Design decisions the
sample data does not carry live here, following the S-33 composition-test
pattern: shell-and-tube utility temperatures come from the flowsheet params,
and PSV sizing is given a full relief basis with k_gas = 1.24
(``pipeline.DEFAULT_K_GAS``; S-34 assigns the heat-capacity ratio to the
caller).
"""

from __future__ import annotations

import argparse
import html
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np

from ngdesign import pipeline, registry
from ngdesign.contracts import PID, Project, SolvedFlowsheet
from ngdesign.export import _cell, _port
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.pipeline import DEFAULT_K_GAS
from ngdesign.study import Axis, CaseStudy, to_csv, to_markdown
from ngdesign.study import run as run_study


def _solve_slice() -> SolvedFlowsheet:
    """Thermo selected by the slice (default pr) -> sequential-modular solve."""
    fs = slice_fs.build()
    thermo = registry.create("thermo", fs.thermo)
    solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(fs, thermo)
    if not solved.converged:
        raise RuntimeError("sample slice did not converge; nothing to draw")
    return solved


def _violations(pid: PID, rules: list[Any]) -> list[str]:
    """Human-readable list of rule violations remaining on the built P&ID."""
    out: list[str] = []
    for rule in rules:
        for v in rule.check(pid):
            out.append(f"{v.rule} @ {v.target}: {v.message}")
    return out


def _iso_stem(index: int, line_number: str) -> str:
    """iso_NN_<line number made filename-safe>: quote and slash characters out."""
    safe = line_number.replace('"', "in").replace("/", "-")
    return f"iso_{index:02d}_{safe}"


def _write(out: Path, name: str, text: str) -> Path:
    path = out / name
    path.write_text(text, encoding="utf-8")
    return path


def _index_html(
    solved: SolvedFlowsheet,
    pid: PID,
    drawing_links: list[tuple[str, str]],
    violations: list[str],
) -> str:
    """The demo's index page: links to every drawing plus the stream table."""
    e = html.escape
    links = "\n".join(f'      <li><a href="{e(h)}">{e(h)}</a></li>' for h, _ in drawing_links)
    rows = []
    for spec in solved.flowsheet.streams:
        state = solved.streams.get(spec.id)
        cells = "</td><td>".join(_cell(state, c) for c in ("T", "P", "F", "W", "VF"))
        rows.append(
            f"    <tr><td>{e(spec.id)}</td><td>{e(spec.service)}</td>"
            f"<td>{e(_port(spec.source))}</td><td>{e(_port(spec.target))}</td>"
            f"<td>{cells}</td></tr>"
        )
    table = "\n".join(rows)
    notes = ""
    if violations:
        items = "\n".join(f"      <li>{e(v)}</li>" for v in violations)
        notes = f"  <h2>Remaining rule violations</h2>\n  <ul>\n{items}\n  </ul>\n"
    pid_line_count = len(pid.lines)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Sample slice &mdash; end to end (S-35)</title>
    <style>
      body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 2rem auto; max-width: 60rem; }}
      table {{ border-collapse: collapse; }}
      th, td {{ border: 1px solid #cbd5e1; padding: 0.25rem 0.6rem; text-align: right; }}
      th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
    </style>
  </head>
  <body>
    <h1>Sample slice &mdash; end to end</h1>
    <p>One Peng&ndash;Robinson solve feeds sizing, the P&amp;ID ({pid_line_count} lines),
    routing and the isometrics below.</p>
    <h2>Drawings</h2>
    <ul>
{links}
    </ul>
    <h2>Streams</h2>
    <table>
      <thead>
        <tr><th>Stream</th><th>Service</th><th>From</th><th>To</th>
            <th>T [&deg;C]</th><th>P [kPa g]</th><th>F [kmol/h]</th>
            <th>W [kg/h]</th><th>Vapour frac.</th></tr>
      </thead>
      <tbody>
{table}
      </tbody>
    </table>
{notes}  </body>
</html>
"""


def _axis_values(spec_value: str) -> list[float]:
    """The values of one input axis: 'start:stop:n' spans n evenly spaced
    points (inclusive); a comma list and a bare value are literal."""
    parts = spec_value.split(":")
    if len(parts) == 3:
        start, stop, points = float(parts[0]), float(parts[1]), int(parts[2])
        if points < 2:
            raise ValueError(f"the range form needs at least 2 points, got {points}")
        return [float(v) for v in np.linspace(start, stop, points)]
    return [float(v) for v in spec_value.split(",")]


def _axis_spec(raw: str) -> tuple[str, list[float]]:
    """argparse type for --input: '<address>=<values>' -> (address, values)."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"bad --input {raw!r}: expected '<address>=<start>:<stop>:<points>' or '<address>=<v1,v2,...>'"
        )
    address, values_part = raw.split("=", 1)
    if not address.strip():
        raise argparse.ArgumentTypeError(f"bad --input {raw!r}: empty address")
    try:
        return address.strip(), _axis_values(values_part)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"bad --input {raw!r}: {exc}") from exc


def _study(args: argparse.Namespace) -> int:
    """One case study against a project JSON file: the table to stdout, CSV
    to ``--csv`` when given."""
    try:
        project = Project.model_validate_json(Path(args.project).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: cannot load project {args.project}: {exc}", file=sys.stderr)
        return 2
    study = CaseStudy(
        id="cli",
        inputs=[Axis(address=address, values=values) for address, values in args.input],
        outputs=list(args.output),
        base=project.flowsheet,
    )
    try:
        thermo = registry.create("thermo", study.base.thermo)
        result = run_study(study, thermo)
    except (KeyError, ValueError) as exc:
        # Unknown thermo/unit plugin (KeyError) or a structurally impossible
        # study (ValueError, e.g. an empty axis): a CLI error, not a traceback.
        print(f"error: {exc.args[0] if isinstance(exc, KeyError) and exc.args else exc}", file=sys.stderr)
        return 2
    print(to_markdown(result), end="")
    if args.csv is not None:
        csv_path = Path(args.csv)
        csv_path.write_text(to_csv(result), encoding="utf-8")
        print(f"wrote {csv_path}")
    return 0


def _write_all(out: Path, solved: SolvedFlowsheet, pid: PID, net: Any, rules: list[Any]) -> list[Path]:
    """Render and write every drawing plus the index; returns the paths."""
    written = [
        _write(out, "pfd.svg", registry.create("diagram", "pfd").render(solved)),
        _write(out, "pid.svg", registry.create("diagram", "pid").render(pid)),
    ]
    links = [("pfd.svg", "PFD"), ("pid.svg", "P&ID")]
    iso = registry.create("iso_renderer", "svg")
    dxf = registry.create("diagram", "iso_dxf") if "iso_dxf" in registry.available("diagram") else None
    for i, line in enumerate(net.lines, start=1):
        stem = _iso_stem(i, line.line_number)
        sheet = iso.render(line, pid)
        written.append(_write(out, f"{stem}.svg", sheet.svg))
        links.append((f"{stem}.svg", f"iso {line.line_number}"))
        if dxf is not None:  # S-23 hook: render(RoutedLine) -> DXF document
            written.append(_write(out, f"{stem}.dxf", dxf.render(line)))
            links.append((f"{stem}.dxf", f"iso {line.line_number} (DXF)"))
    written.append(_write(out, "index.html", _index_html(solved, pid, links, _violations(pid, rules))))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ngdesign", description="ngdesign sample-slice demo (spec S-35)")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("slice", help="run the sample slice end to end and write every drawing")
    demo.add_argument("--out", default="out", help="output directory (default: out)")
    db_init = sub.add_parser("db-init", help="create the store schema (spec P3-01)")  # noqa: F841 -- parser registration side effect
    serve = sub.add_parser("serve", help="run the API server against the store (spec P3-01)")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    worker = sub.add_parser("worker", help="run the solve-job worker until SIGTERM (spec P3-02)")
    worker.add_argument(
        "--once", action="store_true", help="process at most one job (or exit when none is queued), then exit"
    )
    study_cmd = sub.add_parser(
        "study", help="run a case study over a project JSON file and print the table (spec P2-04)"
    )
    study_cmd.add_argument("project", help="path to a project JSON file (the ngdesign Project model)")
    study_cmd.add_argument(
        "--input",
        action="append",
        type=_axis_spec,
        required=True,
        metavar="ADDR=START:STOP:N",
        help="swept write address, 'a:b:n' is n evenly spaced points; comma lists are literal; repeat it",
    )
    study_cmd.add_argument(
        "--output",
        action="append",
        required=True,
        metavar="ADDR",
        help="readable address to report per case; repeatable",
    )
    study_cmd.add_argument("--csv", default=None, help="also write the table as CSV to this path")
    args = parser.parse_args(argv)

    if args.command == "study":
        return _study(args)
    if args.command == "db-init":
        from ngdesign.store import database_url_log_safe, init_db

        init_db()
        print(f"database ready: {database_url_log_safe()}")
        return 0
    if args.command == "serve":
        import uvicorn

        from ngdesign.api.app import app as api_app
        from ngdesign.store import database_url_log_safe, init_db

        init_db()
        print(f"database ready: {database_url_log_safe()}")
        uvicorn.run(api_app, host=args.host, port=args.port)
        return 0
    if args.command == "worker":
        import signal

        from ngdesign.jobs.queue import queue_from_env
        from ngdesign.jobs.worker import run_worker
        from ngdesign.store import init_db

        init_db()
        stop = threading.Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())  # noqa: B023 — one shared event
        processed = run_worker(queue_from_env(), once=args.once, stop_event=stop)
        print(f"worker: processed {processed} job(s)")
        return 0

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    solved = _solve_slice()
    print(f"solver: converged in {solved.iterations} pass(es)")
    solved = pipeline.run_sizers(solved)
    print(f"sizers: {len(solved.datasheets)} datasheet(s): {', '.join(sorted(solved.datasheets))}")
    rules = pipeline.rule_set(solved, k_gas=DEFAULT_K_GAS)
    pid = pipeline.apply_rules(registry.create("pid_builder", "default").build(solved), rules)
    violations = _violations(pid, rules)
    print(
        f"p&id: {len(pid.lines)} line(s) over {len(pid.equipment)} equipment, "
        f"{len(violations)} violation(s) remaining"
    )
    net = pipeline.route(pid, layout={})
    for path in _write_all(out, solved, pid, net, rules):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
