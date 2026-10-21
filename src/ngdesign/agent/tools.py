"""Typed agent tools over the in-process project (spec B-08).

Every tool is the same operation an HTTP route performs — nothing here runs
anything the API cannot already do — validated through the pydantic contracts
and stored with ``store.put``. The LLM never sees secrets or the filesystem:
tools receive the injected :class:`ProjectStore` and :class:`Engine` and return
JSON-serialisable dicts.

Errors are returned, never raised: a handler raises ValueError/KeyError with a
message that tells the model how to fix its own mistake, and :func:`run_tool`
catches it into ``ToolOutcome(ok=False, error=...)``. Validation errors from the
contracts (duplicate tags, unknown ports, bad compositions, slate membership)
surface exactly the same way.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from ngdesign import data as ngdata
from ngdesign import pipeline, registry
from ngdesign.agent import addresses
from ngdesign.agent.engine import DEFAULT_ENGINE, Engine, rebuild_flowsheet
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, Project, StreamSpec, UnitSpec
from ngdesign.contracts.plugins import UnitModel
from ngdesign.study import Axis, CaseStudy, StudyResult
from ngdesign.study import run as run_study


class ProjectStore(Protocol):
    """The API owns the project state; the loop injects this seam."""

    def get(self) -> Project: ...
    def put(self, project: Project) -> Project: ...


@dataclass(frozen=True)
class ToolSpec:
    """One typed tool.

    ``input_schema`` is JSON Schema with ``additionalProperties: false`` and
    every property in ``required`` — the Anthropic strict-tool requirements;
    ``tool_definitions`` marks each spec ``strict: True`` when rendering the API
    ``tools`` list. ``mutates`` marks the tools that ``store.put`` (the loop
    emits ``project_changed`` after a successful one).
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    mutates: bool = False


