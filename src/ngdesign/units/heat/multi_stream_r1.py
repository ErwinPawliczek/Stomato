"""Multi-stream R1: the common-wall layer model with given hA per stream.

Spec ``specs/backend/units/multi_stream.md`` (R1). Each active stream i carries
a given layer conductance ``(hA)_i`` in W/K, distributed uniformly along the
normalised exchanger length x in [0, 1]. Hot streams enter at x = 0 and flow in
+x; cold streams enter at x = 1 and flow in -x. Lateral wall conduction is
perfect and the wall holds no net heat, so all streams share one wall
temperature (Haseler 1983, "Performance calculation methods for multi-stream
plate-fin heat exchangers", in *Heat Exchangers: Theory and Practice*,
Hemisphere; Paffenholz 1984):

    T_w(x) = sum_i (hA)_i * T_i(x) / sum_i (hA)_i

Stream energy balances in the enthalpy-flow state H_i (W) = F_i * h_i(T_i):

    hot:  dH_i/dx = -(hA)_i * (T_i - T_w)      (flows in +x, releases)
    cold: dH_i/dx = +(hA)_i * (T_i - T_w)      (flows in -x, absorbs)

with boundary conditions H_hot(0) = F * h_in,hot and H_cold(1) = F * h_in,cold.
The pure core :func:`solve_common_wall` takes per-stream monotone T(H) tables
(:class:`~scipy.interpolate.PchipInterpolator`, which handles phase-change
plateaus), solves the boundary-value problem with
:func:`scipy.integrate.solve_bvp`, and returns outlet enthalpy flows. With
constant heat-capacity rates the model reduces exactly to counter-current
epsilon-NTU with 1/UA = 1/(hA)_h + 1/(hA)_c (verified in the tests).

:class:`RatingConvergenceError` is defined here privately (U-R2: private
helpers are consolidated by the orchestrator later); the R2 spec expects the
same error from ``ngdesign.units.heat.rating`` once double_pipe merges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.integrate import solve_bvp
from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream import MultiStreamExchanger

#: BVP relative tolerance (spec algorithm step 2).
BVP_TOL = 1e-8

#: BVP node cap (spec algorithm step 2).
BVP_MAX_NODES = 20000

#: Initial mesh size (spec algorithm step 2).
BVP_INITIAL_NODES = 41

#: Allowed wall-ordering violation, K (spec algorithm step 4).
WALL_ORDER_EPS_K = 1e-9

#: T(H) table sample count per stream (spec: 40 flash_ph samples).
TABLE_POINTS = 40

_HOT_PORTS = ("hot_in_1", "hot_in_2")
_COLD_PORTS = ("cold_in_1", "cold_in_2")

#: Inlet port -> positional outlet port (R0 convention: NOT mirrored names).
_OUTLET_OF: dict[str, str] = {
    "hot_in_1": "hot_out_1",
    "hot_in_2": "hot_out_2",
    "cold_in_1": "cold_out_1",
    "cold_in_2": "cold_out_2",
}


class MultiStreamRatingError(ValueError):
    """A multi-stream rating spec that cannot be solved (R1/R2)."""


class RatingConvergenceError(ValueError):
    """A rating iteration (BVP or zone loop) did not converge."""


@dataclass(frozen=True)
class StreamLayer:
    """One active stream handed to the common-wall BVP (pure; tables in).

    ``T_of_H`` maps enthalpy flow H (W) to temperature (K); it must be monotone
    over the stream's reachable span. ``H_far_W`` is the enthalpy flow at the
    farthest opposite-stream inlet temperature - the far end of the T(H) table.
    """

    hA_W_K: float
    H_in_W: float
    H_far_W: float
    T_of_H: PchipInterpolator
    is_hot: bool


@dataclass(frozen=True)
class CommonWallResult:
    """Common-wall BVP solution on its mesh (pure; outlet H out)."""

    x: np.ndarray  # (m,) normalised mesh, 0..1
    H: np.ndarray  # (n, m) enthalpy flows, W
    T: np.ndarray  # (n, m) stream temperatures, K
    T_wall: np.ndarray  # (m,) wall temperature, K
    hA_W_K: tuple[float, ...]
    is_hot: tuple[bool, ...]
    #: Per-stream conductance evaluated at every mesh node, W/K (piecewise
    #: hA in the R2 zone model; None for the uniform-hA R1 solve).
    hA_nodes: np.ndarray | None = None

    def outlet_enthalpy_flows(self) -> tuple[float, ...]:
        """H at each stream's OUTLET end: hot at x = 1, cold at x = 0."""
        return tuple(float(self.H[i][-1] if is_hot else self.H[i][0]) for i, is_hot in enumerate(self.is_hot))


