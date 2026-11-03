"""The opt-in trace recorder (docs/provenance.md section 3).

Nothing here changes a computed value. Instrumented code asks :func:`active`
for the recorder and does nothing when it is ``None`` (the default), so the off
path costs one ``ContextVar.get``. Inside ``with recording() as rec:`` the
solver opens one *scope* per unit solve / feed flash / tear injection, the
thermo packages report every outermost protocol call, and units report their
own equations. :meth:`Recorder.graph` exports the result as a
:class:`~ngdesign.provenance.model.TraceGraph`.

Values passed as plain numbers are linked to the node they came from by exact
float equality against the scope's value table (compositions by their sorted
items); a value nothing explains becomes an ``uncited`` intermediate produced
by an ``unrecorded`` operation, so the audit sees it. 0.0 and +-1.0 are never
matched by value: they are too common to identify anything.

The recorder is duck-typed over the engine's objects (stream states, phase
records, thermo packages) so this package sits below ``contracts`` and
``thermo`` in the import layers. Deferred model fields (transport properties)
are never forced: properties are read from the instance ``__dict__`` only.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from ngdesign.provenance import catalogue
from ngdesign.provenance.model import (
    Citation,
    Edge,
    OpNode,
    Quality,
    TraceGraph,
    TraceValue,
    ValueKind,
    ValueNode,
)

_ACTIVE: ContextVar[Recorder | None] = ContextVar("ngdesign_provenance_recorder", default=None)

#: Flash records kept per scope; older ones are dropped (counted, never materialized).
FLASH_RECORD_CAP = 4000

#: Values never identified by equality (too common to mean anything).
_UNMATCHABLE = frozenset({0.0, 1.0, -1.0})

#: Stream-state scalar properties exported as nodes, with their SI units.
_STATE_PROPS: tuple[tuple[str, str], ...] = (
    ("T", "K"),
    ("P", "Pa"),
    ("molar_flow", "mol/s"),
    ("vapor_fraction", "1"),
    ("enthalpy", "J/mol"),
    ("entropy", "J/(mol K)"),
)
_PHASE_PROPS: tuple[tuple[str, str], ...] = (
    ("mole_fraction", "1"),
    ("density", "kg/m3"),
    ("molecular_weight", "g/mol"),
    ("enthalpy", "J/mol"),
    ("entropy", "J/(mol K)"),
    ("cp", "J/(mol K)"),
    ("z_factor", "1"),
)
_UNITS_BY_NAME: dict[str, str] = {
    "T": "K",
    "P": "Pa",
    "H": "J/mol",
    "S": "J/(mol K)",
    "vf": "1",
    "molar_flow": "mol/s",
    "enthalpy": "J/mol",
    "entropy": "J/(mol K)",
    "density": "kg/m3",
    "molecular_weight": "g/mol",
    "cp": "J/(mol K)",
    "gibbs": "J/mol",
    "z_factor": "1",
    "mole_fraction": "1",
    "duty_W": "W",
    "power_W": "W",
    "z": "1",
    "composition": "1",
    "T_out": "K",
    "P_out": "Pa",
    "outlet_P": "Pa",
    "dP": "Pa",
    "eta": "1",
    "eta_isentropic": "1",
    "vapor_fraction": "1",
    "fractions": "1",
    "duty_kW": "kW",
    "dT_K": "K",
}

#: (inverse applied to the reported value, forward check, from-unit, to-unit label)
_CONVERSIONS: tuple[tuple[str, Any, Any], ...] = (
    ("x / 1000", lambda v: v * 1000.0, lambda x: x / 1000.0),
    ("x * 1000", lambda v: v / 1000.0, lambda x: x * 1000.0),
    ("x - 273.15", lambda v: v + 273.15, lambda x: x - 273.15),
    ("x * 3600", lambda v: v / 3600.0, lambda x: x * 3600.0),
    ("x / 3600", lambda v: v * 3600.0, lambda x: x / 3600.0),
)


def active() -> Recorder | None:
    """The recorder of the enclosing :func:`recording` block, or None (tracing off)."""
    return _ACTIVE.get()


@contextmanager
def recording(**meta: str) -> Iterator[Recorder]:
    """Turn tracing on for the enclosed code; yields the recorder."""
    rec = Recorder(meta)
    token = _ACTIVE.set(rec)
    try:
        yield rec
    finally:
        _ACTIVE.reset(token)


@dataclass(frozen=True, slots=True)
class ValueRef:
    """A handle on a recorded value node (returned by the recording calls)."""

    id: str
    value: TraceValue


InputSpec = Any  # ValueRef | (state, "attr") | float | dict[str, float]


def _comp_key(z: Mapping[str, float]) -> tuple[str, tuple[tuple[str, float], ...]]:
    return ("z", tuple(sorted((str(k), float(v)) for k, v in z.items())))


def _key(value: Any) -> Any:
    """Value-table key: the float itself, or a composition's sorted items."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
        return None if f in _UNMATCHABLE or f != f else f
    if isinstance(value, Mapping) and value and all(isinstance(v, int | float) for v in value.values()):
        return _comp_key(value)
    return None


def _plain(value: Any) -> TraceValue:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, Mapping):
        return {str(k): float(v) for k, v in value.items() if isinstance(v, int | float)}
    if value is None:
        return None
    return str(value)


@dataclass
class _ThermoCall:
    """One outermost thermo-protocol call made inside a scope."""

    package: Any
    method: str
    args: dict[str, Any]
    result: Any
    seq: int = 0  # event time: only values recorded earlier can be its inputs
    convergence: dict[str, Any] | None = None
    op_id: str | None = None  # set once materialized


