"""LOCKED contracts. Every layer talks only through these models."""

from .common import Direction, Model, Nozzle, Vec3
from .components import ComponentSet
from .flowsheet import (
    Datasheet,
    FeedSpec,
    Flowsheet,
    PortRef,
    SolvedFlowsheet,
    StreamSpec,
    UnitResult,
    UnitSpec,
)
from .isometric import BomItem, CutPiece, Isometric, IsoSheet, TitleBlock
from .pid import (
    PID,
    FailPosition,
    InlineItem,
    InlineKind,
    Instrument,
    LineEnd,
    PidEquipment,
    PidLine,
    RuleViolation,
    Valve,
    ValveType,
)
from .piping import Component, ComponentKind, EndType, EquipmentEnvelope, PipingNetwork, RoutedLine, Weld
from .project import XY, Layout, Project
from .stream import DEFAULT_SLATE, Phase, PhaseKind, StreamState

__all__ = [
    "BomItem",
    # NOTE: "Component" here is the PIPING Component (a fitting/weld item from
    # .piping). The component-registry record is deliberately not re-exported to
    # avoid the name clash - import it as
    # `from ngdesign.contracts.components import Component` (spec P1-02).
    "Component",
    "ComponentSet",
    "ComponentKind",
    "CutPiece",
    "DEFAULT_SLATE",
    "Datasheet",
    "Direction",
    "EndType",
    "EquipmentEnvelope",
    "FailPosition",
    "FeedSpec",
    "Flowsheet",
    "InlineItem",
    "InlineKind",
    "Instrument",
    "IsoSheet",
    "Isometric",
    "Layout",
    "LineEnd",
    "Model",
    "Nozzle",
    "PID",
    "Phase",
    "PhaseKind",
    "PidEquipment",
    "PidLine",
    "PipingNetwork",
    "PortRef",
    "Project",
    "RoutedLine",
    "RuleViolation",
    "SolvedFlowsheet",
    "StreamSpec",
    "StreamState",
    "TitleBlock",
    "UnitResult",
    "UnitSpec",
    "Valve",
    "ValveType",
    "Vec3",
    "Weld",
    "XY",
]
