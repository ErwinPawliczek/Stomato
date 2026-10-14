"""P&ID builder from a solved flowsheet (spec S-33). Kind ``pid_builder``,
name ``default``.

Emits the bare P&ID -- equipment with nozzles, one numbered line per stream,
no valves or instruments: the ``pid_rule`` plugins insert those afterwards,
and the S-18 renderer consumes the result.

Equipment comes from datasheets: the registered ``sizer`` plugin for the unit
kind runs when the solved flowsheet carries no datasheet yet; a unit with no
sizer gets default nozzles (one per sim port, west face for inlets, east for
outlets) and design conditions equal to the max operating P/T over its
connected streams.  ``psv`` nozzles on pressure vessels come from the sizer
datasheets (S-14's rule checks for them; it does not create them).
Rotating-machine nozzles carry the conventional ``suction``/``discharge``
service labels the S-13/S-16 rules look for; line ends attach by ``port``.

Lines follow the spec's method: NPS from the S-20 correlation on the stream's
actual volumetric flow, fluid code from ``StreamSpec.service``, pipe class in
the spec's order (D1 above the class-300 CS limit, L1 below 244 K, S1 for
amine/sour, else B1), design P/T as the max over the connected equipment ends,
number ``<nps>"-<fluid>-<seq>-<class>`` numbered from 1001 in stream order,
boundary labels ``BL-<stream id>`` on feeds and products.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ngdesign import registry
from ngdesign.contracts import (
    PID,
    Datasheet,
    Direction,
    LineEnd,
    Nozzle,
    PidEquipment,
    PidLine,
    PortRef,
    SolvedFlowsheet,
    StreamSpec,
    StreamState,
    UnitSpec,
    Vec3,
)
from ngdesign.contracts.plugins import Sizer
from ngdesign.data import pipe_classes
from ngdesign.registry import register
from ngdesign.sizing.line_size import line_size

__all__ = ["DefaultPidBuilder"]

#: Fluid code inside a line number: 1-3 capital letters (see LINE_NO_RE).
FLUID_CODE_RE = re.compile(r"^[A-Z]{1,3}$")

#: Class-300 carbon-steel flange limit at 100 F is 740 psig = 5.1 MPa: above
#: it a line goes to the class-600 pipe class (spec S-33).
CLASS_300_LIMIT_PA = 5.1e6
#: Below this temperature carbon steel leaves its toughness envelope and the
#: LTCS class takes over (spec S-33; A106 min temp -29 C).
COLD_SERVICE_K = 244.0

#: Line numbers run from 1001 in stream order (spec S-33).
FIRST_LINE_SEQ = 1001

_NOZZLE_ID_RE = re.compile(r"^N(\d+)$")

# Default-nozzle geometry (mm) for units whose sizer has not landed yet.
_INLET_X_MM = 0.0
_OUTLET_X_MM = 2000.0
_PORT_PITCH_MM = 600.0
#: Stand-in size for a declared port no stream connects to (nothing flows).
_UNCONNECTED_NPS_IN = 1.0

#: Rotating-machine nozzles carry conventional service labels (the human-owned
#: sample sets the convention; the S-13/S-16 rules search for them).
_MACHINE_SERVICES: dict[str, dict[str, str]] = {
    "pump": {"inlet": "suction", "outlet": "discharge"},
    "compressor": {"inlet": "suction", "outlet": "discharge"},
}


def _nozzle_service(unit_kind: str, port: str) -> str:
    """Nozzle service label for a sim port: machines use ``suction``/
    ``discharge``, every other unit labels nozzles with the port name."""
    return _MACHINE_SERVICES.get(unit_kind, {}).get(port, port)


def _nozzle_for_port(nozzles: list[Nozzle], unit_kind: str, port: str) -> Nozzle | None:
    """The nozzle serving a sim port, if any: an exact ``port`` match first,
    then a portless nozzle whose service names the port (raw port name or the
    conventional machine service)."""
    for noz in nozzles:
        if noz.port == port:
            return noz
    service = _nozzle_service(unit_kind, port)
    for noz in nozzles:
        if noz.port is None and noz.service in (port, service):
            return noz
    return None


def _unit_ports(unit_kind: str, streams: list[StreamSpec]) -> tuple[list[str], list[str]]:
    """(inlet, outlet) sim ports of a unit: the registered unit plugin's
    declaration when one exists, else the ports the streams actually use."""
    try:
        cls: type | None = registry.get("unit", unit_kind)
    except KeyError:
        cls = None
    inlets = [str(p) for p in getattr(cls, "inlet_ports", ())] if cls is not None else []
    outlets = [str(p) for p in getattr(cls, "outlet_ports", ())] if cls is not None else []
    if not inlets:
        inlets = [s.target.port for s in streams if s.target is not None and s.target.port]
    if not outlets:
        outlets = [s.source.port for s in streams if s.source is not None and s.source.port]
    return inlets, outlets


def _connections(solved: SolvedFlowsheet) -> dict[str, list[tuple[StreamSpec, StreamState]]]:
    """(stream spec, solved state) pairs touching each unit, in stream order."""
    connected: dict[str, list[tuple[StreamSpec, StreamState]]] = {u.tag: [] for u in solved.flowsheet.units}
    for stream in solved.flowsheet.streams:
        state = _state_for(solved, stream.id)
        for ref in (stream.source, stream.target):
            if ref is not None:
                connected[ref.unit].append((stream, state))
    return connected


def _sizer_for(unit_kind: str) -> Sizer | None:
    """First registered ``sizer`` whose ``unit_kind`` matches, if any
    (``registry.available`` is sorted, so the choice is deterministic)."""
    for name in registry.available("sizer"):
        cls = registry.get("sizer", name)
        if getattr(cls, "unit_kind", None) == unit_kind:
            sizer: Sizer = cls()
            return sizer
    return None


def _datasheet_for(solved: SolvedFlowsheet, spec: UnitSpec) -> Datasheet | None:
    """The unit's datasheet: one already attached to the solved flowsheet, or
    the registered sizer run now; None when no sizer knows the kind."""
    sheet = solved.datasheets.get(spec.tag)
    if sheet is not None:
        return sheet
    sizer = _sizer_for(spec.kind)
    return None if sizer is None else sizer.size(spec.tag, solved, spec.params)


def _state_for(solved: SolvedFlowsheet, stream_id: str) -> StreamState:
    """The solved state of one stream, with an honest error when missing."""
    state = solved.streams.get(stream_id)
    if state is None:
        raise ValueError(f"stream {stream_id} is unsolved; the builder needs a fully solved flowsheet")
    return state


def _design_conditions(sheet: Datasheet | None, states: list[StreamState], tag: str) -> tuple[float, float]:
    """(design pressure, design temperature) for one equipment: datasheet
    values when a sizer produced them, else the max operating P/T over the
    unit's connected streams (no sizer ran, so no margin)."""
    if sheet is not None:
        return sheet.design_pressure_Pa, sheet.design_temperature_K
    if not states:
        raise ValueError(f"unit {tag} has no sizer and no connected streams; design conditions unknown")
    return max(s.P for s in states), max(s.T for s in states)


