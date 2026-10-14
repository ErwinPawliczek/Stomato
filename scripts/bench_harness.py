#!/usr/bin/env python3
"""Benchmark + profile harness over the slice solve and golden thermo cases (C-7).

Feeds open question OQ-1 (stomato-core parity/speed baseline) with timing
evidence for the Python reference engine. Three lenses over the same cases
(``scripts/bench_cases.py``):

- ``pyperf``    -- statistical timing table (mean +- std dev per case).
- ``cprofile``  -- deterministic hot-spot ranking per case (+ ``.prof`` dumps).
- ``pyspy``     -- sampling flamegraph of a case under load (needs py-spy).

Usage::

    uv run --with pyperf --with py-spy python scripts/bench_harness.py --mode all
    uv run --with pyperf python scripts/bench_harness.py --mode pyperf
    uv run python scripts/bench_harness.py --mode cprofile --case solver

pyperf and py-spy are harness-only tools, deliberately NOT project
dependencies: when missing, the harness re-executes itself through
``uv run --with ...`` (ephemeral, does not touch pyproject.toml/uv.lock).

Artifacts land in ``--out`` (default ``out/bench/``, gitignored): one pyperf
``.json`` per case (re-comparable with ``pyperf compare_to``), one ``.prof``
per case, and one flamegraph ``.svg`` per py-spy run.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import os
import pstats
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

SCRIPT = Path(__file__).resolve()
REPO_ROOT = SCRIPT.parent.parent
DEFAULT_OUT = REPO_ROOT / "out" / "bench"
BOOTSTRAP_ENV = "_C07_BENCH_BOOTSTRAP"

if TYPE_CHECKING:
    import pyperf


# --------------------------------------------------------------------------- runtimes


def _uv() -> str | None:
    found = shutil.which("uv")
    if found is None:
        candidate = Path.home() / ".local" / "bin" / "uv"
        found = str(candidate) if candidate.exists() else None
    return found


def ensure_pyperf() -> None:
    """Import pyperf or re-exec the whole CLI under an ephemeral uv overlay.

    pyperf is a harness-only tool (AGENTS.md forbids new project dependencies),
    so it is pulled in ephemerally at run time instead of declared in
    pyproject.toml.
    """
    try:
        import pyperf  # noqa: F401
    except ModuleNotFoundError:
        if os.environ.get(BOOTSTRAP_ENV) == "1":
            raise SystemExit(
                "pyperf missing despite bootstrap; install it manually: uv tool install pyperf"
            ) from None
        uv = _uv()
        if uv is None:
            raise SystemExit(
                "pyperf not installed and uv not found to fetch it. "
                "Run: uv run --with pyperf python scripts/bench_harness.py " + " ".join(sys.argv[1:])
            ) from None
        env = dict(os.environ, BOOTSTRAP_ENV="1")
        # Let uv resolve a fresh interpreter: passing sys.executable would pin
        # the current (pyperf-less) environment and loop forever.
        os.execve(
            uv,
            [uv, "run", "--with", "pyperf", "--", "python", str(SCRIPT), *sys.argv[1:]],
            env,
        )


def py_spy_command() -> list[str]:
    """Locate py-spy, falling back to an ephemeral uv overlay invocation."""
    exe = shutil.which("py-spy")
    if exe is not None:
        return [exe]
    uv = _uv()
    if uv is None:
        raise SystemExit("py-spy not installed and uv not found to fetch it (pip install py-spy)")
    return [uv, "run", "--with", "py-spy", "--", "py-spy"]


def select_cases(case_filter: str | None) -> dict[str, Callable[[], object]]:
    from bench_cases import default_cases

    cases = default_cases()
    if case_filter is None:
        return cases
    matches = {name: fn for name, fn in cases.items() if case_filter in name}
    if not matches:
        raise SystemExit(f"no case matches {case_filter!r}; have: {', '.join(cases)}")
    return matches


# --------------------------------------------------------------------------- modes


# Our flags absent from pyperf's own parser (--values/--processes already exist
# there). They must all be registered so a single argv serves both this process
# and pyperf's worker re-executions.
OUR_FLAGS = ("--case", "--out", "--mode", "--top", "--seconds")


def _forward_case(runner_args: argparse.Namespace, cmd: list[str]) -> None:
    """Forward the case filter to pyperf worker re-executions. Without it a
    filtered manager registers one case while its workers register all of them,
    and worker task 0 would benchmark the wrong case under the filtered name."""
    if getattr(runner_args, "case", None):
        cmd.extend(["--case", runner_args.case])


def run_pyperf(
    cases: dict[str, Callable[[], object]], out_dir: Path, values: int | None, processes: int | None
) -> list[str]:
    """Statistical timing via pyperf.Runner; returns the emitted table rows."""
    import pyperf

    is_worker = "--worker" in sys.argv
    runner = pyperf.Runner(
        program_args=[],
        show_name=False,
        values=None if is_worker else values,
        processes=None if is_worker else processes,
        add_cmdline_args=_forward_case,
    )
    # Our flags ride on pyperf's parser: the manager's sys.argv carries them,
    # and pyperf workers re-execute this script with its own --worker flags.
    for flag in OUR_FLAGS:
        runner.argparser.add_argument(flag)

    # Worker re-execution: run the registration loop so pyperf finds its task;
    # results travel back through the pipe, never through the out dir.
    if is_worker:
        for name, fn in cases.items():
            runner.bench_func(name, fn)
        return []

    rows: list[str] = []
    for name, fn in cases.items():
        bench = runner.bench_func(name, fn)
        if bench is None:
            continue
        bench.dump(str(out_dir / f"{name}.json"), replace=True)
        rows.append(_pyperf_row(name, bench))
    return rows


def _pyperf_row(name: str, bench: pyperf.Benchmark) -> str:
    mean = bench.mean()
    stdev = bench.stdev()
    nvalues = len(bench.get_values())
    return f"{name:<36} {_fmt_seconds(mean):>10} ± {_fmt_seconds(stdev):>9}   ({nvalues} values)"


def _fmt_seconds(seconds: float) -> str:
    for unit, factor in (("s", 1.0), ("ms", 1e-3), ("µs", 1e-6), ("ns", 1e-9)):
        if seconds >= factor:
            return f"{seconds / factor:.3f} {unit}"
    return f"{seconds:.3e} s"


def run_cprofile(cases: dict[str, Callable[[], object]], out_dir: Path, top: int) -> None:
    """Deterministic hot-spot ranking: one warmup run, then one profiled run per
    case (the warmup absorbs lazy imports so the profile shows steady state)."""
    for name, fn in cases.items():
        fn()  # warmup: PR package construction and plugin imports are lazy
        profiler = cProfile.Profile()
        profiler.enable()
        fn()
        profiler.disable()
        prof_path = out_dir / f"{name}.prof"
        profiler.dump_stats(str(prof_path))

        buffer = io.StringIO()
        stats = pstats.Stats(profiler, stream=buffer)
        stats.sort_stats("cumulative").print_stats(top)
        print(f"== cProfile: {name}  (top {top} by cumulative, full dump: {prof_path}) ==")
        lines = buffer.getvalue().splitlines()
        # Skip pstats' own header noise, keep the table.
        table = [ln for ln in lines if ln.strip()]
        start = next(i for i, ln in enumerate(table) if "ncalls" in ln)
        print("\n".join(table[start:]))
        print()


def run_py_spy(case_name: str, out_dir: Path, seconds: int) -> Path | None:
    """Sampling flamegraph: runs the case in a loop in a child process while
    py-spy records it. Returns the flamegraph path, or None on attach failure."""
    child_cmd = [
        sys.executable,
        str(SCRIPT),
        "--mode",
        "loop",
        "--case",
        case_name,
        "--seconds",
        str(seconds + 5),  # outlive the recording window
    ]
    flamegraph = out_dir / f"{case_name}.flame.svg"
    record_cmd = py_spy_command() + [
        "record",
        "--pid",
        "PLACEHOLDER",
        "--output",
        str(flamegraph),
        "--format",
        "flamegraph",
        "--duration",
        str(seconds),
        "--rate",
        "100",
        "--nonblocking",
    ]
    child = subprocess.Popen(child_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.0)  # let the child reach its case loop before attaching
        cmd = [arg.replace("PLACEHOLDER", str(child.pid)) for arg in record_cmd]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not flamegraph.exists():
            print(f"py-spy failed for {case_name} (exit {result.returncode}):", file=sys.stderr)
            print(result.stderr.strip(), file=sys.stderr)
            return None
        print(f"flamegraph: {flamegraph}")
        return flamegraph
    finally:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()


def run_loop(case_name: str, seconds: int) -> None:
    """Internal mode: repeat one case in-process until the deadline
    (the workload py-spy attaches to)."""
    cases = select_cases(case_name)
    cases[case_name]()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        cases[case_name]()


# --------------------------------------------------------------------------- CLI


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bench_harness",
        description="cProfile + py-spy + pyperf harness over the slice solve and golden thermo cases",
    )
    parser.add_argument(
        "--mode",
        choices=("pyperf", "cprofile", "pyspy", "loop", "all"),
        default="pyperf",
        help="lens to run (default: pyperf; 'all' = cprofile, pyspy, pyperf)",
    )
    parser.add_argument("--case", help="substring filter over case names (default: all)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="artifact directory")
    parser.add_argument("--top", type=int, default=15, help="cProfile rows to show per case")
    parser.add_argument("--seconds", type=int, default=8, help="py-spy recording seconds per case")
    parser.add_argument("--values", type=int, default=None, help="pyperf: values per worker process")
    parser.add_argument("--processes", type=int, default=None, help="pyperf: worker processes per case")
    # parse_known_args: pyperf worker re-executions carry pyperf's own flags.
    args, _ = parser.parse_known_args(argv)
    return args


def main() -> int:
    args = parse_args()
    out_dir: Path = args.out
    is_worker = "--worker" in sys.argv

    if args.mode == "loop":
        run_loop(args.case, args.seconds)
        return 0

    if is_worker:
        # pyperf worker re-execution: only the timed path runs — no profile
        # collection, no flamegraphs, no artifact writes on the worker side.
        ensure_pyperf()
        run_pyperf(select_cases(args.case), out_dir, args.values, args.processes)
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    if args.mode in ("cprofile", "all"):
        run_cprofile(select_cases(args.case), out_dir, args.top)
    if args.mode in ("pyperf", "all"):
        ensure_pyperf()
        rows = run_pyperf(select_cases(args.case), out_dir, args.values, args.processes)
        if rows:
            print("== pyperf table (Python reference engine, stomato) ==")
            for row in rows:
                print(row)
        print(
            f"benchmarks saved to {out_dir}/"
            "  (compare: uv run --with pyperf pyperf compare_to <a.json> <b.json>)"
        )
    if args.mode in ("pyspy", "all"):
        for name in select_cases(args.case):
            run_py_spy(name, out_dir, args.seconds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
