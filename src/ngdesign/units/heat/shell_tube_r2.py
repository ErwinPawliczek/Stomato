"""Shell-and-tube exchanger R2: zone analysis with phase change (``specs/backend/units/shell_tube.md``).

Zone analysis (Serth & Lestina, *Process Heat Transfer*, 2nd ed., ch. 11; Kern 1950,
chs. 12-13), counter-current pairing.  For a trial duty Q the process enthalpy span is
cut into ``n_zones`` equal-duty zones; the utility states at the matching boundaries come
from its own energy balance, so a condensing or boiling utility is zoned too.  Per zone,
A_k = Q_k/(U_k*LMTD_k), and the rating solves Sum A_k/F = A_o for Q.

Local film coefficients by the zone-mean phase regime:

- single phase: the R1 correlations (Gnielinski tube, Kern shell) at the zone-mean T;
- shell-side condensation on horizontal tubes, Nusselt: h_1 = 0.729*[g*rho_l*(rho_l -
  rho_v)*k_l**3*h'_fg/(mu_l*(T_sat - T_w)*D_o)]**(1/4) (Incropera eq. 10.46), with h'_fg =
  h_fg + 0.68*cp_l*(T_sat - T_w) (eq. 10.9), and h = h_1*N_r**(-1/4) for the bank (eq. 10.47);
- tube-side condensation: ``ht.Shah`` (Shah 1979);
- tube-side flow boiling: ``ht.Liu_Winterton`` (Liu & Winterton 1991);
- shell-side boiling is not rated (kettle and thermosiphon are other geometries).

T_w closes by a fixed point on U; the wall viscosity correction stays 1 as at R1.  For
several tube passes a single F from the terminal temperatures applies to every zone, a
stated approximation (Serth ch. 11); F is exact for one zone in a 1-2 exchanger.  Pressure
drops are R1's, from inlet-state properties, so the inlets must be single phase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import ht
from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import (
    FilmProps,
    RatingConvergenceError,
    RatingError,
    SinglePhaseRequired,
    film_props,
    inlet_kind,
    u_outside_tube,
)
from ngdesign.units.heat.shell_tube_r1 import (
    ShellGeometry,
    equiv_diameter,
    geometry,
    shell_dP,
    shell_flow_area,
    shell_friction,
    shell_h,
    tube_dP,
    tube_duct,
)
from ngdesign.units.pump import G_STD

_WALL_MAX_ITER = 50
_WALL_TOL_K = 1.0e-6

#: Bisections separating feasible duties from those with an internal cross.
_FEASIBLE_BISECTIONS = 40


class PhaseRegimeNotRated(RatingError):
    """The zone's regime has no rated correlation here."""


class _Infeasible(Exception):
    """A trial duty crosses temperatures or has no F; the search backs off."""


def nusselt_bank_h(
    rho_l: float,
    rho_v: float,
    k_l: float,
    mu_l: float,
    cp_l: float,
    h_fg: float,
    t_sat: float,
    t_wall: float,
    d_o: float,
    n_rows: int,
) -> float:
    """Film condensation on a bank of N_r horizontal tubes (Incropera eqs. 10.9, 10.46, 10.47)."""
    d_t = t_sat - t_wall
    h_prime = h_fg + 0.68 * cp_l * d_t
    single = 0.729 * (G_STD * rho_l * (rho_l - rho_v) * k_l**3 * h_prime / (mu_l * d_t * d_o)) ** 0.25
    return float(single * n_rows**-0.25)


def fixed_point_wall(h_of_wall: Any, t_sat: float, t_other: float, u_of: Any) -> tuple[float, float]:
    """(h, T_w) closing T_w = T_sat - U*(T_sat - T_other)/h, damped by one half."""
    t_w = 0.5 * (t_sat + t_other)
    for _ in range(_WALL_MAX_ITER):
        h = h_of_wall(t_w)
        target = t_sat - u_of(h) * (t_sat - t_other) / h
        if abs(target - t_w) < _WALL_TOL_K:
            return h, target
        t_w = 0.5 * (t_w + target)
    raise RatingConvergenceError(f"wall-temperature fixed point did not converge at T_sat = {t_sat} K")


