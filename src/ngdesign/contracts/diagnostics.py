"""Solve diagnostics: per-unit error records and convergence history (spec P2-02).

A failed unit no longer aborts the solve: the solver records one :class:`UnitError`
per failed or skipped unit, one :class:`TearRecord` per tear stream per iteration
and one :class:`BlockRecord` per executed block, and the partial
``SolvedFlowsheet`` carries them so the UI (Phase 4) and the agent (B-08) can show
what solved, what failed and how the tears converged. Pure data: frozen models,
no behaviour.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict

from .common import Model

#: Where in the solve a unit failed: the port check before any unit ran, the
#: unit's own ``solve()``, or a missing outlet state in the result it returned.
SolveStage = Literal["ports", "solve", "outlet_missing"]

#: The tear acceleration applied at one iteration (``broyden`` is reserved for
#: spec P2-03; the sequential-modular solver only produces direct substitution
#: and bounded Wegstein today).
SolveAcceleration = Literal["direct", "wegstein", "broyden"]

#: Overall solve outcome, derived on ``SolvedFlowsheet``: ``failed`` when any
#: unit failed outright (a non-upstream ``UnitError``), else the tear
#: convergence flag as ``converged`` / ``not_converged``.
SolveStatus = Literal["converged", "not_converged", "failed"]


class UnitError(Model):
    """One unit's failure or skip, as data instead of an aborting exception.

    ``error_type`` is the exception class name; it is ``""`` for an upstream
    skip, where no exception occurred - the unit was skipped because an inlet
    stream had no state (its source unit failed or was skipped).
    """

    model_config = ConfigDict(frozen=True)

    tag: str  # unit tag
    kind: str  # registry kind, e.g. "compressor"
    error_type: str  # exception class name; "" for an upstream skip
    message: str  # the exception message, or why the unit was skipped
    stage: SolveStage
    upstream: bool = False  # True when skipped because an inlet came from a failed unit


class TearRecord(Model):
    """One tear stream's residuals at one tear iteration.

    ``residual_vector`` holds the same relative measure the convergence test
    uses, ``|y - x| / max(|x|, 1.0)``, keyed by component id then ``"T"`` and
    ``"P"`` (the tear vector's variable order, spec P1-02 slate order).
    ``acceleration`` names the step taken at this iteration; ``q`` is the
    clamped Wegstein factor of the variable with the largest residual, ``None``
    for direct substitution.
    """

    model_config = ConfigDict(frozen=True)

    iteration: int  # 1-based pass over the block
    stream_id: str  # the torn stream
    residual_max: float  # max relative change over the tear vector
    residual_vector: dict[str, float]
    acceleration: SolveAcceleration
    q: float | None = None  # Wegstein factor, None when direct substitution


class BlockRecord(Model):
    """Execution record of one strongly connected component (block).

    An acyclic block runs once (``iterations == 1``, no tears, no records); a
    cyclic block records one :class:`TearRecord` per tear stream per pass, so
    ``len(records) == iterations * len(tears)``. A block with a failed unit, or
    one that could not run at all (a blocked inlet), stops and is marked
    ``converged=False``. ``wall_s`` is timing telemetry: two runs of the same
    flowsheet produce the same record except for it, so equality and hashing
    ignore it - the double-run determinism oracles compare whole solved models.
    """

    model_config = ConfigDict(frozen=True)

    units: list[str]  # unit tags in execution order
    tears: list[str]  # torn stream ids (empty for an acyclic block)
    iterations: int  # passes over the block (1 for acyclic)
    converged: bool
    records: list[TearRecord]
    wall_s: float  # wall time spent in the block, seconds

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BlockRecord):
            return NotImplemented
        return self.model_dump(exclude={"wall_s"}) == other.model_dump(exclude={"wall_s"})

    def __hash__(self) -> int:
        return hash(self.model_dump_json(exclude={"wall_s"}))
