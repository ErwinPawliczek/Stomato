"""Multi-stream exchanger R2: zoned plate-fin rating with phase change (units/multi_stream.md).

The R1 common-wall BVP with each stream's conductance computed from offset-strip fin
geometry, zone by zone, instead of given.

Geometry per layer (Manglik & Bergles, Exp. Therm. Fluid Sci. 10 (1995) 171):
D_h = 4*s*h_f*l/[2*(s*l + h_f*l + t*h_f) + t*s], alpha = s/h_f, delta = t/l, gamma = t/s,
free-flow area A_ff = s*h_f*n_ch and heat-transfer area A_ht = 2*(s + h_f)*L*n_ch with
n_ch = width/(s + t) (Shah & Sekulic, *Fundamentals of Heat Exchanger Design*, 2003, §8.2).

Single phase, Manglik & Bergles 1995 eq. 34:
j = 0.6522*Re**-0.5403*alpha**-0.1541*delta**0.1499*gamma**-0.0678
    *[1 + 5.269e-5*Re**1.340*alpha**0.504*delta**0.456*gamma**-1.055]**0.1
and h = j*G*cp*Pr**(-2/3).  ``ht`` has no offset-strip correlation, so it is here.

Two phase at the zone-mean quality: ``ht.Shah`` condensing, ``ht.Liu_Winterton`` boiling
with T_e from the wall temperature of that zone.  These are tube correlations applied to
plate-fin channels through D_h, a stated approximation (Shah 1979; Liu & Winterton 1991).

Fin efficiency eta_f = tanh(m*L_f)/(m*L_f), m = sqrt(2*h/(k_f*t)), L_f = h_f/2, for a fin
between two parting sheets of one stream; surface efficiency eta_o = 1 - (A_fin/A_ht)*(1 -
eta_f), A_fin/A_ht = h_f/(s + h_f) (Shah & Sekulic §4.3).

Zone loop: R1 from inlet-state conductances, cut the hot composite into equal-duty zones,
recompute every stream's h at the zone-mean state, re-solve with hA constant on each zone
(a multipoint BVP, see :func:`solve_zoned_wall`), and repeat until the outlet temperatures
settle.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import ht
import numpy as np
from scipy.integrate import solve_bvp

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.multi_stream_r1 import (
    _BVP_MAX_NODES,
    _BVP_TOL,
    ActiveStreams,
    MultiStreamRatingError,
    WallSolution,
    WallStream,
    active_streams,
    outlets_and_info,
    solve_common_wall,
    uniform,
)
from ngdesign.units.heat.rating import RatingConvergenceError, film_props
from ngdesign.units.heat.shell_tube_r2 import _mass_quality, _phase

_MAX_ZONE_ITER = 30
_ZONE_NODES = 11
_ZONE_TOL_K = 1.0e-6

#: Smallest T_e handed to the boiling correlation, K.
_MIN_TE_K = 1.0e-3


def plate_fin_dh(s: float, h_f: float, t: float, l: float) -> float:  # noqa: E741
    """Hydraulic diameter of an offset-strip fin channel (Manglik & Bergles 1995)."""
    return 4.0 * s * h_f * l / (2.0 * (s * l + h_f * l + t * h_f) + t * s)


def manglik_bergles_j(Re: float, alpha: float, delta: float, gamma: float) -> float:
    """Colburn j of an offset-strip fin (Manglik & Bergles 1995, eq. 34)."""
    first = 0.6522 * Re**-0.5403 * alpha**-0.1541 * delta**0.1499 * gamma**-0.0678
    second = 1.0 + 5.269e-5 * Re**1.340 * alpha**0.504 * delta**0.456 * gamma**-1.055
    return float(first * second**0.1)


def fin_efficiency(h: float, k_fin: float, t: float, h_f: float) -> float:
    """tanh(m*L)/(m*L) for a fin between two parting sheets of one stream."""
    ml = math.sqrt(2.0 * h / (k_fin * t)) * h_f / 2.0
    return math.tanh(ml) / ml


def surface_efficiency(eta_f: float, s: float, h_f: float) -> float:
    """eta_o = 1 - (A_fin/A_ht)*(1 - eta_f), with A_fin/A_ht = h_f/(s + h_f)."""
    return 1.0 - h_f / (s + h_f) * (1.0 - eta_f)


@dataclass(frozen=True)
class Layers:
    """One stream's plate-fin layers."""

    n_layers: int
    fin_height_m: float
    fin_spacing_m: float
    fin_thickness_m: float
    strip_length_m: float
    width_m: float
    length_m: float
    k_fin: float

    @property
    def n_channels(self) -> float:
        return self.width_m / (self.fin_spacing_m + self.fin_thickness_m)

    @property
    def d_h(self) -> float:
        return plate_fin_dh(self.fin_spacing_m, self.fin_height_m, self.fin_thickness_m, self.strip_length_m)

    @property
    def free_flow_m2(self) -> float:
        return self.n_layers * self.fin_spacing_m * self.fin_height_m * self.n_channels

    @property
    def area_m2(self) -> float:
        return (
            self.n_layers * 2.0 * (self.fin_spacing_m + self.fin_height_m) * self.length_m * self.n_channels
        )


