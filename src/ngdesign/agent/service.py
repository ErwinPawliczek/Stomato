"""Project operations: the one implementation behind every agentic surface
(docs/agentic-layer.md section 2).

The REST API v1, the agent tools (in-app agent and MCP server) all call
:class:`ProjectService`. A mutating operation builds the new
:class:`~ngdesign.contracts.Project` through the pydantic contracts and commits
it through the store's change log, so every edit is an undoable, attributed
change with a structured diff. Failed validation never writes.

Errors are :class:`OpError` with a stable ``code``, an HTTP ``status`` and a
message that tells the caller how to fix the input (nearest valid names).
``OpError`` is a ``ValueError``: code paths that predate it (the B-08
``run_tool`` channel) keep catching it unchanged.

Units at the edge: :meth:`ProjectService.set_cell` and :meth:`ProjectService.read`
accept unit strings parsed by :mod:`ngdesign.uom`. A cell's declared unit comes
from the contracts (feed fields are K, Pa, mol/s) or from the unit catalogue's
own param description (``'outlet pressure, Pa'``); nothing is assumed beyond
what the data declares.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any, Protocol, cast

from ngdesign import data as ngdata
from ngdesign import registry, variables
from ngdesign.agent.diff import diff_lines, project_diff
from ngdesign.agent.engine import DEFAULT_ENGINE, Engine, InvalidProjectError, UnknownPluginError
from ngdesign.contracts import (
    XY,
    FeedSpec,
    Flowsheet,
    PortRef,
    Project,
    SolvedFlowsheet,
    StreamSpec,
    UnitSpec,
)
from ngdesign.contracts.plugins import UnitModel
from ngdesign.contracts.specs import DesignSpec
from ngdesign.thermo import advisor
from ngdesign.thermo.catalogue import load_catalogue
from ngdesign.units.catalogue import UnitRow, load_rows, units_catalogue
from ngdesign.units.levels import implemented_levels, resolve_level
from ngdesign.uom.dimension import UomError
from ngdesign.uom.quantity import Quantity
from ngdesign.uom.units import parse_unit

# --- errors -------------------------------------------------------------------


class OpError(ValueError):
    """An operation refused: stable ``code``, HTTP ``status``, fix-it ``message``."""

    def __init__(self, code: str, message: str, status: int = 422, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


def _not_found(code: str, what: str, name: str, have: list[str]) -> OpError:
    shown = ", ".join(have[:30]) + (f", ... (+{len(have) - 30} more)" if len(have) > 30 else "")
    return OpError(code, f"unknown {what} {name!r}; have [{shown}]", status=404, details={"have": have})


# --- store protocols ------------------------------------------------------------


class ProjectStore(Protocol):
    """The minimum the operations need: read and write the project body."""

    def get(self) -> Project: ...
    def put(self, project: Project) -> Project: ...


class ChangeLike(Protocol):
    """One change as a change-logging store returns it (``ngdesign.store.ChangeRecord``)."""

    seq: int
    kind: str
    op: str
    actor: str
    summary: str
    args: dict[str, Any]
    state: str
    target_seq: int | None
    version: int
    before: str
    after: str


class ChangeLog(Protocol):
    """A store that records every write (``ngdesign.store.DbProjectStore`` structurally).

    ``undo``/``redo`` raise ``LookupError`` with nothing to move and a
    ``RuntimeError`` subclass when the body moved outside the log.
    """

    def commit(
        self, project: Project, *, op: str, actor: str, summary: str, args: dict[str, Any] | None = None
    ) -> Any: ...
    def undo(self, *, actor: str) -> Any: ...
    def redo(self, *, actor: str) -> Any: ...
    def changes(self, *, after: int = 0, limit: int = 100, newest: bool = False) -> list[Any]: ...


def change_payload(change: Any) -> dict[str, Any]:
    """A change record as JSON: identity, attribution and the structured diff."""
    before = Project.model_validate_json(change.before)
    after = Project.model_validate_json(change.after)
    diff = project_diff(before, after)
    created = getattr(change, "created_at", None)
    return {
        "seq": change.seq,
        "kind": change.kind,
        "op": change.op,
        "actor": change.actor,
        "summary": change.summary,
        "state": change.state,
        "target_seq": change.target_seq,
        "version": change.version,
        "created_at": created.isoformat() if created is not None else None,
        "args": change.args,
        "diff": diff,
        "lines": diff_lines(diff),
    }


# --- catalogue (project-independent) -------------------------------------------------

_TAG_PREFIX_RE = re.compile(r"[A-Z]{1,4}")


def _unit_brief(row: UnitRow, registered: set[str]) -> dict[str, Any]:
    return {
        "kind": row.id,
        "name": row.name,
        "family": row.family,
        "registered": row.id in registered,
        "inlet_ports": list(row.ports.inlet_names),
        "outlet_ports": list(row.ports.outlet_names),
        "pid_symbol": row.pid_symbol,
    }


def unit_catalogue(*, registered_only: bool = False) -> list[dict[str, Any]]:
    """Every catalogue unit kind in palette order (family, then id)."""
    registered = set(registry.available("unit"))
    rows = units_catalogue()
    return [_unit_brief(r, registered) for r in rows if r.id in registered or not registered_only]


def unit_kind(kind: str) -> dict[str, Any]:
    """One unit kind in full: ports with descriptions, rigour levels with their
    param JSON schemas, references, and (when registered) the example params
    the unit's own ``example_case`` documents."""
    rows = load_rows()
    row = rows.get(kind)
    registered = set(registry.available("unit"))
    if row is None:
        raise _not_found("unknown_kind", "unit kind", kind, sorted(rows))
    out = _unit_brief(row, registered)
    out["ports"] = row.ports.model_dump(mode="json")
    out["levels"] = {
        name: {"status": level.status, "params": level.params, "note": level.note}
        for name, level in row.levels.items()
    }
    out["implemented_levels"] = list(implemented_levels(row))
    out["references"] = list(row.references)
    out["notes"] = row.notes
    if kind in registered:
        cls = cast("type[UnitModel]", registry.get("unit", kind))
        out["example_params"] = cls.example_case()[1]
    return out


