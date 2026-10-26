"""Multi-stream R2: plate-fin geometry and correlations (spec step 3 pure functions).

Spec ``specs/backend/units/multi_stream.md`` (R2). Each active stream gets an
offset-strip-fin layer geometry instead of a given ``hA``; this module holds
the per-layer geometry and the correlations as pure functions, with no state
and no thermodynamics:

- **Per-layer geometry** (Manglik & Bergles 1995, Exp. Therm. Fluid Sci.
  10:171): hydraulic diameter, the dimensionless fin parameters
  (alpha = s/h_f, delta = t/l, gamma = t/s), the free-flow area per layer and
  the heat-transfer area per layer (fin plus parting sheet; Shah & Sekulic,
  *Fundamentals of Heat Exchanger Design*, 2003, section 8.2).
- **Single-phase surface performance**: the Manglik & Bergles (1995) Colburn
  ``j`` and Fanning ``f`` correlations (their equation 34 pair), valid over
  the fitted range 120 < Re < 10^4 without extrapolation checks here (the
  adapter owns refusal policy). ``h = j*G*cp*Pr^(-2/3)``.
- **Fin efficiency**: ``eta_f = tanh(m L_f)/(m L_f)`` with
  ``m = sqrt(2 h/(k_fin t))`` and ``L_f = h_f/2`` for a fin between two
  parting sheets of the same stream; surface efficiency
  ``eta_o = 1 - (A_fin/A_ht)(1 - eta_f)`` with ``A_fin/A_ht = h_f/(s + h_f)``
  (Shah & Sekulic section 4.3).

The R2 adapter (:class:`MultiStreamR2`, spec step 4) applies the tube-side
condensation (``ht.Shah``) and boiling (``ht.Liu_Winterton``) correlations to
plate-fin channels through the hydraulic diameter - a stated approximation
(Shah 1979; Liu & Winterton 1991) documented there.

U-R2: private helpers live in the owning unit module and are consolidated by
the orchestrator later.
"""

from __future__ import annotations

import inspect
import math
from dataclasses import dataclass
from typing import Any

import ht
import numpy as np

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.multi_stream_r1 import (
    _COLD_PORTS,
    _HOT_PORTS,
    _OUTLET_OF,
    CommonWallResult,
    MultiStreamRatingError,
    RatingConvergenceError,
    StreamLayer,
    build_T_of_H_table,
    check_wall_order,
    min_approach_K,
    solve_common_wall,
    wall_mediated_UA_W_K,
)
from ngdesign.units.heat.rating import FilmProps, film_props, inlet_kind

#: Aluminium alloy fin thermal conductivity default, W/(m K) (spec params).
K_FIN_DEFAULT_W_MK = 180.0

#: Default zone count for the R2 zone loop (spec algorithm step 5).
N_ZONES_DEFAULT = 20

#: Zone-loop outer iteration cap (spec algorithm step 5e).
ZONE_MAX_ITERATIONS = 30

#: Zone-loop outlet-temperature convergence, K (spec algorithm step 5e).
ZONE_TOL_K = 1e-6