def _film_h(layers: Layers, film: Any, mass_flow: float) -> float:
    """Single-phase h on the fin surface."""
    g = mass_flow / layers.free_flow_m2
    re = g * layers.d_h / film.mu_Pa_s
    j = manglik_bergles_j(
        re,
        layers.fin_spacing_m / layers.fin_height_m,
        layers.fin_thickness_m / layers.strip_length_m,
        layers.fin_thickness_m / layers.fin_spacing_m,
    )
    return float(j * g * film.cp_J_kgK * film.Pr ** (-2.0 / 3.0))


def stream_h(
    layers: Layers, state: StreamState, is_hot: bool, t_wall: float, thermo: Thermo, mass_flow: float
) -> float:
    """h of one stream at a zone-mean state: single phase, or Shah/Liu-Winterton."""
    if len(state.phases) == 1:
        phase = state.phases[0]
        return _film_h(
            layers, film_props(thermo, dict(phase.composition), state.T, state.P, phase.kind), mass_flow
        )
    liquid = _phase(state, False)
    vapour = _phase(state, True)
    film = film_props(thermo, dict(liquid.composition), state.T, state.P, liquid.kind)
    db = components()
    pc = math.fsum(x * float(db[cid]["pc_Pa"]) for cid, x in state.composition.items())
    per_channel = mass_flow / (layers.n_layers * layers.n_channels)
    x = _mass_quality(state)
    if is_hot:
        return float(
            ht.Shah(
                per_channel,
                x,
                layers.d_h,
                film.rho_kg_m3,
                film.mu_Pa_s,
                film.k_W_mK,
                film.cp_J_kgK,
                state.P,
                pc,
            )
        )
    return float(
        ht.Liu_Winterton(
            per_channel,
            x,
            layers.d_h,
            film.rho_kg_m3,
            vapour.density,
            film.mu_Pa_s,
            film.k_W_mK,
            film.cp_J_kgK,
            liquid.molecular_weight,
            state.P,
            pc,
            max(t_wall - state.T, _MIN_TE_K),
        )
    )


def conductance_density(layers: Layers, h: float) -> float:
    """h*eta_o*A_ht, the stream's hA per unit normalised length, W/K."""
    eta_f = fin_efficiency(h, layers.k_fin, layers.fin_thickness_m, layers.fin_height_m)
    return h * surface_efficiency(eta_f, layers.fin_spacing_m, layers.fin_height_m) * layers.area_m2


def _positive(params: dict[str, Any], key: str) -> float:
    if key not in params:
        raise MultiStreamRatingError(f"{key} is required for an active stream")
    value = float(params[key])
    if value <= 0.0:
        raise MultiStreamRatingError(f"{key} must be > 0")
    return value


def _layers(params: dict[str, Any], port: str) -> Layers:
    return Layers(
        n_layers=int(_positive(params, f"n_layers_{port}")),
        fin_height_m=_positive(params, f"fin_height_{port}_m"),
        fin_spacing_m=_positive(params, f"fin_spacing_{port}_m"),
        fin_thickness_m=_positive(params, f"fin_thickness_{port}_m"),
        strip_length_m=_positive(params, f"strip_length_{port}_m"),
        width_m=_positive(params, "layer_width_m"),
        length_m=_positive(params, "length_m"),
        k_fin=float(params.get("k_fin_W_mK", 180.0)),
    )


