"""Tests for the S-12 nozzle_isolation rule."""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import PID, InlineItem, InlineKind, Valve, ValveType
from ngdesign.flowsheets.samples import sample_pid

RULE = "nozzle_isolation"


def _rule() -> object:
    return registry.create("pid_rule", RULE)


def _line(pid: PID, number: str) -> object:
    return next(ln for ln in pid.lines if ln.number == number)


def test_finds_violations_on_bare_sample() -> None:
    pid = sample_pid()
    violations = _rule().check(pid)
    # Seven line ends land on equipment in the bare sample.
    assert len(violations) == 7
    assert all(v.rule == RULE for v in violations)
    assert {v.target for v in violations} == {
        '8"-PG-1001-B1',
        '8"-PG-1002-B1',
        '6"-PG-1003-D1',
        '3"-PL-1004-B1',
        '2"-PL-1005-B1',
    }


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    again = _rule().apply(fixed)
    assert again.model_dump() == fixed.model_dump()


def test_shared_valve_satisfies_both_ends_of_short_line() -> None:
    """Walk semantics: a lone isolation valve appears before any other item from
    BOTH ends of line 1002/1004, so five valves cover the seven equipment ends."""
    fixed = _rule().apply(sample_pid())
    assert len(fixed.valves) == 5
    line = _line(fixed, '8"-PG-1002-B1')
    assert [it.kind for it in line.items] == [InlineKind.VALVE]


def test_boundary_ends_get_no_valve() -> None:
    pid = _rule().apply(sample_pid())
    line = _line(pid, '8"-PG-1001-B1')
    # start = battery limit (no valve), end = V-101 N1 (one valve).
    valve_items = [it for it in line.items if it.kind == InlineKind.VALVE]
    assert len(valve_items) == 1
    # The single valve sits at the equipment end: last in flow order.
    assert line.items[-1].kind == InlineKind.VALVE

    line = _line(pid, '6"-PG-1003-D1')
    # start = K-101 N2 (one valve), end = boundary E-101 (none).
    valve_items = [it for it in line.items if it.kind == InlineKind.VALVE]
    assert len(valve_items) == 1
    assert line.items[0].kind == InlineKind.VALVE


def test_valves_match_pipe_class_and_line_size() -> None:
    pid = _rule().apply(sample_pid())
    line = _line(pid, '8"-PG-1002-B1')
    for it in (it for it in line.items if it.kind == InlineKind.VALVE):
        valve = next(v for v in pid.valves if v.tag == it.ref)
        assert valve.type == ValveType.BALL  # B1 default_isolation_valve
        assert valve.nps_in == 8
        assert valve.flange_class == 300  # B1 flange class


def test_existing_valve_is_not_duplicated() -> None:
    pid = sample_pid()
    existing = Valve(tag="HV-1001", type=ValveType.BALL, nps_in=2, flange_class=300)
    pid.valves.append(existing)
    line = _line(pid, '2"-PL-1005-B1')
    line.items.insert(0, InlineItem(kind=InlineKind.VALVE, ref="HV-1001"))
    fixed = _rule().apply(pid)
    # The pre-existing valve serves line 1005's start; the other four valves follow.
    assert len(fixed.valves) == 1 + 4
    assert sum(1 for v in fixed.valves if v.tag == "HV-1001") == 1


def test_tags_allocated_above_max_existing() -> None:
    pid = sample_pid()
    pid.valves.append(Valve(tag="HV-2500", type=ValveType.GATE, nps_in=2, flange_class=300))
    fixed = _rule().apply(pid)
    new_tags = sorted(v.tag for v in fixed.valves if v.tag != "HV-2500")
    assert new_tags[0] == "HV-2501"
    assert len(new_tags) == 5


def test_wrong_valve_type_is_a_violation() -> None:
    pid = sample_pid()
    pid.valves.append(Valve(tag="HV-1001", type=ValveType.GLOBE, nps_in=2, flange_class=300))
    line = _line(pid, '2"-PL-1005-B1')
    line.items.insert(0, InlineItem(kind=InlineKind.VALVE, ref="HV-1001"))
    fixed = _rule().apply(pid)
    # The globe valve does not satisfy the rule; a ball valve is inserted before it.
    assert _rule().check(fixed) == []
    fixed_line = _line(fixed, '2"-PL-1005-B1')
    assert [it.kind for it in fixed_line.items] == [InlineKind.VALVE, InlineKind.VALVE]
    first = next(v for v in fixed.valves if v.tag == fixed_line.items[0].ref)
    assert first.type == ValveType.BALL