@dataclass
class _Scope:
    key: str
    unit_tag: str | None
    kind: str | None = None
    # value key -> [(event time, node id)], in time order
    table: dict[Any, list[tuple[int, str]]] = field(default_factory=dict)
    named: dict[str, str] = field(default_factory=dict)  # equation name -> node id
    # value key -> [(event time, call, prop)] for not-yet-materialized thermo results
    lazy: dict[Any, list[tuple[int, _ThermoCall, str]]] = field(default_factory=dict)
    # id(object) -> [(event time, node id | None, call | None, prop, object)]: identity
    # matches; the object is kept so its id stays unique while the scope lives
    ident: dict[int, list[tuple[int, str | None, _ThermoCall | None, str, Any]]] = field(default_factory=dict)
    # exact float -> input node (params, defaults): the only place 0.0 / +-1.0 may match
    inputs_by_value: dict[float, str] = field(default_factory=dict)
    calls: list[_ThermoCall] = field(default_factory=list)
    by_obj: dict[int, _ThermoCall] = field(default_factory=dict)
    n_calls: int = 0
    params: dict[str, str] = field(default_factory=dict)  # param path -> node id
    inlets: dict[str, Any] = field(default_factory=dict)
    generic_op: str | None = None
    tear_op: str | None = None  # tear scope: flashes materialize as this op's outputs