def solve_zoned_wall(
    streams: Sequence[WallStream], edges: np.ndarray, zones: np.ndarray, guess: WallSolution
) -> WallSolution:
    """The common-wall BVP with hA constant on each zone.

    A jump in hA is a jump in f, which no collocation mesh resolves, so each zone is its
    own interval on s in [0, 1] and the zones meet through continuity conditions: a
    multipoint BVP of n*N_z states.  theta is scaled as in the R1 solver.
    """
    n, n_zones = len(streams), zones.shape[1]
    widths = np.diff(edges)
    sign = np.array([-1.0 if st.is_hot else 1.0 for st in streams]).reshape(-1, 1)
    h_in = np.array([st.H_in_W for st in streams]).reshape(-1, 1)
    scale = max(abs(st.H_far_W - st.H_in_W) for st in streams)

    def temperatures(theta: np.ndarray) -> np.ndarray:
        h = h_in + scale * theta
        return np.vstack([st.T_of_H(h[i]) for i, st in enumerate(streams)])

    def wall(t: np.ndarray, ha: np.ndarray) -> np.ndarray:
        result: np.ndarray = (ha * t).sum(axis=0) / ha.sum()
        return result

    def fun(_s: np.ndarray, y: np.ndarray) -> np.ndarray:
        out = np.zeros_like(y)
        for k in range(n_zones):
            block = slice(n * k, n * (k + 1))
            t = temperatures(y[block])
            ha = zones[:, k : k + 1]
            out[block] = widths[k] * sign * ha * (t - wall(t, ha)) / scale
        return out

    def bc(ya: np.ndarray, yb: np.ndarray) -> np.ndarray:
        residual = [ya[i] if st.is_hot else yb[n * (n_zones - 1) + i] for i, st in enumerate(streams)]
        for k in range(n_zones - 1):
            residual.extend(ya[n * (k + 1) + i] - yb[n * k + i] for i in range(n))
        return np.array(residual)

    mesh = np.linspace(0.0, 1.0, _ZONE_NODES)
    y0 = np.zeros((n * n_zones, mesh.size))
    for k in range(n_zones):
        x = edges[k] + widths[k] * mesh
        for i in range(n):
            y0[n * k + i] = (np.interp(x, guess.x, guess.H_W[i]) - h_in[i, 0]) / scale
    sol = solve_bvp(fun, bc, mesh, y0, tol=_BVP_TOL, max_nodes=_BVP_MAX_NODES)
    if sol.status != 0:
        raise RatingConvergenceError(f"zoned common-wall BVP did not converge: {sol.message}")

    x_all = np.concatenate([edges[k] + widths[k] * sol.x for k in range(n_zones)])
    theta = np.hstack([sol.y[n * k : n * (k + 1)] for k in range(n_zones)])
    t_all = temperatures(theta)
    wall_all = np.concatenate(
        [wall(temperatures(sol.y[n * k : n * (k + 1)]), zones[:, k : k + 1]) for k in range(n_zones)]
    )
    h_all = h_in + scale * theta
    h_out = tuple(float(h_all[i, -1] if st.is_hot else h_all[i, 0]) for i, st in enumerate(streams))
    return WallSolution(x=x_all, H_W=h_all, T_K=t_all, T_wall_K=wall_all, H_out_W=h_out)


def zone_edges(solution: WallSolution, n_hot: int, n_zones: int) -> np.ndarray:
    """x at equal shares of the hot composite's duty."""
    released = solution.H_W[:n_hot, 0].sum() - solution.H_W[:n_hot].sum(axis=0)
    released = np.maximum.accumulate(released)
    targets = np.linspace(0.0, float(released[-1]), n_zones + 1)
    edges: np.ndarray = np.interp(targets, released, solution.x)
    edges[0], edges[-1] = 0.0, 1.0
    return edges


