"""Shared heat-balance physics for the U-C R0 heat units (spec U-C).

Two-stream and multi-stream exchanger balances plus the Linnhoff problem
table, all on top of the :class:`~ngdesign.contracts.plugins.Thermo`
protocol (SI: K, Pa, J/mol, mol/s, W).

Two-stream balance (`two_stream`)
    Counter-current exchange with exactly one active spec: ``duty_W``,
    ``hot_T_out``, ``cold_T_out`` or ``min_approach_K``. The zoned pinch check
    samples each side's enthalpy curve at ``N_ZONE_SAMPLES`` points by PH
    flashes (so phase change is seen), forms zone-average molar cp on the
    union temperature grid and reports the minimum internal approach. A spec
    that drives the minimum approach below zero is refused with
    :class:`TemperatureCross`, naming the minimum delta-T and the hot/cold
    temperatures at the pinch. LMTD comes from
    :func:`ngdesign.sizing.lmtd.lmtd_counter` on the terminal temperatures,
    flagged ``lmtd_valid`` only while neither side changes phase (the
    terminal LMTD is meaningful only then).

Multi-stream balance (`multi_stream`)
    N hot and N cold sides; every active side carries an outlet-T spec except
    exactly one balance stream, which absorbs the residual duty so the unit
    closes at zero net duty. Composite curves are built from the same zoned
    samples; the minimum approach and the REAL hot/cold temperatures at the
    pinch zone end are reported.

Problem table (`problem_table`)
    Linnhoff et al., Trans. IChemE 61 (1983); Kemp, "User Guide on Process
    Integration for the Efficient Use of Energy in Process Plants": shifted
    temperatures hot = T - dtmin/2, cold = T + dtmin; breakpoints from every
    active stream end; interval CP*dT cascade; ``QH_min = max(0, -min
    cumulative)``, ``QC_min = QH_min + (total hot - total cold)``; the pinch
    sits at the BOTTOM breakpoint of the argmin zone, reported as real
    hot/cold temperatures.

Duty signs throughout: heat released by a hot stream is ``F*(h_in - h_out)``,
heat absorbed by a cold stream is ``F*(h_out - h_in)`` - both positive in the
stream's natural direction. Per-port duties reported by the multi-stream
adapter keep exactly these signs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.sizing.lmtd import lmtd_counter

#: PH-flash sample count per stream span for the zoned pinch check (spec: >= 20).
N_ZONE_SAMPLES = 24

#: Boundary-inclusivity epsilon for shifted-temperature comparisons, K.
_ZONE_EPS = 1e-9

#: Bisection iteration cap for the min-approach duty solve.
_BISECT_STEPS = 60

#: Bisection stop: relative duty interval.
_BISECT_RTOL = 1e-9


class TemperatureCross(ValueError):
    """A specified heat duty drives a stream through the other stream's curve.

    The message names the minimum approach and the hot/cold temperatures at
    the pinch where the cross occurs.
    """


@dataclass(frozen=True)
class TwoStreamSpec:
    """Exactly one active specification for a two-stream exchanger."""

    duty_W: float | None = None
    hot_T_out: float | None = None
    cold_T_out: float | None = None
    min_approach_K: float | None = None

    def __post_init__(self) -> None:
        if len(self.given) != 1:
            raise ValueError(
                "specify exactly one of duty_W, hot_T_out, cold_T_out, min_approach_K; "
                f"got {self.given or 'none'}"
            )

    @property
    def given(self) -> tuple[str, ...]:
        """Names of the supplied spec fields."""
        names = ("duty_W", "hot_T_out", "cold_T_out", "min_approach_K")
        return tuple(name for name in names if getattr(self, name) is not None)

    @property
    def name(self) -> str:
        """The active spec's parameter name."""
        return self.given[0]


@dataclass(frozen=True)
class TwoStreamResult:
    """Two-stream balance result: outlets plus the reported info scalars."""

    hot_out: StreamState
    cold_out: StreamState
    duty_W: float  # heat transferred hot -> cold (positive when heating the cold side)
    lmtd_K: float
    lmtd_valid: bool
    min_approach_K: float
    UA_W_K: float
    pinch_T_hot_K: float
    pinch_T_cold_K: float


