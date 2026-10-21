"""Variable addresses over a flowsheet, its project and its solved results (spec P2-01).

The address grammar, moved here from ``agent/addresses.py`` (spec B-08), which
is now a one-line re-export so the B-08 tools keep working.

Read addresses (:func:`resolve`, against a solved flowsheet)::

    S-003.T, S-003.P, S-003.molar_flow, S-003.mass_flow, S-003.vapor_fraction
    S-003.x.CO2                      # mole fraction of CO2 in stream S-003
    K-101.duty_W, K-101.power_W, K-101.info.<key>

Write addresses (:func:`assign` on the unsolved flowsheet, :func:`set_address`
on the whole project)::

    K-101.params.<key>               # unit parameter, merged into the unit's params
    S-001.feed.<T|P|molar_flow>      # boundary feed condition
    S-001.feed.composition.<cid>     # one feed mole fraction; the rest rescale to sum to 1

:func:`readable` and :func:`writable` enumerate the addresses of a solved
flowsheet / flowsheet. Unknown addresses raise ValueError naming the nearest
valid ones.

Layer note: this module sits below ``solver`` (the design-spec outer loop reads
and writes through it) and above ``contracts`` only - in particular it must not
import ``agent``.
"""

from __future__ import annotations

from ngdesign.contracts import Flowsheet, Project, SolvedFlowsheet, StreamSpec
from ngdesign.contracts.specs import (
    READ_STREAM_FIELDS,
    READ_UNIT_FIELDS,
    WRITE_FEED_FIELDS,
)
from ngdesign.contracts.stream import StreamState

_STREAM_FIELDS = READ_STREAM_FIELDS
_UNIT_FIELDS = tuple(f for f in READ_UNIT_FIELDS if f != "info")
_FEED_FIELDS = tuple(f for f in WRITE_FEED_FIELDS if f != "composition")

__all__ = ["assign", "readable", "resolve", "set_address", "writable"]


def resolve(addr: str, solved: SolvedFlowsheet) -> float:
    """Value of a read address against a solved flowsheet.

    Raises ValueError naming the nearest valid addresses when anything along the
    path is unknown.
    """
    head, *rest = addr.split(".")
    if head in solved.streams:
        return _resolve_stream(addr, head, rest, solved)
    if head in solved.units:
        return _resolve_unit(addr, head, rest, solved)
    heads = sorted(solved.streams) + sorted(solved.units)
    shown = ", ".join(heads[:12]) + (f", ... (+{len(heads) - 12} more)" if len(heads) > 12 else "")
    raise ValueError(
        f"unknown address {addr!r}: {head!r} is neither a stream id nor a unit tag; "
        f"valid heads: {shown or '(none — solve first)'}"
    )


def assign(fs: Flowsheet, addr: str, value: float) -> Flowsheet:
    """The flowsheet with a write address set (pure: returns a new Flowsheet).

    Only ``<unit>.params.<key>``, ``<feed stream>.feed.<T|P|molar_flow>`` and
    ``<feed stream>.feed.composition.<cid>`` are writable; the rebuilt flowsheet
    revalidates through the pydantic contracts, so a nonsensical value (negative
    flow, a param a plugin rejects) raises ValueError there. A composition write
    sets one mole fraction and rescales the remaining components proportionally
    so the feed still sums to 1.
    """
    head, *rest = addr.split(".")
    if head in {u.tag for u in fs.units}:
        return _assign_unit_param(fs, head, rest, value)
    if head in {s.id for s in fs.streams}:
        return _assign_feed_field(fs, head, rest, value)
    unit_tags = sorted(u.tag for u in fs.units)
    feed_ids = sorted(s.id for s in fs.streams if s.feed is not None)
    raise ValueError(
        f"unknown write address {addr!r}; writable heads are unit tags "
        f"('<tag>.params.<key>') and feed stream ids ('<id>.feed.<T|P|molar_flow>'): "
        f"{unit_tags + feed_ids}"
    )


def set_address(project: Project, addr: str, value: float) -> Project:
    """The project with a write address set (pure: returns a new Project).

    The B-08 tool seam over :func:`assign`: only the flowsheet changes.
    """
    return Project(name=project.name, flowsheet=assign(project.flowsheet, addr, value), layout=project.layout)


def readable(solved: SolvedFlowsheet) -> list[str]:
    """Every read address the solved flowsheet answers (deterministic order)."""
    out: list[str] = []
    for sid in sorted(solved.streams):
        state = solved.streams[sid]
        out.extend(f"{sid}.{field}" for field in _STREAM_FIELDS if field != "x")
        out.extend(f"{sid}.x.{cid}" for cid in sorted(state.composition))
    for tag in sorted(solved.units):
        result = solved.units[tag]
        out.extend(f"{tag}.{field}" for field in _UNIT_FIELDS)
        out.extend(f"{tag}.info.{key}" for key in sorted(result.info))
    return out


def writable(fs: Flowsheet) -> list[str]:
    """Every write address the flowsheet accepts (deterministic order).

    Unit params list the keys the unit already carries (params are open dicts);
    feed compositions list the components the feed itself carries.
    """
    out: list[str] = []
    for unit in sorted(fs.units, key=lambda u: u.tag):
        out.extend(f"{unit.tag}.params.{key}" for key in sorted(unit.params))
    for s in sorted(fs.streams, key=lambda s: s.id):
        if s.feed is None:
            continue
        out.extend(f"{s.id}.feed.{field}" for field in _FEED_FIELDS)
        out.extend(f"{s.id}.feed.composition.{cid}" for cid in sorted(s.feed.composition))
    return out