def latent_heat_J_kg(thermo: Thermo, z: dict[str, float], p: float) -> float:
    """h_fg, the vapour at the dew point less the liquid at the bubble point, per kg.

    From ``phase_props``, which names the phase and runs no split.  Not ``flash_pvf``: on
    the cubic packages it ignores vf for a pure component and returns the bubble liquid at
    both ends, which reads as a zero latent heat.
    """
    vapour = thermo.phase_props(z, float(thermo.dew_point(z, P=p).T), p, PhaseKind.VAPOR)
    liquid = thermo.phase_props(z, float(thermo.bubble_point(z, P=p).T), p, PhaseKind.HC_LIQUID)
    latent = float((vapour.enthalpy - liquid.enthalpy) * 1000.0 / liquid.molecular_weight)
    if latent <= 0.0:
        raise RatingError(f"latent heat {latent} J/kg at P = {p} Pa is not positive")
    return latent


@dataclass(frozen=True)
class _Side:
    """One stream of the exchanger with its place in the geometry."""

    inlet: StreamState
    p_out: float
    is_tube: bool
    is_hot: bool


def _phase(state: StreamState, vapour: bool) -> Any:
    wanted = [p for p in state.phases if (p.kind is PhaseKind.VAPOR) == vapour]
    return max(wanted, key=lambda p: p.mole_fraction)


def _mass_quality(state: StreamState) -> float:
    vapour = _phase(state, True)
    mass = sum(p.mole_fraction * p.molecular_weight for p in state.phases)
    return float(vapour.mole_fraction * vapour.molecular_weight / mass)