class MultiStreamR2:
    """Multi-stream plate-fin exchanger rated zone by zone, level R2."""

    inlet_ports = MultiStreamExchanger.inlet_ports
    outlet_ports = MultiStreamExchanger.outlet_ports

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        active = active_streams(inlets, params, thermo)
        layers = [_layers(params, port) for port in active.ports]
        n_zones = int(params.get("n_zones", 20))
        if n_zones < 1:
            raise MultiStreamRatingError(f"n_zones {n_zones} must be >= 1")
        solution, zones_ha, edges, zone_h, iterations = self._zone_loop(
            inlets, active, layers, n_zones, thermo
        )
        n_hot = sum(s.is_hot for s in active.streams)
        widths = np.diff(edges)
        ua = float(
            sum(
                dx / (1.0 / zones_ha[:n_hot, k].sum() + 1.0 / zones_ha[n_hot:, k].sum())
                for k, dx in enumerate(widths)
            )
        )
        outlets, duty, info = outlets_and_info(inlets, active, solution, ua, thermo)
        info["n_zones"] = float(n_zones)
        info["zone_iterations"] = float(iterations)
        for i, port in enumerate(active.ports):
            info[f"h_{port}_min_W_m2K"] = float(zone_h[i].min())
            info[f"h_{port}_max_W_m2K"] = float(zone_h[i].max())
            info[f"hA_{port}_W_K"] = float((zones_ha[i] * widths).sum())
        return UnitResult(outlets=outlets, duty_W=duty, power_W=0.0, info=info)

    @staticmethod
    def _zone_loop(
        inlets: dict[str, StreamState],
        active: ActiveStreams,
        layers: Sequence[Layers],
        n_zones: int,
        thermo: Thermo,
    ) -> tuple[WallSolution, np.ndarray, np.ndarray, np.ndarray, int]:
        n_hot = sum(s.is_hot for s in active.streams)
        flows = [float(inlets[p].molar_flow) for p in active.ports]
        masses = [float(inlets[p].mass_flow) for p in active.ports]
        hot_in = max(inlets[p].T for p in active.ports[:n_hot])
        cold_in = min(inlets[p].T for p in active.ports[n_hot:])
        start = [
            conductance_density(lay, stream_h(lay, inlets[p], s.is_hot, 0.5 * (hot_in + cold_in), thermo, m))
            for lay, p, s, m in zip(layers, active.ports, active.streams, masses, strict=True)
        ]
        solution = solve_common_wall(active.streams, uniform(start))
        previous = np.array(solution.H_out_W)
        for iteration in range(1, _MAX_ZONE_ITER + 1):
            edges = zone_edges(solution, n_hot, n_zones)
            mids = 0.5 * (edges[:-1] + edges[1:])
            walls = np.interp(mids, solution.x, solution.T_wall_K)
            zone_h = np.zeros((len(flows), n_zones))
            zones_ha = np.zeros((len(flows), n_zones))
            for i, port in enumerate(active.ports):
                inlet = inlets[port]
                pressure = 0.5 * (float(inlet.P) + active.p_out[port])
                means = np.interp(mids, solution.x, solution.H_W[i]) / flows[i]
                for k, h_mean in enumerate(means):
                    state = thermo.flash_ph(dict(inlet.composition), pressure, float(h_mean), flows[i])
                    h = stream_h(
                        layers[i], state, active.streams[i].is_hot, float(walls[k]), thermo, masses[i]
                    )
                    zone_h[i, k] = h
                    zones_ha[i, k] = conductance_density(layers[i], h)
            solution = solve_zoned_wall(active.streams, edges, zones_ha, solution)
            current = np.array(solution.H_out_W)
            shifts = [
                abs(float(s.T_of_H(np.array([a]))[0]) - float(s.T_of_H(np.array([b]))[0]))
                for s, a, b in zip(active.streams, current, previous, strict=True)
            ]
            previous = current
            if max(shifts) < _ZONE_TOL_K:
                return solution, zones_ha, edges, zone_h, iteration
        raise RatingConvergenceError(f"zone loop did not converge in {_MAX_ZONE_ITER} iterations")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 nitrogen streams on an illustrative core (test inputs, not defaults)."""
        feeds, _ = MultiStreamExchanger.example_case()
        params: dict[str, Any] = {"layer_width_m": 1.2, "length_m": 6.0, "n_zones": 6}
        for port in ("hot_in_1", "cold_in_1"):
            params.update(
                {
                    f"n_layers_{port}": 400,
                    f"fin_height_{port}_m": 6.35e-3,
                    f"fin_spacing_{port}_m": 1.5e-3,
                    f"fin_thickness_{port}_m": 1.5e-4,
                    f"strip_length_{port}_m": 3.175e-3,
                }
            )
        return feeds, params
