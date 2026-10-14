"""Tests for the S-13 discharge_check_valve rule."""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import InlineItem, InlineKind, Valve, ValveType
from ngdesign.flowsheets.samples import sample_pid

RULE = "discharge_check_valve"


def _rule() -> object:
    return registry.create("pid_rule", RULE)


def _line(pid: object, number: str) -> object:
    return next(ln for ln in pid.lines if ln.number == number)  # type: ignore[attr-defined]


def test_finds_violations_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    # P-101 discharge (2") and K-101 discharge (6") both lack a check valve.
    assert {v.target for v in violations} == {'6"-PG-1003-D1', '2"-PL-1005-B1'}
    assert all(v.rule == RULE for v in violations)


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    assert _rule().apply(fixed).model_dump() == fixed.model_dump()


def test_check_valve_type_by_nps() -> None:
    fixed = _rule().apply(sample_pid())
    for number, expected in (
        ('6"-PG-1003-D1', ValveType.CHECK_DUAL_PLATE),
        ('2"-PL-1005-B1', ValveType.CHECK_SWING),
    ):
        line = _line(fixed, number)
        valve = next(v for v in fixed.valves if v.tag == line.items[0].ref)
        assert valve.type == expected
        assert valve.nps_in == line.nps_in


def test_inserts_before_existing_block_valve() -> None:
    pid = sample_pid()
    hv = Valve(tag="HV-1001", type=ValveType.BALL, nps_in=6, flange_class=600)
    pid.valves.append(hv)
    line = _line(pid, '6"-PG-1003-D1')
    line.items.insert(0, InlineItem(kind=InlineKind.VALVE, ref="HV-1001"))
    fixed = _rule().apply(pid)
    fixed_line = _line(fixed, '6"-PG-1003-D1')
    # Check valve goes directly before the block valve, not after it.
    assert [it.kind for it in fixed_line.items] == [InlineKind.VALVE, InlineKind.VALVE]
    first = next(v for v in fixed.valves if v.tag == fixed_line.items[0].ref)
    second = next(v for v in fixed.valves if v.tag == fixed_line.items[1].ref)
    assert first.type == ValveType.CHECK_DUAL_PLATE
    assert second.tag == "HV-1001"
    assert _rule().check(fixed) == []


def test_suction_and_boundary_lines_untouched() -> None:
    fixed = _rule().apply(sample_pid())
    for number in ('8"-PG-1001-B1', '8"-PG-1002-B1', '3"-PL-1004-B1'):
        assert not [it for it in _line(fixed, number).items if it.kind == InlineKind.VALVE]