def component_catalogue() -> list[dict[str, Any]]:
    """The curated component slate: id, name, CAS, molar mass (g/mol)."""
    comps = ngdata.components()
    return [
        {"id": cid, "name": rec.get("name"), "cas": rec.get("cas"), "mw": rec.get("mw")}
        for cid, rec in sorted(comps.items())
    ]


def thermo_catalogue() -> list[dict[str, Any]]:
    """Every thermo catalogue row with its selectable flag and refusal reason
    (issue #154) and whether a plugin is registered under its id."""
    registered = set(registry.available("thermo"))
    models: list[dict[str, Any]] = []
    rows = load_catalogue()
    for row_id in sorted(rows):
        row = rows[row_id]
        selectable = row.status != "experimental"
        entry: dict[str, Any] = {
            "id": row.id,
            "name": row.name,
            "family": row.family,
            "status": row.status,
            "selectable": selectable,
            "registered": row.id in registered,
        }
        if not selectable:
            reason = "status: experimental"
            if row.l0_note:
                reason += f" — {row.l0_note}"
            if row.references:
                reason += f" — see {row.references[0]}"
            entry["refusal_reason"] = reason
        models.append(entry)
    return models


# --- units of measure -----------------------------------------------------------------

#: Declared units of the contract fields (FeedSpec: K, Pa abs, mol/s; StreamState
#: and UnitResult read fields: the SI the engine reports).
_FEED_UNITS = {"T": "K", "P": "Pa", "molar_flow": "mol/s"}
_STREAM_READ_UNITS = {
    "T": "K",
    "P": "Pa",
    "molar_flow": "mol/s",
    "mass_flow": "kg/s",
    "vapor_fraction": "1",
    "x": "1",
}
_UNIT_READ_UNITS = {"duty_W": "W", "power_W": "W"}


def _coherent(symbol: str) -> str | None:
    """``symbol`` if it parses as a coherent (factor 1, no offset) unit."""
    try:
        unit = parse_unit(symbol)
    except UomError:
        return None
    return symbol if unit.factor == 1.0 and unit.offset == 0.0 else None


def _declared_unit_in_text(description: str) -> str | None:
    """The unit a catalogue param description declares after its last comma
    (``'outlet pressure, Pa'`` -> ``'Pa'``); ``None`` when it declares none."""
    if "," not in description:
        return None
    token = description.rsplit(",", 1)[1].strip().split(" ")[0]
    if not token:
        return None
    try:
        parse_unit(token)
    except UomError:
        return None
    return token


def _declared_unit_in_key(key: str) -> str | None:
    """The SI unit an info key carries as its suffix (``power_W``, ``flow_mol_s``)."""
    parts = key.split("_")
    for n in (3, 2, 1):
        if len(parts) > n:
            symbol = _coherent("/".join(parts[-n:]) if n > 1 else parts[-1])
            if symbol is not None:
                return symbol
    return None


def _param_doc(kind: str, params: dict[str, Any], key: str) -> tuple[str | None, str]:
    """(declared unit, description) of one unit param from the catalogue row."""
    row = load_rows().get(kind)
    if row is None:
        return None, ""
    try:
        levels = [resolve_level(row, params), *row.levels]
    except Exception:  # noqa: BLE001 — an unresolvable level just widens the search
        levels = list(row.levels)
    for level in levels:
        props = row.levels[level].params.get("properties", {}) if level in row.levels else {}
        if key in props:
            description = str(props[key].get("description", ""))
            return _declared_unit_in_text(description), description
    return None, ""


def _convert(value: float, from_unit: str, to_unit: str) -> float:
    try:
        return float(cast(float, Quantity(value, from_unit).to(to_unit).magnitude()))
    except UomError as exc:
        raise OpError("unit_mismatch", f"cannot express {value} {from_unit} in {to_unit!r}: {exc}") from exc


# --- the hex grid of the flowsheet canvas ------------------------------------------------

