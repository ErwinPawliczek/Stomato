"""Decanter R1: Stokes settling with Richardson-Zaki hindered settling.

Plugin kind "unit", name "decanter" (level R1) — registered from the
catalogue YAML; no decorator (U-R2 conventions). Read-only over the R0
:class:`~ngdesign.units.separation.decanter.Decanter`, which supplies the
LLE split; this level adds the settling physics on top of it.

Method (spec ``specs/backend/units/decanter.md``):

- **D1** Stokes terminal velocity of a dispersed droplet in the continuous
  phase: ``u_t = g·d²·|ρ_d − ρ_c|/(18·μ_c)`` with g = 9.80665 m/s². Valid
  only for ``Re_t = ρ_c·u_t·d/μ_c < 1``; outside that range the unit refuses
  (R1 is a Stokes model — never extrapolated).
- **D2** dispersed volume fraction ``φ = Q_d/(Q_c + Q_d)`` from the R0
  outlets' volumetric flows.
- **D3** Richardson-Zaki exponent (Trans. IChemE 32:35, 1954), no wall
  correction: ``n = 4.65`` for ``Re_t < 0.2``; ``4.4·Re_t^−0.03`` for
  ``0.2 ≤ Re_t < 1``; ``4.4·Re_t^−0.1`` for ``1 ≤ Re_t < 500`` (unreachable
  under D1's validity); ``2.4`` for ``Re_t ≥ 500``.
- **D4** hindered velocity ``u_h = u_t·(1 − φ)^n``.
- **D5** Hazen (1904) ideal-settler efficiency ``η = min(1, u_h·A_i/Q_c)``,
  with ``A_i`` the interface area — for a horizontal cylinder with the
  interface at the centre line, ``A_i = D·L`` (Sinnott, *Coulson &
  Richardson's Chemical Engineering* Vol. 6, §10.6.3).
- **D6** entrainment: the fraction ``1 − η`` of the dispersed phase leaves
  with the continuous phase.

The dispersed outlet is the R0 outlet scaled to ``η·n_d`` (never re-flashed);
the continuous outlet is re-flashed as a two-liquid mix of the R0 continuous
outlet and the entrained dispersed liquid at the same T and P.
"""

from __future__ import annotations

#: Standard gravity, m/s2 (D1).
G = 9.80665


class DecanterR1SpecError(ValueError):
    """The decanter R1 spec is outside the Stokes settling model."""


def stokes_velocity(d: float, rho_d: float, rho_c: float, mu_c: float) -> float:
    """Stokes terminal velocity (D1): ``u_t = g·d²·|ρ_d − ρ_c|/(18·μ_c)``.

    Units: d in m, densities in kg/m³, ``mu_c`` in Pa·s, result in m/s.
    """
    return G * d**2 * abs(rho_d - rho_c) / (18.0 * mu_c)


def rz_exponent(re_t: float) -> float:
    """Richardson-Zaki exponent (D3) as a function of the droplet Reynolds number."""
    if re_t < 0.2:
        return 4.65
    if re_t < 1.0:
        return float(4.4 * re_t**-0.03)
    if re_t < 500.0:
        return float(4.4 * re_t**-0.1)
    return 2.4


def hindered_velocity(u_t: float, phi: float, n: float) -> float:
    """Richardson-Zaki hindered settling velocity (D4): ``u_h = u_t·(1 − φ)^n``."""
    return u_t * float((1.0 - phi) ** n)


def settler_efficiency(u_h: float, area_m2: float, q_c: float) -> float:
    """Hazen ideal-settler separation efficiency (D5): ``min(1, u_h·A_i/Q_c)``."""
    return min(1.0, u_h * area_m2 / q_c)
