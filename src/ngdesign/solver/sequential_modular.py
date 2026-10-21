"""Sequential-modular flowsheet solver (spec S-30). Plugin kind "solver", name "sequential_modular".

Solves a Flowsheet by flashing boundary feeds with flash_pt, running unit models in
dependency order, and converging recycles by stream tearing + bounded Wegstein
acceleration (Wegstein, J.H., "Accelerating Convergence of Iterative Processes",
Comm. ACM 1(6), 1958; bounded-q form as in Westerberg et al., "Process Flowsheeting",
Cambridge University Press, 1979).

Method:
1. Flash every feed stream (source=None) once; feeds are fixed boundary conditions.
2. Build the unit digraph and find strongly connected components (Kosaraju). The
   condensation is processed in topological order.
3. An acyclic component runs once. A cyclic component is torn: a small set of internal
   streams is picked by greedy cycle-breaking (repeatedly find a cycle and tear its
   edge whose source unit has the highest remaining out-degree, ties by stream id -
   one tear for a simple loop, a small heuristic set for nested ones), then the torn
   vectors (component flows, T, P) are iterated:

       x_k  injected guess, y_k  value calculated by the units
       s_k = (y_k - y_{k-1}) / (x_k - x_{k-1})          per-variable secant
       q_k = s_k / (s_k - 1), clamped to [-5, 0]
       x_{k+1} = q_k * x_k + (1 - q_k) * y_k

   q = 0 is direct substitution, q = -5 the strongest acceleration allowed. The first
   pass and any degenerate secant fall back to direct substitution.
4. Converged when every torn variable satisfies |y - x| <= RTOL * max(|x|, 1.0):
   1e-6 relative per the spec, with a near-zero absolute floor of 1e-6 in the
   variable's own units (mol/s, K, Pa). MAX_ITERATIONS passes are allowed; past that
   the solver returns converged=False - it never raises for non-convergence.

Injection of a torn stream flashes the guessed (T, P, flows) through the thermo
package, so downstream units always see a consistent StreamState. Wegstein iterates
that leave the physical range (negative flows, T or P <= 0) are clamped for injection
only; raw values stay in the secant history. A unit model that raises no longer
aborts the solve (spec P2-02): the exception is recorded as a UnitError, its outlet
streams stay unset, and every downstream unit whose inlet is missing is recorded as
an upstream skip - the partial SolvedFlowsheet (status "failed") is the result.
Port-check failures and unconnected inlets are recorded the same way, as stage
"ports" errors. Only the iteration budget yields converged=False for a loop that
merely fails to converge; a failed unit marks its block (and the sheet) converged
too. Every block appends a BlockRecord (tears, iterations, wall time) and every
tear iteration a TearRecord per tear stream to SolvedFlowsheet.history. Tear
initialization is the molar-flow-weighted mean of the boundary feeds (simple,
deterministic; feed-free sheets start from 1 mol/s nitrogen at ambient conditions).

The torn component flows are indexed by the flowsheet's own component slate (spec
P1-02), not a fixed module constant: solve entry resolves every slate id through
the open component registry (unresolvable ids fail the solve there), so tear
vectors are built in `fs.components` order with T at index len(slate) and P at
len(slate) + 1. The slate may carry flowsheet-owned pseudo definitions (spec
P1-07): they resolve through the flowsheet's own slate - never the module-level
register_pseudo default - and the resolved ComponentSet is handed to the thermo
package once per solve (set_component_set), whose flasher and Psat caches key on
the definitions, so two flowsheets with different definitions of the same pseudo
id never share a flasher.
"""

from __future__ import annotations

import heapq
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import NamedTuple

from ngdesign import registry
from ngdesign.contracts import (
    FeedSpec,
    Flowsheet,
    SolvedFlowsheet,
    StreamSpec,
    StreamState,
    UnitResult,
)
from ngdesign.contracts.components import resolve_set
from ngdesign.contracts.diagnostics import BlockRecord, SolveAcceleration, TearRecord, UnitError
from ngdesign.contracts.plugins import Thermo, UnitModel