#: Circumradius of one flowsheet canvas cell in layout units — the frontend's
#: flat-top hex lattice (frontend/src/hexGrid.ts, HEX_SIZE; Red Blob Games axial
#: coordinates), so a grid placement lands exactly where a dropped unit rests.
HEX_SIZE = 40.0


def hex_centre(q: int, r: int) -> XY:
    """Centre of axial cell (q, r): x = 1.5 s q, y = sqrt(3) s (r + q/2)."""
    return XY(x=HEX_SIZE * 1.5 * q, y=HEX_SIZE * math.sqrt(3.0) * (r + q / 2.0))


def _position(position: dict[str, Any] | None, grid: dict[str, Any] | None) -> XY | None:
    if position is not None and grid is not None:
        raise OpError("bad_position", "give position {x, y} or grid {q, r}, not both")
    if grid is not None:
        try:
            return hex_centre(int(grid["q"]), int(grid["r"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise OpError("bad_position", "grid must be {q: int, r: int}") from exc
    if position is not None:
        try:
            return XY(x=float(position["x"]), y=float(position["y"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise OpError("bad_position", "position must be {x: number, y: number}") from exc
    return None


# --- the service ------------------------------------------------------------------------------


def _rebuild(fs: Flowsheet, **updates: Any) -> Flowsheet:
    """``fs`` with whole-field updates, revalidated through the contracts
    (keeps design specs, solver options and reactions)."""
    try:
        return Flowsheet.model_validate({**fs.model_dump(), **updates})
    except ValueError as exc:
        raise OpError("invalid_project", str(exc)) from exc


class ProjectService:
    """Typed operations over one project (see module docstring).

    ``actor`` attributes every change (``api``, ``ui``, ``agent:<conversation>``,
    ``mcp``). ``last_change`` holds the payload of the most recent change this
    instance committed (``None`` before any, or when the write changed nothing).
    """

    def __init__(self, store: ProjectStore, engine: Engine = DEFAULT_ENGINE, actor: str = "api") -> None:
        self.store = store
        self.engine = engine
        self.actor = actor
        self.last_change: dict[str, Any] | None = None

    # -- plumbing -------------------------------------------------------------

    def project(self) -> Project:
        return self.store.get()

    def _commit(self, project: Project, op: str, summary: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """Write ``project`` as one logged change; returns the change payload."""
        commit = getattr(self.store, "commit", None)
        if commit is not None:
            change = commit(project, op=op, actor=self.actor, summary=summary, args=args)
            self.last_change = None if change is None else change_payload(change)
        else:  # a bare get/put store (tests): no history, the diff still reported
            before = self.store.get()
            self.store.put(project)
            diff = project_diff(before, project)
            self.last_change = (
                {
                    "seq": None,
                    "op": op,
                    "actor": self.actor,
                    "summary": summary,
                    "diff": diff,
                    "lines": diff_lines(diff),
                }
                if diff
                else None
            )
        return self.last_change

    def _write_flowsheet(self, fs: Flowsheet, op: str, summary: str, args: dict[str, Any]) -> Project:
        current = self.project()
        project = current.model_copy(update={"flowsheet": fs})
        self._commit(project, op, summary, args)
        return project

    def _unit(self, fs: Flowsheet, tag: str) -> UnitSpec:
        for spec in fs.units:
            if spec.tag == tag:
                return spec
        raise _not_found("unknown_unit", "unit", tag, sorted(u.tag for u in fs.units))

    def _stream(self, fs: Flowsheet, stream_id: str) -> StreamSpec:
        for spec in fs.streams:
            if spec.id == stream_id:
                return spec
        raise _not_found("unknown_stream", "stream", stream_id, sorted(s.id for s in fs.streams))

    @staticmethod
    def _check_kind(kind: str) -> None:
        known = registry.available("unit")
        if kind not in known:
            raise OpError(
                "unknown_kind",
                f"unknown unit kind {kind!r}; call list_unit_kinds / list_catalogue for the registered kinds",
                status=422,
                details={"have": known},
            )

    @staticmethod
    def _check_port(kind: str, tag: str, port: str, inlet: bool) -> None:
        cls = cast("type[UnitModel]", registry.get("unit", kind))  # locked protocol surface
        valid = cls.inlet_ports if inlet else cls.outlet_ports
        if port not in valid:
            role = "inlet" if inlet else "outlet"
            raise OpError(
                "bad_port",
                f"unit {tag} ({kind}) has no {role} port {port!r}; have {list(valid)}",
                details={"have": list(valid)},
            )

    def _next_tag(self, fs: Flowsheet, kind: str) -> str:
        row = load_rows().get(kind)
        symbol = row.pid_symbol if row is not None and row.pid_symbol else ""
        prefix = symbol if _TAG_PREFIX_RE.fullmatch(symbol) else "U"
        taken = {u.tag for u in fs.units}
        n = 101
        while f"{prefix}-{n}" in taken:
            n += 1
        return f"{prefix}-{n}"

    def _next_stream_id(self, fs: Flowsheet) -> str:
        taken = {s.id for s in fs.streams}
        n = len(taken) + 1
        while f"S-{n:03d}" in taken:
            n += 1
        return f"S-{n:03d}"

    # -- project reads ------------------------------------------------------------

    def flowsheet(self) -> dict[str, Any]:
        result: dict[str, Any] = self.project().flowsheet.model_dump(mode="json")
        return result

    # -- thermo / components -----------------------------------------------------------

    def set_thermo(self, package: str) -> dict[str, Any]:
        known = registry.available("thermo")
        if package not in known:
            raise OpError(
                "unknown_thermo",
                f"thermo model {package!r} has no registered plugin; have {known}",
                details={"have": known},
            )
        fs = self.project().flowsheet
        if fs.thermo == package:
            return {"thermo": package}
        new_fs = _rebuild(fs, thermo=package)
        self._write_flowsheet(
            new_fs, "set_thermo", f"Thermo package {fs.thermo} -> {package}", {"package": package}
        )
        return {"thermo": package}

    def set_components(self, components: list[str]) -> dict[str, Any]:
        fs = self.project().flowsheet
        if not components:
            raise OpError("invalid_project", "the component slate must not be empty")
        new_fs = _rebuild(fs, components=list(components))
        self._write_flowsheet(
            new_fs,
            "set_components",
            f"Component slate set ({len(components)} components)",
            {"components": list(components)},
        )
        return {"components": list(components)}

    def thermo_state(self) -> dict[str, Any]:
        fs = self.project().flowsheet
        return {
            "package": fs.thermo,
            "components": [c if isinstance(c, str) else c.model_dump(mode="json") for c in fs.components],
        }

    def recommend_thermo(self) -> dict[str, Any]:
        result: dict[str, Any] = advisor.payload(self.project().flowsheet)
        return result

    # -- units ------------------------------------------------------------------------------

    def place_unit(
        self,
        kind: str,
        tag: str | None = None,
        params: dict[str, Any] | None = None,
        position: dict[str, Any] | None = None,
        grid: dict[str, Any] | None = None,
        view: str | None = None,
    ) -> dict[str, Any]:
        """Add a catalogue unit; optionally place it at ``position`` {x, y} or hex
        ``grid`` {q, r} in ``view`` (default ``pfd``). No position: auto-layout."""
        self._check_kind(kind)
        project = self.project()
        fs = project.flowsheet
        tag = tag or self._next_tag(fs, kind)
        if tag in {u.tag for u in fs.units}:
            raise OpError("duplicate_tag", f"duplicate unit tags: {tag!r} is already used", status=409)
        try:
            spec = UnitSpec(tag=tag, kind=kind, params=dict(params or {}))
        except ValueError as exc:
            raise OpError("invalid_project", str(exc)) from exc
        new_fs = _rebuild(fs, units=[*fs.units, spec])
        xy = _position(position, grid)
        view = view or "pfd"
        if view not in ("pfd", "pid"):
            raise OpError("bad_view", f"view must be 'pfd' or 'pid', got {view!r}")
        layout = project.layout
        if xy is not None:
            layout = layout.model_copy(update={view: {**getattr(layout, view), tag: xy}})
        new = project.model_copy(update={"flowsheet": new_fs, "layout": layout})
        where = f" at ({xy.x:g}, {xy.y:g})" if xy is not None else ""
        self._commit(new, "place_unit", f"Placed {tag} ({kind}){where}", {"kind": kind, "tag": tag})
        out: dict[str, Any] = {"added": tag, "kind": kind, "units": sorted(u.tag for u in new_fs.units)}
        if xy is not None:
            out["position"] = {"view": view, "x": xy.x, "y": xy.y}
        return out

    def move_unit(
        self,
        tag: str,
        position: dict[str, Any] | None = None,
        grid: dict[str, Any] | None = None,
        view: str | None = None,
    ) -> dict[str, Any]:
        project = self.project()
        self._unit(project.flowsheet, tag)
        xy = _position(position, grid)
        if xy is None:
            raise OpError("bad_position", "give position {x, y} or grid {q, r}")
        view = view or "pfd"
        if view not in ("pfd", "pid"):
            raise OpError("bad_view", f"view must be 'pfd' or 'pid', got {view!r}")
        layout = project.layout.model_copy(update={view: {**getattr(project.layout, view), tag: xy}})
        self._commit(
            project.model_copy(update={"layout": layout}),
            "move_unit",
            f"Moved {tag} to ({xy.x:g}, {xy.y:g}) in {view}",
            {"tag": tag, "view": view, "x": xy.x, "y": xy.y},
        )
        return {"tag": tag, "view": view, "x": xy.x, "y": xy.y}

    def configure_unit(self, tag: str, params: dict[str, Any], replace: bool = False) -> dict[str, Any]:
        fs = self.project().flowsheet
        spec = self._unit(fs, tag)
        merged = dict(params) if replace else {**spec.params, **params}
        units = [u.model_copy(update={"params": merged}) if u.tag == tag else u for u in fs.units]
        new_fs = _rebuild(fs, units=units)
        keys = ", ".join(sorted(params)) or "(none)"
        verb = "Replaced" if replace else "Set"
        self._write_flowsheet(
            new_fs, "configure_unit", f"{verb} {tag} params: {keys}", {"tag": tag, "params": params}
        )
        return {"tag": tag, "params": merged}

    def delete_unit(self, tag: str) -> dict[str, Any]:
        project = self.project()
        fs = project.flowsheet
        self._unit(fs, tag)
        kept = [
            s
            for s in fs.streams
            if not ((s.source and s.source.unit == tag) or (s.target and s.target.unit == tag))
        ]
        dropped = sorted({s.id for s in fs.streams} - {s.id for s in kept})
        new_fs = _rebuild(fs, units=[u for u in fs.units if u.tag != tag], streams=kept)
        layout = project.layout.model_copy(
            update={
                view: {k: v for k, v in getattr(project.layout, view).items() if k != tag}
                for view in ("pfd", "pid", "plot")
            }
        )
        extra = f" and streams {', '.join(dropped)}" if dropped else ""
        self._commit(
            project.model_copy(update={"flowsheet": new_fs, "layout": layout}),
            "delete_unit",
            f"Deleted {tag}{extra}",
            {"tag": tag},
        )
        return {"removed": tag, "dropped_streams": dropped}

    def unit(self, tag: str) -> dict[str, Any]:
        project = self.project()
        spec = self._unit(project.flowsheet, tag)
        out: dict[str, Any] = spec.model_dump(mode="json")
        out["position"] = {
            view: getattr(project.layout, view)[tag].model_dump()
            for view in ("pfd", "pid", "plot")
            if tag in getattr(project.layout, view)
        }
        out["streams"] = sorted(
            s.id
            for s in project.flowsheet.streams
            if (s.source and s.source.unit == tag) or (s.target and s.target.unit == tag)
        )
        return out

    # -- streams -------------------------------------------------------------------------------

    def add_feed(
        self,
        target_unit: str,
        target_port: str,
        T_K: float,
        P_Pa: float,
        molar_flow_mol_s: float,
        composition: dict[str, float],
        stream_id: str | None = None,
        service: str | None = None,
    ) -> dict[str, Any]:
        fs = self.project().flowsheet
        target = self._unit(fs, target_unit)
        self._check_port(target.kind, target_unit, target_port, inlet=True)
        stream_id = stream_id or self._next_stream_id(fs)
        kwargs: dict[str, Any] = {"id": stream_id, "target": PortRef(unit=target_unit, port=target_port)}
        if service is not None:
            kwargs["service"] = service
        try:
            kwargs["feed"] = FeedSpec(T=T_K, P=P_Pa, molar_flow=molar_flow_mol_s, composition=composition)
            stream = StreamSpec(**kwargs)
        except ValueError as exc:
            raise OpError("invalid_project", str(exc)) from exc
        new_fs = _rebuild(fs, streams=[*fs.streams, stream])
        self._write_flowsheet(
            new_fs,
            "add_feed",
            f"Added feed {stream_id} -> {target_unit}.{target_port}",
            {"stream_id": stream_id, "target": f"{target_unit}.{target_port}"},
        )
        return {"added": stream_id, "to": f"{target_unit}.{target_port}"}

    def connect(
        self,
        source_unit: str,
        source_port: str,
        target_unit: str | None = None,
        target_port: str | None = None,
        stream_id: str | None = None,
        service: str | None = None,
    ) -> dict[str, Any]:
        """Connect an outlet port to an inlet port (both target args null: a product)."""
        fs = self.project().flowsheet
        source = self._unit(fs, source_unit)
        self._check_port(source.kind, source_unit, source_port, inlet=False)
        if (target_unit is None) != (target_port is None):
            raise OpError(
                "bad_port", "target_unit and target_port must be given together (or both null for a product)"
            )
        stream_id = stream_id or self._next_stream_id(fs)
        kwargs: dict[str, Any] = {"id": stream_id, "source": PortRef(unit=source_unit, port=source_port)}
        if service is not None:
            kwargs["service"] = service
        to = "product (battery limit)"
        if target_unit is not None and target_port is not None:
            target = self._unit(fs, target_unit)
            self._check_port(target.kind, target_unit, target_port, inlet=True)
            kwargs["target"] = PortRef(unit=target_unit, port=target_port)
            to = f"{target_unit}.{target_port}"
        try:
            stream = StreamSpec(**kwargs)
        except ValueError as exc:
            raise OpError("invalid_project", str(exc)) from exc
        new_fs = _rebuild(fs, streams=[*fs.streams, stream])
        self._write_flowsheet(
            new_fs,
            "connect",
            f"Connected {source_unit}.{source_port} -> {to} as {stream_id}",
            {"stream_id": stream_id, "source": f"{source_unit}.{source_port}", "target": to},
        )
        return {"added": stream_id, "from": f"{source_unit}.{source_port}", "to": to}

    def update_stream(
        self, stream_id: str, service: str | None = None, feed: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Change a stream's service code and/or (feed streams) its feed fields;
        null fields are left unchanged."""
        fs = self.project().flowsheet
        spec = self._stream(fs, stream_id)
        update: dict[str, Any] = {}
        if service is not None:
            update["service"] = service
        changes = {k: v for k, v in (feed or {}).items() if v is not None}
        if changes:
            if spec.feed is None:
                raise OpError(
                    "not_a_feed",
                    f"stream {stream_id} has a source, not a feed; only feed streams take feed fields",
                )
            unknown = sorted(set(changes) - {"T", "P", "molar_flow", "composition"})
            if unknown:
                raise OpError(
                    "invalid_project", f"unknown feed fields {unknown}; have T, P, molar_flow, composition"
                )
            try:
                update["feed"] = FeedSpec.model_validate({**spec.feed.model_dump(), **changes})
            except ValueError as exc:
                raise OpError("invalid_project", str(exc)) from exc
        if not update:
            raise OpError("nothing_to_change", "give service and/or feed fields to change")
        streams = [s.model_copy(update=update) if s.id == stream_id else s for s in fs.streams]
        new_fs = _rebuild(fs, streams=streams)
        fields = (
            sorted(update)
            if "feed" not in update
            else sorted({*update, *(f"feed.{k}" for k in changes)} - {"feed"})
        )
        self._write_flowsheet(
            new_fs,
            "update_stream",
            f"Updated {stream_id}: {', '.join(fields)}",
            {"stream_id": stream_id, "fields": fields},
        )
        return {"stream": self._stream(new_fs, stream_id).model_dump(mode="json")}

    def delete_stream(self, stream_id: str) -> dict[str, Any]:
        fs = self.project().flowsheet
        self._stream(fs, stream_id)
        new_fs = _rebuild(fs, streams=[s for s in fs.streams if s.id != stream_id])
        self._write_flowsheet(
            new_fs, "delete_stream", f"Deleted stream {stream_id}", {"stream_id": stream_id}
        )
        return {"disconnected": stream_id}

    def stream(self, stream_id: str) -> dict[str, Any]:
        out: dict[str, Any] = self._stream(self.project().flowsheet, stream_id).model_dump(mode="json")
        return out

    # -- cells (writable variables with units) ----------------------------------------------------

    def _cell(self, fs: Flowsheet, address: str) -> dict[str, Any]:
        head, *rest = address.split(".")
        for u in fs.units:
            if u.tag == head and len(rest) == 2 and rest[0] == "params":
                key = rest[1]
                declared, description = _param_doc(u.kind, u.params, key)
                return {
                    "address": address,
                    "value": u.params.get(key),
                    "unit": declared,
                    "description": description,
                    "owner": {"unit": head, "kind": u.kind},
                }
        for s in fs.streams:
            if s.id == head and s.feed is not None and len(rest) >= 2 and rest[0] == "feed":
                if len(rest) == 2 and rest[1] in _FEED_UNITS:
                    return {
                        "address": address,
                        "value": getattr(s.feed, rest[1]),
                        "unit": _FEED_UNITS[rest[1]],
                        "description": f"feed {rest[1]}",
                        "owner": {"stream": head},
                    }
                if len(rest) == 3 and rest[1] == "composition" and rest[2] in s.feed.composition:
                    return {
                        "address": address,
                        "value": s.feed.composition[rest[2]],
                        "unit": "1",
                        "description": f"feed mole fraction of {rest[2]} (others rescale to sum 1)",
                        "owner": {"stream": head},
                    }
        writable = variables.writable(fs)
        raise OpError(
            "unknown_address",
            f"unknown or read-only address {address!r}; writable addresses look like "
            "'<unit>.params.<key>', '<feed>.feed.<T|P|molar_flow>', '<feed>.feed.composition.<cid>'",
            status=404,
            details={"have": writable[:200]},
        )

    def cells(self) -> dict[str, Any]:
        fs = self.project().flowsheet
        return {"cells": [self._cell(fs, address) for address in variables.writable(fs)]}

    def cell(self, address: str) -> dict[str, Any]:
        return self._cell(self.project().flowsheet, address)

    def set_cell(self, address: str, value: Any, unit: str | None = None) -> dict[str, Any]:
        """Set one writable variable. Numbers may carry a ``unit`` (converted to
        the cell's declared unit, dimension-checked); unit params also accept
        non-numeric JSON values (no unit)."""
        project = self.project()
        fs = project.flowsheet
        cell = self._cell(fs, address)
        declared = cell["unit"]
        stored: Any = value
        if isinstance(value, bool) or not isinstance(value, int | float):
            if unit is not None:
                raise OpError("unit_mismatch", f"a unit only applies to numbers, got {value!r}")
            if "params" not in address.split("."):
                raise OpError("invalid_value", f"{address} takes a number, got {value!r}")
        else:
            number = float(value)
            if unit is not None:
                if declared is None:
                    # No declared unit: the engine convention is SI.
                    try:
                        number = float(cast(float, Quantity(number, unit).si))
                    except UomError as exc:
                        raise OpError("unit_mismatch", str(exc)) from exc
                else:
                    number = _convert(number, unit, declared)
            stored = number
        if isinstance(stored, float):
            try:
                new_fs = variables.assign(fs, address, stored)
            except ValueError as exc:
                raise OpError("invalid_value", str(exc)) from exc
        else:
            head, _, key = address.split(".")
            units = [
                u.model_copy(update={"params": {**u.params, key: stored}}) if u.tag == head else u
                for u in fs.units
            ]
            new_fs = _rebuild(fs, units=units)
        shown = f"{value} {unit}" if unit else f"{stored}"
        self._write_flowsheet(
            new_fs,
            "set_cell",
            f"Set {address} = {shown}",
            {"address": address, "value": value, "unit": unit},
        )
        return {"address": address, "previous": cell["value"], "value": stored, "unit": declared}

    # -- design specs ------------------------------------------------------------------------

    def design_specs(self) -> dict[str, Any]:
        return {"design_specs": [s.model_dump(mode="json") for s in self.project().flowsheet.design_specs]}

    def add_design_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        fs = self.project().flowsheet
        clean = {k: v for k, v in spec.items() if v is not None}
        try:
            parsed = DesignSpec.model_validate(clean)
        except ValueError as exc:
            raise OpError("invalid_project", str(exc)) from exc
        if parsed.id in {s.id for s in fs.design_specs}:
            raise OpError("duplicate_id", f"design spec {parsed.id!r} already exists", status=409)
        new_fs = _rebuild(fs, design_specs=[*fs.design_specs, parsed])
        self._write_flowsheet(
            new_fs,
            "add_design_spec",
            f"Design spec {parsed.id}: {parsed.target} = {parsed.value:g} by {parsed.manipulated}",
            {"id": parsed.id},
        )
        return {"added": parsed.id, "design_spec": parsed.model_dump(mode="json")}

    def delete_design_spec(self, spec_id: str) -> dict[str, Any]:
        fs = self.project().flowsheet
        if spec_id not in {s.id for s in fs.design_specs}:
            raise _not_found(
                "unknown_design_spec", "design spec", spec_id, sorted(s.id for s in fs.design_specs)
            )
        new_fs = _rebuild(fs, design_specs=[s for s in fs.design_specs if s.id != spec_id])
        self._write_flowsheet(new_fs, "delete_design_spec", f"Removed design spec {spec_id}", {"id": spec_id})
        return {"removed": spec_id}

    # -- solve and results ----------------------------------------------------------------------

    def solved(self) -> SolvedFlowsheet:
        try:
            return self.engine.solve_project(self.project())
        except UnknownPluginError as exc:
            raise OpError("unknown_plugin", str(exc), status=501) from exc
        except InvalidProjectError as exc:
            raise OpError("invalid_project", str(exc)) from exc

    def results(self) -> dict[str, Any]:
        """Convergence, diagnostics and the per-unit / per-stream summary."""
        solved = self.solved()
        return {
            "converged": solved.converged,
            "status": solved.status,
            "iterations": solved.iterations,
            "errors": [e.model_dump(mode="json") for e in solved.errors],
            "design_spec_results": [r.model_dump(mode="json") for r in solved.design_spec_results],
            "units": {
                tag: {"duty_W": r.duty_W, "power_W": r.power_W, "info": r.info}
                for tag, r in solved.units.items()
            },
            "streams": {
                sid: {"T": st.T, "P": st.P, "molar_flow": st.molar_flow, "vapor_fraction": st.vapor_fraction}
                for sid, st in solved.streams.items()
            },
        }

    def stream_result(self, stream_id: str) -> dict[str, Any]:
        solved = self.solved()
        if stream_id not in solved.streams:
            raise _not_found("unknown_stream", "stream", stream_id, sorted(solved.streams))
        return {"id": stream_id, "state": solved.streams[stream_id].model_dump(mode="json")}

    def unit_result(self, tag: str) -> dict[str, Any]:
        solved = self.solved()
        if tag not in solved.units:
            raise _not_found("unknown_unit", "unit", tag, sorted(solved.units))
        r = solved.units[tag]
        return {
            "tag": tag,
            "duty_W": r.duty_W,
            "power_W": r.power_W,
            "info": r.info,
            "outlets": {port: st.model_dump(mode="json") for port, st in r.outlets.items()},
        }

    @staticmethod
    def read_unit_of(address: str, solved: SolvedFlowsheet) -> str | None:
        """The declared SI unit of a read address (None when nothing declares it)."""
        head, *rest = address.split(".")
        if head in solved.streams and rest:
            return _STREAM_READ_UNITS.get(rest[0])
        if head in solved.units and rest:
            if rest[0] == "info" and len(rest) == 2:
                return _declared_unit_in_key(rest[1])
            return _UNIT_READ_UNITS.get(rest[0])
        return None

    def read(self, address: str, unit: str | None = None) -> dict[str, Any]:
        """One solved value by address, in SI or converted to ``unit``."""
        solved = self.solved()
        try:
            value = variables.resolve(address, solved)
        except ValueError as exc:
            raise OpError("unknown_address", str(exc), status=404) from exc
        si_unit = self.read_unit_of(address, solved)
        out: dict[str, Any] = {"address": address, "value": value, "unit": si_unit}
        if unit is not None:
            if si_unit is None:
                raise OpError(
                    "unit_mismatch", f"{address} declares no unit, so it cannot be converted to {unit!r}"
                )
            out = {
                **out,
                "value": _convert(value, si_unit, unit),
                "unit": unit,
                "si_value": value,
                "si_unit": si_unit,
            }
        return out

    # -- provenance --------------------------------------------------------------------------

    def explain(self, address: str, *, include_graph: bool = False) -> dict[str, Any]:
        """How a reported value was computed: the methods (with references) and
        the inputs and data (with sources) it rests on, from the traced solve."""
        project = self.project()
        try:
            solved, graph = self.engine.trace_project(project)
        except UnknownPluginError as exc:
            raise OpError("unknown_plugin", str(exc), status=501) from exc
        except InvalidProjectError as exc:
            raise OpError("invalid_project", str(exc)) from exc
        head, *rest = address.split(".")
        if not rest:
            raise OpError("unknown_address", f"address {address!r} needs a property, e.g. '{head}.T'")
        stream = head if head in solved.streams else None
        unit = head if stream is None and head in solved.units else None
        if stream is None and unit is None:
            raise _not_found(
                "unknown_address", "stream or unit", head, sorted(solved.streams) + sorted(solved.units)
            )
        prop = "composition" if rest[0] == "x" else ".".join(rest)
        node = graph.find(stream=stream, unit=unit, prop=prop)
        if node is None:
            props = sorted(
                {
                    v.prop
                    for v in graph.values
                    if v.kind == "output"
                    and v.prop
                    and (v.stream == stream if stream else v.unit_tag == unit and v.stream is None)
                }
            )
            raise OpError(
                "not_traced",
                f"no traced value {prop!r} for {head}; traced properties: {props}",
                status=404,
                details={"have": props},
            )
        sub = graph.upstream(node.id)
        steps = [
            {
                "id": op.id,
                "name": op.name,
                "method": op.method,
                "unit": op.unit_tag,
                "reference": op.references[0].citation if op.references else None,
                "converged": op.converged,
                "iterations": op.iterations,
            }
            for op in sub.ops
        ]
        inputs = [
            {
                "id": v.id,
                "label": v.label,
                "kind": v.kind,
                "value": v.value,
                "unit": v.unit,
                "quality": v.quality,
                "source": v.citation.citation if v.citation else None,
            }
            for v in sub.values
            if v.kind in ("input", "constant", "parameter")
        ]
        value: Any = node.value
        try:
            value = variables.resolve(address, solved)
        except ValueError:
            pass
        text = [f"{address} = {value} {node.unit} (quality: {node.quality})"]
        text += [
            f"  computed by {s['name']} [{s['method']}]"
            + (f" — {s['reference']}" if s["reference"] else " — unreferenced")
            for s in steps
        ]
        uncited = [str(i["label"]) for i in inputs if not i["source"]]
        text.append(f"  from {len(inputs)} inputs/data; uncited: {', '.join(uncited[:10]) or 'none'}")
        out: dict[str, Any] = {
            "address": address,
            "value": value,
            "unit": node.unit,
            "quality": node.quality,
            "node": node.id,
            "steps": steps,
            "inputs": inputs,
            "text": "\n".join(text),
        }
        if include_graph:
            out["graph"] = sub.model_dump(mode="json")
        return out

    # -- history ---------------------------------------------------------------------------------

    def _log(self) -> ChangeLog:
        if not all(hasattr(self.store, m) for m in ("commit", "undo", "redo", "changes")):
            raise OpError("no_history", "this project store keeps no change history", status=501)
        return cast(ChangeLog, self.store)

    def _move(self, move: Callable[..., Any], verb: str) -> dict[str, Any]:
        try:
            change = move(actor=self.actor)
        except LookupError as exc:
            raise OpError(f"nothing_to_{verb}", str(exc), status=409) from exc
        except RuntimeError as exc:
            raise OpError("conflict", str(exc), status=409) from exc
        self.last_change = change_payload(change)
        return {verb: self.last_change["target_seq"], "summary": self.last_change["summary"]}

    def undo(self) -> dict[str, Any]:
        return self._move(self._log().undo, "undo")

    def redo(self) -> dict[str, Any]:
        return self._move(self._log().redo, "redo")

    def changes(self, after: int = 0, limit: int = 100, newest: bool = False) -> dict[str, Any]:
        """The change log oldest first; ``newest``: only the latest ``limit``."""
        if limit < 1 or limit > 500:
            raise OpError("invalid_value", "limit must be in 1..500")
        log = self._log()
        rows = (
            list(reversed(log.changes(after=after, limit=limit, newest=True)))
            if newest
            else log.changes(after=after, limit=limit)
        )
        return {"changes": [change_payload(c) for c in rows]}


__all__ = [
    "HEX_SIZE",
    "ChangeLog",
    "OpError",
    "ProjectService",
    "ProjectStore",
    "change_payload",
    "component_catalogue",
    "hex_centre",
    "thermo_catalogue",
    "unit_catalogue",
    "unit_kind",
]