@dataclass(frozen=True)
class ToolOutcome:
    """Result of one tool run: ok with a result dict, or not ok with error text."""

    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    """Strict-tool input schema: object, additionalProperties false, every property required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# --- read-only tools ---------------------------------------------------------


def _get_project(store: ProjectStore, engine: Engine) -> dict[str, Any]:
    return store.get().model_dump(mode="json")


def _list_unit_kinds(store: ProjectStore, engine: Engine) -> dict[str, Any]:
    kinds: dict[str, Any] = {}
    for name in registry.available("unit"):
        # Every registered unit implements the locked UnitModel protocol.
        cls = cast("type[UnitModel]", registry.get("unit", name))
        _, example_params = cls.example_case()
        kinds[name] = {
            "inlet_ports": list(cls.inlet_ports),
            "outlet_ports": list(cls.outlet_ports),
            "params": example_params,  # the params each unit documents via its example_case
        }
    return {"kinds": kinds}


def _list_components(store: ProjectStore, engine: Engine) -> dict[str, Any]:
    fs = store.get().flowsheet
    return {"components": sorted(set(ngdata.components()) | set(fs.components))}


# --- mutating tools ----------------------------------------------------------


def _put(store: ProjectStore, fs: Flowsheet) -> Project:
    """Store the project over ``fs`` (pydantic validates; see rebuild_flowsheet)."""
    current = store.get()
    return store.put(Project(name=current.name, flowsheet=fs, layout=current.layout))


def _unit_spec(fs: Flowsheet, tag: str) -> UnitSpec:
    for spec in fs.units:
        if spec.tag == tag:
            return spec
    raise ValueError(f"unknown unit {tag!r}; have {sorted(u.tag for u in fs.units)}")


def _check_port(kind: str, tag: str, port: str, inlet: bool) -> None:
    """Port names are declared by the unit plugin; catch mistakes before solving."""
    cls = cast("type[UnitModel]", registry.get("unit", kind))  # locked protocol surface
    valid = cls.inlet_ports if inlet else cls.outlet_ports
    if port not in valid:
        role = "inlet" if inlet else "outlet"
        raise ValueError(f"unit {tag} ({kind}) has no {role} port {port!r}; have {list(valid)}")


def _add_unit(
    store: ProjectStore, engine: Engine, *, tag: str, kind: str, params: dict[str, Any]
) -> dict[str, Any]:
    fs = store.get().flowsheet
    if kind not in registry.available("unit"):
        raise ValueError(f"unknown unit kind {kind!r}; call list_unit_kinds for the registered kinds")
    new_fs = rebuild_flowsheet(fs, units=[*fs.units, UnitSpec(tag=tag, kind=kind, params=params)])
    _put(store, new_fs)
    return {"added": tag, "kind": kind, "units": sorted(u.tag for u in new_fs.units)}


def _remove_unit(store: ProjectStore, engine: Engine, *, tag: str) -> dict[str, Any]:
    fs = store.get().flowsheet
    _unit_spec(fs, tag)
    units = [u for u in fs.units if u.tag != tag]
    kept = [
        s
        for s in fs.streams
        if not ((s.source and s.source.unit == tag) or (s.target and s.target.unit == tag))
    ]
    dropped = sorted(set(s.id for s in fs.streams) - set(s.id for s in kept))
    new_fs = rebuild_flowsheet(fs, units=units, streams=kept)
    _put(store, new_fs)
    return {"removed": tag, "dropped_streams": dropped}


def _set_params(store: ProjectStore, engine: Engine, *, tag: str, params: dict[str, Any]) -> dict[str, Any]:
    fs = store.get().flowsheet
    spec = _unit_spec(fs, tag)
    merged = {**spec.params, **params}
    units = [UnitSpec(tag=tag, kind=spec.kind, params=merged) if u.tag == tag else u for u in fs.units]
    _put(store, rebuild_flowsheet(fs, units=units))
    return {"tag": tag, "params": merged}


def _add_feed(
    store: ProjectStore,
    engine: Engine,
    *,
    stream_id: str,
    target_unit: str,
    target_port: str,
    T_K: float,
    P_Pa: float,
    molar_flow_mol_s: float,
    composition: dict[str, float],
    service: str | None = None,
) -> dict[str, Any]:
    fs = store.get().flowsheet
    target = _unit_spec(fs, target_unit)
    _check_port(target.kind, target_unit, target_port, inlet=True)
    spec_kwargs: dict[str, Any] = {
        "id": stream_id,
        "target": PortRef(unit=target_unit, port=target_port),
        "feed": FeedSpec(T=T_K, P=P_Pa, molar_flow=molar_flow_mol_s, composition=composition),
    }
    if service is not None:
        spec_kwargs["service"] = service
    stream = StreamSpec(**spec_kwargs)
    new_fs = rebuild_flowsheet(fs, streams=[*fs.streams, stream])
    _put(store, new_fs)
    return {"added": stream_id, "to": f"{target_unit}.{target_port}"}


def _connect(
    store: ProjectStore,
    engine: Engine,
    *,
    stream_id: str,
    source_unit: str,
    source_port: str,
    target_unit: str | None = None,
    target_port: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    """Connect source.port to target.port; null target args for a product stream."""
    fs = store.get().flowsheet
    source = _unit_spec(fs, source_unit)
    _check_port(source.kind, source_unit, source_port, inlet=False)
    if (target_unit is None) != (target_port is None):
        raise ValueError("target_unit and target_port must be given together (or both null for a product)")
    spec_kwargs: dict[str, Any] = {
        "id": stream_id,
        "source": PortRef(unit=source_unit, port=source_port),
    }
    if service is not None:
        spec_kwargs["service"] = service
    to = "product (battery limit)"
    if target_unit is not None and target_port is not None:
        target = _unit_spec(fs, target_unit)
        _check_port(target.kind, target_unit, target_port, inlet=True)
        spec_kwargs["target"] = PortRef(unit=target_unit, port=target_port)
        to = f"{target_unit}.{target_port}"
    stream = StreamSpec(**spec_kwargs)
    new_fs = rebuild_flowsheet(fs, streams=[*fs.streams, stream])
    _put(store, new_fs)
    return {"added": stream_id, "from": f"{source_unit}.{source_port}", "to": to}


def _disconnect(store: ProjectStore, engine: Engine, *, stream_id: str) -> dict[str, Any]:
    fs = store.get().flowsheet
    if stream_id not in {s.id for s in fs.streams}:
        raise ValueError(f"unknown stream {stream_id!r}; have {sorted(s.id for s in fs.streams)}")
    _put(store, rebuild_flowsheet(fs, streams=[s for s in fs.streams if s.id != stream_id]))
    return {"disconnected": stream_id}


def _set_thermo(store: ProjectStore, engine: Engine, *, name: str) -> dict[str, Any]:
    known = registry.available("thermo")
    if name not in known:
        raise ValueError(f"thermo model {name!r} has no registered plugin; have {known}")
    fs = store.get().flowsheet
    _put(
        store,
        Flowsheet(name=fs.name, units=fs.units, streams=fs.streams, thermo=name, components=fs.components),
    )
    return {"thermo": name}


# --- solve / read tools ------------------------------------------------------


def _solve(store: ProjectStore, engine: Engine) -> dict[str, Any]:
    solved = engine.solve_project(store.get())
    return {
        "converged": solved.converged,
        "iterations": solved.iterations,
        "units": {
            tag: {"duty_W": result.duty_W, "power_W": result.power_W, "info": result.info}
            for tag, result in solved.units.items()
        },
        "streams": {
            sid: {"T": st.T, "P": st.P, "molar_flow": st.molar_flow, "vapor_fraction": st.vapor_fraction}
            for sid, st in solved.streams.items()
        },
    }


def _read_stream(store: ProjectStore, engine: Engine, *, stream_id: str) -> dict[str, Any]:
    solved = engine.solve_project(store.get())
    if stream_id not in solved.streams:
        raise ValueError(f"unknown stream {stream_id!r}; have {sorted(solved.streams)}")
    return {"id": stream_id, "state": solved.streams[stream_id].model_dump(mode="json")}


def _read_unit(store: ProjectStore, engine: Engine, *, tag: str) -> dict[str, Any]:
    solved = engine.solve_project(store.get())
    if tag not in solved.units:
        raise ValueError(f"unknown unit {tag!r}; have {sorted(solved.units)}")
    result = solved.units[tag]
    return {
        "tag": tag,
        "duty_W": result.duty_W,
        "power_W": result.power_W,
        "info": result.info,
        "outlets": {port: st.model_dump(mode="json") for port, st in result.outlets.items()},
    }


def _read_variable(store: ProjectStore, engine: Engine, *, address: str) -> dict[str, Any]:
    solved = engine.solve_project(store.get())
    return {"address": address, "value": addresses.resolve(address, solved)}


def _case_study(
    store: ProjectStore,
    engine: Engine,
    *,
    address: str,
    values: list[float],
    outputs: list[str],
) -> dict[str, Any]:
    """Sweep a write address over ``values``; one solved row per value.

    The sweep runs on copies — the stored project is unchanged. Spec P2-04
    re-pointed this tool at :func:`ngdesign.study.run` (the same runner the
    CLI and POST /api/study use); the B-08 output shape and error behaviour
    are kept: when every case failed (a P2-02 failed solve or an address the
    contracts rejected), the reasons come back as this tool's error outcome
    so the model can fix its own mistake.
    """
    project = store.get()
    study = CaseStudy(
        id="agent",
        inputs=[Axis(address=address, values=[float(v) for v in values])],
        outputs=list(outputs),
        base=project.flowsheet,
    )
    thermo = registry.create("thermo", project.flowsheet.thermo)
    result: StudyResult = run_study(study, thermo)
    if result.failed and len(result.failed) == len(result.rows):
        why = "; ".join(
            f"{address}={row.inputs[address]}: "
            + (row.message or (row.errors[0].message if row.errors else "the solve did not converge"))
            for row in result.failed
        )
        raise ValueError(why)
    rows = [{"value": row.inputs[address], **row.outputs} for row in result.rows]
    return {"address": address, "outputs": list(outputs), "rows": rows}


def _render(store: ProjectStore, engine: Engine, *, view: str) -> dict[str, Any]:
    project = store.get()
    solved = engine.solve_project(project)
    layout = project.layout.pfd if view == "pfd" else project.layout.pid
    engine.render_view(solved, layout, view)  # proves the view renders with the stored placements
    pid = pipeline.build_pid(solved.model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
    return {
        "url": f"/api/views/{view}.svg",
        "units": len(pid.equipment),
        "lines": len(pid.lines),
        "instruments": len(pid.instruments),
    }


#: The tool registry (spec B-08). Order is fixed: byte-stable prompt caching.
TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "get_project",
        "Read the full current project: flowsheet units (tag, kind, params), streams "
        "(id, source, target, feed), thermo selection and stored view placements.",
        _schema({}),
        _get_project,
    ),
    ToolSpec(
        "list_unit_kinds",
        "Every registered unit kind with its inlet/outlet port names and the params "
        "documented by each unit's example_case. Call this before adding a unit kind "
        "you have not seen in this session.",
        _schema({}),
        _list_unit_kinds,
    ),
    ToolSpec(
        "list_components",
        "Every component id resolvable today: the curated slate plus this flowsheet's "
        "component slate. Feed compositions may only use these ids.",
        _schema({}),
        _list_components,
    ),
    ToolSpec(
        "add_unit",
        "Add one unit operation by tag (like 'K-201') and registered kind, with its "
        "params (see list_unit_kinds). Invalid tags, unknown kinds or duplicate tags "
        "come back as errors.",
        _schema(
            {
                "tag": {"type": "string"},
                "kind": {"type": "string"},
                "params": {"type": "object", "description": "unit params; {} for defaults"},
            }
        ),
        _add_unit,
        mutates=True,
    ),
    ToolSpec(
        "add_feed",
        "Add a boundary feed stream into a unit's inlet port. SI units: T_K in "
        "kelvin, P_Pa in pascal absolute, molar_flow_mol_s in mol/s, composition in "
        "mole fractions summing to 1 (ids from list_components). service is the "
        "fluid code for line sizing and the P&ID (PG process gas, PL process "
        "liquid, W water, GL glycol); null leaves the contract default.",
        _schema(
            {
                "stream_id": {"type": "string"},
                "target_unit": {"type": "string"},
                "target_port": {"type": "string"},
                "T_K": {"type": "number"},
                "P_Pa": {"type": "number"},
                "molar_flow_mol_s": {"type": "number"},
                "composition": {"type": "object"},
                "service": {"type": ["string", "null"], "description": "PG | PL | W | GL"},
            }
        ),
        _add_feed,
        mutates=True,
    ),
    ToolSpec(
        "connect",
        "Add a stream from a unit's outlet port to a unit's inlet port. Give "
        "target_unit and target_port as null for a product stream leaving the "
        "battery limit. service is the fluid code for line sizing and the P&ID "
        "(PG process gas, PL process liquid, W water, GL glycol); null leaves "
        "the contract default.",
        _schema(
            {
                "stream_id": {"type": "string"},
                "source_unit": {"type": "string"},
                "source_port": {"type": "string"},
                "target_unit": {"type": ["string", "null"]},
                "target_port": {"type": ["string", "null"]},
                "service": {"type": ["string", "null"], "description": "PG | PL | W | GL"},
            }
        ),
        _connect,
        mutates=True,
    ),
    ToolSpec(
        "set_params",
        "Merge params into one unit's params (given keys are overwritten, others kept).",
        _schema({"tag": {"type": "string"}, "params": {"type": "object"}}),
        _set_params,
        mutates=True,
    ),
    ToolSpec(
        "remove_unit",
        "Remove a unit and any streams connected to it (they are dropped with it).",
        _schema({"tag": {"type": "string"}}),
        _remove_unit,
        mutates=True,
    ),
    ToolSpec(
        "disconnect",
        "Remove one stream (by id) from the flowsheet.",
        _schema({"stream_id": {"type": "string"}}),
        _disconnect,
        mutates=True,
    ),
    ToolSpec(
        "set_thermo",
        "Select the thermodynamic property package by registered plugin name; an "
        "unknown name returns an error listing the registered packages.",
        _schema({"name": {"type": "string"}}),
        _set_thermo,
        mutates=True,
    ),
    ToolSpec(
        "solve",
        "Solve the current project (sequential modular, the project's thermo "
        "selection). Returns convergence, per-unit duty/power/info and per-stream "
        "T/P/molar_flow/vapor_fraction. Call after every topology change, before "
        "reading results or rendering.",
        _schema({}),
        _solve,
    ),
    ToolSpec(
        "read_stream",
        "Full solved state of one stream by id: T, P, molar_flow, composition and "
        "phase split. Solves first if the project changed.",
        _schema({"stream_id": {"type": "string"}}),
        _read_stream,
    ),
    ToolSpec(
        "read_unit",
        "Full solved result of one unit by tag: duty_W, power_W, info and each "
        "outlet port's full stream state.",
        _schema({"tag": {"type": "string"}}),
        _read_unit,
    ),
    ToolSpec(
        "read_variable",
        "Read one variable by address: '<stream>.<T|P|molar_flow|mass_flow|"
        "vapor_fraction>', '<stream>.x.<component_id>' (mole fraction), or "
        "'<unit>.<duty_W|power_W|info.<key>>'. Unknown addresses come back with "
        "the nearest valid ones.",
        _schema({"address": {"type": "string"}}),
        _read_variable,
    ),
    ToolSpec(
        "case_study",
        "Sweep a writable address ('<unit>.params.<key>' or '<feed>.feed.<T|P|"
        "molar_flow>') over values and solve each case; one row per value with "
        "every requested output address. The stored project is unchanged.",
        _schema(
            {
                "address": {"type": "string"},
                "values": {"type": "array", "items": {"type": "number"}},
                "outputs": {"type": "array", "items": {"type": "string"}},
            }
        ),
        _case_study,
    ),
    ToolSpec(
        "render",
        "Render a view of the solved project and return its URL plus the P&ID "
        "counts (equipment, lines, instruments). view is 'pfd' or 'pid'; fetch "
        "the URL for the drawing.",
        _schema({"view": {"type": "string", "enum": ["pfd", "pid"]}}),
        _render,
    ),
)

TOOLS_BY_NAME: dict[str, ToolSpec] = {tool.name: tool for tool in TOOLS}


def tool_definitions() -> list[dict[str, Any]]:
    """The API ``tools`` list: every spec strict; the last definition carries the
    prompt-cache marker. Byte-stable per process (no timestamps)."""
    defs: list[dict[str, Any]] = [
        {
            "name": tool.name,
            "description": tool.description,
            "strict": True,
            "input_schema": tool.input_schema,
        }
        for tool in TOOLS
    ]
    defs[-1]["cache_control"] = {"type": "ephemeral"}
    return defs


def run_tool(
    name: str, tool_input: dict[str, Any], store: ProjectStore, engine: Engine = DEFAULT_ENGINE
) -> ToolOutcome:
    """Run one tool by name; errors come back as the outcome, never raised.

    The engine defaults to the real one; the loop injects whatever the API
    passed so tests can substitute either helper.
    """
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return ToolOutcome(ok=False, error=f"unknown tool {name!r}; have {sorted(TOOLS_BY_NAME)}")
    try:
        result = spec.handler(store, engine, **tool_input)
    except (ValueError, KeyError) as exc:
        # The contracts' own validation channel: the model fixes its mistakes.
        return ToolOutcome(ok=False, error=str(exc))
    except TypeError as exc:
        return ToolOutcome(ok=False, error=f"bad input for tool {name!r}: {exc}")
    return ToolOutcome(ok=True, result=result)