def _phase_mass_kg_s(state: StreamState, phase_mole_fraction: float, phase_mw: float) -> float:
    return state.molar_flow * phase_mole_fraction * phase_mw / 1000.0


def _volumetric_flow_m3_s(state: StreamState, stream_id: str) -> float:
    """Actual volumetric flow: each phase's mass flow over its density,
    summed (the S-20 correlation sizes by velocity)."""
    if not state.phases:
        raise ValueError(f"stream {stream_id} has no phases; the builder needs flashed states")
    return sum(
        _phase_mass_kg_s(state, ph.mole_fraction, ph.molecular_weight) / ph.density for ph in state.phases
    )


def _flowing_density_kg_m3(state: StreamState, q_m3_s: float, stream_id: str) -> float:
    """Mixture density: total mass flow over total volumetric flow (what the
    API RP 14E erosional check inside the S-20 correlation uses)."""
    if q_m3_s <= 0.0:
        raise ValueError(f"stream {stream_id} has no flow; cannot size a line")
    mass = sum(_phase_mass_kg_s(state, ph.mole_fraction, ph.molecular_weight) for ph in state.phases)
    return mass / q_m3_s


def _line_nps_in(state: StreamState, service: str, stream_id: str) -> float:
    """NPS from the S-20 line-size correlation (``line`` role), keyed on the
    stream's service code."""
    if not FLUID_CODE_RE.match(service):
        raise ValueError(f"stream {stream_id} service {service!r} is not a 1-3 letter fluid code")
    q_m3_s = _volumetric_flow_m3_s(state, stream_id)
    rho = _flowing_density_kg_m3(state, q_m3_s, stream_id)
    try:
        sized = line_size(service=service, flow_m3_s=q_m3_s, rho_kg_m3=rho)
    except ValueError as err:
        raise ValueError(f"stream {stream_id} ({service}): {err}") from err
    return float(sized["nps_in"])