@dataclass(frozen=True)
class MultiStreamSide:
    """One side handed to :func:`multi_stream`; ``T_out=None`` = balance stream."""

    state: StreamState
    T_out: float | None = None
    dP: float = 0.0


@dataclass(frozen=True)
class MultiStreamResult:
    """Multi-stream balance result, positional per hot/cold side."""

    hot_outs: tuple[StreamState, ...]
    cold_outs: tuple[StreamState, ...]
    #: Heat released by each hot side, F*(h_in - h_out), W (positive when releasing).
    hot_duties_W: tuple[float, ...]
    #: Heat absorbed by each cold side, F*(h_out - h_in), W (positive when absorbing).
    cold_duties_W: tuple[float, ...]
    min_approach_K: float
    pinch_T_hot_K: float
    pinch_T_cold_K: float


@dataclass(frozen=True)
class ProblemStream:
    """One stream handed to the problem table (pure arithmetic, no thermo)."""

    T_supply: float  # K
    T_target: float  # K
    cp_W_per_K: float  # W/K, positive
    is_hot: bool


@dataclass(frozen=True)
class ProblemTableResult:
    """Problem-table targets: minimum utilities and the pinch temperatures."""

    qh_min_W: float
    qc_min_W: float
    pinch_T_hot_K: float
    pinch_T_cold_K: float


@dataclass(frozen=True)
class _Sampled:
    """One stream side sampled on its span (per-mole enthalpies, T descending)."""

    temps: tuple[float, ...]  # K, strictly descending from the hot end of the span
    enthalpies: tuple[float, ...]  # J/mol at each sample, aligned with temps
    vapor_fractions: tuple[float, ...]  # at each sample, aligned with temps
    flow: float  # mol/s

    @property
    def T_top(self) -> float:
        return self.temps[0]

    @property
    def T_bottom(self) -> float:
        return self.temps[-1]

    def h_at(self, T: float) -> float:
        """Piecewise-linear per-mole enthalpy at T, clamped to the span."""
        temps, hs = self.temps, self.enthalpies
        if T >= temps[0]:
            return hs[0]
        if T <= temps[-1]:
            return hs[-1]
        for i in range(len(temps) - 1):
            t_hi, t_lo = temps[i], temps[i + 1]
            if t_lo <= T <= t_hi:
                w = (T - t_lo) / (t_hi - t_lo)
                return hs[i + 1] + w * (hs[i] - hs[i + 1])
        raise AssertionError("unreachable: T inside span but no bracketing sample")  # pragma: no cover

    def phase_change_free(self) -> bool:
        """True while every sample keeps the inlet's phase (vf within 1e-6)."""
        vf_in = self.vapor_fractions[0]
        return all(abs(vf_in - vf) <= 1e-6 for vf in self.vapor_fractions)


def _sample_side(
    thermo: Thermo,
    z: dict[str, float],
    P: float,
    T_in: float,
    h_in: float,
    T_out: float,
    h_out: float,
    flow: float,
    n_points: int = N_ZONE_SAMPLES,
) -> _Sampled:
    """Sample a side's span at n_points+1 enthalpy levels by PH flashes.

    The endpoints are the solved inlet/outlet states themselves, so the grid
    is exact at both ends; interior points see phase change because each
    sample is a PH flash at the side's outlet pressure.
    """
    pairs: list[tuple[float, float, float]] = []
    for i in range(n_points + 1):
        w = i / n_points
        h = h_in + w * (h_out - h_in)
        state = thermo.flash_ph(z, P, h, flow)
        pairs.append((state.T, h, state.vapor_fraction))
    # Descending temperature (PH flashes are monotone in h for normal fluids;
    # a stable sort keeps the grid consistent, duplicates dropped).
    pairs.sort(key=lambda p: -p[0])
    temps = [pairs[0][0]]
    enthalpies = [pairs[0][1]]
    vfs = [pairs[0][2]]
    for t, h, vf in pairs[1:]:
        if t < temps[-1] - 1e-12:
            temps.append(t)
            enthalpies.append(h)
            vfs.append(vf)
    return _Sampled(temps=tuple(temps), enthalpies=tuple(enthalpies), vapor_fractions=tuple(vfs), flow=flow)


