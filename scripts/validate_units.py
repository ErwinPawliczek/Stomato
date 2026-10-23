"""Unit-catalogue validator: V0 self-consistency, V1 cases, generated docs.

Spec U-00 (issue #189). The catalogue is the contract between the 83-row
palette and the registry, so its checks live in their own script — the same
pattern as ``scripts/validate_properties.py`` (the thermo catalogue audit),
which owns its checks outside pytest.

**V0 self-consistency** — every implemented row/level is solved on its own
``example_case()`` basis and must close:

1. material: molar inventory in == out (the palette has no reactors yet, so
   every adapter repartitions moles; relative tolerance 1e-8);
2. energy: ``sum(n*h) in + duty_W + power_W == sum(n*h) out`` (relative 1e-8);
3. determinism: a second solve reproduces every outlet state within 1e-8.

The catalogue must also refuse honestly: every roadmap-only row and every
planned level declaration raises :class:`UnitLevelNotImplemented`. Over the
current palette that is 21 implemented levels x 3 + 62 roadmap rows + 14
planned declarations = **139 V0 checks**.

**V1 worked cases** — ``data/validation_units/<family>/cases.yaml`` pairs a
row/level with a cited reference result (V1 coverage ships in a later spec;
the files exist and are empty today). Every case is executed; failures are
reported as findings and listed in the docs — they do not flip the exit code,
which belongs to V0.

**Generated docs** — ``docs/units.md`` (one overview table per family) and
``docs/units/<family>/<id>.md`` (one page per unit) are regenerated on every
run. ``--audit`` regenerates in memory and fails when any generated file is
stale; CI's audit job runs exactly that.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units.catalogue import UnitRow, load_rows, register_all
from ngdesign.units.levels import (
    LEVEL_ORDER,
    LevelName,
    UnitLevelNotImplemented,
    implemented_levels,
    resolve_level,
)

#: Relative closure tolerance, fixed by the spec before any run (the plan's
#: V0 layer): mass and energy residuals and re-solve drift all sit at 1e-8.
TOLERANCE = 1e-8

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
UNITS_DOC = DOCS_DIR / "units.md"
UNIT_PAGES_DIR = DOCS_DIR / "units"
VALIDATION_DIR = REPO_ROOT / "data" / "validation_units"

#: Family display order (plan §2).
FAMILIES: tuple[str, ...] = (
    "logical",
    "flow",
    "heat",
    "separation",
    "column",
    "reactors",
    "treating",
    "refining",
)


@dataclass(frozen=True)
class Solved:
    """One implemented level solved on its example basis."""

    row: UnitRow
    level: LevelName
    inlets: dict[str, StreamState]
    outlets: dict[str, StreamState]
    duty_W: float
    power_W: float


@dataclass(frozen=True)
class Finding:
    """A V1 case failure — evidence debt, not a broken build."""

    case: str
    unit: str
    detail: str


def _thermo() -> Thermo:
    names = registry.available("thermo")
    impl: Thermo = registry.create("thermo", "pr" if "pr" in names else names[0])
    return impl


def _level_impl(row: UnitRow, level: LevelName) -> type:
    """The adapter class behind an implemented level (validated at load)."""
    adapter = row.levels[level].adapter
    if adapter is None:  # pragma: no cover - load_rows() rejects this first
        raise UnitLevelNotImplemented(row.id, level, implemented_levels(row))
    module_name, _, class_name = adapter.partition(":")
    import importlib

    return getattr(importlib.import_module(module_name), class_name)  # type: ignore[no-any-return]


def solve_level(row: UnitRow, level: LevelName, thermo: Thermo) -> Solved:
    """Solve one implemented level on the adapter's example basis."""
    unit = _level_impl(row, level)()
    feeds, defaults = unit.example_case()
    inlets = {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for port, f in feeds.items()
    }
    params: dict[str, Any] = dict(defaults)
    result = unit.solve(inlets, params, thermo)
    return Solved(row, level, inlets, result.outlets, result.duty_W, result.power_W)


