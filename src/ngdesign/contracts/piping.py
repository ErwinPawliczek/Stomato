"""3D piping model: routed lines as ordered components. Geometry in mm. LOCKED."""

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import model_validator

from .common import Model, Vec3

CONNECT_TOL_MM = 0.5


class ComponentKind(StrEnum):
    PIPE = "pipe"
    ELBOW_90_LR = "elbow_90_lr"
    ELBOW_90_SR = "elbow_90_sr"
    ELBOW_45_LR = "elbow_45_lr"
    TEE_EQUAL = "tee_equal"
    TEE_REDUCING = "tee_reducing"
    REDUCER_CONC = "reducer_concentric"
    REDUCER_ECC = "reducer_eccentric"
    CAP = "cap"
    FLANGE_WN = "flange_weld_neck"
    FLANGE_BLIND = "flange_blind"
    GASKET = "gasket"
    VALVE = "valve"
    OLET = "olet"
    STRAINER = "strainer"


class EndType(StrEnum):
    BUTT_WELD = "bw"
    SOCKET_WELD = "sw"
    FLANGED = "fl"
    THREADED = "thd"


class Component(Model):
    """One physical item. start->end is the centerline in flow direction.

    For elbows, `center` is the intersection point of the two legs.
    For tees, `branch_end` is the branch connection point.
    """

    id: str
    kind: ComponentKind
    nps_in: float
    nps_out: float | None = None  # reducers, reducing tees
    pipe_class: str
    schedule: str | None = None
    start: Vec3
    end: Vec3
    center: Vec3 | None = None
    branch_end: Vec3 | None = None
    end_types: tuple[EndType, EndType] = (EndType.BUTT_WELD, EndType.BUTT_WELD)
    ref: str | None = None  # valve tag etc.
    description: str = ""  # BOM description

    @property
    def length_mm(self) -> float:
        d = (self.end.x - self.start.x, self.end.y - self.start.y, self.end.z - self.start.z)
        return math.sqrt(sum(c * c for c in d))


class Weld(Model):
    id: str  # W1, W2 ...
    at: Vec3
    between: tuple[str, str]  # component ids
    shop: bool = True  # False = field weld


class RoutedLine(Model):
    line_number: str  # matches PidLine.number
    components: list[Component]  # in flow order, run component-to-component
    welds: list[Weld] = []
    spool_breaks: list[str] = []  # weld ids where spools split

    @model_validator(mode="after")
    def _continuous(self) -> RoutedLine:
        for a, b in zip(self.components, self.components[1:], strict=False):
            gap = math.dist((a.end.x, a.end.y, a.end.z), (b.start.x, b.start.y, b.start.z))
            if gap > CONNECT_TOL_MM:
                raise ValueError(f"{self.line_number}: gap {gap:.2f} mm between {a.id} and {b.id}")
        return self


class EquipmentEnvelope(Model):
    """Axis-aligned box for collision checks (mm)."""

    tag: str
    min: Vec3
    max: Vec3


class PipingNetwork(Model):
    lines: list[RoutedLine]
    equipment: list[EquipmentEnvelope] = []
    rack_elevation_mm: float = 6000.0  # default pipe-rack centerline elevation