def _cum_hot(sides: tuple[_Sampled, ...], T: float) -> float:
    """Cumulative heat released above temperature T by the hot composite, W."""
    total = 0.0
    for s in sides:
        total += s.flow * (s.h_at(s.T_top) - s.h_at(min(T, s.T_top)))
    return total


def _cum_cold(sides: tuple[_Sampled, ...], T: float) -> float:
    """Cumulative heat absorbed below temperature T by the cold composite, W."""
    total = 0.0
    for s in sides:
        total += s.flow * (s.h_at(min(T, s.T_top)) - s.h_at(s.T_bottom))
    return total


def _invert(grid: tuple[tuple[float, float], ...], u: float) -> float:
    """Piecewise-linear inversion: temperature at cumulative duty u.

    ``grid`` is ((u_k, T_k), ...) with u ascending; plateaus (zero composite
    cp outside a stream's span) resolve to the edge where the real curve
    ends: at ``u_max`` the FIRST temperature attaining it (the hot bottom /
    cold top), at ``u_min`` the LAST one (the hot top / cold bottom).
    """
    u_min, u_max = grid[0][0], grid[-1][0]
    if u >= u_max:
        for _u, t in grid:
            if _u >= u_max:
                return t
    if u <= u_min:
        t = grid[0][1]
        for _u, t_k in grid:
            if _u > u_min:
                break
            t = t_k
        return t
    for i in range(len(grid) - 1):
        u0, t0 = grid[i]
        u1, t1 = grid[i + 1]
        if u0 <= u <= u1 and u1 > u0:
            w = (u - u0) / (u1 - u0)
            return t0 + w * (t1 - t0)
    raise AssertionError("unreachable: u inside the grid but no non-degenerate bracket")  # pragma: no cover


def _pinch(
    hots: tuple[_Sampled, ...],
    colds: tuple[_Sampled, ...],
) -> tuple[float, float, float]:
    """Minimum composite approach and the real hot/cold temperatures at it, K.

    Counter-current pairing: walking down from the hot-inlet end, the hot
    composite has released u while the cold composite has absorbed Q - u. The
    minimum of the approach over the union of both composites' zone boundaries
    is exact piecewise-linear arithmetic (the minimum of a piecewise-linear
    function sits on a knot of one of the two curves).
    """
    q_tot = _cum_hot(hots, min(s.T_bottom for s in hots))
    boundary_temps: set[float] = set()
    for s in hots + colds:
        boundary_temps.update(s.temps)

    # Hot composite: (u, T) with u ascending as T descends. Cold composite:
    # (v, T) with v ascending as T ASCENDS (absorbed from the cold inlet end).
    hot_pairs: list[tuple[float, float]] = []
    cold_pairs: list[tuple[float, float]] = []
    for T in sorted(boundary_temps, reverse=True):
        hot_pairs.append((_cum_hot(hots, T), T))
    for T in sorted(boundary_temps):
        cold_pairs.append((_cum_cold(colds, T), T))
    hot_grid = tuple(hot_pairs)
    cold_grid = tuple(cold_pairs)

    best = (float("inf"), float("nan"), float("nan"))
    for u, T_hot in hot_grid:
        T_cold = _invert(cold_grid, q_tot - u)
        if T_hot - T_cold < best[0]:
            best = (T_hot - T_cold, T_hot, T_cold)
    for v, T_cold in cold_grid:
        T_hot = _invert(hot_grid, q_tot - v)
        if T_hot - T_cold < best[0]:
            best = (T_hot - T_cold, T_hot, T_cold)
    return best


