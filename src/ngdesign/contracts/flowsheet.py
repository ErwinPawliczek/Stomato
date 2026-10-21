"""Flowsheet topology + solved results. LOCKED."""

from __future__ import annotations

from typing import Any

from pydantic import field_validator, model_validator

from ngdesign.data import is_curated

from .common import Model, Nozzle, check_tag
from .components import ComponentRef, PseudoDefinition
from .diagnostics import BlockRecord, SolveStatus, UnitError
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
    # The flowsheet's component slate (specs P1-02, P1-07). Each entry is a plain
    # id the component registry resolves (curated, databank or registered pseudo)
    # or a PseudoDefinition the flowsheet owns and carries with itself - so a
    # saved project is self-describing and two flowsheets in one process can
    # define the same pseudo id differently. When omitted, a validator derives
    # the slate from the feed compositions (sorted, for deterministic tear-vector
    # indexing) so every existing sample keeps its meaning.
    components: list[ComponentRef] = []

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
        for entry in self.components:
            if isinstance(entry, PseudoDefinition) and is_curated(entry.id):
                raise ValueError(f"pseudo-component {entry.id!r} is reserved by the curated slate")
        tags = [u.tag for u in self.units]
        if len(tags) != len(set(tags)):
            raise ValueError("duplicate unit tags")
        ids = [s.id for s in self.streams]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate stream ids")
        known = set(tags)
        slate = set(self.slate_ids())
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

    def slate_ids(self) -> list[str]:
        """The component ids of the slate, in order (tear-vector indexing order)."""
        return [entry if isinstance(entry, str) else entry.id for entry in self.components]

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
    # Spec P2-02 diagnostics: which units failed, and how the tears converged.
    # ``status`` is derived, never set by hand: ``failed`` when any unit failed
    # outright (a non-upstream UnitError - upstream skips are not failures),
    # else the ``converged`` flag as "converged"/"not_converged".
    status: SolveStatus = "converged"
    errors: list[UnitError] = []
    history: list[BlockRecord] = []

    @model_validator(mode="after")
    def _derive_status(self) -> SolvedFlowsheet:
        # Derived, never set by hand. The write goes through __dict__ because
        # validate_assignment re-runs this validator on a plain assignment.
        if any(not e.upstream for e in self.errors):
            self.__dict__["status"] = "failed"
        elif self.converged:
            self.__dict__["status"] = "converged"
        else:
            self.__dict__["status"] = "not_converged"
        return self
