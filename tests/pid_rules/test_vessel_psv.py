"""Tests for the S-14 vessel_psv rule."""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import (
    Direction,
    InlineItem,
    InlineKind,
    LineEnd,
    Nozzle,
    PidEquipment,
    PidLine,
    Valve,
    ValveType,
    Vec3,
)
from ngdesign.contracts.pid import LINE_NO_RE
from ngdesign.flowsheets.samples import sample_pid

RULE = "vessel_psv"


def _rule() -> object:
    return registry.create("pid_rule", RULE)


def _line(pid: object, number: str) -> object:
    return next(ln for ln in pid.lines if ln.number == number)  # type: ignore[attr-defined]


def test_finds_violation_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    assert len(violations) == 1
    assert violations[0].rule == RULE
    assert violations[0].target == "V-101"


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    assert _rule().apply(fixed).model_dump() == fixed.model_dump()


def test_set_pressure_equals_design_pressure() -> None:
    fixed = _rule().apply(sample_pid())
    psv = next(v for v in fixed.valves if v.tag.startswith("PSV-"))
    assert psv.set_pressure_Pa == 4.0e6  # V-101 design pressure
    assert psv.nps_in == 3  # N5 nozzle NPS
    assert psv.flange_class == 300  # B1 (inlet line pipe class) flange class


def test_relief_line_number_and_routing() -> None:
    fixed = _rule().apply(sample_pid())
    flare = [ln for ln in fixed.lines if ln.end.boundary == "FLARE"]
    assert len(flare) == 1
    line = flare[0]
    assert LINE_NO_RE.match(line.number)
    assert line.number == '3"-FL-1006-B1'  # sequence above max existing (1005)
    assert line.fluid_code == "FL"
    assert line.pipe_class == "B1"  # the vessel inlet line's pipe class
    assert line.start == LineEnd(equipment="V-101", nozzle="N5")
    # The PSV valve sits on its own relief line.
    assert any(it.ref == "PSV-1001" for it in line.items)


def test_vessel_without_psv_nozzle_is_reported_and_left() -> None:
    pid = sample_pid()
    pid.equipment.append(
        PidEquipment(
            tag="V-900",
            kind="ko_drum",
            design_pressure_Pa=1.0e6,
            design_temperature_K=323.15,
            nozzles=[
                Nozzle(
                    id="N1",
                    service="inlet",
                    port=None,
                    nps_in=4,
                    flange_class=150,
                    position_mm=Vec3(x=0, y=0, z=1000),
                    facing=Direction.W,
                )
            ],
        )
    )
    violations = _rule().check(pid)
    assert [v.target for v in violations] == ["V-101", "V-900"]
    fixed = _rule().apply(pid)
    # V-101 got its PSV; V-900 was left alone (no psv nozzle to relieve).
    assert len([v for v in fixed.valves if v.tag.startswith("PSV-")]) == 1
    assert not [ln for ln in fixed.lines if ln.start.equipment == "V-900"]


def test_existing_psv_is_not_duplicated() -> None:
    pid = sample_pid()
    pid.valves.append(
        Valve(tag="PSV-2000", type=ValveType.PSV, nps_in=3, flange_class=300, set_pressure_Pa=4.0e6)
    )
    pid.lines.append(
        PidLine(
            number='3"-FL-1006-B1',
            nps_in=3,
            fluid_code="FL",
            pipe_class="B1",
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            start=LineEnd(equipment="V-101", nozzle="N5"),
            end=LineEnd(boundary="FLARE"),
            items=[InlineItem(kind=InlineKind.VALVE, ref="PSV-2000")],
        )
    )
    assert _rule().check(pid) == []
    fixed = _rule().apply(pid)
    assert fixed.model_dump() == pid.model_dump()
