"""Column parameters, shared solver constants and typed errors (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file: validated, typed
column parameters (stages, condenser/reboiler kinds, feeds, draws, pressure
profile, operating specs), the iteration budgets and tolerances shared by the
solver modules, and the two typed errors they raise.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: Iteration budgets. Non-convergence raises a typed error; it never hangs.
_OUTER_MAX = 40
_OUTER_DAMP = 0.5  # feedback damping on model and profile updates between sweeps

#: Between-sweep profile damping for zero/one-tear columns. 1.0 = undamped
#: (measured, P1-09): the feed-traffic seed sits close enough to the operating
#: line that the half-step back toward it stalled wide absorbers in a limit
#: cycle; undamped the 8-stage absorber closes at sweep 2.
_OUTER_DAMP_ZERO_ONE = 1.0
#: Between-sweep profile damping for ONE-tear columns (kettle-only stripper,
#: total-condenser rectifier) - measured, P1-09: undamped, the frozen-model
#: update overshoots the tear neighbourhood and the walk degenerates; these
#: columns carry a single tear through the spec secant and need the
#: Boston-Sullivan style between-sweep damping the two-tear path already uses.
_OUTER_DAMP_ONE_TEAR = 0.8
_INNER_MAX = 120
_INNER_TOL = 1e-10
_NS_MAX = 10
#: Mesh acceptance gates. Stage mass residuals converge far tighter than the
#: enthalpy-line anchor floor (a few 1e-3 relative between the frozen inner
#: lines and the re-anchored exact check), so the H gate sits above that floor.
#: The overall mass/energy balances reported to the user close exactly over the
#: boundary streams regardless of these stage-level tolerances.
_MESH_M_TOL = 1e-8
_MESH_H_TOL = 1e-2
#: Stage-level M acceptance for NON-reactive zero/one-tear columns (inside-out
#: loop, NS handoff, and NS final gate alike - one gate, one number). Measured
#: P1-09 stripper (4-stage kettle, boilup sweep) on the converging branches:
#: NS's finite-difference Newton polished a warm-chained state to M=2.90e-7,
#: H=4.46e-10 and other accepted-quality solves floored at M=4.05e-8, 5.01e-8,
#: 1.02e-7, 6.87e-7 - the FD Jacobian's noise floor straddles 1e-7, so the
#: 1e-8 gate rejected measurably converged columns while the boundary-stream
#: overall balances closed far below it. 1e-6 sits just above the measured
#: floor band; the boundary balances (what users read) close exactly regardless.
_MESH_M_TOL_ZERO_ONE_TEAR = 1e-6
#: Stage-level M gate for zero/one-tear columns on a REACTIVE amine package
#: only. Measured P1-09 (20-stage MDEA absorber, amine_ke): the corrected
#: inside-out converges in 3 sweeps to a physical solution (temperature bulge
#: 281 -> 314 K, rich loading 0.502) and then stagnates at M = 5.2e-3 over
#: sweeps 3-8 - the ln Kb = A + B/T correlation tracks the reactive acid-gas
#: K-values' temperature dependence but not their composition dependence. The
#: Naphtali-Sandholm fallback is WORSE on this package: its finite-difference
#: Newton walks M uphill (measured 5.2e-3 -> 4.1e-1 over 30 passes while H
#: closed to 3e-9 - the reactive K evaluation is too noisy for FD derivatives),
#: so the inside-out floor IS the reactive floor. Gate sits just above it.
_MESH_M_TOL_REACTIVE = 1e-3
#: Loose bound separating a Naphtali-Sandholm state that reached its
#: finite-difference Newton floor from a genuinely stalled one (spec P1-10).
#: Measured P1-10 stripper on the physical branch at kettle vapour 50-76 mol/s:
#: NS converges to M = 4.2e-6 - 5.6e-6 (boundary total balance closes at
#: D + B = 100.00000000 against a 100 mol/s feed) but cannot cross the 1e-6
#: gate - the FD Jacobian's noise floor at these tears. A stalled state sits
#: at 1e-2 or worse. Below this bound the mesh hands the state to the
#: inside-out polish instead of failing the tear; the polish lifts it onto
#: the gate or the NS state stands (its floor is the measured solver limit).
_NS_FLOOR_M = 1e-3
#: Polish target for non-reactive zero/one-tear columns, two decades below the
#: 1e-6 acceptance gate (spec P1-10): the spec tests read BOUNDARY component
#: balances, and a profile accepted at the stage gate leaves ~1e-7 relative
#: component residuals at the boundary (measured P1-10 recovery case: C1 closed
#: at 1.5e-7 with a 1e-6 break). The stagnation counter bounds the effort when
#: the solver floor is above this.
_POLISH_M_TOL_ZERO_ONE_TEAR = 1e-8


def _is_reactive_package(tb: object) -> bool:
    """True when tb wraps an amine-reactive package (the spec's marker only)."""
    return bool(getattr(getattr(tb, "_thermo", tb), "is_amine_reactive_package", False))


#: Consecutive sweeps without any residual improvement before the inside-out
#: loop hands its best profile to the Naphtali-Sandholm fallback. Zero/one-tear
#: columns get a longer patience (measured in the P1-09 PR): their sweeps wobble
#: in M while H still improves for several sweeps before stalling.
_STAGNATION_MAX = 3
_STAGNATION_MAX_ZERO_ONE_TEAR = 8
#: Naphtali-Sandholm pass budget for zero/one-tear columns (measured in the
#: P1-09 PR); two-tear columns keep _NS_MAX.
_NS_MAX_ZERO_ONE_TEAR = 30
#: Ceiling on the H-solve's vapour traffic, as a multiple of the total feed
#: (mol/s). Degenerate subcooled-band walks drove free V past 1e9 mol/s and
#: singularized the tridiagonal M system; no physical column traffic approaches
#: 50x the feed (measured: the two-tear bench column never touches the cap).
_V_TRAFFIC_CAP = 50.0
#: A converged stage temperature this close (K) to t_band_lo/t_band_hi is a clamped
#: walk, not an operating point: the mesh rejects the profile (spec P1-10 item 1).
_BAND_LIMIT_EPS = 1e-6
_SPEC_MAX = 20
# Spec tolerance must sit ABOVE the mesh's own acceptance noise floor: the mesh
# accepts profiles with stage-mass residuals up to _MESH_M_TOL, and that noise
# propagates into the measured product rates (~1e-3 relative on strongly
# stressed cases). A tolerance below the floor makes the secant chase mesh
# noise instead of the spec target.
_SPEC_TOL = 5e-3

#: Floor for vapour/liquid flows (mol/s) so degenerate stages stay solvable.
_FLOW_FLOOR = 1e-9

#: Pure-component extreme seeds wider than this defer to the equilibrium-based
#: estimate (a wide span across the component list is not a usable profile).
_SEED_SPAN_MAX = 120.0

_CONDENSER_KINDS = ("total", "partial", "none")
_REBOILER_KINDS = ("kettle", "none")
_SPEC_KEYS = (
    "reflux_ratio",
    "boilup_ratio",
    "distillate_rate",
    "bottoms_rate",
    "component_recovery",
    "product_purity",
    "condenser_duty_W",
    "reboiler_duty_W",
    # S0-1 feature 4: refiner specs. Value shapes (validated in _parse_params):
    #   draw_rate:            {"name": <draw or stripper name>, "value": mol/s}
    #   stage_temperature:    {"stage": <1-indexed stage>, "value": K}
    #   pumparound_duty:      {"name": <pumparound name>, "value": W}
    #   pumparound_return_T:  {"name": <pumparound name>, "value": K}
    "draw_rate",
    "stage_temperature",
    "pumparound_duty",
    "pumparound_return_T",
)
#: Spec keys S0-1 feature 4 added. A params['specs'] dict holding any of these
#: (or a column with free tears: pumparound flows, named free draws, stripper
#: draws) solves on the generalized secant (``_solve_specs_full``), not the
#: legacy two-tear path whose benchmarked mesh sequence is locked.
_FULL_SPEC_KEYS = ("draw_rate", "stage_temperature", "pumparound_duty", "pumparound_return_T")


class ColumnSpecError(ValueError):
    """Infeasible, contradictory or unsatisfiable column specification."""


class ColumnConvergenceError(RuntimeError):
    """The column did not converge within its bounded iteration budgets."""


# --------------------------------------------------------------------------------------
# Parameters (validated once, typed)
# --------------------------------------------------------------------------------------


# --------------------------------------------------------------------------------------
# Parameters (validated once, typed)
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _FeedSpec:
    """One feed: the port stream and/or a params-level feed, assigned to a stage."""

    stage: int  # 1-indexed
    T: float
    P: float
    flow: float
    comp: dict[str, float]


@dataclass(frozen=True)
class _DrawSpec:
    """One side draw leaving an intermediate stage."""

    stage: int  # 1-indexed
    vapor: bool
    flow: float | None  # None = free tear (a draw_rate spec drives it)
    name: str | None = None


@dataclass(frozen=True)
class _Pumparound:
    """One pumparound loop: liquid drawn at ``draw_stage``, cooled externally,
    returned at ``return_stage`` (<= draw_stage, i.e. at or above) as a
    subcooled liquid feed.

    Exactly one of ``duty_W`` / ``return_T_K`` is the FIXED operating
    variable (``duty_W = 0`` with ``return_stage == draw_stage`` is the
    degenerate identity loop); the other is an outcome. Either the flow or
    the fixed variable may instead be a free tear driven by a spec
    (``pa_tear`` records which, empty when both are fixed).
    """

    name: str
    draw_stage: int  # 1-indexed
    return_stage: int  # 1-indexed, <= draw_stage
    flow_mol_s: float | None  # None = free tear
    duty_W: float | None  # fixed cooler duty, negative = heat removed
    return_T_K: float | None  # fixed return temperature
    tear: str = ""  # which variable is the free tear: "", "flow", "duty"


@dataclass(frozen=True)
class _SideStripper:
    """A side stripper coupled to the main column (S0-1 feature 2).

    Liquid is drawn from the main column at ``draw_stage``, flows down an
    ``n_stages``-stage stripper section, and its stripped overhead vapour
    returns to ``return_stage`` (at or above the draw). The stripping agent
    is either bottom steam (``steam_flow``) or a kettle reboiler
    (``reboiler_duty_W``); the stripper bottoms leave as an internal product.

    The draw rate is not configured: it is a tear of the coupled solve,
    driven by ``product_rate`` (the stripper bottoms rate) or by a
    ``draw_rate`` spec naming this stripper. ``n_stages = 0`` is the
    degenerate case: the entire draw leaves as product and nothing returns.
    """

    name: str
    draw_stage: int
    return_stage: int
    n_stages: int
    steam_flow: float | None  # steam option: bottom steam flow, mol/s (0 = none)
    steam_T: float
    steam_P: float
    reboiler_duty_W: float | None  # reboiler option: kettle duty, W
    product_rate: float | None  # stripper bottoms rate, mol/s, or free (draw_rate spec)


@dataclass(frozen=True)
class _Params:
    """Validated column parameters."""

    n_stages: int
    condenser: str
    reboiler: str
    feeds: list[_FeedSpec]
    draws: list[_DrawSpec]
    pressures: list[float]
    specs: dict[str, Any]
    pumparounds: list[_Pumparound] = field(default_factory=list)
    side_strippers: list[_SideStripper] = field(default_factory=list)
    #: S0-1 feature 3: water that the package reports as an AQUEOUS liquid
    #: phase at a total condenser leaves as a separate internal product
    #: (``water_decant``). Requires condenser == "total".
    condenser_water_decant: bool = False


def _positive(value: Any, name: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ColumnSpecError(f"{name} must be a number, got {value!r}") from exc
    if not math.isfinite(v) or v <= 0.0:
        raise ColumnSpecError(f"{name} must be a positive finite number, got {value!r}")
    return v


def _stage_index(value: Any, name: str, n_stages: int) -> int:
    try:
        s = int(value)
    except (TypeError, ValueError) as exc:
        raise ColumnSpecError(f"{name} must be an integer stage, got {value!r}") from exc
    if not 1 <= s <= n_stages:
        raise ColumnSpecError(f"{name} must be in 1..{n_stages}, got {s}")
    return s


def _parse_pressure_profile(raw: Any, n_stages: int) -> list[float]:
    if isinstance(raw, (int, float)):
        p = _positive(raw, "pressure_profile")
        return [p] * n_stages
    if isinstance(raw, dict):
        top = _positive(raw.get("top"), "pressure_profile.top")
        bottom = _positive(raw.get("bottom"), "pressure_profile.bottom")
        if n_stages == 1:
            return [top]
        step = (bottom - top) / (n_stages - 1)
        return [top + step * j for j in range(n_stages)]
    if isinstance(raw, (list, tuple)):
        if len(raw) != n_stages:
            raise ColumnSpecError(f"pressure_profile list needs {n_stages} values, got {len(raw)}")
        return [_positive(p, "pressure_profile") for p in raw]
    raise ColumnSpecError(f"pressure_profile must be a number, list or top/bottom dict, got {raw!r}")


def _parse_comp_spec(spec: dict[str, Any], key: str, support: set[str]) -> dict[str, Any]:
    comp = str(spec.get("component", ""))
    if comp not in support:
        raise ColumnSpecError(f"specs.{key} component {comp!r} is not in the feed support")
    product = str(spec.get("product", "distillate"))
    if product not in ("distillate", "bottoms"):
        raise ColumnSpecError(f"specs.{key}.product must be 'distillate' or 'bottoms'")
    raw_value = spec.get("value", spec.get("fraction", spec.get("mole_fraction")))
    value = _positive(raw_value, f"specs.{key}")
    if not 0.0 < value < 1.0:
        raise ColumnSpecError(f"specs.{key} value must be in (0, 1), got {value}")
    return {"component": comp, "product": product, "value": value}


def _parse_params(params: dict[str, Any], graph_feed: dict[str, Any] | None) -> _Params:
    """Validate params (and the optional port feed) into typed structures."""
    try:
        n_stages = int(params.get("n_stages"))  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ColumnSpecError(f"n_stages must be an integer, got {params.get('n_stages')!r}") from exc
    if n_stages < 2:
        raise ColumnSpecError(f"n_stages must be >= 2, got {n_stages}")

    condenser = str(params.get("condenser", "total"))
    if condenser not in _CONDENSER_KINDS:
        raise ColumnSpecError(f"condenser must be one of {_CONDENSER_KINDS}, got {condenser!r}")
    reboiler = str(params.get("reboiler", "kettle"))
    if reboiler not in _REBOILER_KINDS:
        raise ColumnSpecError(f"reboiler must be one of {_REBOILER_KINDS}, got {reboiler!r}")

    feeds: list[_FeedSpec] = []
    if graph_feed is not None:
        feed_stage = _stage_index(params.get("feed_stage", max(1, n_stages // 2)), "feed_stage", n_stages)
        feeds.append(
            _FeedSpec(
                stage=feed_stage,
                T=_positive(graph_feed.get("T"), "feed T"),
                P=_positive(graph_feed.get("P"), "feed P"),
                flow=_positive(graph_feed.get("molar_flow"), "feed molar_flow"),
                comp={k: float(v) for k, v in dict(graph_feed.get("composition", {})).items()},
            )
        )
    raw_feeds = params.get("feeds", [])
    if not isinstance(raw_feeds, (list, tuple)):
        raise ColumnSpecError("feeds must be a list of feed dicts")
    for k, raw in enumerate(raw_feeds):
        d = dict(raw)
        comp = {key: float(v) for key, v in dict(d.get("composition", {})).items()}
        if not comp:
            raise ColumnSpecError(f"feeds[{k}] has no composition")
        feeds.append(
            _FeedSpec(
                stage=_stage_index(d.get("stage"), f"feeds[{k}].stage", n_stages),
                T=_positive(d.get("T"), f"feeds[{k}].T"),
                P=_positive(d.get("P"), f"feeds[{k}].P"),
                flow=_positive(d.get("molar_flow"), f"feeds[{k}].molar_flow"),
                comp=comp,
            )
        )
    if not feeds:
        raise ColumnSpecError("column needs a feed: connect the 'feed' port or list params['feeds']")

    raw_draws = params.get("draws", [])
    if not isinstance(raw_draws, (list, tuple)):
        raise ColumnSpecError("draws must be a list of draw dicts")
    draws: list[_DrawSpec] = []
    for k, raw in enumerate(raw_draws):
        d = dict(raw)
        phase = str(d.get("phase", "liquid"))
        if phase not in ("liquid", "vapor"):
            raise ColumnSpecError(f"draws[{k}].phase must be 'liquid' or 'vapor', got {phase!r}")
        stage = _stage_index(d.get("stage"), f"draws[{k}].stage", n_stages)
        flow = d.get("flow_mol_s")
        if flow is not None:
            flow = _positive(flow, f"draws[{k}].flow_mol_s")
        name = d.get("name")
        if name is not None and (not isinstance(name, str) or not name):
            raise ColumnSpecError(f"draws[{k}].name must be a non-empty string")
        if flow is None and name is None:
            raise ColumnSpecError(
                f"draws[{k}]: a draw without flow_mol_s needs a name (a draw_rate spec drives it)"
            )
        # A named draw without flow_mol_s is a free tear: a draw_rate spec
        # (S0-1 feature 4) drives it, and the count rule in _tear_names
        # refuses the config when no such spec exists.
        draws.append(_DrawSpec(stage=stage, vapor=phase == "vapor", flow=flow, name=name))
    total_draws = sum(d.flow for d in draws if d.flow is not None)
    total_feeds = sum(f.flow for f in feeds)
    if total_draws >= total_feeds:
        raise ColumnSpecError(
            f"total draw flow {total_draws} mol/s leaves nothing of the {total_feeds} mol/s feed"
        )

    specs = dict(params.get("specs", {}))
    unknown = set(specs) - set(_SPEC_KEYS)
    if unknown:
        raise ColumnSpecError(f"unknown spec keys {sorted(unknown)}; allowed: {list(_SPEC_KEYS)}")
    pumparounds = _parse_pumparounds(params, n_stages)
    strippers = _parse_side_strippers(params, n_stages)
    decant = _parse_decant(params, condenser)
    _validate_full_specs(specs, pumparounds, draws, strippers, n_stages)
    n_tears = (1 if condenser != "none" else 0) + (1 if reboiler != "none" else 0)
    tear_list = _tear_names(condenser, reboiler, pumparounds, draws, strippers)
    n_drivers = len(specs) + sum(1 for st in strippers if st.product_rate is not None)
    if len(tear_list) != n_drivers:
        legacy = (
            not strippers
            and not any(pa.flow_mol_s is None for pa in pumparounds)
            and not any(d.flow is None for d in draws)
            and not any(k in specs for k in _FULL_SPEC_KEYS)
        )
        if legacy:
            raise ColumnSpecError(
                f"this column has {n_tears} degrees of freedom ({condenser} condenser, "
                f"{reboiler} reboiler) and needs exactly {n_tears} specs, got {len(specs)}"
            )
        raise ColumnSpecError(
            f"spec count ({n_drivers}: {sorted(_spec_driver_names(specs, strippers))}) must equal "
            f"tear count ({len(tear_list)}: {tear_list}); every tear needs exactly one driver"
        )
    if condenser == "none" and ("reflux_ratio" in specs or "condenser_duty_W" in specs):
        raise ColumnSpecError("reflux_ratio/condenser_duty_W specs need a condenser (condenser='none')")
    if condenser == "partial" and "reflux_ratio" in specs:
        raise ColumnSpecError(
            "reflux_ratio needs a total condenser (the mesh pins condenser-stage vapour traffic "
            "directly and carries no reflux tear for condenser='partial'); use distillate_rate "
            "with a duty or purity/recovery spec instead"
        )
    if reboiler == "none" and ("boilup_ratio" in specs or "reboiler_duty_W" in specs):
        raise ColumnSpecError("boilup_ratio/reboiler_duty_W specs need a reboiler (reboiler='none')")
    if "distillate_rate" in specs and "bottoms_rate" in specs:
        raise ColumnSpecError(
            "distillate_rate + bottoms_rate do not determine a column: D + B = F is forced while "
            "internal vapour/liquid traffic stays free. Replace one with reflux_ratio, boilup_ratio, "
            "a duty, or a purity/recovery spec."
        )
    room = total_feeds - total_draws
    for key in ("distillate_rate", "bottoms_rate"):
        if key in specs:
            rate = _positive(specs[key], f"specs.{key}")
            if rate >= room:
                raise ColumnSpecError(
                    f"specs.{key} {rate} mol/s is not achievable: only {room} mol/s of feed "
                    f"is available after draws"
                )
    for key in (
        "reflux_ratio",
        "boilup_ratio",
        "distillate_rate",
        "bottoms_rate",
        "condenser_duty_W",
        "reboiler_duty_W",
    ):
        if key in specs:
            _positive(specs[key], f"specs.{key}")
    support = {c for f in feeds for c in f.comp}
    for key in ("component_recovery", "product_purity"):
        if key in specs:
            specs[key] = _parse_comp_spec(dict(specs[key]), key, support)

    return _Params(
        n_stages=n_stages,
        condenser=condenser,
        reboiler=reboiler,
        feeds=feeds,
        draws=draws,
        pressures=_parse_pressure_profile(params.get("pressure_profile", params.get("P")), n_stages),
        specs=specs,
        pumparounds=pumparounds,
        side_strippers=strippers,
        condenser_water_decant=decant,
    )


def _spec_driver_names(specs: dict[str, Any], strippers: list[_SideStripper]) -> list[str]:
    """Both driver lists, for the count-mismatch refusal (S0-1: 'naming both lists')."""
    names = list(specs)
    names += [f"stripper:{st.name}.product_rate_mol_s" for st in strippers if st.product_rate is not None]
    return names


def _parse_pumparounds(params: Mapping[str, Any], n_stages: int) -> list[_Pumparound]:
    """Parse and validate ``params["pumparounds"]`` (list of pumparound loops)."""
    raw = params.get("pumparounds", [])
    if not isinstance(raw, (list, tuple)):
        raise ColumnSpecError("pumparounds must be a list of pumparound dicts")
    # The duty stages are excluded hardware (review item 2, PR #238): the
    # condenser and kettle-reboiler stage balances define qc/qr and carry no
    # pumparound terms, so a loop touching them would report silently wrong
    # duties. With no such hardware the stage is an ordinary tray and allowed.
    condenser = str(params.get("condenser", "total"))
    reboiler = str(params.get("reboiler", "kettle"))
    forbidden_stages: list[tuple[int, str]] = []
    if condenser != "none":
        forbidden_stages.append((1, "the condenser stage (the condenser's own balance defines qc)"))
    if reboiler == "kettle":
        forbidden_stages.append((n_stages, "the reboiler stage (the kettle's own balance defines qr)"))
    pas: list[_Pumparound] = []
    names: set[str] = set()
    for k, item in enumerate(raw):
        pa = dict(item)
        draw_stage = _stage_index(pa.get("draw_stage"), f"pumparounds[{k}].draw_stage", n_stages)
        return_stage = _stage_index(pa.get("return_stage"), f"pumparounds[{k}].return_stage", n_stages)
        for stage, why in forbidden_stages:
            if draw_stage == stage or return_stage == stage:
                which = "draw_stage" if draw_stage == stage else "return_stage"
                raise ColumnSpecError(
                    f"pumparounds[{k}]: {which} {stage} is {why}; "
                    f"pumparounds on duty stages would report wrong duties"
                )
        if return_stage > draw_stage:
            raise ColumnSpecError(
                f"pumparounds[{k}]: return_stage {return_stage} must be at or above "
                f"draw_stage {draw_stage} (a pumparound returns cooled liquid higher in the tower)"
            )
        flow = pa.get("flow_mol_s")
        if flow is not None:
            flow = _positive(flow, f"pumparounds[{k}].flow_mol_s")
        # A pumparound without flow_mol_s is a free tear: a pumparound_duty
        # or pumparound_return_T spec (S0-1 feature 4) drives it, and the
        # count rule refuses the config when no such spec exists.
        duty = pa.get("duty_W")
        if duty is not None:
            try:
                duty = float(duty)
            except (TypeError, ValueError) as exc:
                raise ColumnSpecError(f"pumparounds[{k}].duty_W must be a number, got {duty!r}") from exc
            if not math.isfinite(duty) or duty > 0.0:
                raise ColumnSpecError(
                    f"pumparounds[{k}].duty_W must be <= 0 (a pumparound cooler removes heat)"
                )
        return_t = pa.get("return_T_K")
        if return_t is not None:
            return_t = _positive(return_t, f"pumparounds[{k}].return_T_K")
        if (duty is None) == (return_t is None):
            raise ColumnSpecError(f"pumparounds[{k}]: exactly one of duty_W / return_T_K is required")
        name = pa.get("name")
        if name is None:
            name = str(k + 1)  # info keys read pa_1_duty_W, not pa_pa_1_duty_W (review item 8)
        if not isinstance(name, str) or not name:
            raise ColumnSpecError(f"pumparounds[{k}].name must be a non-empty string")
        if name in names:
            raise ColumnSpecError(f"pumparounds: duplicate name {name!r}")
        names.add(name)
        pas.append(
            _Pumparound(
                name=name,
                draw_stage=draw_stage,
                return_stage=return_stage,
                flow_mol_s=flow,
                duty_W=duty,
                return_T_K=return_t,
                tear="flow" if flow is None else "",
            )
        )
    return pas


def _parse_side_strippers(params: Mapping[str, Any], n_stages: int) -> list[_SideStripper]:
    """Parse and validate ``params["side_strippers"]`` (S0-1 feature 2)."""
    raw = params.get("side_strippers", [])
    if not isinstance(raw, (list, tuple)):
        raise ColumnSpecError("side_strippers must be a list of side-stripper dicts")
    # Like pumparounds, a stripper draw may not sit on a duty stage: the
    # condenser and kettle balances define qc/qr and carry no draw terms.
    condenser = str(params.get("condenser", "total"))
    reboiler = str(params.get("reboiler", "kettle"))
    forbidden_stages: list[tuple[int, str]] = []
    if condenser != "none":
        forbidden_stages.append((1, "the condenser stage (the condenser's own balance defines qc)"))
    if reboiler == "kettle":
        forbidden_stages.append((n_stages, "the reboiler stage (the kettle's own balance defines qr)"))
    strippers: list[_SideStripper] = []
    names: set[str] = set()
    for k, item in enumerate(raw):
        st = dict(item)
        draw_stage = _stage_index(st.get("draw_stage"), f"side_strippers[{k}].draw_stage", n_stages)
        return_stage = _stage_index(st.get("return_stage"), f"side_strippers[{k}].return_stage", n_stages)
        for stage, why in forbidden_stages:
            if draw_stage == stage:
                raise ColumnSpecError(
                    f"side_strippers[{k}]: draw_stage {stage} is {why}; "
                    f"stripper draws on duty stages would report wrong duties"
                )
        if return_stage > draw_stage:
            raise ColumnSpecError(
                f"side_strippers[{k}]: return_stage {return_stage} must be at or above "
                f"draw_stage {draw_stage} (the stripped overhead vapour returns above the draw)"
            )
        n = st.get("n_stages")
        if n is None:
            raise ColumnSpecError(f"side_strippers[{k}]: n_stages is required (0 = plain liquid draw)")
        try:
            n_strippers = int(n)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ColumnSpecError(f"side_strippers[{k}].n_stages must be an integer, got {n!r}") from exc
        if n_strippers < 0:
            raise ColumnSpecError(f"side_strippers[{k}].n_stages must be >= 0, got {n_strippers}")
        if n_strippers == 1:
            raise ColumnSpecError(
                f"side_strippers[{k}].n_stages must be 0 (plain liquid draw) or >= 2 "
                f"(the mesh solves at least 2 equilibrium stages; 1 is not solvable)"
            )
        steam = st.get("steam")
        duty = st.get("reboiler_duty_W")
        if (steam is None) == (duty is None):
            raise ColumnSpecError(
                f"side_strippers[{k}]: exactly one of steam (a dict) / reboiler_duty_W is required"
            )
        steam_flow = steam_T = steam_P = 0.0
        if steam is not None:
            s = dict(steam)
            flow_raw = s.get("flow_mol_s", 0.0)
            try:
                steam_flow = float(flow_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ColumnSpecError(
                    f"side_strippers[{k}].steam.flow_mol_s must be a number, got {flow_raw!r}"
                ) from exc
            if not math.isfinite(steam_flow) or steam_flow < 0.0:
                raise ColumnSpecError(
                    f"side_strippers[{k}].steam.flow_mol_s must be >= 0 (0 = no steam), got {steam_flow!r}"
                )
            steam_T = _positive(s.get("T_K"), f"side_strippers[{k}].steam.T_K")
            steam_P = _positive(s.get("P_Pa"), f"side_strippers[{k}].steam.P_Pa")
        else:
            try:
                duty_val = float(duty)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ColumnSpecError(f"side_strippers[{k}].reboiler_duty_W must be a number, got {duty!r}") from exc
            if not math.isfinite(duty_val) or duty_val < 0.0:
                raise ColumnSpecError(
                    f"side_strippers[{k}].reboiler_duty_W must be >= 0 (heat added), got {duty_val!r}"
                )
        rate_raw = st.get("product_rate_mol_s")
        product_rate: float | None = None
        if rate_raw is not None:
            product_rate = _positive(rate_raw, f"side_strippers[{k}].product_rate_mol_s")
        name = st.get("name")
        if name is None:
            name = str(k + 1)
        if not isinstance(name, str) or not name:
            raise ColumnSpecError(f"side_strippers[{k}].name must be a non-empty string")
        if name in names:
            raise ColumnSpecError(f"side_strippers: duplicate name {name!r}")
        names.add(name)
        strippers.append(
            _SideStripper(
                name=name,
                draw_stage=draw_stage,
                return_stage=return_stage,
                n_stages=n_strippers,
                steam_flow=steam_flow if steam is not None else None,
                steam_T=steam_T,
                steam_P=steam_P,
                reboiler_duty_W=float(duty) if duty is not None else None,  # type: ignore[arg-type]
                product_rate=product_rate,
            )
        )
    draw_names = set()
    for d in params.get("draws", []) or []:
        if isinstance(d, Mapping) and d.get("name") is not None:
            draw_names.add(str(d["name"]))
    for st in strippers:
        if st.name in draw_names:
            raise ColumnSpecError(
                f"side_strippers: name {st.name!r} collides with a named draw; info keys would overlap"
            )
    return strippers


def _parse_decant(params: Mapping[str, Any], condenser: str) -> bool:
    """Parse ``params["condenser_water_decant"]`` (S0-1 feature 3)."""
    raw = params.get("condenser_water_decant", False)
    if not isinstance(raw, bool):
        raise ColumnSpecError(f"condenser_water_decant must be a bool, got {raw!r}")
    if raw and condenser != "total":
        raise ColumnSpecError(
            "condenser_water_decant needs a total condenser: the decant lives at the "
            f"condensate split, and condenser={condenser!r} has no condensate"
        )
    return raw


def _parse_named_spec(spec: dict[str, Any], key: str) -> dict[str, Any]:
    """Normalize a ``{name|stage, value}`` refiner spec (S0-1 feature 4)."""
    if key == "stage_temperature":
        raw_stage = spec.get("stage")
        try:
            stage = int(raw_stage)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ColumnSpecError(f"specs.stage_temperature.stage must be an integer, got {raw_stage!r}") from exc
        return {"stage": stage, "value": _positive(spec.get("value"), "specs.stage_temperature.value")}
    name = str(spec.get("name", ""))
    if not name:
        raise ColumnSpecError(f"specs.{key} needs a 'name' (the draw, stripper or pumparound it drives)")
    if key == "pumparound_duty":
        # Sign convention matches the reported pa_<name>_duty_W (negative =
        # heat removed by the cooler); only finiteness and non-zero apply.
        raw = spec.get("value")
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ColumnSpecError(f"specs.pumparound_duty.value must be a finite number, got {raw!r}") from exc
        if not math.isfinite(value) or value == 0.0:
            raise ColumnSpecError(f"specs.pumparound_duty.value must be a non-zero finite number, got {raw!r}")
        return {"name": name, "value": value}
    return {"name": name, "value": _positive(spec.get("value"), f"specs.{key}.value")}


def _validate_full_specs(
    specs: dict[str, Any],
    pumparounds: list[_Pumparound],
    draws: list[_DrawSpec],
    strippers: list[_SideStripper],
    n_stages: int,
) -> None:
    """Pair the S0-1 feature 4 specs with the tears they drive (parse time).

    Every refusal here names the spec key, so an unsatisfiable configuration
    fails before any solve, on an input the column could otherwise converge.
    """
    free_pas = {pa.name: pa for pa in pumparounds if pa.flow_mol_s is None}
    free_draws = {d.name for d in draws if d.flow is None}
    stripper_map = {st.name: st for st in strippers}
    draw_rate_names: set[str] = set()
    for key in _FULL_SPEC_KEYS:
        if key not in specs:
            continue
        spec = specs[key] = _parse_named_spec(dict(specs[key]), key)
        if key == "stage_temperature":
            _stage_index(spec["stage"], "specs.stage_temperature.stage", n_stages)
            continue
        name = spec["name"]
        if key == "draw_rate":
            if name in draw_rate_names:
                raise ColumnSpecError(f"specs.draw_rate: target {name!r} is driven twice")
            if name in free_draws:
                draw_rate_names.add(name)
            elif name in stripper_map:
                if stripper_map[name].product_rate is not None:
                    raise ColumnSpecError(
                        f"specs.draw_rate {name!r}: the stripper already has product_rate_mol_s; "
                        f"give one driver, not both"
                    )
                draw_rate_names.add(name)
            else:
                raise ColumnSpecError(
                    f"specs.draw_rate: no free draw or stripper named {name!r} "
                    f"(free draws: {sorted(free_draws)}, strippers: {sorted(stripper_map)})"
                )
        elif key == "pumparound_duty":
            pa = free_pas.get(name)
            if pa is None:
                raise ColumnSpecError(
                    f"specs.pumparound_duty: no pumparound with a free flow_mol_s named {name!r} "
                    f"(a duty spec drives the loop flow, so the flow must be unset and return_T_K fixed)"
                )
            if pa.return_T_K is None:
                raise ColumnSpecError(
                    f"specs.pumparound_duty {name!r}: duty_W must be unset (it is the quantity the spec drives)"
                )
        elif key == "pumparound_return_T":
            pa = free_pas.get(name)
            if pa is None:
                raise ColumnSpecError(
                    f"specs.pumparound_return_T: no pumparound with a free flow_mol_s named {name!r} "
                    f"(a return-temperature spec drives the loop flow, so the flow must be unset and duty_W fixed)"
                )
            if pa.duty_W is None:
                raise ColumnSpecError(
                    f"specs.pumparound_return_T {name!r}: return_T_K must be unset (it is the quantity the spec drives)"
                )
    for st in strippers:
        if st.product_rate is None and st.name not in draw_rate_names:
            raise ColumnSpecError(
                f"side_strippers[{st.name!r}]: the stripper draw has no driver; give "
                f"product_rate_mol_s or a draw_rate spec naming it"
            )


def _tear_names(
    condenser: str,
    reboiler: str,
    pumparounds: list[_Pumparound],
    draws: list[_DrawSpec],
    strippers: list[_SideStripper],
) -> list[str]:
    """The named free tears of the generalized solve (S0-1 feature 4).

    Every stripper draw is a tear (driven by ``product_rate_mol_s`` or a
    ``draw_rate`` spec); free pumparound flows and named free draws are tears
    driven by their specs. The count rule: one driver per tear.
    """
    names: list[str] = []
    if condenser != "none":
        names.append("top")
    if reboiler == "kettle":
        names.append("boilup")
    names += [f"pumparound:{pa.name}" for pa in pumparounds if pa.flow_mol_s is None]
    names += [f"draw:{d.name}" for d in draws if d.flow is None]
    names += [f"stripper:{st.name}" for st in strippers]
    return names