class ShellTubeR2:
    """Zoned shell-and-tube rating with phase change and the F check, level R2."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        geom = geometry(params)
        n_zones = int(params.get("n_zones", 20))
        if not 1 <= n_zones <= 200:
            raise ValueError(f"n_zones {n_zones} outside 1-200")
        f_min = float(params.get("F_min", 0.75))
        rows = params.get("tube_rows_vertical")
        process = inlets["inlet"]
        utility = thermo.flash_pt(
            geom.utility_composition, geom.utility_T_K, geom.utility_P_Pa, geom.utility_molar_flow
        )
        if abs(process.T - utility.T) <= 1e-9:
            raise TemperatureCross(f"inlet temperatures are equal at T = {process.T} K: no driving force")
        for side_name, state in (("process", process), ("utility", utility)):
            try:
                inlet_kind(state)
            except SinglePhaseRequired as exc:
                raise SinglePhaseRequired(
                    f"{exc} ({side_name} inlet); the pressure drops need a single-phase inlet"
                ) from exc

        tube_state, shell_state = (process, utility) if geom.process_side == "tube" else (utility, process)
        dp_tube, dp_shell = _pressure_drops(geom, tube_state, shell_state, thermo)
        hot_state, cold_state = (process, utility) if process.T > utility.T else (utility, process)
        hot = _Side(
            hot_state,
            hot_state.P - (dp_tube if hot_state is tube_state else dp_shell),
            hot_state is tube_state,
            True,
        )
        cold = _Side(
            cold_state,
            cold_state.P - (dp_tube if cold_state is tube_state else dp_shell),
            cold_state is tube_state,
            False,
        )
        if min(hot.p_out, cold.p_out) <= 0.0:
            raise RatingError("non-positive outlet pressure across this geometry")

        area = geom.n_tubes * math.pi * geom.tube_OD_m * geom.tube_length_m
        q_max = min(
            hot_state.molar_flow
            * (
                hot_state.enthalpy
                - thermo.flash_pt(hot_state.composition, cold_state.T, hot.p_out, 1.0).enthalpy
            ),
            cold_state.molar_flow
            * (
                thermo.flash_pt(cold_state.composition, hot_state.T, cold.p_out, 1.0).enthalpy
                - cold_state.enthalpy
            ),
        )
        rater = _Rater(geom, hot, cold, n_zones, rows, thermo)

        q_star = self._rated_duty(rater, area, q_max)
        needed, zones = rater.area_required(q_star)
        hot_out, cold_out = zones.hot_out, zones.cold_out

        f_value = zones.f
        shells_required = 0.0
        if geom.tube_passes >= 2:
            shells_required = _shells_required(hot_state.T, hot_out.T, cold_state.T, cold_out.T, f_min)
            if not math.isfinite(f_value) or f_value < f_min:
                raise TemperatureCross(
                    f"F = {f_value} is below F_min {f_min} at the rated duty: temperature cross; "
                    f"shells_required = {shells_required:g}"
                )

        process_out = hot_out if process is hot_state else cold_out
        utility_out = cold_out if process is hot_state else hot_out
        info: dict[str, float] = {
            "Q_W": q_star,
            "A_m2": area,
            "A_required_m2": needed,
            "U_W_m2K": q_star / (f_value * zones.sum_q_over_lmtd_u_inverse),
            "F_LMTD": f_value,
            "LMTD_K": lmtd_counter(hot_state.T, hot_out.T, cold_state.T, cold_out.T),
            "dP_tube_Pa": dp_tube,
            "dP_shell_Pa": dp_shell,
            "utility_T_out_K": utility_out.T,
            "utility_P_out_Pa": utility_out.P,
            "utility_duty_W": q_star,
            "n_zones": float(n_zones),
            "shells_required": shells_required,
            "min_zone_dT_K": zones.min_dt,
            "zone_U_min_W_m2K": zones.u_min,
            "zone_U_max_W_m2K": zones.u_max,
            # Zones carry equal duty, so the plain mean is the duty-weighted mean film.
            "h_tube_mean_W_m2K": sum(zones.h_tube) / len(zones.h_tube),
            "h_shell_mean_W_m2K": sum(zones.h_shell) / len(zones.h_shell),
        }
        for k, (h_t, h_s) in enumerate(zip(zones.h_tube, zones.h_shell, strict=True)):
            info[f"zone_{k:02d}_h_tube_W_m2K"] = h_t
            info[f"zone_{k:02d}_h_shell_W_m2K"] = h_s
        duty = process.molar_flow * (process_out.enthalpy - process.enthalpy)
        return UnitResult(outlets={"outlet": process_out}, duty_W=duty, power_W=0.0, info=info)

    @staticmethod
    def _rated_duty(rater: _Rater, area: float, q_max: float) -> float:
        """The duty whose required area is the exchanger's.

        Required area rises with Q, and a duty that crosses needs more than any area, so
        an infeasible trial reads as too much duty.  Bisection stops at the first feasible
        duty above the root; the bracket then goes to brentq.  If no feasible duty needs
        the whole area, the unit is pinched, and the largest feasible duty is the rating.
        """

        def excess(q: float) -> float:
            return rater.area_required(q)[0] - area

        lo, hi = 1.0e-6 * q_max, q_max
        for trial in range(_FEASIBLE_BISECTIONS):
            q = hi if trial == 0 else 0.5 * (lo + hi)
            try:
                over = excess(q)
            except _Infeasible:
                hi = q
                continue
            if over > 0.0:
                hi = q
                break
            lo = q
            if trial == 0:
                return q  # even Q_max does not need the whole area
        else:
            return lo
        try:
            return float(brentq(excess, lo, hi, xtol=1.0e-10 * q_max, maxiter=100))
        except (RuntimeError, ValueError) as exc:
            raise RatingConvergenceError(f"zone rating did not converge: {exc}") from exc

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A C3/nC4 vapour condensed on the shell by cooling water in the tubes.

        A shortened G1 from the R1 example; the feed, utility, tube count and N_r are
        illustrative test inputs, not defaults.
        """
        feed = {"T": 355.0, "P": 1.2e6, "molar_flow": 8.0, "composition": {"C3": 0.5, "nC4": 0.5}}
        params: dict[str, Any] = {
            "process_side": "shell",
            "shell_ID_m": 0.489,
            "n_tubes": 60,
            "tube_OD_m": 0.01905,
            "tube_ID_m": 0.01483,
            "tube_length_m": 2.0,
            "pitch_m": 0.02381,
            "layout": "triangular30",
            "baffle_spacing_m": 0.3048,
            "n_baffles": 15,
            "tube_passes": 2,
            "utility_composition": {"H2O": 1.0},
            "utility_T_K": 303.15,
            "utility_P_Pa": 4.0e5,
            "utility_molar_flow": 1000.0,
            "tube_rows_vertical": 10,
            "n_zones": 8,
        }
        return {"inlet": feed}, params


