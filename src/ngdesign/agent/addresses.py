"""Variable addresses over the project and its solved results (spec B-08).

Grammar (B-07 later generalises this module into ``ngdesign.variables``; the
grammar stays identical).

Read addresses (:func:`resolve`, against a solved flowsheet)::

    S-003.T, S-003.P, S-003.molar_flow, S-003.mass_flow, S-003.vapor_fraction
    S-003.x.CO2                      # mole fraction of CO2 in stream S-003
    K-101.duty_W, K-101.power_W, K-101.info.<key>

Write addresses (:func:`set_address`, on the unsolved project)::

    K-101.params.<key>               # unit parameter, merged into the unit's params
    S-001.feed.<T|P|molar_flow>      # boundary feed condition

Unknown addresses raise ValueError naming the nearest valid ones.
"""

from __future__ import annotations

from ngdesign.agent.engine import rebuild_flowsheet
from ngdesign.contracts import FeedSpec, Flowsheet, Project, SolvedFlowsheet, StreamSpec, UnitSpec
from ngdesign.contracts.stream import StreamState

_STREAM_FIELDS = ("T", "P", "molar_flow", "mass_flow", "vapor_fraction")
_UNIT_FIELDS = ("duty_W", "power_W")
_FEED_FIELDS = ("T", "P", "molar_flow")


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


def set_address(project: Project, addr: str, value: float) -> Project:
    """The project with a write address set (pure: returns a new Project).

    Only ``<unit>.params.<key>`` and ``<feed stream>.feed.<T|P|molar_flow>`` are
    writable; the rebuilt project revalidates through the pydantic contracts, so
    a nonsensical value (negative flow, a param a plugin rejects) raises
    ValueError there.
    """
    head, *rest = addr.split(".")
    fs = project.flowsheet
    if head in {u.tag for u in fs.units}:
        return _set_unit_param(project, head, rest, value)
    if head in {s.id for s in fs.streams}:
        return _set_feed_field(project, head, rest, value)
    unit_tags = sorted(u.tag for u in fs.units)
    feed_ids = sorted(s.id for s in fs.streams if s.feed is not None)
    raise ValueError(
        f"unknown write address {addr!r}; writable heads are unit tags "
        f"('<tag>.params.<key>') and feed stream ids ('<id>.feed.<T|P|molar_flow>'): "
        f"{unit_tags + feed_ids}"
    )


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


def _set_unit_param(project: Project, tag: str, rest: list[str], value: float) -> Project:
    fs = project.flowsheet
    if len(rest) != 2 or rest[0] != "params":
        raise ValueError(
            f"bad write address {tag}.{'.'.join(rest)!r}: unit writes look like '{tag}.params.<key>'"
        )
    spec = fs.unit(tag)  # exists: set_address checked the head
    new_params = {**spec.params, rest[1]: value}
    units = [UnitSpec(tag=tag, kind=spec.kind, params=new_params) if u.tag == tag else u for u in fs.units]
    return _with_flowsheet(project, fs, units=units)


def _set_feed_field(project: Project, stream_id: str, rest: list[str], value: float) -> Project:
    fs = project.flowsheet
    if len(rest) != 2 or rest[0] != "feed":
        raise ValueError(
            f"bad write address {stream_id}.{'.'.join(rest)!r}: stream writes look like "
            f"'{stream_id}.feed.<T|P|molar_flow>'"
        )
    field = rest[1]
    if field not in _FEED_FIELDS:
        raise ValueError(f"unknown feed field {field!r}; writable feed fields are {sorted(_FEED_FIELDS)}")
    spec = next(s for s in fs.streams if s.id == stream_id)  # exists: set_address checked the head
    if spec.feed is None:
        raise ValueError(
            f"stream {stream_id} has a source, not a feed; only feed streams accept '.feed.' writes"
        )
    values = {"T": spec.feed.T, "P": spec.feed.P, "molar_flow": spec.feed.molar_flow}
    values[field] = value
    feed = FeedSpec(
        T=values["T"], P=values["P"], molar_flow=values["molar_flow"], composition=dict(spec.feed.composition)
    )
    streams = [
        StreamSpec(id=stream_id, source=spec.source, target=spec.target, feed=feed, service=spec.service)
        if s.id == stream_id
        else s
        for s in fs.streams
    ]
    return _with_flowsheet(project, fs, streams=streams)


def _with_flowsheet(
    project: Project,
    fs: Flowsheet,
    *,
    units: list[UnitSpec] | None = None,
    streams: list[StreamSpec] | None = None,
) -> Project:
    """The project over a rebuilt flowsheet (pydantic revalidates the result)."""
    return Project(
        name=project.name,
        flowsheet=rebuild_flowsheet(fs, units=units, streams=streams),
        layout=project.layout,
    )
