"""Unit-catalogue validator: V0 self-consistency, V1 cases, generated docs.

Spec U-00 (issue #189). The catalogue is the contract between the 83-row
palette and the registry, so its checks live in their own script — the same
pattern as ``scripts/validate_properties.py`` (the thermo catalogue audit),
which owns its checks outside pytest.

**V0 self-consistency** — every implemented row/level is solved on its own
``example_case()`` basis and must close:

1. material: molar inventory in == out for ``balance: molar`` rows; for
   ``balance: mass_elements`` rows (reactive units) total mass and every
   element's atom flow in == out instead (relative tolerance 1e-8);
2. energy: ``sum(n*h) in + duty_W + power_W == sum(n*h) out`` (relative 1e-8),
   with ``h`` lifted to the formation-enthalpy basis on ``mass_elements`` rows
   (or the package enthalpy, when a species lacks formation data and the unit
   declares ``heat_of_reaction_basis_sensible_only``; ``ngdesign.units.balance``);
3. determinism: a second solve reproduces every outlet state within 1e-8.

Each row solves on its ``example_thermo`` package (default ``pr``).

The catalogue must also refuse honestly: every roadmap-only row and every
planned level declaration raises :class:`UnitLevelNotImplemented`. Over the
current palette that is 21 implemented levels x 3 + 62 roadmap rows + 14
planned declarations = **139 V0 checks**.

**V1 worked cases** — ``data/validation_units/<family>/cases.yaml`` pairs a
row/level with a cited reference result (spec U-01). One case::

    - id: V-pump-perry-ex1          # V-prefixed, unique
      unit: pump                    # catalogue row id
      level: R0                     # optional; default level otherwise
      source: "Perry 9th ed., Example 10-3, p. 10-31"   # mandatory citation
      thermo: pr                    # optional; else the row's example_thermo
      feeds: {inlet: {T: 300.0, P: 2.0e5, molar_flow: 10.0, composition: {H2O: 1.0}}}
      params: {outlet_P: 1.0e6, efficiency: 0.75}       # override example params
      expected:
      - {quantity: power_W, value: 1234.0, tol_rel: 0.01}
      - {quantity: outlet.outlet.T, value: 300.4, tol_abs: 0.2}
      assessed: "..."               # optional: a measured, explained miss

``feeds`` default to the adapter's ``example_case`` feeds and ``params`` are
laid over its example params key by key. Quantities: ``duty_W``, ``power_W``,
``info.<key>``, ``outlet.<port>.<T|P|molar_flow|vapor_fraction|enthalpy|
entropy>`` and ``outlet.<port>.composition.<cid>``. Every expected value needs
``tol_rel`` or ``tol_abs`` (the book's rounding, fixed before the run). A case
fails when it cannot solve or any comparison misses; a failing case without an
``assessed`` note, a case with no ``source`` or no ``expected`` entry, a level
``validation`` id with no case, and a ``validated`` level with a failing case
are findings, and findings fail the run exactly like V0 failures.

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
from ngdesign.contracts.flowsheet import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units.balance import BalanceBasisError, energy_basis, mass_and_atoms, stream_enthalpy
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
    info: dict[str, float]


@dataclass(frozen=True)
class Finding:
    """A V1 evidence gap: a failing, uncited or unasserted case."""

    case: str
    unit: str
    detail: str


@dataclass(frozen=True)
class Comparison:
    """One expected quantity of a V1 case against its measured value."""

    quantity: str
    expected: float
    measured: float | None
    tolerance: str
    ok: bool


@dataclass(frozen=True)
class CaseResult:
    """One executed V1 case."""

    case: str
    unit: str
    level: str
    source: str
    comparisons: tuple[Comparison, ...]
    error: str | None
    assessed: str | None

    @property
    def passed(self) -> bool:
        return self.error is None and bool(self.comparisons) and all(c.ok for c in self.comparisons)


def _thermo(name: str | None = None) -> Thermo:
    names = registry.available("thermo")
    chosen = name or ("pr" if "pr" in names else names[0])
    impl: Thermo = registry.create("thermo", chosen)
    return impl


def _row_thermo(row: UnitRow) -> Thermo:
    """The package a row's example and V1 cases solve on (``example_thermo``)."""
    return _thermo(row.example_thermo)