class Recorder:
    """Collects value/operation nodes while a solve runs (see module docstring)."""

    def __init__(self, meta: Mapping[str, str] | None = None) -> None:
        self.meta: dict[str, str] = dict(meta or {})
        self.values: dict[str, ValueNode] = {}
        self.ops: dict[str, OpNode] = {}
        self.edges: list[Edge] = []
        self._owner: dict[str, str] = {}  # node id -> scope key
        self._edge_owner: list[str] = []  # parallel to edges
        self._state_nodes: dict[int, dict[str, str]] = {}  # id(state) -> prop -> node id
        self._state_keep: dict[int, Any] = {}  # keeps state objects alive (stable ids)
        self._state_owner: dict[int, str] = {}
        self._bound: dict[int, str] = {}  # id(state) -> stream id it is bound to
        self._scope: _Scope | None = None
        self._scopes: dict[str, _Scope] = {}
        self._params_cache: dict[tuple[int, tuple[str, ...]], str] = {}
        self._leaf_cache: dict[tuple[Any, ...], str] = {}
        self._counter = 0
        self._clock = 0
        self.in_thermo = False
        self._pending_convergence: dict[str, Any] | None = None

    # ------------------------------------------------------------ node plumbing

    def _new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _owner_key(self) -> str:
        return self._scope.key if self._scope is not None else "global"

    def _add_value(
        self,
        label: str,
        value: Any,
        unit: str,
        kind: ValueKind,
        quality: Quality,
        *,
        citation: Citation | None = None,
        stream: str | None = None,
        unit_tag: str | None = None,
        prop: str | None = None,
        note: str | None = None,
        owner: str | None = None,
    ) -> str:
        nid = self._new_id("v")
        self.values[nid] = ValueNode(
            id=nid,
            label=label,
            value=_plain(value),
            unit=unit,
            kind=kind,
            quality=quality,
            citation=citation,
            stream=stream,
            unit_tag=unit_tag,
            prop=prop,
            note=note,
        )
        self._owner[nid] = owner or self._owner_key()
        return nid

    def _add_op(
        self,
        method: str,
        label: str | None = None,
        *,
        unit_tag: str | None = None,
        owner: str | None = None,
        note: str | None = None,
        name: str | None = None,
    ) -> str:
        entry = catalogue.method(method)
        oid = self._new_id("o")
        self.ops[oid] = OpNode(
            id=oid,
            label=label or (entry.name if entry else method),
            method=method,
            name=name or (entry.name if entry else method),
            latex=entry.latex if entry else None,
            references=list(entry.references) if entry else [],
            unit_tag=unit_tag,
            note=note,
        )
        self._owner[oid] = owner or self._owner_key()
        return oid

    def _edge(self, source: str, target: str, role: str = "", *, feedback: bool = False) -> None:
        self.edges.append(Edge(source=source, target=target, role=role, feedback=feedback))
        self._edge_owner.append(self._owner_key())

    def _tick(self) -> int:
        self._clock += 1
        return self._clock

    def _index(self, scope: _Scope | None, value: Any, nid: str, t: int | None = None) -> None:
        if scope is None:
            return
        key = _key(value)
        when = self._tick() if t is None else t
        if key is not None:
            scope.table.setdefault(key, []).append((when, nid))
        if isinstance(value, float | Mapping) and not isinstance(value, bool):
            scope.ident.setdefault(id(value), []).append((when, nid, None, "", value))

    def _lookup_identity(self, scope: _Scope, obj: Any, before: int) -> str | None:
        """The earliest holder of this very object before ``before`` (its origin)."""
        for t, nid, call, prop, held in scope.ident.get(id(obj), ()):
            if t >= before or held is not obj:
                continue
            if nid is not None:
                if nid in self.values:
                    return nid
                continue
            if call is not None:
                self._materialize_call(call, scope)
                found = self._state_nodes.get(id(call.result), {}).get(prop)
                if found is not None:
                    return found
        return None

    def _lookup(self, scope: _Scope, key: Any, before: int) -> str | None:
        """The most recent node (recorded or lazily materialized) with this value before ``before``."""
        best_t, best = -1, None
        for t, nid in reversed(scope.table.get(key, ())):
            if t < before and nid in self.values:
                best_t, best = t, nid
                break
        hit: tuple[int, _ThermoCall, str] | None = None
        for entry in reversed(scope.lazy.get(key, ())):
            if entry[0] < before:
                hit = entry
                break
        if hit is not None and hit[0] > best_t:
            t, call, prop = hit
            self._materialize_call(call, scope)
            found = self._state_nodes.get(id(call.result), {}).get(prop)
            if found is not None:
                return found
        return best

    # ------------------------------------------------------------ scopes

    def _purge(self, key: str) -> None:
        """Drop everything a previous run of scope ``key`` recorded (re-run passes)."""
        dead = {nid for nid, owner in self._owner.items() if owner == key}
        if not dead and key not in self._edge_owner:
            return
        for nid in dead:
            self.values.pop(nid, None)
            self.ops.pop(nid, None)
            del self._owner[nid]
        keep = [
            (e, o)
            for e, o in zip(self.edges, self._edge_owner, strict=True)
            if o != key and e.source not in dead and e.target not in dead
        ]
        self.edges = [e for e, _ in keep]
        self._edge_owner = [o for _, o in keep]
        for sid in [s for s, owner in self._state_owner.items() if owner == key]:
            del self._state_owner[sid]
            self._state_nodes.pop(sid, None)
            self._state_keep.pop(sid, None)
            self._bound.pop(sid, None)

    @contextmanager
    def scope(self, key: str, *, unit_tag: str | None = None, kind: str | None = None) -> Iterator[_Scope]:
        """Open a recording scope; re-opening a key replaces what it recorded before."""
        self._purge(key)
        outer = self._scope
        sc = _Scope(key=key, unit_tag=unit_tag, kind=kind)
        self._scopes[key] = sc
        self._scope = sc
        try:
            yield sc
        finally:
            self._scope = outer

    def begin_solve(self) -> None:
        """Forget everything but cached model parameters (a new inner solve starts)."""
        keep = {nid for nid, owner in self._owner.items() if owner == "model"}
        self.values = {k: v for k, v in self.values.items() if k in keep}
        self.ops = {k: v for k, v in self.ops.items() if k in keep}
        pairs = [(e, o) for e, o in zip(self.edges, self._edge_owner, strict=True) if o == "model"]
        self.edges = [e for e, _ in pairs]
        self._edge_owner = [o for _, o in pairs]
        self._owner = {k: v for k, v in self._owner.items() if k in keep}
        self._state_nodes.clear()
        self._state_keep.clear()
        self._state_owner.clear()
        self._bound.clear()
        self._scopes.clear()

    # ------------------------------------------------------------ inputs

    def _user_citation(self, what: str) -> Citation:
        fs = self.meta.get("flowsheet", "")
        where = f"flowsheet '{fs}', " if fs else ""
        return Citation(source="user", citation=f"User input: {where}{what}")

    def feed(
        self, stream_id: str, T: float, P: float, molar_flow: float, composition: Mapping[str, float]
    ) -> None:
        """Register a feed stream's specification as user inputs of the current scope."""
        sc = self._scope
        for prop, value, unit in (
            ("T", T, "K"),
            ("P", P, "Pa"),
            ("molar_flow", molar_flow, "mol/s"),
            ("composition", composition, "1"),
        ):
            nid = self._add_value(
                f"{stream_id} {prop} (spec)",
                value,
                unit,
                "input",
                "user",
                citation=self._user_citation(f"feed stream {stream_id} {prop}"),
                stream=stream_id,
                prop=f"spec.{prop}",
            )
            self._index(sc, value, nid)

    def unit_inputs(
        self, tag: str, flowsheet_name: str | None, inlets: Mapping[str, Any], params: Mapping[str, Any]
    ) -> None:
        """Register a unit's inlet states and numeric params in the current scope."""
        sc = self._scope
        if sc is None:
            return
        sc.inlets = dict(inlets)
        for state in inlets.values():
            self._index_state(sc, state, self._materialize_state(state))
        for path, value in _flatten(params):
            nid = self._add_value(
                f"{tag} {path}",
                value,
                _UNITS_BY_NAME.get(path.rsplit(".", 1)[-1].split("[", 1)[0], ""),
                "input",
                "user",
                citation=self._user_citation(f"unit {tag} parameter {path}"),
                unit_tag=tag,
                prop=f"param.{path}",
            )
            sc.params[path] = nid
            self._index(sc, value, nid)
            if isinstance(value, float):
                sc.inputs_by_value[value] = nid

    def default(self, name: str, value: float, unit: str, note: str) -> ValueRef:
        """A model default the unit applied because the user gave no value."""
        sc = self._scope
        tag = sc.unit_tag if sc else None
        if sc is not None and name in sc.params:
            return ValueRef(sc.params[name], value)
        nid = self._add_value(
            f"{tag or ''} {name} (default)".strip(),
            value,
            unit,
            "input",
            "user",
            citation=Citation(source="model_default", citation=f"Unit model default: {note}"),
            unit_tag=tag,
            prop=f"param.{name}",
        )
        if sc is not None:
            sc.named[name] = nid
            self._index(sc, value, nid)
            sc.inputs_by_value[float(value)] = nid
        return ValueRef(nid, value)

    def constant(self, name: str, value: float, unit: str, source: str) -> ValueRef:
        """A physical constant the code uses, cited by a source key (data/provenance/sources.yaml)."""
        cit = catalogue.source_citation(source)
        lk = ("constant", name, repr(value), source)
        nid = self._leaf_cache.get(lk)
        if nid is None or nid not in self.values:
            nid = self._add_value(
                name,
                value,
                unit,
                "constant",
                "cited" if cit else "uncited",
                citation=cit,
                prop=name,
                owner="model",
            )
            self._leaf_cache[lk] = nid
        self._index(self._scope, value, nid)
        return ValueRef(nid, value)

    def cited(
        self,
        name: str,
        value: Any,
        unit: str,
        citation: Citation | None,
        *,
        quality: Quality = "cited",
        note: str | None = None,
    ) -> ValueRef:
        """A data value the code read from a cited record (e.g. a chemdb row).

        ``citation=None`` records the value as ``uncited`` so the audit sees it.
        Identical (name, value, citation source) leaves are shared across scopes.
        """
        lk = ("cited", name, repr(_plain(value)), citation.source if citation else None)
        nid = self._leaf_cache.get(lk)
        if nid is None or nid not in self.values:
            nid = self._add_value(
                name,
                value,
                unit,
                "constant",
                quality if citation is not None else "uncited",
                citation=citation,
                prop=name,
                note=note,
                owner="model",
            )
            self._leaf_cache[lk] = nid
        self._index(self._scope, value, nid)
        return ValueRef(nid, _plain(value))

    # ------------------------------------------------------------ thermo calls

    def note_convergence(self, info: Mapping[str, Any] | None) -> None:
        """Called by the flash kernel with the flash's convergence record."""
        if info is not None:
            self._pending_convergence = dict(info)

    def thermo_call(self, package: Any, method: str, args: dict[str, Any], result: Any) -> None:
        """Record one outermost thermo-protocol call (called by the package wrapper)."""
        sc = self._scope
        conv, self._pending_convergence = self._pending_convergence, None
        if sc is None:
            return
        sc.n_calls += 1
        call = _ThermoCall(
            package=package, method=method, args=args, result=result, seq=self._tick(), convergence=conv
        )
        sc.calls.append(call)
        sc.by_obj[id(result)] = call
        if len(sc.calls) > FLASH_RECORD_CAP:
            # Keep the newest half (amortized): outlets come from the last calls.
            # Materialized calls survive - their nodes are already in the graph.
            half = len(sc.calls) // 2
            dropped, sc.calls = sc.calls[:half], sc.calls[half:]
            sc.calls = [c for c in dropped if c.op_id is not None] + sc.calls
            keep_ids = {id(c) for c in sc.calls}
            sc.by_obj = {k: c for k, c in sc.by_obj.items() if id(c) in keep_ids}
            sc.lazy = {
                k: kept for k, hits in sc.lazy.items() if (kept := [h for h in hits if id(h[1]) in keep_ids])
            }
            sc.ident = {
                k: kept_ident
                for k, hits in sc.ident.items()
                if (kept_ident := [h for h in hits if h[2] is None or id(h[2]) in keep_ids])
            }
        # A result attribute that IS one of the call's arguments (a flash_pt state's T and
        # P, a memoized result handed out again) was not produced by this call: it is not
        # registered as an identity holder, so it never shadows the value's real origin.
        passed = {id(v) for v in args.values()}
        for prop, value in _result_props(result):
            key = _key(value)
            if key is not None:
                sc.lazy.setdefault(key, []).append((call.seq, call, prop))
            if id(value) in passed:
                continue
            if isinstance(value, float | Mapping) and not isinstance(value, bool):
                sc.ident.setdefault(id(value), []).append((call.seq, None, call, prop, value))

    def _model_entry(self, package: Any) -> catalogue.MethodEntry | None:
        """The package's model: its vetted EOS key, else its thermo catalogue row."""
        model = getattr(package, "trace_model", lambda: None)()
        entry = catalogue.method(model) if model else None
        if entry is not None:
            return entry
        cls = type(package)
        row = catalogue.thermo_row_for_adapter(f"{cls.__module__}:{cls.__name__}") or self.meta.get("thermo")
        return catalogue.method(f"thermo_model:{row}") if row else None

    def _params_node(self, package: Any, ids: tuple[str, ...]) -> str | None:
        """The (cached) model-parameter-set node for a package over a component support."""
        ck = (id(package), ids)
        if ck in self._params_cache and self._params_cache[ck] in self.values:
            return self._params_cache[ck]
        describe = getattr(package, "trace_parameters", None)
        spec: dict[str, Any] = (
            describe(ids)
            if describe is not None
            else {
                "model": type(package).__name__,
                "leaves": [
                    {
                        "key": ("untraced", type(package).__name__),
                        "label": f"{type(package).__name__} parameters (not traced)",
                        "value": "model parameters",
                        "quality": "uncited",
                        "kind": "parameter",
                        "role": "parameters",
                        "note": "This property package does not report its parameters yet.",
                    }
                ],
            }
        )
        model_name = spec.get("model", type(package).__name__)
        set_id = self._add_value(
            f"{model_name} parameters ({', '.join(ids)})",
            f"{model_name}: {len(ids)} components",
            "",
            "parameter",
            "derived",
            prop="parameter_set",
            owner="model",
        )
        op = self._add_op(
            "parameter_set",
            f"assemble {model_name} parameters",
            owner="model",
        )
        self.edges.append(Edge(source=op, target=set_id, role="set"))
        self._edge_owner.append("model")
        for leaf in spec.get("leaves", []):
            lk = (leaf["key"], repr(leaf["value"]))
            nid = self._leaf_cache.get(lk)
            if nid is None or nid not in self.values:
                nid = self._add_value(
                    leaf["label"],
                    leaf["value"],
                    leaf.get("unit", ""),
                    leaf.get("kind", "constant"),
                    leaf.get("quality", "uncited"),
                    citation=leaf.get("citation"),
                    note=leaf.get("note"),
                    prop=leaf.get("prop"),
                    owner="model",
                )
                self._leaf_cache[lk] = nid
            self.edges.append(Edge(source=nid, target=op, role=leaf.get("role", "")))
            self._edge_owner.append("model")
        self._params_cache[ck] = set_id
        return set_id

    def _materialize_call(self, call: _ThermoCall, scope: _Scope) -> str:
        """Create the operation node and output nodes of a recorded thermo call."""
        if call.op_id is not None and call.op_id in self.ops:
            return call.op_id
        owner = scope.key
        if scope.tear_op is not None:
            op = scope.tear_op
        else:
            op = self._add_op(call.method, unit_tag=scope.unit_tag, owner=owner)
            node = self.ops[op]
            entry = self._model_entry(call.package)
            if entry is not None:
                node.name = f"{node.name} · {entry.name}"
                node.references = [*entry.references, *node.references]
                node.latex = entry.latex or node.latex
            node.label = f"{call.method} ({scope.unit_tag or scope.key})"
            call.op_id = op
            if call.convergence:
                it = call.convergence.get("iterations")
                err = call.convergence.get("err")
                node.iterations = int(it) if isinstance(it, int | float) else None
                node.residual = float(err) if isinstance(err, int | float) else None
                node.converged = True
            for name, value in call.args.items():
                if name in ("self",):
                    continue
                src = self._resolve(value, scope, role=name, before=call.seq)
                if src is not None:
                    self._edge(src, op, name)
            comp = call.args.get("z") or call.args.get("composition")
            cid = call.args.get("cid")
            ids = (
                tuple(sorted(k for k, v in comp.items() if v > 0.0))
                if isinstance(comp, Mapping)
                else ((str(cid),) if cid is not None else ())
            )
            if ids:
                pset = self._params_node(call.package, ids)
                if pset is not None:
                    self._edge(pset, op, "model")
        call.op_id = op
        if _is_state(call.result):
            self._materialize_state(call.result, producer=op, owner=owner)
        else:
            rid = id(call.result)
            nodes: dict[str, str] = {}
            for prop, value in _result_props(call.result):
                nid = self._add_value(
                    f"{call.method} {prop}",
                    value,
                    _UNITS_BY_NAME.get(prop.rsplit(".", 1)[-1], ""),
                    "intermediate",
                    "derived",
                    unit_tag=scope.unit_tag,
                    prop=prop,
                    owner=owner,
                )
                self._edge(op, nid, prop)
                nodes[prop] = nid
            self._state_nodes[rid] = nodes
            self._state_owner[rid] = owner
        return op

    # ------------------------------------------------------------ states

    def _materialize_state(
        self, state: Any, producer: str | None = None, owner: str | None = None
    ) -> dict[str, str]:
        """Value nodes for a stream state's properties (created once per object)."""
        sid = id(state)
        existing = self._state_nodes.get(sid)
        if existing is not None:
            return existing
        if producer is None:
            sc = self._find_call_scope(state)
            if sc is not None:
                call = sc.by_obj[sid]
                self._materialize_call(call, sc)
                return self._state_nodes[sid]
        owner = owner or self._owner_key()
        sc = self._scope
        tag = sc.unit_tag if sc else None
        if producer is None:
            producer = self._add_op("unrecorded", "unrecorded state", unit_tag=tag, owner=owner)
        nodes: dict[str, str] = {}
        where = self.ops[producer].label
        for prop, value in _state_values(state):
            nid = self._add_value(
                f"{where}: {prop}",
                value,
                _UNITS_BY_NAME.get(prop.rsplit(".", 1)[-1], ""),
                "intermediate",
                "derived" if self.ops[producer].method != "unrecorded" else "uncited",
                unit_tag=tag,
                prop=prop,
                owner=owner,
            )
            self._edge(producer, nid, prop)
            nodes[prop] = nid
        self._state_nodes[sid] = nodes
        self._state_keep[sid] = state
        self._state_owner[sid] = owner
        return nodes

    def _find_call_scope(self, obj: Any) -> _Scope | None:
        oid = id(obj)
        if self._scope is not None and oid in self._scope.by_obj:
            return self._scope
        for sc in reversed(list(self._scopes.values())):
            if oid in sc.by_obj:
                return sc
        return None

    def derived_state(
        self, state: Any, method: str, inputs: Mapping[str, InputSpec], note: str | None = None
    ) -> None:
        """Declare that ``state`` was built by ``method`` from ``inputs`` (no flash)."""
        sc = self._scope
        if sc is None:
            return
        if id(state) in self._state_nodes:
            return
        op = self._add_op(method, unit_tag=sc.unit_tag, note=note)
        for role, spec in inputs.items():
            src = self._resolve(spec, sc, role=role)
            if src is not None:
                self._edge(src, op, role)
        self._index_state(sc, state, self._materialize_state(state, producer=op))

    def _index_state(self, sc: _Scope, state: Any, nodes: Mapping[str, str]) -> None:
        """Register a state's raw property objects (identity and value) in a scope."""
        t = self._tick()
        for prop, raw in _state_values(state):
            nid = nodes.get(prop)
            if nid is not None:
                self._index(sc, raw, nid, t)

    def bind_stream(self, stream_id: str, state: Any) -> None:
        """Name a state's nodes after the stream the solver stored it as (outputs)."""
        sc = self._scope
        nodes = self._materialize_state(state)
        if id(state) in self._bound and self._bound[id(state)] != stream_id:
            op = self._add_op("identity", f"{stream_id} = {self._bound[id(state)]}")
            copy: dict[str, str] = {}
            for prop, nid in nodes.items():
                src = self.values[nid]
                cid = self._add_value(
                    f"{stream_id} {prop}",
                    src.value,
                    src.unit,
                    "output",
                    "derived",
                    stream=stream_id,
                    prop=prop,
                )
                self._edge(nid, op, prop)
                self._edge(op, cid, prop)
                copy[prop] = cid
            return
        self._bound[id(state)] = stream_id
        for prop, nid in nodes.items():
            node = self.values[nid]
            node.stream = stream_id
            node.label = f"{stream_id} {prop}"
            node.kind = "output"
            node.unit_tag = sc.unit_tag if sc else node.unit_tag

    # ------------------------------------------------------------ equations

    def _resolve(
        self, spec: InputSpec, scope: _Scope | None, role: str = "", before: int | None = None
    ) -> str | None:
        """The node id an equation/flash input came from (an unattributed node if unknown)."""
        if isinstance(spec, ValueRef):
            return spec.id
        if isinstance(spec, tuple) and len(spec) == 2 and isinstance(spec[1], str):
            obj, attr = spec
            nodes = self._materialize_state(obj)
            if attr in nodes:
                return nodes[attr]
            value = getattr(obj, attr, None)
            return self._unattributed(role or attr, value, scope)
        if spec is None or isinstance(spec, str | bool):
            return None
        key = _key(spec)
        if scope is not None and isinstance(spec, float | Mapping):
            limit = self._clock + 1 if before is None else before
            nid = self._lookup_identity(scope, spec, limit)
            if nid is None and key is not None:
                nid = self._lookup(scope, key, limit)
            if nid is None and key is None and isinstance(spec, float):
                found = scope.inputs_by_value.get(spec)
                nid = found if found in self.values else None
            if nid is not None:
                return nid
            # an inlet-stream / upstream value referenced directly
            for state in scope.inlets.values():
                for prop, v in _state_values(state):
                    if _key(v) == key:
                        return self._materialize_state(state)[prop]
        if not isinstance(spec, int | float | Mapping):
            return None
        return self._unattributed(role, spec, scope)

    def _unattributed(self, role: str, value: Any, scope: _Scope | None) -> str:
        tag = scope.unit_tag if scope else None
        op = self._add_op("unrecorded", f"unrecorded calculation ({tag or role})", unit_tag=tag)
        nid = self._add_value(
            f"{tag + ' ' if tag else ''}{role} (unattributed)",
            value,
            _UNITS_BY_NAME.get(role, ""),
            "intermediate",
            "uncited",
            unit_tag=tag,
            prop=role,
            note="No recorded operation produced this value; instrument the code that computes it.",
        )
        self._edge(op, nid, role)
        self._index(scope, value, nid)
        return nid

    def equation(
        self,
        name: str,
        value: Any,
        unit: str,
        method: str,
        inputs: Mapping[str, InputSpec],
        *,
        label: str | None = None,
        note: str | None = None,
        iterations: int | None = None,
        residual: float | None = None,
    ) -> ValueRef:
        """Record ``name = method(inputs)``; returns a handle usable as a later input."""
        sc = self._scope
        tag = sc.unit_tag if sc else None
        op = self._add_op(method, label, unit_tag=tag, note=note)
        if iterations is not None:
            self.ops[op].iterations = iterations
            self.ops[op].converged = True
        if residual is not None:
            self.ops[op].residual = residual
        for role, spec in inputs.items():
            src = self._resolve(spec, sc, role=role)
            if src is not None:
                self._edge(src, op, role)
        nid = self._add_value(
            f"{tag + ' ' if tag else ''}{name}",
            value,
            unit,
            "intermediate",
            "derived",
            unit_tag=tag,
            prop=name,
        )
        self._edge(op, nid, name)
        if sc is not None:
            sc.named[name] = nid
            self._index(sc, value, nid)
        return ValueRef(nid, _plain(value))

    def results(
        self,
        method: str,
        outputs: Mapping[str, Any],
        inputs: Mapping[str, InputSpec],
        *,
        states: Sequence[Any] = (),
        label: str | None = None,
        note: str | None = None,
        iterations: int | None = None,
        residual: float | None = None,
    ) -> dict[str, ValueRef]:
        """Record one operation with several results (a converged column, a reactor solve).

        ``outputs`` maps result names to numbers (nested mappings and numeric lists are
        flattened to ``a.b`` / ``a[0]``, the names the unit's ``info`` binds by); each
        becomes an intermediate of the operation. ``states`` are outlet stream states the
        operation produced directly (their flashes, if any, are not shown separately).
        Use this for iterative solvers whose internals are not traced: the operation
        carries the iteration count and residual instead.
        """
        sc = self._scope
        tag = sc.unit_tag if sc else None
        op = self._add_op(method, label, unit_tag=tag, note=note)
        if iterations is not None:
            self.ops[op].iterations = iterations
            self.ops[op].converged = True
        if residual is not None:
            self.ops[op].residual = residual
        for role, spec in inputs.items():
            src = self._resolve(spec, sc, role=role)
            if src is not None:
                self._edge(src, op, role)
        refs: dict[str, ValueRef] = {}
        for name, value in _flatten(outputs):
            nid = self._add_value(
                f"{tag + ' ' if tag else ''}{name}",
                value,
                _unit_of(name),
                "intermediate",
                "derived",
                unit_tag=tag,
                prop=name,
            )
            self._edge(op, nid, name)
            if sc is not None:
                sc.named[name] = nid
                self._index(sc, value, nid)
            refs[name] = ValueRef(nid, _plain(value))
        if sc is not None:
            for state in states:
                if id(state) not in self._state_nodes:
                    self._index_state(sc, state, self._materialize_state(state, producer=op))
        return refs

    # ------------------------------------------------------------ unit results

    def bind_unit_result(self, tag: str, kind: str, result: Any) -> None:
        """Bind a unit's duty/power/info numbers to the nodes that computed them."""
        sc = self._scope
        if sc is None:
            return
        items: list[tuple[str, float]] = []
        for name in ("duty_W", "power_W"):
            v = getattr(result, name, None)
            if isinstance(v, int | float) and not isinstance(v, bool):
                items.append((name, float(v)))
        info = getattr(result, "info", None) or {}
        items.extend((f"info.{p}", v) for p, v in _flatten(info) if isinstance(v, float))
        for name, value in items:
            short = name.removeprefix("info.")
            src = sc.named.get(short)
            if src is not None and src in self.values and self.values[src].value != value:
                src = None
            if src is None:
                src = self._resolve_lazy(value, sc)
            if src is not None:
                node = self.values[src]
                if node.kind == "intermediate" and node.unit_tag == tag and node.stream is None:
                    node.kind = "output"
                    node.label = f"{tag} {name}"
                    node.prop = name
                    continue
                self._report(tag, name, value, node.unit, src, "identity")
                continue
            conv = self._conversion(value, sc)
            if conv is not None:
                src, expr = conv
                self._report(tag, name, value, "", src, "unit_conversion", note=f"{name} = {expr}")
                continue
            if value == 0.0 and name in ("duty_W", "power_W"):
                op = self._add_op("not_applicable", f"{tag}: no {name.removesuffix('_W')}", unit_tag=tag)
                nid = self._add_value(
                    f"{tag} {name}", value, "W", "output", "derived", unit_tag=tag, prop=name
                )
                self._edge(op, nid, name)
                continue
            gen = self._generic_op(sc, tag, kind)
            nid = self._add_value(
                f"{tag} {name}",
                value,
                _UNITS_BY_NAME.get(short, ""),
                "output",
                "uncited",
                unit_tag=tag,
                prop=name,
            )
            self._edge(gen, nid, name)
        if sc.n_calls:
            gen_ids = [
                o for o in self.ops.values() if o.unit_tag == tag and o.method.startswith("unit_model")
            ]
            for o in gen_ids:
                o.calls = sc.n_calls
        self._annotate_iterations(sc, result)

    def _annotate_iterations(self, sc: _Scope, result: Any) -> None:
        info = getattr(result, "info", None) or {}
        it = next(
            (info[k] for k in ("iterations", "n_iterations", "iter") if isinstance(info.get(k), int)), None
        )
        res = next(
            (info[k] for k in ("residual", "residual_max", "max_residual") if isinstance(info.get(k), float)),
            None,
        )
        if it is None and res is None:
            return
        for o in self.ops.values():
            if (
                o.unit_tag == sc.unit_tag
                and self._owner.get(o.id) == sc.key
                and o.method.startswith(("unit_model", "column", "reactor"))
            ):
                o.iterations = it if o.iterations is None else o.iterations
                o.residual = res if o.residual is None else o.residual

    def _resolve_lazy(self, value: float, sc: _Scope) -> str | None:
        key = _key(value)
        if key is None:
            return None
        limit = self._clock + 1
        return self._lookup_identity(sc, value, limit) or self._lookup(sc, key, limit)

    def _conversion(self, value: float, sc: _Scope) -> tuple[str, str] | None:
        for expr, inverse, forward in _CONVERSIONS:
            x = inverse(value)
            key = _key(x)
            if key is None:
                continue
            src = self._resolve_lazy(x, sc)
            if src is not None and forward(x) == value:
                return src, expr
        return None

    def _report(
        self, tag: str, name: str, value: float, unit: str, src: str, method: str, note: str | None = None
    ) -> None:
        op = self._add_op(method, unit_tag=tag, note=note)
        self._edge(src, op, "x")
        nid = self._add_value(
            f"{tag} {name}",
            value,
            unit if method == "identity" else "",
            "output",
            "derived",
            unit_tag=tag,
            prop=name,
        )
        self._edge(op, nid, name)

    def _generic_op(self, sc: _Scope, tag: str, kind: str) -> str:
        if sc.generic_op is not None and sc.generic_op in self.ops:
            return sc.generic_op
        op = self._add_op(
            f"unit_model:{kind}",
            f"{tag} ({kind}) model",
            unit_tag=tag,
            note="This unit has not recorded its equations; its results are not traceable yet.",
        )
        self.ops[op].calls = sc.n_calls
        for port, state in sc.inlets.items():
            nodes = self._materialize_state(state)
            for prop in ("T", "P", "molar_flow", "enthalpy", "composition"):
                if prop in nodes:
                    self._edge(nodes[prop], op, f"{port}.{prop}")
        for path, nid in sc.params.items():
            self._edge(nid, op, path)
        sc.generic_op = op
        return op

    def unit_outlets(self, tag: str, kind: str, outlets: Mapping[str, Any]) -> None:
        """Make sure every outlet state has a producer (generic unit op if unrecorded)."""
        sc = self._scope
        if sc is None:
            return
        for state in outlets.values():
            if id(state) in self._state_nodes:
                continue
            if self._find_call_scope(state) is not None:
                continue
            op = self._generic_op(sc, tag, kind)
            self._materialize_state(state, producer=op)

    # ------------------------------------------------------------ tears

    def tear_scope_op(self, stream_id: str) -> None:
        """In the current (tear-injection) scope, flashes become outputs of one tear op."""
        sc = self._scope
        if sc is None:
            return
        op = self._add_op("tear_stream", f"tear {stream_id}")
        sc.tear_op = op

    def close_tear(
        self,
        stream_id: str,
        injected: Any,
        computed: Any,
        *,
        method: str,
        iterations: int,
        residual: float | None,
    ) -> None:
        """Annotate a converged tear: the injected guess is fed back from the computed stream."""
        sc = self._scopes.get(f"tear:{stream_id}")
        if sc is None or sc.tear_op is None or sc.tear_op not in self.ops:
            return
        op = self.ops[sc.tear_op]
        entry = catalogue.method(method)
        if entry is not None:
            op.name = entry.name
            op.latex = entry.latex
            op.references = list(entry.references)
            op.method = method
        op.iterations = iterations
        op.residual = residual
        op.converged = True
        op.label = f"tear {stream_id}: {iterations} it."
        inj = self._materialize_state(injected)
        for prop, nid in inj.items():
            node = self.values[nid]
            node.label = f"{stream_id} {prop} (tear)"
            node.stream = None
        comp = self._materialize_state(computed)
        outer, self._scope = self._scope, sc
        try:
            for prop in ("T", "P", "molar_flow", "composition"):
                if prop in comp:
                    self._edge(comp[prop], op.id, prop, feedback=True)
        finally:
            self._scope = outer

    # ------------------------------------------------------------ design specs

    def _address_node(self, address: str, *, write: bool) -> str | None:
        """The value node of a variable address (ngdesign.variables grammar), if traced."""
        head, *rest = address.split(".")
        if write:
            if rest[:1] == ["params"]:
                prop, unit_tag, stream = "param." + ".".join(rest[1:]), head, None
            elif rest[:1] == ["feed"]:
                field_ = "composition" if rest[1:2] == ["composition"] else ".".join(rest[1:])
                prop, unit_tag, stream = f"spec.{field_}", None, head
            else:
                return None
        elif rest[:1] == ["x"]:
            prop, unit_tag, stream = "composition", head, head
        else:
            prop, unit_tag, stream = ".".join(rest), head, head
        for v in self.values.values():
            if v.prop != prop:
                continue
            if write and (
                (stream is not None and v.stream == stream) or (unit_tag and v.unit_tag == unit_tag)
            ):
                return v.id
            if (
                not write
                and v.kind == "output"
                and (v.stream == stream or (v.stream is None and v.unit_tag == unit_tag))
            ):
                return v.id
        return None

    def design_spec(
        self,
        spec_id: str,
        *,
        manipulated: str,
        target: str,
        value: float,
        achieved: float,
        iterations: int,
        converged: bool,
        method: str,
    ) -> None:
        """The manipulated variable was set by a design-spec loop, not by the user."""
        mnode = self._address_node(manipulated, write=True)
        if mnode is None:
            return
        op = self._add_op(method, f"design spec {spec_id}", owner="design_spec")
        node = self.ops[op]
        node.iterations = iterations
        node.converged = converged
        node.residual = abs(achieved - value) / max(abs(value), 1e-300)
        node.note = f"Drives {target} to {value!r} by adjusting {manipulated}."
        goal = self._add_value(
            f"{spec_id} target {target}",
            value,
            "",
            "input",
            "user",
            citation=self._user_citation(f"design spec {spec_id} target value"),
            prop=f"design_spec.{spec_id}",
            owner="design_spec",
        )
        self.edges.append(Edge(source=goal, target=op, role="target"))
        self._edge_owner.append("design_spec")
        tnode = self._address_node(target, write=False)
        if tnode is not None:
            self.edges.append(Edge(source=tnode, target=op, role="achieved", feedback=True))
            self._edge_owner.append("design_spec")
        self.edges.append(Edge(source=op, target=mnode, role=manipulated))
        self._edge_owner.append("design_spec")
        m = self.values[mnode]
        m.kind = "intermediate"
        m.quality = "derived"
        m.citation = None
        m.note = f"Set by design spec {spec_id} (the flowsheet's value is only the start point)."

    # ------------------------------------------------------------ export

    def graph(self) -> TraceGraph:
        """The recorded graph (edges whose endpoints were dropped are removed)."""
        live = set(self.values) | set(self.ops)
        edges = [e for e in self.edges if e.source in live and e.target in live]
        return TraceGraph(
            values=list(self.values.values()),
            ops=list(self.ops.values()),
            edges=edges,
            meta=dict(self.meta),
        )


