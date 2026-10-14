"""Tests for the S-21 orthogonal pipe router (kind router, name orthogonal)."""

from __future__ import annotations

import math
import sys
import types

import pytest

from ngdesign import registry
from ngdesign.contracts import (
    PID,
    ComponentKind,
    Direction,
    EndType,
    EquipmentEnvelope,
    LineEnd,
    Nozzle,
    PidEquipment,
    PidLine,
    RoutedLine,
    Vec3,
)
from ngdesign.flowsheets.samples import sample_pid
from ngdesign.piping.fittings import elbow_90_lr_cte_mm
from ngdesign.piping.router_orthogonal import (
    BOUNDARY_SETBACK_MM,
    DEFAULT_ENVELOPE_HALF_MM,
    DEFAULT_EQUIPMENT_SPACING_MM,
    DEFAULT_RACK_ELEVATION_MM,
    segment_hits_envelope,
)

RACK = DEFAULT_RACK_ELEVATION_MM


def _close(p: Vec3, x: float, y: float, z: float) -> None:
    assert (p.x, p.y, p.z) == pytest.approx((x, y, z), abs=1e-6)


@pytest.fixture(name="network")
def _network():
    router = registry.create("router", "orthogonal")
    return router.route(sample_pid(), {})


def _foreign_envelopes(line: PidLine, envelopes: list[EquipmentEnvelope]) -> list[EquipmentEnvelope]:
    """Envelopes of equipment the line does not connect to."""
    own = {line.start.equipment, line.end.equipment}
    return [e for e in envelopes if e.tag not in own]


def _assert_clash_free(pid: PID, network) -> None:
    for pl in pid.lines:
        routed = next(rl for rl in network.lines if rl.line_number == pl.number)
        for c in routed.components:
            if c.kind != ComponentKind.PIPE:
                continue
            for env in _foreign_envelopes(pl, network.equipment):
                assert not segment_hits_envelope(c.start, c.end, env), f"{c.id} hits {env.tag}"


def test_router_registered() -> None:
    assert registry.available("router") == ["orthogonal"]


def test_sample_routes_every_line(network) -> None:
    assert [rl.line_number for rl in network.lines] == [pl.number for pl in sample_pid().lines]
    for rl in network.lines:
        assert isinstance(rl, RoutedLine)
        assert len(rl.components) >= 2


def test_network_defaults(network) -> None:
    assert network.rack_elevation_mm == RACK
    assert [e.tag for e in network.equipment] == ["V-101", "P-101", "K-101"]
    v101 = network.equipment[0]
    h = DEFAULT_ENVELOPE_HALF_MM
    _close(v101.min, DEFAULT_EQUIPMENT_SPACING_MM - h, -h, -h)
    _close(v101.max, DEFAULT_EQUIPMENT_SPACING_MM + h, h, h)


def test_boundaries_beyond_extreme_equipment_at_grade(network) -> None:
    first = network.lines[0].components[0]
    last = network.lines[2].components[-1]
    _close(first.start, DEFAULT_EQUIPMENT_SPACING_MM - BOUNDARY_SETBACK_MM, 0.0, 0.0)
    _close(last.end, 3 * DEFAULT_EQUIPMENT_SPACING_MM + BOUNDARY_SETBACK_MM, 0.0, 0.0)


def test_line1_chain_components_and_geometry(network) -> None:
    """Boundary-to-nozzle line: 4 legs, 3 elbows, end flange at the nozzle."""
    comps = network.lines[0].components
    assert [c.kind for c in comps] == [
        ComponentKind.PIPE,
        ComponentKind.ELBOW_90_LR,
        ComponentKind.PIPE,
        ComponentKind.ELBOW_90_LR,
        ComponentKind.PIPE,
        ComponentKind.ELBOW_90_LR,
        ComponentKind.PIPE,
        ComponentKind.FLANGE_WN,
    ]
    assert [c.id for c in comps] == [f"C{i}" for i in range(1, 9)]
    _close(comps[0].start, 9000.0, 0.0, 0.0)
    _close(comps[-1].end, 12000.0, 0.0, 1500.0)  # V-101/N1 world point
    assert comps[-1].end_types == (EndType.BUTT_WELD, EndType.FLANGED)


