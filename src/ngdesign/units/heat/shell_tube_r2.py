"""Shell-and-tube exchanger, R2 rating level: zoned phase change (spec U-R2).

R2 extends the R1 Kern rating (``shell_tube_r1``) with zoned phase-change
analysis: the process enthalpy span is split into equal-dH zones (Serth &
Lestina, *Process Heat Transfer*, 2nd ed., Ch. 11), each zone picks its film
coefficient by the local phase regime, and the duty is solved from the
installed area rather than assumed.

Rating solve: ``brentq`` on ``Q`` with ``g(Q) = sum_k dA_k(Q)/F_corr - A_o``,
bracket bottom ``1e-6*Q_max``; the bracket top starts at ``Q_max`` and walks
inward (factor 0.9) until the zoned area demand is finite, because the
terminal approach vanishes at ``Q_max`` itself (one stream reaches the
other's inlet temperature there) and the demand diverges. Duties with an
internal zone cross or a non-physical trial state report an infinite area
demand rather than raising; the converged duty is re-evaluated strictly, so a
zone cross at the rated point raises ``TemperatureCross`` per the refusal
table. ``F_corr = 1`` for a single tube pass; otherwise
``ht.F_LMTD_Fakheri`` at the trial's terminal temperatures, applied uniformly
(the stated Serth Ch. 11 approximation); Fakheri domain errors on crossed
trials become a non-finite factor (infinite demand). After convergence with
``N_tp >= 2``, a non-finite or ``F < F_min`` result (default 0.75, Kern's
practical limit) raises ``TemperatureCross`` naming ``F`` and the minimum
shells in series required. ``xtol = 1e-10*Q_max``, ``maxiter = 100``.

Zone films (the zone-mean vapour fraction ``x_v`` from the flash selects the
regime):

- single phase: the R1 correlations (Gnielinski tube, Kern shell);
- shell-side condensation: Nusselt film on horizontal tubes, ``h_1`` per
  Incropera eq. 10.46 with ``h'_fg`` per eq. 10.9, the tube-bank correction
  ``h_1*N_r^(-1/4)`` per eq. 10.47 with ``N_r = tube_rows_vertical`` (a
  required param whenever a shell-side condensation zone is evaluated); the
  wall temperature comes from a fixed point capped at 50 iterations;
- tube-side condensation: ``ht.Shah`` (Shah 1979) with the zone-mean quality
  and the per-tube mass flow;
- tube-side flow boiling: ``ht.Liu_Winterton`` (Liu & Winterton 1991) with
  ``T_e = T_w - T_sat`` from the same fixed-point treatment;
- shell-side boiling is refused (``PhaseRegimeNotRated``): kettle and
  thermosiphon reboilers are not rated at R2.

The zone saturation temperature of a two-phase zone is the zone-mean
temperature of the stream (exact for a pure fluid, a zonal approximation for
mixtures); liquid properties are evaluated at the film temperature
``(T_sat + T_w)/2``. Pressure drops are inlet-property estimates distributed
linearly along each flow path (the R1 step-4 practice), so zone boundaries
flash on a fixed pressure schedule.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import ht
from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import components
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import (
    FilmProps,
    PropertyUnavailable,
    RatingConvergenceError,
    RatingError,
    SinglePhaseRequired,
    film_props,
    inlet_kind,
    u_outside_tube,
)
from ngdesign.units.heat.shell_tube_r1 import (
    KERN_RE_MAX,
    KERN_RE_MIN,
    KernRangeError,
    ShellGeometry,
    ShellTubeGeometryError,
    equiv_diameter,
    geometry,
    shell_dP,
    shell_flow_area,
    shell_friction,
    shell_h,
    tube_dP,
    tube_duct,
)

#: Standard gravity for the Nusselt film model (Incropera eq. 10.46), m/s2.
GRAVITY = 9.80665

#: Wall fixed-point tolerance, K (spec: |dT_w| < 1e-6).
WALL_TOL_K = 1e-6

#: Wall fixed-point iteration cap (spec: 50).
WALL_MAX_ITER = 50

#: brentq bracket low end as a fraction of Q_max (spec Rating solve).
Q_LO_FRACTION = 1e-6

#: Inward steps from Q_max for the finite-demand bracket top (the terminal
#: approach vanishes at Q_max itself, so the demand diverges there).
Q_HI_SEARCH_MAX = 100

#: Multiplicative shrink applied to the bracket top each inward step.
Q_HI_SHRINK_FACTOR = 0.9

#: brentq absolute tolerance as a fraction of Q_max (spec Rating solve).
BRENTQ_XTOL_FRACTION = 1e-10

#: brentq iteration cap (spec Rating solve).
BRENTQ_MAXITER = 100

#: Largest shell count tried when searching for the minimum shells in series.
SHELLS_SEARCH_MAX = 10

#: Vapour fractions within this distance of 0 or 1 count as single phase.
X_EPS = 1e-9

#: Typed aliases for the ht callables (ht 1.2.0 ships them unannotated).
FAKHERI: Any = ht.F_LMTD_Fakheri
SHAH: Any = ht.Shah
LIU_WINTERTON: Any = ht.Liu_Winterton


class PhaseRegimeNotRated(RatingError):
    """A phase regime R2 does not rate (shell-side boiling) was requested."""


def h_prime_fg(h_fg: float, cp_l: float, T_sat: float, T_w: float) -> float:
    """Corrected latent heat ``h_fg + 0.68*cp_l*(T_sat - T_w)`` (Incropera eq. 10.9)."""
    return h_fg + 0.68 * cp_l * (T_sat - T_w)


def nusselt_h1(
    rho_l: float,
    rho_v: float,
    k_l: float,
    mu_l: float,
    cp_l: float,
    h_fg: float,
    T_sat: float,
    T_w: float,
    D_o: float,
) -> float:
    """Nusselt film coefficient on a single horizontal tube (Incropera eq. 10.46).

    ``0.729*[g*rho_l*(rho_l - rho_v)*k_l^3*h'_fg/(mu_l*(T_sat - T_w)*D_o)]^0.25``
    with ``h'_fg`` per eq. 10.9; all properties liquid at the film temperature.
    """
    hp = h_prime_fg(h_fg, cp_l, T_sat, T_w)
    return float(
        0.729 * (GRAVITY * rho_l * (rho_l - rho_v) * k_l**3 * hp / (mu_l * (T_sat - T_w) * D_o)) ** 0.25
    )


def nusselt_bank(h_1: float, n_rows: float) -> float:
    """Tube-bank correction ``h_1*N_r^(-1/4)`` (Incropera eq. 10.47)."""
    return float(h_1 * n_rows ** (-0.25))


def wall_temperature_fixed_point(
    T_sat: float,
    T_util: float,
    *,
    boiling: bool,
    next_wall: Callable[[float], float],
    tol: float = WALL_TOL_K,
    max_iter: int = WALL_MAX_ITER,
) -> float:
    """Wall-temperature fixed point ``T_w = f(T_w)`` inside the wall band.

    Starts at the midpoint of ``(T_util, T_sat)`` (condensation) or
    ``(T_sat, T_util)`` (boiling) and iterates ``next_wall`` until ``|dT_w| <
    tol``. A map that leaves the open band between the saturation and utility
    temperatures raises ``RatingConvergenceError`` ("diverged"); a map that
    never settles raises ``RatingConvergenceError`` ("did not converge").
    """
    lo, hi = (T_util, T_sat) if not boiling else (T_sat, T_util)
    t_w = 0.5 * (T_sat + T_util)
    for _ in range(max_iter):
        t_next = next_wall(t_w)
        if not lo < t_next < hi:
            raise RatingConvergenceError(
                f"shell_tube R2: wall temperature diverged: T_w = {t_next} K left the band ({lo}, {hi}) K"
            )
        if abs(t_next - t_w) < tol:
            return t_next
        t_w = t_next
    raise RatingConvergenceError(
        f"shell_tube R2: wall-temperature fixed point did not converge within "
        f"{max_iter} iterations (last T_w = {t_w} K)"
    )


@dataclass(frozen=True)
class _Zone:
    """One zone's rating results (per-zone diagnostics and area demand)."""

    dQ: float
    dA: float
    U_W_m2K: float
    h_tube_W_m2K: float
    h_shell_W_m2K: float
    Re_tube: float
    Re_shell: float
    dT_lm_K: float
    dT_min_K: float


@dataclass(frozen=True)
class _Zoning:
    """The zoned area demand for one trial duty."""

    area_required_m2: float
    zones: tuple[_Zone, ...]
    process_out: StreamState
    utility_out: StreamState
    f_corr: float
    T_hot_in: float
    T_hot_out: float
    T_cold_in: float
    T_cold_out: float
    min_zone_dT_K: float

    @classmethod
    def diverged(cls, process: StreamState, utility: StreamState) -> _Zoning:
        """Sentinel for a non-physical or internally crossed trial duty."""
        return cls(
            area_required_m2=math.inf,
            zones=(),
            process_out=process,
            utility_out=utility,
            f_corr=math.nan,
            T_hot_in=process.T,
            T_hot_out=process.T,
            T_cold_in=utility.T,
            T_cold_out=utility.T,
            min_zone_dT_K=math.nan,
        )


def _liquid_kind(z: dict[str, float]) -> PhaseKind:
    """The liquid phase kind of a composition: aqueous when water-dominated."""
    if z.get("H2O", 0.0) >= 0.5:
        return PhaseKind.AQUEOUS
    return PhaseKind.HC_LIQUID


def _mw_g_mol(z: dict[str, float]) -> float:
    """Mole-weighted molecular weight, g/mol, from the component database."""
    db = components()
    return sum(x * float(db[cid]["mw"]) for cid, x in z.items())


def _critical_pressure_Pa(z: dict[str, float]) -> float:
    """Mole-weighted critical pressure (the control-valve convention), Pa."""
    db = components()
    return sum(x * float(db[cid]["pc_Pa"]) for cid, x in z.items())


def _phase_film(thermo: Thermo, z: dict[str, float], T: float, P: float, kind: PhaseKind) -> FilmProps:
    """Mass-specific film properties of one phase built without flashing."""
    props = thermo.phase_props(z, T, P, kind)
    if props.viscosity is None or props.thermal_conductivity is None:
        raise PropertyUnavailable(
            f"shell_tube R2: liquid/vapour transport properties unavailable at T = {T} K"
        )
    return FilmProps(
        rho_kg_m3=props.density,
        mu_Pa_s=props.viscosity,
        k_W_mK=props.thermal_conductivity,
        cp_J_kgK=props.cp / props.molecular_weight * 1000.0,
    )


def _latent_heat_J_kg(thermo: Thermo, z: dict[str, float], P: float) -> float:
    """The zone's latent heat: dew-state minus bubble-state enthalpy (spec R2).

    ``dew_point``/``bubble_point`` at the zone pressure plus ``flash_pt`` for
    each incipient state; molar J/mol converted with the mixture molar mass.
    """
    dew = thermo.dew_point(z, P=P)
    bub = thermo.bubble_point(z, P=P)
    h_dew = thermo.flash_pt(z, dew.T, P, 1.0).enthalpy
    h_bub = thermo.flash_pt(z, bub.T, P, 1.0).enthalpy
    return (h_dew - h_bub) / _mw_g_mol(z) * 1000.0


@dataclass(frozen=True)
class R2Geometry:
    """Validated R1 geometry plus the R2-only params (defaults applied)."""

    base: ShellGeometry
    n_zones: int
    tube_rows_vertical: int | None
    F_min: float


def _int_param(name: str, value: Any, low: int, high: int | None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ShellTubeGeometryError(f"shell_tube R2: {name} must be an integer, got {value!r}") from None
    if parsed != value or parsed < low or (high is not None and parsed > high):
        bound = f">= {low}" if high is None else f"within [{low}, {high}]"
        raise ShellTubeGeometryError(f"shell_tube R2: {name} must be {bound}, got {value!r}")
    return parsed


def geometry_r2(params: dict[str, Any]) -> R2Geometry:
    """Validate the R2 params on top of the R1 geometry validation."""
    base = geometry(params)
    n_zones = _int_param("n_zones", params.get("n_zones", 20), 1, 200)
    rows_raw = params.get("tube_rows_vertical")
    rows = None if rows_raw is None else _int_param("tube_rows_vertical", rows_raw, 1, None)
    f_min_raw = params.get("F_min", 0.75)
    try:
        f_min = float(f_min_raw)
    except (TypeError, ValueError):
        raise ShellTubeGeometryError(
            f"shell_tube R2: F_min must be a number in (0, 1), got {f_min_raw!r}"
        ) from None
    if not 0.0 < f_min < 1.0:
        raise ShellTubeGeometryError(f"shell_tube R2: F_min must lie in (0, 1), got {f_min}")
    return R2Geometry(base=base, n_zones=n_zones, tube_rows_vertical=rows, F_min=f_min)


class ShellTubeR2:
    """Shell-and-tube exchanger, R2: zoned phase-change rating level.

    One process port pair (``inlet`` -> ``outlet``); the utility stream comes
    from the ``utility_*`` params, is computed internally and is never a port.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A C3/C4 vapour condensed by cooling water (spec step 5).

        The process is a propane/butane vapour at 360 K, 1.5 MPa, 380 mol/s on
        the SHELL side of geometry G1 (the flow keeps the shell-side inlet
        Re_s inside Kern's 2e3-1e6 band), against cooling water (H2O, 303.15 K,
        4 bar, 1000 mol/s) in the tubes; the vapour partly condenses across
        the rated duty, so the zones span superheated vapour, two-phase
        condensation and (possibly) subcooled liquid.
        """
        feed = {
            "T": 360.0,
            "P": 1.5e6,
            "molar_flow": 380.0,
            "composition": {"C3": 0.6, "nC4": 0.4},
        }
        params: dict[str, Any] = {
            "process_side": "shell",
            "shell_ID_m": 0.489,
            "n_tubes": 158,
            "tube_OD_m": 0.01905,
            "tube_ID_m": 0.01483,
            "tube_length_m": 4.877,
            "pitch_m": 0.02381,
            "layout": "triangular30",
            "baffle_spacing_m": 0.3048,
            "n_baffles": 15,
            "tube_passes": 2,
            "utility_composition": {"H2O": 1.0},
            "utility_T_K": 303.15,
            "utility_P_Pa": 4.0e5,
            "utility_molar_flow": 1000.0,
            "tube_rows_vertical": 12,
        }
        return {"inlet": feed}, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the exchanger at the R2 level; see the module docstring."""
        geom2 = geometry_r2(params)
        geom = geom2.base
        process = inlets["inlet"]
        utility = thermo.flash_pt(
            geom.utility_composition, geom.utility_T_K, geom.utility_P_Pa, geom.utility_molar_flow
        )

        # Hot/cold assignment: the hotter inlet is "hot"; equal inlets refuse.
        if abs(process.T - utility.T) <= 1e-9:
            raise TemperatureCross(
                f"shell_tube R2: inlet temperatures are equal (within 1e-9 K) at "
                f"T = {process.T} K; no driving force"
            )
        hot_is_process = process.T > utility.T

        # Shell-side boiling is refused up front when the shell side carries a
        # two-phase stream that is being heated; a liquid that boils across the
        # duty is caught by the zone-level backstop below.
        shell_is_process = geom.process_side == "shell"
        shell_is_cold = shell_is_process != hot_is_process
        shell_is_hot = not shell_is_cold
        shell_inlet = process if shell_is_process else utility
        if shell_is_cold and 0.0 < shell_inlet.vapor_fraction < 1.0:
            raise PhaseRegimeNotRated(
                "shell_tube R2: shell-side boiling (kettle/thermosiphon) is not rated at R2"
            )

        # Geometry scalars (Eq. S1, S2 and A_o = Nt*pi*Do*L).
        a_s = shell_flow_area(geom.shell_ID_m, geom.pitch_m, geom.tube_OD_m, geom.baffle_spacing_m)
        de = equiv_diameter(geom.pitch_m, geom.tube_OD_m, geom.layout)
        a_o = geom.n_tubes * math.pi * geom.tube_OD_m * geom.tube_length_m

        tube_is_process = not shell_is_process
        tube_state = process if tube_is_process else utility
        shell_state = utility if tube_is_process else process

        # Inlet films and pressure drops from INLET-state properties (the R1
        # step-4 practice); a two-phase inlet uses its dominant-phase film for
        # the estimate only.
        def inlet_film(state: StreamState) -> FilmProps:
            try:
                kind = inlet_kind(state)
            except SinglePhaseRequired:
                kind = PhaseKind.VAPOR if state.vapor_fraction >= 0.5 else _liquid_kind(state.composition)
            return film_props(thermo, state.composition, state.T, state.P, kind)

        film_tube_in = inlet_film(tube_state)
        film_shell_in = inlet_film(shell_state)
        tube_in = tube_duct(
            tube_state.mass_flow,
            geom.n_tubes,
            geom.tube_passes,
            geom.tube_ID_m,
            film_tube_in,
            geom.roughness_m,
        )
        gs_in = shell_state.mass_flow / a_s
        re_s_in = de * gs_in / film_shell_in.mu_Pa_s
        dP_tube = tube_dP(
            tube_in.fd,
            geom.tube_passes,
            geom.tube_length_m,
            geom.tube_ID_m,
            film_tube_in.rho_kg_m3,
            tube_in.v_m_s,
        )
        dP_shell = shell_dP(
            shell_friction(re_s_in),
            gs_in,
            geom.n_baffles,
            geom.shell_ID_m,
            film_shell_in.rho_kg_m3,
            de,
        )
        dP_process = dP_tube if tube_is_process else dP_shell
        dP_utility = dP_shell if tube_is_process else dP_tube
        if process.P - dP_process <= 0.0 or utility.P - dP_utility <= 0.0:
            raise RatingError(
                f"non-positive outlet pressure across this geometry "
                f"(process drops {dP_process} Pa, utility drops {dP_utility} Pa)"
            )

        # Kern's shell-side band, checked on the inlet state (R1 step-6 parity);
        # the zone-level Re values are reported in info.
        kern_in_range = KERN_RE_MIN < re_s_in <= KERN_RE_MAX
        if not kern_in_range and not geom.allow_extrapolation:
            raise KernRangeError(
                f"shell-side Re_s = {re_s_in} outside Kern's validity band "
                f"[{KERN_RE_MIN}, {KERN_RE_MAX}]; raise the utility flow or set allow_extrapolation"
            )

        # Energy maximum: one stream reaching the other's inlet temperature.
        p_at_uT = thermo.flash_pt(process.composition, utility.T, process.P, process.molar_flow)
        u_at_pT = thermo.flash_pt(utility.composition, process.T, utility.P, utility.molar_flow)
        q_max = min(
            process.molar_flow * abs(p_at_uT.enthalpy - process.enthalpy),
            utility.molar_flow * abs(u_at_pT.enthalpy - utility.enthalpy),
        )
        if q_max <= 0.0:
            raise TemperatureCross(
                f"shell_tube R2: no heat-transfer driving force between {process.T} K and {utility.T} K"
            )

        n = geom2.n_zones
        s_p = -1.0 if hot_is_process else 1.0
        s_u = -s_p

        def process_boundaries(Q: float) -> list[StreamState]:
            """Equal-dH zone boundaries of the process on a fixed P schedule."""
            q_mol = Q / process.molar_flow
            return [
                thermo.flash_ph(
                    process.composition,
                    process.P - dP_process * k / n,
                    process.enthalpy + s_p * q_mol * k / n,
                    process.molar_flow,
                )
                for k in range(n + 1)
            ]

        def utility_boundaries(Q: float) -> list[StreamState]:
            """Utility boundaries from its own energy balance on flash_ph."""
            q_mol = Q / utility.molar_flow
            return [
                thermo.flash_ph(
                    utility.composition,
                    utility.P - dP_utility * j / n,
                    utility.enthalpy + s_u * q_mol * j / n,
                    utility.molar_flow,
                )
                for j in range(n + 1)
            ]

        gs_zone = shell_state.mass_flow / a_s
        area_per_tube = math.pi * geom.tube_ID_m * geom.tube_ID_m / 4.0

        def zone_films(
            tube_a: StreamState,
            tube_b: StreamState,
            shell_a: StreamState,
            shell_b: StreamState,
            tube_is_hot: bool,
        ) -> tuple[float, float, float, float, float]:
            """Tube/shell film coefficients and Re for one zone, plus U.

            The tube side is evaluated first (Shah and the single-phase core
            need no opposite-side value); a shell-side condensation fixed
            point uses the tube-side h, and a tube-side boiling fixed point
            re-runs with the converged shell-side h.
            """
            x_t = 0.5 * (tube_a.vapor_fraction + tube_b.vapor_fraction)
            x_s = 0.5 * (shell_a.vapor_fraction + shell_b.vapor_fraction)
            Tt = 0.5 * (tube_a.T + tube_b.T)
            Ts = 0.5 * (shell_a.T + shell_b.T)
            Pt = 0.5 * (tube_a.P + tube_b.P)
            Ps = 0.5 * (shell_a.P + shell_b.P)
            m_per_tube = tube_a.mass_flow / (geom.n_tubes / geom.tube_passes)

            # --- tube side, pass 1 ---
            re_t: float
            if x_t <= X_EPS or x_t >= 1.0 - X_EPS:
                film_t = film_props(
                    thermo,
                    tube_a.composition,
                    Tt,
                    Pt,
                    PhaseKind.VAPOR if x_t > 0.5 else _liquid_kind(tube_a.composition),
                )
                duct = tube_duct(
                    tube_a.mass_flow,
                    geom.n_tubes,
                    geom.tube_passes,
                    geom.tube_ID_m,
                    film_t,
                    geom.roughness_m,
                )
                h_t, re_t = duct.h_W_m2K, duct.Re
            elif tube_is_hot:
                liq = _phase_film(thermo, tube_a.composition, Tt, Pt, _liquid_kind(tube_a.composition))
                pc = _critical_pressure_Pa(tube_a.composition)
                h_t = float(
                    SHAH(
                        m_per_tube,
                        x_t,
                        geom.tube_ID_m,
                        liq.rho_kg_m3,
                        liq.mu_Pa_s,
                        liq.k_W_mK,
                        liq.cp_J_kgK,
                        Pt,
                        pc,
                    )
                )
                re_t = m_per_tube / area_per_tube * geom.tube_ID_m / liq.mu_Pa_s
            else:
                # Tube-side flow boiling: first pass with the mid-band wall
                # superheat; the converged pass runs after the shell side.
                liq = _phase_film(thermo, tube_a.composition, Tt, Pt, _liquid_kind(tube_a.composition))
                vap = _phase_film(thermo, tube_a.composition, Tt, Pt, PhaseKind.VAPOR)
                pc = _critical_pressure_Pa(tube_a.composition)
                mw = _mw_g_mol(tube_a.composition)

                def lw_h(te: float) -> float:
                    return float(
                        LIU_WINTERTON(
                            m_per_tube,
                            x_t,
                            geom.tube_ID_m,
                            liq.rho_kg_m3,
                            vap.rho_kg_m3,
                            liq.mu_Pa_s,
                            liq.k_W_mK,
                            liq.cp_J_kgK,
                            mw,
                            Pt,
                            pc,
                            te,
                        )
                    )

                h_t = lw_h(0.5 * (Ts - Tt))
                re_t = m_per_tube / area_per_tube * geom.tube_ID_m / liq.mu_Pa_s

            # --- shell side ---
            re_s: float
            if x_s <= X_EPS or x_s >= 1.0 - X_EPS:
                film_s = film_props(
                    thermo,
                    shell_a.composition,
                    Ts,
                    Ps,
                    PhaseKind.VAPOR if x_s > 0.5 else _liquid_kind(shell_a.composition),
                )
                re_s = de * gs_zone / film_s.mu_Pa_s
                h_s = shell_h(film_s.k_W_mK, de, re_s, film_s.Pr)
            elif not shell_is_hot:
                raise PhaseRegimeNotRated(
                    "shell_tube R2: shell-side boiling (kettle/thermosiphon) is not rated at R2"
                )
            else:
                # Shell-side condensation: Nusselt bank with the wall-temperature
                # fixed point (Incropera eqs. 10.46/10.47/10.9).
                rows = geom2.tube_rows_vertical
                if rows is None:
                    raise ShellTubeGeometryError(
                        "shell_tube R2 requires geometry param 'tube_rows_vertical' "
                        "(N_r, the mean tubes per vertical row, for the Incropera eq. 10.47 bank correction)"
                    )
                liq_vap = _phase_film(thermo, shell_a.composition, Ts, Ps, PhaseKind.VAPOR)
                h_fg = _latent_heat_J_kg(thermo, shell_a.composition, Ps)

                def bank_at(t_w: float, T_sat: float) -> float:
                    film = _phase_film(
                        thermo,
                        shell_a.composition,
                        0.5 * (T_sat + t_w),
                        Ps,
                        _liquid_kind(shell_a.composition),
                    )
                    h1 = nusselt_h1(
                        film.rho_kg_m3,
                        liq_vap.rho_kg_m3,
                        film.k_W_mK,
                        film.mu_Pa_s,
                        film.cp_J_kgK,
                        h_fg,
                        T_sat,
                        t_w,
                        geom.tube_OD_m,
                    )
                    return nusselt_bank(h1, float(rows))

                def next_wall(t_w: float) -> float:
                    h_c = bank_at(t_w, Ts)
                    u_k = u_outside_tube(
                        h_i=h_t,
                        h_o=h_c,
                        Do=geom.tube_OD_m,
                        Di=geom.tube_ID_m,
                        k_wall=geom.k_wall_W_mK,
                        R_fi=geom.R_f_tube_m2K_W,
                        R_fo=geom.R_f_shell_m2K_W,
                    )
                    return Ts - u_k * (Ts - Tt) / h_c

                t_w = wall_temperature_fixed_point(Ts, Tt, boiling=False, next_wall=next_wall)
                h_s = bank_at(t_w, Ts)
                liq_film = _phase_film(
                    thermo,
                    shell_a.composition,
                    0.5 * (Ts + t_w),
                    Ps,
                    _liquid_kind(shell_a.composition),
                )
                re_s = de * gs_zone / liq_film.mu_Pa_s

            # --- tube side, pass 2 (boiling only): fixed point on T_e ---
            if X_EPS < x_t < 1.0 - X_EPS and not tube_is_hot:
                liq = _phase_film(thermo, tube_a.composition, Tt, Pt, _liquid_kind(tube_a.composition))
                vap = _phase_film(thermo, tube_a.composition, Tt, Pt, PhaseKind.VAPOR)
                pc = _critical_pressure_Pa(tube_a.composition)
                mw = _mw_g_mol(tube_a.composition)

                def lw_final(te: float) -> float:
                    return float(
                        LIU_WINTERTON(
                            m_per_tube,
                            x_t,
                            geom.tube_ID_m,
                            liq.rho_kg_m3,
                            vap.rho_kg_m3,
                            liq.mu_Pa_s,
                            liq.k_W_mK,
                            liq.cp_J_kgK,
                            mw,
                            Pt,
                            pc,
                            te,
                        )
                    )

                def next_wall_boil(t_w: float) -> float:
                    h_b = lw_final(t_w - Tt)
                    u_k = u_outside_tube(
                        h_i=h_b,
                        h_o=h_s,
                        Do=geom.tube_OD_m,
                        Di=geom.tube_ID_m,
                        k_wall=geom.k_wall_W_mK,
                        R_fi=geom.R_f_tube_m2K_W,
                        R_fo=geom.R_f_shell_m2K_W,
                    )
                    return Tt + u_k * (Ts - Tt) / h_b

                t_wall = wall_temperature_fixed_point(Tt, Ts, boiling=True, next_wall=next_wall_boil)
                h_t = lw_final(t_wall - Tt)

            u_k_final = u_outside_tube(
                h_i=h_t,
                h_o=h_s,
                Do=geom.tube_OD_m,
                Di=geom.tube_ID_m,
                k_wall=geom.k_wall_W_mK,
                R_fi=geom.R_f_tube_m2K_W,
                R_fo=geom.R_f_shell_m2K_W,
            )
            return h_t, h_s, re_t, re_s, u_k_final

        def evaluate(Q: float, *, strict: bool) -> _Zoning:
            """Zone the trial duty and sum the area demand."""
            try:
                p_states = process_boundaries(Q)
                u_states = utility_boundaries(Q)
                zones: list[_Zone] = []
                for k in range(n):
                    pa, pb = p_states[k], p_states[k + 1]
                    ua, ub = u_states[n - k], u_states[n - k - 1]
                    # Counter-current pairing: end A (process-inlet side) and
                    # end B (process-outlet side) of the zone.
                    if hot_is_process:
                        th_a, th_b, tc_a, tc_b = pa.T, pb.T, ua.T, ub.T
                    else:
                        th_a, th_b, tc_a, tc_b = ua.T, ub.T, pa.T, pb.T
                    d_a, d_b = th_a - tc_a, th_b - tc_b
                    d_min = min(d_a, d_b)
                    if d_min <= 0.0:
                        raise TemperatureCross(
                            f"shell_tube R2: internal temperature cross in zone {k}: "
                            f"zone-end approaches {d_a} K and {d_b} K"
                        )
                    dT_lm = lmtd_counter(th_a, th_b, tc_b, tc_a)
                    tube_a, tube_b = (pa, pb) if tube_is_process else (ua, ub)
                    shell_a, shell_b = (ua, ub) if tube_is_process else (pa, pb)
                    h_t, h_s, re_t, re_s, u_k = zone_films(
                        tube_a, tube_b, shell_a, shell_b, hot_is_process == tube_is_process
                    )
                    d_q = Q / n
                    zones.append(
                        _Zone(
                            dQ=d_q,
                            dA=d_q / (u_k * dT_lm),
                            U_W_m2K=u_k,
                            h_tube_W_m2K=h_t,
                            h_shell_W_m2K=h_s,
                            Re_tube=re_t,
                            Re_shell=re_s,
                            dT_lm_K=dT_lm,
                            dT_min_K=d_min,
                        )
                    )
                a_req = sum(z.dA for z in zones)
                if geom.tube_passes == 1:
                    f_corr = 1.0
                else:
                    try:
                        f_corr = float(
                            FAKHERI(
                                p_states[0].T if hot_is_process else u_states[0].T,
                                p_states[n].T if hot_is_process else u_states[n].T,
                                u_states[0].T if hot_is_process else p_states[0].T,
                                u_states[n].T if hot_is_process else p_states[n].T,
                                shells=geom.n_shells,
                            )
                        )
                    except (ValueError, ZeroDivisionError):
                        f_corr = math.nan
            except TemperatureCross:
                if strict:
                    raise
                return _Zoning.diverged(process, utility)
            except (ValueError, ArithmeticError):
                # Non-physical trial flash (e.g. an enthalpy the package cannot
                # place): infinite demand, per the rating-solve contract.
                if strict:
                    raise
                return _Zoning.diverged(process, utility)
            return _Zoning(
                area_required_m2=a_req,
                zones=tuple(zones),
                process_out=p_states[n],
                utility_out=u_states[n],
                f_corr=f_corr,
                T_hot_in=p_states[0].T if hot_is_process else u_states[0].T,
                T_hot_out=p_states[n].T if hot_is_process else u_states[n].T,
                T_cold_in=u_states[0].T if hot_is_process else p_states[0].T,
                T_cold_out=u_states[n].T if hot_is_process else p_states[n].T,
                min_zone_dT_K=min(z.dT_min_K for z in zones),
            )

        def area_demand(Q: float) -> float:
            """g(Q) = A_req(Q)/F_corr - A_o; infinite for crossed trials."""
            trial = evaluate(Q, strict=False)
            if not math.isfinite(trial.area_required_m2):
                return math.inf
            if not math.isfinite(trial.f_corr) or trial.f_corr <= 0.0:
                return math.inf
            return trial.area_required_m2 / trial.f_corr - a_o

        # brentq bracket: bottom at 1e-6*Q_max; the top walks inward from
        # Q_max until the demand is finite and positive.
        q_hi = q_max
        g_hi = area_demand(q_hi)
        steps = 0
        while not (math.isfinite(g_hi) and g_hi > 0.0) and steps < Q_HI_SEARCH_MAX:
            q_hi *= Q_HI_SHRINK_FACTOR
            g_hi = area_demand(q_hi)
            steps += 1
        if not (math.isfinite(g_hi) and g_hi > 0.0):
            raise RatingConvergenceError(
                "shell_tube R2: did not converge: no finite-demand duty bracket "
                f"found below the energy maximum {q_max} W"
            )
        q_lo = Q_LO_FRACTION * q_max
        g_lo = area_demand(q_lo)
        if not (math.isfinite(g_lo) and g_lo < 0.0):
            raise RatingConvergenceError(
                "shell_tube R2: did not converge: the area demand is already "
                f"positive at the smallest trial duty {q_lo} W (the installed area is far too small)"
            )
        Q = brentq(area_demand, q_lo, q_hi, xtol=BRENTQ_XTOL_FRACTION * q_max, maxiter=BRENTQ_MAXITER)

        rated = evaluate(Q, strict=True)
        if not math.isfinite(rated.area_required_m2) or rated.area_required_m2 <= 0.0:
            raise RatingConvergenceError("shell_tube R2: did not converge at the rated duty")

        # Multi-pass temperature cross: F must be finite and >= F_min.
        shells_required = 1
        if geom.tube_passes >= 2:
            f_final = rated.f_corr
            if not math.isfinite(f_final) or f_final < geom2.F_min:
                n_star: int | None = None
                for shells in range(1, SHELLS_SEARCH_MAX + 1):
                    try:
                        f_sh = float(
                            FAKHERI(
                                rated.T_hot_in,
                                rated.T_hot_out,
                                rated.T_cold_in,
                                rated.T_cold_out,
                                shells=shells,
                            )
                        )
                    except (ValueError, ZeroDivisionError):
                        continue
                    if math.isfinite(f_sh) and f_sh >= geom2.F_min:
                        n_star = shells
                        break
                message = (
                    f"shell_tube R2: F_LMTD = {f_final} is below F_min = {geom2.F_min} "
                    f"at the converged duty: a multi-pass temperature cross"
                )
                if n_star is not None:
                    message += f"; shells_required = {n_star} shells in series reaches F >= F_min"
                else:
                    message += (
                        f"; no arrangement within {SHELLS_SEARCH_MAX} shells in series reaches F >= F_min"
                    )
                raise TemperatureCross(message)
            shells_required = 1

        # dA-weighted zone diagnostics.
        w_total = rated.area_required_m2
        zones_t = rated.zones

        def dA_mean(attr: str) -> float:
            return float(sum(getattr(z, attr) * z.dA for z in zones_t) / w_total)

        lmtd_global = lmtd_counter(rated.T_hot_in, rated.T_hot_out, rated.T_cold_in, rated.T_cold_out)
        ua_w_k = Q / lmtd_global
        c_hot = Q / abs(rated.T_hot_in - rated.T_hot_out)
        c_cold = Q / abs(rated.T_cold_out - rated.T_cold_in)
        c_min = min(c_hot, c_cold)
        duty_W = process.molar_flow * (rated.process_out.enthalpy - process.enthalpy)
        info: dict[str, Any] = {
            "Q_W": duty_W,
            "U_W_m2K": ua_w_k / a_o,
            "A_m2": a_o,
            "UA_W_K": ua_w_k,
            "NTU": ua_w_k / c_min,
            "effectiveness": Q / (c_min * (rated.T_hot_in - rated.T_cold_in)),
            "F_LMTD": rated.f_corr,
            "LMTD_K": lmtd_global,
            "h_tube_W_m2K": dA_mean("h_tube_W_m2K"),
            "h_shell_W_m2K": dA_mean("h_shell_W_m2K"),
            "Re_tube": dA_mean("Re_tube"),
            "Re_shell": dA_mean("Re_shell"),
            "dP_tube_Pa": dP_tube,
            "dP_shell_Pa": dP_shell,
            "utility_T_out_K": rated.utility_out.T,
            "utility_P_out_Pa": utility.P - dP_utility,
            "utility_duty_W": duty_W,
            "kern_in_range": float(kern_in_range),
            "n_zones": n,
            "A_required_m2": rated.area_required_m2,
            "shells_required": shells_required,
            "min_zone_dT_K": rated.min_zone_dT_K,
            "zone_U_min_W_m2K": min(z.U_W_m2K for z in zones_t),
            "zone_U_max_W_m2K": max(z.U_W_m2K for z in zones_t),
        }
        return UnitResult(
            outlets={"outlet": rated.process_out},
            duty_W=duty_W,
            power_W=0.0,
            info=info,
        )


__all__ = [
    "BRENTQ_MAXITER",
    "BRENTQ_XTOL_FRACTION",
    "FAKHERI",
    "GRAVITY",
    "LIU_WINTERTON",
    "Q_HI_SEARCH_MAX",
    "Q_HI_SHRINK_FACTOR",
    "Q_LO_FRACTION",
    "SHELLS_SEARCH_MAX",
    "SHAH",
    "WALL_MAX_ITER",
    "WALL_TOL_K",
    "PhaseRegimeNotRated",
    "R2Geometry",
    "ShellTubeR2",
    "geometry_r2",
    "h_prime_fg",
    "nusselt_bank",
    "nusselt_h1",
    "wall_temperature_fixed_point",
]