def _relative(value: float, scale: float) -> float:
    return abs(value) / max(abs(scale), 1.0)


def check_material(solved: Solved) -> str | None:
    """Molar inventory in == out, relative 1e-8."""
    total_in = sum(s.molar_flow for s in solved.inlets.values())
    total_out = sum(s.molar_flow for s in solved.outlets.values())
    if _relative(total_out - total_in, total_in) > TOLERANCE:
        return f"material: {total_in:.6f} mol/s in vs {total_out:.6f} mol/s out"
    return None


def check_energy(solved: Solved) -> str | None:
    """Duty + shaft power balance the enthalpy change, relative 1e-8."""
    h_in = sum(s.molar_flow * s.enthalpy for s in solved.inlets.values())
    h_out = sum(s.molar_flow * s.enthalpy for s in solved.outlets.values())
    residual = h_out - h_in - solved.duty_W - solved.power_W
    scale = max(abs(h_in), abs(h_out), abs(solved.duty_W), abs(solved.power_W))
    if _relative(residual, scale) > TOLERANCE:
        return f"energy: residual {residual:.6g} W on {scale:.6g} W scale"
    return None


def _stream_close(a: StreamState, b: StreamState) -> bool:
    scale = max(abs(a.molar_flow), 1.0)
    checks = (
        _relative(a.T - b.T, a.T),
        _relative(a.P - b.P, a.P),
        _relative(a.molar_flow - b.molar_flow, scale),
        _relative(a.enthalpy - b.enthalpy, a.enthalpy),
        _relative(a.entropy - b.entropy, max(abs(a.entropy), 1.0)),
        abs(a.vapor_fraction - b.vapor_fraction),
    )
    if max(checks) > TOLERANCE:
        return False
    if set(a.composition) != set(b.composition):
        return False
    return all(
        _relative(a.composition[k] - b.composition[k], max(a.composition.values(), default=1.0)) <= TOLERANCE
        for k in a.composition
    )


def check_determinism(row: UnitRow, level: LevelName, thermo: Thermo) -> str | None:
    """A second solve on the same basis reproduces the first within 1e-8."""
    again = solve_level(row, level, thermo)
    first = solve_level(row, level, thermo)
    if set(first.outlets) != set(again.outlets):
        return "determinism: outlet ports differ between solves"
    for port, state in first.outlets.items():
        if not _stream_close(state, again.outlets[port]):
            return f"determinism: outlet {port!r} drifted on re-solve"
    if _relative(first.duty_W - again.duty_W, max(abs(first.duty_W), 1.0)) > TOLERANCE:
        return "determinism: duty drifted on re-solve"
    if _relative(first.power_W - again.power_W, max(abs(first.power_W), 1.0)) > TOLERANCE:
        return "determinism: shaft power drifted on re-solve"
    return None


def run_v0(rows: dict[str, UnitRow], thermo: Thermo) -> tuple[int, int, list[str]]:
    """Run every V0 check; returns (passed, total, failure messages)."""
    failures: list[str] = []
    passed = 0
    total = 0

    def record(where: str, error: str | None) -> None:
        nonlocal passed, total
        total += 1
        if error is None:
            passed += 1
        else:
            failures.append(f"{where}: {error}")

    for row in sorted(rows.values(), key=lambda r: (FAMILIES.index(r.family), r.id)):
        levels = implemented_levels(row)
        # Roadmap-only rows refuse the default selection: one honest refusal.
        if not levels:
            try:
                resolve_level(row, {})
                record(f"{row.id} roadmap refusal", "resolved instead of refusing")
            except UnitLevelNotImplemented:
                passed += 1
                total += 1
            except ValueError as exc:
                record(f"{row.id} roadmap refusal", f"raised {type(exc).__name__}: {exc}")
            continue
        for level in levels:
            try:
                solved = solve_level(row, level, thermo)
            except Exception as exc:  # noqa: BLE001 - findings name every failure
                record(f"{row.id}/{level} solve", f"{type(exc).__name__}: {exc}")
                continue
            record(f"{row.id}/{level} material", check_material(solved))
            record(f"{row.id}/{level} energy", check_energy(solved))
            record(f"{row.id}/{level} determinism", check_determinism(row, level, thermo))
        # Declared-but-planned levels refuse and name the implemented ones.
        for level, spec in row.levels.items():
            if not spec.planned:
                continue
            try:
                resolve_level(row, {"model": level})
                record(f"{row.id}/{level} planned refusal", "resolved instead of refusing")
            except UnitLevelNotImplemented as exc:
                if implemented_levels(row) and ", ".join(implemented_levels(row)) in str(exc):
                    passed += 1
                    total += 1
                else:
                    record(
                        f"{row.id}/{level} planned refusal",
                        f"refusal message lacks implemented levels: {exc}",
                    )
            except ValueError as exc:
                record(f"{row.id}/{level} planned refusal", f"raised {type(exc).__name__}: {exc}")
    return passed, total, failures


