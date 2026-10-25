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
    raise PipeSegmentR1Error(
        f"march refinement did not converge by N = {MAX_SEGMENTS} segments"
    )


def dP_fittings_Pa(K_fittings: float, D_m: float, mdot: float, rho_in: float) -> float:
    """Crane TP-410 K-method fitting drop, ``sum(K) * G^2/(2 rho_in)``, applied at the inlet."""
    area = math.pi * D_m**2 / 4
    G = mdot / area
    return K_fittings * G**2 / (2 * rho_in)
