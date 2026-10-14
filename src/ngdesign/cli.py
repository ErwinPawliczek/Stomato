"""End-to-end slice demo CLI (spec S-35).

``python -m ngdesign.cli slice --out out/`` runs the full chain on the
locked sample flowsheet: PR thermo -> sequential-modular solve -> sizers ->
P&ID build -> P&ID rules to a fixed point (max 5 passes; rules create work
for each other, e.g. a new PSV line needs isolation) -> PFD and P&ID SVG ->
router -> one isometric SVG per routed line (plus DXF when a DXF iso
renderer is registered) -> index.html linking every drawing with the
stream table.

Design decisions the sample data does not carry live here, following the
S-33 composition-test pattern: shell-and-tube utility temperatures come
from the flowsheet params, and PSV sizing is given a full relief basis
with k_gas = 1.24 - S-34 assigns the heat-capacity ratio to the caller.
"""

from __future__ import annotations

import argparse
import html
from pathlib import Path
from typing import Any

from ngdesign import registry
from ngdesign.contracts import PID, PortRef, SolvedFlowsheet
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.pid_rules.psv_sizing import relief_basis

#: Rule fixed-point cap; matches the S-35 spec and the locked e2e oracle.
MAX_RULE_PASSES = 5

#: Heat-capacity ratio of the relieving vapour. The StreamState contract
#: does not carry it, so S-34 assigns it to the caller; same value the S-33
#: composition tests use.
RELIEF_K_GAS = 1.24


def _solve_slice() -> SolvedFlowsheet:
    """PR thermo -> sequential-modular solve of the locked sample slice."""
    thermo = registry.create("thermo", "pr")
    solved = registry.create("solver", "sequential_modular").solve(slice_fs.build(), thermo)
    if not solved.converged:
        raise RuntimeError("sample slice did not converge; nothing to draw")
    return solved


def _sizer_for(unit_kind: str) -> Any | None:
    """First registered ``sizer`` whose ``unit_kind`` matches, if any.

    Mirrors the P&ID builder's own selection over the sorted registry; kept
    local so the CLI stays a wiring module and the builder's file its own.
    """
    for name in registry.available("sizer"):
        cls = registry.get("sizer", name)
        if getattr(cls, "unit_kind", None) == unit_kind:
            return cls()
    return None


def _run_sizers(solved: SolvedFlowsheet) -> SolvedFlowsheet:
    """Run the registered sizer per unit kind and attach the datasheets.

    The builder adopts attached datasheets verbatim and falls back to its
    internal sizing when none is attached; running them here makes the
    sizing step an observable CLI stage. Units without a sizer (the sample's
    jt_valve) are skipped and get the builder's default nozzles. Sizer
    errors propagate: the demo stops rather than drawing unsized equipment.
    """
    for spec in solved.flowsheet.units:
        if spec.tag in solved.datasheets:
            continue
        sizer = _sizer_for(spec.kind)
        if sizer is not None:
            solved.datasheets[spec.tag] = sizer.size(spec.tag, solved, spec.params)
    return solved


def _rule_set(solved: SolvedFlowsheet) -> list[Any]:
    """Every registered P&ID rule, psv_sizing given the full relief basis."""
    rules: list[Any] = []
    for name in registry.available("pid_rule"):
        if name == "psv_sizing":
            rules.append(registry.create("pid_rule", name, basis=relief_basis(solved, k_gas=RELIEF_K_GAS)))
        else:
            rules.append(registry.create("pid_rule", name))
    return rules


def _apply_rules(pid: PID, rules: list[Any]) -> PID:
    """Apply every rule repeatedly to a fixed point, capped at MAX_RULE_PASSES."""
    for _ in range(MAX_RULE_PASSES):
        before = pid.model_dump()
        for rule in rules:
            pid = rule.apply(pid)
        if pid.model_dump() == before:
            break
    return pid


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


def _port(ref: PortRef | None) -> str:
    return "battery limit" if ref is None else f"{ref.unit}.{ref.port}"


def _cell(state: Any, column: str) -> str:
    """Stream-table cell in the PFD renderer's units (degC, barg, kmol/h, kg/h)."""
    if state is None:
        return "&mdash;"
    if column == "T":
        return f"{state.T - 273.15:.1f}"
    if column == "P":
        return f"{state.P / 1000.0 - 101.325:.1f}"
    if column == "F":
        return f"{state.molar_flow * 3600.0 / 1000.0:.2f}"
    if column == "W":
        try:
            return f"{state.mass_flow * 3600.0:.0f}"
        except ValueError:
            return "&mdash;"  # mass flow needs the thermo layer
    return f"{state.vapor_fraction:.2f}"


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
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    solved = _solve_slice()
    print(f"solver: converged in {solved.iterations} pass(es)")
    solved = _run_sizers(solved)
    print(f"sizers: {len(solved.datasheets)} datasheet(s): {', '.join(sorted(solved.datasheets))}")
    pid = registry.create("pid_builder", "default").build(solved)
    rules = _rule_set(solved)
    pid = _apply_rules(pid, rules)
    violations = _violations(pid, rules)
    print(
        f"p&id: {len(pid.lines)} line(s) over {len(pid.equipment)} equipment, "
        f"{len(violations)} violation(s) remaining"
    )
    net = registry.create("router", "orthogonal").route(pid, layout={})
    for path in _write_all(out, solved, pid, net, rules):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
