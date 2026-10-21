#!/usr/bin/env python3
"""Benchmark baseline: flash count + wall time per benchmark flowsheet (spec P0-06).

Gives every PR a number: ``flashes_pt/ph/ps`` and wall time for each benchmark
case, compared against the committed ``bench/baseline.json``. Flash counts are
deterministic (regressions > 2 % fail); wall time is noisy (regressions only
warn, > 50 %, and never fail CI unless ``--fail-on=all``).

A ``CountingThermo`` proxy wraps any registered ``thermo`` plugin: it counts
``flash_pt/ph/ps`` calls and accumulates wall time spent inside them
(``time.perf_counter`` around each delegated call). It satisfies
``contracts.plugins.Thermo`` (runtime-checkable) and is transparent: the
``StreamState`` it returns is the wrapped plugin's own object, untouched. The
contract-v2 methods (spec P1-01) delegate untouched and are deliberately not
counted — the baseline measures flash counts, and the per-instance PT/phase_props
cache (P1-01) sits inside the plugin, below the proxy, where it belongs.

Cases (spec P0-06; flowsheet builders reused from ``ngdesign.flowsheets`` /
``scripts.bench_cases``, the standalone column reuses its own ``example_case``):

- ``slice``           -- the end-to-end slice solve (tests/e2e/test_slice.py).
- ``recycle_bench``   -- recycle-heavy solve (tests/e2e/test_recycle_bench.py).
- ``amine_loop``      -- MDEA sour-gas amine loop with lean-solvent recycle.
- ``mea_amine_loop``  -- the MEA twin of the MDEA loop.
- ``column``          -- the 16-stage column ``example_case()`` solved standalone.

Usage::

    uv run python scripts/bench_baseline.py --update          # rewrite baseline
    uv run python scripts/bench_baseline.py --check           # both rules
    uv run python scripts/bench_baseline.py --check --fail-on=flashes   # CI

``--check`` prints a per-case delta table (markdown) on stdout; CI tees it to
``$GITHUB_STEP_SUMMARY`` (``.github/workflows/bench.yml``). ``solver_passes``
is ``SolvedFlowsheet.iterations`` for flowsheet cases; the standalone column
has no ``SolvedFlowsheet``, and exposing unit-internal iteration counts is out
of scope for P0-06, so it records ``0``.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from ngdesign import registry
from ngdesign.contracts.flowsheet import SolvedFlowsheet
from ngdesign.contracts.plugins import Thermo, UnitModel
from ngdesign.contracts.stream import PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.flowsheets import amine_loop, mea_amine_loop, recycle_bench
from ngdesign.flowsheets import slice as slice_fs

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / "bench" / "baseline.json"

FLASH_TOLERANCE = 1.02  # flash counts are deterministic: any growth > 2 % fails
WALL_TOLERANCE = 1.50  # wall time is noisy: generous 50 % headroom


# --------------------------------------------------------------------------- proxy


class CountingThermo:
    """Transparent ``Thermo`` wrapper that counts flash calls and their wall time.

    Delegates every call to the wrapped plugin and returns its results
    unchanged, so counts are bit-identical to an unwrapped solve.

    Flash-equivalent counting (spec P1-03): ``flash_pt``/``flash_ph``/
    ``flash_ps`` plus the v2 calls that each cost one flash internally
    (``k_values``, ``bubble_point``, ``dew_point``, ``flash_tvf``,
    ``flash_pvf``) each add 1 to ``flashes``; ``phase_props``,
    ``derivatives`` and ``pure_psat`` are single-phase builds that skip the
    flash and are tracked separately as ``props_calls`` (not budgeted).
    Existing baselines are unchanged by this definition because the cases
    that predate P1-03 call none of the v2 methods.
    """

    def __init__(self, inner: Thermo) -> None:
        self._inner = inner
        self.flashes_pt: int = 0
        self.flashes_ph: int = 0
        self.flashes_ps: int = 0
        self.flashes_k_values: int = 0
        self.flashes_bubble_point: int = 0
        self.flashes_dew_point: int = 0
        self.flashes_flash_tvf: int = 0
        self.flashes_flash_pvf: int = 0
        self.props_calls: int = 0
        self.flash_wall_s: float = 0.0

    @property
    def flashes(self) -> int:
        """Total flash-equivalents: every call that runs a PT/PH/PS flash."""
        return int(
            self.flashes_pt
            + self.flashes_ph
            + self.flashes_ps
            + self.flashes_k_values
            + self.flashes_bubble_point
            + self.flashes_dew_point
            + self.flashes_flash_tvf
            + self.flashes_flash_pvf
        )

    def _timed_flash[T](self, fn: Callable[[], T]) -> T:
        start = time.perf_counter()
        try:
            return fn()
        finally:
            self.flash_wall_s += time.perf_counter() - start

    def __getattr__(self, name: str) -> Any:
        """Transparent for everything the protocol does not name (package helpers,
        duck-typing markers such as ``is_amine_reactive_package``)."""
        return getattr(self._inner, name)

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        self.flashes_pt += 1
        return self._timed_flash(lambda: self._inner.flash_pt(z, T, P, molar_flow))

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        self.flashes_ph += 1
        return self._timed_flash(lambda: self._inner.flash_ph(z, P, H, molar_flow))

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        self.flashes_ps += 1
        return self._timed_flash(lambda: self._inner.flash_ps(z, P, S, molar_flow))

    # -- Thermo contract v2 (spec P1-01): flash-equivalent calls are counted;
    #    single-phase builds are tracked separately and are not budgeted ------

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        self.flashes_flash_tvf += 1
        return self._timed_flash(lambda: self._inner.flash_tvf(z, T, vf, molar_flow))

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        self.flashes_flash_pvf += 1
        return self._timed_flash(lambda: self._inner.flash_pvf(z, P, vf, molar_flow))

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        self.flashes_bubble_point += 1
        return self._timed_flash(lambda: self._inner.bubble_point(z, T=T, P=P))

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        self.flashes_dew_point += 1
        return self._timed_flash(lambda: self._inner.dew_point(z, T=T, P=P))

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        self.flashes_k_values += 1
        return self._timed_flash(lambda: self._inner.k_values(z, T, P))

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        self.props_calls += 1
        return self._inner.phase_props(composition, T, P, kind)

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        self.props_calls += 1
        return self._inner.derivatives(composition, T, P, kind)

    def pure_psat(self, cid: str, T: float) -> float | None:
        self.props_calls += 1
        return self._inner.pure_psat(cid, T)


# --------------------------------------------------------------------------- cases


def _solver() -> Callable[[Any, Thermo], SolvedFlowsheet]:
    solver = registry.create("solver", "sequential_modular")
    return cast(Callable[[Any, Thermo], SolvedFlowsheet], solver.solve)


def _case_slice(thermo: Thermo) -> SolvedFlowsheet:
    fs = slice_fs.build()
    return _solver()(fs, thermo)


def _case_recycle_bench(thermo: Thermo) -> SolvedFlowsheet:
    fs = recycle_bench.build()
    return _solver()(fs, thermo)


def _case_amine_loop(thermo: Thermo) -> SolvedFlowsheet:
    fs = amine_loop.build()
    return _solver()(fs, thermo)


def _case_mea_amine_loop(thermo: Thermo) -> SolvedFlowsheet:
    fs = mea_amine_loop.build()
    return _solver()(fs, thermo)


def _case_column(thermo: Thermo) -> object:
    """The column ``example_case()`` solved standalone (no flowsheet, no solver)."""
    unit: UnitModel = registry.create("unit", "column")
    feeds, params = unit.example_case()
    inlets = {
        port: thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
        for port, feed in feeds.items()
    }
    return unit.solve(inlets, params, thermo)


CASES: dict[str, Callable[[Thermo], object]] = {
    "slice": _case_slice,
    "recycle_bench": _case_recycle_bench,
    "amine_loop": _case_amine_loop,
    "mea_amine_loop": _case_mea_amine_loop,
    "column": _case_column,
}


# --------------------------------------------------------------------------- measurement


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_case(name: str, thermo_name: str = "pr") -> dict[str, Any]:
    """Run one case under a fresh ``CountingThermo``; return its metric record."""
    raw: Thermo = registry.create("thermo", thermo_name)
    counting = CountingThermo(raw)
    runner = CASES[name]
    start = time.perf_counter()
    result = runner(counting)
    total_wall_s = time.perf_counter() - start

    if isinstance(result, SolvedFlowsheet):
        solver_passes = result.iterations
        converged = result.converged
    else:
        # Standalone unit solve: no SolvedFlowsheet diagnostics. Unit plugins
        # raise ColumnNotConverged on failure, so returning at all means converged.
        solver_passes = 0
        converged = True

    record: dict[str, Any] = {
        "flashes": counting.flashes,
        "flashes_pt": counting.flashes_pt,
        "flashes_ph": counting.flashes_ph,
        "flashes_ps": counting.flashes_ps,
        "flashes_k_values": counting.flashes_k_values,
        "flashes_bubble_point": counting.flashes_bubble_point,
        "flashes_dew_point": counting.flashes_dew_point,
        "flashes_flash_tvf": counting.flashes_flash_tvf,
        "flashes_flash_pvf": counting.flashes_flash_pvf,
        "props_calls": counting.props_calls,
        "flash_wall_s": round(counting.flash_wall_s, 6),
        "total_wall_s": round(total_wall_s, 6),
        "solver_passes": solver_passes,
        "converged": converged,
    }
    return record


def run_all() -> dict[str, Any]:
    """Every case, wrapped in the baseline document shape."""
    cases = {name: run_case(name) for name in CASES}
    return {
        "cases": cases,
        "budgets": _preserve_budgets(),
        "metadata": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "commit": _git_commit(),
        },
    }


# Pre-change flash-equivalent totals frozen for budget tests (spec P1-03):
# the column case measured on main before the contract-v2 migration
# (11,208 flash_pt calls; the v2 counting definition maps 1:1 onto it).
PRE_CHANGE_FLASHES: dict[str, int] = {"column": 11208}


def _preserve_budgets() -> dict[str, Any]:
    """Carry the frozen pre-change totals forward across baseline rewrites."""
    existing: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        try:
            existing = json.loads(BASELINE_PATH.read_text()).get("budgets", {})
        except (OSError, json.JSONDecodeError):
            existing = {}
    budgets: dict[str, Any] = {
        name: {"pre_change_flash_equivalents": count} for name, count in PRE_CHANGE_FLASHES.items()
    }
    budgets.update(existing)
    return budgets


# --------------------------------------------------------------------------- compare / report


def _total_flashes(record: dict[str, Any]) -> int:
    total = record["flashes"]
    return cast(int, total)


def _fmt(x: float) -> str:
    return f"{x:.2f}"


def check(baseline: dict[str, Any], fail_on: str) -> tuple[list[str], bool]:
    """Re-run every case and compare against the baseline.

    Returns (markdown table lines, ok). Flash counts over FLASH_TOLERANCE fail;
    wall time over WALL_TOLERANCE fails only when fail_on == "all".
    """
    current = run_all()
    header = (
        "| case | flashes (base → now) | Δ% | flash wall s (base → now) | Δ% "
        "| total wall s (base → now) | Δ% | converged | verdict |"
    )
    lines = [header, "|---|---|---|---|---|---|---|---|---|"]
    ok = True
    for name in CASES:
        base = baseline["cases"].get(name)
        now = current["cases"][name]
        if base is None:
            lines.append(
                f"| {name} | — | — | — | — | — | — | {now['converged']} | missing from baseline ❌ |"
            )
            ok = False
            continue
        base_flashes = _total_flashes(base)
        now_flashes = _total_flashes(now)
        base_flash_wall = float(base["flash_wall_s"])
        now_flash_wall = float(now["flash_wall_s"])
        base_total_wall = float(base["total_wall_s"])
        now_total_wall = float(now["total_wall_s"])

        flash_ratio = now_flashes / base_flashes if base_flashes else float("inf")
        flash_wall_ratio = now_flash_wall / base_flash_wall if base_flash_wall else float("inf")
        total_wall_ratio = now_total_wall / base_total_wall if base_total_wall else float("inf")

        flash_bad = flash_ratio > FLASH_TOLERANCE
        flash_wall_bad = flash_wall_ratio > WALL_TOLERANCE
        total_wall_bad = total_wall_ratio > WALL_TOLERANCE
        wall_bad = flash_wall_bad or total_wall_bad
        conv_bad = not now["converged"]

        if flash_bad or conv_bad or (wall_bad and fail_on == "all"):
            verdict = "regression ❌"
            ok = False
        elif wall_bad:
            verdict = "wall-time warning ⚠️"
        else:
            verdict = "ok ✅"

        def pct(now_v: float, base_v: float) -> str:
            if base_v == 0:
                return "—"
            return f"{(now_v / base_v - 1.0) * 100:+.1f}%"

        lines.append(
            f"| {name} "
            f"| {base_flashes} → {now_flashes} | {pct(now_flashes, base_flashes)} "
            f"| {_fmt(base_flash_wall)} → {_fmt(now_flash_wall)} | {pct(now_flash_wall, base_flash_wall)} "
            f"| {_fmt(base_total_wall)} → {_fmt(now_total_wall)} | {pct(now_total_wall, base_total_wall)} "
            f"| {now['converged']} | {verdict} |"
        )

        if flash_bad:
            print(
                f"REGRESSION {name}: flash count {base_flashes} -> {now_flashes} "
                f"(> {FLASH_TOLERANCE:.0%} of baseline)",
                file=sys.stderr,
            )
        if wall_bad and fail_on == "all":
            print(
                f"REGRESSION {name}: wall time beyond {WALL_TOLERANCE:.0%} of baseline "
                f"(flash_wall {base_flash_wall} -> {now_flash_wall} s, "
                f"total {base_total_wall} -> {now_total_wall} s)",
                file=sys.stderr,
            )
    return lines, ok


def _baseline_doc(baseline: dict[str, Any]) -> str:
    meta = baseline.get("metadata", {})
    generated = f"generated from commit {meta.get('commit', '?')}"
    return f"Benchmark baseline check (P0-06, baseline {generated})\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="bench_baseline",
        description="Flash-count + wall-time benchmark baseline (spec P0-06)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--update", action="store_true", help="re-run and rewrite bench/baseline.json")
    mode.add_argument("--check", action="store_true", help="re-run and compare against bench/baseline.json")
    parser.add_argument(
        "--fail-on",
        choices=("all", "flashes"),
        default="all",
        help="which rules exit non-zero: both (default) or flash counts only (CI; wall time is noisy)",
    )
    args = parser.parse_args()

    if args.update:
        doc = run_all()
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(doc, indent=2) + "\n")
        meta = doc["metadata"]
        print(f"baseline written: {BASELINE_PATH} (python {meta['python']}, {meta['platform']})")
        for name, record in doc["cases"].items():
            v2_equiv = record["flashes"] - record["flashes_pt"] - record["flashes_ph"] - record["flashes_ps"]
            print(
                f"  {name:<16} flashes {record['flashes']:>6} "
                f"(pt/ph/ps {record['flashes_pt']}/{record['flashes_ph']}/{record['flashes_ps']}, "
                f"v2 flash-equivalents {v2_equiv}, "
                f"props {record['props_calls']})  "
                f"flash_wall {record['flash_wall_s']:.2f} s  "
                f"total {record['total_wall_s']:.2f} s  "
                f"passes {record['solver_passes']}  converged {record['converged']}"
            )
        return 0

    if not BASELINE_PATH.exists():
        print(f"no baseline at {BASELINE_PATH}; generate one with --update", file=sys.stderr)
        return 2
    baseline = json.loads(BASELINE_PATH.read_text())
    lines, ok = check(baseline, args.fail_on)
    print(_baseline_doc(baseline))
    for line in lines:
        print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