@dataclass(frozen=True)
class FinGeometry:
    """One stream's offset-strip-fin layer geometry (pure; spec R2 params)."""

    fin_height_m: float
    fin_spacing_m: float
    fin_thickness_m: float
    strip_length_m: float

    @property
    def alpha(self) -> float:
        """``s/h_f`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_spacing_m / self.fin_height_m

    @property
    def delta(self) -> float:
        """``t/l`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_thickness_m / self.strip_length_m

    @property
    def gamma(self) -> float:
        """``t/s`` (Manglik & Bergles 1995; spec R2 equation 1)."""
        return self.fin_thickness_m / self.fin_spacing_m


def osf_hydraulic_diameter_m(geom: FinGeometry) -> float:
    """Offset-strip-fin hydraulic diameter, m (Manglik & Bergles 1995).

    ``D_h = 4 s h_f l / [2 (s l + h_f l + t h_f) + t s]`` - the spec R2
    equation 1; the test geometry reproduces 0.00232730508 m.
    """
    s, h_f, t, strip_length = (
        geom.fin_spacing_m,
        geom.fin_height_m,
        geom.fin_thickness_m,
        geom.strip_length_m,
    )
    return 4.0 * s * h_f * strip_length / (2.0 * (s * strip_length + h_f * strip_length + t * h_f) + t * s)


def osf_channels_per_layer(fin_spacing_m: float, fin_thickness_m: float, layer_width_m: float) -> float:
    """Number of fin channels in one layer, ``layer_width/(s + t)`` (spec R2)."""
    return layer_width_m / (fin_spacing_m + fin_thickness_m)


def osf_free_flow_area_m2(geom: FinGeometry, layer_width_m: float) -> float:
    """Free-flow area of one layer, ``A_ff = s h_f n_channels`` (spec R2)."""
    n = osf_channels_per_layer(geom.fin_spacing_m, geom.fin_thickness_m, layer_width_m)
    return geom.fin_spacing_m * geom.fin_height_m * n


def osf_heat_transfer_area_m2(geom: FinGeometry, length_m: float, layer_width_m: float) -> float:
    """Heat-transfer area of one layer, ``A_ht = 2 (s + h_f) L n_channels``.

    Fin plus parting-sheet area (Shah & Sekulic 2003, section 8.2; spec R2
    equation 1).
    """
    n = osf_channels_per_layer(geom.fin_spacing_m, geom.fin_thickness_m, layer_width_m)
    return 2.0 * (geom.fin_spacing_m + geom.fin_height_m) * length_m * n


def manglik_bergles_j(Re: float, alpha: float, delta: float, gamma: float) -> float:
    """Colburn ``j`` factor of an offset-strip-fin surface.

    Manglik & Bergles 1995, Exp. Therm. Fluid Sci. 10:171 (equation 34 pair):

        j = 0.6522 Re^-0.5403 alpha^-0.1541 delta^0.1499 gamma^-0.0678
            [1 + 5.269e-5 Re^1.340 alpha^0.504 delta^0.456 gamma^-1.055]^0.1
    """
    return float(
        0.6522
        * Re**-0.5403
        * alpha**-0.1541
        * delta**0.1499
        * gamma**-0.0678
        * (1.0 + 5.269e-5 * Re**1.340 * alpha**0.504 * delta**0.456 * gamma**-1.055) ** 0.1
    )


def manglik_bergles_f(Re: float, alpha: float, delta: float, gamma: float) -> float:
    """Fanning friction factor of an offset-strip-fin surface.

    Manglik & Bergles 1995, Exp. Therm. Fluid Sci. 10:171 (the friction
    member of the equation 34 pair):

        f = 9.6243 Re^-0.7422 alpha^-0.1856 delta^0.3053 gamma^-0.2659
            [1 + 7.669e-8 Re^4.429 alpha^0.920 delta^3.767 gamma^0.236]^0.1
    """
    return float(
        9.6243
        * Re**-0.7422
        * alpha**-0.1856
        * delta**0.3053
        * gamma**-0.2659
        * (1.0 + 7.669e-8 * Re**4.429 * alpha**0.920 * delta**3.767 * gamma**0.236) ** 0.1
    )


def fin_conductance_parameter_1_m(h_W_m2K: float, k_fin_W_mK: float, fin_thickness_m: float) -> float:
    """Fin parameter ``m = sqrt(2 h/(k_fin t))``, 1/m (spec R2 equation 3)."""
    if fin_thickness_m <= 0.0 or k_fin_W_mK <= 0.0:
        raise MultiStreamRatingError(
            f"param fin geometry must be positive: k_fin {k_fin_W_mK}, t {fin_thickness_m}"
        )
    return math.sqrt(2.0 * h_W_m2K / (k_fin_W_mK * fin_thickness_m))


def fin_efficiency(h_W_m2K: float, k_fin_W_mK: float, geom: FinGeometry) -> tuple[float, float]:
    """Fin efficiency ``eta_f = tanh(m L_f)/(m L_f)`` with ``L_f = h_f/2``.

    A strip fin between two parting sheets of the same stream (spec R2
    equation 3). Returns ``(m, eta_f)``.
    """
    m = fin_conductance_parameter_1_m(h_W_m2K, k_fin_W_mK, geom.fin_thickness_m)
    m_L_f = m * geom.fin_height_m / 2.0
    return m, math.tanh(m_L_f) / m_L_f


def surface_efficiency(h_W_m2K: float, k_fin_W_mK: float, geom: FinGeometry) -> float:
    """Overall surface efficiency ``eta_o = 1 - (A_fin/A_ht)(1 - eta_f)``.

    With ``A_fin/A_ht = h_f/(s + h_f)`` (Shah & Sekulic 2003, section 4.3;
    spec R2 equation 3).
    """
    _, eta_f = fin_efficiency(h_W_m2K, k_fin_W_mK, geom)
    A_fin_over_A_ht = geom.fin_height_m / (geom.fin_spacing_m + geom.fin_height_m)
    return 1.0 - A_fin_over_A_ht * (1.0 - eta_f)


#: Vapor-fraction band edges separating single-phase from two-phase zones.
_VF_LIQUID_MAX = 1e-8
_VF_VAPOR_MIN = 1.0 - 1e-8

#: Minimum wall superheat fed to ht.Liu_Winterton, K. The correlation's
#: nucleate-boiling member scales as Te^0.67 and is undefined at Te <= 0; a
#: zone whose wall is at or below saturation gets this floor (visible in the
#: zone's reported h, never hidden in a refusal).
_TE_FLOOR_K = 1e-6


@dataclass(frozen=True)
class R2StreamLayer:
    """One active stream's R2 geometry plus its shared T(H) table."""

    port: str
    state: StreamState
    is_hot: bool
    layer: StreamLayer  # hA_W_K is unused in R2; the zone model sets the hA
    geom: FinGeometry
    hydraulic_diameter_m: float
    mass_flux_kg_m2s: float  # G = mass flow / total free-flow area
    heat_transfer_area_m2: float  # total A_ht over all layers


@dataclass(frozen=True)
class R2SolveDetail:
    """Everything the zone loop produced (used by the identity test)."""

    outlets: dict[str, StreamState]
    info: dict[str, Any]
    final_result: CommonWallResult
    hA_zones: np.ndarray  # (n_streams, n_zones), W/K per unit x
    zone_iterations: int


def _geometry_of(port: str, params: dict[str, Any]) -> FinGeometry:
    """Read one stream's offset-strip-fin params, refusing missing or non-positive."""
    values: dict[str, float] = {}
    for name in ("fin_height", "fin_spacing", "fin_thickness", "strip_length"):
        key = f"{name}_{port}_m"
        raw = params.get(key)
        if raw is None:
            raise MultiStreamRatingError(f"active stream {port}: required param {key} is missing")
        value = float(raw)
        if value <= 0.0:
            raise MultiStreamRatingError(f"param {key} must be positive; got {value}")
        values[name] = value
    return FinGeometry(
        fin_height_m=values["fin_height"],
        fin_spacing_m=values["fin_spacing"],
        fin_thickness_m=values["fin_thickness"],
        strip_length_m=values["strip_length"],
    )


def _critical_pressure_Pa(composition: dict[str, float]) -> float:
    """Mole-weighted pseudo-critical pressure, Pa (component database)."""
    db = components()
    return sum(x * float(db[cid]["pc_Pa"]) for cid, x in composition.items())


def _molar_mass_g_over_mol(composition: dict[str, float]) -> float:
    """Mole-weighted molar mass from the component database, g/mol."""
    db = components()
    return sum(x * float(db[cid]["mw"]) for cid, x in composition.items())


def _mass_quality(state: StreamState) -> float:
    """Mass quality of a flashed state (vapor-phase mass over total mass)."""
    if not state.phases:
        return 1.0 if state.vapor_fraction >= 0.5 else 0.0
    masses = [p.mole_fraction * p.molecular_weight for p in state.phases]
    total = sum(masses)
    vapor = sum(m for m, p in zip(masses, state.phases, strict=False) if p.kind == PhaseKind.VAPOR)
    return vapor / total if total > 0.0 else 0.0


def _single_phase_h(geom: FinGeometry, Dh_m: float, G: float, props: FilmProps) -> float:
    """Single-phase film coefficient from Manglik-Bergles j: h = j*G*cp*Pr^(-2/3)."""
    Re = G * Dh_m / props.mu_Pa_s
    j = manglik_bergles_j(Re, geom.alpha, geom.delta, geom.gamma)
    return float(j * G * props.cp_J_kgK * props.Pr ** (-2.0 / 3.0))


def _two_phase_h(
    stream: R2StreamLayer,
    mean_state: StreamState,
    T_wall_zone_K: float,
    thermo: Thermo,
) -> float:
    """Two-phase film coefficient via the tube correlations through D_h.

    Stated approximation (Shah 1979; Liu & Winterton 1991): the tube-side
    condensation (ht.Shah) and flow-boiling (ht.Liu_Winterton) correlations
    are applied to the plate-fin channel by substituting the offset-strip-fin
    hydraulic diameter and a per-channel equivalent mass flow rate
    ``G * pi*Dh^2/4`` so the correlation's internal mass flux equals the
    channel's true ``G = mass flow / total free-flow area``.
    """
    P = stream.state.P
    liquid = film_props(thermo, stream.state.composition, mean_state.T, P, PhaseKind.HC_LIQUID)
    Pc = _critical_pressure_Pa(stream.state.composition)
    m_equiv = stream.mass_flux_kg_m2s * math.pi * stream.hydraulic_diameter_m**2 / 4.0
    x = _mass_quality(mean_state)
    if stream.is_hot:  # condensing: ht.Shah(m, x, D, rhol, mul, kl, Cpl, P, Pc)
        return float(
            ht.Shah(
                m_equiv,
                x,
                stream.hydraulic_diameter_m,
                liquid.rho_kg_m3,
                liquid.mu_Pa_s,
                liquid.k_W_mK,
                liquid.cp_J_kgK,
                P,
                Pc,
            )
        )
    vapor = film_props(thermo, stream.state.composition, mean_state.T, P, PhaseKind.VAPOR)
    Te = max(T_wall_zone_K - mean_state.T, _TE_FLOOR_K)
    MW = _molar_mass_g_over_mol(stream.state.composition)
    return float(
        ht.Liu_Winterton(
            m_equiv,
            x,
            stream.hydraulic_diameter_m,
            liquid.rho_kg_m3,
            vapor.rho_kg_m3,
            liquid.mu_Pa_s,
            liquid.k_W_mK,
            liquid.cp_J_kgK,
            MW,
            P,
            Pc,
            Te,
        )
    )


def _signature_of(func: Any) -> str:
    """Print helper for the measured-correlation check (test output)."""
    return f"{func.__name__}{inspect.signature(func)}"


class MultiStreamR2:
    """R2 multi-stream rating: zoned plate-fin with phase change.

    Plugin kind "unit", name "multi_stream", catalogue level R2. Same ports
    and zero-flow pass-through as R1; each active stream carries offset-strip
    fin layer geometry instead of ``hA``. The zone loop (spec algorithm step
    5) starts from the inlet-state single-phase h, cuts the hot composite
    into ``n_zones`` equal-delta-H zones, recomputes every stream's film
    coefficient at the zone-mean state (single-phase Manglik-Bergles j, or
    the two-phase tube correlations through D_h), and re-solves the
    common-wall BVP with a zoned conductance profile until the outlet
    temperatures stop moving.

    **Zoned conductance profile (orchestrator ruling on the R2 SPEC ISSUE).**
    Spec step (d) says "piecewise-constant hA_i(x) on the zone mesh", but
    ``solve_bvp``'s collocation error estimate refines every hA discontinuity
    until the node cap: measured on the R2 example case, ANY step in hA -
    down to a single 0.4% two-zone jump - hits ``max_nodes`` at tol 1e-8 and
    still at tol 1e-5, from every initial mesh tried (denser, warm-started,
    zone-edge-seeded). The re-solve therefore uses a CONTINUOUS conductance
    profile, piecewise-linear through the zone-centre values (spec option 1,
    accepted 2026-10-25): same zone-mean h values, same equations, and the
    more physical choice since the local film coefficients vary continuously
    along the exchanger. ``solve_bvp`` stays at the spec's tol 1e-8.

    The two-phase treatment is a stated approximation: tube-side correlations
    (ht.Shah condensation, ht.Liu_Winterton boiling) applied to plate-fin
    channels via the hydraulic diameter (Shah 1979; Liu & Winterton 1991).
    """

    inlet_ports = ("hot_in_1", "hot_in_2", "cold_in_1", "cold_in_2")
    outlet_ports = ("hot_out_1", "hot_out_2", "cold_out_1", "cold_out_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the exchanger (spec algorithm steps 1-5); see :meth:`_solve`."""
        detail = self._solve(inlets, params, thermo)
        duty_W = float(detail.info.pop("duty_W"))
        return UnitResult(outlets=detail.outlets, duty_W=duty_W, power_W=0.0, info=detail.info)

    def _solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> R2SolveDetail:
        hot_active = [(p, inlets[p]) for p in _HOT_PORTS if inlets[p].molar_flow > 0.0]
        cold_active = [(p, inlets[p]) for p in _COLD_PORTS if inlets[p].molar_flow > 0.0]
        if not hot_active or not cold_active:
            raise MultiStreamRatingError("at least one hot and one cold active stream are required")
        hottest_cold = max(state.T for _, state in cold_active)
        coldest_hot = min(state.T for _, state in hot_active)
        if hottest_cold >= coldest_hot:
            raise TemperatureCross(
                f"inlet temperatures give no positive driving force anywhere: "
                f"hottest cold inlet {hottest_cold:.6f} K >= coldest hot inlet "
                f"{coldest_hot:.6f} K"
            )

        raw_zones = params.get("n_zones", N_ZONES_DEFAULT)
        n_zones = int(raw_zones)
        if n_zones < 1:
            raise MultiStreamRatingError(f"param n_zones must be >= 1; got {n_zones}")
        raw_width = params.get("layer_width_m")
        raw_length = params.get("length_m")
        if raw_width is None:
            raise MultiStreamRatingError("required param layer_width_m is missing")
        if raw_length is None:
            raise MultiStreamRatingError("required param length_m is missing")
        layer_width_m, length_m = float(raw_width), float(raw_length)
        if layer_width_m <= 0.0 or length_m <= 0.0:
            raise MultiStreamRatingError("params layer_width_m and length_m must be positive")
        raw_k = params.get("k_fin_W_mK", K_FIN_DEFAULT_W_MK)
        k_fin = float(raw_k)
        if k_fin <= 0.0:
            raise MultiStreamRatingError(f"param k_fin_W_mK must be positive; got {k_fin}")

        active: list[tuple[str, StreamState, bool]] = [(p, s, True) for p, s in hot_active] + [
            (p, s, False) for p, s in cold_active
        ]
        hot_T_max = max(s.T for _, s in hot_active)
        cold_T_min = min(s.T for _, s in cold_active)

        streams: list[R2StreamLayer] = []
        for port, state, is_hot in active:
            geom = _geometry_of(port, params)
            raw_n = params.get(f"n_layers_{port}")
            if raw_n is None:
                raise MultiStreamRatingError(
                    f"active stream {port}: required param n_layers_{port} is missing"
                )
            n_layers = int(raw_n)
            if n_layers <= 0:
                raise MultiStreamRatingError(f"param n_layers_{port} must be positive; got {n_layers}")
            Dh = osf_hydraulic_diameter_m(geom)
            A_ff_total = n_layers * osf_free_flow_area_m2(geom, layer_width_m)
            A_ht_total = n_layers * osf_heat_transfer_area_m2(geom, length_m, layer_width_m)
            G = state.mass_flow / A_ff_total
            T_far = cold_T_min if is_hot else hot_T_max
            T_of_H, H_in, H_far = build_T_of_H_table(state, T_far, thermo)
            layer = StreamLayer(hA_W_K=1.0, H_in_W=H_in, H_far_W=H_far, T_of_H=T_of_H, is_hot=is_hot)
            streams.append(
                R2StreamLayer(
                    port=port,
                    state=state,
                    is_hot=is_hot,
                    layer=layer,
                    geom=geom,
                    hydraulic_diameter_m=Dh,
                    mass_flux_kg_m2s=G,
                    heat_transfer_area_m2=A_ht_total,
                )
            )

        def conductance_from_h(h_values: list[float]) -> np.ndarray:
            """(n_streams, 1) conductance hA_i = h_i * eta_o_i * A_ht_i, W/K per unit x."""
            return np.array(
                [
                    [h * surface_efficiency(h, k_fin, s.geom) * s.heat_transfer_area_m2]
                    for h, s in zip(h_values, streams, strict=False)
                ]
            )

        # (a) initial solve: hA from the inlet-state single-phase h.
        h_values = [
            _single_phase_h(
                s.geom,
                s.hydraulic_diameter_m,
                s.mass_flux_kg_m2s,
                film_props(thermo, s.state.composition, s.state.T, s.state.P, inlet_kind(s.state)),
            )
            for s in streams
        ]
        result = solve_common_wall(tuple(s.layer for s in streams), hA_zones=conductance_from_h(h_values))
        h_min: dict[str, float] = {}
        h_max: dict[str, float] = {}
        for stream, h in zip(streams, h_values, strict=False):
            h_min[stream.port], h_max[stream.port] = h, h

        hA_zones = np.zeros((len(streams), n_zones))
        iterations = 0
        T_out_previous: list[float] | None = None
        for _iterations in range(1, ZONE_MAX_ITERATIONS + 1):
            iterations = _iterations
            # (b) cut the hot composite into n_zones equal-delta-H zones.
            hot_idx = [i for i, stream in enumerate(streams) if stream.is_hot]
            composite = np.sum([result.H[i] for i in hot_idx], axis=0)
            edges = np.interp(
                np.linspace(composite[0], composite[-1], n_zones + 1), composite[::-1], result.x[::-1]
            )
            edges[0], edges[-1] = 0.0, 1.0
            # (c) zone-mean state per stream, then h_i,k.
            h_zones = np.zeros((len(streams), n_zones))
            for k in range(n_zones):
                x_lo, x_hi = sorted((edges[k], edges[k + 1]))
                mask = (result.x >= x_lo) & (result.x <= x_hi)
                T_wall_zone = (
                    float(np.mean(result.T_wall[mask])) if mask.any() else float(np.mean(result.T_wall))
                )
                for i, stream in enumerate(streams):
                    H_zone = result.H[i][mask]
                    H_mean = float(np.mean(H_zone)) if H_zone.size else float(np.mean(result.H[i]))
                    mean_state = thermo.flash_ph(
                        stream.state.composition,
                        stream.state.P,
                        H_mean / stream.state.molar_flow,
                        stream.state.molar_flow,
                    )
                    vf = mean_state.vapor_fraction
                    if vf <= _VF_LIQUID_MAX or vf >= _VF_VAPOR_MIN:
                        props = film_props(
                            thermo,
                            stream.state.composition,
                            mean_state.T,
                            stream.state.P,
                            PhaseKind.VAPOR if vf >= _VF_VAPOR_MIN else PhaseKind.HC_LIQUID,
                        )
                        h = _single_phase_h(
                            stream.geom, stream.hydraulic_diameter_m, stream.mass_flux_kg_m2s, props
                        )
                    else:
                        h = _two_phase_h(stream, mean_state, T_wall_zone, thermo)
                    h_zones[i, k] = h
                    h_min[stream.port] = min(h_min[stream.port], h)
                    h_max[stream.port] = max(h_max[stream.port], h)
            # Full-layer conductance h * eta_o * A_ht per unit normalised
            # length: the BVP integrates conductance over x, so per-zone
            # values need no zone-length scaling.
            hA_zones = np.array(
                [
                    [h * surface_efficiency(h, k_fin, s.geom) * s.heat_transfer_area_m2 for h in h_zones[i]]
                    for i, s in enumerate(streams)
                ]
            )
            # (d) re-solve with the continuous zoned conductance profile -
            # piecewise-linear through the zone-centre values (see the class
            # docstring for why a piecewise-constant profile cannot converge).
            zone_mesh = np.linspace(0.0, 1.0, 2 * n_zones + 1)
            result = solve_common_wall(
                tuple(s.layer for s in streams),
                hA_zones=hA_zones,
                y_init=np.vstack([np.interp(zone_mesh, result.x, result.H[i]) for i in range(len(streams))]),
            )
            # (e) outlet temperatures; converged when max |delta T_out| < ZONE_TOL_K.
            H_out = result.outlet_enthalpy_flows()
            T_out = [
                thermo.flash_ph(s.state.composition, s.state.P, H / s.state.molar_flow, s.state.molar_flow).T
                for s, H in zip(streams, H_out, strict=False)
            ]
            if (
                T_out_previous is not None
                and max(abs(a - b) for a, b in zip(T_out, T_out_previous, strict=False)) < ZONE_TOL_K
            ):
                break
            T_out_previous = T_out
        else:
            residual = (
                max(abs(a - b) for a, b in zip(T_out, T_out_previous, strict=False))
                if T_out_previous is not None
                else float("inf")
            )
            raise RatingConvergenceError(
                f"multi_stream R2 zone loop did not converge in {ZONE_MAX_ITERATIONS} iterations; "
                f"last max |delta T_out| = {residual:.3e} K"
            )

        check_wall_order(result)
        H_out = result.outlet_enthalpy_flows()
        outlets: dict[str, StreamState] = {}
        duty_by_port: dict[str, float] = {}
        for i, stream in enumerate(streams):
            raw_dP = params.get(f"dP_{stream.port}", 0.0)
            p_out = stream.state.P - float(raw_dP)
            if p_out <= 0.0:
                raise MultiStreamRatingError(
                    f"port {stream.port}: dP_{stream.port} = {raw_dP} Pa gives a non-positive "
                    f"outlet pressure {p_out} Pa"
                )
            outlet = thermo.flash_ph(
                stream.state.composition,
                p_out,
                H_out[i] / stream.state.molar_flow,
                stream.state.molar_flow,
            )
            outlets[_OUTLET_OF[stream.port]] = outlet
            duty_by_port[stream.port] = stream.state.molar_flow * (
                (stream.state.enthalpy - outlet.enthalpy)
                if stream.is_hot
                else (outlet.enthalpy - stream.state.enthalpy)
            )
        for port in (*_HOT_PORTS, *_COLD_PORTS):
            if inlets[port].molar_flow <= 0.0:
                outlets[_OUTLET_OF[port]] = inlets[port]

        h_in_total = sum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out_total = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        info: dict[str, Any] = {
            "min_approach_K": min_approach_K(result),
            "UA_total_W_K": wall_mediated_UA_W_K(result),
            "bvp_nodes": int(result.x.size),
            "n_zones": n_zones,
            "zone_iterations": iterations,
            "duty_W": h_out_total - h_in_total,
        }
        for port in (*_HOT_PORTS, *_COLD_PORTS):
            if port in duty_by_port:
                info[f"duty_{port}_W"] = duty_by_port[port]
            if port in h_min:
                info[f"h_{port}_min_W_m2K"] = h_min[port]
                info[f"h_{port}_max_W_m2K"] = h_max[port]
        return R2SolveDetail(
            outlets=outlets, info=info, final_result=result, hA_zones=hA_zones, zone_iterations=iterations
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feeds plus offset-strip-fin layer geometry for the
        two active streams; the second pair is zero-flow and passes through."""
        feeds, _ = MultiStreamExchanger.example_case()
        return feeds, {
            "n_layers_hot_in_1": 20,
            "fin_height_hot_in_1_m": 0.00635,
            "fin_spacing_hot_in_1_m": 0.0015,
            "fin_thickness_hot_in_1_m": 0.00015,
            "strip_length_hot_in_1_m": 0.003175,
            "n_layers_cold_in_1": 20,
            "fin_height_cold_in_1_m": 0.00635,
            "fin_spacing_cold_in_1_m": 0.0015,
            "fin_thickness_cold_in_1_m": 0.00015,
            "strip_length_cold_in_1_m": 0.003175,
            "layer_width_m": 0.6,
            "length_m": 2.0,
        }
