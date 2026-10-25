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

import numpy as np
from scipy.integrate import solve_bvp
from scipy.interpolate import PchipInterpolator

from ngdesign.units._physics.heat_balance import TemperatureCross

#: BVP relative tolerance (spec algorithm step 2).
BVP_TOL = 1e-8

#: BVP node cap (spec algorithm step 2).
BVP_MAX_NODES = 20000

#: Initial mesh size (spec algorithm step 2).
BVP_INITIAL_NODES = 41

#: Allowed wall-ordering violation, K (spec algorithm step 4).
WALL_ORDER_EPS_K = 1e-9


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


def solve_common_wall(
    layers: tuple[StreamLayer, ...],
    *,
    tol: float = BVP_TOL,
    max_nodes: int = BVP_MAX_NODES,
    n_mesh: int = BVP_INITIAL_NODES,
) -> CommonWallResult:
    """Solve the common-wall BVP for the stream enthalpy flows H_i(x).

    Pure: tables in (the ``T_of_H`` interpolants of ``layers``), outlet H out
    (:meth:`CommonWallResult.outlet_enthalpy_flows`). Hot streams enter at
    x = 0, cold at x = 1. Raises :class:`RatingConvergenceError` when
    ``solve_bvp`` reports ``status != 0``.
    """
    if not layers:
        raise MultiStreamRatingError("at least one hot and one cold active stream are required")
    hA = np.array([layer.hA_W_K for layer in layers])
    signs = np.array([-1.0 if layer.is_hot else 1.0 for layer in layers])

    def rhs(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        temperatures = np.vstack([layer.T_of_H(y[i]) for i, layer in enumerate(layers)])
        wall = hA @ temperatures / hA.sum()
        return (signs * hA)[:, None] * (temperatures - wall[None, :])

    def bc(ya: np.ndarray, yb: np.ndarray) -> np.ndarray:
        residuals = []
        for i, layer in enumerate(layers):
            edge_value = ya[i] if layer.is_hot else yb[i]
            residuals.append(edge_value - layer.H_in_W)
        return np.array(residuals)

    x_init = np.linspace(0.0, 1.0, n_mesh)
    solution = solve_bvp(rhs, bc, x_init, _initial_guess(layers, x_init), tol=tol, max_nodes=max_nodes)
    if solution.status != 0:
        raise RatingConvergenceError(f"common-wall BVP did not converge: {solution.message}")

    temperatures = np.vstack([layer.T_of_H(solution.y[i]) for i, layer in enumerate(layers)])
    wall = hA @ temperatures / hA.sum()
    return CommonWallResult(
        x=solution.x,
        H=solution.y,
        T=temperatures,
        T_wall=wall,
        hA_W_K=tuple(layer.hA_W_K for layer in layers),
        is_hot=tuple(layer.is_hot for layer in layers),
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
    hA = np.asarray(result.hA_W_K)
    hot = np.asarray(result.is_hot)
    hA_hot = float(hA[hot].sum())
    hA_cold = float(hA[~hot].sum())
    hA_all = float(hA.sum())
    # Mesh sum of the (uniform) per-node conductance: the trapezoidal integral
    # over the normalised mesh equals the constant node value.
    node_value = hA_hot * hA_cold / hA_all
    return float(np.trapezoid(np.full(result.x.size, node_value), result.x))
