"""S-13: P&ID rule — check valve on pump and compressor discharge.

Every line starting at a pump or compressor discharge nozzle carries a check
valve to prevent reverse flow.  Walking the line from the discharge end, the
check valve must come before the first isolation (non-check) valve; apply()
inserts it directly before that valve, or at the start of the line when no
isolation valve exists.
"""

from __future__ import annotations

import re

from ngdesign.contracts import (
    PID,
    InlineItem,
    InlineKind,
    PidEquipment,
    PidLine,
    RuleViolation,
    Valve,
    ValveType,
)
from ngdesign.data import pipe_classes
from ngdesign.registry import register

RULE_NAME = "discharge_check_valve"
_TAG_RE = re.compile(r"^CV-(\d{4})$")
_FIRST_TAG = 1001
_CHECK_KINDS = ("pump", "compressor")
_DUAL_PLATE_MIN_NPS = 3.0


def _check_type_for(nps_in: float) -> ValveType:
    if nps_in >= _DUAL_PLATE_MIN_NPS:
        return ValveType.CHECK_DUAL_PLATE
    return ValveType.CHECK_SWING


def _is_check_type(valve_type: ValveType) -> bool:
    return valve_type in (
        ValveType.CHECK_SWING,
        ValveType.CHECK_PISTON,
        ValveType.CHECK_DUAL_PLATE,
    )


def _valve_for(item: InlineItem, pid: PID) -> Valve | None:
    if item.kind != InlineKind.VALVE or item.ref is None:
        return None
    return next((v for v in pid.valves if v.tag == item.ref), None)


def _has_check_before_first_isolation(line: PidLine, pid: PID) -> bool:
    """Walk from the discharge end (index 0): a correct check valve must sit
    before the first non-check valve (or anywhere if there is none)."""
    required = _check_type_for(line.nps_in)
    seen_check = False
    for item in line.items:
        valve = _valve_for(item, pid)
        if valve is None:
            continue
        if _is_check_type(valve.type):
            if valve.type == required:
                seen_check = True
            continue
        return seen_check  # first non-check valve reached
    return seen_check


def _discharge_line(pid: PID, eq: PidEquipment) -> PidLine | None:
    nozzle = next((n for n in eq.nozzles if n.service == "discharge"), None)
    if nozzle is None:
        return None
    return next(
        (ln for ln in pid.lines if ln.start.equipment == eq.tag and ln.start.nozzle == nozzle.id),
        None,
    )


def _next_cv_tag(pid: PID) -> str:
    numbers = [int(m.group(1)) for v in pid.valves if (m := _TAG_RE.match(v.tag))]
    return f"CV-{max(numbers, default=_FIRST_TAG - 1) + 1:04d}"


@register("pid_rule", RULE_NAME)
class DischargeCheckValve:
    """Check valve on pump and compressor discharge (spec S-13)."""

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for eq in pid.equipment:
            if eq.kind not in _CHECK_KINDS:
                continue
            line = _discharge_line(pid, eq)
            if line is not None and not _has_check_before_first_isolation(line, pid):
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=line.number,
                        message=f"no check valve on {eq.kind} {eq.tag} discharge line {line.number}",
                    )
                )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for eq in fixed.equipment:
            if eq.kind not in _CHECK_KINDS:
                continue
            line = _discharge_line(fixed, eq)
            if line is None or _has_check_before_first_isolation(line, fixed):
                continue
            pc = pipe_classes()[line.pipe_class]
            valve = Valve(
                tag=_next_cv_tag(fixed),
                type=_check_type_for(line.nps_in),
                nps_in=line.nps_in,
                flange_class=int(pc["flange_class"]),
            )
            fixed.valves.append(valve)
            # Insert directly before the first non-check valve, else at the start.
            index = len(line.items)
            for i, item in enumerate(line.items):
                v = _valve_for(item, fixed)
                if v is not None and not _is_check_type(v.type):
                    index = i
                    break
            line.items.insert(index, InlineItem(kind=InlineKind.VALVE, ref=valve.tag))
        return fixed