def _pipe_class_for(design_P_Pa: float, design_T_K: float, composition: dict[str, float]) -> str:
    """Pipe class per spec S-33, in the spec's order: D1 above the class-300
    CS limit, L1 below 244 K, S1 for amine or sour service (MDEA or H2S
    present; S1 covers amine and wet acid gas per data/pipe_classes.yaml),
    else B1."""
    if design_P_Pa > CLASS_300_LIMIT_PA:
        return "D1"
    if design_T_K < COLD_SERVICE_K:
        return "L1"
    if composition.get("MDEA", 0.0) > 0.0 or composition.get("H2S", 0.0) > 0.0:
        return "S1"
    return "B1"


def _line_number(nps_in: float, fluid_code: str, seq: int, pipe_class: str) -> str:
    """Line number ``<nps>"-<fluid>-<seq>-<class>``, e.g. ``6"-PG-1001-B1``."""
    return f'{nps_in:g}"-{fluid_code}-{seq:04d}-{pipe_class}'


def _next_nozzle_id(existing: list[Nozzle]) -> str:
    numbers = [int(m.group(1)) for noz in existing if (m := _NOZZLE_ID_RE.match(noz.id))]
    return f"N{max(numbers, default=0) + 1}"


def _default_nozzle(
    nozzles: list[Nozzle],
    unit_kind: str,
    port: str,
    inlet: bool,
    index: int,
    nps_in: float,
    flange_class: int,
) -> Nozzle:
    """A deterministic stand-in nozzle for one sim port (units whose sizer has
    not landed): inlets on the west face, outlets on the east face, stacked in
    port order."""
    if inlet:
        position = Vec3(x=_INLET_X_MM, y=0.0, z=_PORT_PITCH_MM * (index + 1))
        facing = Direction.W
    else:
        position = Vec3(x=_OUTLET_X_MM, y=0.0, z=_PORT_PITCH_MM * (index + 1))
        facing = Direction.E
    return Nozzle(
        id=_next_nozzle_id(nozzles),
        service=_nozzle_service(unit_kind, port),
        port=port,
        nps_in=nps_in,
        flange_class=flange_class,
        position_mm=position,
        facing=facing,
    )


def _flange_class_of(pipe_class: str) -> int:
    return int(pipe_classes()[pipe_class]["flange_class"])


@dataclass(frozen=True)
class _SizedStream:
    """Everything one line needs, before its ends are attached."""

    stream: StreamSpec
    nps_in: float
    pipe_class: str
    design_pressure_Pa: float
    design_temperature_K: float
    seq: int


def _size_streams(solved: SolvedFlowsheet, conditions: dict[str, tuple[float, float]]) -> list[_SizedStream]:
    """One sized line per stream, in stream order.  A line's design P/T is the
    max over its connected equipment ends (boundary ends contribute nothing)."""
    sized: list[_SizedStream] = []
    for seq, stream in enumerate(solved.flowsheet.streams, start=FIRST_LINE_SEQ):
        state = _state_for(solved, stream.id)
        refs = (stream.source, stream.target)
        design_P = max((conditions[ref.unit][0] for ref in refs if ref is not None), default=0.0)
        design_T = max((conditions[ref.unit][1] for ref in refs if ref is not None), default=0.0)
        sized.append(
            _SizedStream(
                stream=stream,
                nps_in=_line_nps_in(state, stream.service, stream.id),
                pipe_class=_pipe_class_for(design_P, design_T, state.composition),
                design_pressure_Pa=design_P,
                design_temperature_K=design_T,
                seq=seq,
            )
        )
    return sized


def _first_composition(states: list[StreamState]) -> dict[str, float]:
    """A representative composition for one unit: the first connected
    stream's, in stream order."""
    return states[0].composition if states else {}


def _unconnected_line(conditions: tuple[float, float], states: list[StreamState]) -> tuple[float, int]:
    """Stand-in sizing for a declared port no stream connects to (nothing
    flows, so nothing sizes it): smallest line, the equipment's own flange
    class."""
    own_class = _pipe_class_for(conditions[0], conditions[1], _first_composition(states))
    return _UNCONNECTED_NPS_IN, _flange_class_of(own_class)


