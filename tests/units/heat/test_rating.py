"""Closed-form tests for the shared rating core (spec double_pipe R1, "Tests").

Every expected number is an independent hand-computed value (from
``calc_double_pipe.py``, carried in the spec), checked at rel 1e-8.
Case 1 basis: water-like film at ~320 K (rho 990, mu 5.77e-4, k 0.637,
cp_mass 4180) in the inner pipe D_i = 0.0266 m at 0.5 kg/s - hand arithmetic
gives v = 0.5/(990*pi*0.0266^2/4) = 0.908827909 m/s,
Re = 990*0.908827909*0.0266/5.77e-4 = 41478.4647,
Pr = 4180*5.77e-4/0.637 = 3.78627943; the turbulent numbers then come from
the same Colebrook + Gnielinski equations the module calls.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units.heat.rating import (
    FilmProps,
    darcy_dP,
    duct_h,
    nu_tube,
    u_outside_tube,
)

REL = 1e-8


def _film(rho: float, mu: float, k: float, cp_mass: float) -> FilmProps:
    return FilmProps(rho_kg_m3=rho, mu_Pa_s=mu, k_W_mK=k, cp_J_kgK=cp_mass)


def test_closed_form_tube_turbulent() -> None:
    """Case 1: turbulent water-like film, D_i = 0.0266 m, 0.5 kg/s, eps 4.5e-5 m."""
    props = _film(990.0, 5.77e-4, 0.637, 4180.0)
    area = math.pi * 0.0266**2 / 4.0
    r = duct_h(0.5, area, 0.0266, props, 4.5e-5)
    assert r.v_m_s == pytest.approx(0.908827909, rel=REL)
    assert r.Re == pytest.approx(41478.4647, rel=REL)
    assert props.Pr == pytest.approx(3.78627943, rel=REL)
    assert r.fd == pytest.approx(0.0263385704, rel=REL)
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(247.163932, rel=REL)
    assert r.h_W_m2K == pytest.approx(5918.92574, rel=REL)
    assert darcy_dP(r.fd, 6.0, 0.0266, 990.0, r.v_m_s) == pytest.approx(2429.0157, rel=REL)


def test_closed_form_laminar() -> None:
    """Case 2: laminar oil-like film in the same pipe; Nu = 3.66, f = 64/Re."""
    props = _film(900.0, 0.05, 0.13, 2000.0)
    area = math.pi * 0.0266**2 / 4.0
    r = duct_h(0.02, area, 0.0266, props, 4.5e-5)
    assert r.Re == pytest.approx(19.1464593, rel=REL)
    assert r.fd == pytest.approx(3.34265458, rel=REL)  # 64/Re
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(3.66, rel=REL)
    assert r.h_W_m2K == pytest.approx(17.887218, rel=REL)  # 3.66*0.13/0.0266


def test_closed_form_annulus() -> None:
    """Case 3: annulus, D_tube,o 0.0334 / D_shell,i 0.0525, N2 film, 0.3 kg/s.

    A = pi*(0.0525^2 - 0.0334^2)/4 = 0.00128859491 m2, Dh = 0.0191 m
    (hydraulic diameter, Incropera 7th ed. section 8.7; the Gnielinski 2009
    annulus correction is deliberately omitted).
    """
    props = _film(8.41, 2.22e-5, 0.0330, 1053.7)
    area = math.pi * (0.0525**2 - 0.0334**2) / 4.0
    assert area == pytest.approx(0.00128859491, rel=REL)
    r = duct_h(0.3, area, 0.0191, props, 4.5e-5)
    assert r.Re == pytest.approx(200301.977, rel=REL)
    assert r.fd == pytest.approx(0.0252700562, rel=REL)
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(522.74325, rel=REL)
    assert r.h_W_m2K == pytest.approx(903.168965, rel=REL)


def test_closed_form_u_outside_tube() -> None:
    """Case 4: U_o from case 1 (inner) and case 3 (annulus) films plus fouling.

    1/U_o = 1/h_o + R_fo + Do*ln(Do/Di)/(2*k_wall) + R_fi*Do/Di + Do/(Di*h_i)
    with h_i = 5918.92574, h_o = 903.168965, Do = 0.0334, Di = 0.0266,
    k_wall = 45, R_fi = 1.8e-4, R_fo = 3.5e-4.
    """
    u = u_outside_tube(
        h_i=5918.92574,
        h_o=903.168965,
        Do=0.0334,
        Di=0.0266,
        k_wall=45.0,
        R_fi=1.8e-4,
        R_fo=3.5e-4,
    )
    assert u == pytest.approx(505.089091, rel=REL)
