"""Multi-stream exchanger R1: common-wall layer model (``specs/backend/units/multi_stream.md``).

Common-wall-temperature model (Haseler 1983, in *Heat Exchangers: Theory and Practice*,
Hemisphere; Paffenholz 1984), on a normalised length x in [0, 1], with a given layer
conductance (hA)_i per stream.  Hot streams enter at x = 0 and flow in +x; cold streams
enter at x = 1 and flow in -x:

    T_w(x) = Sum_i (hA)_i*T_i(x) / Sum_i (hA)_i
    hot:   dH_i/dx = -(hA)_i*(T_i - T_w)
    cold:  dH_i/dx = +(hA)_i*(T_i - T_w)
    H_hot(0) = F*h_in,   H_cold(1) = F*h_in

With two streams and constant C this is exactly counterflow with 1/UA = 1/(hA)_h +
1/(hA)_c.  T_i(H_i) is a monotone PCHIP table of 40 ``flash_ph`` samples, so phase-change
plateaus are carried.  Hot or cold is the port's role, not a temperature comparison.

A hot stream may sit below the wall locally and take heat back (with a colder hot stream
beside a hotter one); that is the model, not a fault, so the ordering check is on the
composites, max T_hot >= T_w >= min T_cold.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_bvp
from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.rating import RatingConvergenceError

HOT_PORTS = ("hot_in_1", "hot_in_2")
COLD_PORTS = ("cold_in_1", "cold_in_2")
_OUT_PORT = {
    "hot_in_1": "hot_out_1",
    "hot_in_2": "hot_out_2",
    "cold_in_1": "cold_out_1",
    "cold_in_2": "cold_out_2",
}

#: Flash samples of each stream's T(H) table.
_N_TABLE = 40

#: Fractional margin of a table past the opposite inlet, so a BVP trial stays inside it.
_TABLE_MARGIN = 0.02

_BVP_NODES = 41
_BVP_TOL = 1.0e-8
_BVP_MAX_NODES = 20000
_ORDER_TOL_K = 1.0e-9


class MultiStreamRatingError(ValueError):
    """A refused multi-stream rating; the message names the parameter."""


#: T(H) of one stream, vectorised.
TemperatureOf = Callable[[np.ndarray], np.ndarray]

#: Layer conductance density per stream at x: shape (n_streams, x.size), W/K.
ConductanceOf = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class WallStream:
    """One active stream of the common-wall BVP."""

    is_hot: bool
    H_in_W: float
    H_far_W: float  # the enthalpy flow at the opposite inlet temperature
    T_of_H: TemperatureOf


@dataclass(frozen=True)
class WallSolution:
    """The solved profiles on the BVP mesh."""

    x: np.ndarray
    H_W: np.ndarray  # (n_streams, n_x)
    T_K: np.ndarray  # (n_streams, n_x)
    T_wall_K: np.ndarray
    H_out_W: tuple[float, ...]


def uniform(ha: Sequence[float]) -> ConductanceOf:
    """Conductances spread uniformly along x."""
    values = np.asarray(ha, dtype=float).reshape(-1, 1)
    return lambda x: np.broadcast_to(values, (values.shape[0], x.size))


def solve_common_wall(
    streams: Sequence[WallStream], conductance: ConductanceOf, guess: WallSolution | None = None
) -> WallSolution:
    """Solve the common-wall BVP for any T(H) tables and hA(x)."""
    n = len(streams)
    sign = np.array([-1.0 if st.is_hot else 1.0 for st in streams]).reshape(-1, 1)
    h_in = np.array([st.H_in_W for st in streams]).reshape(-1, 1)
    # Solved in theta = (H - H_in)/scale: solve_bvp normalises its residual by 1 + |f|, so
    # with H near 1e6 W the round-off in y' exceeds the tolerance wherever a stream's f
    # crosses zero, and mesh refinement only makes it worse.
    scale = max(abs(st.H_far_W - st.H_in_W) for st in streams)

    def temperatures(theta: np.ndarray) -> np.ndarray:
        h = h_in + scale * theta
        return np.vstack([st.T_of_H(h[i]) for i, st in enumerate(streams)])

    def fun(x: np.ndarray, theta: np.ndarray) -> np.ndarray:
        t = temperatures(theta)
        ha = conductance(x)
        t_w = (ha * t).sum(axis=0) / ha.sum(axis=0)
        slope: np.ndarray = sign * ha * (t - t_w) / scale
        return slope

    def bc(ya: np.ndarray, yb: np.ndarray) -> np.ndarray:
        return np.array([ya[i] if st.is_hot else yb[i] for i, st in enumerate(streams)])

    if guess is None:
        x0 = np.linspace(0.0, 1.0, _BVP_NODES)
        y0 = np.zeros((n, x0.size))
        for i, st in enumerate(streams):
            distance = x0 if st.is_hot else 1.0 - x0
            y0[i] = 0.5 * (st.H_far_W - st.H_in_W) * distance / scale
    else:
        x0, y0 = guess.x, (guess.H_W - h_in) / scale
    sol = solve_bvp(fun, bc, x0, y0, tol=_BVP_TOL, max_nodes=_BVP_MAX_NODES)
    if sol.status != 0:
        raise RatingConvergenceError(f"common-wall BVP did not converge: {sol.message}")
    h_profile = h_in + scale * sol.y
    t = temperatures(sol.y)
    ha = conductance(sol.x)
    t_w = (ha * t).sum(axis=0) / ha.sum(axis=0)
    h_out = tuple(float(h_profile[i, -1] if st.is_hot else h_profile[i, 0]) for i, st in enumerate(streams))
    return WallSolution(x=sol.x, H_W=h_profile, T_K=t, T_wall_K=t_w, H_out_W=h_out)


def _table(state: StreamState, is_hot: bool, t_far: float, p_out: float, thermo: Thermo) -> WallStream:
    """The T(H) table of a stream, from its inlet to the farthest opposite inlet T."""
    z, flow = dict(state.composition), float(state.molar_flow)
    h_in = float(state.enthalpy)
    h_far = float(thermo.flash_pt(z, t_far, p_out, flow).enthalpy)
    span = h_far - h_in
    edges = np.linspace(h_in - _TABLE_MARGIN * span, h_far + _TABLE_MARGIN * span, _N_TABLE)
    temps = np.array([thermo.flash_ph(z, p_out, float(h), flow).T for h in edges])
    order = np.argsort(edges)
    h_sorted, t_sorted = edges[order] * flow, temps[order]
    interp = PchipInterpolator(h_sorted, np.maximum.accumulate(t_sorted), extrapolate=False)
    low, high = float(h_sorted[0]), float(h_sorted[-1])

    def t_of_h(h: np.ndarray) -> np.ndarray:
        return np.asarray(interp(np.clip(h, low, high)), dtype=float)

    return WallStream(is_hot=is_hot, H_in_W=h_in * flow, H_far_W=h_far * flow, T_of_H=t_of_h)


@dataclass(frozen=True)
class ActiveStreams:
    """The active ports in BVP order, their tables and outlet pressures."""

    ports: tuple[str, ...]
    streams: tuple[WallStream, ...]
    p_out: dict[str, float]


def active_streams(inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> ActiveStreams:
    """Collect the active streams, refuse a bad set-up, and build the T(H) tables."""
    hot = [p for p in HOT_PORTS if inlets[p].molar_flow > 0.0]
    cold = [p for p in COLD_PORTS if inlets[p].molar_flow > 0.0]
    if not hot or not cold:
        raise MultiStreamRatingError("the exchanger needs at least one hot and one cold active stream")
    max_hot = max(inlets[p].T for p in hot)
    min_cold = min(inlets[p].T for p in cold)
    if max_hot <= min_cold:
        raise TemperatureCross(
            f"inlet temperatures leave no driving force: hottest hot {max_hot} K <= coldest cold {min_cold} K"
        )
    p_out: dict[str, float] = {}
    for port in (*hot, *cold):
        drop = float(params.get(f"dP_{port}", 0.0))
        p_out[port] = float(inlets[port].P) - drop
        if p_out[port] <= 0.0:
            raise MultiStreamRatingError(f"dP_{port} gives a non-positive outlet pressure")
    streams = tuple(
        _table(inlets[p], p in HOT_PORTS, min_cold if p in HOT_PORTS else max_hot, p_out[p], thermo)
        for p in (*hot, *cold)
    )
    return ActiveStreams(ports=(*hot, *cold), streams=streams, p_out=p_out)


def outlets_and_info(
    inlets: dict[str, StreamState],
    active: ActiveStreams,
    solution: WallSolution,
    ua_total: float,
    thermo: Thermo,
) -> tuple[dict[str, StreamState], float, dict[str, float]]:
    """Outlet flashes, the round-off duty and the shared info keys; checks the composites."""
    n_hot = sum(s.is_hot for s in active.streams)
    t_hot = solution.T_K[:n_hot]
    t_cold = solution.T_K[n_hot:]
    violation = max(
        float((solution.T_wall_K - t_hot.max(axis=0)).max()),
        float((t_cold.min(axis=0) - solution.T_wall_K).max()),
    )
    if violation > _ORDER_TOL_K:
        raise TemperatureCross(f"the wall temperature left the composites by {violation} K")

    outlets = {_OUT_PORT[p]: inlets[p].model_copy() for p in (*HOT_PORTS, *COLD_PORTS)}
    info: dict[str, float] = {}
    for port, stream, h_out in zip(active.ports, active.streams, solution.H_out_W, strict=True):
        state = inlets[port]
        flow = float(state.molar_flow)
        outlets[_OUT_PORT[port]] = thermo.flash_ph(
            dict(state.composition), active.p_out[port], h_out / flow, flow
        )
        change = h_out - stream.H_in_W
        info[f"duty_{port}_W"] = -change if stream.is_hot else change
    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_all = sum(s.enthalpy * s.molar_flow for s in outlets.values())
    info["min_approach_K"] = float((t_hot.min(axis=0) - t_cold.max(axis=0)).min())
    info["UA_total_W_K"] = ua_total
    info["bvp_nodes"] = float(solution.x.size)
    return outlets, h_all - h_in, info


class MultiStreamR1:
    """Multi-stream exchanger rated on given layer conductances, level R1."""

    inlet_ports = MultiStreamExchanger.inlet_ports
    outlet_ports = MultiStreamExchanger.outlet_ports

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        active = active_streams(inlets, params, thermo)
        ha: list[float] = []
        for port in active.ports:
            key = f"hA_{port}_W_K"
            if key not in params:
                raise MultiStreamRatingError(f"{key} is required for an active stream")
            value = float(params[key])
            if value <= 0.0:
                raise MultiStreamRatingError(f"{key} must be > 0")
            ha.append(value)
        solution = solve_common_wall(active.streams, uniform(ha))
        ha_hot = sum(v for v, s in zip(ha, active.streams, strict=True) if s.is_hot)
        ha_cold = sum(v for v, s in zip(ha, active.streams, strict=True) if not s.is_hot)
        ua = 1.0 / (1.0 / ha_hot + 1.0 / ha_cold)
        outlets, duty, info = outlets_and_info(inlets, active, solution, ua, thermo)
        return UnitResult(outlets=outlets, duty_W=duty, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 streams with illustrative layer conductances (test inputs)."""
        feeds, _ = MultiStreamExchanger.example_case()
        return feeds, {"hA_hot_in_1_W_K": 8.0e5, "hA_cold_in_1_W_K": 8.0e5}
