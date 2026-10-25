"""Pipe segment, levels R1 and R2 (spec specs/backend/units/pipe_segment.md).

R1 -- single-phase Darcy-Colebrook marching with elevation. The steady 1-D
momentum balance (acceleration neglected) is

    dP/dx = -f/D * G^2/(2 rho(P)) - rho(P) * g * sin(theta),

with mass flux G = mdot/A, A = pi*D^2/4, sin(theta) = dz/L for a straight
segment of uniform slope, and f the Darcy friction factor from Colebrook
(1939) -- both f and Re come from the repo's single owner of single-phase
friction, :func:`ngdesign.sizing.line_friction.darcy_colebrook` (f = 64/Re
below Re 2300, Colebrook above). Fittings use the Crane TP-410 K method,
``dP_K = sum(K) * G^2/(2 rho_in)``, applied at the inlet. The march is
Heun's method (explicit trapezoid) over N equal segments, refined by
doubling N until the outlet changes by less than 1e-6 of the total drop.

Each node is adiabatic and isenthalpic: the state at pressure P is a PH
flash at the inlet enthalpy. Potential and kinetic energy are not booked
into the enthalpy balance (as at R0), so the V0 balance closes exactly; the
neglected term is g*dz, about 0.1 kJ/kg per 10 m of elevation.

R2 -- two-phase Beggs-Brill with a profile along the length, built on this
module's marcher: on segments whose node is two-phase the step's dP comes
from ``fluids.two_phase.Beggs_Brill`` (original 1973 holdup with the
Brill-Beggs transition interpolation, Moody/Clamond friction factor with
roughness, and **no Payne correction** -- the holdup and friction
corrections of Payne et al. are not applied), single-phase segments use the
R1 Darcy step, and the integration is the same Heun predictor-corrector at
a fixed N (no auto-refinement: regime switches make the refinement norm
non-smooth; the N/2 discretisation check is reported instead).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.line_friction import darcy_colebrook
from ngdesign.units.flow.pipe_segment import G_STD, PipeSegmentSpecError

#: Callable returning (density, viscosity) at a pressure, Pa and Pa.s.
PropsFn = Callable[[float], tuple[float, float]]

#: Refinement cap on the segment count (spec: raise past N = 1024).
MAX_SEGMENTS = 1024

#: Refinement tolerance: |P_out(N) - P_out(N/2)| <= this * |P_in - P_out(N)|.
REFINE_RTOL = 1.0e-6


class PipeSegmentR1Error(PipeSegmentSpecError):
    """Typed refusal for an R1 pipe-segment spec outside the level's validity."""


def node_terms(
    rho: float, mu: float, mdot: float, D_m: float, roughness_m: float, sin_theta: float
) -> tuple[float, float]:
    """Friction and gravity pressure-drop gradients (Pa/m, both positive for a drop).

    Friction is ``f/D * G^2/(2 rho)`` with f from ``darcy_colebrook`` (called
    per metre of length so its ``dP_Pa`` is the gradient directly); gravity is
    ``rho * g * sin(theta)``.
    """
    r = darcy_colebrook(
        Q_m3_s=mdot / rho,
        D_m=D_m,
        rho=rho,
        mu=mu,
        roughness_m=roughness_m,
        L_m=1.0,
    )
    return r["dP_Pa"], rho * G_STD * sin_theta


def _march_terms(
    P_in: float,
    L: float,
    D: float,
    dz: float,
    eps: float,
    mdot: float,
    props: PropsFn,
    n: int,
) -> tuple[float, float, float]:
    """One Heun march of n segments; returns (P_out, dP_friction, dP_hydrostatic)."""
    if L <= 0:
        raise PipeSegmentSpecError(f"L_m {L} m must be > 0")
    if D <= 0:
        raise PipeSegmentSpecError(f"D_m {D} m must be > 0")
    if eps < 0:
        raise PipeSegmentSpecError(f"roughness_m {eps} m must be >= 0")
    if n < 1:
        raise PipeSegmentSpecError(f"n_segments {n} must be >= 1")

    sin_theta = dz / L
    h = L / n
    P = P_in
    dP_friction = 0.0
    dP_hydro = 0.0
    for _ in range(n):
        rho_1, mu_1 = props(P)
        fric_1, grav_1 = node_terms(rho_1, mu_1, mdot, D, eps, sin_theta)
        k1 = -(fric_1 + grav_1)
        P_star = P + h * k1
        if P_star <= 0:
            raise PipeSegmentR1Error(f"pressure falls to zero along the segment (predictor {P_star} Pa)")
        rho_2, mu_2 = props(P_star)
        fric_2, grav_2 = node_terms(rho_2, mu_2, mdot, D, eps, sin_theta)
        k2 = -(fric_2 + grav_2)
        P = P + h * (k1 + k2) / 2
        if P <= 0:
            raise PipeSegmentR1Error(f"pressure falls to zero along the segment (corrector {P} Pa)")
        dP_friction += h * (fric_1 + fric_2) / 2
        dP_hydro += h * (grav_1 + grav_2) / 2
    return P, dP_friction, dP_hydro


