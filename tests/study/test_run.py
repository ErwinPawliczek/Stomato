"""P2-04 acceptance: the case-study runner over the slice flowsheet.

- a P_out sweep answers converged rows with monotonically rising power;
- a case forced to fail by an out-of-range value is a ``failed`` row carrying
  its ``UnitError`` and the sweep continues;
- unreadable output addresses read ``None``, grids run in axis order, warm
  starts and cold starts agree on the converged answers, and the tables render.
"""

from __future__ import annotations

from typing import cast

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.registry import create as _create_plugin
from ngdesign.study import Axis, CaseStudy, StudyResult, run, to_csv, to_markdown


def _sweep(values: list[float], outputs: list[str] | None = None) -> StudyResult:
    """One P_out axis over the slice (the spec's example sweep)."""
    return run(
        CaseStudy(
            id="test",
            inputs=[Axis(address="K-101.params.P_out", values=values)],
            outputs=outputs if outputs is not None else ["K-101.power_W", "E-101.duty_W"],
            base=slice_fs.build(),
        ),
        _thermo(),
    )


def _thermo() -> Thermo:
    return cast(Thermo, _create_plugin("thermo", "pr"))


def test_slice_sweep_converges_with_monotonic_power() -> None:
    result = _sweep([7.0e6, 8.0e6, 9.0e6])
    assert len(result.rows) == 3
    assert result.failed == []
    assert all(row.status == "converged" for row in result.rows)
    powers = [row.outputs["K-101.power_W"] for row in result.rows]
    assert all(power is not None for power in powers)
    values = [cast(float, power) for power in powers]
    assert all(b > a for a, b in zip(values, values[1:], strict=False)), values


def test_failing_case_keeps_the_sweep_going() -> None:
    """P_out below the contactor's water spec cannot converge: the middle case
    is a failed row with its UnitErrors, the sweep still answers the others."""
    result = _sweep([7.5e6, -1.0, 8.5e6])
    assert [row.inputs["K-101.params.P_out"] for row in result.rows] == [7.5e6, -1.0, 8.5e6]
    assert [row.status for row in result.rows] == ["converged", "failed", "converged"]
    assert result.failed == [row for row in result.rows if row.status == "failed"]
    failed = result.failed[0]
    assert failed.errors, "the failed case carries no UnitError"
    # The root cause comes from K-101; downstream units (E-101, T-101) report
    # that they were skipped for lack of an inlet state.
    assert any(error.tag == "K-101" and "P_out" in (error.message or "") for error in failed.errors)
    assert all(error.tag for error in failed.errors)
    powers = [row.outputs["K-101.power_W"] for row in result.rows if row.status == "converged"]
    values = [cast(float, power) for power in powers]
    assert all(b > a for a, b in zip(values, values[1:], strict=False))


def test_unreadable_output_address_reads_none() -> None:
    result = _sweep([8.0e6], outputs=["K-101.power_W", "no-such-unit.power_W"])
    row = result.rows[0]
    assert isinstance(row.outputs["K-101.power_W"], float)
    assert row.outputs["no-such-unit.power_W"] is None


def test_grid_runs_in_axis_order() -> None:
    result = run(
        CaseStudy(
            id="grid",
            inputs=[
                Axis(address="K-101.params.P_out", values=[7.5e6, 8.5e6]),
                Axis(address="S-001.feed.P", values=[6.0e6, 6.5e6]),
            ],
            outputs=["K-101.power_W"],
            base=slice_fs.build(),
        ),
        _thermo(),
    )
    assert [(r.inputs["K-101.params.P_out"], r.inputs["S-001.feed.P"]) for r in result.rows] == [
        (7.5e6, 6.0e6),
        (7.5e6, 6.5e6),
        (8.5e6, 6.0e6),
        (8.5e6, 6.5e6),
    ]


def test_warm_start_and_cold_start_agree() -> None:
    """The warm start may change iteration counts, never the converged answers."""
    warm = _sweep([7.0e6, 8.0e6, 9.0e6])
    cold = run(
        CaseStudy(
            id="cold",
            inputs=[Axis(address="K-101.params.P_out", values=[7.0e6, 8.0e6, 9.0e6])],
            outputs=["K-101.power_W", "E-101.duty_W"],
            base=slice_fs.build(),
        ),
        _thermo(),
        warm_start=False,
    )
    for w, c in zip(warm.rows, cold.rows, strict=True):
        assert w.inputs == c.inputs
        assert w.outputs == c.outputs


def test_structurally_impossible_studies_raise() -> None:
    with pytest.raises(ValueError, match="at least one input axis"):
        run(
            CaseStudy(id="empty", inputs=[], outputs=["K-101.power_W"], base=slice_fs.build()),
            _thermo(),
        )
    with pytest.raises(ValueError, match="has no values"):
        run(
            CaseStudy(
                id="blank",
                inputs=[Axis(address="K-101.params.P_out", values=[])],
                outputs=["K-101.power_W"],
                base=slice_fs.build(),
            ),
            _thermo(),
        )


def test_unknown_write_address_fails_that_case_and_sweeps_on() -> None:
    result = run(
        CaseStudy(
            id="bad-addr",
            inputs=[Axis(address="X-999.params.P_out", values=[7.5e6, 8.5e6])],
            outputs=["K-101.power_W"],
            base=slice_fs.build(),
        ),
        _thermo(),
    )
    assert len(result.rows) == 2 and len(result.failed) == 2
    assert result.rows[0].message is not None and "X-999" in result.rows[0].message


def test_tables_render_the_grid() -> None:
    result = _sweep([8.0e6])
    lines = to_markdown(result).strip().split("\n")
    assert len(lines) == 3  # header + rules + one case
    assert lines[0].split("|")[1].strip() == "K-101.params.P_out"
    cells = to_csv(result).strip().split("\r\n")
    assert len(cells) == 2  # header + one case
    assert "K-101.params.P_out" in cells[0] and "status" in cells[0] and "wall_s" in cells[0]