def _level_impl(row: UnitRow, level: LevelName) -> type:
    """The adapter class behind an implemented level (validated at load)."""
    adapter = row.levels[level].adapter
    if adapter is None:  # pragma: no cover - load_rows() rejects this first
        raise UnitLevelNotImplemented(row.id, level, implemented_levels(row))
    module_name, _, class_name = adapter.partition(":")
    import importlib

    return getattr(importlib.import_module(module_name), class_name)  # type: ignore[no-any-return]


def solve_level(
    row: UnitRow,
    level: LevelName,
    thermo: Thermo,
    feeds: dict[str, dict[str, Any]] | None = None,
    params: dict[str, Any] | None = None,
) -> Solved:
    """Solve one implemented level on the adapter's example basis.

    ``feeds`` replace the example feeds; ``params`` are laid over the example
    params key by key (a V1 case states only what its book example fixes).
    """
    unit = _level_impl(row, level)()
    example_feeds, defaults = unit.example_case()
    use_feeds = example_feeds if feeds is None else feeds
    inlets = {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
        for port, f in use_feeds.items()
    }
    merged: dict[str, Any] = dict(defaults)
    merged.update(params or {})
    result: UnitResult = unit.solve(inlets, merged, thermo)
    return Solved(row, level, inlets, result.outlets, result.duty_W, result.power_W, dict(result.info))


def _relative(value: float, scale: float) -> float:
    return abs(value) / max(abs(scale), 1.0)


def check_material(solved: Solved) -> str | None:
    """Molar (or, on ``mass_elements`` rows, mass + element) inventory in == out, relative 1e-8."""
    if solved.row.balance == "mass_elements":
        mass_in, atoms_in = mass_and_atoms(solved.inlets.values())
        mass_out, atoms_out = mass_and_atoms(solved.outlets.values())
        if _relative(mass_out - mass_in, mass_in) > TOLERANCE:
            return f"material: {mass_in:.6f} g/s in vs {mass_out:.6f} g/s out"
        for element in sorted(set(atoms_in) | set(atoms_out)):
            a_in, a_out = atoms_in.get(element, 0.0), atoms_out.get(element, 0.0)
            if _relative(a_out - a_in, max(a_in, a_out)) > TOLERANCE:
                return f"material: element {element} {a_in:.6f} mol/s in vs {a_out:.6f} mol/s out"
        return None
    total_in = sum(s.molar_flow for s in solved.inlets.values())
    total_out = sum(s.molar_flow for s in solved.outlets.values())
    if _relative(total_out - total_in, total_in) > TOLERANCE:
        return f"material: {total_in:.6f} mol/s in vs {total_out:.6f} mol/s out"
    return None


def check_energy(solved: Solved) -> str | None:
    """Duty + shaft power balance the enthalpy change, relative 1e-8.

    The basis comes from :func:`ngdesign.units.balance.energy_basis`:
    ``mass_elements`` rows close on the formation-enthalpy basis, so a
    reactor's heat of reaction appears in the stream enthalpies, not the duty;
    a row whose streams carry species without formation data closes on the
    package enthalpy only when the unit declares that in its info.
    """
    try:
        basis = energy_basis(solved.row.balance, solved.inlets.values(), solved.outlets.values(), solved.info)
    except BalanceBasisError as exc:
        return f"energy: {exc}"
    h_in = stream_enthalpy(solved.inlets.values(), basis)
    h_out = stream_enthalpy(solved.outlets.values(), basis)
    residual = h_out - h_in - solved.duty_W - solved.power_W
    scale = max(abs(h_in), abs(h_out), abs(solved.duty_W), abs(solved.power_W))
    if _relative(residual, scale) > TOLERANCE:
        return f"energy: residual {residual:.6g} W on {scale:.6g} W scale ({basis} basis)"
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