#: Relative convergence tolerance for torn variables (spec S-30).
RTOL = 1e-6

#: Hard cap on passes over a cyclic component (spec S-30).
MAX_ITERATIONS = 100

#: Strongest Wegstein acceleration allowed (spec S-30: q in [-5, 0]).
WEGSTEIN_Q_MIN = -5.0


class _Edge(NamedTuple):
    """One directed unit-to-unit connection, carrying the stream that realizes it."""

    stream_id: str
    src: str
    dst: str


@dataclass
class _Tear:
    """Bookkeeping for one torn stream: guess, calculated values, secant history."""

    stream_id: str
    x: list[float]
    x_prev: list[float] | None = None
    y_prev: list[float] | None = None


@dataclass
class _Context:
    """Mutable working state threaded through the solver's helpers."""

    fs: Flowsheet
    units: dict[str, UnitModel]
    thermo: Thermo
    states: dict[str, StreamState]
    results: dict[str, UnitResult]
    components: tuple[str, ...]
    errors: list[UnitError]  # spec P2-02: per-unit failure records
    history: list[BlockRecord]  # spec P2-02: one record per executed block
    # Spec P2-01: previous solve's tear vectors per stream id (design-spec outer
    # loop). None keeps the mean-of-feeds initialization below, byte-identically.
    warm_start: dict[str, list[float]] | None = None
    # Spec P3-02: optional progress sink, called with every TearRecord as it is
    # appended. Purely observational - no numeric change, None by default.
    on_progress: Callable[[TearRecord], None] | None = None


def _stream_edges(fs: Flowsheet) -> list[_Edge]:
    """Directed edges between units: one per stream with both ends on units."""
    edges = []
    for s in fs.streams:
        if s.source is not None and s.target is not None:
            edges.append(_Edge(s.id, s.source.unit, s.target.unit))
    return edges


def _topo_order[K: (str, int)](nodes: list[K], edges: list[tuple[K, K]]) -> list[K]:
    """Kahn topological order of a DAG; deterministic (smallest node first).

    Raises RuntimeError on a cycle - callers must have removed one first (tears).
    """
    successor: dict[K, list[K]] = {n: [] for n in nodes}
    indegree: dict[K, int] = {n: 0 for n in nodes}
    for u, v in edges:
        successor[u].append(v)
        indegree[v] += 1
    for lst in successor.values():
        lst.sort()
    ready = [n for n in nodes if indegree[n] == 0]
    heapq.heapify(ready)
    order: list[K] = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for nxt in successor[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) != len(nodes):
        raise RuntimeError("cycle where the solver expected a DAG - tear selection failed")
    return order