def test_elbows_orthogonal_with_correct_centre_to_end(network) -> None:
    for rl, pl in zip(network.lines, sample_pid().lines, strict=False):
        cte = elbow_90_lr_cte_mm(pl.nps_in)
        elbows = [c for c in rl.components if c.kind == ComponentKind.ELBOW_90_LR]
        assert elbows, pl.number
        for e in elbows:
            assert e.center is not None
            d_in = (e.start.x - e.center.x, e.start.y - e.center.y, e.start.z - e.center.z)
            d_out = (e.end.x - e.center.x, e.end.y - e.center.y, e.end.z - e.center.z)
            assert math.sqrt(sum(c * c for c in d_in)) == pytest.approx(cte, rel=1e-9)
            assert math.sqrt(sum(c * c for c in d_out)) == pytest.approx(cte, rel=1e-9)
            dot = sum(i * o for i, o in zip(d_in, d_out, strict=True))
            assert abs(dot) < 1e-9, f"{pl.number} {e.id} is not a 90 deg change"


def test_no_pipe_through_foreign_envelope(network) -> None:
    _assert_clash_free(sample_pid(), network)


def test_flanges_only_at_nozzle_ends(network) -> None:
    origins = {
        "V-101": Vec3(x=12000, y=0, z=0),
        "P-101": Vec3(x=24000, y=0, z=0),
        "K-101": Vec3(x=36000, y=0, z=0),
    }
    for rl, pl in zip(network.lines, sample_pid().lines, strict=False):
        assert (rl.components[0].kind == ComponentKind.FLANGE_WN) == (pl.start.equipment is not None), (
            pl.number
        )
        assert (rl.components[-1].kind == ComponentKind.FLANGE_WN) == (pl.end.equipment is not None), (
            pl.number
        )
        if pl.start.equipment:
            noz = next(
                n
                for e in sample_pid().equipment
                if e.tag == pl.start.equipment
                for n in e.nozzles
                if n.id == pl.start.nozzle
            )
            o = origins[pl.start.equipment]
            _close(
                rl.components[0].start,
                o.x + noz.position_mm.x,
                o.y + noz.position_mm.y,
                o.z + noz.position_mm.z,
            )
            assert rl.components[0].end_types[0] == EndType.FLANGED


def test_schedule_matches_b313_module() -> None:
    """S-02 is merged: every component carries the module's own schedule."""
    from ngdesign.sizing.wall_thickness import select_schedule

    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {})
    for pl, rl in zip(sample_pid().lines, network.lines, strict=False):
        expected = select_schedule(pl.nps_in, pl.design_pressure_Pa - 101325.0, pl.pipe_class)[
            "selected_schedule"
        ]
        for c in rl.components:
            assert c.schedule == expected, f"{rl.line_number} {c.id}"


def test_schedule_fallback_40_when_module_absent(monkeypatch) -> None:
    """None in sys.modules makes the lazy import fail -> fallback "40"."""
    monkeypatch.setitem(sys.modules, "ngdesign.sizing.wall_thickness", None)
    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {})
    for rl in network.lines:
        for c in rl.components:
            assert c.schedule == "40", f"{rl.line_number} {c.id}"