def load_v1_cases(rows: dict[str, UnitRow]) -> tuple[int, list[Finding]]:
    """Execute every V1 worked case; returns (cases run, findings)."""
    findings: list[Finding] = []
    run = 0
    for family_dir in sorted(VALIDATION_DIR.iterdir()):
        cases_path = family_dir / "cases.yaml"
        if not cases_path.is_file():
            continue
        cases = yaml.safe_load(cases_path.read_text()) or []
        if not isinstance(cases, list):
            findings.append(Finding(cases_path.name, family_dir.name, "cases.yaml must be a list"))
            continue
        for case in cases:
            run += 1
            unit_id = str(case.get("unit", ""))
            row = rows.get(unit_id)
            if row is None:
                findings.append(Finding(str(case.get("id", "?")), unit_id, "unknown unit id"))
                continue
            try:
                level = resolve_level(row, {"model": case["level"]} if "level" in case else {})
            except (UnitLevelNotImplemented, KeyError) as exc:
                findings.append(Finding(str(case.get("id", "?")), unit_id, f"level unavailable: {exc}"))
                continue
            thermo = _thermo()
            try:
                solve_level(row, level, thermo)
            except Exception as exc:  # noqa: BLE001 - findings name every failure
                findings.append(Finding(str(case.get("id", "?")), unit_id, f"{type(exc).__name__}: {exc}"))
    return run, findings


def _ladder(row: UnitRow) -> str:
    marks = []
    for level in LEVEL_ORDER:
        spec = row.levels.get(level)
        if spec is None:
            continue
        marks.append(f"{level} {'planned' if spec.planned else spec.status}")
    return ", ".join(marks)


def _port_rows(row: UnitRow) -> str:
    lines = ["| direction | port | required | description |", "|---|---|---|---|"]
    for direction in ("inlet", "outlet"):
        for port in getattr(row.ports, direction):
            lines.append(
                f"| {direction} | `{port.name}` | {'yes' if port.required else 'no'} | {port.description} |"
            )
    return "\n".join(lines)


def unit_page(row: UnitRow) -> str:
    """The generated per-unit docs page."""
    out: list[str] = []
    out.append(f"# {row.name} (`{row.id}`)")
    out.append("")
    out.append(f"Family: **{row.family}** · P&ID symbol: `{row.pid_symbol}`")
    out.append("")
    out.append(f"Rigour ladder: {_ladder(row)}")
    out.append("")
    out.append("## Ports")
    out.append("")
    out.append(_port_rows(row))
    out.append("")
    out.append("## Levels")
    out.append("")
    out.append("| level | status | adapter | basis |")
    out.append("|---|---|---|---|")
    for level in LEVEL_ORDER:
        spec = row.levels.get(level)
        if spec is None:
            continue
        adapter = f"`{spec.adapter}`" if spec.adapter else "—"
        out.append(f"| {level} | {spec.status} | {adapter} | {spec.note} |")
    out.append("")
    if row.sizer:
        out.append(f"Sizer plugin: `{row.sizer}`")
        out.append("")
    for level in LEVEL_ORDER:
        spec = row.levels.get(level)
        if spec is None or not spec.params or spec.params == {"type": "object", "properties": {}}:
            continue
        out.append(f"### {level} parameters")
        out.append("")
        out.append("```yaml")
        out.append(yaml.safe_dump(spec.params, sort_keys=True).rstrip())
        out.append("```")
        out.append("")
    if row.mode_map:
        out.append("Mode map: " + ", ".join(f"`{mode}` → `{level}`" for mode, level in row.mode_map.items()))
        out.append("")
    if row.references:
        out.append("## References")
        out.append("")
        out.extend(f"- {ref}" for ref in row.references)
        out.append("")
    if row.notes:
        out.append(f"> {row.notes}")
        out.append("")
    return "\n".join(out)


