"""S-17: P&ID rule — drains at low points, vents at high points.

Every line with at least one equipment end carries a DRAIN at its low end and
a VENT at its high end.  End elevations come from the nozzle position_mm.z (a
boundary end counts as elevation 0).  check() tests presence only, so other
rules may insert items around the drain and vent; apply() inserts them at the
ends and is idempotent.  Hydrocarbon services get double block and bleed
tappings ("3/4in DBB"), everything else plain "3/4in".
"""

from __future__ import annotations

from ngdesign.contracts import PID, InlineItem, InlineKind, LineEnd, RuleViolation
from ngdesign.registry import register

RULE_NAME = "drains_vents"
_DBB_FLUID_CODES = frozenset({"PG", "PL", "NG", "FL"})
_BOUNDARY_ELEVATION = 0.0


def _end_elevation(pid: PID, end: LineEnd) -> float:
    if end.equipment is None:  # boundary end
        return _BOUNDARY_ELEVATION
    eq = next((e for e in pid.equipment if e.tag == end.equipment), None)
    if eq is None or end.nozzle is None:
        return _BOUNDARY_ELEVATION
    nozzle = next((n for n in eq.nozzles if n.id == end.nozzle), None)
    return nozzle.position_mm.z if nozzle is not None else _BOUNDARY_ELEVATION


def _note(fluid_code: str) -> str:
    return "3/4in DBB" if fluid_code in _DBB_FLUID_CODES else "3/4in"


@register("pid_rule", RULE_NAME)
class DrainsVents:
    """Drains at low points, vents at high points (spec S-17)."""

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for line in pid.lines:
            if line.start.equipment is None and line.end.equipment is None:
                continue
            kinds = [it.kind for it in line.items]
            if InlineKind.DRAIN not in kinds:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=line.number,
                        message=f"line {line.number} has no drain at its low point",
                    )
                )
            if InlineKind.VENT not in kinds:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=line.number,
                        message=f"line {line.number} has no vent at its high point",
                    )
                )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for line in fixed.lines:
            if line.start.equipment is None and line.end.equipment is None:
                continue
            kinds = [it.kind for it in line.items]
            start_z = _end_elevation(fixed, line.start)
            end_z = _end_elevation(fixed, line.end)
            note = _note(line.fluid_code)
            # Drain at the low end: index 0 if the start is lower, else appended.
            if InlineKind.DRAIN not in kinds:
                drain = InlineItem(kind=InlineKind.DRAIN, note=note)
                if start_z < end_z:
                    line.items.insert(0, drain)
                else:
                    line.items.append(drain)
            # Vent at the high end: index 0 if the start is higher, else
            # appended (equal elevations: drain at start, vent at end).
            if InlineKind.VENT not in kinds:
                vent = InlineItem(kind=InlineKind.VENT, note=note)
                if start_z > end_z:
                    line.items.insert(0, vent)
                else:
                    line.items.append(vent)
        return fixed
