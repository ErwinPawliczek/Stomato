"""Request and response models of the public REST API v1, with OpenAPI examples."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def _examples(*examples: dict[str, Any]) -> ConfigDict:
    return ConfigDict(json_schema_extra={"examples": list(examples)})


class XYIn(BaseModel):
    x: float
    y: float


class GridIn(BaseModel):
    """An axial cell (q, r) of the flowsheet canvas's flat-top hex lattice."""

    q: int
    r: int


class Change(BaseModel):
    """One recorded project change: who, what, and the structured diff."""

    seq: int | None
    kind: str | None = None
    op: str
    actor: str
    summary: str
    state: str | None = None
    target_seq: int | None = None
    version: int | None = None
    created_at: str | None = None
    args: dict[str, Any] = {}
    diff: dict[str, Any]
    lines: list[str]


class Mutation(BaseModel):
    """Every mutating v1 call answers with the operation result and the change
    it committed (``null`` when the write changed nothing)."""

    result: dict[str, Any]
    change: Change | None


class ChangeList(BaseModel):
    changes: list[Change]


class ApiIndex(BaseModel):
    version: str
    openapi: str
    docs: str
    tools: str
    mcp: str


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    mutates: bool


class ToolRun(BaseModel):
    """A tool run's output: the result plus the change of a mutating tool."""

    result: dict[str, Any]
    change: Change | None


class UnitCreate(BaseModel):
    model_config = _examples(
        {
            "kind": "cooler",
            "tag": "E-201",
            "params": {"T_out": 313.15, "dP": 20000},
            "grid": {"q": 4, "r": 0},
        },
        {"kind": "separator_3phase", "position": {"x": 480, "y": 120}},
    )

    kind: str = Field(description="Unit kind id from GET /api/v1/catalogue/units")
    tag: str | None = Field(None, description="Tag like V-102; omitted: next free tag from the P&ID symbol")
    params: dict[str, Any] | None = Field(None, description="Unit params (SI, see the kind's param schema)")
    position: XYIn | None = Field(None, description="Free placement in layout units")
    grid: GridIn | None = Field(None, description="Hex-grid placement (exclusive with position)")
    view: Literal["pfd", "pid"] = "pfd"


class UnitPatch(BaseModel):
    model_config = _examples({"params": {"P_out": 6500000}}, {"params": {"T_out": 300.0}, "replace": True})

    params: dict[str, Any]
    replace: bool = Field(False, description="true: replace all params; false: merge")


class UnitPosition(BaseModel):
    model_config = _examples(
        {"view": "pfd", "grid": {"q": 3, "r": 1}}, {"view": "pid", "position": {"x": 200, "y": 90}}
    )

    view: Literal["pfd", "pid"] = "pfd"
    position: XYIn | None = None
    grid: GridIn | None = None


class PortIn(BaseModel):
    unit: str
    port: str


class FeedIn(BaseModel):
    """Boundary feed conditions in SI (K, Pa abs, mol/s, mole fractions)."""

    T: float
    P: float
    molar_flow: float
    composition: dict[str, float]


class StreamCreate(BaseModel):
    """A feed (``source`` omitted: ``target`` + ``feed``), a connection (both
    ends) or a product (``target`` omitted)."""

    model_config = _examples(
        {
            "id": "S-020",
            "target": {"unit": "V-101", "port": "inlet"},
            "feed": {"T": 293.15, "P": 3.5e6, "molar_flow": 100.0, "composition": {"C1": 0.9, "C2": 0.1}},
            "service": "PG",
        },
        {"source": {"unit": "K-101", "port": "outlet"}, "target": {"unit": "E-201", "port": "inlet"}},
    )

    id: str | None = Field(None, description="Stream id; omitted: next free S-NNN")
    source: PortIn | None = None
    target: PortIn | None = None
    feed: FeedIn | None = None
    service: str | None = Field(None, description="Fluid code: PG, PL, W, GL")


class FeedPatch(BaseModel):
    T: float | None = None
    P: float | None = None
    molar_flow: float | None = None
    composition: dict[str, float] | None = None


class StreamPatch(BaseModel):
    model_config = _examples({"service": "PG"}, {"feed": {"T": 300.0, "P": 4.0e6}})

    service: str | None = None
    feed: FeedPatch | None = None


class CellSet(BaseModel):
    """A value with an optional unit (converted to the cell's declared unit)."""

    model_config = _examples({"value": 25, "unit": "degC"}, {"value": 65, "unit": "bar"}, {"value": 0.8})

    value: float | str | bool
    unit: str | None = None


class ThermoSet(BaseModel):
    model_config = _examples({"package": "srk"})

    package: str = Field(description="Registered thermo package id (GET /api/v1/catalogue/thermo)")


class ComponentsSet(BaseModel):
    model_config = _examples({"components": ["N2", "CO2", "C1", "C2", "C3", "H2O"]})

    components: list[str]


class DesignSpecIn(BaseModel):
    model_config = _examples(
        {
            "id": "DS-001",
            "target": "S-003.T",
            "value": 400.0,
            "manipulated": "K-101.params.P_out",
            "lower": 5.0e6,
            "upper": 8.0e6,
        }
    )

    id: str
    target: str = Field(description="Readable address, e.g. S-005.x.H2O")
    value: float
    manipulated: str = Field(description="Writable address, e.g. K-101.params.P_out")
    lower: float
    upper: float
    tolerance: float | None = None
    max_iterations: int | None = None


__all__ = [
    "ApiIndex",
    "CellSet",
    "Change",
    "ChangeList",
    "ComponentsSet",
    "DesignSpecIn",
    "FeedIn",
    "FeedPatch",
    "GridIn",
    "Mutation",
    "PortIn",
    "StreamCreate",
    "StreamPatch",
    "ThermoSet",
    "ToolInfo",
    "ToolRun",
    "UnitCreate",
    "UnitPatch",
    "UnitPosition",
    "XYIn",
]
