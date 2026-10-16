"""Rigorous equilibrium-stage vapour-liquid equilibrium column. Plugin kind "unit", name "column".

A staged distillation/absorption column on the shared Peng-Robinson thermo plugin.
N equilibrium stages numbered 1..N top to bottom; the kettle reboiler is stage N
and a partial condenser is stage 1. A total condenser is hardware *above* stage 1
(it adds no separation: x_D = y_1, the McCabe-Thiele convention), so stage 1
remains a normal equilibrium tray whose overhead vapour V_1 is fully condensed
into reflux L_0 + distillate D.

Method (primary): Boston-Sullivan inside-out. Outer sweeps refresh real K-values
stage by stage from ``thermo.flash_pt`` and refit the frozen inner models - per
stage relative volatilities alpha_ij = K_ij / Kb_j against one column-wide
reference component, the two-parameter correlation ln Kb = A + B/T (Boston &
Sullivan 1974, "An Improved Algorithm for Solving Mass Balance Equations in
Multistage Separation Processes", Can. J. Chem. Eng. 52, 52-63), and linear
per-phase enthalpy models H(T) = h0 + cp*(T - T_ref). The inner loop then solves
MESH with those frozen models only (no thermo calls): component balances as a
tridiagonal system (Thomas algorithm), bubble equations Kb_j = 1/(sum_i
alpha_ij x_ij), stage temperatures from the Kb correlation, and the enthalpy
balances as a damped Newton system for the vapour profile. This keeps the
expensive PT flashes (17-23 ms each) on the outer sweeps only; PH/PS flashes
(~112 ms) are never used.

Fallback: if the inside-out loop fails to converge, a Naphtali-Sandholm style
simultaneous Newton corrects (x, T, V) together against the MESH residuals with
K-values frozen between Newton passes and refreshed from the thermo plugin each
pass (Naphtali & Sandholm 1971, "Multicomponent Separation Calculations by
Linearization", AIChE J. 17(1), 148-153: the equations are grouped by stage and
linearized; the K-composition coupling is updated between passes).

Boundary structure: the column's degrees of freedom are its boundary flows -
the top tear (reflux L_0 for a total condenser, distillate D for a partial
condenser) and the bottom tear (boilup V_N for a kettle reboiler). A
condenserless stage's vapour and a reboilerless stage's vapour are outcomes of
their enthalpy balances, as are all duties. The number of required column specs
therefore equals the number of tears: two for a condenser+reboiler column, one
for a stripper or a rectifier-without-reboiler, zero for a feed-determined
absorber. Specs are driven to their targets by a bounded Broyden secant loop
over the tears.

Per-phase enthalpies: the thermo contract exposes only mixture enthalpies, so
liquid/vapour phase enthalpies come from single-phase flashes just outside the
two-phase region with a linear extrapolation to stage temperature. The reboiler
duty is finally defined by the exact overall energy balance over the real
boundary streams given the condenser-duty balance, so the reported duty closes
the stream table exactly (module users get a consistent UnitResult.duty_W; the
Qc/Qr split is accurate to the converged stage-balance residual).

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register

#: Iteration budgets. Non-convergence raises a typed error; it never hangs.
_OUTER_MAX = 40
_OUTER_DAMP = 0.5  # feedback damping on model and profile updates between sweeps
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


def _thomas(sub: list[float], diag: list[float], up: list[float], rhs: list[float]) -> list[float]:
    """Thomas algorithm for the tridiagonal system sub*x + diag*x + up*x = rhs.

    The M-equation matrix is diagonally dominant here (|diag| = L + V*K dominates
    its neighbours), so no pivoting is needed; a vanishing pivot is a convergence
    failure, not a case for a silent fix.
    """
    n = len(diag)
    if abs(diag[0]) < 1e-300:
        raise ColumnConvergenceError("singular tridiagonal system in stage balances")
    if n == 1:
        return [rhs[0] / diag[0]]
    cp = [0.0] * n
    dp = [0.0] * n
    cp[0] = up[0] / diag[0]
    dp[0] = rhs[0] / diag[0]
    for j in range(1, n):
        m = diag[j] - sub[j] * cp[j - 1]
        if abs(m) < 1e-300:
            raise ColumnConvergenceError("singular tridiagonal system in stage balances")
        cp[j] = up[j] / m if j < n - 1 else 0.0
        dp[j] = (rhs[j] - sub[j] * dp[j - 1]) / m
    out = [0.0] * n
    out[n - 1] = dp[n - 1]
    for j in range(n - 2, -1, -1):
        out[j] = dp[j] - cp[j] * out[j + 1]
    return out


def _gauss(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Solve a dense square linear system by Gaussian elimination with partial pivoting."""
    n = len(rhs)
    a = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot_row = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot_row][col]) < 1e-300:
            raise ColumnConvergenceError("singular Newton system in column solver")
        a[col], a[pivot_row] = a[pivot_row], a[col]
        pivot = a[col][col]
        for r in range(col + 1, n):
            factor = a[r][col] / pivot
            if factor == 0.0:
                continue
            for c in range(col, n + 1):
                a[r][c] -= factor * a[col][c]
    out = [0.0] * n
    for r in range(n - 1, -1, -1):
        acc = a[r][n] - sum(a[r][c] * out[c] for c in range(r + 1, n))
        out[r] = acc / a[r][r]
    return out


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


# --------------------------------------------------------------------------------------
# Thermo adapter: one flash cache + K / per-phase enthalpy helpers per solve
# --------------------------------------------------------------------------------------