def _is_state(obj: Any) -> bool:
    d = getattr(obj, "__dict__", None)
    return isinstance(d, dict) and "vapor_fraction" in d and "molar_flow" in d


def _state_values(state: Any) -> list[tuple[str, Any]]:
    d = state.__dict__
    out: list[tuple[str, Any]] = [(p, d[p]) for p, _ in _STATE_PROPS if p in d]
    out.append(("composition", d.get("composition", {})))
    for phase in d.get("phases") or []:
        pd = phase.__dict__
        kind = str(pd.get("kind", "phase"))
        for prop, _ in _PHASE_PROPS:
            v = pd.get(prop)
            if isinstance(v, int | float) and not isinstance(v, bool):
                out.append((f"{kind}.{prop}", v))
        out.append((f"{kind}.composition", pd.get("composition", {})))
    return out


def _result_props(result: Any) -> list[tuple[str, Any]]:
    if _is_state(result):
        return _state_values(result)
    if isinstance(result, int | float) and not isinstance(result, bool):
        return [("value", result)]
    if isinstance(result, Mapping):
        return [(str(k), v) for k, v in result.items() if isinstance(v, int | float)]
    d = getattr(result, "__dict__", None)
    if isinstance(d, dict):
        return [
            (k, v)
            for k, v in d.items()
            if (isinstance(v, int | float) and not isinstance(v, bool))
            or (isinstance(v, Mapping) and v and all(isinstance(x, int | float) for x in v.values()))
        ]
    return []


