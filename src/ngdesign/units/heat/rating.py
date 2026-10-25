"""Shared single-phase rating core for the heat-family R1 units (spec U-R2).

Owned by the double_pipe R1 thread (issue #266); shell_tube, plate_exchanger
and air_cooler run after it and import from this module read-only. No
unit-specific logic lives here: the unit supplies the geometry, the
``ua_of``/``eps_of`` closures and the port wiring; this module owns the
duct-flow correlations, the wall resistance, and the counter-current
epsilon-NTU duty solve on top of the :class:`~ngdesign.contracts.plugins.Thermo`
protocol (SI: K, Pa, mol/s, J/mol, W).

Method (double_pipe R1 spec, "Equations"):
1. Film properties at each side's bulk mean state, in the inlet's single
   phase kind; ``cp_mass = cp/(MW/1000)``, ``Pr = cp_mass*mu/k``.
2. Duct flow: ``v = m/(rho*A_flow)``, ``Re = rho*v*D_h/mu`` with the hydraulic
   diameter (Incropera et al., Fundamentals of Heat and Mass Transfer, 7th ed.,
   section 8.7). The Gnielinski 2009 annulus correction is deliberately
   omitted.
3. Darcy friction: ``f_D = 64/Re`` for Re < 2300 (Incropera eq. 8.19);
   otherwise the Colebrook root (Colebrook 1939; Incropera eq. 8.20) through
   ``fluids.friction_factor`` (Clamond method, machine precision).
4. Nusselt: ``Nu = 3.66`` for Re < 2300 (fully developed laminar, constant
   wall temperature; Incropera eq. 8.55); otherwise Gnielinski (Gnielinski
   1976; Incropera eq. 8.62) through ``ht.turbulent_Gnielinski`` with the
   DARCY friction factor. ``h = Nu*k/D_h``.
5. Overall U referenced to the inner tube's outside area (Incropera eq. 11.5
   with the fouling terms of Table 11.1's convention).
7. Pressure drop per side from INLET-state properties (Darcy-Weisbach) - kept
   explicit, with no deltaP-property loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

import fluids
import ht
from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross

#: Laminar/turbulent transition for both correlations (no blend between them).
TURBULENT_RE = 2300.0

#: Fully developed laminar Nusselt number, constant wall temperature
#: (Incropera eq. 8.55).
LAMINAR_NU = 3.66

#: The solver's lower duty bracket as a fraction of Q_max.
Q_LO_FRACTION = 1e-6

#: brentq absolute tolerance as a fraction of Q_max.
BRENTQ_XTOL_FRACTION = 1e-12

#: brentq iteration cap.
BRENTQ_MAXITER = 100


class RatingError(ValueError):
    """A rating the method cannot run; the refusal names the parameter."""


class SinglePhaseRequired(RatingError):
    """R1 rates single-phase duty only; the two-phase side is named."""


class PropertyUnavailable(RatingError):
    """The thermo package returned no viscosity or thermal conductivity."""


class RatingConvergenceError(RatingError):
    """The duty solve did not converge; the last Q and bracket are named."""


@dataclass(frozen=True)
class FilmProps:
    """Bulk film properties of one side, mass-specific cp (J/(kg K))."""

    rho_kg_m3: float
    mu_Pa_s: float
    k_W_mK: float
    cp_J_kgK: float

    @property
    def Pr(self) -> float:
        """Prandtl number, ``cp_mass*mu/k``."""
        return self.cp_J_kgK * self.mu_Pa_s / self.k_W_mK


def film_props(
    thermo: Thermo, z: dict[str, float], T: float, P: float, kind: PhaseKind
) -> FilmProps:
    """Film properties of one single phase at (composition, T, P).

    Raises:
        PropertyUnavailable: ``phase_props`` returned ``viscosity`` or
            ``thermal_conductivity`` as ``None`` (the property, the
            composition and the package are named).
    """
    props = thermo.phase_props(z, T, P, kind)
    missing = [
        name
        for name, value in (
            ("viscosity", props.viscosity),
            ("thermal_conductivity", props.thermal_conductivity),
        )
        if value is None
    ]
    if missing:
        package = type(thermo).__name__
        raise PropertyUnavailable(
            f"thermo package {package} returned no {missing[0]} for "
            f"{'+'.join(sorted(z))} at T={T} K, P={P} Pa ({kind.value}); "
            "R1 rating needs viscosity and thermal_conductivity"
        )
    cp_mass = props.cp / (props.molecular_weight / 1000.0)  # J/(kg K)
    return FilmProps(
        rho_kg_m3=props.density,
        mu_Pa_s=float(props.viscosity),  # type: ignore[arg-type]  # not None above
        k_W_mK=float(props.thermal_conductivity),  # type: ignore[arg-type]
        cp_J_kgK=cp_mass,
    )


def inlet_kind(state: StreamState) -> PhaseKind:
    """The single phase of a single-phase inlet state.

    Raises:
        SinglePhaseRequired: the state does not have exactly one phase.
    """
    n_phases = len(state.phases)
    if n_phases != 1:
        raise SinglePhaseRequired(
            f"R1 rates single-phase duty: the state has {n_phases} phases, exactly 1 required"
        )
    return state.phases[0].kind


def darcy_friction(Re: float, eD: float = 0.0) -> float:
    """Darcy friction factor.

    ``64/Re`` for Re < 2300 (Incropera eq. 8.19); otherwise the Colebrook root
    (Colebrook 1939; Incropera eq. 8.20) through ``fluids.friction_factor``
    (Clamond method, which solves Colebrook to machine precision).
    """
    if Re < TURBULENT_RE:
        return 64.0 / Re
    return float(fluids.friction_factor(Re, eD=eD, Darcy=True))


def nu_tube(Re: float, Pr: float, fd: float) -> float:
    """Nusselt number in a duct.

    3.66 for Re < 2300 (fully developed laminar, constant wall temperature;
    Incropera eq. 8.55); otherwise Gnielinski (Gnielinski 1976; Incropera
    eq. 8.62), called with the DARCY friction factor.
    """
    if Re < TURBULENT_RE:
        return LAMINAR_NU
    return float(ht.turbulent_Gnielinski(Re, Pr, fd))


@dataclass(frozen=True)
class DuctResult:
    """One duct's flow, friction and film coefficient."""

    h_W_m2K: float
    Re: float
    v_m_s: float
    fd: float