def test_schedule_from_sizing_module_when_present(monkeypatch) -> None:
    calls: list[tuple[float, float, str]] = []

    def fake_select_schedule(
        nps_in: float, design_gauge_Pa: float, pipe_class: str
    ) -> dict[str, float | str]:
        calls.append((nps_in, design_gauge_Pa, pipe_class))
        return {
            "od_mm": 0.0,
            "t_pressure_mm": 0.0,
            "t_required_nominal_mm": 0.0,
            "selected_wall_mm": 0.0,
            "selected_schedule": "80",
        }

    fake = types.ModuleType("ngdesign.sizing.wall_thickness")
    fake.select_schedule = fake_select_schedule
    monkeypatch.setitem(sys.modules, "ngdesign.sizing.wall_thickness", fake)

    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {})
    for rl in network.lines:
        for c in rl.components:
            assert c.schedule == "80", f"{rl.line_number} {c.id}"
    assert calls[0] == (8.0, 4.0e6 - 101325.0, "B1")  # gauge pressure, not absolute


def test_rack_override() -> None:
    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {"rack_elevation_mm": 4500.0})
    assert network.rack_elevation_mm == 4500.0
    for rl in network.lines:
        zs = [v for c in rl.components for v in (c.start.z, c.end.z, c.center.z if c.center else c.start.z)]
        assert max(zs) == pytest.approx(4500.0, abs=1e-6), rl.line_number


def test_relocated_equipment_produces_y_run() -> None:
    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {"K-101": Vec3(x=36000, y=8000, z=0)})
    k_env = next(e for e in network.equipment if e.tag == "K-101")
    _close(k_env.min, 35000.0, 7000.0, -1000.0)
    _close(k_env.max, 37000.0, 9000.0, 1000.0)
    line2 = next(rl for rl in network.lines if rl.line_number == '8"-PG-1002-B1')
    y_runs = [
        c
        for c in line2.components
        if c.kind == ComponentKind.PIPE
        and abs(c.end.y - c.start.y) > 1.0
        and abs(c.end.x - c.start.x) < 1e-6
        and abs(c.end.z - c.start.z) < 1e-6
    ]
    assert y_runs, "relocation off the x axis must produce a rack y-run"
    _assert_clash_free(sample_pid(), network)


def test_provided_envelope_replaces_default() -> None:
    env = EquipmentEnvelope(tag="V-101", min=Vec3(x=11000, y=-1000, z=-500), max=Vec3(x=13000, y=1000, z=500))
    router = registry.create("router", "orthogonal")
    network = router.route(sample_pid(), {"V-101": env})
    assert network.equipment[0] == env
    assert len(network.lines) == 5
    _assert_clash_free(sample_pid(), network)


def test_unknown_layout_key_raises() -> None:
    router = registry.create("router", "orthogonal")
    with pytest.raises(ValueError, match="V-1012"):
        router.route(sample_pid(), {"V-1012": Vec3(x=0, y=0, z=0)})


def test_segment_hits_envelope_cases() -> None:
    env = EquipmentEnvelope(tag="X", min=Vec3(x=0, y=0, z=0), max=Vec3(x=10, y=10, z=10))
    v = Vec3
    assert segment_hits_envelope(v(x=-5, y=5, z=5), v(x=15, y=5, z=5), env)  # through
    assert not segment_hits_envelope(v(x=-5, y=5, z=15), v(x=15, y=5, z=15), env)  # above
    assert segment_hits_envelope(v(x=-5, y=-5, z=-5), v(x=15, y=15, z=15), env)  # diagonal
    assert segment_hits_envelope(v(x=5, y=5, z=5), v(x=5, y=5, z=5), env)  # point inside
    assert not segment_hits_envelope(v(x=12, y=12, z=12), v(x=20, y=12, z=12), env)  # outside


def _nozzle(facing: Direction) -> Nozzle:
    return Nozzle(
        id="N1",
        service="process",
        port=None,
        nps_in=8,
        flange_class=300,
        position_mm=Vec3(x=0, y=0, z=500),
        facing=facing,
    )