def _initial_guess(layers: tuple[StreamLayer, ...], x: np.ndarray) -> np.ndarray:
    """Linear H profile from each stream's inlet end toward its far end."""
    y0 = np.empty((len(layers), x.size))
    for i, layer in enumerate(layers):
        weight = x if layer.is_hot else 1.0 - x
        y0[i] = layer.H_in_W + (layer.H_far_W - layer.H_in_W) * weight
    return y0


def build_T_of_H_table(
    state: StreamState, T_far: float, thermo: Thermo
) -> tuple[PchipInterpolator, float, float]:
    """Build one stream's monotone T(H) table (spec algorithm step 2).

    40 ``flash_ph`` samples from the inlet enthalpy flow to the enthalpy flow
    at ``T_far`` (the farthest opposite-stream inlet temperature), at the
    inlet pressure. Returns ``(T_of_H, H_in_W, H_far_W)``.
    """
    H_in = state.molar_flow * state.enthalpy
    H_far = state.molar_flow * thermo.flash_pt(state.composition, T_far, state.P, state.molar_flow).enthalpy
    span = H_far - H_in
    floor = 1e-6 * max(abs(H_in), 1.0)
    if abs(span) < floor:  # keep the table strictly increasing for PCHIP
        H_far = H_in + (floor if span >= 0.0 else -floor)
    lo, hi = (H_in, H_far) if H_in <= H_far else (H_far, H_in)
    flows = np.linspace(lo, hi, TABLE_POINTS)
    temperatures = [
        thermo.flash_ph(state.composition, state.P, float(H) / state.molar_flow, state.molar_flow).T
        for H in flows
    ]
    return PchipInterpolator(flows, np.asarray(temperatures)), H_in, H_far


