"""Hand-built sample objects so downstream layers can be built before upstream ones exist.
Human-owned. Tests and plugins may import these; agents must not edit them.
"""

from __future__ import annotations

from ngdesign.contracts import (
    PID,
    Component,
    ComponentKind,
    Direction,
    EndType,
    LineEnd,
    Nozzle,
    PidEquipment,
    PidLine,
    PipingNetwork,
    RoutedLine,
    Vec3,
)

INCH = 25.4


def _noz(
    i: str,
    service: str,
    port: str | None,
    nps: float,
    cls: int,
    x: float,
    y: float,
    z: float,
    facing: Direction,
) -> Nozzle:
    return Nozzle(
        id=i,
        service=service,
        port=port,
        nps_in=nps,
        flange_class=cls,
        position_mm=Vec3(x=x, y=y, z=z),
        facing=facing,
    )


def sample_pid() -> PID:
    """Bare P&ID of part of the slice: equipment, nozzles and lines only.
    No valves or instruments: the pid_rule plugins insert those.
    """
    v101 = PidEquipment(
        tag="V-101",
        kind="separator_3phase",
        design_pressure_Pa=4.0e6,
        design_temperature_K=338.15,
        nozzles=[
            _noz("N1", "inlet", "inlet", 8, 300, 0, 0, 1500, Direction.W),
            _noz("N2", "gas_out", "gas_out", 8, 300, 5000, 0, 2600, Direction.UP),
            _noz("N3", "hc_out", "hc_out", 2, 300, 3500, 0, 0, Direction.DOWN),
            _noz("N4", "water_out", "water_out", 2, 300, 4500, 0, 0, Direction.DOWN),
            _noz("N5", "psv", None, 3, 300, 2500, 0, 2600, Direction.UP),
            _noz("N6", "drain", None, 2, 300, 1000, 0, 0, Direction.DOWN),
        ],
    )
    p101 = PidEquipment(
        tag="P-101",
        kind="pump",
        design_pressure_Pa=2.0e6,
        design_temperature_K=338.15,
        nozzles=[
            _noz("N1", "suction", "inlet", 3, 300, 0, 0, 500, Direction.W),
            _noz("N2", "discharge", "outlet", 2, 300, 400, 0, 800, Direction.UP),
        ],
    )
    k101 = PidEquipment(
        tag="K-101",
        kind="compressor",
        design_pressure_Pa=7.7e6,
        design_temperature_K=423.15,
        nozzles=[
            _noz("N1", "suction", "inlet", 8, 300, 0, 0, 1200, Direction.UP),
            _noz("N2", "discharge", "outlet", 6, 600, 2000, 0, 1200, Direction.UP),
        ],
    )
    lines = [
        PidLine(
            number='8"-PG-1001-B1',
            stream_id="S-001",
            nps_in=8,
            fluid_code="PG",
            pipe_class="B1",
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            start=LineEnd(boundary="BL-INLET"),
            end=LineEnd(equipment="V-101", nozzle="N1"),
        ),
        PidLine(
            number='8"-PG-1002-B1',
            stream_id="S-002",
            nps_in=8,
            fluid_code="PG",
            pipe_class="B1",
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            start=LineEnd(equipment="V-101", nozzle="N2"),
            end=LineEnd(equipment="K-101", nozzle="N1"),
        ),
        PidLine(
            number='6"-PG-1003-D1',
            stream_id="S-003",
            nps_in=6,
            fluid_code="PG",
            pipe_class="D1",
            design_pressure_Pa=7.7e6,
            design_temperature_K=423.15,
            start=LineEnd(equipment="K-101", nozzle="N2"),
            end=LineEnd(boundary="E-101"),
        ),
        PidLine(
            number='3"-PL-1004-B1',
            stream_id="S-008",
            nps_in=3,
            fluid_code="PL",
            pipe_class="B1",
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            start=LineEnd(equipment="V-101", nozzle="N3"),
            end=LineEnd(equipment="P-101", nozzle="N1"),
        ),
        PidLine(
            number='2"-PL-1005-B1',
            stream_id="S-009",
            nps_in=2,
            fluid_code="PL",
            pipe_class="B1",
            design_pressure_Pa=2.0e6,
            design_temperature_K=338.15,
            start=LineEnd(equipment="P-101", nozzle="N2"),
            end=LineEnd(boundary="E-102"),
        ),
    ]
    return PID(equipment=[v101, p101, k101], lines=lines, valves=[], instruments=[])


def sample_routed_line() -> RoutedLine:
    """6" line: flange at nozzle, 2 m east, LR elbow up, 3 m up, LR elbow north, 1.5 m north, flange.
    Geometry in mm. LR 90 elbow center-to-end = 1.5 * NPS(in) * 25.4.
    """
    nps = 6.0
    a = 1.5 * nps * INCH  # 228.6 mm
    fl = 100.0  # placeholder flange length; the flange-dimension spec replaces this
    common = dict(nps_in=nps, pipe_class="D1", schedule="80")
    c: list[Component] = []
    c.append(
        Component(
            id="C1",
            kind=ComponentKind.FLANGE_WN,
            start=Vec3(x=0, y=0, z=0),
            end=Vec3(x=fl, y=0, z=0),
            end_types=(EndType.FLANGED, EndType.BUTT_WELD),
            description='6" WN flange cl600 RTJ',
            **common,
        )
    )
    c.append(
        Component(
            id="C2",
            kind=ComponentKind.PIPE,
            start=Vec3(x=fl, y=0, z=0),
            end=Vec3(x=2000 - a, y=0, z=0),
            description='6" pipe SCH80',
            **common,
        )
    )
    c.append(
        Component(
            id="C3",
            kind=ComponentKind.ELBOW_90_LR,
            start=Vec3(x=2000 - a, y=0, z=0),
            end=Vec3(x=2000, y=0, z=a),
            center=Vec3(x=2000, y=0, z=0),
            description='6" 90 LR elbow SCH80',
            **common,
        )
    )
    c.append(
        Component(
            id="C4",
            kind=ComponentKind.PIPE,
            start=Vec3(x=2000, y=0, z=a),
            end=Vec3(x=2000, y=0, z=3000 - a),
            description='6" pipe SCH80',
            **common,
        )
    )
    c.append(
        Component(
            id="C5",
            kind=ComponentKind.ELBOW_90_LR,
            start=Vec3(x=2000, y=0, z=3000 - a),
            end=Vec3(x=2000, y=a, z=3000),
            center=Vec3(x=2000, y=0, z=3000),
            description='6" 90 LR elbow SCH80',
            **common,
        )
    )
    c.append(
        Component(
            id="C6",
            kind=ComponentKind.PIPE,
            start=Vec3(x=2000, y=a, z=3000),
            end=Vec3(x=2000, y=1500 - fl, z=3000),
            description='6" pipe SCH80',
            **common,
        )
    )
    c.append(
        Component(
            id="C7",
            kind=ComponentKind.FLANGE_WN,
            start=Vec3(x=2000, y=1500 - fl, z=3000),
            end=Vec3(x=2000, y=1500, z=3000),
            end_types=(EndType.BUTT_WELD, EndType.FLANGED),
            description='6" WN flange cl600 RTJ',
            **common,
        )
    )
    return RoutedLine(line_number='6"-PG-1003-D1', components=c)


def sample_network() -> PipingNetwork:
    return PipingNetwork(lines=[sample_routed_line()])