#: Name-suffix -> SI unit, for results named like ``duty_reboiler_W`` or ``A_m2``.
_SUFFIX_UNITS: tuple[tuple[str, str], ...] = (
    ("_W_m2K", "W/(m2 K)"),
    ("_W_K", "W/K"),
    ("_mol_s", "mol/s"),
    ("_kg_s", "kg/s"),
    ("_m3_s", "m3/s"),
    ("_kW", "kW"),
    ("_W", "W"),
    ("_K", "K"),
    ("_Pa", "Pa"),
    ("_m2", "m2"),
    ("_m3", "m3"),
    ("_m", "m"),
    ("_s", "s"),
)


def _unit_of(name: str) -> str:
    """SI unit of a named result: a known name, else its suffix, else dimensionless."""
    leaf = name.rsplit(".", 1)[-1].split("[", 1)[0]
    if leaf in _UNITS_BY_NAME:
        return _UNITS_BY_NAME[leaf]
    return next((unit for suffix, unit in _SUFFIX_UNITS if leaf.endswith(suffix)), "")


def _flatten(params: Mapping[str, Any], prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for k, v in params.items():
        path = f"{prefix}{k}"
        if isinstance(v, bool):
            continue
        if isinstance(v, int | float):
            out.append((path, float(v)))
        elif (
            isinstance(v, list | tuple)
            and v
            and all(isinstance(x, int | float) and not isinstance(x, bool) for x in v)
        ):
            out.extend((f"{path}[{i}]", float(x)) for i, x in enumerate(v))
        elif isinstance(v, list | tuple) and v and all(isinstance(x, Mapping) for x in v):
            # e.g. a reaction set's reactions: their kinetic constants are user inputs too
            for i, x in enumerate(v):
                out.extend(_flatten(x, f"{path}[{i}]."))
        elif isinstance(v, Mapping):
            if (
                v
                and all(isinstance(x, int | float) and not isinstance(x, bool) for x in v.values())
                and _looks_like_composition(v)
            ):
                out.append((path, v))  # the mapping itself: identity matching needs the object
            else:
                out.extend(_flatten(v, f"{path}."))
    return out


def param_inputs(params: Mapping[str, Any], *, skip: tuple[str, ...] = ()) -> dict[str, Any]:
    """A unit's numeric params as equation inputs, by their flattened param paths.

    The values are the ones :meth:`Recorder.unit_inputs` registered as user inputs, so
    they resolve to those nodes. Top-level keys in ``skip`` are left out.
    """
    return dict(_flatten({k: v for k, v in params.items() if k not in skip}))


def _looks_like_composition(v: Mapping[str, Any]) -> bool:
    try:
        return abs(sum(float(x) for x in v.values()) - 1.0) < 1e-6 and len(v) > 1
    except (TypeError, ValueError):
        return False
