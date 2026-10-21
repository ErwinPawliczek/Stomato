"""Solve and render helpers shared by the API routes and the agent tools (spec B-08).

The solve path and its project-hash cache move here from ``api/routes_solve.py``
(spec B-02) so ``POST /api/solve`` and the agent's ``solve`` tool are ONE solve
path with ONE cache: the route calls :func:`solve_project`, and so does the
agent loop. Repeated solves of an unchanged project return instantly.

``render_view`` renders a solved flowsheet through ``ngdesign.pipeline`` (sizers,
S-33 builder, every pid_rule at a fixed point) and the render layer's diagram
renderers, applying the view's stored placements exactly like
``GET /api/views/{pfd,pid}.svg``. All pure functions of their inputs plus one
cache — no I/O, no clock, no randomness.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from ngdesign import pipeline, registry
from ngdesign.contracts import XY, Flowsheet, Project, SolvedFlowsheet, StreamSpec, UnitSpec
from ngdesign.render.pfd_svg import render_pfd_svg
from ngdesign.render.pid_svg import render_pid_svg

#: project hash -> solved result (spec B-02: "cache by project hash"; moved here
#: from api/routes_solve.py by B-08 so both callers share one cache).
_cache: dict[str, SolvedFlowsheet] = {}


class UnknownPluginError(ValueError):
    """A unit kind or thermo model with no registered plugin (the route maps to 501)."""


class InvalidProjectError(ValueError):
    """Semantically invalid project the PUT-time contracts cannot reject (the route maps to 422)."""


def project_hash(project: Project) -> str:
    """Stable content hash of the full project model."""
    return hashlib.sha256(project.model_dump_json().encode("utf-8")).hexdigest()


def first_missing_unit_kind(project: Project) -> str | None:
    """First unit kind in the flowsheet with no registered plugin, if any."""
    known = set(registry.available("unit"))
    for spec in project.flowsheet.units:
        if spec.kind not in known:
            return spec.kind
    return None


def solve_project(
    project: Project,
    *,
    cache: dict[str, SolvedFlowsheet] | None = None,
) -> SolvedFlowsheet:
    """Solve the project: registry thermo by ``project.flowsheet.thermo`` and
    ``sequential_modular``, cached by project hash.

    ``cache`` defaults to the engine's module cache (the agent path); the HTTP
    route passes its own module dict — a locked test (tests/api/test_solve_errors.py)
    monkeypatches ``routes_solve._cache`` for isolation, so the route keeps that
    seam and injects it here. One solve path, per-caller cache instances.

    Raises :class:`UnknownPluginError` for a unit kind or thermo selection with
    no registered plugin, and :class:`InvalidProjectError` for a project whose
    declared ports and feed specs only the plugins can reject at solve time.
    """
    store = _cache if cache is None else cache
    missing = first_missing_unit_kind(project)
    if missing is not None:
        raise UnknownPluginError(f"unit kind {missing!r} has no registered plugin")
    thermo_name = project.flowsheet.thermo
    known_thermo = registry.available("thermo")
    if thermo_name not in known_thermo:
        raise UnknownPluginError(
            f"thermo model {thermo_name!r} has no registered plugin; have {known_thermo}"
        )
    key = project_hash(project)
    if key not in store:
        thermo = registry.create("thermo", thermo_name)
        try:
            store[key] = registry.create("solver", "sequential_modular").solve(project.flowsheet, thermo)
        except ValueError as exc:
            # Semantically invalid project the PUT-time contracts cannot reject:
            # declared ports and feed specs are only known to the plugins at
            # solve time (e.g. a stream naming a port the unit does not have).
            # That is client error (422), never a 500.
            raise InvalidProjectError(str(exc)) from exc
    return store[key]


def render_view(solved: SolvedFlowsheet, layout: dict[str, XY], view: str) -> bytes:
    """Render ``view`` (``"pfd"`` | ``"pid"``) as SVG bytes with the view's placements.

    The P&ID chain runs on a deep copy so sizers' datasheet attachments keep the
    cached solve result byte-identical to a bare solve (same pattern as the
    P&ID route).
    """
    if view == "pfd":
        svg = render_pfd_svg(solved, overrides=layout)
    elif view == "pid":
        pid = pipeline.build_pid(solved.model_copy(deep=True), k_gas=pipeline.DEFAULT_K_GAS)
        svg = render_pid_svg(pid, placed=layout)
    else:
        raise ValueError(f"unknown view {view!r}; have 'pfd', 'pid'")
    return svg.encode("utf-8")


def rebuild_flowsheet(
    fs: Flowsheet,
    *,
    units: list[UnitSpec] | None = None,
    streams: list[StreamSpec] | None = None,
) -> Flowsheet:
    """The flowsheet with ``units``/``streams`` replaced, revalidated through the
    pydantic contracts — the one construction path every mutating tool and
    address write shares (duplicate tags, unknown unit references, port reuse,
    feed/slate mismatches all fail here, so callers can return them as the
    tool's ``error``)."""
    return Flowsheet(
        name=fs.name,
        units=fs.units if units is None else units,
        streams=fs.streams if streams is None else streams,
        thermo=fs.thermo,
        components=fs.components,
    )


@dataclass(frozen=True)
class Engine:
    """The solve/render helpers injected into the tool loop.

    Bundles the module functions so the loop and tools never reach into engine
    module state directly and tests can substitute either helper.
    """

    solve_project: Callable[[Project], SolvedFlowsheet]
    render_view: Callable[[SolvedFlowsheet, dict[str, XY], str], bytes]


#: The engine the API injects: the real module functions.
DEFAULT_ENGINE = Engine(solve_project=solve_project, render_view=render_view)