def march(
    P_in: float,
    L: float,
    D: float,
    dz: float,
    eps: float,
    mdot: float,
    props: PropsFn,
    n: int,
) -> float:
    """March the outlet pressure with Heun's method over n equal segments.

    ``props(P)`` returns ``(rho, mu)`` at pressure P. Returns P_out in Pa; a
    node pressure at or below zero raises :class:`PipeSegmentR1Error`.
    """
    return _march_terms(P_in, L, D, dz, eps, mdot, props, n)[0]


def march_refined(
    P_in: float,
    L: float,
    D: float,
    dz: float,
    eps: float,
    mdot: float,
    props: PropsFn,
    n: int,
) -> tuple[float, int]:
    """Heun march refined by doubling N from n.

    Doubles N until ``|P_out(N) - P_out(N/2)| <= 1e-6 * |P_in - P_out(N)|``
    and returns ``(P_out, N_used)``; raises :class:`PipeSegmentR1Error` when
    the cap of 1024 segments is reached without convergence. (The spec's
    norm assumes a pressure drop; the absolute value keeps a downhill line,
    where the pressure rises, well-defined.)
    """
    P_prev = march(P_in, L, D, dz, eps, mdot, props, n)
    N = n
    while 2 * N <= MAX_SEGMENTS:
        P_new = march(P_in, L, D, dz, eps, mdot, props, 2 * N)
        if abs(P_new - P_prev) <= REFINE_RTOL * abs(P_in - P_new):
            return P_new, 2 * N
        P_prev, N = P_new, 2 * N
    raise PipeSegmentR1Error(f"march refinement did not converge by N = {MAX_SEGMENTS} segments")


def dP_fittings_Pa(K_fittings: float, D_m: float, mdot: float, rho_in: float) -> float:
    """Crane TP-410 K-method fitting drop, ``sum(K) * G^2/(2 rho_in)``, applied at the inlet."""
    area = math.pi * D_m**2 / 4
    G = mdot / area
    return K_fittings * G**2 / (2 * rho_in)


#: Absolute roughness of commercial steel pipe, m (Moody 1944).
DEFAULT_ROUGHNESS_M = 4.57e-5


def _required(params: dict[str, Any], key: str) -> float:
    if key not in params:
        raise PipeSegmentSpecError(f"{key} is required")
    return float(params[key])


def _validated(
    params: dict[str, Any], n_default: int, n_max: int
) -> tuple[float, float, float, float, float, int]:
    """Validate the shared pipe-segment params; every refusal names its parameter."""
    L_m = _required(params, "L_m")
    if L_m <= 0:
        raise PipeSegmentSpecError(f"L_m {L_m} m must be > 0")
    D_m = _required(params, "D_m")
    if D_m <= 0:
        raise PipeSegmentSpecError(f"D_m {D_m} m must be > 0")
    eps = float(params.get("roughness_m", DEFAULT_ROUGHNESS_M))
    if eps < 0:
        raise PipeSegmentSpecError(f"roughness_m {eps} m must be >= 0")
    K = float(params.get("K_fittings", 0.0))
    if K < 0:
        raise PipeSegmentSpecError(f"K_fittings {K} must be >= 0")
    dz = float(params.get("elevation_m", 0.0))
    if abs(dz) > L_m:
        raise PipeSegmentSpecError(
            f"elevation_m {dz} m exceeds the segment length L_m {L_m} m (uniform slope)"
        )
    n = int(params.get("n_segments", n_default))
    if n < 1 or n > n_max:
        raise PipeSegmentSpecError(f"n_segments {n} must be in 1..{n_max}")
    return L_m, D_m, eps, K, dz, n


