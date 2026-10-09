"""Plugin interfaces. LOCKED. Every plugin implements one of these Protocols
and registers itself with @register(kind, name) from ngdesign.registry.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .flowsheet import Datasheet, Flowsheet, SolvedFlowsheet, UnitResult
from .isometric import IsoSheet
from .pid import PID, RuleViolation
from .piping import PipingNetwork, RoutedLine
from .stream import StreamState


@runtime_checkable
class Thermo(Protocol):
    """Kind "thermo". Peng-Robinson package. All SI."""

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState: ...
    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState: ...
    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState: ...


@runtime_checkable
class Correlation(Protocol):
    """Kind "correlation". A pure function object; name matches data/golden/<name>.yaml.
    Called with that file's `inputs` as kwargs; returns a dict containing every `expected` key.
    """

    def __call__(self, **inputs: Any) -> dict[str, Any]: ...


@runtime_checkable
class UnitModel(Protocol):
    """Kind "unit". Pure: no I/O, no global state.

    example_case() returns (feeds, params): feeds maps inlet port -> FeedSpec kwargs
    (T, P, molar_flow, composition). The shared balance test uses it for every unit.
    """

    inlet_ports: tuple[str, ...]
    outlet_ports: tuple[str, ...]

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult: ...

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]: ...


@runtime_checkable
class Sizer(Protocol):
    """Kind "sizer". Produces an equipment datasheet for one unit kind."""

    unit_kind: str

    def size(self, tag: str, solved: SolvedFlowsheet, params: dict[str, Any]) -> Datasheet: ...


@runtime_checkable
class Solver(Protocol):
    """Kind "solver"."""

    def solve(self, fs: Flowsheet, thermo: Thermo) -> SolvedFlowsheet: ...


@runtime_checkable
class PidBuilder(Protocol):
    """Kind "pid_builder". SolvedFlowsheet -> PID (before rules)."""

    def build(self, solved: SolvedFlowsheet) -> PID: ...


@runtime_checkable
class PidRule(Protocol):
    """Kind "pid_rule". `apply` inserts what the rule requires; `check` reports violations.
    Invariant (tested for every rule): check(apply(pid)) == [].
    """

    def apply(self, pid: PID) -> PID: ...
    def check(self, pid: PID) -> list[RuleViolation]: ...


@runtime_checkable
class Router(Protocol):
    """Kind "router". PID + equipment layout -> 3D PipingNetwork."""

    def route(self, pid: PID, layout: dict[str, Any]) -> PipingNetwork: ...


@runtime_checkable
class IsoRenderer(Protocol):
    """Kind "iso_renderer"."""

    def render(self, line: RoutedLine, pid: PID) -> IsoSheet: ...


@runtime_checkable
class DiagramRenderer(Protocol):
    """Kind "diagram". Returns a complete SVG document string (PFD or P&ID)."""

    def render(self, obj: Any) -> str: ...
