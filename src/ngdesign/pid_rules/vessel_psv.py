"""S-14: P&ID rule — PSV on every pressure vessel.

Every pressure vessel gets a relief valve set at its design pressure,
discharging to the flare header: the vessel's ``psv`` nozzle receives a
Valve(type=PSV, set_pressure = design pressure) and a new line from that
nozzle to boundary ``FLARE``.  Nozzles are owned by the sizers, so a vessel
without a ``psv`` nozzle is reported by check() and left alone by apply().
"""

from __future__ import annotations

import re

from ngdesign.contracts import (
    PID,
    InlineItem,
    InlineKind,
    LineEnd,
    PidEquipment,
    PidLine,
    RuleViolation,
    Valve,
    ValveType,
)
from ngdesign.data import pipe_classes
from ngdesign.pid_rules._common import psv_nozzle
from ngdesign.registry import register

RULE_NAME = "vessel_psv"
_TAG_RE = re.compile(r"^PSV-(\d{4})$")
_SEQ_RE = re.compile(r'^[^"]*"-[A-Z]{1,3}-(\d{4})-[A-Z]\d$')
_FIRST_TAG = 1001
_PRESSURE_VESSEL_KINDS = frozenset(
    {
        "separator_3phase",
        "scrubber",
        "teg_contactor",
        "amine_contactor",
        "flash_drum",
        "reflux_drum",
        "ko_drum",
    }
)


def _inlet_line(pid: PID, eq: PidEquipment) -> PidLine | None:
    """The vessel's inlet line: a line ending at the vessel, preferring an
    'inlet' service nozzle."""
    ends = [ln for ln in pid.lines if ln.end.equipment == eq.tag]
    for ln in ends:
        noz = next((n for n in eq.nozzles if n.id == ln.end.nozzle), None)
        if noz is not None and noz.service == "inlet":
            return ln
    return ends[0] if ends else None


def _relieved(pid: PID, eq: PidEquipment, nozzle_id: str) -> bool:
    """True if a line from the psv nozzle already carries a PSV valve."""
    for ln in pid.lines:
        if ln.start.equipment != eq.tag or ln.start.nozzle != nozzle_id:
            continue
        for item in ln.items:
            if item.kind != InlineKind.VALVE or item.ref is None:
                continue
            valve = next((v for v in pid.valves if v.tag == item.ref), None)
            if valve is not None and valve.type == ValveType.PSV:
                return True
    return False


def _next_sequence(pid: PID) -> int:
    numbers = [int(m.group(1)) for ln in pid.lines if (m := _SEQ_RE.match(ln.number))]
    return max(numbers, default=1000) + 1


def _next_psv_tag(pid: PID) -> str:
    numbers = [int(m.group(1)) for v in pid.valves if (m := _TAG_RE.match(v.tag))]
    return f"PSV-{max(numbers, default=_FIRST_TAG - 1) + 1:04d}"


def _nps_str(nps_in: float) -> str:
    return f"{nps_in:g}"


@register("pid_rule", RULE_NAME)
class VesselPsv:
    """PSV on every pressure vessel (spec S-14)."""

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for eq in pid.equipment:
            if eq.kind not in _PRESSURE_VESSEL_KINDS:
                continue
            nozzle = psv_nozzle(eq)
            if nozzle is None:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=eq.tag,
                        message=(f"pressure vessel {eq.tag} has no psv nozzle (nozzles are owned by sizers)"),
                    )
                )
            elif not _relieved(pid, eq, nozzle.id):
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=eq.tag,
                        message=f"pressure vessel {eq.tag} has no PSV on its psv nozzle",
                    )
                )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for eq in fixed.equipment:
            if eq.kind not in _PRESSURE_VESSEL_KINDS:
                continue
            nozzle = psv_nozzle(eq)
            if nozzle is None or _relieved(fixed, eq, nozzle.id):
                continue
            inlet = _inlet_line(fixed, eq)
            pipe_class = inlet.pipe_class if inlet is not None else "B1"
            pc = pipe_classes()[pipe_class]
            tag = _next_psv_tag(fixed)
            fixed.valves.append(
                Valve(
                    tag=tag,
                    type=ValveType.PSV,
                    nps_in=nozzle.nps_in,
                    flange_class=int(pc["flange_class"]),
                    set_pressure_Pa=eq.design_pressure_Pa,
                )
            )
            number = f'{_nps_str(nozzle.nps_in)}"-FL-{_next_sequence(fixed):04d}-{pipe_class}'
            fixed.lines.append(
                PidLine(
                    number=number,
                    nps_in=nozzle.nps_in,
                    fluid_code="FL",
                    pipe_class=pipe_class,
                    design_pressure_Pa=(
                        inlet.design_pressure_Pa if inlet is not None else eq.design_pressure_Pa
                    ),
                    design_temperature_K=(
                        inlet.design_temperature_K if inlet is not None else eq.design_temperature_K
                    ),
                    start=LineEnd(equipment=eq.tag, nozzle=nozzle.id),
                    end=LineEnd(boundary="FLARE"),
                    items=[InlineItem(kind=InlineKind.VALVE, ref=tag)],
                )
            )
        return fixed