def _synthetic_pid() -> PID:
    """Source A and sink B 8 m apart, plus cooler C whose tall envelope blocks A's drop."""
    a = PidEquipment(
        tag="A-100",
        kind="separator_3phase",
        design_pressure_Pa=4.0e6,
        design_temperature_K=338.15,
        nozzles=[_nozzle(Direction.E)],
    )
    b = PidEquipment(
        tag="B-100",
        kind="pump",
        design_pressure_Pa=4.0e6,
        design_temperature_K=338.15,
        nozzles=[_nozzle(Direction.W)],
    )
    c = PidEquipment(
        tag="C-103", kind="cooler", design_pressure_Pa=4.0e6, design_temperature_K=338.15, nozzles=[]
    )
    line = PidLine(
        number='8"-PG-2001-B1',
        stream_id="S-901",
        nps_in=8,
        fluid_code="PG",
        pipe_class="B1",
        design_pressure_Pa=4.0e6,
        design_temperature_K=338.15,
        start=LineEnd(equipment="A-100", nozzle="N1"),
        end=LineEnd(equipment="B-100", nozzle="N1"),
    )
    return PID(equipment=[a, b, c], lines=[line], valves=[], instruments=[])


def _c_envelope(x_min: float, x_max: float, z_min: float = 1500.0) -> EquipmentEnvelope:
    """Obstacle box over x [x_min, x_max]. Default z 1500-4000 blocks rack
    drops but not the horizontal nozzle approaches at z = 500; a lower floor
    (z_min=-1000) also blocks the approaches, making the line unroutable."""
    return EquipmentEnvelope(
        tag="C-103", min=Vec3(x=x_min, y=-1000, z=z_min), max=Vec3(x=x_max, y=1000, z=4000)
    )


def test_nozzle_leg_extends_to_clear_foreign_envelope() -> None:
    """A's rack drop lands inside C's tall envelope at the minimum leg; the leg
    extends until the drop clears it."""
    pid = _synthetic_pid()
    router = registry.create("router", "orthogonal")
    layout = {
        "A-100": Vec3(x=0, y=0, z=0),
        "B-100": Vec3(x=8000, y=0, z=0),
        "C-103": _c_envelope(400.0, 1000.0),
    }
    network = router.route(pid, layout)
    line = network.lines[0]
    flange, first_pipe = line.components[0], line.components[1]
    assert flange.kind == ComponentKind.FLANGE_WN and first_pipe.kind == ComponentKind.PIPE
    # the minimum leg (504.8) puts the drop corner inside C's envelope
    # ([400,1000] x-range); exactly one +1000 mm extension clears it: the
    # corner lands at 1504.8, past C's face at 1000, so the first pipe ends
    # one elbow centre-to-end short of the corner: 1504.8 - 304.8 = 1200
    assert first_pipe.end.x == pytest.approx(1200.0), f"leg did not extend as expected: {first_pipe.end.x}"
    _assert_clash_free(pid, network)


def test_unroutable_envelope_clash_raises() -> None:
    """C's envelope spans the whole yard strip: no leg length can clear the drops."""
    pid = _synthetic_pid()
    router = registry.create("router", "orthogonal")
    layout = {
        "A-100": Vec3(x=0, y=0, z=0),
        "B-100": Vec3(x=8000, y=0, z=0),
        "C-103": _c_envelope(-500.0, 10000.0, z_min=-1000.0),
    }
    with pytest.raises(ValueError, match="C-103"):
        router.route(pid, layout)


def test_iso_renderer_accepts_routed_network(network) -> None:
    if "svg" not in registry.available("iso_renderer"):
        pytest.skip("no iso_renderer registered")
    renderer = registry.create("iso_renderer", "svg")
    pid = sample_pid()
    for pl, rl in zip(pid.lines, network.lines, strict=False):
        sheet = renderer.render(rl, pid)
        pipe_mm = sum(
            math.sqrt((c.end.x - c.start.x) ** 2 + (c.end.y - c.start.y) ** 2 + (c.end.z - c.start.z) ** 2)
            for c in rl.components
            if c.kind == ComponentKind.PIPE
        )
        assert sheet.total_pipe_length_mm == pytest.approx(pipe_mm, rel=1e-9)
        assert sheet.weld_count == len(rl.components) - 1, pl.number  # all-butt joints
