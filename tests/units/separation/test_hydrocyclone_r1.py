"""Hydrocyclone R1 closed-form tests (spec specs/backend/units/hydrocyclone.md).

Basis (a Lapple standard-proportion gas cyclone, D = 0.5 m, so W = 0.125 m,
H = 0.25 m, D_e = 0.25 m, L_b = L_c = 1.0 m), Q = 0.5 m3/s, rho_f = 1.2 kg/m3,
mu = 1.8e-5 Pa.s, rho_p = 2000 kg/m3.

Hand-computed anchor values (the numbers below are re-derived here from the
spec's equations, not from the implementation):

- H1: v_i = Q/(W*H) = 0.5/(0.125*0.25) = 16 m/s.
- H2: N_e = (L_b + L_c/2)/H = (1.0 + 0.5)/0.25 = 6.
- H3: d50 = sqrt(9*mu*W/(2*pi*N_e*v_i*|rho_p - rho_f|))
      = sqrt(9*1.8e-5*0.125/(2*pi*6*16*1998.8))
      = sqrt(2.025e-5/1.20584e6) = 4.09828629e-6 m.
- H4: eta(5 um)  = 1/(1 + (4.09828629/5)^2)    = 0.598144072;
      eta(10 um) = 1/(1 + (4.09828629/10)^2)   = 0.856194068.
- H6: N_H = K*H*W/De^2 = 16*0.25*0.125/0.0625 = 8;
      dP = 0.5*1.2*16^2*8 = 1228.8 Pa.
- H5: E = int_0^1 eta(d_RR*(-ln(1-F))^(1/n)) dF by 64-point Gauss-Legendre
      with d_RR = 10 um, n = 1.5 gives 0.685967673. An independent midpoint
      rule with 2e6 points gives 0.685967816; the 1.4e-7 difference is
      quadrature, so the test pins GL64 (spec CF4).
- H7 (CF5): particle underflow fraction E + (1 - E)*R_f
      = 0.685967673 + 0.314032327*0.1 = 0.717370906.
- Light-particle branch: rho_p < rho_f sends the separated fraction to the
  overflow, so with E = 0.6 and R_f = 0.2 the underflow fraction is
  (1 - 0.6)*0.2 = 0.08 exactly.
"""

from __future__ import annotations

import pytest

from ngdesign.units.separation.hydrocyclone_r1 import (
    effective_turns,
    grade_efficiency,
    inlet_velocity,
    lapple_cut_diameter,
    overall_efficiency,
    shepherd_lapple_number,
    shepherd_lapple_pressure_drop,
    underflow_fraction,
)

_W, _H, _D_E, _L_B, _L_C = 0.125, 0.25, 0.25, 1.0, 1.0
_Q, _RHO_F, _MU, _RHO_P = 0.5, 1.2, 1.8e-5, 2000.0


def _d50() -> float:
    v_i = inlet_velocity(_Q, _W, _H)
    return lapple_cut_diameter(_MU, _W, effective_turns(_L_B, _L_C, _H), v_i, _RHO_P, _RHO_F)


def test_cf1_inlet_velocity_turns_and_cut_diameter() -> None:
    v_i = inlet_velocity(_Q, _W, _H)
    N_e = effective_turns(_L_B, _L_C, _H)
    assert v_i == pytest.approx(16.0, rel=1e-9)
    assert N_e == pytest.approx(6.0, rel=1e-9)
    assert _d50() == pytest.approx(4.09828629e-6, rel=1e-9)


def test_cf2_grade_efficiency_at_5_and_10_um() -> None:
    d50 = _d50()
    assert grade_efficiency(d50, 5e-6) == pytest.approx(0.598144072, rel=1e-9)
    assert grade_efficiency(d50, 10e-6) == pytest.approx(0.856194068, rel=1e-9)


def test_cf3_shepherd_lapple_pressure_drop() -> None:
    N_H = shepherd_lapple_number(_H, _W, _D_E)
    assert N_H == pytest.approx(8.0, rel=1e-12)
    assert shepherd_lapple_pressure_drop(_RHO_F, inlet_velocity(_Q, _W, _H), N_H) == pytest.approx(
        1228.8, rel=1e-12
    )


def test_cf4_overall_efficiency_gl64_rosin_rammler() -> None:
    assert overall_efficiency(_d50(), 10e-6, 1.5) == pytest.approx(0.685967673, rel=1e-9)


def test_cf5_particle_underflow_fraction_with_fluid_split() -> None:
    E = overall_efficiency(_d50(), 10e-6, 1.5)
    assert underflow_fraction(E, 0.1, light_particle=False) == pytest.approx(0.717370906, rel=1e-9)


def test_light_particle_branch_reports_to_overflow() -> None:
    """H7 with rho_p < rho_f: underflow fraction (1 - E)*R_f; E = 0.6, R_f = 0.2."""
    assert underflow_fraction(0.6, 0.2, light_particle=True) == pytest.approx(0.08, rel=1e-12)