def overview(rows: dict[str, UnitRow]) -> str:
    """The generated docs/units.md overview."""
    out: list[str] = []
    out.append("# Unit catalogue")
    out.append("")
    out.append(
        "GENERATED by `scripts/validate_units.py` from `data/unit_models/` — edit the YAML, not this file."
    )
    out.append("")
    implemented = sum(1 for r in rows.values() if implemented_levels(r))
    out.append(
        f"{len(rows)} units across {len(FAMILIES)} families; {implemented} implemented in the registry today."
    )
    out.append("")
    for family in FAMILIES:
        family_rows = sorted((r for r in rows.values() if r.family == family), key=lambda r: r.id)
        if not family_rows:
            continue
        out.append(f"## {family} ({len(family_rows)})")
        out.append("")
        out.append("| unit | rigour ladder | sizer |")
        out.append("|---|---|---|")
        for row in family_rows:
            sizer = f"`{row.sizer}`" if row.sizer else "—"
            page = f"[{row.name}]({'units/' + family + '/' + row.id + '.md'})"
            out.append(f"| {page} | {_ladder(row)} | {sizer} |")
        out.append("")
    return "\n".join(out)


def generate_docs(rows: dict[str, UnitRow]) -> dict[Path, str]:
    """Every generated docs file, keyed by path (deterministic content)."""
    files = {UNITS_DOC: overview(rows)}
    for row in rows.values():
        path = UNIT_PAGES_DIR / row.family / f"{row.id}.md"
        files[path] = unit_page(row)
    return files


def write_docs(files: dict[Path, str]) -> None:
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def audit_docs(files: dict[Path, str]) -> list[str]:
    """Stale/missing generated docs, newest first."""
    stale = []
    for path, content in files.items():
        if not path.is_file():
            stale.append(f"missing generated doc: {path.relative_to(REPO_ROOT)}")
        elif path.read_text() != content:
            stale.append(f"stale generated doc: {path.relative_to(REPO_ROOT)}")
    for path in sorted(UNIT_PAGES_DIR.rglob("*.md")):
        if path not in files:
            stale.append(f"orphan generated doc: {path.relative_to(REPO_ROOT)}")
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="fail when the generated docs are stale instead of writing them",
    )
    args = parser.parse_args(argv)

    registry.discover()
    rows = load_rows()
    register_all()
    thermo = _thermo()

    passed, total, failures = run_v0(rows, thermo)
    print(f"V0 self-consistency: {passed}/{total} checks passed (tolerance {TOLERANCE:g})")
    for failure in failures:
        print(f"  FAIL {failure}")

    cases, findings = load_v1_cases(rows)
    print(f"V1 worked cases: {cases} executed, {len(findings)} findings")
    for finding in findings:
        print(f"  FINDING {finding.unit}: {finding.case} — {finding.detail}")

    files = generate_docs(rows)
    if args.audit:
        stale = audit_docs(files)
        if stale:
            for line in stale:
                print(f"  AUDIT {line}")
            print("docs audit: FAILED — run `uv run python scripts/validate_units.py`")
            return 1
        print("docs audit: ok")
    else:
        write_docs(files)
        print(f"docs: wrote {len(files)} generated files under docs/")

    if failures:
        print(f"FAILED: {total - passed} V0 check(s) failed")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
