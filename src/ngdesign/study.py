"""Case-study runner (spec P2-04): parameter grid -> N solves -> table.

One runner serves the CLI (:mod:`ngdesign.cli`, the ``study`` command), the API
(``POST /api/study``) and the agent (the ``case_study`` tool): a parameter grid
over write addresses (full cartesian product of the axes), one solve per case,
rows in a deterministic, sequential order.

Solve path per case (the P2-01 seams, used exactly as registered):

- a flowsheet without ``design_specs`` runs the bare
  :class:`~ngdesign.solver.sequential_modular.SequentialModular` inner solve
  with ``warm_start=...``: every case starts each recycle from the previous
  converged tear vectors instead of the mean-of-feeds guess;
- a flowsheet carrying ``design_specs`` goes through the registered
  ``sequential_modular`` solver (``ngdesign.solver.design_specs``, the
  warm-started outer loop), because that loop owns warm-starting its own inner
  solves; the ``solver`` name applies there.

A case whose units raise or whose recycles do not converge (spec P2-02,
``status == "failed"``) is recorded with its ``UnitError`` list in
:attr:`StudyResult.failed` and the sweep continues. A case whose write address
cannot even be applied (unknown address or axis, a structurally bad flow) is
recorded the same way, with the exception's text on ``StudyRow.message`` and
an empty ``errors``: there is no unit to blame yet.

Inputs and outputs are variable addresses over the flowsheet grammar of
:mod:`ngdesign.variables` (:func:`assign` to set, :func:`resolve` to read); an
output address a case cannot answer reads ``None`` - the column stays honest
instead of aborting the sweep.
"""

from __future__ import annotations

import csv
import io
import itertools
import time
from collections.abc import Callable

from ngdesign import registry
from ngdesign.contracts import Flowsheet, Model, SolvedFlowsheet
from ngdesign.contracts.components import resolve_set
from ngdesign.contracts.diagnostics import SolveStatus, TearRecord, UnitError
from ngdesign.contracts.plugins import Thermo
from ngdesign.solver.sequential_modular import SequentialModular, _tear_vector
from ngdesign.variables import assign, resolve

__all__ = [
    "Axis",
    "CaseStudy",
    "CaseStudyRequest",
    "StudyResult",
    "StudyRow",
    "run",
    "to_csv",
    "to_markdown",
]


class Axis(Model):
    """One swept address and the values it takes; every combination with the
    other axes (the full grid) becomes one case."""

    address: str
    values: list[float]


class CaseStudy(Model):
    """A parameter grid over a base flowsheet with the outputs to report.

    ``inputs`` are write addresses (:func:`~ngdesign.variables.assign`); the
    full cartesian product of their values is the case list, in axis order
    (first axis outermost). ``outputs`` are readable addresses
    (:func:`~ngdesign.variables.resolve`) evaluated on each case's result.
    """

    id: str
    inputs: list[Axis]
    outputs: list[str]
    base: Flowsheet


class CaseStudyRequest(Model):
    """The ``POST /api/study`` body: a :class:`CaseStudy` without ``base`` -
    the route fills it from the current project's flowsheet."""

    id: str
    inputs: list[Axis]
    outputs: list[str]


class StudyRow(Model):
    """One case of the grid: its inputs, its read outputs and how it solved.

    ``status`` mirrors the case's :class:`~ngdesign.contracts.SolvedFlowsheet`
    ``status`` (spec P2-02); ``errors`` carries the case's ``UnitError`` list.
    ``message`` is set (and ``errors`` empty) when the case failed before any
    unit ran: a write address :func:`~ngdesign.variables.assign` rejected -
    the exception's text names the mistake. An output address the case cannot
    answer reads ``None``.
    """

    inputs: dict[str, float]
    outputs: dict[str, float | None]
    status: SolveStatus
    iterations: int = 0
    wall_s: float = 0.0
    errors: list[UnitError] = []
    message: str | None = None


class StudyResult(Model):
    """Every case's row in sweep order. ``failed`` is the subset of rows whose
    ``status`` is ``"failed"``: the same rows, singled out for the caller."""

    rows: list[StudyRow]
    failed: list[StudyRow]