def two_stream(
    hot: StreamState,
    cold: StreamState,
    spec: TwoStreamSpec,
    thermo: Thermo,
    dP_hot: float = 0.0,
    dP_cold: float = 0.0,
) -> TwoStreamResult:
    """Counter-current two-stream balance with a zoned pinch check.

    ``spec`` carries exactly one of duty_W / hot_T_out / cold_T_out /
    min_approach_K (the last solved by duty bisection against the zoned
    check). Pressures drop by dP_hot / dP_cold. Refuses a temperature cross
    with the minimum approach and the temperatures at the pinch.
    """
    if dP_hot < 0 or dP_cold < 0:
        raise ValueError("dP_hot and dP_cold must be >= 0")
    P_h_out = hot.P - dP_hot
    P_c_out = cold.P - dP_cold
    if P_h_out <= 0:
        raise ValueError(f"dP_hot {dP_hot} leaves a non-positive hot outlet pressure")
    if P_c_out <= 0:
        raise ValueError(f"dP_cold {dP_cold} leaves a non-positive cold outlet pressure")

    F_h, F_c = hot.molar_flow, cold.molar_flow
    if F_h <= 0.0 or F_c <= 0.0:
        # No heat transfer is possible: both sides pass through (the zero-flow
        # side as a copy of its inlet; the active side re-flashed at its dP).
        if spec.name != "duty_W" or spec.duty_W != 0.0:
            raise ValueError(
                f"{spec.name} needs both streams flowing; a zero-flow side cannot transfer duty"
            )
        hot_pass = hot.model_copy(update={"P": P_h_out}) if F_h > 0 else hot.model_copy()
        cold_pass = cold.model_copy(update={"P": P_c_out}) if F_c > 0 else cold.model_copy()
        return TwoStreamResult(
            hot_out=hot_pass,
            cold_out=cold_pass,
            duty_W=0.0,
            lmtd_K=0.0,
            lmtd_valid=False,
            min_approach_K=0.0,
            UA_W_K=0.0,
            pinch_T_hot_K=hot.T,
            pinch_T_cold_K=cold.T,
        )

    hot_out, cold_out, duty_W = _two_stream_outlets(hot, cold, spec, thermo, P_h_out, P_c_out)

    hot_side = _sample_side(thermo, hot.composition, P_h_out, hot.T, hot.enthalpy, hot_out.T, hot_out.enthalpy, F_h)
    cold_side = _sample_side(thermo, cold.composition, P_c_out, cold.T, cold.enthalpy, cold_out.T, cold_out.enthalpy, F_c)
    min_approach, pinch_T_hot, pinch_T_cold = _pinch((hot_side,), (cold_side,))
    if min_approach < 0.0:
        raise TemperatureCross(
            f"temperature cross: minimum approach {min_approach:.4f} K at hot T = "
            f"{pinch_T_hot:.2f} K / cold T = {pinch_T_cold:.2f} K"
        )

    lmtd = lmtd_counter(hot.T, hot_out.T, cold.T, cold_out.T)
    lmtd_valid = hot_side.phase_change_free() and cold_side.phase_change_free()
    return TwoStreamResult(
        hot_out=hot_out,
        cold_out=cold_out,
        duty_W=duty_W,
        lmtd_K=lmtd,
        lmtd_valid=lmtd_valid,
        min_approach_K=min_approach,
        UA_W_K=duty_W / lmtd,
        pinch_T_hot_K=pinch_T_hot,
        pinch_T_cold_K=pinch_T_cold,
    )


def _two_stream_outlets(
    hot: StreamState,
    cold: StreamState,
    spec: TwoStreamSpec,
    thermo: Thermo,
    P_h_out: float,
    P_c_out: float,
) -> tuple[StreamState, StreamState, float]:
    """Solve both outlet states for the active spec; returns (hot, cold, duty)."""
    F_h, F_c = hot.molar_flow, cold.molar_flow
    match spec.name:
        case "duty_W":
            duty = float(spec.duty_W)  # type: ignore[arg-type]
            hot_out = thermo.flash_ph(hot.composition, P_h_out, hot.enthalpy - duty / F_h, F_h)
            cold_out = thermo.flash_ph(cold.composition, P_c_out, cold.enthalpy + duty / F_c, F_c)
            return hot_out, cold_out, duty
        case "hot_T_out":
            T_out = float(spec.hot_T_out)  # type: ignore[arg-type]
            if T_out <= 0:
                raise ValueError(f"hot_T_out {T_out} K must be > 0")
            hot_out = thermo.flash_pt(hot.composition, T_out, P_h_out, F_h)
            duty = F_h * (hot.enthalpy - hot_out.enthalpy)
            cold_out = thermo.flash_ph(cold.composition, P_c_out, cold.enthalpy + duty / F_c, F_c)
            return hot_out, cold_out, duty
        case "cold_T_out":
            T_out = float(spec.cold_T_out)  # type: ignore[arg-type]
            if T_out <= 0:
                raise ValueError(f"cold_T_out {T_out} K must be > 0")
            cold_out = thermo.flash_pt(cold.composition, T_out, P_c_out, F_c)
            duty = F_c * (cold_out.enthalpy - cold.enthalpy)
            hot_out = thermo.flash_ph(hot.composition, P_h_out, hot.enthalpy - duty / F_h, F_h)
            return hot_out, cold_out, duty
        case _:
            return _two_stream_min_approach(hot, cold, spec, thermo, P_h_out, P_c_out)


