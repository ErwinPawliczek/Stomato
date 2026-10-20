"""Flowsheet topology + solved results. LOCKED."""

from __future__ import annotations

from typing import Any

from pydantic import field_validator, model_validator

from .common import Model, Nozzle, check_tag
from .stream import StreamState, _check_composition


class PortRef(Model):
    unit: str  # unit tag
    port: str  # port name defined by the unit plugin, e.g. "inlet", "gas_out"


class FeedSpec(Model):
    """Boundary feed conditions; the solver flashes this into a StreamState."""

    T: float  # K
    P: float  # Pa abs
    molar_flow: float  # mol/s
    composition: dict[str, float]

    @field_validator("composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)


class StreamSpec(Model):
    """A stream between two ports. source=None means a feed; target=None means a product."""

    id: str  # S-001 style, unique
    source: PortRef | None = None
    target: PortRef | None = None
    feed: FeedSpec | None = None  # required when source is None
    service: str = "process"  # fluid code basis for line numbering, e.g. "PG", "PL", "W"

    @model_validator(mode="after")
    def _ends(self) -> StreamSpec:
        if self.source is None and self.target is None:
            raise ValueError(f"stream {self.id} has no source and no target")
        if self.source is None and self.feed is None:
            raise ValueError(f"feed stream {self.id} needs a feed state")
        return self


class UnitSpec(Model):
    tag: str
    kind: str  # registry name, e.g. "separator_3phase"
    params: dict[str, Any] = {}

    @field_validator("tag")
    @classmethod
    def _tag(cls, v: str) -> str:
        return check_tag(v)


class Flowsheet(Model):
    name: str
    units: list[UnitSpec]
    streams: list[StreamSpec]
    # Registered "thermo" plugin name (expansion spec): resolved against the
    # registry at solve entry; an unknown name fails the solve there.
    thermo: str = "pr"
    # The flowsheet's component slate (spec P1-02). Open: any id the component
    # registry resolves. When omitted, a validator derives it from the feed
    # compositions (sorted, for deterministic tear-vector indexing) so every
    # existing sample keeps its meaning.
    components: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _default_components(cls, data: Any) -> Any:
        """Default the slate to the ids present in the feeds when it is not given."""
        if isinstance(data, dict) and data.get("components") is None:
            ids: set[str] = set()
            for stream in data.get("streams") or []:
                feed = stream.get("feed") if isinstance(stream, dict) else getattr(stream, "feed", None)
                composition = (
                    feed.get("composition") if isinstance(feed, dict) else getattr(feed, "composition", None)
                )
                if composition:
                    ids |= set(composition)
            data = {**data, "components": sorted(ids)}
        return data

    @model_validator(mode="after")
    def _topology(self) -> Flowsheet:
        tags = [u.tag for u in self.units]
        if len(tags) != len(set(tags)):
            raise ValueError("duplicate unit tags")
        ids = [s.id for s in self.streams]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate stream ids")
        known = set(tags)
        slate = set(self.components)
        used: set[tuple[str, str]] = set()
        for s in self.streams:
            if s.feed is not None:
                unknown = set(s.feed.composition) - slate
                if unknown:
                    raise ValueError(
                        f"stream {s.id}: feed components {sorted(unknown)} are not in the "
                        "flowsheet component slate"
                    )
            for ref in (s.source, s.target):
                if ref is None:
                    continue
                if ref.unit not in known:
                    raise ValueError(f"stream {s.id} references unknown unit {ref.unit}")
                key = (ref.unit, ref.port)
                if key in used:
                    raise ValueError(f"port {ref.unit}.{ref.port} connected twice")
                used.add(key)
        return self

    def unit(self, tag: str) -> UnitSpec:
        return next(u for u in self.units if u.tag == tag)

    def inlets(self, tag: str) -> list[StreamSpec]:
        return [s for s in self.streams if s.target and s.target.unit == tag]

    def outlets(self, tag: str) -> list[StreamSpec]:
        return [s for s in self.streams if s.source and s.source.unit == tag]


class UnitResult(Model):
    """What a unit plugin returns from solve()."""

    outlets: dict[str, StreamState]  # port -> state
    duty_W: float = 0.0  # heat added to process (+) or removed (-)
    power_W: float = 0.0  # shaft power into process (+) or out (-)
    info: dict[str, float] = {}  # unit-specific scalars (efficiency used, stages, ...)


class Datasheet(Model):
    """Sizing output for one piece of equipment."""

    tag: str
    kind: str
    design_pressure_Pa: float
    design_temperature_K: float
    dimensions: dict[str, float]  # m, e.g. {"diameter": 1.5, "length_tt": 6.0}
    nozzles: list[Nozzle]
    notes: list[str] = []


class SolvedFlowsheet(Model):
    flowsheet: Flowsheet
    streams: dict[str, StreamState]  # stream id -> state
    units: dict[str, UnitResult]  # tag -> result
    datasheets: dict[str, Datasheet] = {}  # tag -> sizing
    converged: bool
    iterations: int = 0