def run_v0(rows: dict[str, UnitRow]) -> tuple[int, int, list[str]]:
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
        thermo = _row_thermo(row)
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
        for key, spec in row.levels.items():
            if not spec.planned:
                continue
            try:
                resolve_level(row, {"model": key})
                record(f"{row.id}/{key} planned refusal", "resolved instead of refusing")
            except UnitLevelNotImplemented as exc:
                if implemented_levels(row) and ", ".join(implemented_levels(row)) in str(exc):
                    passed += 1
                    total += 1
                else:
                    record(
                        f"{row.id}/{key} planned refusal",
                        f"refusal message lacks implemented levels: {exc}",
                    )
            except ValueError as exc:
                record(f"{row.id}/{key} planned refusal", f"raised {type(exc).__name__}: {exc}")
    return passed, total, failures


_STATE_FIELDS = ("T", "P", "molar_flow", "vapor_fraction", "enthalpy", "entropy")


def _measure(solved: Solved, quantity: str) -> float:
    """Resolve one V1 quantity path on a solved case (KeyError names a bad path)."""
    if quantity == "duty_W":
        return solved.duty_W
    if quantity == "power_W":
        return solved.power_W
    head, _, rest = quantity.partition(".")
    if head == "info":
        if rest not in solved.info:
            raise KeyError(f"info has no {rest!r} (keys: {sorted(solved.info)})")
        return float(solved.info[rest])
    if head == "outlet":
        port, _, field = rest.partition(".")
        if port not in solved.outlets:
            raise KeyError(f"no outlet port {port!r} (ports: {sorted(solved.outlets)})")
        state = solved.outlets[port]
        if field in _STATE_FIELDS:
            return float(getattr(state, field))
        kind, _, cid = field.partition(".")
        if kind == "composition":
            return float(state.composition.get(cid, 0.0))
        raise KeyError(f"unknown stream field {field!r}")
    raise KeyError(f"unknown quantity {quantity!r}")


def _compare(solved: Solved, entry: dict[str, Any]) -> Comparison:
    quantity = str(entry.get("quantity", ""))
    expected = float(entry["value"])
    if "tol_rel" in entry:
        tol = float(entry["tol_rel"])
        tolerance = f"rel {tol:g}"
    elif "tol_abs" in entry:
        tol = float(entry["tol_abs"])
        tolerance = f"abs {tol:g}"
    else:
        raise KeyError(f"{quantity}: expected value carries neither tol_rel nor tol_abs")
    measured = _measure(solved, quantity)
    if "tol_rel" in entry:
        ok = abs(measured - expected) <= tol * abs(expected)
    else:
        ok = abs(measured - expected) <= tol
    return Comparison(quantity, expected, measured, tolerance, ok)


def _load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for family_dir in sorted(VALIDATION_DIR.iterdir()):
        cases_path = family_dir / "cases.yaml"
        if not cases_path.is_file():
            continue
        loaded = yaml.safe_load(cases_path.read_text()) or []
        if not isinstance(loaded, list):
            raise ValueError(f"{cases_path.relative_to(REPO_ROOT)} must be a YAML list")
        cases.extend(loaded)
    return cases