def _two_stream_min_approach(
    hot: StreamState,
    cold: StreamState,
    spec: TwoStreamSpec,
    thermo: Thermo,
    P_h_out: float,
    P_c_out: float,
) -> tuple[StreamState, StreamState, float]:
    """Bisect the duty until the zoned minimum approach hits the target."""
    F_h, F_c = hot.molar_flow, cold.molar_flow
    target = float(spec.min_approach_K)  # type: ignore[arg-type]
    if target < 0:
        raise ValueError(f"min_approach_K {target} must be >= 0")

    def approach_at(duty: float) -> float:
        hot_out = thermo.flash_ph(hot.composition, P_h_out, hot.enthalpy - duty / F_h, F_h)
        cold_out = thermo.flash_ph(cold.composition, P_c_out, cold.enthalpy + duty / F_c, F_c)
        hs = _sample_side(thermo, hot.composition, P_h_out, hot.T, hot.enthalpy, hot_out.T, hot_out.enthalpy, F_h)
        cs = _sample_side(thermo, cold.composition, P_c_out, cold.T, cold.enthalpy, cold_out.T, cold_out.enthalpy, F_c)
        return _pinch((hs,), (cs,))[0]

    # Upper duty bound: the hot outlet reaches the cold inlet temperature
    # (zero bottom approach), the closest a counter-current pair can get.
    hot_ref = thermo.flash_pt(hot.composition, cold.T, P_h_out, F_h)
    q_max = F_h * (hot.enthalpy - hot_ref.enthalpy)
    if q_max <= 0:
        raise ValueError(f"inlet temperatures cross: hot {hot.T} K vs cold {cold.T} K")

    q_lo, q_hi = 0.0, q_max
    if approach_at(q_lo) < target:
        raise ValueError(
            f"min_approach_K {target} exceeds the zero-duty approach {approach_at(q_lo):.4f} K"
        )
    for _ in range(_BISECT_STEPS):
        mid = 0.5 * (q_lo + q_hi)
        if approach_at(mid) >= target:
            q_lo = mid  # approach still above target: more duty is available
        else:
            q_hi = mid  # crossed below target: pull the duty back
        if q_hi - q_lo <= _BISECT_RTOL * max(abs(q_lo), abs(q_hi), 1.0):
            break
    duty = q_lo
    hot_out = thermo.flash_ph(hot.composition, P_h_out, hot.enthalpy - duty / F_h, F_h)
    cold_out = thermo.flash_ph(cold.composition, P_c_out, cold.enthalpy + duty / F_c, F_c)
    return hot_out, cold_out, duty


