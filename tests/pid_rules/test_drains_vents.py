"""Tests for the S-17 drains_vents rule."""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import PID, InlineKind, PidLine
from ngdesign.contracts.plugins import PidRule
from ngdesign.flowsheets.samples import sample_pid

RULE = "drains_vents"


def _rule() -> PidRule:
    rule: PidRule = registry.create("pid_rule", RULE)
    return rule


def _line(pid: PID, number: str) -> PidLine:
    return next(ln for ln in pid.lines if ln.number == number)


def test_finds_violations_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    # All five sample lines touch equipment; none has a drain or vent yet.
    assert len(violations) == 10
    assert {v.target for v in violations} == {
        '8"-PG-1001-B1',
        '8"-PG-1002-B1',
        '6"-PG-1003-D1',
        '3"-PL-1004-B1',
        '2"-PL-1005-B1',
    }
    assert all(v.rule == RULE for v in violations)


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    assert _rule().apply(fixed).model_dump() == fixed.model_dump()


def test_drain_low_vent_high() -> None:
    fixed = _rule().apply(sample_pid())
    # Line 1001: boundary (z=0) -> V-101 N1 (z=1500). Start is lower: drain at
    # index 0, vent appended.
    line = _line(fixed, '8"-PG-1001-B1')
    assert line.items[0].kind == InlineKind.DRAIN
    assert line.items[-1].kind == InlineKind.VENT
    # Line 1003: K-101 N2 (z=1200) -> boundary (z=0). Start is higher: vent at
    # index 0, drain appended.
    line = _line(fixed, '6"-PG-1003-D1')
    assert line.items[0].kind == InlineKind.VENT
    assert line.items[-1].kind == InlineKind.DRAIN


def test_dbb_note_on_hydrocarbon_services() -> None:
    fixed = _rule().apply(sample_pid())
    for number in ('8"-PG-1001-B1', '2"-PL-1005-B1'):
        line = _line(fixed, number)
        for it in line.items:
            if it.kind in (InlineKind.DRAIN, InlineKind.VENT):
                assert it.note == "3/4in DBB"


def test_plain_note_on_non_hydrocarbon_service() -> None:
    from ngdesign.contracts import LineEnd, PidLine

    pid = sample_pid()
    pid.lines.append(
        PidLine(
            number='2"-W-1006-A1',
            nps_in=2,
            fluid_code="W",
            pipe_class="A1",
            design_pressure_Pa=1.0e6,
            design_temperature_K=323.15,
            start=LineEnd(equipment="V-101", nozzle="N6"),
            end=LineEnd(boundary="COOLING"),
        )
    )
    fixed = _rule().apply(pid)
    line = _line(fixed, '2"-W-1006-A1')
    for it in line.items:
        if it.kind in (InlineKind.DRAIN, InlineKind.VENT):
            assert it.note == "3/4in"


def test_boundary_to_boundary_lines_ignored() -> None:
    from ngdesign.contracts import LineEnd, PidLine

    pid = sample_pid()
    pid.lines.append(
        PidLine(
            number='2"-W-1007-A1',
            nps_in=2,
            fluid_code="W",
            pipe_class="A1",
            design_pressure_Pa=1.0e6,
            design_temperature_K=323.15,
            start=LineEnd(boundary="A"),
            end=LineEnd(boundary="B"),
        )
    )
    assert not [v for v in _rule().check(pid) if v.target == '2"-W-1007-A1']
    fixed = _rule().apply(pid)
    assert _line(fixed, '2"-W-1007-A1').items == []
