"""Filter R1 closed-form tests (spec ``specs/backend/units/filter.md``).

The expected numbers are the spec's CF1-CF4 set, hand-computed here from the
spec's equations (SI):

- c = mdot_s/Q_f = 0.10/2.0e-3 = 50 kg/m3 (F6).
- V_cycle = Q_f*(t_f + t_d) = 2.0e-3*(600 + 300) = 1.8 m3 (F3).
- a = mu*alpha*c/(2*dP) = 8.937e-4*1e11*50/(2*1e5) = 22342.5 s/m2 (F1).
- b = mu*R_m/dP = 8.937e-4*1e10/1e5 = 89.37 s/m (F1).
- v = (-b + sqrt(b^2 + 4*a*t_f))/(2a)
    = (-89.37 + sqrt(89.37^2 + 4*22342.5*600))/(2*22342.5)
    = (-89.37 + sqrt(53629986.9969))/44685
    = 7233.879.../44685 = 0.161886086 m  (F2).
- A_req = 1.8/0.161886086 = 11.118929634834254 m2 (F3). The spec prints
  11.1189296, its 9-significant-digit rounding.
- capacity_ratio at A = 10 m2: 10/11.118929634834254 = 0.8993671448977621 (F7).
- L_cake = 50*1.8/(11.118929634834254*2650*0.6) = 5.090757423949597e-3 m (F4).
- q_ret = 0.4/0.6*0.10/2650 = 2.515723270440252e-5 m3/s (F5), a fraction
  2.515723270440252e-5/2.0e-3 = 0.01257861635220126 of the 2.0e-3 m3/s
  filtrate. The spec prints 0.0125786164, its 9-digit rounding.

rtol 1e-9 per the spec; the expected constants are the exact evaluation of
the spec's printed inputs, so the comparison is not absorbed by print
rounding (the spec's 9-digit prints sit ~3e-9 relative away from them).
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units.separation.filter_r1 import (
    cake_thickness,
    capacity_ratio,
    concentration,
    retained_liquid_rate,
    ruth_area,
    ruth_constants,
    ruth_time,
    ruth_volume_per_area,
)

_MU = 8.937e-4  # Pa s
_ALPHA = 1e11  # m/kg
_RM = 1e10  # 1/m
_DP = 1e5  # Pa
_MDOT_S = 0.10  # kg/s dry solids
_QF = 2.0e-3  # m3/s filtrate
_TF = 600.0  # s
_TD = 300.0  # s


class TestCF1RuthArea:
    """CF1: a, b, v and the required area from one set of printed inputs."""

    def test_coefficients(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert a == pytest.approx(22342.5, rel=1e-9)
        assert b == pytest.approx(89.37, rel=1e-9)

    def test_volume_per_area(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        v = ruth_volume_per_area(_TF, a, b)
        assert v == pytest.approx(0.161886086, rel=1e-9)

    def test_root_is_the_positive_one(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert ruth_volume_per_area(_TF, a, b) > 0.0

    def test_ruth_time_inverts_volume_per_area(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert ruth_time(0.161886086, a, b) == pytest.approx(_TF, rel=1e-9)

    def test_required_area(self) -> None:
        area = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert area == pytest.approx(11.118929634834254, rel=1e-9)


class TestCF2Capacity:
    """CF2: an installed area of 10 m2 against the required 11.1189296 m2."""

    def test_capacity_ratio(self) -> None:
        area_required = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert capacity_ratio(10.0, area_required) == pytest.approx(0.899367145, rel=1e-9)


class TestCF3CakeThickness:
    """CF3: cake thickness at the required area, rho_s = 2650, eps = 0.4."""

    def test_thickness(self) -> None:
        area_required = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert cake_thickness(50.0, 1.8, area_required, 2650.0, 0.4) == pytest.approx(5.09075742e-3, rel=1e-9)


class TestCF4Moisture:
    """CF4: liquid held in the cake voids, eps = 0.4, rho_s = 2650."""

    def test_retained_rate_and_fraction(self) -> None:
        q_ret = retained_liquid_rate(_MDOT_S, 2650.0, 0.4)
        assert q_ret == pytest.approx(2.515723270440252e-5, rel=1e-9)
        assert q_ret / _QF == pytest.approx(0.01257861635220126, rel=1e-9)


class TestF6Concentration:
    """F6 sanity: c = mdot_s/Q_f."""

    def test_concentration(self) -> None:
        assert concentration(_MDOT_S, _QF) == pytest.approx(50.0, rel=1e-12)
        assert math.isclose(concentration(0.3, 1.5), 0.2)