def _pressure_drops(
    geom: ShellGeometry, tube_state: StreamState, shell_state: StreamState, thermo: Thermo
) -> tuple[float, float]:
    """R1's pressure drops, from inlet-state properties."""
    film_t = film_props(thermo, tube_state.composition, tube_state.T, tube_state.P, inlet_kind(tube_state))
    film_s = film_props(
        thermo, shell_state.composition, shell_state.T, shell_state.P, inlet_kind(shell_state)
    )
    tube = tube_duct(
        tube_state.mass_flow, geom.n_tubes, geom.tube_passes, geom.tube_ID_m, film_t, geom.roughness_m
    )
    de = equiv_diameter(geom.pitch_m, geom.tube_OD_m, geom.layout)
    gs = shell_state.mass_flow / shell_flow_area(
        geom.shell_ID_m, geom.pitch_m, geom.tube_OD_m, geom.baffle_spacing_m
    )
    f = shell_friction(de * gs / film_s.mu_Pa_s)
    return (
        tube_dP(tube.fd, geom.tube_passes, geom.tube_length_m, geom.tube_ID_m, film_t.rho_kg_m3, tube.v_m_s),
        shell_dP(f, gs, geom.n_baffles, geom.shell_ID_m, film_s.rho_kg_m3, de),
    )


def _f_factor(thi: float, tho: float, tci: float, tco: float, shells: int) -> float:
    """Fakheri's F, or nan where the arrangement has none."""
    try:
        return float(ht.F_LMTD_Fakheri(thi, tho, tci, tco, shells=shells))  # type: ignore[arg-type]
    except (ValueError, ZeroDivisionError):
        return math.nan


def _shells_required(thi: float, tho: float, tci: float, tco: float, f_min: float) -> float:
    """The smallest shell count up to 10 reaching F_min (0 if none does)."""
    for n in range(1, 11):
        f = _f_factor(thi, tho, tci, tco, n)
        if math.isfinite(f) and f >= f_min:
            return float(n)
    return 0.0


@dataclass(frozen=True)
class _Zones:
    """One trial duty's zone sums."""

    hot_out: StreamState
    cold_out: StreamState
    f: float
    sum_q_over_lmtd_u_inverse: float
    min_dt: float
    u_min: float
    u_max: float
    #: Per-zone film coefficients (W/m2/K), zone 0 at the hot inlet: tube side
    #: on the inside-area basis, shell side on the outside-area basis.
    h_tube: tuple[float, ...] = ()
    h_shell: tuple[float, ...] = ()