def _build_equipment(
    spec: UnitSpec,
    sheet: Datasheet | None,
    connections: list[tuple[StreamSpec, StreamState]],
    port_lines: dict[str, tuple[float, int]],
    conditions: tuple[float, float],
) -> PidEquipment:
    """One PidEquipment: datasheet nozzles when a sizer ran (the vessels'
    psv nozzles come from their datasheets; the sizers own them), default
    nozzles where no sizer (or an incomplete datasheet) leaves a sim port
    uncovered.  Adopted portless datasheet nozzles get their ``port`` filled
    and the conventional service label, so line ends and pid_rule lookups
    find them."""
    streams = [s for s, _ in connections]
    states = [state for _, state in connections]
    inlets, outlets = _unit_ports(spec.kind, streams)
    nozzles = [noz.model_copy(deep=True) for noz in sheet.nozzles] if sheet is not None else []

    def ensure_port(port: str, inlet: bool, index: int) -> None:
        noz = _nozzle_for_port(nozzles, spec.kind, port)
        if noz is None:
            nps, flange_class = port_lines.get(port, _unconnected_line(conditions, states))
            nozzles.append(_default_nozzle(nozzles, spec.kind, port, inlet, index, nps, flange_class))
        elif noz.port is None:
            noz.port = port
            noz.service = _nozzle_service(spec.kind, port)

    for i, port in enumerate(inlets):
        ensure_port(port, inlet=True, index=i)
    for i, port in enumerate(outlets):
        ensure_port(port, inlet=False, index=i)

    return PidEquipment(
        tag=spec.tag,
        kind=spec.kind,
        nozzles=nozzles,
        design_pressure_Pa=conditions[0],
        design_temperature_K=conditions[1],
    )


def _line_end(ref: PortRef | None, stream_id: str, equipment: dict[str, PidEquipment]) -> LineEnd:
    """A line's end: the nozzle serving the stream port, or a battery-limit
    label on feeds and products."""
    if ref is None:
        return LineEnd(boundary=f"BL-{stream_id}")
    eq = equipment[ref.unit]
    noz = _nozzle_for_port(eq.nozzles, eq.kind, ref.port)
    if noz is None:  # every connected port got a nozzle in _build_equipment
        raise ValueError(f"unit {ref.unit} has no nozzle for port {ref.port!r}")
    return LineEnd(equipment=eq.tag, nozzle=noz.id)


def _to_line(sized: _SizedStream, equipment: dict[str, PidEquipment]) -> PidLine:
    """The bare PidLine for one sized stream: no items, no valves."""
    return PidLine(
        number=_line_number(sized.nps_in, sized.stream.service, sized.seq, sized.pipe_class),
        stream_id=sized.stream.id,
        nps_in=sized.nps_in,
        fluid_code=sized.stream.service,
        pipe_class=sized.pipe_class,
        design_pressure_Pa=sized.design_pressure_Pa,
        design_temperature_K=sized.design_temperature_K,
        start=_line_end(sized.stream.source, sized.stream.id, equipment),
        end=_line_end(sized.stream.target, sized.stream.id, equipment),
        items=[],
    )


@register("pid_builder", "default")
class DefaultPidBuilder:
    """Bare P&ID from a solved flowsheet (spec S-33): equipment, nozzles and
    numbered lines; the pid_rule plugins add valves and instruments."""

    def build(self, solved: SolvedFlowsheet) -> PID:
        fs = solved.flowsheet
        connections = _connections(solved)

        sheets: dict[str, Datasheet | None] = {}
        conditions: dict[str, tuple[float, float]] = {}
        for spec in fs.units:
            sheets[spec.tag] = _datasheet_for(solved, spec)
            states = [state for _, state in connections[spec.tag]]
            conditions[spec.tag] = _design_conditions(sheets[spec.tag], states, spec.tag)

        sized = _size_streams(solved, conditions)

        # Per-port line facts for the nozzle tables: a nozzle matches its
        # line's NPS and flange class, so no reducer sits at the equipment.
        port_lines: dict[str, dict[str, tuple[float, int]]] = {u.tag: {} for u in fs.units}
        for s in sized:
            for ref in (s.stream.source, s.stream.target):
                if ref is not None:
                    port_lines[ref.unit][ref.port] = (s.nps_in, _flange_class_of(s.pipe_class))

        equipment = {
            spec.tag: _build_equipment(
                spec,
                sheets[spec.tag],
                connections[spec.tag],
                port_lines[spec.tag],
                conditions[spec.tag],
            )
            for spec in fs.units
        }
        return PID(
            equipment=[equipment[u.tag] for u in fs.units],
            lines=[_to_line(s, equipment) for s in sized],
            valves=[],
            instruments=[],
        )