class PipeSegmentR1:
    """Single-phase Darcy-Colebrook pipe segment with elevation (level R1).

    Method (spec pipe_segment.md): steady 1-D momentum, acceleration neglected,
    marched with Heun's method and refined by segment doubling; adiabatic
    isenthalpic nodes (PH flash at the inlet enthalpy); Crane TP-410 K-method
    fittings at the inlet. Refuses a two-phase inlet or any node that flashes
    two-phase, a vapour pressure ratio below 0.5 (acceleration and choking are
    not modelled at this level), and zero flow.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        L_m, D_m, eps, K, dz, n_start = _validated(params, n_default=10, n_max=MAX_SEGMENTS)
        if inlet.molar_flow <= 0:
            raise PipeSegmentSpecError(
                f"molar_flow {inlet.molar_flow} mol/s must be > 0 (darcy_colebrook needs Q > 0)"
            )
        if 0.001 < inlet.vapor_fraction < 0.999:
            raise PipeSegmentR1Error("two-phase inlet; use R2")
        dominant = max(inlet.phases, key=lambda p: p.mole_fraction)
        mu_in = dominant.viscosity if dominant.viscosity is not None else params.get("mu_Pa_s")
        if mu_in is None:
            raise PipeSegmentSpecError("mu_Pa_s is required: the thermo gives no phase viscosity")
        mu_in = float(mu_in)

        mdot = inlet.mass_flow
        rho_in = dominant.density
        inlet_friction = darcy_colebrook(
            Q_m3_s=mdot / rho_in,
            D_m=D_m,
            rho=rho_in,
            mu=mu_in,
            roughness_m=eps,
            L_m=1.0,
        )
        dP_K = dP_fittings_Pa(K, D_m, mdot, rho_in)

        z = dict(inlet.composition)
        h_in = inlet.enthalpy
        molar_flow = inlet.molar_flow
        calls = {"n": 0}

        def props(P: float) -> tuple[float, float]:
            try:
                state = thermo.flash_ph(z, P, h_in, molar_flow)
            except Exception as exc:
                # The registered PR package cannot converge a pure-component
                # two-phase PH flash (thermo's flash_utils raises inside the
                # solver); any flash failure inside the march means the line
                # entered the two-phase region, which R1 refuses.
                x = (calls["n"]) * (L_m / n_start) / 2
                raise PipeSegmentR1Error(f"flashes to two-phase at x ~= {x:.1f} m; use R2") from exc
            calls["n"] += 1
            if 0.001 < state.vapor_fraction < 0.999:
                x = (calls["n"] - 1) * (L_m / n_start) / 2
                raise PipeSegmentR1Error(f"flashes to two-phase at x ~= {x:.1f} m; use R2")
            node = max(state.phases, key=lambda p: p.mole_fraction)
            mu = node.viscosity if node.viscosity is not None else mu_in
            return node.density, float(mu)

        P_out, n_used = march_refined(inlet.P - dP_K, L_m, D_m, dz, eps, mdot, props, n_start)
        if inlet.vapor_fraction > 0.999 and P_out / inlet.P < 0.5:
            raise PipeSegmentR1Error(
                "pressure ratio below 0.5: acceleration and choking are not modelled at R1"
            )
        # Deterministic re-run at the converged N for the friction/hydrostatic split.
        _, dP_friction, dP_hydro = _march_terms(inlet.P - dP_K, L_m, D_m, dz, eps, mdot, props, n_used)
        outlet = thermo.flash_ph(z, P_out, h_in, molar_flow)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={
                "dP_friction_Pa": dP_friction,
                "dP_fittings_Pa": dP_K,
                "hydrostatic_Pa": dP_hydro,
                "dP_total_Pa": dP_friction + dP_K + dP_hydro,
                "velocity_in_m_s": inlet_friction["velocity_m_s"],
                "Re_in": inlet_friction["Re"],
                "darcy_f_in": inlet_friction["darcy_f"],
                "n_segments_used": float(n_used),
                "dT_K": outlet.T - inlet.T,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 condensate basis through 200 m of 3 in. schedule 40 pipe, 10 m rise."""
        feed = {
            "T": 293.15,
            "P": 1.0e6,
            "molar_flow": 50.0,
            "composition": {"iC4": 0.392, "nC4": 0.248, "iC5": 0.157, "nC5": 0.203},
        }
        return {"inlet": feed}, {"L_m": 200.0, "D_m": 0.0779, "elevation_m": 10.0}