def _rebuild(fs: Flowsheet, **updates: object) -> Flowsheet:
    """A revalidated copy of ``fs`` with whole-model ``updates`` (pure)."""
    dump = fs.model_dump()
    return Flowsheet(**{**dump, **updates})


def _resolve_stream(addr: str, stream_id: str, rest: list[str], solved: SolvedFlowsheet) -> float:
    state: StreamState = solved.streams[stream_id]
    if not rest:
        fields = (*_STREAM_FIELDS, "x.<component_id>")
        raise ValueError(f"incomplete address {addr!r}: '{stream_id}.<field>' with fields {sorted(fields)}")
    field = rest[0]
    if field == "x":
        if len(rest) != 2:
            raise ValueError(f"bad address {addr!r}: '{stream_id}.x' needs a component id")
        cid = rest[1]
        if cid not in state.composition:
            raise ValueError(
                f"component {cid!r} is not in stream {stream_id}; have {sorted(state.composition)}"
            )
        return state.composition[cid]
    if field == "mass_flow":
        return state.mass_flow
    if field in ("T", "P", "molar_flow", "vapor_fraction"):
        return float(getattr(state, field))
    raise ValueError(
        f"unknown field {field!r} in {addr!r}; stream fields are {sorted(_STREAM_FIELDS)} "
        "and x.<component_id>"
    )


def _resolve_unit(addr: str, tag: str, rest: list[str], solved: SolvedFlowsheet) -> float:
    result = solved.units[tag]
    if not rest:
        raise ValueError(
            f"incomplete address {addr!r}: '{tag}.<field>' with fields {sorted(_UNIT_FIELDS)} and info.<key>"
        )
    field = rest[0]
    if field in _UNIT_FIELDS:
        return float(getattr(result, field))
    if field == "info":
        if len(rest) != 2 or rest[1] not in result.info:
            raise ValueError(f"bad address {addr!r}: unit {tag} info keys are {sorted(result.info)}")
        return result.info[rest[1]]
    raise ValueError(
        f"unknown field {field!r} in {addr!r}; unit fields are {sorted(_UNIT_FIELDS)} and info.<key>"
    )


def _assign_unit_param(fs: Flowsheet, tag: str, rest: list[str], value: float) -> Flowsheet:
    if len(rest) != 2 or rest[0] != "params":
        raise ValueError(
            f"bad write address {tag}.{'.'.join(rest)!r}: unit writes look like '{tag}.params.<key>'"
        )
    units = [
        u.model_copy(update={"params": {**u.params, rest[1]: value}}) if u.tag == tag else u for u in fs.units
    ]
    return _rebuild(fs, units=units)


def _assign_feed_field(fs: Flowsheet, stream_id: str, rest: list[str], value: float) -> Flowsheet:
    spec: StreamSpec = next(s for s in fs.streams if s.id == stream_id)  # exists: assign checked
    if len(rest) >= 2 and rest[0] != "feed":
        raise ValueError(
            f"bad write address {stream_id}.{'.'.join(rest)!r}: stream writes look like "
            f"'{stream_id}.feed.<T|P|molar_flow|composition.<cid>>'"
        )
    if len(rest) == 3 and rest[1] == "composition":
        return _assign_feed_composition(fs, spec, rest[2], value)
    if len(rest) != 2:
        raise ValueError(
            f"bad write address {stream_id}.{'.'.join(rest)!r}: stream writes look like "
            f"'{stream_id}.feed.<T|P|molar_flow|composition.<cid>>'"
        )
    field = rest[1]
    if field not in _FEED_FIELDS:
        raise ValueError(
            f"unknown feed field {field!r}; writable feed fields are {sorted(_FEED_FIELDS)} "
            "and composition.<cid>"
        )
    if spec.feed is None:
        raise ValueError(
            f"stream {stream_id} has a source, not a feed; only feed streams accept '.feed.' writes"
        )
    streams: list[StreamSpec] = []
    for s in fs.streams:
        if s.id == stream_id and s.feed is not None:
            streams.append(s.model_copy(update={"feed": s.feed.model_copy(update={field: value})}))
        else:
            streams.append(s)
    return _rebuild(fs, streams=streams)


def _assign_feed_composition(fs: Flowsheet, spec: StreamSpec, cid: str, value: float) -> Flowsheet:
    """One feed mole fraction set, the rest rescaled to keep the sum at 1 (pure)."""
    if spec.feed is None:
        raise ValueError(
            f"stream {spec.id} has a source, not a feed; only feed streams accept '.feed.' writes"
        )
    composition = dict(spec.feed.composition)
    if cid not in composition:
        raise ValueError(
            f"component {cid!r} is not in the feed of stream {spec.id}; have {sorted(composition)}"
        )
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"mole fraction for {cid!r} must be in [0, 1], got {value}")
    others_total = sum(composition.values()) - composition[cid]
    scale = (1.0 - value) / others_total if others_total > 0.0 else 0.0
    new_composition = {c: value if c == cid else max(v * scale, 0.0) for c, v in composition.items()}
    streams: list[StreamSpec] = []
    for s in fs.streams:
        if s.id == spec.id and s.feed is not None:
            streams.append(
                s.model_copy(update={"feed": s.feed.model_copy(update={"composition": new_composition})})
            )
        else:
            streams.append(s)
    return _rebuild(fs, streams=streams)