def duct_h(
    m_kg_s: float, flow_area_m2: float, Dh_m: float, props: FilmProps, roughness_m: float
) -> DuctResult:
    """Film coefficient in a duct of hydraulic diameter ``Dh_m``.

    ``v = m/(rho*A)``, ``Re = rho*v*Dh/mu``, then the friction and Nusselt
    correlations above and ``h = Nu*k/Dh``. For an annulus ``Dh`` is the
    hydraulic diameter (Incropera 7th ed. section 8.7); the Gnielinski 2009
    annulus correction is deliberately omitted.
    """
    v = m_kg_s / (props.rho_kg_m3 * flow_area_m2)
    Re = props.rho_kg_m3 * v * Dh_m / props.mu_Pa_s
    fd = darcy_friction(Re, roughness_m / Dh_m)
    Nu = nu_tube(Re, props.Pr, fd)
    return DuctResult(h_W_m2K=Nu * props.k_W_mK / Dh_m, Re=Re, v_m_s=v, fd=fd)


def darcy_dP(fd: float, L_m: float, Dh_m: float, rho: float, v: float) -> float:
    """Darcy-Weisbach pressure drop, ``f*(L/Dh)*rho*v^2/2``."""
    return fd * (L_m / Dh_m) * rho * v * v / 2.0


def u_outside_tube(
    h_i: float, h_o: float, Do: float, Di: float, k_wall: float, R_fi: float, R_fo: float
) -> float:
    """Overall U referenced to the tube's OUTSIDE area (Incropera eq. 11.5).

    ``1/U_o = 1/h_o + R_fo + Do*ln(Do/Di)/(2*k_wall) + R_fi*Do/Di + Do/(Di*h_i)``,
    the fouling terms following Table 11.1's convention (R_fi is an inside
    resistance referred to the inside area, R_fo an outside one).
    """
    resistance = (
        1.0 / h_o
        + R_fo
        + Do * math.log(Do / Di) / (2.0 * k_wall)
        + R_fi * Do / Di
        + Do / (Di * h_i)
    )
    return 1.0 / resistance


@dataclass(frozen=True)
class RatedTwoStream:
    """The converged two-stream rating: outlets plus the epsilon-NTU scalars."""

    hot_out: StreamState
    cold_out: StreamState
    duty_W: float
    UA_W_K: float
    NTU: float
    effectiveness: float
    iterations: int


