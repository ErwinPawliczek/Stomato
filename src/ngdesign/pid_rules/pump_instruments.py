"""S-16: P&ID rule — pump instrumentation.

Every pump gets a PI on its suction line and one on its discharge line
(connected_to = line number) plus an INSTRUMENT_TAP inline item referencing
each PI tag on those lines.  Same loop allocation scheme as S-15: scan the
existing instruments for the max loop and allocate sequentially from 1001
above it.
"""

from __future__ import annotations

from ngdesign.contracts import PID, InlineItem, InlineKind, Instrument, PidEquipment, PidLine, RuleViolation
from ngdesign.registry import register

RULE_NAME = "pump_instruments"
_FIRST_LOOP = 1001


def _nozzle_of_service(eq: PidEquipment, service: str) -> str | None:
    return next((n.id for n in eq.nozzles if n.service == service), None)


def _line_ending_at(pid: PID, tag: str, nozzle_id: str | None) -> str | None:
    if nozzle_id is None:
        return None
    return next(
        (ln.number for ln in pid.lines if ln.end.equipment == tag and ln.end.nozzle == nozzle_id),
        None,
    )


def _line_starting_at(pid: PID, tag: str, nozzle_id: str | None) -> str | None:
    if nozzle_id is None:
        return None
    return next(
        (ln.number for ln in pid.lines if ln.start.equipment == tag and ln.start.nozzle == nozzle_id),
        None,
    )


def _next_loop(instruments: list[Instrument]) -> int:
    return max((i.loop for i in instruments), default=_FIRST_LOOP - 1) + 1


def _line_of(pid: PID, number: str) -> PidLine:
    return next(ln for ln in pid.lines if ln.number == number)


@register("pid_rule", RULE_NAME)
class PumpInstruments:
    """Pump instrumentation (spec S-16)."""

    def _suction_discharge(self, pid: PID, eq: PidEquipment) -> list[tuple[str, bool]]:
        """[(line number, is_discharge)] for one pump, in allocation order."""
        result: list[tuple[str, bool]] = []
        suction = _line_ending_at(pid, eq.tag, _nozzle_of_service(eq, "suction"))
        if suction is not None:
            result.append((suction, False))
        discharge = _line_starting_at(pid, eq.tag, _nozzle_of_service(eq, "discharge"))
        if discharge is not None:
            result.append((discharge, True))
        return result

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for eq in pid.equipment:
            if eq.kind != "pump":
                continue
            for number, _ in self._suction_discharge(pid, eq):
                pi = next(
                    (i for i in pid.instruments if i.function == "PI" and i.connected_to == number),
                    None,
                )
                if pi is None:
                    violations.append(
                        RuleViolation(
                            rule=RULE_NAME,
                            target=number,
                            message=f"pump {eq.tag} line {number} has no pressure indicator",
                        )
                    )
                    continue
                line = _line_of(pid, number)
                if not any(it.kind == InlineKind.INSTRUMENT_TAP and it.ref == pi.tag for it in line.items):
                    violations.append(
                        RuleViolation(
                            rule=RULE_NAME,
                            target=number,
                            message=f"line {number} has no instrument tap for {pi.tag}",
                        )
                    )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for eq in fixed.equipment:
            if eq.kind != "pump":
                continue
            for number, is_discharge in self._suction_discharge(fixed, eq):
                pi = next(
                    (i for i in fixed.instruments if i.function == "PI" and i.connected_to == number),
                    None,
                )
                if pi is None:
                    loop = _next_loop(fixed.instruments)
                    pi = Instrument(
                        tag=f"PI-{loop}",
                        function="PI",
                        loop=loop,
                        connected_to=number,
                    )
                    fixed.instruments.append(pi)
                line = _line_of(fixed, number)
                if any(it.kind == InlineKind.INSTRUMENT_TAP and it.ref == pi.tag for it in line.items):
                    continue
                # Tap sits next to the pump: end of the suction line, start of
                # the discharge line.  Taps are inert to the other rules.
                line.items.insert(
                    len(line.items) if not is_discharge else 0,
                    InlineItem(kind=InlineKind.INSTRUMENT_TAP, ref=pi.tag),
                )
        return fixed