def _strongly_connected(nodes: list[str], edges: list[_Edge]) -> list[list[str]]:
    """Kosaraju SCCs; deterministic (nodes sorted, components returned member-sorted)."""
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    transpose: dict[str, list[str]] = {n: [] for n in nodes}
    for e in edges:
        adjacency[e.src].append(e.dst)
        transpose[e.dst].append(e.src)
    for table in (adjacency, transpose):
        for lst in table.values():
            lst.sort()
    visited: set[str] = set()
    finished: list[str] = []
    for start in nodes:
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if idx < len(adjacency[node]):
                stack[-1] = (node, idx + 1)
                nxt = adjacency[node][idx]
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt, 0))
            else:
                finished.append(node)
                stack.pop()
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in reversed(finished):
        if start in seen:
            continue
        seen.add(start)
        component: list[str] = []
        remaining: list[str] = [start]
        while remaining:
            node = remaining.pop()
            component.append(node)
            for nxt in transpose[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    remaining.append(nxt)
        components.append(sorted(component))
    return components


def _condensation_topo(tags: list[str], edges: list[_Edge]) -> list[list[str]]:
    """Strongly connected components of the unit graph, in execution order."""
    components = _strongly_connected(tags, edges)
    index_of = {tag: i for i, component in enumerate(components) for tag in component}
    cross: list[tuple[int, int]] = sorted(
        {(index_of[e.src], index_of[e.dst]) for e in edges if index_of[e.src] != index_of[e.dst]}
    )
    if not cross:
        return components
    order = _topo_order(list(range(len(components))), cross)
    return [components[i] for i in order]


def _find_cycle(nodes: list[str], edges: list[_Edge]) -> list[_Edge] | None:
    """One cycle as an ordered list of its edges (DFS back edge); None if acyclic."""
    adjacency: dict[str, list[_Edge]] = {n: [] for n in nodes}
    for e in edges:
        adjacency[e.src].append(e)
    for lst in adjacency.values():
        lst.sort(key=lambda e: e.stream_id)
    white, gray, black = 0, 1, 2
    color = dict.fromkeys(nodes, white)
    parent_edge: dict[str, _Edge] = {}
    for start in nodes:
        if color[start] != white:
            continue
        color[start] = gray
        stack: list[tuple[str, int]] = [(start, 0)]
        while stack:
            node, idx = stack[-1]
            if idx < len(adjacency[node]):
                stack[-1] = (node, idx + 1)
                edge = adjacency[node][idx]
                nxt = edge.dst
                if color[nxt] == gray:
                    cycle = [edge]
                    walk = node
                    while walk != nxt:
                        step = parent_edge[walk]
                        cycle.append(step)
                        walk = step.src
                    cycle.reverse()
                    return cycle
                if color[nxt] == white:
                    color[nxt] = gray
                    parent_edge[nxt] = edge
                    stack.append((nxt, 0))
            else:
                color[node] = black
                stack.pop()
    return None


def _pick_tears(fs: Flowsheet, block: set[str]) -> list[str]:
    """Streams to tear so the block runs acyclically: greedy cycle-breaking.

    Repeatedly finds a cycle and tears the edge whose source unit has the most
    remaining out-degree (ties by stream id): the minimum set for a simple loop,
    a small heuristic set for nested ones (minimum feedback arc set is NP-hard;
    the spec asks for a simple heuristic).
    """
    edges = [e for e in _stream_edges(fs) if e.src in block and e.dst in block]
    nodes = sorted(block)
    torn: list[str] = []
    remaining = list(edges)
    while (cycle := _find_cycle(nodes, remaining)) is not None:
        out_degree = {n: 0 for n in nodes}
        for e in remaining:
            out_degree[e.src] += 1
        best = min(cycle, key=lambda e: (-out_degree[e.src], e.stream_id))
        remaining.remove(best)
        torn.append(best.stream_id)
    return sorted(torn)


def _block_order(fs: Flowsheet, block: set[str], torn: set[str]) -> list[str]:
    """Execution order for the units of one block; the tears break its cycles."""
    tags = sorted(block)
    edges = [
        (e.src, e.dst)
        for e in _stream_edges(fs)
        if e.src in block and e.dst in block and e.stream_id not in torn
    ]
    return _topo_order(tags, edges)


def _check_ports(fs: Flowsheet, units: dict[str, UnitModel]) -> list[UnitError]:
    """Record every stream end naming a port the unit plugin does not declare.

    Without this, a typo'd port name would silently drop or invent material.
    Spec P2-02: the failures are stage="ports" UnitErrors on the unit owning the
    mistyped end - the solve continues and the partial result carries them,
    instead of aborting the whole sheet.
    """
    errors: list[UnitError] = []
    for s in fs.streams:
        if s.source is not None and s.source.port not in units[s.source.unit].outlet_ports:
            tag = s.source.unit
            errors.append(
                UnitError(
                    tag=tag,
                    kind=fs.unit(tag).kind,
                    error_type="ValueError",
                    message=f"stream {s.id}: unit {tag} has no outlet port {s.source.port!r}",
                    stage="ports",
                )
            )
        if s.target is not None and s.target.port not in units[s.target.unit].inlet_ports:
            tag = s.target.unit
            errors.append(
                UnitError(
                    tag=tag,
                    kind=fs.unit(tag).kind,
                    error_type="ValueError",
                    message=f"stream {s.id}: unit {tag} has no inlet port {s.target.port!r}",
                    stage="ports",
                )
            )
    return errors


def _flash_feed(spec: StreamSpec, thermo: Thermo) -> StreamState:
    """Flash one boundary feed at its specified (T, P)."""
    feed = spec.feed
    if feed is None:  # unreachable: Flowsheet validation requires a feed when source is None
        raise ValueError(f"feed stream {spec.id} has no feed spec")
    return thermo.flash_pt(feed.composition, feed.T, feed.P, feed.molar_flow)


def _tear_vector(state: StreamState, components: tuple[str, ...]) -> list[float]:
    """The torn variables of a stream: component flows (mol/s), then T (K), P (Pa).

    Component flows are indexed by the flowsheet's slate order (spec P1-02); T sits
    at index len(components), P at len(components) + 1.
    """
    flows = state.component_flows()
    return [flows.get(c, 0.0) for c in components] + [state.T, state.P]


def _inject_tear(
    vector: list[float],
    components: tuple[str, ...],
    fallback_composition: dict[str, float],
    thermo: Thermo,
) -> StreamState:
    """Build the StreamState a tear guess is injected as, by flashing it.

    Values outside the physical range (negative flows, T or P <= 0) are clamped for
    injection only - raw values stay in the secant history. A zero-flow guess cannot
    be flashed; it becomes a degenerate stream at the fallback composition.
    """
    flows = {c: max(vector[i], 0.0) for i, c in enumerate(components)}
    total = sum(flows.values())
    t = max(vector[len(components)], 1.0)
    p = max(vector[len(components) + 1], 1.0)
    if total <= 0.0:
        return StreamState(
            T=t,
            P=p,
            molar_flow=0.0,
            composition=dict(fallback_composition),
            vapor_fraction=1.0,
            enthalpy=0.0,
            entropy=0.0,
            phases=[],
        )
    composition = {c: n / total for c, n in flows.items() if n > 0.0}
    return thermo.flash_pt(composition, t, p, total)


def _init_guess(fs: Flowsheet, components: tuple[str, ...]) -> tuple[list[float], dict[str, float]]:
    """Initial tear guess: the molar-flow-weighted mean of the boundary feeds.

    Feed-free sheets start from 1 mol/s nitrogen at ambient conditions - any
    positive, normalized guess converges for a well-posed loop. (A feed-free sheet
    whose slate omits N2 gets a zero first guess; the degenerate-stream path keeps
    it consistent.)
    """
    feeds: list[FeedSpec] = []
    for s in fs.streams:
        if s.source is None and s.feed is not None:
            feeds.append(s.feed)
    total = sum(f.molar_flow for f in feeds)
    if not feeds or total <= 0.0:
        composition: dict[str, float] = {"N2": 1.0}
        t, p, flow = 298.15, 101325.0, 1.0
    else:
        t = sum(f.T * f.molar_flow for f in feeds) / total
        p = sum(f.P * f.molar_flow for f in feeds) / total
        flow = total
        moles: dict[str, float] = {}
        for f in feeds:
            for c, z in f.composition.items():
                moles[c] = moles.get(c, 0.0) + z * f.molar_flow
        composition = {c: n / flow for c, n in sorted(moles.items())}
    vector = [flow * composition.get(c, 0.0) for c in components] + [t, p]
    return vector, composition


def _wegstein_q(xc: float, yc: float, xp: float, yp: float) -> float | None:
    """Bounded Wegstein factor of one torn variable from its secant history.

        s = (y - y_prev) / (x - x_prev); q = s / (s - 1), clamped to [-5, 0]

    ``None`` when the secant is degenerate (direct substitution, q = 0). The one
    owner of the formula: the step and the history record both read it here.
    """
    dx = xc - xp
    if abs(dx) <= 1e-12 * max(abs(xc), 1.0):
        return None
    slope = (yc - yp) / dx
    return min(max(slope / (slope - 1.0), WEGSTEIN_Q_MIN), 0.0)


def _wegstein_next(x: list[float], y: list[float], x_prev: list[float], y_prev: list[float]) -> list[float]:
    """One bounded-Wegstein step, per variable: x_next = q * x + (1 - q) * y with
    q from :func:`_wegstein_q`; direct substitution when the secant is degenerate."""
    out: list[float] = []
    for xc, yc, xp, yp in zip(x, y, x_prev, y_prev, strict=True):
        q = _wegstein_q(xc, yc, xp, yp)
        out.append(yc if q is None else q * xc + (1.0 - q) * yc)
    return out


def _converged(x: list[float], y: list[float]) -> bool:
    """Every torn variable stable to RTOL relative (with a near-zero absolute floor)."""
    return all(abs(yc - xc) <= RTOL * max(abs(xc), 1.0) for xc, yc in zip(x, y, strict=True))


def _run_units(ctx: _Context, order: list[str]) -> bool:
    """Run the units of one block in order, writing stream states and unit results.

    Spec P2-02: a unit exception is recorded as a stage="solve" UnitError, its
    outlet streams stay unset, and every later unit in the block whose inlet has
    no state is recorded as an upstream skip (no exception propagates). An inlet
    port with no connected stream is a stage="ports" error. A unit that fails
    outright, or cannot run at all (blocked inlet), marks the block not
    converged; a block whose units all ran cleanly stays converged. Upstream
    skips keep the sheet's status derivation honest (they are not failures), but
    the block they sit in did not execute, so it is not converged either.
    """
    ok = True
    for tag in order:
        spec = ctx.fs.unit(tag)
        unit = ctx.units[tag]
        inlets: dict[str, StreamState] = {}
        blocked: UnitError | None = None
        for port in unit.inlet_ports:
            incoming = [s for s in ctx.fs.inlets(tag) if s.target is not None and s.target.port == port]
            if not incoming:
                blocked = UnitError(
                    tag=tag,
                    kind=spec.kind,
                    error_type="ValueError",
                    message=f"unit {tag}: inlet port {port!r} has no connected stream",
                    stage="ports",
                )
                break
            state = ctx.states.get(incoming[0].id)
            if state is None:
                blocked = UnitError(
                    tag=tag,
                    kind=spec.kind,
                    error_type="",
                    message=(
                        f"unit {tag} skipped: inlet stream {incoming[0].id} on port {port!r} has no "
                        "state (its source unit failed or was skipped)"
                    ),
                    stage="solve",
                    upstream=True,
                )
                break
            inlets[port] = state
        if blocked is not None:
            ok = False
            ctx.errors.append(blocked)
            continue
        try:
            result = unit.solve(inlets, spec.params, ctx.thermo)
        except Exception as exc:  # the failure IS the result (spec P2-02)
            ok = False
            ctx.errors.append(
                UnitError(
                    tag=tag,
                    kind=spec.kind,
                    error_type=type(exc).__name__,
                    message=str(exc),
                    stage="solve",
                )
            )
            continue
        ctx.results[tag] = result
        for stream in ctx.fs.outlets(tag):
            source = stream.source
            if source is None or source.port not in result.outlets:
                ok = False
                ctx.errors.append(
                    UnitError(
                        tag=tag,
                        kind=spec.kind,
                        error_type="ValueError",
                        message=(
                            f"unit {tag} returned no state for outlet port "
                            f"{source.port if source else '?'!r} (stream {stream.id})"
                        ),
                        stage="outlet_missing",
                    )
                )
                continue
            ctx.states[stream.id] = result.outlets[source.port]
    return ok


def _emit_progress(ctx: _Context, record: TearRecord) -> None:
    """Forward one freshly appended TearRecord to the progress sink, if any."""
    if ctx.on_progress is not None:
        ctx.on_progress(record)


def _tear_record(iteration: int, tear: _Tear, state: StreamState, components: tuple[str, ...]) -> TearRecord:
    """One tear stream's residual record at one iteration (spec P2-02).

    Residuals use the convergence test's own relative measure, |y - x| / max(|x|,
    1.0), keyed by component id then "T" and "P". ``acceleration`` names the step
    taken at this iteration (the first pass and an all-degenerate secant are direct
    substitution); ``q`` is the clamped Wegstein factor of the variable with the
    largest residual - the per-variable secant makes one representative q the
    honest summary.
    """
    y = _tear_vector(state, components)
    x = tear.x
    residuals = [abs(yc - xc) / max(abs(xc), 1.0) for xc, yc in zip(x, y, strict=True)]
    n = len(components)
    residual_vector = {
        **dict(zip(components, residuals[:n], strict=True)),
        "T": residuals[n],
        "P": residuals[n + 1],
    }
    residual_max = max(residuals)
    acceleration: SolveAcceleration
    q: float | None
    if tear.y_prev is None or tear.x_prev is None:
        acceleration, q = "direct", None
    else:
        history = zip(x, y, tear.x_prev, tear.y_prev, strict=True)
        q_values = [_wegstein_q(xc, yc, xp, yp) for xc, yc, xp, yp in history]
        if all(qv is None for qv in q_values):
            acceleration, q = "direct", None
        else:
            worst = max(range(len(residuals)), key=residuals.__getitem__)
            acceleration, q = "wegstein", q_values[worst] or 0.0  # degenerate worst variable: q = 0
    return TearRecord(
        iteration=iteration,
        stream_id=tear.stream_id,
        residual_max=residual_max,
        residual_vector=residual_vector,
        acceleration=acceleration,
        q=q,
    )


def _converge_block(ctx: _Context, order: list[str], tears: list[str]) -> tuple[bool, int]:
    """Iterate one cyclic block to a converged tear solution, or give up at the cap.

    Every pass appends one TearRecord per tear stream to the block's record list
    (spec P2-02). A unit that fails mid-iteration ends the block after that pass
    with converged=False: the torn states downstream of the failure are
    meaningless, so further Wegstein passes would iterate on garbage.
    """
    start = time.perf_counter()
    guess, fallback_composition = _init_guess(ctx.fs, ctx.components)
    torn: list[_Tear] = []
    for sid in tears:
        x = list(guess)
        if ctx.warm_start is not None:
            warm = ctx.warm_start.get(sid)
            if warm is not None and len(warm) == len(ctx.components) + 2:
                x = list(warm)  # warm start (spec P2-01): the previous solve's tear vector
        torn.append(_Tear(stream_id=sid, x=x))
    converged = False
    iterations = 0
    records: list[TearRecord] = []
    for iteration in range(1, MAX_ITERATIONS + 1):
        iterations = iteration
        for t in torn:
            ctx.states[t.stream_id] = _inject_tear(t.x, ctx.components, fallback_composition, ctx.thermo)
        if not _run_units(ctx, order):
            break  # a unit failed this pass: stop iterating, converged stays False
        if all(_converged(t.x, _tear_vector(ctx.states[t.stream_id], ctx.components)) for t in torn):
            converged = True
            for t in torn:
                record = _tear_record(iteration, t, ctx.states[t.stream_id], ctx.components)
                records.append(record)
                _emit_progress(ctx, record)
            break
        for t in torn:
            calculated = _tear_vector(ctx.states[t.stream_id], ctx.components)
            record = _tear_record(iteration, t, ctx.states[t.stream_id], ctx.components)
            records.append(record)
            _emit_progress(ctx, record)
            injected = t.x
            if t.y_prev is None or t.x_prev is None:
                t.x = list(calculated)  # first pass: direct substitution
            else:
                t.x = _wegstein_next(injected, calculated, t.x_prev, t.y_prev)
            t.x_prev, t.y_prev = injected, calculated
    ctx.history.append(
        BlockRecord(
            units=list(order),
            tears=list(tears),
            iterations=iterations,
            converged=converged,
            records=records,
            wall_s=time.perf_counter() - start,
        )
    )
    return converged, iterations


class SequentialModular:
    """Sequential-modular execution with tearing + Wegstein.

    Unregistered as of spec P2-01: the "sequential_modular" registry name now
    belongs to the design-spec outer solver (solver/design_specs.py), which
    delegates here when the flowsheet carries no design specs. Import this class
    for the bare inner solve; ``solve``'s ``warm_start`` argument takes the
    previous solve's tear vectors per stream id so an outer loop (or a repeated
    solve) starts each recycle from the converged values instead of the
    mean-of-feeds guess — with ``warm_start=None`` the behaviour and flash
    counts are unchanged. ``on_progress`` (spec P3-02) is called with every
    freshly appended TearRecord — the async-job path streams them; cached
    replays (engine-level) never reach here and emit nothing. Both seams are
    observational for the numerics.
    """

    def solve(
        self,
        fs: Flowsheet,
        thermo: Thermo,
        warm_start: dict[str, list[float]] | None = None,
        *,
        on_progress: Callable[[TearRecord], None] | None = None,
    ) -> SolvedFlowsheet:
        units: dict[str, UnitModel] = {u.tag: registry.create("unit", u.kind) for u in fs.units}
        errors = _check_ports(fs, units)
        # Specs P1-02/P1-07: every slate id must resolve through the open
        # component registry - the thermo factory and tear vectors below both
        # index by it, so an unresolvable id fails here, at the solve entry,
        # with its name. Flowsheet-owned pseudo definitions resolve through the
        # flowsheet's own slate, and the resolved ComponentSet is handed to the
        # thermo package so its flasher constants build from the slate's own
        # characterizations (packages without the seam - test doubles, amine
        # packages - keep the spec P1-02 global-resolution behaviour).
        component_set = resolve_set(fs.components)
        set_component_set = getattr(thermo, "set_component_set", None)
        if callable(set_component_set):
            set_component_set(component_set)
        components = tuple(component_set.ids)
        ctx = _Context(
            fs=fs,
            units=units,
            thermo=thermo,
            states={},
            results={},
            components=components,
            errors=errors,
            history=[],
            warm_start=warm_start,
        )
        ctx.on_progress = on_progress
        for s in fs.streams:
            if s.source is None:
                ctx.states[s.id] = _flash_feed(s, thermo)
        tags = sorted(u.tag for u in fs.units)
        converged = True
        iterations = 0
        for block in _condensation_topo(tags, _stream_edges(fs)):
            block_set = set(block)
            tears = _pick_tears(fs, block_set)
            order = _block_order(fs, block_set, set(tears))
            if tears:
                ok, block_iterations = _converge_block(ctx, order, tears)
            else:
                start = time.perf_counter()
                ok = _run_units(ctx, order)
                ctx.history.append(
                    BlockRecord(
                        units=list(order),
                        tears=[],
                        iterations=1,
                        converged=ok,
                        records=[],
                        wall_s=time.perf_counter() - start,
                    )
                )
                block_iterations = 1
            converged = converged and ok
            iterations = max(iterations, block_iterations)
        return SolvedFlowsheet(
            flowsheet=fs,
            streams=ctx.states,
            units=ctx.results,
            converged=converged,
            iterations=iterations,
            errors=ctx.errors,
            history=ctx.history,
        )