def rate_two_stream(
    hot: StreamState,
    cold: StreamState,
    thermo: Thermo,
    P_h_out: float,
    P_c_out: float,
    ua_of: Callable[[StreamState, StreamState], float],
    eps_of: Callable[[float, float], float],
) -> RatedTwoStream:
    """Rate a two-stream exchanger by counter-current epsilon-NTU on enthalpies.

    Solves ``g(Q) = Q - eps(NTU, Cr)*C_min*(T_h_in - T_c_in)`` with ``brentq``
    on ``[1e-6*Q_max, Q_max]`` (``xtol = 1e-12*Q_max``, ``maxiter = 100``).
    The heat-capacity rates come from the actual enthalpy change,
    ``C = Q/(T_in - T_out)`` (as Q -> 0, the inlet ``F*cp_mass*MW/1000``), so
    they are not constant-cp approximations. Outlets are ``flash_ph`` at
    ``P_out`` and the duty-shifted enthalpies, and each outlet must stay in
    its inlet's phase.

    Args:
        ua_of: ``UA(W/K)`` at the current outlet pair, from the unit's own
            film-coefficient and area model.
        eps_of: ``effectiveness(NTU, Cr)`` for the unit's flow arrangement.

    Raises:
        RatingError: a side has zero flow ("needs both streams flowing").
        TemperatureCross: ``T_h_in <= T_c_in``.
        SinglePhaseRequired: an inlet or an outlet is not single phase.
        RatingConvergenceError: ``brentq`` failed or did not converge.
    """
    F_h, F_c = hot.molar_flow, cold.molar_flow
    if F_h <= 0.0 or F_c <= 0.0:
        raise RatingError(
            "R1 rating needs both streams flowing: got hot="
            f"{F_h} mol/s, cold={F_c} mol/s"
        )
    if hot.T <= cold.T:
        raise TemperatureCross(
            f"inlet temperatures cross: hot T={hot.T} K <= cold T={cold.T} K"
        )
    kind_h = _inlet_kind(hot, "hot")
    kind_c = _inlet_kind(cold, "cold")
    film_h = film_props(thermo, hot.composition, hot.T, hot.P, kind_h)
    film_c = film_props(thermo, cold.composition, cold.T, cold.P, kind_c)
    # F*cp_mass*MW/1000 at the inlet, the Q -> 0 heat-capacity rate (Eq. 6):
    # mass_flow/F is the molar mass in kg/mol.
    C_h_zero = F_h * film_h.cp_J_kgK * (hot.mass_flow / F_h)
    C_c_zero = F_c * film_c.cp_J_kgK * (cold.mass_flow / F_c)

    h_h_cold_end = thermo.flash_pt(hot.composition, cold.T, P_h_out, F_h).enthalpy
    h_c_hot_end = thermo.flash_pt(cold.composition, hot.T, P_c_out, F_c).enthalpy
    Q_max = min(F_h * (hot.enthalpy - h_h_cold_end), F_c * (h_c_hot_end - cold.enthalpy))

    def evaluate(Q: float) -> tuple[float, StreamState, StreamState, float, float, float]:
        """Residual, outlets and the UA/NTU/eps triple at duty Q."""
        hot_out = thermo.flash_ph(hot.composition, P_h_out, hot.enthalpy - Q / F_h, F_h)
        cold_out = thermo.flash_ph(cold.composition, P_c_out, cold.enthalpy + Q / F_c, F_c)
        for side, inlet, out in (("hot", hot, hot_out), ("cold", cold, cold_out)):
            if len(out.phases) != 1 or abs(out.vapor_fraction - inlet.vapor_fraction) > 1e-6:
                raise SinglePhaseRequired(
                    f"R1 rates single-phase duty: {side} outlet leaves the inlet's phase "
                    f"(vapor fraction {out.vapor_fraction} vs inlet {inlet.vapor_fraction}) at Q={Q} W"
                )
        UA = ua_of(hot_out, cold_out)
        # C from the enthalpy change (Eq. 6); the cp fallback covers Q -> 0.
        dT_h = hot.T - hot_out.T
        dT_c = cold_out.T - cold.T
        C_h = Q / dT_h if dT_h > 0.0 else C_h_zero
        C_c = Q / dT_c if dT_c > 0.0 else C_c_zero
        C_min, C_max = min(C_h, C_c), max(C_h, C_c)
        Cr = C_min / C_max
        NTU = UA / C_min
        eps = eps_of(NTU, Cr)
        g = Q - eps * C_min * (hot.T - cold.T)
        return g, hot_out, cold_out, UA, NTU, eps

    g_max, hot_max, cold_max, UA_max, NTU_max, eps_max = evaluate(Q_max)
    if g_max <= 0.0:  # round-off: Q_max already reaches the epsilon-NTU duty
        return RatedTwoStream(hot_max, cold_max, Q_max, UA_max, NTU_max, eps_max, 0)

    Q_lo = Q_LO_FRACTION * Q_max
    try:
        Q, r = brentq(
            lambda q: evaluate(q)[0],
            Q_lo,
            Q_max,
            xtol=BRENTQ_XTOL_FRACTION * Q_max,
            maxiter=BRENTQ_MAXITER,
            full_output=True,
        )
    except (RuntimeError, ValueError) as exc:
        raise RatingConvergenceError(
            f"rating did not converge: {exc}; last duty bracket [{Q_lo}, {Q_max}] W, "
            f"g(Q_max)={g_max} W"
        ) from exc
    _, hot_out, cold_out, UA, NTU, eps = evaluate(float(Q))
    return RatedTwoStream(hot_out, cold_out, float(Q), UA, NTU, eps, r.iterations)


def _inlet_kind(state: StreamState, side: str) -> PhaseKind:
    """``inlet_kind`` with the side named in the refusal."""
    try:
        return inlet_kind(state)
    except SinglePhaseRequired as exc:
        raise SinglePhaseRequired(f"{exc} ({side} inlet)") from exc
