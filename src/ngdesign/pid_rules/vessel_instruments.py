"""S-15: P&ID rule — vessel instrumentation.

Every separator gets level instrumentation (LT, LG, LSHH, LSLL); three-phase
separators additionally get a LIT on the interface.  Every pressure vessel
gets a PT.  One loop number per measured variable per vessel, allocated
sequentially from 1001 above the max existing loop; tags are ISA S5.1
``<FUNC>-<loop>`` with connected_to = vessel tag.
"""

from __future__ import annotations

from ngdesign.contracts import PID, Instrument, PidEquipment, RuleViolation
from ngdesign.registry import register

RULE_NAME = "vessel_instruments"
_FIRST_LOOP = 1001

_LEVEL_FUNCS = frozenset({"LT", "LG", "LSHH", "LSLL"})
_INTERFACE_FUNCS = frozenset({"LIT"})
_PRESSURE_FUNCS = frozenset({"PT"})

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
_SEPARATOR_MARKER = ("separator", "scrubber", "drum")


def _is_separator(eq: PidEquipment) -> bool:
    return any(marker in eq.kind for marker in _SEPARATOR_MARKER)


def _variables(eq: PidEquipment) -> list[frozenset[str]]:
    """Measured variables (as function sets) expected on this vessel, in
    deterministic allocation order."""
    variables: list[frozenset[str]] = []
    if _is_separator(eq):
        variables.append(_LEVEL_FUNCS)
        if eq.kind == "separator_3phase":
            variables.append(_INTERFACE_FUNCS)
    if eq.kind in _PRESSURE_VESSEL_KINDS:
        variables.append(_PRESSURE_FUNCS)
    return variables


def _next_loop(instruments: list[Instrument]) -> int:
    return max((i.loop for i in instruments), default=_FIRST_LOOP - 1) + 1


def _of_vessel(instruments: list[Instrument], eq: PidEquipment) -> list[Instrument]:
    return [i for i in instruments if i.connected_to == eq.tag]


@register("pid_rule", RULE_NAME)
class VesselInstruments:
    """Vessel instrumentation (spec S-15)."""

    def check(self, pid: PID) -> list[RuleViolation]:
        violations: list[RuleViolation] = []
        for eq in pid.equipment:
            mine = _of_vessel(pid.instruments, eq)
            for funcs in _variables(eq):
                for function in sorted(funcs - {i.function for i in mine}):
                    violations.append(
                        RuleViolation(
                            rule=RULE_NAME,
                            target=eq.tag,
                            message=f"vessel {eq.tag} is missing a {function} instrument",
                        )
                    )
        return violations

    def apply(self, pid: PID) -> PID:
        fixed = pid.model_copy(deep=True)
        for eq in fixed.equipment:
            for funcs in _variables(eq):
                mine = [i for i in _of_vessel(fixed.instruments, eq) if i.function in funcs]
                # One loop per measured variable: reuse an existing loop when
                # some of the variable's instruments are already present.
                loop = mine[0].loop if mine else _next_loop(fixed.instruments)
                for function in sorted(funcs):
                    if any(i.function == function for i in mine):
                        continue
                    fixed.instruments.append(
                        Instrument(
                            tag=f"{function}-{loop}",
                            function=function,
                            loop=loop,
                            connected_to=eq.tag,
                        )
                    )
        return fixed