def run_v1(rows: dict[str, UnitRow]) -> tuple[list[CaseResult], list[Finding]]:
    """Execute every V1 worked case; returns (results, findings).

    A finding is an evidence gap that fails the run: a case without a source
    or expected values, an unassessed failing case, a level validation id with
    no case, or a ``validated`` level whose case fails (assessed or not).
    """
    results: list[CaseResult] = []
    findings: list[Finding] = []
    seen: dict[str, str] = {}
    for case in _load_cases():
        case_id = str(case.get("id", "?"))
        unit_id = str(case.get("unit", ""))
        if case_id in seen:
            findings.append(Finding(case_id, unit_id, "duplicate case id"))
            continue
        seen[case_id] = unit_id
        if not case_id.startswith("V"):
            findings.append(Finding(case_id, unit_id, "case id is not V-prefixed"))
        row = rows.get(unit_id)
        if row is None:
            findings.append(Finding(case_id, unit_id, "unknown unit id"))
            continue
        source = str(case.get("source", "")).strip()
        expected = case.get("expected") or []
        if not source:
            findings.append(Finding(case_id, unit_id, "no source citation"))
        if not expected:
            findings.append(Finding(case_id, unit_id, "no expected values"))
        try:
            level = resolve_level(row, {"model": case["level"]} if "level" in case else {})
        except UnitLevelNotImplemented as exc:
            findings.append(Finding(case_id, unit_id, f"level unavailable: {exc}"))
            continue
        assessed = case.get("assessed")
        error: str | None = None
        comparisons: list[Comparison] = []
        try:
            thermo = _thermo(case.get("thermo") or row.example_thermo)
            solved = solve_level(row, level, thermo, case.get("feeds"), case.get("params"))
            comparisons = [_compare(solved, entry) for entry in expected]
        except Exception as exc:  # noqa: BLE001 - findings name every failure
            error = f"{type(exc).__name__}: {exc}"
        result = CaseResult(case_id, unit_id, level, source, tuple(comparisons), error, assessed)
        results.append(result)
        if not result.passed:
            detail = error or "; ".join(
                f"{c.quantity} {c.measured:.6g} vs {c.expected:.6g} ({c.tolerance})"
                for c in comparisons
                if not c.ok
            )
            if row.levels[level].status == "validated":
                findings.append(Finding(case_id, unit_id, f"validated level fails its case: {detail}"))
            elif not assessed:
                findings.append(Finding(case_id, unit_id, f"unassessed miss: {detail}"))
    for row in rows.values():
        for key, spec in row.levels.items():
            for case_id in spec.validation:
                if seen.get(case_id) != row.id:
                    findings.append(
                        Finding(case_id, row.id, f"{key} names a validation case that does not exist")
                    )
    return results, findings


def _case_rows(results: list[CaseResult]) -> list[str]:
    lines = [
        "| case | level | quantity | expected | measured | tolerance | result |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        if result.error is not None:
            lines.append(f"| `{result.case}` | {result.level} | — | — | — | — | error: {result.error} |")
            continue
        for c in result.comparisons:
            measured = "—" if c.measured is None else f"{c.measured:.6g}"
            verdict = "pass" if c.ok else ("assessed miss" if result.assessed else "MISS")
            lines.append(
                f"| `{result.case}` | {result.level} | `{c.quantity}` | {c.expected:.6g} | {measured} "
                f"| {c.tolerance} | {verdict} |"
            )
    return lines


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


def unit_page(row: UnitRow, results: list[CaseResult] | None = None) -> str:
    """The generated per-unit docs page (with its V1 case table when it has cases)."""
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
    if results:
        out.append("## V1 worked cases")
        out.append("")
        out.extend(_case_rows(results))
        out.append("")
        for result in results:
            out.append(f"- `{result.case}`: {result.source}")
            if result.assessed:
                out.append(f"  - assessed: {result.assessed}")
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


def generate_docs(rows: dict[str, UnitRow], results: list[CaseResult] | None = None) -> dict[Path, str]:
    """Every generated docs file, keyed by path (deterministic content)."""
    files = {UNITS_DOC: overview(rows)}
    by_unit: dict[str, list[CaseResult]] = {}
    for result in results or []:
        by_unit.setdefault(result.unit, []).append(result)
    for row in rows.values():
        path = UNIT_PAGES_DIR / row.family / f"{row.id}.md"
        files[path] = unit_page(row, by_unit.get(row.id))
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
    passed, total, failures = run_v0(rows)
    print(f"V0 self-consistency: {passed}/{total} checks passed (tolerance {TOLERANCE:g})")
    for failure in failures:
        print(f"  FAIL {failure}")

    results, findings = run_v1(rows)
    n_pass = sum(r.passed for r in results)
    print(f"V1 worked cases: {n_pass}/{len(results)} pass, {len(findings)} findings")
    for finding in findings:
        print(f"  FINDING {finding.unit}: {finding.case} — {finding.detail}")

    files = generate_docs(rows, results)
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

    if failures or findings:
        print(f"FAILED: {total - passed} V0 check(s) failed, {len(findings)} V1 finding(s)")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
