"""Dividing-wall (Petlyuk-equivalent) column, R2 (plan U-E 10, unit ``divided_wall``).

Plugin kind "unit", name "divided_wall", level R2 (adapter registered through
the catalogue row). Ports ``feed`` -> ``distillate`` + ``side_product`` +
``bottoms``.

One shell, four sections: a common rectifying section under the total
condenser, a common stripping section over the kettle reboiler, and between
them two parallel sections separated by the wall - the prefractionator (the
feed side) and the main side (the side-draw side). Every stage is an
equilibrium MESH stage and the whole shell is ONE equation system on the
column core's stage graph (``graph_ns``; Russell 1983, Comput. Chem. Eng. 7,
571-578, the simultaneous formulation the side strippers use): the main
cascade runs common top -> main side -> common bottom, the prefractionator is
a section appended to it with four links (``inside_out._WallSection``).

Degrees of freedom beyond a plain column, as Dejanovic, Matijasevic & Olujic
(Chem. Eng. Process. 49 (2010) 559-580) set them out: the liquid split at the
top of the wall (``liquid_split``, a fraction of the liquid leaving the stage
above the wall sent to the prefractionator - specified, it is a manipulated
variable in operation) and the vapour split at its bottom. The vapour split
is a Newton unknown with its own equation - equal pressure drop across the
two sides, the prefractionator holding ``wall_area_fraction`` of the
cross-section (``graph_ns._wall_dp_residual``, equation and sources there) -
or ``vapour_split`` when given. The remaining two column specs are the
reflux ratio and the distillate rate (top-vapour mode of the graph Newton:
V_1 = L_0 + D pinned, the boilup an unknown), plus the side-draw rate.

Initializer: the same shell without the wall (the common sections and the main
side as one plain column, the feed on the main side at the prefractionator
feed's position, the side draw where it is) through the plain column's own
spec loop; its profile seeds both wall sides, the flows divided by the splits.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

from . import _column_result
from .graph_ns import _graph_flows, _graph_liquid_profile, _graph_state, _wall_side_loads
from .inside_out import _build_column, _Column, _Profile, _WallSection
from .spec import _FLOW_FLOOR, ColumnConvergenceError, ColumnSpecError, _parse_params
from .specs import _graph_mesh_once, _solve_specs
from .thermo_adapter import _ThermoBox

_ALLOWED_PARAMS = frozenset(
    {
        "n_top",
        "n_prefractionator",
        "n_main_wall",
        "n_bottom",
        "feed_stage",
        "side_draw_stage",
        "side_draw_rate",
        "liquid_split",
        "vapour_split",
        "wall_area_fraction",
        "pressure_profile",
        "specs",
    }
)
_REQUIRED_SPECS = frozenset({"reflux_ratio", "distillate_rate"})
#: Newton pass budget of the wall solve. The seed puts the feed on the main
#: side, so the first passes move the composition fronts across the wall
#: under the shared controller's max-norm descent test (line-search steps
#: of 1/32 - 1/4): measured on equimolar BTX at 1.2 bar, 6 + 10|10 + 6 stages
#: at R = 4 needs 14 - 23 passes over liquid splits 0.5 - 0.3 (the plain
#: two-tear budget is 10), the 4 + 6|6 + 4 example at R = 3 needs 5.
_WALL_NS_MAX = 40


class DividedWallError(ColumnSpecError):
    """Invalid dividing-wall column specification (names the parameter)."""


def _count(params: dict[str, Any], key: str, minimum: int) -> int:
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise DividedWallError(f"{key} must be an integer >= {minimum}, got {value!r}")
    return value


def _fraction(value: Any, key: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise DividedWallError(f"{key} must be a number in (0, 1), got {value!r}") from exc
    if not (math.isfinite(v) and 0.0 < v < 1.0):
        raise DividedWallError(f"{key} must be in (0, 1), got {value!r}")
    return v


@dataclasses.dataclass(frozen=True)
class _WallParams:
    """Validated dividing-wall geometry and splits."""

    n_top: int
    n_pre: int
    n_main: int
    n_bottom: int
    feed_stage: int
    liquid_split: float
    vapour_split: float | None
    area_fraction: float

    @property
    def n(self) -> int:
        """Main-cascade stages: common top, main side, common bottom."""
        return self.n_top + self.n_main + self.n_bottom


def _parse_wall(params: dict[str, Any]) -> _WallParams:
    unknown = sorted(set(params) - _ALLOWED_PARAMS)
    if unknown:
        raise DividedWallError(f"divided_wall refuses unknown parameters {unknown}")
    n_pre = _count(params, "n_prefractionator", 1)
    feed_stage = _count(params, "feed_stage", 1)
    if feed_stage > n_pre:
        raise DividedWallError(
            f"feed_stage must be in 1..{n_pre} (a prefractionator stage), got {feed_stage}"
        )
    raw_v = params.get("vapour_split")
    return _WallParams(
        n_top=_count(params, "n_top", 1),
        n_pre=n_pre,
        n_main=_count(params, "n_main_wall", 1),
        n_bottom=_count(params, "n_bottom", 2),
        feed_stage=feed_stage,
        liquid_split=_fraction(params.get("liquid_split"), "liquid_split"),
        vapour_split=None if raw_v is None else _fraction(raw_v, "vapour_split"),
        area_fraction=_fraction(params.get("wall_area_fraction", 0.5), "wall_area_fraction"),
    )


def _attach_wall(col: _Column, wp: _WallParams) -> None:
    """Give a built main-cascade column its prefractionator (graph stages
    n .. n + n_pre - 1). Each prefractionator stage sits at the pressure of
    the matching height between the stages above and below the wall."""
    above, below = wp.n_top - 1, wp.n_top + wp.n_main
    p_a, p_b = col.pressures[above], col.pressures[below]
    col.pressures = col.pressures[: col.n] + [
        p_a + (p_b - p_a) * (k + 1) / (wp.n_pre + 1) for k in range(wp.n_pre)
    ]
    col.wall = _WallSection(
        above=above,
        below=below,
        stages=tuple(range(col.n, col.n + wp.n_pre)),
        liquid_split=wp.liquid_split,
        vapour_split=wp.vapour_split,
        area_fraction=wp.area_fraction,
    )


def _main_side_twin(wp: _WallParams, k: int) -> int:
    """The main-side stage (0-based) at the height of prefractionator stage k
    (0-based): the initializer's feed position and each seed stage's source."""
    return wp.n_top + min(k * wp.n_main // wp.n_pre, wp.n_main - 1)


def _seed_wall(col: _Column, wp: _WallParams, seed: _Profile, beta: float) -> _Profile:
    """Extend the wall-free initializer's converged profile over the wall.

    Both wall sides start from the plain column's profile at their height;
    the main side keeps (1 - beta) of its vapour, the prefractionator takes
    beta of it; the liquids follow from the graph's total balances (the
    liquid split included) at those vapours.
    """
    wall = col.wall
    assert wall is not None
    n = col.n
    xs = [dict(seed.x[j]) for j in range(n)]
    ys = [dict(seed.y[j]) for j in range(n)]
    ts = list(seed.T[:n])
    vs = list(seed.V[:n])
    for j in range(wall.above + 1, wall.below):
        vs[j] = max((1.0 - beta) * seed.V[j], _FLOW_FLOOR)
    for k in range(len(wall.stages)):
        twin = _main_side_twin(wp, k)
        xs.append(dict(seed.x[twin]))
        ys.append(dict(seed.y[twin]))
        ts.append(seed.T[twin])
        vs.append(max(beta * seed.V[twin], _FLOW_FLOOR))
    prof = _Profile(T=ts, V=vs, L=[_FLOW_FLOOR] * col.n_graph, x=xs, y=ys, l0=seed.l0)
    prof.draw_flows = [beta * vs[wall.below]]
    model, _xs, _ts, gvs, draw_flows = _graph_state(col, prof)
    prof.L = _graph_liquid_profile(model, prof.l0, gvs, draw_flows)
    return prof


def _wall_info(col: _Column, tb: _ThermoBox, prof: _Profile) -> dict[str, float]:
    """The wall's converged splits and hydraulics as info keys."""
    wall = col.wall
    assert wall is not None
    model, _xs, ts, vs, draw_flows = _graph_state(col, prof)
    _liquid, l_wall = _graph_flows(model, prof.l0, vs, draw_flows)
    v_split = draw_flows[-1]
    info = {
        "n_graph_stages": float(col.n_graph),
        "ns_passes": float(prof.ns_passes),
        "wall_above_stage": float(wall.above),
        "wall_below_stage": float(wall.below),
        "prefractionator_first_stage": float(wall.stages[0]),
        "wall_liquid_split": wall.liquid_split,
        "wall_vapour_split": v_split / max(vs[wall.below], _FLOW_FLOOR),
        "wall_vapour_split_specified": float(wall.vapour_split is not None),
        "wall_area_fraction": wall.area_fraction,
        "wall_liquid_to_prefractionator_mol_s": l_wall,
        "wall_vapour_to_prefractionator_mol_s": v_split,
        "prefractionator_top_vapour_mol_s": vs[wall.stages[0]],
        "prefractionator_bottom_liquid_mol_s": prof.L[wall.stages[-1]],
    }
    loads = _wall_side_loads(model, tb, ts, vs, [dict(y) for y in prof.y])
    if loads is not None:
        pre, main = loads
        info["wall_load_prefractionator_kg_m3"] = pre
        info["wall_load_main_kg_m3"] = main
        info["wall_dp_imbalance"] = (pre - main) / max(pre + main, 1e-300)
    return info


