"""Spec P2-02: the diagnostics contracts round-trip through JSON and the solve
status is derived, never set by hand: ``failed`` when any unit failed outright
(a non-upstream UnitError), else the tear convergence flag as
``converged``/``not_converged``. Upstream skips alone are not failures.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ngdesign.contracts import Flowsheet, PortRef, SolvedFlowsheet, StreamSpec, UnitSpec
from ngdesign.contracts.diagnostics import BlockRecord, TearRecord, UnitError


def _solved(*, converged: bool = True, errors: list[UnitError] | None = None) -> SolvedFlowsheet:
    flowsheet = Flowsheet(
        name="diag",
        units=[UnitSpec(tag="P-101", kind="pump")],
        streams=[StreamSpec(id="S-001", source=PortRef(unit="P-101", port="outlet"))],
    )
    return SolvedFlowsheet(
        flowsheet=flowsheet,
        streams={},
        units={},
        converged=converged,
        errors=errors or [],
    )


def _block() -> BlockRecord:
    return BlockRecord(
        units=["U-101", "U-102"],
        tears=["S-003"],
        iterations=3,
        converged=True,
        records=[
            TearRecord(
                iteration=1,
                stream_id="S-003",
                residual_max=0.5,
                residual_vector={"C1": 0.5, "T": 0.1, "P": 0.01},
                acceleration="direct",
                q=None,
            ),
            TearRecord(
                iteration=2,
                stream_id="S-003",
                residual_max=0.01,
                residual_vector={"C1": 0.01, "T": 0.001, "P": 0.0001},
                acceleration="wegstein",
                q=-2.5,
            ),
        ],
        wall_s=0.25,
    )


def test_diagnostics_round_trip_json() -> None:
    block = _block()
    restored = BlockRecord.model_validate_json(block.model_dump_json())
    assert restored == block
    assert restored.records[1].q == pytest.approx(-2.5)

    error = UnitError(
        tag="U-102",
        kind="compressor",
        error_type="ValueError",
        message="two-phase inlet",
        stage="solve",
    )
    assert UnitError.model_validate_json(error.model_dump_json()) == error


def test_diagnostics_models_are_frozen() -> None:
    error = UnitError(tag="U-102", kind="compressor", error_type="ValueError", message="x", stage="solve")
    with pytest.raises(ValidationError):
        error.message = "y"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        _block().iterations = 4  # type: ignore[misc]


def test_status_converged() -> None:
    assert _solved(converged=True).status == "converged"


def test_status_not_converged() -> None:
    assert _solved(converged=False).status == "not_converged"


def test_status_failed_on_non_upstream_error() -> None:
    error = UnitError(
        tag="U-102",
        kind="compressor",
        error_type="ValueError",
        message="two-phase inlet",
        stage="solve",
        upstream=False,
    )
    # Even with converged=True, a unit that failed outright fails the solve.
    assert _solved(converged=True, errors=[error]).status == "failed"


def test_status_upstream_skip_alone_is_not_a_failure() -> None:
    skip = UnitError(tag="U-103", kind="pump", error_type="", message="skipped", stage="solve", upstream=True)
    assert _solved(converged=True, errors=[skip]).status == "converged"
    assert _solved(converged=False, errors=[skip]).status == "not_converged"