def run(
    study: CaseStudy,
    thermo: Thermo,
    *,
    solver: str = "sequential_modular",
    warm_start: bool = True,
    on_progress: Callable[[TearRecord], None] | None = None,
) -> StudyResult:
    """Run the whole grid sequentially and deterministically; rows in order.

    ``thermo`` is the property package for the base flowsheet (one instance
    serves all cases: assigning never changes ``flowsheet.components``). With
    ``warm_start`` every case after the first injects the previous converged
    case's tear vectors; a failed case leaves the warm start untouched. With
    ``warm_start=False`` every recycle starts cold from the mean-of-feeds
    guess, byte-identically to the un-warm-started solver.

    Raises ValueError for a structurally impossible study (no input axes, an
    axis with no values) and never for a failed case. ``on_progress`` (spec
    P3-02, pass-through) is called with every tear record each case's solve
    produces, on both solve paths.
    """
    if not study.inputs:
        raise ValueError("a case study needs at least one input axis")
    for axis in study.inputs:
        if not axis.values:
            raise ValueError(f"input axis {axis.address!r} has no values")
    components = tuple(resolve_set(study.base.components).ids)
    with_specs = bool(study.base.design_specs)
    warm: dict[str, list[float]] | None = None
    rows: list[StudyRow] = []
    for values in itertools.product(*(axis.values for axis in study.inputs)):
        case_inputs = {axis.address: float(v) for axis, v in zip(study.inputs, values, strict=True)}
        start = time.perf_counter()
        try:
            fs = study.base
            for axis, v in zip(study.inputs, values, strict=True):
                fs = assign(fs, axis.address, float(v))
            solved = _solve_case(fs, thermo, warm, with_specs, solver, warm_start, on_progress)
        except ValueError as exc:
            # The contracts or a unit rejected the case outright: record it
            # and sweep on (spec P2-04 - the result grades, the sweep continues).
            rows.append(
                StudyRow(
                    inputs=case_inputs,
                    outputs={addr: None for addr in study.outputs},
                    status="failed",
                    iterations=0,
                    wall_s=time.perf_counter() - start,
                    errors=[],
                    message=str(exc),
                )
            )
            continue
        row = StudyRow(
            inputs=case_inputs,
            outputs={addr: _read(addr, solved) for addr in study.outputs},
            status=solved.status,
            iterations=solved.iterations,
            wall_s=time.perf_counter() - start,
            errors=list(solved.errors),
        )
        rows.append(row)
        if solved.status != "failed":
            warm = {sid: _tear_vector(state, components) for sid, state in solved.streams.items()}
    return StudyResult(rows=rows, failed=[row for row in rows if row.status == "failed"])


def _solve_case(
    fs: Flowsheet,
    thermo: Thermo,
    warm: dict[str, list[float]] | None,
    with_specs: bool,
    solver: str,
    warm_start: bool,
    on_progress: Callable[[TearRecord], None] | None,
) -> SolvedFlowsheet:
    """One case solve through the right P2-01 seam (see the module docstring).

    The bare inner solve takes the caller's warm start (``warm_start=False``
    keeps the mean-of-feeds init byte-identically); the design-spec outer loop
    warm-starts its own inner solves. Both forward the P3-02 ``on_progress``
    callback.
    """
    if with_specs:
        solved: SolvedFlowsheet = registry.create("solver", solver).solve(fs, thermo, on_progress=on_progress)
        return solved
    return SequentialModular().solve(fs, thermo, warm if warm_start else None, on_progress=on_progress)


def _read(addr: str, solved: SolvedFlowsheet) -> float | None:
    """One output address on one case's result; unreadable reads ``None``."""
    try:
        return resolve(addr, solved)
    except ValueError:
        return None


def _columns(result: StudyResult) -> tuple[list[str], list[str]]:
    """The input and output column names, in stable encounter order."""
    ins: list[str] = []
    outs: list[str] = []
    seen_in: set[str] = set()
    seen_out: set[str] = set()
    for row in result.rows:
        for addr in row.inputs:
            if addr not in seen_in:
                seen_in.add(addr)
                ins.append(addr)
        for addr in row.outputs:
            if addr not in seen_out:
                seen_out.add(addr)
                outs.append(addr)
    return ins, outs


def _fmt(value: float | None) -> str:
    """A cell value: blank for the unreadable (``None``), 6 significant figures."""
    return "" if value is None else f"{value:.6g}"


def to_csv(result: StudyResult) -> str:
    """The table as CSV: the inputs, then the outputs, then status, iterations
    and per-case wall time (columns in encounter order)."""
    ins, outs = _columns(result)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([*ins, *outs, "status", "iterations", "wall_s"])
    for row in result.rows:
        writer.writerow(
            [
                *(_fmt(row.inputs.get(addr)) for addr in ins),
                *(_fmt(row.outputs.get(addr)) for addr in outs),
                row.status,
                str(row.iterations),
                f"{row.wall_s:.6f}",
            ]
        )
    return buffer.getvalue()


def to_markdown(result: StudyResult) -> str:
    """The table as a Markdown pipe table (the CLI and agent display)."""
    ins, outs = _columns(result)
    header = [*ins, *outs, "status", "iterations"]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in result.rows:
        cells = [
            *(_fmt(row.inputs.get(addr)) for addr in ins),
            *(_fmt(row.outputs.get(addr)) for addr in outs),
            row.status,
            str(row.iterations),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
