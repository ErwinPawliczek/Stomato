"""Tests for the S-15 vessel_instruments rule."""

from __future__ import annotations

from ngdesign import registry
from ngdesign.contracts import Direction, Nozzle, PidEquipment, Vec3
from ngdesign.contracts.pid import INSTR_TAG_RE
from ngdesign.flowsheets.samples import sample_pid

RULE = "vessel_instruments"


def _rule() -> object:
    return registry.create("pid_rule", RULE)


def test_finds_violations_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    # V-101: LT, LG, LSHH, LSLL (level), LIT (interface), PT (pressure).
    assert len(violations) == 6
    assert {v.target for v in violations} == {"V-101"}
    assert all(v.rule == RULE for v in violations)


def test_apply_then_check_clean_and_idempotent() -> None:
    pid = sample_pid()
    fixed = _rule().apply(pid)
    assert _rule().check(fixed) == []
    assert _rule().apply(fixed).model_dump() == fixed.model_dump()


def test_tags_match_isa_and_loops_unique_per_variable() -> None:
    fixed = _rule().apply(sample_pid())
    instruments = [i for i in fixed.instruments if i.connected_to == "V-101"]
    by_func = {i.function: i for i in instruments}
    assert set(by_func) == {"LT", "LG", "LSHH", "LSLL", "LIT", "PT"}
    for inst in instruments:
        assert INSTR_TAG_RE.match(inst.tag)
        assert inst.tag == f"{inst.function}-{inst.loop}"
    level_loop = by_func["LT"].loop
    assert by_func["LG"].loop == by_func["LSHH"].loop == by_func["LSLL"].loop == level_loop
    assert len({by_func[f].loop for f in ("LT", "LIT", "PT")}) == 3  # one loop per variable


def test_loops_allocated_above_max_existing() -> None:
    from ngdesign.contracts import Instrument

    pid = sample_pid()
    pid.instruments.append(Instrument(tag="FT-1050", function="FT", loop=1050, connected_to='8"-PG-1001-B1'))
    fixed = _rule().apply(pid)
    loops = sorted(i.loop for i in fixed.instruments if i.connected_to == "V-101")
    assert loops[0] == 1051


def test_scrubber_gets_level_set_but_no_interface() -> None:

    pid = sample_pid()
    pid.equipment.append(
        PidEquipment(
            tag="V-200",
            kind="scrubber",
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            nozzles=[
                Nozzle(
                    id="N1",
                    service="inlet",
                    port=None,
                    nps_in=4,
                    flange_class=300,
                    position_mm=Vec3(x=0, y=0, z=1000),
                    facing=Direction.W,
                )
            ],
        )
    )
    fixed = _rule().apply(pid)
    funcs = {i.function for i in fixed.instruments if i.connected_to == "V-200"}
    assert funcs == {"LT", "LG", "LSHH", "LSLL", "PT"}
    assert _rule().check(fixed) == []


def test_non_vessel_equipment_ignored() -> None:
    fixed = _rule().apply(sample_pid())
    assert not [i for i in fixed.instruments if i.connected_to in ("P-101", "K-101")]
