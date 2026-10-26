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
internal zone cross or a non-physical trial state report an infinite demand
rather than raising. ``F_corr = 1`` for a single tube pass; otherwise
``ht.F_LMTD_Fakheri`` at the trial's terminal temperatures, applied uniformly
(the stated Serth Ch. 11 approximation). After convergence with ``N_tp >= 2``,
a non-finite or ``F < F_min`` result (default 0.75, Kern's practical limit)
raises ``TemperatureCross`` naming ``F`` and the minimum shells in series
required. ``xtol = 1e-10*Q_max``, ``maxiter = 100``.

Zone films (the zone-mean vapour fraction ``x_v`` from the flash selects the
regime):

- single phase: the R1 correlations (Gnielinski tube, Kern shell);
- shell-side condensation: Nusselt film on horizontal tubes, ``h_1`` per
  Incropera eq. 10.46 with ``h'_fg`` per eq. 10.9, the tube-bank correction
  ``h_1*N_r^(-1/4)`` per eq. 10.47 with ``N_r = tube_rows_vertical``; the wall
  temperature comes from a fixed point capped at 50 iterations;
- tube-side condensation: ``ht.Shah`` (Shah 1979) with the zone-mean quality;
- tube-side flow boiling: ``ht.Liu_Winterton`` (Liu & Winterton 1991) with
  ``T_e = T_w - T_sat`` from the same fixed point.
- shell-side boiling is refused (``PhaseRegimeNotRated``): kettle and
  thermosiphon reboilers are not rated at R2.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import ht

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import components
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import (
    DuctResult,
    FilmProps,
    RatingConvergenceError,
    RatingError,
    duct_h,
    film_props,
    inlet_kind,
    u_outside_tube,
)
from ngdesign.units.heat.shell_tube_r1 import (
    KERN_RE_MAX,
    KERN_RE_MIN,
    ShellGeometry,
    ShellTubeGeometryError,
    ShellTubeR1,
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

#: Typed aliases for the ht callables (ht 1.2.0 ships them unannotated).
FAKHERI = ht.F_LMTD_Fakheri
SHAH = ht.Shah
LIU_WINTERTON = ht.Liu_Winterton


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
    return 0.729 * (
        GRAVITY * rho_l * (rho_l - rho_v) * k_l**3 * hp / (mu_l * (T_sat - T_w) * D_o)
    ) ** 0.25


def nusselt_bank(h_1: float, n_rows: float) -> float:
    """Tube-bank correction ``h_1*N_r^(-1/4)`` (Incropera eq. 10.47)."""
    return h_1 * n_rows ** (-0.25)


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
                f"shell_tube R2: wall temperature diverged: T_w = {t_next} K left the band "
                f"({lo}, {hi}) K"
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
