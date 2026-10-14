"""S-12: P&ID rule — isolation valve at every process nozzle.

Every line end that connects to an equipment nozzle gets a block valve adjacent
to the nozzle: walking the line's items from that end, an isolation valve (type
= the pipe class ``default_isolation_valve``, same NPS as the line, flange class
of the pipe class) must appear before any item other than check valves, drains,
vents, instrument taps and reducers.  Those are allowed to sit between the
nozzle and the block valve so the other P&ID rules can insert them without
breaking this one.
"""

from __future__ import annotations

import re

from ngdesign.contracts import (
    PID,
    InlineItem,
    InlineKind,
    PidLine,
    RuleViolation,
    Valve,
    ValveType,
)
from ngdesign.data import pipe_classes
from ngdesign.registry import register

RULE_NAME = "nozzle_isolation"
_TAG_RE = re.compile(r"^HV-(\d{4})$")
_FIRST_TAG = 1001

# Item kinds that may sit between the nozzle and the isolation valve.
_PREFIX_KINDS = frozenset(
    {
        InlineKind.DRAIN,
        InlineKind.VENT,
        InlineKind.INSTRUMENT_TAP,
        InlineKind.REDUCER_CONC,
        InlineKind.REDUCER_ECC,
    }
)
_CHECK_TYPES = frozenset({ValveType.CHECK_SWING, ValveType.CHECK_PISTON, ValveType.CHECK_DUAL_PLATE})


def _is_check_valve(item: InlineItem, pid: PID) -> bool:
    if item.kind != InlineKind.VALVE or item.ref is None:
        return False
    valve = next((v for v in pid.valves if v.tag == item.ref), None)
    return valve is not None and valve.type in _CHECK_TYPES


def _allowed_before_valve(item: InlineItem, pid: PID) -> bool:
    """Items that may legally appear between the nozzle and the block valve."""
    return item.kind in _PREFIX_KINDS or _is_check_valve(item, pid)


def _is_expected_isolation(valve: Valve, line: PidLine) -> bool:
    expected_type = ValveType(pipe_classes()[line.pipe_class]["default_isolation_valve"])
    expected_class = int(pipe_classes()[line.pipe_class]["flange_class"])
    return (
        valve.type == expected_type and valve.nps_in == line.nps_in and valve.flange_class == expected_class
    )


def _end_missing_valve(line: PidLine, pid: PID, at_end: bool) -> bool:
    """True if the line end at equipment lacks an adjacent isolation valve."""
    items = line.items if not at_end else list(reversed(line.items))
    for item in items:
        if _allowed_before_valve(item, pid):
            continue
        if item.kind == InlineKind.VALVE and item.ref is not None:
            valve = next((v for v in pid.valves if v.tag == item.ref), None)
            if valve is not None and _is_expected_isolation(valve, line):
                return False
        return True
    return True  # no items at all: the valve is missing


def _insertion_index(line: PidLine, pid: PID, at_end: bool) -> int:
    """Index just past the allowed prefix, walking from the given end."""
    items = line.items if not at_end else list(reversed(line.items))
    count = 0
    for item in items:
        if not _allowed_before_valve(item, pid):
            break
        count += 1
    return count if not at_end else len(line.items) - count


def _next_hv_tag(pid: PID) -> str:
    numbers = [int(m.group(1)) for v in pid.valves if (m := _TAG_RE.match(v.tag))]
    start = max(numbers, default=_FIRST_TAG - 1) + 1
    return f"HV-{start:04d}"


def _missing_ends(line: PidLine, pid: PID) -> list[bool]:
    """[start end needs a valve, end end needs a valve] for one line."""
    needs: list[bool] = []
    for at_end in (False, True):
        line_end = line.end if at_end else line.start
        if line_end.equipment is None:
            needs.append(False)  # boundary ends get no valve
        else:
            needs.append(_end_missing_valve(line, pid, at_end))
    return needs


@register("pid_rule", RULE_NAME)
class NozzleIsolation:
    """Isolation valve at every process nozzle (spec S-12)."""

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for line in pid.lines:
            start_missing, end_missing = _missing_ends(line, pid)
            if start_missing:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=line.number,
                        message=f"no isolation valve at the start (equipment) end of {line.number}",
                    )
                )
            if end_missing:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=line.number,
                        message=f"no isolation valve at the end (equipment) end of {line.number}",
                    )
                )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for line in fixed.lines:
            for at_end in (False, True):
                # Re-evaluate per end: inserting for one end shifts the other.
                if line.start.equipment is None and not at_end:
                    continue
                if line.end.equipment is None and at_end:
                    continue
                if not _end_missing_valve(line, fixed, at_end):
                    continue
                pc = pipe_classes()[line.pipe_class]
                valve = Valve(
                    tag=_next_hv_tag(fixed),
                    type=ValveType(pc["default_isolation_valve"]),
                    nps_in=line.nps_in,
                    flange_class=int(pc["flange_class"]),
                )
                fixed.valves.append(valve)
                index = _insertion_index(line, fixed, at_end)
                line.items.insert(index, InlineItem(kind=InlineKind.VALVE, ref=valve.tag))
        return fixed
