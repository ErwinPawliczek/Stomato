"""Tests for the S-16 pump_instruments rule."""

from __future__ import annotations

from typing import cast

from ngdesign import registry
from ngdesign.contracts import PID, InlineKind, Instrument, PidLine
from ngdesign.contracts.pid import INSTR_TAG_RE
from ngdesign.contracts.plugins import PidRule
from ngdesign.flowsheets.samples import sample_pid

RULE = "pump_instruments"


def _rule() -> PidRule:
    rule: PidRule = registry.create("pid_rule", RULE)
    return rule


def _line(pid: PID, number: str) -> PidLine:
    return next(ln for ln in pid.lines if ln.number == number)


def test_finds_violations_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    # P-101 suction (1004) and discharge (1005) both lack PIs.
    assert {v.target for v in violations} == {'3"-PL-1004-B1', '2"-PL-1005-B1'}
    assert all(v.rule == RULE for v in violations)


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    assert _rule().apply(fixed).model_dump() == fixed.model_dump()


def test_pis_connected_to_line_numbers_with_taps() -> None:
    fixed = _rule().apply(sample_pid())
    pis = [i for i in fixed.instruments if i.function == "PI"]
    assert {i.connected_to for i in pis} == {'3"-PL-1004-B1', '2"-PL-1005-B1'}
    for pi in pis:
        assert INSTR_TAG_RE.match(pi.tag)
        assert pi.tag == f"PI-{pi.loop}"
        line = _line(fixed, pi.connected_to)
        taps = [it for it in line.items if it.kind == InlineKind.INSTRUMENT_TAP]
        assert len(taps) == 1
        assert taps[0].ref == pi.tag
    # Discharge tap sits at the pump end (index 0); suction tap at the pump end
    # (last item).
    assert cast(str, [it.ref for it in _line(fixed, '2"-PL-1005-B1').items][0]).startswith("PI-")


def test_loops_allocated_above_max_existing() -> None:
    pid = sample_pid()
    pid.instruments.append(Instrument(tag="FT-1050", function="FT", loop=1050, connected_to='8"-PG-1001-B1'))
    fixed = _rule().apply(pid)
    pump_loops = sorted(i.loop for i in fixed.instruments if i.function == "PI")
    assert pump_loops == [1051, 1052]


def test_compressor_not_touched() -> None:
    fixed = _rule().apply(sample_pid())
    assert not [i for i in fixed.instruments if i.connected_to == '6"-PG-1003-D1']