def multi_stream(
    hots: tuple[MultiStreamSide, ...],
    colds: tuple[MultiStreamSide, ...],
    thermo: Thermo,
) -> MultiStreamResult:
    """Multi-stream balance: every active side spec'd except one balance stream.

    The balance stream (``T_out=None``) absorbs the residual duty so the unit
    closes at zero net duty. Zero-flow sides pass through as copies of their
    inlets and are excluded from the balance and the pinch check. Refuses
    with :class:`TemperatureCross` when the composite curves cross.
    """
    active_hot = [(i, side) for i, side in enumerate(hots) if side.state.molar_flow > 0.0]
    active_cold = [(i, side) for i, side in enumerate(colds) if side.state.molar_flow > 0.0]
    if not active_hot and not active_cold:
        raise ValueError("multi_stream needs at least one stream with positive flow")
    balance = [
        (kind, i, side)
        for kind, sides in (("hot", active_hot), ("cold", active_cold))
        for i, side in sides
        if side.T_out is None
    ]
    if len(balance) != 1:
        raise ValueError(
            "exactly one active stream must be the balance stream (no T_out spec); got "
            f"{len(balance)}"
        )
    kind_b, i_b, side_b = balance[0]
    for _, side in (*active_hot, *active_cold):
        if side.T_out is not None:
            if side.T_out <= 0:
                raise ValueError(f"T_out {side.T_out} K must be > 0")
            if side.dP < 0:
                raise ValueError("side dP must be >= 0")

    hot_outs = list(hots)
    cold_outs = list(colds)
    residual_W = 0.0  # duty the balance stream must absorb (sign: into the stream)
    hot_duties: dict[int, float] = {}
    cold_duties: dict[int, float] = {}
    for kind, sides in (("hot", active_hot), ("cold", active_cold)):
        for i, side in sides:
            if (kind, i) == (kind_b, i_b):
                continue
            state = side.state
            P_out = state.P - side.dP
            if P_out <= 0:
                raise ValueError(f"side dP {side.dP} leaves a non-positive outlet pressure")
            out = thermo.flash_pt(state.composition, float(side.T_out), P_out, state.molar_flow)  # type: ignore[arg-type]
            duty = state.molar_flow * (out.enthalpy - state.enthalpy)
            if kind == "hot":
                hot_outs[i] = out
                hot_duties[i] = -duty  # released
                residual_W -= duty
            else:
                cold_outs[i] = out
                cold_duties[i] = duty  # absorbed
                residual_W += duty

    b_state = side_b.state
    P_b_out = b_state.P - side_b.dP
    if P_b_out <= 0:
        raise ValueError(f"balance side dP {side_b.dP} leaves a non-positive outlet pressure")
    F_b = b_state.molar_flow  # positive: balance sides come from the active lists
    b_out = thermo.flash_ph(b_state.composition, P_b_out, b_state.enthalpy + residual_W / F_b, F_b)
    b_duty = F_b * (b_out.enthalpy - b_state.enthalpy)
    if kind_b == "hot":
        hot_outs[i_b] = b_out
        hot_duties[i_b] = -b_duty
    else:
        cold_outs[i_b] = b_out
        cold_duties[i_b] = b_duty

    sampled_hot = tuple(
        _sample_side(thermo, s.state.composition, s.state.P - s.dP, s.state.T, s.state.enthalpy, out.T, out.enthalpy, s.state.molar_flow)
        for s, out in ((side, hot_outs[i]) for i, side in active_hot)
    )
    sampled_cold = tuple(
        _sample_side(thermo, s.state.composition, s.state.P - s.dP, s.state.T, s.state.enthalpy, out.T, out.enthalpy, s.state.molar_flow)
        for s, out in ((side, cold_outs[i]) for i, side in active_cold)
    )
    min_approach, pinch_T_hot, pinch_T_cold = _pinch(sampled_hot, sampled_cold)
    if min_approach < 0.0:
        raise TemperatureCross(
            f"temperature cross: minimum approach {min_approach:.4f} K at hot T = "
            f"{pinch_T_hot:.2f} K / cold T = {pinch_T_cold:.2f} K"
        )

    final_hot = tuple(
        hot_outs[i] if i in hot_duties or (kind_b == "hot" and i == i_b) else side.state.model_copy()
        for i, side in enumerate(hots)
    )
    final_cold = tuple(
        cold_outs[i] if i in cold_duties or (kind_b == "cold" and i == i_b) else side.state.model_copy()
        for i, side in enumerate(colds)
    )
    return MultiStreamResult(
        hot_outs=final_hot,
        cold_outs=final_cold,
        hot_duties_W=tuple(hot_duties.get(i, 0.0) for i, _ in enumerate(hots)),
        cold_duties_W=tuple(cold_duties.get(i, 0.0) for i, _ in enumerate(colds)),
        min_approach_K=min_approach,
        pinch_T_hot_K=pinch_T_hot,
        pinch_T_cold_K=pinch_T_cold,
    )