def solve_divided_wall(inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
    """Solve the dividing-wall column; outlets ``distillate``, ``side_product``,
    ``bottoms`` (see the module docstring)."""
    feed = inlets.get("feed")
    if feed is None or feed.molar_flow <= 0.0:
        raise DividedWallError("divided_wall needs a feed inlet with a positive molar flow")
    wp = _parse_wall(params)
    specs = dict(params.get("specs") or {})
    if set(specs) != _REQUIRED_SPECS:
        raise DividedWallError(
            f"divided_wall specs must be exactly {sorted(_REQUIRED_SPECS)}, got {sorted(specs)}"
        )
    side_stage = _count(params, "side_draw_stage", 1)
    if side_stage > wp.n_main:
        raise DividedWallError(
            f"side_draw_stage must be in 1..{wp.n_main} (a main-side stage), got {side_stage}"
        )
    side_rate = params.get("side_draw_rate")
    plain = {
        "n_stages": wp.n,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": _main_side_twin(wp, wp.feed_stage - 1) + 1,
        "pressure_profile": params.get("pressure_profile", feed.P),
        "draws": [{"stage": wp.n_top + side_stage, "flow_mol_s": side_rate}],
        "specs": specs,
    }
    result = _solve_wall(feed, plain, wp, wp.n + wp.feed_stage, thermo)
    outlets = result.outlets
    return UnitResult(
        outlets={
            "distillate": outlets["distillate"],
            "side_product": outlets["side_draw"],
            "bottoms": outlets["bottoms"],
        },
        duty_W=result.duty_W,
        power_W=result.power_W,
        info=result.info,
    )


def _solve_wall(
    feed: StreamState, plain: dict[str, Any], wp: _WallParams, feed_graph_stage: int, thermo: Thermo
) -> UnitResult:
    """The wall column's solve, on the column result's ports.

    ``plain`` is the column-row params dict of the shell without its wall
    (main-cascade stages, the feed at its initializer position, draws and
    the reflux_ratio + distillate_rate specs); the wall column's feed then
    sits on graph stage ``feed_graph_stage`` (1-based: prefractionator stage
    k is n + k; a main stage is its own number).
    """
    specs = plain["specs"]
    graph_feed = {
        "T": feed.T,
        "P": feed.P,
        "molar_flow": feed.molar_flow,
        "composition": dict(feed.composition),
    }
    try:
        parsed_plain = _parse_params(plain, graph_feed)
    except ColumnSpecError as exc:
        raise DividedWallError(str(exc)) from exc
    # The shell's pressures are given over the main cascade (top to bottom).
    parsed = dataclasses.replace(
        parsed_plain,
        feeds=[dataclasses.replace(parsed_plain.feeds[0], stage=feed_graph_stage)],
    )
    tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
    col = _build_column(parsed, tb)
    _attach_wall(col, wp)

    # Initializer: the shell without its wall, on the same specs.
    plain_col = _build_column(parsed_plain, tb)
    seed = _solve_specs(plain_col, tb, parsed_plain)
    beta0 = wp.vapour_split if wp.vapour_split is not None else wp.area_fraction
    prof = _seed_wall(col, wp, seed, beta0)
    l0 = float(specs["reflux_ratio"]) * float(specs["distillate_rate"])
    v_top = l0 + float(specs["distillate_rate"])
    try:
        prof = _graph_mesh_once(col, tb, l0, None, prof, top_vapour=v_top, ns_max=_WALL_NS_MAX)
    except ColumnConvergenceError as exc:
        raise ColumnConvergenceError(f"divided_wall: {exc}") from exc

    result, _internal = _column_result(col, tb, parsed, prof, feed)
    info = dict(result.info)
    info.update(_wall_info(col, tb, prof))
    return result.model_copy(update={"info": info})


class DividedWallR2:
    """Dividing-wall column: one stage-graph MESH solve over both wall sides."""

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "side_product", "bottoms")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        return solve_divided_wall(inlets, params, thermo)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Benzene/toluene/o-xylene, equimolar, 100 mol/s subcooled liquid at
        1.2 bar; 4 + 6|6 + 4 stages, the three products a third each."""
        feed = {
            "T": 370.0,
            "P": 1.2e5,
            "molar_flow": 100.0,
            "composition": {"benzene": 1.0 / 3.0, "toluene": 1.0 / 3.0, "o-xylene": 1.0 / 3.0},
        }
        params = {
            "n_top": 4,
            "n_prefractionator": 6,
            "n_main_wall": 6,
            "n_bottom": 4,
            "feed_stage": 3,
            "side_draw_stage": 3,
            "side_draw_rate": 100.0 / 3.0,
            "liquid_split": 0.35,
            "pressure_profile": 1.2e5,
            "specs": {"reflux_ratio": 3.0, "distillate_rate": 100.0 / 3.0},
        }
        return {"feed": feed}, params
