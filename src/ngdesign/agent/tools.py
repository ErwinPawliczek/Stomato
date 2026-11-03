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
from typing import Any, cast

from ngdesign import data as ngdata
from ngdesign import pipeline, registry
from ngdesign.agent import addresses, service
from ngdesign.agent.engine import DEFAULT_ENGINE, Engine
from ngdesign.agent.service import ProjectService, ProjectStore
from ngdesign.contracts.plugins import UnitModel
from ngdesign.study import Axis, CaseStudy, StudyResult
from ngdesign.study import run as run_study


@dataclass(frozen=True)
class ToolSpec:
    """One typed tool.

    ``input_schema`` is JSON Schema with ``additionalProperties: false`` and
    every property in ``required`` — the Anthropic strict-tool requirements;
    ``tool_definitions`` marks each spec ``strict: True`` when rendering the API
    ``tools`` list. ``mutates`` marks the tools that commit a project change
    (the loop emits ``project_changed`` after a successful one). The handler
    receives the :class:`ProjectService` bound to the caller's store, engine
    and actor — the same operations the REST API v1 runs.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    mutates: bool = False


@dataclass(frozen=True)
class ToolOutcome:
    """Result of one tool run: ok with a result dict, or not ok with error text.

    ``change`` is the committed change (seq, summary, structured diff) when a
    mutating tool changed the project; ``code`` the stable error code.
    """

    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    code: str | None = None
    change: dict[str, Any] | None = None

    def payload(self) -> dict[str, Any]:
        """The JSON a non-Anthropic surface returns (MCP, REST tool runner)."""
        if not self.ok:
            return {"error": self.error, "code": self.code}
        out = dict(self.result or {})
        if self.change is not None:
            out["change"] = self.change
        return out


def _schema(properties: dict[str, Any]) -> dict[str, Any]:
    """Strict-tool input schema: object, additionalProperties false, every property required."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    """``schema`` or null (strict tools mark optional inputs nullable, never absent)."""
    return {"anyOf": [schema, {"type": "null"}]}


_XY = _schema({"x": {"type": "number"}, "y": {"type": "number"}})
_GRID = _schema({"q": {"type": "integer"}, "r": {"type": "integer"}})
_VIEW = {"type": ["string", "null"], "enum": ["pfd", "pid", None], "description": "pfd (default) | pid"}


# --- read-only tools ---------------------------------------------------------


def _get_project(svc: ProjectService) -> dict[str, Any]:
    return svc.project().model_dump(mode="json")


def _list_unit_kinds(svc: ProjectService) -> dict[str, Any]:
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


def _list_components(svc: ProjectService) -> dict[str, Any]:
    fs = svc.project().flowsheet
    return {"components": sorted(set(ngdata.components()) | set(fs.components))}


def _list_catalogue(svc: ProjectService, *, section: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if section in ("units", "all"):
        out["units"] = service.unit_catalogue()
    if section in ("components", "all"):
        out["components"] = service.component_catalogue()
    if section in ("thermo", "all"):
        out["thermo"] = service.thermo_catalogue()
    if not out:
        raise service.OpError("bad_section", "section must be one of units, components, thermo, all")
    return out


def _describe_unit_kind(svc: ProjectService, *, kind: str) -> dict[str, Any]:
    return service.unit_kind(kind)


# --- mutating tools (B-08 names and shapes) ------------------------------------


def _add_unit(svc: ProjectService, *, tag: str, kind: str, params: dict[str, Any]) -> dict[str, Any]:
    return svc.place_unit(kind=kind, tag=tag, params=params)


def _remove_unit(svc: ProjectService, *, tag: str) -> dict[str, Any]:
    return svc.delete_unit(tag)


def _set_params(svc: ProjectService, *, tag: str, params: dict[str, Any]) -> dict[str, Any]:
    return svc.configure_unit(tag, params)


def _add_feed(
    svc: ProjectService,
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
    return svc.add_feed(
        target_unit,
        target_port,
        T_K,
        P_Pa,
        molar_flow_mol_s,
        composition,
        stream_id=stream_id,
        service=service,
    )


def _connect(
    svc: ProjectService,
    *,
    stream_id: str,
    source_unit: str,
    source_port: str,
    target_unit: str | None = None,
    target_port: str | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    """Connect source.port to target.port; null target args for a product stream."""
    return svc.connect(
        source_unit, source_port, target_unit, target_port, stream_id=stream_id, service=service
    )


def _disconnect(svc: ProjectService, *, stream_id: str) -> dict[str, Any]:
    return svc.delete_stream(stream_id)


def _set_thermo(svc: ProjectService, *, name: str) -> dict[str, Any]:
    return svc.set_thermo(name)


def _recommend_thermo(svc: ProjectService) -> dict[str, Any]:
    """Ranked property-method recommendations for the current flowsheet (spec T-08)."""
    return svc.recommend_thermo()


# --- solve / read tools ------------------------------------------------------


def _solve(svc: ProjectService) -> dict[str, Any]:
    full = svc.results()
    return {k: full[k] for k in ("converged", "iterations", "units", "streams")}


def _read_stream(svc: ProjectService, *, stream_id: str) -> dict[str, Any]:
    return svc.stream_result(stream_id)


def _read_unit(svc: ProjectService, *, tag: str) -> dict[str, Any]:
    return svc.unit_result(tag)


def _read_variable(svc: ProjectService, *, address: str) -> dict[str, Any]:
    solved = svc.solved()
    return {"address": address, "value": addresses.resolve(address, solved)}


def _case_study(
    svc: ProjectService,
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
    project = svc.project()
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


def _render(svc: ProjectService, *, view: str) -> dict[str, Any]:
    project = svc.project()
    solved = svc.solved()
    layout = project.layout.pfd if view == "pfd" else project.layout.pid
    svc.engine.render_view(solved, layout, view)  # proves the view renders with the stored placements
    pid = pipeline.build_pid(solved.model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
    return {
        "url": f"/api/views/{view}.svg",
        "units": len(pid.equipment),
        "lines": len(pid.lines),
        "instruments": len(pid.instruments),
    }


# --- agentic-layer tools (docs/agentic-layer.md section 5) ----------------------


def _place_unit(
    svc: ProjectService,
    *,
    kind: str,
    tag: str | None,
    params: dict[str, Any] | None,
    position: dict[str, Any] | None,
    grid: dict[str, Any] | None,
    view: str | None,
) -> dict[str, Any]:
    return svc.place_unit(kind=kind, tag=tag, params=params, position=position, grid=grid, view=view)


def _move_unit(
    svc: ProjectService,
    *,
    tag: str,
    position: dict[str, Any] | None,
    grid: dict[str, Any] | None,
    view: str | None,
) -> dict[str, Any]:
    return svc.move_unit(tag, position=position, grid=grid, view=view)


def _configure_unit(
    svc: ProjectService, *, tag: str, params: dict[str, Any], replace: bool
) -> dict[str, Any]:
    return svc.configure_unit(tag, params, replace=replace)


def _update_stream(
    svc: ProjectService, *, stream_id: str, service: str | None, feed: dict[str, Any] | None
) -> dict[str, Any]:
    return svc.update_stream(stream_id, service=service, feed=feed)


def _set_components(svc: ProjectService, *, components: list[str]) -> dict[str, Any]:
    return svc.set_components(components)


def _list_cells(svc: ProjectService) -> dict[str, Any]:
    return svc.cells()


def _set_cell(svc: ProjectService, *, address: str, value: Any, unit: str | None) -> dict[str, Any]:
    return svc.set_cell(address, value, unit)


def _add_design_spec(
    svc: ProjectService,
    *,
    id: str,
    target: str,
    value: float,
    manipulated: str,
    lower: float,
    upper: float,
    tolerance: float | None,
) -> dict[str, Any]:
    return svc.add_design_spec(
        {
            "id": id,
            "target": target,
            "value": value,
            "manipulated": manipulated,
            "lower": lower,
            "upper": upper,
            "tolerance": tolerance,
        }
    )


def _remove_design_spec(svc: ProjectService, *, id: str) -> dict[str, Any]:
    return svc.delete_design_spec(id)


def _read_results(svc: ProjectService, *, address: str | None, unit: str | None) -> dict[str, Any]:
    if address is None:
        if unit is not None:
            raise service.OpError("invalid_value", "unit needs an address")
        return svc.results()
    return svc.read(address, unit)


def _explain_value(svc: ProjectService, *, address: str) -> dict[str, Any]:
    return svc.explain(address)


def _undo(svc: ProjectService) -> dict[str, Any]:
    return svc.undo()


def _redo(svc: ProjectService) -> dict[str, Any]:
    return svc.redo()


def _list_changes(svc: ProjectService, *, after: int | None, limit: int | None) -> dict[str, Any]:
    # No 'after': the latest changes (an agent asks "what changed recently").
    return svc.changes(after=after or 0, limit=limit or 20, newest=after is None)


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
        "recommend_thermo",
        "Rank the registered thermo property methods for the CURRENT flowsheet: "
        "component slate, feed conditions and expected phases, with the rule reasons "
        "(Carlson 1996, GPSA, Kohl & Nielsen, Prausnitz) and warnings (missing binary "
        "parameters, free water, provisional status) for each. Call this before "
        "set_thermo; experimental rows never rank.",
        _schema({}),
        _recommend_thermo,
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
    # --- agentic layer (docs/agentic-layer.md section 5); appended so the B-08
    # prefix stays byte-stable for prompt caching.
    ToolSpec(
        "list_catalogue",
        "The catalogue: 'units' (every unit kind in palette order with family, ports and "
        "whether a model is registered), 'components' (curated component ids with name, "
        "CAS, molar mass g/mol), 'thermo' (property packages with status and whether "
        "selectable), or 'all'.",
        _schema({"section": {"type": "string", "enum": ["units", "components", "thermo", "all"]}}),
        _list_catalogue,
    ),
    ToolSpec(
        "describe_unit_kind",
        "One unit kind in full: port descriptions, rigour levels with each level's param "
        "JSON schema (descriptions carry the units, e.g. 'outlet pressure, Pa'), references "
        "and the example params of a registered kind. Call before configuring a new kind.",
        _schema({"kind": {"type": "string"}}),
        _describe_unit_kind,
    ),
    ToolSpec(
        "place_unit",
        "Place a unit from the catalogue. tag null picks the next free tag from the P&ID "
        "symbol (e.g. V-102). params null means {}. Position it with position {x, y} "
        "(PFD layout units) or grid {q, r} (the flowsheet canvas's hex cell; neighbours "
        "of (q, r) are (q±1, r), (q, r±1), (q+1, r-1), (q-1, r+1)), or both null to let "
        "auto-layout place it. view is pfd (default) or pid. Undoable.",
        _schema(
            {
                "kind": {"type": "string"},
                "tag": {"type": ["string", "null"]},
                "params": _nullable({"type": "object"}),
                "position": _nullable(_XY),
                "grid": _nullable(_GRID),
                "view": _VIEW,
            }
        ),
        _place_unit,
        mutates=True,
    ),
    ToolSpec(
        "move_unit",
        "Move a placed unit: position {x, y} or grid {q, r} (exactly one), in view pfd "
        "(default) or pid. Undoable.",
        _schema(
            {
                "tag": {"type": "string"},
                "position": _nullable(_XY),
                "grid": _nullable(_GRID),
                "view": _VIEW,
            }
        ),
        _move_unit,
        mutates=True,
    ),
    ToolSpec(
        "configure_unit",
        "Set a unit's params: merged into the existing params, or replacing them all when "
        "replace is true. Values in the units the kind's param schema declares (SI). Undoable.",
        _schema({"tag": {"type": "string"}, "params": {"type": "object"}, "replace": {"type": "boolean"}}),
        _configure_unit,
        mutates=True,
    ),
    ToolSpec(
        "update_stream",
        "Change a stream's service code (PG, PL, W, GL) and/or, for feed streams, feed "
        "fields T (K), P (Pa abs), molar_flow (mol/s), composition (mole fractions "
        "summing to 1). Null leaves a field unchanged. Undoable.",
        _schema(
            {
                "stream_id": {"type": "string"},
                "service": {"type": ["string", "null"]},
                "feed": _nullable(
                    _schema(
                        {
                            "T": {"type": ["number", "null"]},
                            "P": {"type": ["number", "null"]},
                            "molar_flow": {"type": ["number", "null"]},
                            "composition": _nullable({"type": "object"}),
                        }
                    )
                ),
            }
        ),
        _update_stream,
        mutates=True,
    ),
    ToolSpec(
        "set_components",
        "Set the flowsheet's component slate (ids from list_catalogue components). Feed "
        "compositions must stay within it. Undoable.",
        _schema({"components": {"type": "array", "items": {"type": "string"}}}),
        _set_components,
        mutates=True,
    ),
    ToolSpec(
        "list_cells",
        "Every writable variable (cell) of the project: address, current value, its "
        "declared unit and description — unit params '<tag>.params.<key>', feed fields "
        "'<feed>.feed.<T|P|molar_flow>' and '<feed>.feed.composition.<cid>'.",
        _schema({}),
        _list_cells,
    ),
    ToolSpec(
        "set_cell",
        "Set one writable variable by address. value is a number with an optional unit "
        "(e.g. 25 with 'degC', 50 with 'bar', 100 with 'kmol/h' — converted to the "
        "cell's declared unit and dimension-checked; null unit means the declared unit), "
        "or a string/boolean for non-numeric unit params. Setting one feed mole fraction "
        "rescales the others. Undoable.",
        _schema(
            {
                "address": {"type": "string"},
                "value": {"type": ["number", "string", "boolean"]},
                "unit": {"type": ["string", "null"]},
            }
        ),
        _set_cell,
        mutates=True,
    ),
    ToolSpec(
        "add_design_spec",
        "Add a design spec: drive the readable address target to value by manipulating "
        "the writable address manipulated within [lower, upper] (SI); tolerance is "
        "relative on the target (null: 1e-4). Undoable.",
        _schema(
            {
                "id": {"type": "string"},
                "target": {"type": "string"},
                "value": {"type": "number"},
                "manipulated": {"type": "string"},
                "lower": {"type": "number"},
                "upper": {"type": "number"},
                "tolerance": {"type": ["number", "null"]},
            }
        ),
        _add_design_spec,
        mutates=True,
    ),
    ToolSpec(
        "remove_design_spec",
        "Remove a design spec by id. Undoable.",
        _schema({"id": {"type": "string"}}),
        _remove_design_spec,
        mutates=True,
    ),
    ToolSpec(
        "read_results",
        "Solved results (solves first if the project changed). address null: the full "
        "summary — status, diagnostics, design-spec results, per-unit and per-stream "
        "values (SI). With an address ('<stream>.T', '<unit>.power_W', ...): that value, "
        "converted to unit when given (e.g. 'degC', 'bar', 'kW', 'kmol/h').",
        _schema({"address": {"type": ["string", "null"]}, "unit": {"type": ["string", "null"]}}),
        _read_results,
    ),
    ToolSpec(
        "explain_value",
        "Explain how a solved value was computed from the calculation trace: each method "
        "with its literature reference, and the inputs and data it rests on with their "
        "sources (uncited data is flagged). address like 'S-003.T', 'S-003.x.CO2', "
        "'K-101.power_W', 'S-003.vapor.density'.",
        _schema({"address": {"type": "string"}}),
        _explain_value,
    ),
    ToolSpec(
        "undo",
        "Undo the most recent project change (any actor's: agent, UI or API).",
        _schema({}),
        _undo,
        mutates=True,
    ),
    ToolSpec(
        "redo",
        "Redo the most recently undone change (a new edit clears the redo history).",
        _schema({}),
        _redo,
        mutates=True,
    ),
    ToolSpec(
        "list_changes",
        "The project's change history, oldest first: seq, actor, summary and the "
        "structured diff of each change after seq 'after' (null: the latest ones), at most limit (null: 20).",
        _schema({"after": {"type": ["integer", "null"]}, "limit": {"type": ["integer", "null"]}}),
        _list_changes,
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
    name: str,
    tool_input: dict[str, Any],
    store: ProjectStore,
    engine: Engine = DEFAULT_ENGINE,
    *,
    actor: str = "agent",
) -> ToolOutcome:
    """Run one tool by name; errors come back as the outcome, never raised.

    The engine defaults to the real one; the loop injects whatever the API
    passed so tests can substitute either helper. ``actor`` attributes the
    change a mutating tool commits (``agent:<conversation>``, ``mcp``, ``api``).
    """
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        return ToolOutcome(
            ok=False, error=f"unknown tool {name!r}; have {sorted(TOOLS_BY_NAME)}", code="unknown_tool"
        )
    svc = ProjectService(store, engine, actor=actor)
    try:
        result = spec.handler(svc, **tool_input)
    except service.OpError as exc:
        return ToolOutcome(ok=False, error=exc.message, code=exc.code)
    except (ValueError, KeyError) as exc:
        # The contracts' own validation channel: the model fixes its mistakes.
        return ToolOutcome(ok=False, error=str(exc), code="invalid")
    except TypeError as exc:
        return ToolOutcome(ok=False, error=f"bad input for tool {name!r}: {exc}", code="bad_input")
    return ToolOutcome(ok=True, result=result, change=svc.last_change if spec.mutates else None)


__all__ = [
    "TOOLS",
    "TOOLS_BY_NAME",
    "ProjectStore",
    "ToolOutcome",
    "ToolSpec",
    "run_tool",
    "tool_definitions",
]