def problem_table(streams: tuple[ProblemStream, ...], dT_min: float) -> ProblemTableResult:
    """The Linnhoff problem table: minimum utilities and the pinch (Kemp ch. 2).

    Shifted temperatures: hot ``T - dT_min/2``, cold ``T + dT_min/2``. Breakpoints
    are every active stream's shifted ends, sorted descending; each interval cascades
    ``(sum hot CP - sum cold CP) * dT`` with a stream active when both its
    shifted ends bracket the interval. ``QH_min = max(0, -min cumulative)``,
    ``QC_min = QH_min + (total hot - total cold)``. The pinch is the BOTTOM
    breakpoint of the argmin interval (using the top one is the classic
    off-by-one), reported as the real hot/cold temperatures
    ``T_shifted + dT_min/2`` / ``T_shifted - dT_min/2``. Pure arithmetic.
    """
    if dT_min <= 0:
        raise ValueError(f"dT_min {dT_min} K must be > 0")
    active = [s for s in streams if s.cp_W_per_K > 0.0 and s.T_supply != s.T_target]
    if not active:
        raise ValueError("problem table needs at least one stream with CP > 0 and a temperature span")
    for s in active:
        if s.is_hot and s.T_target > s.T_supply:
            raise ValueError(f"hot stream {s.T_supply} -> {s.T_target} K heats up: swap is_hot or fix targets")
        if not s.is_hot and s.T_target < s.T_supply:
            raise ValueError(f"cold stream {s.T_supply} -> {s.T_target} K cools down: fix targets")

    shifted: list[tuple[float, bool]] = []
    for s in active:
        half = dT_min / 2.0
        if s.is_hot:
            shifted.append((s.T_supply - half, True))
            shifted.append((s.T_target - half, True))
        else:
            shifted.append((s.T_supply + half, False))
            shifted.append((s.T_target + half, False))

    breakpoints: list[float] = []
    for value in sorted((t for t, _ in shifted), reverse=True):
        if not breakpoints or value < breakpoints[-1] - _ZONE_EPS:
            breakpoints.append(value)
        else:
            breakpoints[-1] = max(breakpoints[-1], value)

    qh_total = sum(s.cp_W_per_K * (s.T_supply - s.T_target) for s in active if s.is_hot)
    qc_total = sum(s.cp_W_per_K * (s.T_target - s.T_supply) for s in active if not s.is_hot)

    cumulative = 0.0
    min_cum = 0.0
    min_index = -1  # -1: the cascade start (pinch at the top when QH_min = 0)
    for j in range(len(breakpoints) - 1):
        t_top, t_bottom = breakpoints[j], breakpoints[j + 1]
        dT_zone = t_top - t_bottom
        if dT_zone <= _ZONE_EPS:
            continue
        cp_hot = sum(
            s.cp_W_per_K
            for s in active
            if s.is_hot and s.T_supply - dT_min / 2.0 >= t_top - _ZONE_EPS and s.T_target - dT_min / 2.0 <= t_bottom + _ZONE_EPS
        )
        cp_cold = sum(
            s.cp_W_per_K
            for s in active
            if not s.is_hot and s.T_supply + dT_min / 2.0 <= t_bottom + _ZONE_EPS and s.T_target + dT_min / 2.0 >= t_top - _ZONE_EPS
        )
        cumulative += (cp_hot - cp_cold) * dT_zone
        if cumulative < min_cum:
            min_cum = cumulative
            min_index = j

    qh_min = max(0.0, -min_cum)
    qc_min = qh_min + (qh_total - qc_total)

    # Pinch: the BOTTOM breakpoint of the argmin interval; the cascade start
    # (index -1) reports the top breakpoint (no deficit case, QH_min = 0).
    pinch_shifted = breakpoints[min_index + 1] if min_index >= 0 else breakpoints[0]
    half = dT_min / 2.0
    return ProblemTableResult(
        qh_min_W=qh_min,
        qc_min_W=qc_min,
        pinch_T_hot_K=pinch_shifted + half,
        pinch_T_cold_K=pinch_shifted - half,
    )
