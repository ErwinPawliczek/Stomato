"""Column parameters, shared solver constants and typed errors (spec P1-03).

Moved unchanged from the former ``units/column.py`` god-file: validated, typed
column parameters (stages, condenser/reboiler kinds, feeds, draws, pressure
profile, operating specs), the iteration budgets and tolerances shared by the
solver modules, and the two typed errors they raise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
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
_MESH_M_TOL_REACTIVE = 1e-2
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
)


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
    flow: float


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
        draws.append(
            _DrawSpec(
                stage=_stage_index(d.get("stage"), f"draws[{k}].stage", n_stages),
                vapor=phase == "vapor",
                flow=_positive(d.get("flow_mol_s"), f"draws[{k}].flow_mol_s"),
            )
        )
    total_draws = sum(d.flow for d in draws)
    total_feeds = sum(f.flow for f in feeds)
    if total_draws >= total_feeds:
        raise ColumnSpecError(
            f"total draw flow {total_draws} mol/s leaves nothing of the {total_feeds} mol/s feed"
        )

    specs = dict(params.get("specs", {}))
    unknown = set(specs) - set(_SPEC_KEYS)
    if unknown:
        raise ColumnSpecError(f"unknown spec keys {sorted(unknown)}; allowed: {list(_SPEC_KEYS)}")
    n_tears = (1 if condenser != "none" else 0) + (1 if reboiler != "none" else 0)
    if len(specs) != n_tears:
        raise ColumnSpecError(
            f"this column has {n_tears} degrees of freedom ({condenser} condenser, "
            f"{reboiler} reboiler) and needs exactly {n_tears} specs, got {len(specs)}"
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
    )