class _ThermoBox:
    """Wraps the Thermo protocol with a memo and the K-value / phase-enthalpy helpers.

    The K chain (stage liquid composition, then stage overall composition, then
    feed composition) returns None when every candidate comes back single-phase;
    callers keep the previous K in that case. Per-phase enthalpies use two
    single-phase flashes straddling the phase boundary and a linear model
    H(T) = h0 + cp*(T - T_ref).
    """

    def __init__(self, thermo: Thermo, p_anchor_lo: float, p_anchor_hi: float) -> None:
        self._thermo = thermo
        self._cache: dict[tuple[Any, ...], StreamState] = {}
        self._misc_cache: dict[tuple[Any, ...], float | None] = {}
        self._p_lo = p_anchor_lo
        self._p_hi = p_anchor_hi
        self._cc: dict[str, tuple[float, float, float]] = {}  # cid -> (D, T_ref, ln P_ref)

    def pt(self, z: dict[str, float], T: float, P: float, flow: float = 1.0) -> StreamState:
        key = (tuple(sorted(z.items())), T, P, flow)
        hit = self._cache.get(key)
        if hit is None:
            hit = self._thermo.flash_pt(z, T, P, flow)
            self._cache[key] = hit
        return hit

    def k_values(self, candidates: list[dict[str, float]], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i from the first two-phase flash among the candidates.

        Returns None when every candidate is single-phase at (T, P); callers
        then use the Clausius-Clapeyron estimate (see k_estimate).
        """
        for z in candidates:
            state = self.pt(z, T, P)
            if state.vapor_fraction <= 1e-6 or state.vapor_fraction >= 1.0 - 1e-6:
                continue
            vapor = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
            liquid = next(p for p in state.phases if p.kind != PhaseKind.VAPOR)
            k: dict[str, float] = {}
            for cid, xl in liquid.composition.items():
                yl = max(vapor.composition.get(cid, 0.0), 0.0)
                k[cid] = max(yl / xl, 1e-12) if xl > 0.0 else (1e6 if yl > 0.0 else 1.0)
            if k:
                return k
        return None

    def _cc_params(self, cid: str) -> tuple[float, float, float] | None:
        """Clausius-Clapeyron line (D, T_ref, ln P_ref) for a pure component.

        ln Psat(T) = ln P_ref - D * (1/T - 1/T_ref), with the slope measured
        between the pure-component saturation temperatures at the column's
        lowest and highest stage pressures (2500 K fallback when one anchor
        is unavailable, e.g. above the critical pressure).
        """
        hit = self._cc.get(cid)
        if hit is not None:
            return hit
        t_lo = self.bubble_temperature({cid: 1.0}, self._p_lo)
        t_hi = self.bubble_temperature({cid: 1.0}, self._p_hi)
        entry: tuple[float, float, float] | None = None
        if t_lo is not None and t_hi is not None and t_hi > t_lo + 1.0:
            d = math.log(self._p_hi / self._p_lo) / (1.0 / t_lo - 1.0 / t_hi)
            if math.isfinite(d) and d > 0.0:
                entry = (d, t_lo, math.log(self._p_lo))
        if entry is None and t_lo is not None:
            entry = (2500.0, t_lo, math.log(self._p_lo))
        if entry is None and t_hi is not None:
            entry = (2500.0, t_hi, math.log(self._p_hi))
        if entry is not None:
            self._cc[cid] = entry
        return entry

    def k_estimate(self, comp: dict[str, float], T: float, P: float) -> dict[str, float]:
        """Temperature-dependent K estimate at a single-phase stage state.

        Raoult form K_i = Psat_i(T)/P from the pure-component Clausius-Clapeyron
        line. This is the inner-loop K form; real flash K replaces it wherever a
        two-phase stage state exists, and the exact-residual gate (real K) still
        judges the converged profile.
        """
        out: dict[str, float] = {}
        for cid in comp:
            cc = self._cc_params(cid)
            if cc is None:
                out[cid] = 1.0
                continue
            d, t_ref, ln_p_ref = cc
            ln_psat = ln_p_ref - d * (1.0 / T - 1.0 / t_ref)
            out[cid] = max(math.exp(min(ln_psat, 50.0)) / P, 1e-10)
        return out

    def bubble_temperature(self, z: dict[str, float], P: float) -> float | None:
        """Pure/composition saturation temperature at P: the liquid-to-vapour jump.

        The PR flasher returns degenerate vapour fractions far below the phase
        envelope, so a plain bracket over [150, 700] can collapse on the wrong
        side; instead walk until a liquid state appears, then walk up to the
        first vapour state and bisect the jump between them.
        """
        key = ("bub", tuple(sorted(z.items())), P)
        hit = self._misc_cache.get(key)
        if hit is not None:
            return hit
        try:
            t_liq: float | None = None
            t = 120.0
            while t <= 690.0:
                if self.pt(z, t, P).vapor_fraction < 0.5:
                    t_liq = t
                    break
                t += 25.0
            if t_liq is None:
                self._misc_cache[key] = None
                return None
            lo, hi = t_liq, None
            t = t_liq
            while t <= 700.0:
                if self.pt(z, t, P).vapor_fraction > 0.5:
                    hi = t
                    break
                lo = t
                t += 10.0
            if hi is None:
                self._misc_cache[key] = None
                return None
            for _ in range(30):
                mid = 0.5 * (lo + hi)
                if self.pt(z, mid, P).vapor_fraction > 0.5:
                    hi = mid
                else:
                    lo = mid
        except Exception:  # noqa: BLE001 - component outside the EOS domain
            self._misc_cache[key] = None
            return None
        result: float | None = 0.5 * (lo + hi)
        self._misc_cache[key] = result
        return result

    def phase_enthalpy_model(
        self, z: dict[str, float], T: float, P: float, vapor: bool
    ) -> tuple[float, float, float]:
        """(h0, cp, T_ref) for a linear enthalpy model of one phase near T.

        Two single-phase flashes at T + delta (vapour) or T - delta (liquid),
        delta escalated until the flash really is that single phase; near a
        critical point the escalation can fail and the mixture enthalpy stands
        in for both phases (documented approximation).
        """
        for delta in (2.0, 5.0, 10.0, 20.0, 40.0):
            t1 = max(T + delta if vapor else T - delta, 90.0)
            t2 = max(T + 2.0 * delta if vapor else T - 2.0 * delta, 90.0)
            s1 = self.pt(z, t1, P)
            if vapor and s1.vapor_fraction < 0.98:
                continue
            if not vapor and s1.vapor_fraction > 0.02:
                continue
            s2 = self.pt(z, t2, P)
            # Secant slope over [t2, t1]: the liquid branch walks DOWNWARD
            # (t2 < t1), so dividing by the positive delta would negate the heat
            # capacity and make every liquid enthalpy line decrease with T.
            cp = (s2.enthalpy - s1.enthalpy) / (t2 - t1)
            return s1.enthalpy, cp, t1
        mixed = self.pt(z, T, P)
        return mixed.enthalpy, 0.0, T

    def h_vapor(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=True)
        return h0 + cp * (T - t_ref)

    def h_liquid(self, z: dict[str, float], T: float, P: float) -> float:
        h0, cp, t_ref = self.phase_enthalpy_model(z, T, P, vapor=False)
        return h0 + cp * (T - t_ref)


# --------------------------------------------------------------------------------------
# Column model
# --------------------------------------------------------------------------------------


@dataclass
class _StageFeed:
    """The flashed feed parts entering one stage (SI; h_flow = enthalpy flow, W)."""

    v_flow: float = 0.0
    y: dict[str, float] = field(default_factory=dict)
    l_flow: float = 0.0
    x: dict[str, float] = field(default_factory=dict)
    h_flow: float = 0.0
    total: float = 0.0


@dataclass
class _Column:
    """All static problem data for one solve. Stage index 0 = stage 1 (top)."""

    n: int
    condenser: str
    reboiler: str
    pressures: list[float]
    feeds: list[_StageFeed]
    draw_l: list[float]
    draw_v: list[float]
    draws: list[_DrawSpec]
    comps: list[str]
    f_total: float
    z_total: dict[str, float]
    feed_comp: dict[str, float]
    # Two-phase operating window for the inner temperature walk, set from the
    # temperature seed in _build_column.
    t_band_lo: float = 150.0
    t_band_hi: float = 600.0


@dataclass
class _Profile:
    """One stage profile (possibly mid-iteration). Index 0 = stage 1 (top)."""

    T: list[float]
    V: list[float]
    L: list[float]
    x: list[dict[str, float]]
    y: list[dict[str, float]]
    l0: float = 0.0  # reflux entering stage 1 (the total-condenser tear); 0 otherwise
    d: float = 0.0
    b: float = 0.0
    qc: float = 0.0  # condenser duty removed, W
    qr: float = 0.0  # reboiler duty added, W
    outer: int = 0
    inner: int = 0
    ns_used: bool = False


def _flash_stage_feeds(col_params: _Params, tb: _ThermoBox) -> list[_StageFeed]:
    """Flash every feed and split it into the vapour/liquid parts entering its stage."""
    stage_feeds = [_StageFeed() for _ in range(col_params.n_stages)]
    for f in col_params.feeds:
        state = tb.pt(f.comp, f.T, f.P, f.flow)
        part = stage_feeds[f.stage - 1]
        part.total += f.flow
        part.h_flow += state.enthalpy * f.flow
        vapor_part = state.vapor_fraction * f.flow
        liquid_part = (1.0 - state.vapor_fraction) * f.flow
        if vapor_part > _FLOW_FLOOR and state.phases:
            vapor_phase = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
            part.v_flow += vapor_part
            for cid, frac in vapor_phase.composition.items():
                part.y[cid] = part.y.get(cid, 0.0) + frac * vapor_part
        if liquid_part > _FLOW_FLOOR and state.phases:
            liquid_phases = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
            total_liq = sum(p.mole_fraction for p in liquid_phases)
            if total_liq > 0.0:
                part.l_flow += liquid_part
                for phase in liquid_phases:
                    weight = phase.mole_fraction / total_liq
                    for cid, frac in phase.composition.items():
                        part.x[cid] = part.x.get(cid, 0.0) + frac * weight * liquid_part
    for part in stage_feeds:
        if part.v_flow > _FLOW_FLOOR:
            s = sum(part.y.values())
            part.y = {cid: v / s for cid, v in part.y.items()}
        else:
            part.v_flow = 0.0
        if part.l_flow > _FLOW_FLOOR:
            s = sum(part.x.values())
            part.x = {cid: v / s for cid, v in part.x.items()}
        else:
            part.l_flow = 0.0
    return stage_feeds


def _build_column(col_params: _Params, tb: _ThermoBox) -> _Column:
    feeds = _flash_stage_feeds(col_params, tb)
    comps = sorted({cid for part in feeds for cid in part.y} | {cid for part in feeds for cid in part.x})
    f_total = sum(part.total for part in feeds)
    moles: dict[str, float] = {}
    for f in col_params.feeds:
        for cid, frac in f.comp.items():
            moles[cid] = moles.get(cid, 0.0) + frac * f.flow
    z_total = {cid: n / f_total for cid, n in sorted(moles.items())}
    col = _Column(
        n=col_params.n_stages,
        condenser=col_params.condenser,
        reboiler=col_params.reboiler,
        pressures=list(col_params.pressures),
        feeds=feeds,
        draw_l=[0.0] * col_params.n_stages,
        draw_v=[0.0] * col_params.n_stages,
        draws=list(col_params.draws),
        comps=comps,
        f_total=f_total,
        z_total=z_total,
        feed_comp=dict(z_total),
    )
    col.draw_l, col.draw_v = _draw_flows(col)
    # Clamp the inner temperature walk to a window around the physical operating
    # range: the seed estimates the distillate/bottoms temperatures, and stages
    # wandering far outside that range sit in single-phase states where the
    # equilibrium correlation degenerates and the profile collapses.
    t_top, t_bot = _temperature_seed(col, tb)
    if t_bot > t_top + 20.0:
        col.t_band_lo = max(t_top - 30.0, 150.0)
        col.t_band_hi = min(t_bot + 30.0, 600.0)
    return col


def _draw_flows(col: _Column) -> tuple[list[float], list[float]]:
    draw_l = [0.0] * col.n
    draw_v = [0.0] * col.n
    for d in col.draws:
        if d.vapor:
            draw_v[d.stage - 1] += d.flow
        else:
            draw_l[d.stage - 1] += d.flow
    return draw_l, draw_v


def _l_profile(col: _Column, l0: float, v: list[float]) -> list[float]:
    """Liquid profile from the stage-wise total balances, closed form:

    L_j = L_0 + sum_{m<=j}(F_m - S_m) + V_{j+1} - V_1  (V_{N+1} = 0),
    the telescoped sum of the stage total material balances.
    """
    out = []
    cum = 0.0
    v1 = v[0]
    for j in range(col.n):
        cum += col.feeds[j].total - col.draw_l[j] - col.draw_v[j]
        v_above = v[j + 1] if j + 1 < col.n else 0.0
        out.append(max(l0 + cum + v_above - v1, _FLOW_FLOOR))
    return out


def _d_and_b(col: _Column, l0: float, v: list[float], liquid: list[float]) -> tuple[float, float]:
    """Distillate and bottoms from the boundary balances.

    Total condenser: the hardware splits V_1 into reflux L_0 + distillate D.
    Partial/none: the distillate is the stage-1 vapour V_1 itself.
    The bottoms is the liquid leaving stage N.

    The values are kept raw (possibly negative mid-iteration): flooring them
    would flatten the spec residuals' gradient and stall the secant loop. The
    converged solution satisfies the specs, so the reported flows are positive.
    """
    d = v[0] - l0 if col.condenser == "total" else v[0]
    return d, liquid[col.n - 1]


def _temperature_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float]:
    """Estimate (T_top, T_bottom) for the starting profile.

    Two estimates. (1) Pure-component extremes: coldest and hottest component
    saturation temperatures at the end pressures - good for narrow-boiling
    feeds (their own bubble/dew can sit within a few kelvin, on either side).
    (2) Equilibrium-based: flash the feed at the mid-column pressure, take the
    bubble point of the vapour phase at the top pressure as T_top and of the
    liquid phase at the bottom pressure as T_bottom - the distillate/bottoms
    compositions of an average split. Extremes win for narrow boiling, but for
    wide-boiling feeds they smear the profile across the whole component list
    (a trace of C1 drops the top seed ~70 K into a region where the flash of
    C3+ liquids degenerates), so wide spans defer to the equilibrium estimate.
    """
    ext = _extreme_seed(col, tb)
    if ext is not None:
        t_top, t_bot = ext
        if t_bot > t_top + 1.0 and t_bot - t_top <= _SEED_SPAN_MAX:
            return t_top + 2.0, t_bot
    eq = _equilibrium_seed(col, tb)
    if eq is not None and eq[1] > eq[0] + 1.0:
        return eq[0] + 2.0, eq[1]
    t_top = bisect_feed_phase(col, tb, col.pressures[0], want_vapor=True)
    t_bot = bisect_feed_phase(col, tb, col.pressures[-1], want_vapor=False)
    if t_bot <= t_top:
        t_feed = tb.pt(col.feed_comp, 300.0, col.pressures[-1]).T
        t_top, t_bot = t_feed - 25.0, t_feed + 25.0
    return t_top, t_bot


def _extreme_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float] | None:
    """Coldest / hottest pure-component saturation temperatures, if flasheable."""
    sats_top: list[float] = []
    sats_bot: list[float] = []
    for cid in col.feed_comp:
        pure = {cid: 1.0}
        t_sat = tb.bubble_temperature(pure, col.pressures[0])
        if t_sat is not None:
            sats_top.append(t_sat)
        t_sat = tb.bubble_temperature(pure, col.pressures[-1])
        if t_sat is not None:
            sats_bot.append(t_sat)
    if not sats_top or not sats_bot:
        return None
    return min(sats_top), max(sats_bot)


def _equilibrium_seed(col: _Column, tb: _ThermoBox) -> tuple[float, float] | None:
    """Feed flash at the mid pressure; bubble points of each phase at the ends."""
    p_mid = 0.5 * (col.pressures[0] + col.pressures[-1])
    t_bub = bisect_feed_phase(col, tb, p_mid, want_vapor=False)
    t_dew = bisect_feed_phase(col, tb, p_mid, want_vapor=True)
    if not t_dew > t_bub + 2.0:
        return None
    state = tb.pt(col.feed_comp, 0.5 * (t_bub + t_dew), p_mid)
    vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
    liq = next((p for p in state.phases if p.kind != PhaseKind.VAPOR), None)
    if vap is None or liq is None:
        return None
    t_top = tb.bubble_temperature(_flash_ready(vap.composition, col.feed_comp), col.pressures[0])
    t_bot = tb.bubble_temperature(_flash_ready(liq.composition, col.feed_comp), col.pressures[-1])
    if t_top is None or t_bot is None:
        return None
    return t_top, t_bot


def bisect_feed_phase(col: _Column, tb: _ThermoBox, p: float, want_vapor: bool) -> float:
    """Bounded bisection on the feed flash for its dew (want_vapor) / bubble point."""
    lo, hi = 100.0, 700.0
    for _ in range(24):
        mid = 0.5 * (lo + hi)
        vf = tb.pt(col.feed_comp, mid, p).vapor_fraction
        if want_vapor:
            lo, hi = (mid, hi) if vf < 0.97 else (lo, mid)
        else:
            lo, hi = (lo, mid) if vf > 0.03 else (mid, hi)
    return 0.5 * (lo + hi)


def _seed_profile(col: _Column, t_top: float, t_bot: float) -> _Profile:
    n = col.n
    temps = [t_top + (t_bot - t_top) * (j / max(n - 1, 1)) for j in range(n)]
    z = col.feed_comp
    d_guess = max(0.35 * col.f_total, _FLOW_FLOOR)
    v1_guess = d_guess * 2.5
    vn_guess = (col.f_total - d_guess) * 1.5
    vapour = [max(v1_guess + (vn_guess - v1_guess) * (j / max(n - 1, 1)), _FLOW_FLOOR) for j in range(n)]
    l0 = max(v1_guess - d_guess, _FLOW_FLOOR) if col.condenser == "total" else 0.0
    if col.condenser == "partial":
        vapour[0] = max(d_guess, _FLOW_FLOOR)
    liquid = _l_profile(col, l0, vapour)
    x = [dict(z) for _ in range(n)]
    y = [dict(z) for _ in range(n)]
    return _Profile(T=temps, V=vapour, L=liquid, x=x, y=y, l0=l0)


# --------------------------------------------------------------------------------------
# Inside-out (Boston-Sullivan) solver
# --------------------------------------------------------------------------------------


@dataclass
class _InnerModel:
    """Frozen per-sweep models: raw K, alpha_ij, the ln Kb = A + B/T fit, enthalpy lines."""

    k_raw: list[dict[str, float]]
    alpha: list[dict[str, float]]
    ref_comp: str
    corr_a: float
    corr_b: float
    h_vap: list[tuple[float, float, float]]  # (h0, cp, T_ref) per stage, vapour
    h_liq: list[tuple[float, float, float]]  # per stage, liquid
    h_cond: tuple[float, float, float] | None  # condensate (total-condenser reflux) line
    fit_T: list[float]  # temperatures the enthalpy lines were fitted at


def _stage_overall(col: _Column, prof: _Profile, j: int) -> dict[str, float]:
    """Overall composition sitting on stage j: flows-weighted liquid, vapour and feed."""
    part = col.feeds[j]
    total = prof.L[j] + prof.V[j] + part.total - col.draw_l[j] - col.draw_v[j]
    if total <= _FLOW_FLOOR:
        return col.feed_comp
    acc: dict[str, float] = {}
    for src_comp, src_flow in (
        (prof.x[j], prof.L[j]),
        (prof.y[j], prof.V[j]),
        (part.x, part.l_flow),
        (part.y, part.v_flow),
    ):
        for cid, frac in src_comp.items():
            acc[cid] = acc.get(cid, 0.0) + frac * src_flow
    return {cid: v / total for cid, v in acc.items() if v > 0.0} or col.feed_comp


def _refresh_model(col: _Column, tb: _ThermoBox, prof: _Profile, model: _InnerModel | None) -> _InnerModel:
    """One outer sweep: real K-values per stage, alpha against a column-wide reference
    component, the ln Kb = A + B/T correlation (least squares over the stage points),
    and per-stage linear enthalpy models (refitted only when temperatures moved)."""
    n = col.n
    k_stages: list[dict[str, float]] = []
    for j in range(n):
        k = tb.k_values(
            [
                _flash_ready(prof.x[j], col.feed_comp),
                _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                col.feed_comp,
            ],
            prof.T[j],
            col.pressures[j],
        )
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None and model is not None:
            k = model.k_raw[j]
        k_stages.append(k or {cid: 1.0 for cid in col.comps})

    weights = {
        cid: sum(k_stages[j].get(cid, 0.0) * prof.x[j].get(cid, 0.0) for j in range(n)) for cid in col.comps
    }
    ref_comp = max(weights, key=lambda cid: weights[cid])
    kb = [max(k_stages[j].get(ref_comp, 1.0), 1e-12) for j in range(n)]
    alpha = [{cid: max(k_stages[j].get(cid, 1.0) / kb[j], 1e-12) for cid in col.comps} for j in range(n)]

    s_xx = sum(1.0 / (t * t) for t in prof.T)
    s_x = sum(1.0 / t for t in prof.T)
    s_y = sum(math.log(k) for k in kb)
    s_xy = sum(math.log(k) / t for k, t in zip(kb, prof.T, strict=True))
    det = n * s_xx - s_x * s_x
    if abs(det) < 1e-300:
        corr_a, corr_b = s_y / n, 0.0
    else:
        corr_b = (n * s_xy - s_x * s_y) / det
        corr_a = (s_y - corr_b * s_x) / n

    w = _OUTER_DAMP
    if model is not None:
        # Feedback damping (Boston-Sullivan): blend the refreshed correlation and
        # relative volatility with the previous sweep's values. Without it the
        # K/T/V coupling develops a two-cycle around the solution.
        corr_a = w * corr_a + (1.0 - w) * model.corr_a
        corr_b = w * corr_b + (1.0 - w) * model.corr_b
        alpha = [
            {cid: w * alpha[j][cid] + (1.0 - w) * model.alpha[j].get(cid, alpha[j][cid]) for cid in col.comps}
            for j in range(n)
        ]

    # Refit the enthalpy anchors every sweep: near convergence temperatures
    # barely move, so a refit-on-temperature-drift rule left the lines anchored
    # at stale compositions while x kept sharpening - the exact energy recheck
    # then never closed above the anchor floor.
    h_vap = [
        tb.phase_enthalpy_model(_flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j], True)
        for j in range(n)
    ]
    h_liq = [
        tb.phase_enthalpy_model(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j], False)
        for j in range(n)
    ]
    h_cond = (
        tb.phase_enthalpy_model(_flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0], False)
        if col.condenser == "total"
        else None
    )
    return _InnerModel(
        k_raw=k_stages,
        alpha=alpha,
        ref_comp=ref_comp,
        corr_a=corr_a,
        corr_b=corr_b,
        h_vap=h_vap,
        h_liq=h_liq,
        h_cond=h_cond,
        fit_T=list(prof.T),
    )


def _enthalpy_at(line: tuple[float, float, float], t: float) -> float:
    h0, cp, t_ref = line
    return h0 + cp * (t - t_ref)


def _mesh_x(col: _Column, model: _InnerModel, prof: _Profile, kb: list[float]) -> list[list[float]]:
    """M-equations: one tridiagonal solve per component for the liquid compositions.

    Returns x[component_index][stage_index].

    Stage j balance, component i, with y = K x and K_ij = alpha_ij * Kb_j:
        L_{j-1} x_{j-1} + V_{j+1} K_{j+1} x_{j+1} + F^L x^F + F^V y^F
        - (L_j + S^L_j) x_j - (V_j + S^V_j) K_j x_j = 0
    For a total condenser the reflux L_0 enters stage 1 at the condensate
    composition y_1 = K_1 x_1, folding L_0 K_1 into the stage-1 diagonal.
    """
    n = col.n
    k = [{cid: model.alpha[j].get(cid, 1.0) * kb[j] for cid in col.comps} for j in range(n)]
    liquid = _l_profile(col, prof.l0, prof.V)
    out: list[list[float]] = []
    for cid in col.comps:
        sub = [0.0] * n
        diag = [0.0] * n
        up = [0.0] * n
        rhs = [0.0] * n
        for j in range(n):
            part = col.feeds[j]
            if j > 0:
                sub[j] = liquid[j - 1]
            diag[j] = -((liquid[j] + col.draw_l[j]) + (prof.V[j] + col.draw_v[j]) * k[j].get(cid, 1.0))
            if j == 0 and col.condenser == "total":
                diag[j] += prof.l0 * k[j].get(cid, 1.0)
            if j < n - 1:
                up[j] = prof.V[j + 1] * k[j + 1].get(cid, 1.0)
            rhs[j] = -(part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0))
        sol = _thomas(sub, diag, up, rhs)
        out.append([max(v, 0.0) for v in sol])
    return out


def _h_equation_stages(col: _Column) -> list[int]:
    """Stages whose energy balance closes with the profile (duty-output stages drop out)."""
    n = col.n
    stages = list(range(n))
    if col.condenser == "partial":
        stages = [j for j in stages if j != 0]
    if col.reboiler == "kettle":
        stages = [j for j in stages if j != n - 1]
    return stages


def _v_free_indices(col: _Column) -> list[int]:
    """Vapour flows the enthalpy system may correct (tears and V_1-outcome excluded)."""
    n = col.n
    free = list(range(n))
    if col.condenser == "partial":
        free = [j for j in free if j != 0]  # V_1 = D is the top tear
    if col.reboiler == "kettle":
        free = [j for j in free if j != n - 1]  # V_N = boilup is the bottom tear
    return free


def _mesh_v(col: _Column, model: _InnerModel, prof: _Profile, t_bot_tear: float | None) -> list[float]:
    """H-equations: exact one-shot solve for the vapour profile.

    Stage j energy balance (Q_j = heat added to the stage):
        V_{j+1} H^V_{j+1} + L_{j-1} H^L_{j-1} + F_j H^F - (V_j + S^V_j) H^V_j
        - (L_j + S^L_j) H^L_j - Q_j = 0
    With the enthalpy lines and temperatures frozen, every term is affine in the
    free vapour flows (the L recursion is linear in V), so one Jacobian
    evaluation plus one linear solve is exact - no iteration, no line search.
    """
    n = col.n
    equation_stages = _h_equation_stages(col)
    free = _v_free_indices(col)

    def residuals(v: list[float]) -> list[float]:
        liquid = _l_profile(col, prof.l0, v)
        out = []
        for j in equation_stages:
            h_in = (
                (v[j + 1] * _enthalpy_at(model.h_vap[j + 1], prof.T[j + 1]) if j + 1 < n else 0.0)
                + (liquid[j - 1] * _enthalpy_at(model.h_liq[j - 1], prof.T[j - 1]) if j > 0 else 0.0)
                + (
                    prof.l0 * _enthalpy_at(model.h_cond, prof.T[0])
                    if j == 0 and model.h_cond is not None
                    else 0.0
                )
                + col.feeds[j].h_flow
            )
            h_out = (v[j] + col.draw_v[j]) * _enthalpy_at(model.h_vap[j], prof.T[j]) + (
                liquid[j] + col.draw_l[j]
            ) * _enthalpy_at(model.h_liq[j], prof.T[j])
            out.append(h_in - h_out)
        return out

    v_work = list(prof.V)
    if t_bot_tear is not None:
        v_work[n - 1] = t_bot_tear
    r0 = residuals(v_work)
    jac_cols = []
    for vk in free:
        perturbed = list(v_work)
        perturbed[vk] = v_work[vk] * (1.0 + 1e-6) + 1e-9
        r1 = residuals(perturbed)
        jac_cols.append([(r1[row] - r0[row]) / (perturbed[vk] - v_work[vk]) for row in range(len(r0))])
    jac = [[jac_cols[c][r] for c in range(len(free))] for r in range(len(r0))]
    try:
        step = _gauss(jac, [-r for r in r0])
    except ColumnConvergenceError:
        return v_work  # singular H system: keep the incoming profile, the exact
        # residual test will reject it and the NS fallback takes over
    candidate = list(v_work)
    for idx, vk in enumerate(free):
        candidate[vk] = max(v_work[vk] + step[idx], _FLOW_FLOOR)
    if t_bot_tear is not None:
        candidate[n - 1] = t_bot_tear
    # One safeguarded refinement pass guards against conditioning loss; the
    # system is affine, so this lands on the solution to round-off.
    for _ in range(2):
        r1 = residuals(candidate)
        if max(abs(r) for r in r1) <= max(abs(r) for r in r0):
            break
        jac_cols = []
        for vk in free:
            perturbed = list(candidate)
            perturbed[vk] = candidate[vk] * (1.0 + 1e-6) + 1e-9
            r2 = residuals(perturbed)
            jac_cols.append([(r2[row] - r1[row]) / (perturbed[vk] - candidate[vk]) for row in range(len(r1))])
        jac = [[jac_cols[c][r] for c in range(len(free))] for r in range(len(r1))]
        try:
            step = _gauss(jac, [-r for r in r1])
        except ColumnConvergenceError:
            break
        refined = list(candidate)
        for idx, vk in enumerate(free):
            refined[vk] = max(candidate[vk] + step[idx], _FLOW_FLOOR)
        if t_bot_tear is not None:
            refined[n - 1] = t_bot_tear
        candidate = refined
    return candidate


def _inner_solve(col: _Column, model: _InnerModel, prof: _Profile, t_bot_tear: float | None) -> int:
    """The inside-out inner loop: M -> bubble (Kb) -> T (correlation) -> H (Newton).

    With alpha, the Kb correlation and the enthalpy lines frozen, the loop
    iterates until flows and temperatures stop moving. No thermo calls.
    """
    n = col.n
    kb = [1.0] * n
    iterations = 0
    for i in range(1, _INNER_MAX + 1):
        iterations = i
        x_sets = _mesh_x(col, model, prof, kb)
        x_new: list[dict[str, float]] = []
        for j in range(n):
            s = sum(x_sets[i_c][j] for i_c in range(len(col.comps)))
            if s <= 0.0:
                x_new.append(dict(col.feed_comp))
            else:
                x_new.append({cid: x_sets[i_c][j] / s for i_c, cid in enumerate(col.comps)})
        kb = [
            max(1.0 / sum(model.alpha[j].get(cid, 1.0) * x_new[j].get(cid, 0.0) for cid in col.comps), 1e-12)
            for j in range(n)
        ]
        t_old = prof.T
        v_old = prof.V
        t_new = []
        for j in range(n):
            denom = math.log(kb[j]) - model.corr_a
            t_corr = model.corr_b / denom if abs(denom) > 1e-12 else t_old[j]
            t_corr = min(max(t_corr, col.t_band_lo), col.t_band_hi)  # two-phase operating window
            step = 0.7 * (t_corr - t_old[j])
            step = max(min(step, 30.0), -30.0)  # bounded walk, one sweep at a time
            t_new.append(t_old[j] + step)
        prof.T = t_new  # the V-solve must see the temperatures it will be judged at
        v_new = _mesh_v(col, model, prof, t_bot_tear)
        delta_t = max(abs(t_new[j] - t_old[j]) / max(t_old[j], 1.0) for j in range(n))
        delta_v = max(abs(v_new[j] - v_old[j]) / max(v_old[j], 1.0) for j in range(n))
        prof.V = v_new
        prof.x = x_new
        prof.L = _l_profile(col, prof.l0, prof.V)
        if delta_t < _INNER_TOL and delta_v < _INNER_TOL:
            break
    prof.y = []
    for j in range(n):
        y_j = {cid: model.alpha[j].get(cid, 1.0) * kb[j] * prof.x[j].get(cid, 0.0) for cid in col.comps}
        s = sum(y_j.values())
        prof.y.append({cid: v / s for cid, v in y_j.items()} if s > 0.0 else dict(col.feed_comp))
    prof.inner += iterations
    return iterations


def _exact_residuals(col: _Column, tb: _ThermoBox, prof: _Profile) -> tuple[float, float]:
    """Max relative MESH residuals with real thermo K-values and phase enthalpies.

    The honest convergence measure: the frozen inner models closed the equations,
    and the refreshed thermo values must still close them.
    """
    n = col.n
    max_m = 0.0
    max_h = 0.0
    liquid = _l_profile(col, prof.l0, prof.V)
    h_scale = max(col.f_total * 2e4, 1.0)
    h_stages = set(_h_equation_stages(col))
    for j in range(n):
        k = tb.k_values(
            [
                _flash_ready(prof.x[j], col.feed_comp),
                _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                col.feed_comp,
            ],
            prof.T[j],
            col.pressures[j],
        )
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None:
            # A stage whose equilibrium cannot be evaluated is NOT converged.
            # Skipping it let degenerate all-liquid profiles read as exact.
            max_m = max(max_m, 1.0)
            max_h = max(max_h, 1.0)
            continue
        part = col.feeds[j]
        for cid in col.comps:
            inflow = liquid[j - 1] * prof.x[j - 1].get(cid, 0.0) if j > 0 else 0.0
            if j == 0 and col.condenser == "total":
                inflow = prof.l0 * prof.y[0].get(cid, 0.0)
            inflow += prof.V[j + 1] * prof.y[j + 1].get(cid, 0.0) if j + 1 < n else 0.0
            inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
            outflow = (liquid[j] + col.draw_l[j]) * prof.x[j].get(cid, 0.0) + (
                prof.V[j] + col.draw_v[j]
            ) * prof.y[j].get(cid, 0.0)
            scale = max(abs(inflow), abs(outflow), col.f_total * 1e-6)
            max_m = max(max_m, abs(inflow - outflow) / scale)
        if j not in h_stages:
            continue  # duty-output stage: its balance defines the duty (qc/qr);
            # counting it here would report the duty magnitude as a residual
        h_in = (
            (
                prof.V[j + 1]
                * tb.h_vapor(_flash_ready(prof.y[j + 1], col.feed_comp), prof.T[j + 1], col.pressures[j + 1])
                if j + 1 < n
                else 0.0
            )
            + (
                liquid[j - 1]
                * tb.h_liquid(_flash_ready(prof.x[j - 1], col.feed_comp), prof.T[j - 1], col.pressures[j - 1])
                if j > 0
                else 0.0
            )
            + part.h_flow
        )
        if j == 0 and col.condenser == "total":
            h_in += prof.l0 * tb.h_liquid(_flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0])
        h_out = (prof.V[j] + col.draw_v[j]) * tb.h_vapor(
            _flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j]
        ) + (liquid[j] + col.draw_l[j]) * tb.h_liquid(
            _flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j]
        )
        max_h = max(max_h, abs(h_in - h_out) / h_scale)
    return max_m, max_h


# --------------------------------------------------------------------------------------
# Naphtali-Sandholm fallback
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _NsPass:
    """Thermo data frozen for one Naphtali-Sandholm Newton pass."""

    k_stages: list[dict[str, float]]
    h_vap: list[tuple[float, float, float]]
    h_liq: list[tuple[float, float, float]]
    h_cond: tuple[float, float, float] | None


def _ns_residual_function(
    col: _Column,
    tb: _ThermoBox,
    l0: float,
    models: _NsPass,
    h_stages: list[int],
    t_bot_tear: float | None,
) -> Callable[[list[float]], list[float]]:
    """Build the residual function for one Newton pass (fresh closures per pass).

    Full NS equation set: per stage one M balance per component, the summation
    sum_i x_ij = 1, and the H balance where the duty is not an output. K is
    evaluated LIVE at each stage's current state: with frozen K the M rows carry
    no temperature information and the stage temperatures float free - the SVD
    of the frozen-K Jacobian shows the kettle T as an exact null direction, and
    fixing it with a separate bubble row over-determines the composition block.
    With live K the M + summation block is locally square in (x_j, T_j) and
    embeds the bubble condition, so no extra rows are needed.

    A per-stage K cache keeps the finite-difference Jacobian affordable: a
    perturbation of one packed unknown changes only its own stage's state, so
    all other stages hit the cache and cost no flash.
    """
    k_cache: dict[
        tuple[tuple[tuple[str, float], ...], tuple[tuple[str, float], ...], float, float],
        dict[str, float],
    ] = {}

    def _live_k(
        j: int, xs: list[dict[str, float]], ts: list[float], vs: list[float], liquid: list[float]
    ) -> dict[str, float]:
        part = col.feeds[j]
        stage_total = liquid[j] + vs[j] + part.total - col.draw_l[j] - col.draw_v[j]
        overall: dict[str, float] = {}
        for src_comp, src_flow in ((xs[j], liquid[j]), (part.x, part.l_flow), (part.y, part.v_flow)):
            for cid, frac in src_comp.items():
                overall[cid] = overall.get(cid, 0.0) + frac * src_flow
        if stage_total > _FLOW_FLOOR:
            overall = {cid: v / stage_total for cid, v in overall.items()}
        key = (
            tuple(sorted(xs[j].items())),
            tuple(sorted(overall.items())),
            round(ts[j], 12),
            col.pressures[j],
        )
        hit = k_cache.get(key)
        if hit is not None:
            return hit
        # The thermo flash validates normalized compositions; Newton trial states
        # can be far off-normalized or degenerate (all flows at the floor), so
        # evaluate K at the normalized projection - or at the feed composition
        # when the trial state carries no composition at all.
        liq = xs[j] or col.feed_comp
        liq_sum = sum(liq.values())
        liq = {cid: v / liq_sum for cid, v in liq.items()} if liq_sum > _FLOW_FLOOR else col.feed_comp
        overall_sum = sum(overall.values())
        overall = (
            {cid: v / overall_sum for cid, v in overall.items()}
            if overall_sum > _FLOW_FLOOR
            else col.feed_comp
        )
        k = (
            tb.k_values([liq, overall, col.feed_comp], ts[j], col.pressures[j])
            or tb.k_estimate(liq, ts[j], col.pressures[j])
            or models.k_stages[j]
        )
        k_cache[key] = k
        return k

    def residuals(u: list[float]) -> list[float]:
        n = col.n
        xs = _unpack_x(u, col)
        ts = _unpack_t(u, col)
        vs = _unpack_v(u, col, _v_free_indices(col), t_bot_tear)
        liquid = _l_profile(col, l0, vs)
        k_live = [_live_k(j, xs, ts, vs, liquid) for j in range(n)]
        out: list[float] = []
        for j in range(n):
            part = col.feeds[j]
            for cid in col.comps:
                inflow = liquid[j - 1] * xs[j - 1].get(cid, 0.0) if j > 0 else 0.0
                if j == 0 and col.condenser == "total":
                    inflow = l0 * k_live[0].get(cid, 1.0) * xs[0].get(cid, 0.0)
                inflow += (
                    vs[j + 1] * k_live[j + 1].get(cid, 1.0) * xs[j + 1].get(cid, 0.0) if j + 1 < n else 0.0
                )
                inflow += part.l_flow * part.x.get(cid, 0.0) + part.v_flow * part.y.get(cid, 0.0)
                outflow = (liquid[j] + col.draw_l[j]) * xs[j].get(cid, 0.0) + (
                    vs[j] + col.draw_v[j]
                ) * k_live[j].get(cid, 1.0) * xs[j].get(cid, 0.0)
                out.append(inflow - outflow)
            out.append(sum(xs[j].values()) - 1.0)
            if j in h_stages:
                h_in = (
                    (vs[j + 1] * _enthalpy_at(models.h_vap[j + 1], ts[j + 1]) if j + 1 < n else 0.0)
                    + (liquid[j - 1] * _enthalpy_at(models.h_liq[j - 1], ts[j - 1]) if j > 0 else 0.0)
                    + (
                        l0 * _enthalpy_at(models.h_cond, ts[0])
                        if j == 0 and models.h_cond is not None
                        else 0.0
                    )
                    + part.h_flow
                )
                h_out = (vs[j] + col.draw_v[j]) * _enthalpy_at(models.h_vap[j], ts[j]) + (
                    liquid[j] + col.draw_l[j]
                ) * _enthalpy_at(models.h_liq[j], ts[j])
                out.append(h_in - h_out)
        return out

    return residuals


def _naphtali_sandholm(col: _Column, tb: _ThermoBox, prof: _Profile, t_bot_tear: float | None) -> _Profile:
    """Fallback: simultaneous damped Newton on (x, T, V) with K frozen per pass.

    Unknowns: the liquid mole fractions x_ij, the stage temperatures T_j and the
    free vapour flows V_j. Equations: the M balances, the summations
    sum_i x_ij = 1, and the H balances whose duty is not an output - square per
    stage grouping (Naphtali & Sandholm 1971). K-values and enthalpy lines
    refresh from the thermo plugin between Newton passes.
    """
    n = col.n
    l0 = prof.l0
    h_stages = _h_equation_stages(col)
    v_free = _v_free_indices(col)
    f_scale = max(col.f_total, 1.0)
    h_scale = max(col.f_total * 2e4, 1.0)
    n_m = n * len(col.comps) + n  # component M rows + summation rows

    def norm_of(r: list[float]) -> float:
        return max(
            max(abs(r[i]) for i in range(n_m)) / f_scale,
            max(abs(r[i]) for i in range(n_m, len(r))) / h_scale,
        )

    def gates_ok(r: list[float]) -> bool:
        """Same acceptance semantics as the inside-out mesh gate.

        A pure 1e-10 norm can never be reached: the frozen enthalpy lines carry
        an anchor floor around 1e-3 relative, so Newton would exhaust its pass
        budget refining a state the mesh itself already accepts.
        """
        return (
            max(abs(r[i]) for i in range(n_m)) / f_scale < _MESH_M_TOL
            and max(abs(r[i]) for i in range(n_m, len(r))) / h_scale < _MESH_H_TOL
        )

    for _ in range(_NS_MAX):
        k_stages = [
            tb.k_values(
                [
                    _flash_ready(prof.x[j], col.feed_comp),
                    _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                    col.feed_comp,
                ],
                prof.T[j],
                col.pressures[j],
            )
            or tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
            or {cid: 1.0 for cid in col.comps}
            for j in range(n)
        ]
        h_vap = [
            tb.phase_enthalpy_model(_flash_ready(prof.y[j], col.feed_comp), prof.T[j], col.pressures[j], True)
            for j in range(n)
        ]
        h_liq = [
            tb.phase_enthalpy_model(
                _flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j], False
            )
            for j in range(n)
        ]
        h_cond = (
            tb.phase_enthalpy_model(prof.y[0] or col.feed_comp, prof.T[0], col.pressures[0], False)
            if col.condenser == "total"
            else None
        )
        models = _NsPass(k_stages=k_stages, h_vap=h_vap, h_liq=h_liq, h_cond=h_cond)
        residuals = _ns_residual_function(col, tb, l0, models, h_stages, t_bot_tear)

        u = _pack_state(prof, col, v_free)
        r0 = residuals(u)
        norm = norm_of(r0)
        if gates_ok(r0):
            break
        n_unk = len(u)
        jac = [[0.0] * n_unk for _ in range(len(r0))]
        for i in range(n_unk):
            delta = max(abs(u[i]) * 1e-7, 1e-9)
            u2 = list(u)
            u2[i] += delta
            r1 = residuals(u2)
            for row in range(len(r0)):
                jac[row][i] = (r1[row] - r0[row]) / delta
        try:
            step = _gauss(jac, [-r for r in r0])
        except ColumnConvergenceError:
            break
        lam = 1.0
        for _ in range(10):
            u_try = [u[i] + lam * step[i] for i in range(n_unk)]
            try:
                trial_norm = norm_of(residuals(u_try))
            except ColumnConvergenceError:
                # A trial step landed in a degenerate state the residual
                # machinery cannot evaluate; reject it and shrink the step.
                trial_norm = float("inf")
            if trial_norm < norm:
                _apply_state(prof, u_try, col, v_free, t_bot_tear)
                break
            lam *= 0.5
        else:
            break
    else:
        raise ColumnConvergenceError("Naphtali-Sandholm fallback did not converge within budget")
    _refresh_y(col, tb, prof)
    m_res, h_res = _exact_residuals(col, tb, prof)
    prof.ns_used = True
    # Same tolerances as the inside-out acceptance gate: the enthalpy-line
    # anchor floor sits around 1e-3-1e-4 relative, while mass closes to
    # machine precision. Demanding 1e-6 on H here would reject a solution
    # the mesh itself accepts.
    if m_res > _MESH_M_TOL or h_res > _MESH_H_TOL:
        raise ColumnConvergenceError(
            f"Naphtali-Sandholm fallback stalled: max residuals M={m_res:.2e}, H={h_res:.2e}"
        )
    _finalize_duties(col, tb, prof)
    return prof


def _pack_state(prof: _Profile, col: _Column, v_free: list[int]) -> list[float]:
    u = [prof.x[j][cid] for j in range(col.n) for cid in col.comps]
    u.extend(prof.T)
    u.extend(prof.V[j] for j in v_free)
    return u


def _unpack_x(u: list[float], col: _Column) -> list[dict[str, float]]:
    out = []
    pos = 0
    for _ in range(col.n):
        out.append({cid: max(u[pos + i], 0.0) for i, cid in enumerate(col.comps)})
        pos += len(col.comps)
    return out


def _unpack_t(u: list[float], col: _Column) -> list[float]:
    base = col.n * len(col.comps)
    return [min(max(u[base + j], 100.0), 800.0) for j in range(col.n)]


def _unpack_v(u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None) -> list[float]:
    base = col.n * len(col.comps) + col.n
    full = [_FLOW_FLOOR] * col.n
    for idx, j in enumerate(v_free):
        full[j] = max(_FLOW_FLOOR, u[base + idx])
    if t_bot_tear is not None:
        full[col.n - 1] = t_bot_tear
    return full


def _apply_state(
    prof: _Profile, u: list[float], col: _Column, v_free: list[int], t_bot_tear: float | None
) -> None:
    # _unpack_x clamps Newton trial values at zero without renormalizing (the
    # residual algebra needs the raw clamped values); the applied profile must
    # be a valid composition - downstream consumers flash it.
    prof.x = [
        _flash_ready({cid: max(v, 0.0) for cid, v in xs.items()}, col.feed_comp) for xs in _unpack_x(u, col)
    ]
    prof.T = _unpack_t(u, col)
    prof.V = _unpack_v(u, col, v_free, t_bot_tear)
    prof.L = _l_profile(col, prof.l0, prof.V)


def _flash_ready(z: dict[str, float], fallback: dict[str, float]) -> dict[str, float]:
    """Normalize a composition for the thermo plugin, which validates sum-to-1.

    Newton trial states and mid-sweep meshes wander off-normalized; every
    direct flash or enthalpy evaluation of a stage composition goes through
    this projection so the residual machinery sees a continuous K/enthalpy
    field instead of a validation error.
    """
    total = sum(z.values())
    if total > _FLOW_FLOOR:
        return {cid: v / total for cid, v in z.items()}
    return fallback


def _refresh_y(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Recompute vapour compositions y = K(T, P) x from the current stage states.

    The Newton apply writes x/T/V/L only; downstream consumers (boundary
    streams, spec residuals, duties, info) need the vapour side of the same
    equilibrium, not the stale flash composition from an earlier state.
    """
    for j in range(col.n):
        k = tb.k_values(
            [
                _flash_ready(prof.x[j], col.feed_comp),
                _flash_ready(_stage_overall(col, prof, j), col.feed_comp),
                col.feed_comp,
            ],
            prof.T[j],
            col.pressures[j],
        )
        if k is None:
            k = tb.k_estimate(_flash_ready(prof.x[j], col.feed_comp), prof.T[j], col.pressures[j])
        if k is None:
            k = {cid: 1.0 for cid in col.comps}
        y = {cid: k.get(cid, 1.0) * prof.x[j].get(cid, 0.0) for cid in col.comps}
        total = sum(y.values())
        if total > _FLOW_FLOOR:
            y = {cid: v / total for cid, v in y.items()}
        prof.y[j] = y


# --------------------------------------------------------------------------------------
# Mesh driver and duty reporting
# --------------------------------------------------------------------------------------


def _apply_tears(col: _Column, prof: _Profile, t_top: float | None, t_bot: float | None) -> None:
    """Write the tear values into the profile (reflux, distillate vapour, boilup)."""
    if col.condenser == "total":
        prof.l0 = max(t_top, _FLOW_FLOOR) if t_top is not None else prof.l0
    elif col.condenser == "partial":
        prof.l0 = 0.0
        if t_top is not None:
            prof.V[0] = max(t_top, _FLOW_FLOOR)
    else:
        prof.l0 = 0.0
    if col.reboiler == "kettle" and t_bot is not None:
        prof.V[col.n - 1] = max(t_bot, _FLOW_FLOOR)


def _finalize_duties(col: _Column, tb: _ThermoBox, prof: _Profile) -> None:
    """Duties from the converged profile.

    Condenser duty from its own balance; reboiler duty from the stage balance,
    then closed exactly on the overall energy balance over the real boundary
    streams (see module docstring). Draws leave at their stage conditions.
    """
    # Converged states satisfy the summation rows only to solver tolerance;
    # normalize every stage composition in place so the duties and the outlet
    # boundary streams built from this profile pass the thermo's validation.
    for j in range(col.n):
        for comp in (prof.x[j], prof.y[j]):
            total = sum(comp.values())
            if total > _FLOW_FLOOR and abs(total - 1.0) > 1e-12:
                for cid in comp:
                    comp[cid] /= total
    liquid = _l_profile(col, prof.l0, prof.V)
    prof.d, prof.b = _d_and_b(col, prof.l0, prof.V, liquid)
    if col.condenser == "total":
        y0 = _flash_ready(prof.y[0], col.feed_comp)
        prof.qc = max(
            prof.V[0]
            * (tb.h_vapor(y0, prof.T[0], col.pressures[0]) - tb.h_liquid(y0, prof.T[0], col.pressures[0])),
            0.0,
        )
    elif col.condenser == "partial":
        y1 = _flash_ready(prof.y[1], col.feed_comp) if col.n > 1 else col.feed_comp
        h_in = (prof.V[1] * tb.h_vapor(y1, prof.T[1], col.pressures[1]) if col.n > 1 else 0.0) + col.feeds[
            0
        ].h_flow
        h_out = prof.V[0] * tb.h_vapor(
            _flash_ready(prof.y[0], col.feed_comp), prof.T[0], col.pressures[0]
        ) + (liquid[0] + col.draw_l[0]) * tb.h_liquid(
            _flash_ready(prof.x[0], col.feed_comp), prof.T[0], col.pressures[0]
        )
        prof.qc = max(h_in - h_out, 0.0)
    else:
        prof.qc = 0.0
    if col.reboiler == "kettle":
        h_in = (
            liquid[col.n - 2]
            * tb.h_liquid(
                _flash_ready(prof.x[col.n - 2], col.feed_comp),
                prof.T[col.n - 2],
                col.pressures[col.n - 2],
            )
            if col.n > 1
            else 0.0
        ) + col.feeds[col.n - 1].h_flow
        h_out = prof.V[col.n - 1] * tb.h_vapor(
            _flash_ready(prof.y[col.n - 1], col.feed_comp),
            prof.T[col.n - 1],
            col.pressures[col.n - 1],
        ) + (liquid[col.n - 1] + col.draw_l[col.n - 1]) * tb.h_liquid(
            _flash_ready(prof.x[col.n - 1], col.feed_comp),
            prof.T[col.n - 1],
            col.pressures[col.n - 1],
        )
        prof.qr = max(h_in - h_out, 0.0)
    else:
        prof.qr = 0.0


def _close_energy_balance(
    col: _Column,
    tb: _ThermoBox,
    prof: _Profile,
    feed_states: list[StreamState],
    out_states: list[StreamState],
) -> None:
    """Exact overall closure: qr = sum(H_out) - sum(H_in) + qc, over the real streams.

    This makes UnitResult.duty_W = qr - qc close the stream enthalpy table to
    machine precision; the deviation from the stage-balance reboiler duty is the
    converged MESH residual, far below the duty magnitudes.
    """
    h_in = sum(s.enthalpy * s.molar_flow for s in feed_states)
    h_out = sum(s.enthalpy * s.molar_flow for s in out_states)
    prof.qr = h_out - h_in + prof.qc


def _solve_mesh(
    col: _Column, tb: _ThermoBox, t_top: float | None, t_bot: float | None, seed: _Profile | None
) -> _Profile:
    """Converge the MESH equations at given tear values: inside-out, NS fallback."""
    prof: _Profile | None = None
    if seed is None:
        t_top_seed, t_bot_seed = _temperature_seed(col, tb)
        prof = _seed_profile(col, t_top_seed, t_bot_seed)
    else:
        # Copy: the sweep loop mutates the profile in place, and a failed mesh
        # must not corrupt the seed the spec layer warm-starts from.
        prof = _copy_profile(col, seed)
    _apply_tears(col, prof, t_top, t_bot)
    model: _InnerModel | None = None
    stalled = 0
    best_prof: _Profile | None = None
    best_m = float("inf")
    best_h = float("inf")
    for outer in range(1, _OUTER_MAX + 1):
        t_prev, v_prev = list(prof.T), list(prof.V)
        model = _refresh_model(col, tb, prof, model)
        prof.outer = outer
        _inner_solve(col, model, prof, t_bot)  # accumulates prof.inner itself
        w = _OUTER_DAMP
        # Feedback damping between sweeps on temperature and vapour profiles:
        # the frozen-model update overshoots near unstable tears.
        for j in range(col.n):
            prof.T[j] = t_prev[j] + w * (prof.T[j] - t_prev[j])
            prof.V[j] = v_prev[j] + w * (prof.V[j] - v_prev[j])
        prof.L = _l_profile(col, prof.l0, prof.V)
        m_res, h_res = _exact_residuals(col, tb, prof)
        if m_res < _MESH_M_TOL and h_res < _MESH_H_TOL:
            _finalize_duties(col, tb, prof)
            return prof
        # Stagnation = NO improvement in either residual for 3 consecutive
        # sweeps. Early sweeps wobble in mass while enthalpy still improves
        # monotonically; a single combined metric misreads that as stagnation
        # and hands a healthy iteration to the fallback.
        if m_res < best_m or h_res < best_h:
            stalled = 0
            if best_prof is None or m_res + h_res < best_m + best_h:
                best_prof, best_m, best_h = _copy_profile(col, prof), m_res, h_res
        else:
            stalled += 1
            if stalled >= 3:
                break
    # The inside-out loop stalled or exhausted its budget: hand the best profile
    # to the Naphtali-Sandholm Newton fallback, which polishes from there.
    if best_prof is not None:
        prof = _copy_profile(col, best_prof)
    try:
        _naphtali_sandholm(col, tb, prof, t_bot)
    except ColumnConvergenceError as exc:
        raise ColumnConvergenceError(
            f"column did not converge in {_OUTER_MAX} inside-out sweeps and the "
            f"Naphtali-Sandholm fallback failed: {exc}"
        ) from exc
    return prof


def _copy_profile(col: _Column, src: _Profile) -> _Profile:
    """Deep-copy a profile: lists and per-stage composition dicts are mutable."""
    return _Profile(
        T=list(src.T),
        V=list(src.V),
        L=list(src.L),
        x=[dict(c) for c in src.x],
        y=[dict(c) for c in src.y],
        l0=src.l0,
        d=src.d,
        b=src.b,
        qc=src.qc,
        qr=src.qr,
        outer=src.outer,
        inner=src.inner,
        ns_used=src.ns_used,
    )


def _initial_tears(col: _Column, params: _Params) -> tuple[float, float]:
    """Starting guesses for the two tear flows (top reflux, kettle boilup), mol/s.

    Plain fractions of the feed: the spec secant moves them, the mesh converges
    from any sane start, and elaborate temperature-based seeds bought nothing.
    """
    return 0.5 * col.f_total, 0.8 * col.f_total


def _fenske_alpha(col: _Column, tb: _ThermoBox, cid: str, product: str) -> float | None:
    """Mean relative volatility of cid against its limiting reference component.

    The Fenske total-reflux bound needs the mean stage relative volatility.
    K is evaluated from real two-phase flashes just inside the feed's bubble
    and dew points at the mid column pressure - the ends of the true stage
    temperature window - and combined GEOMETRICALLY (alpha varies roughly
    exponentially with temperature along the profile). Single-phase flashes
    are useless here: the seed band ends sit OUTSIDE the two-phase envelope,
    where only the temperature-insensitive Clausius-Clapeyron Raoult estimate
    is available (measured: it returned alpha=2.49 at both ends on the C3/iC4
    case and masked an unreachable spec; the two-phase end flashes give 1.83).

    Returns None when either window end yields no two-phase flash K, or when
    the component is not the key for its product side (alpha <= 1: the Fenske
    enrichment bound does not apply to an anti-enrichment purity spec).
    """
    if cid not in col.feed_comp:
        return None
    p_mid = 0.5 * (col.pressures[0] + col.pressures[-1])
    t_bub = bisect_feed_phase(col, tb, p_mid, want_vapor=False)
    t_dew = bisect_feed_phase(col, tb, p_mid, want_vapor=True)
    alphas: list[float] = []
    for t in (t_bub + 2.0, t_dew - 2.0):
        if t <= t_bub + 1.0:
            continue  # two-phase window too narrow to sample twice
        k = tb.k_values([_flash_ready(col.feed_comp, col.feed_comp)], t, p_mid)
        if k is None or cid not in k or len(k) < 2:
            continue
        others = [v for name, v in k.items() if name != cid]
        if min(others) <= 0.0 or k[cid] <= 0.0:
            continue
        ref = min(others) if product == "distillate" else max(others)
        alpha = k[cid] / ref if product == "distillate" else ref / k[cid]
        if alpha > 1.0:
            alphas.append(alpha)
    if not alphas:
        return None
    return math.prod(alphas) ** (1.0 / len(alphas))


def _check_spec_feasibility(col: _Column, tb: _ThermoBox, params: _Params) -> None:
    """Reject provably unreachable specs BEFORE the secant/spec walk.

    An infeasible spec used to surface only after the secant had wandered into
    degenerate tear corners (measured 162 s on the 0.999-purity case). Each
    check here rejects only what is unreachable even at total reflux - the
    maximum-separation limit of any finite column - and is deliberately
    permissive near its own boundary:

    - distillate/bottoms rates: the [0, available-feed] window is enforced in
      ``_parse_params`` (the draw-room check); nothing left to add here.
    - product purity: Fenske at total reflux (Fenske, Ind. Eng. Chem. 24:482,
      1932). The most favorable split (vanishing opposite product) needs
      separation factor S = p/(1-p) * (1-z)/z for a distillate purity p of a
      component at feed fraction z, and S = p/(1-p) * z/(1-z) for a bottoms
      purity. A column with N stages delivers at most S_max = alpha^N; if
      S_max < S the target is unreachable even at total reflux.
    - component recovery: r <= alpha^N / (1 + alpha^N) at total reflux, from
      the Fenske pair relation d_i/b_i = alpha^N with the limiting reference
      component overwhelmingly reporting to the other product (same permissive
      bias as the purity bound).
    - reflux/boilup ratios: positivity is enforced in ``_parse_params``; the
      meaningful lower bound (R > R_min) has no cheap closed form and is the
      secant bracket abort's job (see ``_solve_specs``).
    """
    for key, target_d in params.specs.items():
        if key not in ("product_purity", "component_recovery"):
            continue
        comp = str(target_d["component"])
        product = str(target_d.get("product", "distillate"))
        value = float(target_d["value"])
        alpha = _fenske_alpha(col, tb, comp, product)
        if alpha is None:
            continue
        s_max = alpha**col.n
        if key == "component_recovery":
            r_max = s_max / (1.0 + s_max)
            if value > r_max:
                raise ColumnSpecError(
                    f"specs.{key} {value} exceeds the total-reflux recovery limit {r_max:.4g} "
                    f"(alpha={alpha:.3g} over {col.n} stages); the specification is infeasible"
                )
            continue
        z = col.feed_comp.get(comp, 0.0)
        if not 0.0 < z < 1.0:
            continue
        if product == "distillate":
            s_need = (value / (1.0 - value)) * ((1.0 - z) / z)
        else:
            s_need = (value / (1.0 - value)) * (z / (1.0 - z))
        if s_max < s_need:
            n_min = math.ceil(math.log(s_need) / math.log(alpha))
            raise ColumnSpecError(
                f"specs.{key} {value} of {comp!r} in the {product} needs at least {n_min} "
                f"equilibrium stages at TOTAL reflux (alpha={alpha:.3g}); this column has "
                f"{col.n}, so the specification is infeasible"
            )


def _spec_g(col: _Column, params: _Params, prof: _Profile, skip: set[str]) -> tuple[list[float], list[float]]:
    """Raw spec residuals and their scales; the secant drives rel = g / scale to zero."""
    g: list[float] = []
    scales: list[float] = []
    for key, raw_target in params.specs.items():
        if key in skip:
            continue
        if key in ("component_recovery", "product_purity"):
            target_d: dict[str, Any] = raw_target
            comp = str(target_d["component"])
            value = float(target_d["value"])
            is_dist = str(target_d.get("product", "distillate")) == "distillate"
            out_frac = (prof.y[0] if is_dist else prof.x[col.n - 1]).get(comp, 0.0)
            if key == "product_purity":
                g.append(out_frac - value)
            else:
                out_flow = prof.d if is_dist else prof.b
                feed_frac = col.feed_comp.get(comp, 0.0) * col.f_total
                measured = out_flow * out_frac / max(feed_frac, _FLOW_FLOOR)
                g.append(measured - value)
            scales.append(max(value, 1e-12))
            continue
        target = float(raw_target)
        if key == "reflux_ratio":
            g.append(prof.l0 / max(prof.d, _FLOW_FLOOR) - target)
        elif key == "boilup_ratio":
            g.append(prof.V[col.n - 1] / max(prof.b, _FLOW_FLOOR) - target)
        elif key == "distillate_rate":
            g.append(prof.d - target)
        elif key == "bottoms_rate":
            g.append(prof.b - target)
        elif key == "condenser_duty_W":
            g.append(prof.qc - target)
        elif key == "reboiler_duty_W":
            g.append(prof.qr - target)
        else:  # pragma: no cover - _parse_params rejects unknown keys
            raise ColumnSpecError(f"unsupported spec {key!r}")
        scales.append(max(target, 1e-12))
    return g, scales


def _solve_specs(col: _Column, tb: _ThermoBox, params: _Params) -> _Profile:
    """Drive the column specs onto their targets: bounded secant over the tears.

    Ratio-plus-rate pairs (reflux_ratio + distillate_rate and friends) pin the
    corresponding tear algebraically - l0 = R*D etc. - leaving a one-dimensional
    secant in the remaining tear. The mesh vapour profile barely responds to the
    reflux tear, so the full 2-D system is near-singular; the pinned ratio's
    residual is satisfied by construction and dropped. A spec that pins a tear
    directly (distillate_rate on a partial condenser) is applied as a constant.
    """
    _check_spec_feasibility(col, tb, params)
    t_top, t_bot = _initial_tears(col, params)
    specs = params.specs
    d_spec = specs.get("distillate_rate")
    b_spec = specs.get("bottoms_rate")
    r_spec = specs.get("reflux_ratio")
    vb_spec = specs.get("boilup_ratio")
    draw_total = sum(dr.flow for dr in params.draws)
    pin_top = False
    pin_bot = False
    skip: set[str] = set()
    if col.condenser == "total" and r_spec is not None and d_spec is not None:
        t_top = float(r_spec) * float(d_spec)
        pin_top = True
        skip.add("reflux_ratio")
    elif col.condenser == "total" and r_spec is not None and b_spec is not None:
        t_top = float(r_spec) * max(col.f_total - float(b_spec) - draw_total, _FLOW_FLOOR)
        pin_top = True
        skip.add("reflux_ratio")
    if col.reboiler == "kettle" and vb_spec is not None and d_spec is not None:
        t_bot = float(vb_spec) * max(col.f_total - float(d_spec) - draw_total, _FLOW_FLOOR)
        pin_bot = True
        skip.add("boilup_ratio")
    elif col.reboiler == "kettle" and vb_spec is not None and b_spec is not None:
        t_bot = float(vb_spec) * float(b_spec)
        pin_bot = True
        skip.add("boilup_ratio")
    if col.condenser == "partial" and d_spec is not None:
        t_top = float(d_spec)
        pin_top = True
        skip.add("distillate_rate")
    free_top = t_top is not None and not pin_top
    free_bot = t_bot is not None and not pin_bot
    if col.condenser == "total" and pin_top and free_bot and t_top is not None:
        # Seed the first mesh at high vapour traffic: a fully-boiling column has
        # every stage two-phase and the mesh converges robustly there; the warm-
        # started secant then walks the kettle tear down to the specification.
        t_bot = t_top + col.f_total * 0.2

    state: dict[str, _Profile | None] = {"seed": None}

    def mesh_at(top: float | None, bot: float | None) -> _Profile:
        """Solve the mesh at given tears, backtracking toward the seed on failure."""
        last: ColumnConvergenceError | None = None
        for _attempt in range(3):
            try:
                prof = _solve_mesh(col, tb, top, bot, state["seed"])
                state["seed"] = _copy_profile(col, prof)
                return prof
            except ColumnConvergenceError as exc:
                last = exc
            except ValueError as exc:
                # Unconverged iterates can leave the flash's physical domain
                # (pydantic stream validation inside the PR package). That is a
                # convergence failure of this iterate, not a caller error.
                last = ColumnConvergenceError(f"iterate left the flash domain: {exc}")
            seed = state["seed"]
            if seed is None:
                break
            if top is not None:
                top = top + 0.5 * (seed.l0 - top)
            if bot is not None:
                bot = bot + 0.5 * (seed.V[col.n - 1] - bot)
        raise ColumnConvergenceError(f"mesh failed at tears {(top, bot)}: {last}")

    def apply_vector(v: list[float]) -> tuple[float | None, float | None]:
        """Map the free-tear vector back onto (top, bot) tears."""
        it = iter(v)
        a = next(it) if free_top else t_top
        b2 = next(it) if free_bot else t_bot
        return a, b2

    def tears_of(v: list[float]) -> tuple[float, float]:
        """Unpack the free-tear vector into concrete tears.

        The ``None`` members of ``apply_vector``'s result denote a pinned tear
        that was never set from specs; the spec loop only runs when every
        tear is either pinned to a value or free, so None here is a caller
        bug and must surface as a typed error.
        """
        top, bot = apply_vector(v)
        if top is None or bot is None:
            raise ColumnSpecError("column spec tears unresolved before secant solve")
        return top, bot

    x: list[float] = []
    # Separation direction per free tear slot: more reflux (total-condenser top
    # tear) and more boilup mean MORE separation; a partial-condenser distillate
    # tear is inverted (a bigger distillate draw means less refluxing).
    tear_dir: list[float] = []
    if free_top and t_top is not None:
        x.append(float(t_top))
        tear_dir.append(1.0 if col.condenser == "total" else -1.0)
    if free_bot and t_bot is not None:
        x.append(float(t_bot))
        tear_dir.append(1.0)
    if not x:
        # Everything pinned algebraically: the tears already encode both targets.
        prof = mesh_at(t_top, t_bot)
        g0, s0 = _spec_g(col, params, prof, skip)
        rel0 = [gi / s for gi, s in zip(g0, s0, strict=True)]
        if max(abs(r) for r in rel0) < _SPEC_TOL:
            return prof
        raise ColumnSpecError(
            f"column specs cannot be driven: no free tear variables remain; "
            f"residuals {[round(r, 6) for r in rel0]}"
        )

    flow_cap = 50.0 * col.f_total
    best_res = float("inf")
    # Monotone-bracket abort state: purity/recovery residuals are monotone in
    # the separation level, so if every still-unmet separation residual sits on
    # the wrong side of its target and the secant keeps stepping FURTHER from
    # the maximum-separation corner without any of them improving, both bracket
    # ends (worst and best separation explored) are on the wrong side - the
    # target is unreachable. Raise immediately instead of wandering into
    # degenerate tears (measured 162 s on the 0.999-purity case before this).
    keys = [k for k in params.specs if k not in skip]
    sep_idx = [k for k, key in enumerate(keys) if key in ("product_purity", "component_recovery")]
    best_wrong = [float("inf")] * len(sep_idx)
    flee = 0
    stale = 0
    rel: list[float] = []
    for _ in range(_SPEC_MAX):
        top, bot = tears_of(x)
        prof = mesh_at(top, bot)
        g, scales = _spec_g(col, params, prof, skip)
        rel = [gi / s for gi, s in zip(g, scales, strict=True)]
        if max(abs(r) for r in rel) < _SPEC_TOL:
            return prof
        res = max(abs(r) for r in rel)
        if res < best_res - 1e-4 * best_res:
            best_res, stale = res, 0
        else:
            stale += 1
            if stale >= 6:
                raise ColumnSpecError(
                    f"column spec residual stuck near {res:.4g} over 6 secant iterations; "
                    f"the specification is likely infeasible for this column"
                )
        jac_cols = []
        for i in range(len(x)):
            dx = max(0.02 * abs(x[i]), 1e-3 * col.f_total)
            x2 = list(x)
            x2[i] += dx
            prof2: _Profile | None = None
            # A finite-difference probe may land in an unsolvable tear region
            # long before the main line does; shrink the probe before giving up
            # on the secant entirely.
            last_probe_err: ColumnConvergenceError | None = None
            for _shrink in range(3):
                t2_top, t2_bot = tears_of(x2)
                try:
                    prof2 = mesh_at(t2_top, t2_bot)
                    break
                except ColumnConvergenceError as exc:
                    last_probe_err = exc
                    x2 = list(x)
                    x2[i] += dx / 8.0 ** (_shrink + 1)
            if prof2 is None:
                raise ColumnSpecError(
                    f"spec secant cannot probe the column state (tears {apply_vector(x2)}); "
                    f"the specification is likely infeasible: {last_probe_err}"
                ) from last_probe_err
            g2, _ = _spec_g(col, params, prof2, skip)
            # Jacobian on the SAME scaled residuals the rhs uses - mixing raw
            # differences with a scaled rhs shrank rate-spec steps by the rate
            # scale (45x here) and crawled toward the target.
            rel2 = [g2i / s for g2i, s in zip(g2, scales, strict=True)]
            jac_cols.append([(rel2[k] - rel[k]) / dx for k in range(len(rel))])
        nf = len(x)
        matrix = [[jac_cols[i][k] for i in range(nf)] for k in range(nf)]
        try:
            step = _gauss(matrix, [-r for r in rel])
        except ZeroDivisionError as exc:
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {[round(r, 6) for r in rel]}"
            ) from exc
        if any(abs(v) > flow_cap for v in step):
            raise ColumnSpecError(
                f"column specs are unsatisfiable (secant Jacobian singular); "
                f"residuals {[round(r, 6) for r in rel]}"
            )
        if sep_idx:
            sep_step = sum(tear_dir[i] * step[i] for i in range(nf))
            improved = False
            wrong = False
            for k, j in zip(sep_idx, range(len(sep_idx)), strict=True):
                if abs(rel[k]) < _SPEC_TOL:
                    best_wrong[j] = 0.0
                    continue
                wrong = True
                if abs(rel[k]) < best_wrong[j] - 1e-12:
                    best_wrong[j] = abs(rel[k])
                    improved = True
            if wrong and not improved:
                away = all((rel[k] < 0.0) == (sep_step < 0.0) for k in sep_idx if abs(rel[k]) >= _SPEC_TOL)
                if away:
                    flee += 1
                    if flee >= 2:
                        raise ColumnSpecError(
                            f"column specs are unreachable: the separation bracket shows the "
                            f"target on the far side of the maximum-separation corner "
                            f"(separation residuals {[round(r, 6) for r in rel]}); the "
                            f"specification is infeasible for this column"
                        )
                else:
                    flee = 0
            else:
                flee = 0
        x = [min(max(x[i] + step[i], _FLOW_FLOOR), flow_cap) for i in range(nf)]
    raise ColumnSpecError(
        f"column specs could not be satisfied within {_SPEC_MAX} secant iterations "
        f"(residuals {[round(r, 6) for r in rel]}); the specification is likely infeasible "
        f"for this column (stages, pressure, feeds)"
    )