def solve_common_wall(
    layers: tuple[StreamLayer, ...],
    *,
    tol: float = BVP_TOL,
    max_nodes: int = BVP_MAX_NODES,
    n_mesh: int = BVP_INITIAL_NODES,
    hA_zones: np.ndarray | None = None,
    y_init: np.ndarray | None = None,
) -> CommonWallResult:
    """Solve the common-wall BVP for the stream enthalpy flows H_i(x).

    Pure: tables in (the ``T_of_H`` interpolants of ``layers``), outlet H out
    (:meth:`CommonWallResult.outlet_enthalpy_flows`). Hot streams enter at
    x = 0, cold at x = 1. Raises :class:`RatingConvergenceError` when
    ``solve_bvp`` reports ``status != 0``.

    ``hA_zones`` (R2): per-stream per-zone conductance, shape (n_streams,
    n_zones), W/K per unit normalised length - piecewise-constant on equal
    zones of x. ``y_init`` (R2 zone loop): warm-start profile from the
    previous iteration.
    """
    if not layers:
        raise MultiStreamRatingError("at least one hot and one cold active stream are required")
    hA = np.array([layer.hA_W_K for layer in layers])
    signs = np.array([-1.0 if layer.is_hot else 1.0 for layer in layers])
    n_zones = 1 if hA_zones is None else int(hA_zones.shape[1])

    def conductance_at(x: np.ndarray) -> np.ndarray:
        """Per-stream conductance at mesh x, shape (n_streams, x.size), W/K."""
        if hA_zones is None:
            return np.tile(hA[:, None], (1, x.size))
        zone_index = np.clip((x * n_zones).astype(int), 0, n_zones - 1)
        return hA_zones[:, zone_index]

    def rhs(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        temperatures = np.vstack([layer.T_of_H(y[i]) for i, layer in enumerate(layers)])
        conductance = conductance_at(x)
        wall = conductance @ temperatures / conductance.sum(axis=0)
        return np.asarray((signs[:, None] * conductance) * (temperatures - wall[None, :]), dtype=float)

    def bc(ya: np.ndarray, yb: np.ndarray) -> np.ndarray:
        residuals = []
        for i, layer in enumerate(layers):
            edge_value = ya[i] if layer.is_hot else yb[i]
            residuals.append(edge_value - layer.H_in_W)
        return np.array(residuals)

    x_init = np.linspace(0.0, 1.0, n_mesh) if hA_zones is None else np.linspace(0.0, 1.0, 2 * n_zones + 1)
    guess = _initial_guess(layers, x_init) if y_init is None else y_init
    solution = solve_bvp(rhs, bc, x_init, guess, tol=tol, max_nodes=max_nodes)
    if solution.status != 0:
        raise RatingConvergenceError(f"common-wall BVP did not converge: {solution.message}")

    temperatures = np.vstack([layer.T_of_H(solution.y[i]) for i, layer in enumerate(layers)])
    conductance_nodes = conductance_at(solution.x)
    wall = conductance_nodes @ temperatures / conductance_nodes.sum(axis=0)
    return CommonWallResult(
        x=solution.x,
        H=solution.y,
        T=temperatures,
        T_wall=wall,
        hA_W_K=tuple(layer.hA_W_K for layer in layers),
        is_hot=tuple(layer.is_hot for layer in layers),
        hA_nodes=conductance_nodes,
    )


def check_wall_order(result: CommonWallResult) -> None:
    """Refuse a solution where any hot stream dips below the wall or any cold
    stream rises above it (spec algorithm step 4, within -1e-9 K).

    This cannot happen physically - the wall is a weighted average of the
    stream temperatures - so a violation signals a table or solver defect.
    Raises :class:`~ngdesign.units._physics.heat_balance.TemperatureCross`
    naming the mesh position and the offending temperatures.
    """
    for i, is_hot in enumerate(result.is_hot):
        gap = result.T[i] - result.T_wall if is_hot else result.T_wall - result.T[i]
        k = int(np.argmin(gap))
        if gap[k] < -WALL_ORDER_EPS_K:
            kind = "hot" if is_hot else "cold"
            raise TemperatureCross(
                f"stream temperature ordering violated at x = {result.x[k]:.6f}: "
                f"{kind} stream T = {result.T[i][k]:.6f} K against wall "
                f"T_w = {result.T_wall[k]:.6f} K (gap {gap[k]:.3e} K); "
                "a table or solver defect"
            )


def min_approach_K(result: CommonWallResult) -> float:
    """Minimum hot-cold approach over the solution mesh, K (spec step 5).

    min over mesh nodes k of (min hot T at k - max cold T at k); with a single
    hot and a single cold stream this is the plain counter-current approach.
    """
    hot_mask = np.array(result.is_hot)
    cold_hot_min = result.T[hot_mask].min(axis=0) - result.T[~hot_mask].max(axis=0)
    return float(cold_hot_min.min())


def wall_mediated_UA_W_K(result: CommonWallResult) -> float:
    """Total wall-mediated conductance, W/K (spec step 6: summed over the mesh).

    At each node the hot composite sees the wall through sum(hA_hot) and the
    cold composite through sum(hA_cold); the wall-mediated conductance of the
    node is the series combination, and the mesh integral of that per-length
    conductance over the uniform layers is

        UA = sum(hA_hot) * sum(hA_cold) / sum(hA_all)

    which for two streams is exactly 1/(1/(hA)_h + 1/(hA)_c).
    """
    hA = (
        np.asarray(result.hA_nodes)
        if result.hA_nodes is not None
        else np.tile(np.asarray(result.hA_W_K)[:, None], (1, result.x.size))
    )
    hot = np.asarray(result.is_hot)
    node_value = hA[hot].sum(axis=0) * hA[~hot].sum(axis=0) / hA.sum(axis=0)
    return float(np.trapezoid(node_value, result.x))


class MultiStreamR1:
    """R1 multi-stream rating: the common-wall layer model with given hA.

    Plugin kind "unit", name "multi_stream", catalogue level R1. Same ports and
    zero-flow pass-through as R0 (:class:`ngdesign.units.heat.multi_stream.
    MultiStreamExchanger`), but no T_out specs: every active stream carries
    ``hA_<port>_W_K`` and the coupled energy balances decide all outlets. Hot
    streams enter at x = 0, cold at x = 1; dH/dx signs follow the flow
    direction (hot releases, cold absorbs - both positive as R0 duties).
    """

    inlet_ports = ("hot_in_1", "hot_in_2", "cold_in_1", "cold_in_2")
    outlet_ports = ("hot_out_1", "hot_out_2", "cold_out_1", "cold_out_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        hot_active = [(p, inlets[p]) for p in _HOT_PORTS if inlets[p].molar_flow > 0.0]
        cold_active = [(p, inlets[p]) for p in _COLD_PORTS if inlets[p].molar_flow > 0.0]
        if not hot_active or not cold_active:
            raise MultiStreamRatingError("at least one hot and one cold active stream are required")
        hot_T_max = max(state.T for _, state in hot_active)
        cold_T_min = min(state.T for _, state in cold_active)
        hottest_cold = max(state.T for _, state in cold_active)
        coldest_hot = min(state.T for _, state in hot_active)
        if hottest_cold >= coldest_hot:
            raise TemperatureCross(
                f"inlet temperatures give no positive driving force anywhere: "
                f"hottest cold inlet {hottest_cold:.6f} K >= coldest hot inlet "
                f"{coldest_hot:.6f} K"
            )

        active: list[tuple[str, StreamState, bool]] = [(port, state, True) for port, state in hot_active] + [
            (port, state, False) for port, state in cold_active
        ]

        layers = tuple(
            self._layer(port, state, hot_T_max, cold_T_min, params, thermo) for port, state, _ in active
        )
        result = solve_common_wall(layers)
        check_wall_order(result)
        H_out = result.outlet_enthalpy_flows()

        outlets: dict[str, StreamState] = {}
        duty_by_port: dict[str, float] = {}
        for i, (port, state, is_hot) in enumerate(active):
            raw_dP = params.get(f"dP_{port}", 0.0)
            p_out = state.P - float(raw_dP)
            if p_out <= 0.0:
                raise MultiStreamRatingError(
                    f"port {port}: dP_{port} = {raw_dP} Pa gives a non-positive outlet pressure {p_out} Pa"
                )
            outlet = thermo.flash_ph(state.composition, p_out, H_out[i] / state.molar_flow, state.molar_flow)
            outlets[_OUTLET_OF[port]] = outlet
            duty_by_port[port] = state.molar_flow * (
                (state.enthalpy - outlet.enthalpy) if is_hot else (outlet.enthalpy - state.enthalpy)
            )
        for port in (*_HOT_PORTS, *_COLD_PORTS):  # zero-flow ports pass through
            if inlets[port].molar_flow <= 0.0:
                outlets[_OUTLET_OF[port]] = inlets[port]

        info: dict[str, Any] = {
            "min_approach_K": min_approach_K(result),
            "UA_total_W_K": wall_mediated_UA_W_K(result),
            "bvp_nodes": int(result.x.size),
        }
        for port in (*_HOT_PORTS, *_COLD_PORTS):
            if port in duty_by_port:  # R0 signs: released/absorbed, both positive
                info[f"duty_{port}_W"] = duty_by_port[port]

        h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(outlets=outlets, duty_W=h_out - h_in, power_W=0.0, info=info)

    def _layer(
        self,
        port: str,
        state: StreamState,
        hot_T_max: float,
        cold_T_min: float,
        params: dict[str, Any],
        thermo: Thermo,
    ) -> StreamLayer:
        """Build one stream's T(H) table and layer (spec algorithm steps 1-2)."""
        key = f"hA_{port}_W_K"
        raw = params.get(key)
        if raw is None:
            raise MultiStreamRatingError(f"active stream {port}: required param {key} is missing")
        hA_value = float(raw)
        if hA_value <= 0.0:
            raise MultiStreamRatingError(f"param {key} must be positive; got {hA_value}")
        is_hot = port in _HOT_PORTS
        # Farthest opposite-stream inlet temperature sets the T(H) table span.
        T_far = cold_T_min if is_hot else hot_T_max
        T_of_H, H_in, H_far = build_T_of_H_table(state, T_far, thermo)
        return StreamLayer(
            hA_W_K=hA_value,
            H_in_W=H_in,
            H_far_W=H_far,
            T_of_H=T_of_H,
            is_hot=is_hot,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feeds (Smith Table 16.2 streams 1 and 3 basis) plus
        layer conductances for the two active streams; the second pair is
        zero-flow and passes through."""
        feeds, _ = MultiStreamExchanger.example_case()
        return feeds, {"hA_hot_in_1_W_K": 60000.0, "hA_cold_in_1_W_K": 60000.0}