class _Rater:
    """Zone sums at a trial duty (spec equations and regime table)."""

    def __init__(
        self,
        geom: ShellGeometry,
        hot: _Side,
        cold: _Side,
        n_zones: int,
        rows: Any,
        thermo: Thermo,
    ) -> None:
        self.geom, self.hot, self.cold, self.n, self.rows, self.thermo = (
            geom,
            hot,
            cold,
            n_zones,
            rows,
            thermo,
        )
        self.a_s = shell_flow_area(geom.shell_ID_m, geom.pitch_m, geom.tube_OD_m, geom.baffle_spacing_m)
        self.de = equiv_diameter(geom.pitch_m, geom.tube_OD_m, geom.layout)
        ids = list(cold.inlet.composition) + list(hot.inlet.composition)
        self.db = {cid: components()[cid] for cid in ids}

    def _outlet(self, side: _Side, q: float) -> StreamState:
        flow = float(side.inlet.molar_flow)
        h = side.inlet.enthalpy + (-q if side.is_hot else q) / flow
        return self.thermo.flash_ph(dict(side.inlet.composition), side.p_out, h, flow)

    def _boundaries(self, side: _Side, q: float) -> list[StreamState]:
        """States from each stream's inlet to its outlet, equal duty per zone."""
        inlet = side.inlet
        flow = float(inlet.molar_flow)
        sign = -1.0 if side.is_hot else 1.0
        states = []
        for k in range(self.n + 1):
            frac = k / self.n
            p = inlet.P + (side.p_out - inlet.P) * frac
            h = inlet.enthalpy + sign * q * frac / flow
            states.append(self.thermo.flash_ph(dict(inlet.composition), p, h, flow))
        return states

    def area_required(self, q: float) -> tuple[float, _Zones]:
        """Sum_k A_k/F at duty q; raises _Infeasible on a cross or a missing F."""
        # The terminal states alone decide F and the end crosses: two flashes, not a sweep.
        hot_out = self._outlet(self.hot, q)
        cold_out = self._outlet(self.cold, q)
        if hot_out.T <= self.cold.inlet.T or self.hot.inlet.T <= cold_out.T:
            raise _Infeasible
        f = 1.0
        if self.geom.tube_passes >= 2:
            f = _f_factor(self.hot.inlet.T, hot_out.T, self.cold.inlet.T, cold_out.T, self.geom.n_shells)
            if not math.isfinite(f) or f <= 0.0:
                raise _Infeasible
        hot_states = self._boundaries(self.hot, q)
        cold_states = self._boundaries(self.cold, q)[::-1]  # counter-current pairing
        area = 0.0
        q_over_lmtd_u = 0.0
        min_dt = math.inf
        u_min, u_max = math.inf, 0.0
        h_tube: list[float] = []
        h_shell: list[float] = []
        for k in range(self.n):
            hot_a, hot_b = hot_states[k], hot_states[k + 1]
            cold_a, cold_b = cold_states[k], cold_states[k + 1]
            dt1, dt2 = hot_a.T - cold_a.T, hot_b.T - cold_b.T
            if dt1 <= 0.0 or dt2 <= 0.0:
                raise _Infeasible
            u, h_t, h_s = self._zone_u(hot_a, hot_b, cold_a, cold_b)
            h_tube.append(h_t)
            h_shell.append(h_s)
            lmtd = lmtd_counter(hot_a.T, hot_b.T, cold_b.T, cold_a.T)
            area += (q / self.n) / (u * lmtd)
            q_over_lmtd_u += (q / self.n) / lmtd
            min_dt = min(min_dt, dt1, dt2)
            u_min, u_max = min(u_min, u), max(u_max, u)
        zones = _Zones(
            hot_out, cold_out, f, q_over_lmtd_u, min_dt, u_min, u_max, tuple(h_tube), tuple(h_shell)
        )
        return area / f, zones

    def _mean_state(self, a: StreamState, b: StreamState, side: _Side) -> StreamState:
        """The zone-mean state: the mean enthalpy, at the mean pressure."""
        h = 0.5 * (a.enthalpy + b.enthalpy)
        return self.thermo.flash_ph(dict(side.inlet.composition), 0.5 * (a.P + b.P), h, float(a.molar_flow))

    def _single_h(self, side: _Side, z: dict[str, float], t: float, p: float, kind: PhaseKind) -> float:
        film = film_props(self.thermo, z, t, p, kind)
        g = self.geom
        if side.is_tube:
            return tube_duct(
                side.inlet.mass_flow, g.n_tubes, g.tube_passes, g.tube_ID_m, film, g.roughness_m
            ).h_W_m2K
        re_s = self.de * (side.inlet.mass_flow / self.a_s) / film.mu_Pa_s
        return shell_h(film.k_W_mK, self.de, re_s, film.Pr)

    def _liquid_film(self, state: StreamState) -> FilmProps:
        liquid = _phase(state, False)
        return film_props(self.thermo, dict(liquid.composition), state.T, state.P, liquid.kind)

    def _latent_J_kg(self, side: _Side, p: float) -> float:
        return latent_heat_J_kg(self.thermo, dict(side.inlet.composition), p)

    def _pc(self, state: StreamState) -> float:
        return math.fsum(x * float(self.db[cid]["pc_Pa"]) for cid, x in state.composition.items())

    def _two_phase_h(self, side: _Side, mean: StreamState, u_of: Any, t_other: float) -> float:
        g = self.geom
        film = self._liquid_film(mean)
        vapour = _phase(mean, True)
        x = _mass_quality(mean)
        per_tube = side.inlet.mass_flow / (g.n_tubes / g.tube_passes)
        if side.is_hot and not side.is_tube:
            if self.rows is None:
                raise RatingError("tube_rows_vertical is required for shell-side condensation")
            n_rows = int(self.rows)
            if n_rows < 1:
                raise RatingError("tube_rows_vertical must be >= 1")
            h_fg = self._latent_J_kg(side, mean.P)

            def condensing(t_w: float) -> float:
                return nusselt_bank_h(
                    film.rho_kg_m3,
                    vapour.density,
                    film.k_W_mK,
                    film.mu_Pa_s,
                    film.cp_J_kgK,
                    h_fg,
                    mean.T,
                    t_w,
                    g.tube_OD_m,
                    n_rows,
                )

            return fixed_point_wall(condensing, mean.T, t_other, u_of)[0]
        if side.is_hot:
            return float(
                ht.Shah(
                    per_tube,
                    x,
                    g.tube_ID_m,
                    film.rho_kg_m3,
                    film.mu_Pa_s,
                    film.k_W_mK,
                    film.cp_J_kgK,
                    mean.P,
                    self._pc(mean),
                )
            )
        if not side.is_tube:
            raise PhaseRegimeNotRated("shell-side boiling (kettle/thermosiphon) is not rated at R2")
        mw = _phase(mean, False).molecular_weight

        def boiling(t_w: float) -> float:
            return float(
                ht.Liu_Winterton(
                    per_tube,
                    x,
                    g.tube_ID_m,
                    film.rho_kg_m3,
                    vapour.density,
                    film.mu_Pa_s,
                    film.k_W_mK,
                    film.cp_J_kgK,
                    mw,
                    mean.P,
                    self._pc(mean),
                    max(t_w - mean.T, 1.0e-3),
                )
            )

        return fixed_point_wall(boiling, mean.T, t_other, u_of)[0]

    def _zone_u(
        self, hot_a: StreamState, hot_b: StreamState, cold_a: StreamState, cold_b: StreamState
    ) -> tuple[float, float, float]:
        """Zone U with its (tube, shell) film coefficients."""
        g = self.geom

        def films(h_hot: float, h_cold: float) -> tuple[float, float, float]:
            h_t, h_s = (h_hot, h_cold) if self.hot.is_tube else (h_cold, h_hot)
            return overall(h_hot, h_cold), h_t, h_s

        def overall(h_hot: float, h_cold: float) -> float:
            h_t, h_s = (h_hot, h_cold) if self.hot.is_tube else (h_cold, h_hot)
            return u_outside_tube(
                h_i=h_t,
                h_o=h_s,
                Do=g.tube_OD_m,
                Di=g.tube_ID_m,
                k_wall=g.k_wall_W_mK,
                R_fi=g.R_f_tube_m2K_W,
                R_fo=g.R_f_shell_m2K_W,
            )

        def single(side: _Side, a: StreamState, b: StreamState) -> tuple[float | None, StreamState | None]:
            """The single-phase h at the mean of the end T, or the two-phase zone-mean state.

            Both ends in one same phase need no flash; otherwise the mean state decides.
            """
            one = len(a.phases) == 1 and len(b.phases) == 1 and a.phases[0].kind is b.phases[0].kind
            mean = None if one else self._mean_state(a, b, side)
            if mean is not None and len(mean.phases) != 1:
                return None, mean
            kind = a.phases[0].kind if mean is None else mean.phases[0].kind
            t, p = 0.5 * (a.T + b.T), 0.5 * (a.P + b.P)
            return self._single_h(side, dict(side.inlet.composition), t, p, kind), None

        h_hot, hot_mean = single(self.hot, hot_a, hot_b)
        h_cold, cold_mean = single(self.cold, cold_a, cold_b)
        if h_hot is not None and h_cold is not None:
            return films(h_hot, h_cold)
        if h_hot is None and h_cold is None:
            raise PhaseRegimeNotRated("both sides change phase in one zone: not rated at R2")
        if h_cold is not None:
            assert hot_mean is not None
            known_cold = h_cold
            t_cold = 0.5 * (cold_a.T + cold_b.T)
            hot_two = self._two_phase_h(self.hot, hot_mean, lambda h: overall(h, known_cold), t_cold)
            return films(hot_two, known_cold)
        assert h_hot is not None and cold_mean is not None
        known_hot = h_hot
        t_hot = 0.5 * (hot_a.T + hot_b.T)
        cold_two = self._two_phase_h(self.cold, cold_mean, lambda h: overall(known_hot, h), t_hot)
        return films(known_hot, cold_two)