def _condensed_distillate(
    tb: _ThermoBox, y0: dict[str, float], t_top: float, p_cond: float, d: float
) -> StreamState:
    """Total-condenser product: saturated liquid at the condenser pressure.

    Flashed at the bubble point of the vapour composition so the returned phase
    list is self-consistent; flashing the two-phase top-stage equilibrium would
    carry phase fractions that do not sum to one for a pure-liquid product.
    """
    y0_ready = _flash_ready(y0, y0)
    t_bubble = tb.bubble_temperature(y0_ready, p_cond)
    if t_bubble is None:
        t_bubble = t_top  # degenerate edge; flash near the top-stage state
    return tb.pt(y0_ready, t_bubble, p_cond, max(d, _FLOW_FLOOR))


def _zero_flow_state(comp: dict[str, float], t: float, p: float) -> StreamState:
    """Placeholder outlet for a port the configuration leaves unused."""
    return StreamState(
        T=t,
        P=p,
        molar_flow=0.0,
        composition=_flash_ready(comp, comp),
        vapor_fraction=0.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )


@register("unit", "column")
class Column:
    """Rigorous equilibrium-stage column: inside-out (Boston-Sullivan) primary,
    Naphtali-Sandholm Newton fallback on non-convergence.

    Ports: one ``feed`` inlet; ``distillate``, ``bottoms`` and one ``side_draw``
    outlet (a zero-flow state when no draw is configured). Additional feeds on
    any stage and further draws are declared in params; their material stays
    inside the unit's own balance (reported in info) - the flowsheet graph sees
    the three outlet ports only.
    """

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms", "side_draw")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        graph_feed = inlets.get("feed")
        graph_dict: dict[str, Any] | None = None
        if graph_feed is not None:
            if graph_feed.molar_flow <= 0.0:
                raise ColumnSpecError("feed port stream has zero molar flow")
            graph_dict = {
                "T": graph_feed.T,
                "P": graph_feed.P,
                "molar_flow": graph_feed.molar_flow,
                "composition": dict(graph_feed.composition),
            }
        parsed = _parse_params(params, graph_dict)
        tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
        col = _build_column(parsed, tb)

        prof = _solve_specs(col, tb, parsed)

        # Boundary stream states (exact; these drive the reported energy balance).
        feed_states: list[StreamState] = []
        if graph_feed is not None:
            feed_states.append(graph_feed)
        for f in parsed.feeds:
            if graph_feed is not None and f.comp == dict(graph_feed.composition) and f is parsed.feeds[0]:
                continue  # the port feed is already counted
            feed_states.append(tb.pt(f.comp, f.T, f.P, f.flow))

        try:
            if col.condenser == "total":
                distillate = _condensed_distillate(tb, prof.y[0], prof.T[0], col.pressures[0], prof.d)
            else:
                distillate = tb.pt(prof.y[0], prof.T[0], col.pressures[0], prof.d)
            bottoms = tb.pt(prof.x[col.n - 1], prof.T[col.n - 1], col.pressures[col.n - 1], prof.b)
            out_states: list[StreamState] = [distillate, bottoms]
            if parsed.draws:
                first = parsed.draws[0]
                j = first.stage - 1
                comp = prof.y[j] if first.vapor else prof.x[j]
                side_draw = tb.pt(comp, prof.T[j], col.pressures[j], first.flow)
                out_states.append(side_draw)
                for extra in parsed.draws[1:]:
                    je = extra.stage - 1
                    comp_e = prof.y[je] if extra.vapor else prof.x[je]
                    out_states.append(tb.pt(comp_e, prof.T[je], col.pressures[je], extra.flow))
            else:
                side_draw = _zero_flow_state(bottoms.composition, prof.T[col.n - 1], col.pressures[col.n - 1])

            _close_energy_balance(col, tb, prof, feed_states, out_states)
        except ValueError as exc:
            # A converged profile should be physical; a degenerate edge (zero
            # distillate at an extreme tear) still must not leak a pydantic
            # error past the plugin contract.
            raise ColumnConvergenceError(f"converged column state left the physical domain: {exc}") from exc

        info: dict[str, float] = {
            "n_stages": float(col.n),
            "condenser_duty_W": prof.qc,
            "reboiler_duty_W": prof.qr,
            "distillate_mol_s": prof.d,
            "bottoms_mol_s": prof.b,
            "outer_iterations": float(prof.outer),
            "inner_iterations": float(prof.inner),
            "ns_used": float(prof.ns_used),
            "reflux_ratio": prof.l0 / max(prof.d, _FLOW_FLOOR) if col.condenser == "total" else 0.0,
            "boilup_ratio": (
                prof.V[col.n - 1] / max(prof.b, _FLOW_FLOOR) if col.reboiler == "kettle" else 0.0
            ),
        }
        for j in range(col.n):
            info[f"stage_{j}_T_K"] = prof.T[j]
            info[f"stage_{j}_P_Pa"] = col.pressures[j]
            info[f"stage_{j}_L_mol_s"] = prof.L[j]
            info[f"stage_{j}_V_mol_s"] = prof.V[j]
            for cid, frac in prof.x[j].items():
                info[f"stage_{j}_x_{cid}"] = frac
            for cid, frac in prof.y[j].items():
                info[f"stage_{j}_y_{cid}"] = frac

        return UnitResult(
            outlets={"distillate": distillate, "bottoms": bottoms, "side_draw": side_draw},
            duty_W=prof.qr - prof.qc,
            info=info,
        )

    @staticmethod
    def example_case() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """16-stage propane/isobutane split: 100 mol/s 50/50 at 330 K, 1.5 MPa.

        Total condenser, kettle reboiler, feed on stage 8, reflux ratio 2.5,
        distillate 45 mol/s.
        """
        feed = {
            "T": 330.0,
            "P": 1.5e6,
            "molar_flow": 100.0,
            "composition": {"C3": 0.5, "iC4": 0.5},
        }
        params = {
            "n_stages": 16,
            "condenser": "total",
            "reboiler": "kettle",
            "feed_stage": 8,
            "pressure_profile": 1.5e6,
            "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
        }
        return {"feed": feed}, params
