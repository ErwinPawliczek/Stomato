"""Closed-form Kern-method tests for shell_tube R1 (spec: Tests 1-3).

Hand-checkable chain from the spec's equations on geometry G1
(D_s 0.489 m; 158 tubes, 19.05/14.83 mm; L 4.877 m; P_T 23.81 mm
triangular; B 0.3048 m; 15 baffles; 2 passes), with the expected values
independent numbers transcribed from the spec:

1. Shell (Kern): mdot 18 kg/s, rho 995, mu 8.0e-4, k 0.615, cp 4180.
   - a_s = Ds*(PT-Do)*B/PT = 0.489*0.00476*0.3048/0.02381 = 0.0297969203 m2
   - De,tri = 4*(sqrt(3)/4*PT^2 - pi*Do^2/8)/(pi*Do/2) = 0.0137644071 m
   - De,sq = 4*(PT^2 - pi*Do^2/4)/(pi*Do) = 0.0188408135 m
   - G_s = 18/0.0297969203 = 604.089276 kg/(m2 s); Re_s = De*Gs/mu = 10393.6634
   - Pr = cp*mu/k = 4180*8e-4/0.615 = 5.43739837
   - h_o = 0.36*(0.615/0.0137644071)*10393.6634^0.55*5.43739837^(1/3)
     = 4579.02747 W/(m2 K)
   - f = exp(0.576 - 0.19*ln(10393.6634)) = 0.306879289
   - dP_s = f*Gs^2*(15+1)*Ds/(2*995*De) = 31988.0737 Pa
2. Tube: mdot 12 kg/s, rho 700, mu 4.0e-4, k 0.12, cp 2300, eps 4.5e-5.
   - A/pass = (158/2)*pi*0.01483^2/4 = 0.0136458086 m2
   - v = 12/(700*0.0136458086) = 1.25627273 m/s; Re = rho*v*Di/mu = 32603.4179
   - Colebrook at e/D = 4.5e-5/0.01483: f_D = 0.0297781346
   - Gnielinski: Nu = 278.547286, h_i = Nu*k/Di = 2253.92274 W/(m2 K)
   - dP_t = 2*f_D*(L/Di)*rho*v^2/2 + 4*2*rho*v^2/2 = 15237.7172 Pa
3. U and area: U_o clean (k_w 45) = 1188.61873 W/(m2 K);
   A_o = 158*pi*0.01905*4.877 = 46.1163254 m2; UA = 54814.7284 W/K.

All assertions use rel 1e-8 (the spec's closed-form band; the expected
values are quoted to 9-10 significant figures).
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units.heat.rating import FilmProps, u_outside_tube
from ngdesign.units.heat.shell_tube_r1 import (
    KernRangeError,
    equiv_diameter,
    shell_dP,
    shell_flow_area,
    shell_friction,
    shell_h,
    tube_dP,
    tube_duct,
    tube_flow_area,
)

#: Geometry G1 from the spec's Tests section.
DS = 0.489
N_TUBES = 158
TUBE_OD = 0.01905
TUBE_ID = 0.01483
LENGTH = 4.877
PITCH = 0.02381
BAFFLE = 0.3048
N_BAFFLES = 15
N_PASSES = 2

REL = 1e-8


def _rel(got: float, want: float) -> float:
    return abs(got - want) / abs(want)


def test_shell_side_kern_chain() -> None:
    """Eq. S1-S3 shell chain: a_s, De per layout, Gs, Re_s, Pr, h_o, f, dP_s."""
    a_s = shell_flow_area(DS, PITCH, TUBE_OD, BAFFLE)
    assert _rel(a_s, 0.0297969203) < REL
    de_tri = equiv_diameter(PITCH, TUBE_OD, "triangular30")
    de_sq = equiv_diameter(PITCH, TUBE_OD, "square90")
    assert _rel(de_tri, 0.0137644071) < REL
    assert _rel(de_sq, 0.0188408135) < REL
    gs = 18.0 / a_s
    assert _rel(gs, 604.089276) < REL
    re_s = de_tri * gs / 8.0e-4
    assert _rel(re_s, 10393.6634) < REL
    pr = 4180.0 * 8.0e-4 / 0.615
    assert _rel(pr, 5.43739837) < REL
    h_o = shell_h(0.615, de_tri, re_s, pr)
    assert _rel(h_o, 4579.02747) < REL
    f = shell_friction(re_s)
    assert _rel(f, 0.306879289) < REL
    dP_s = shell_dP(f, gs, N_BAFFLES, DS, 995.0, de_tri)
    assert _rel(dP_s, 31988.0737) < REL


def test_tube_side_kern_chain() -> None:
    """Tube chain: area per pass, v, Re, Colebrook f_D, Gnielinski h_i, dP with returns."""
    area = tube_flow_area(N_TUBES, N_PASSES, TUBE_ID)
    assert _rel(area, 0.0136458086) < REL
    props = FilmProps(rho_kg_m3=700.0, mu_Pa_s=4.0e-4, k_W_mK=0.12, cp_J_kgK=2300.0)
    duct = tube_duct(12.0, N_TUBES, N_PASSES, TUBE_ID, props, 4.5e-5)
    assert _rel(duct.v_m_s, 1.25627273) < REL
    assert _rel(duct.Re, 32603.4179) < REL
    assert _rel(duct.fd, 0.0297781346) < REL
    assert _rel(duct.h_W_m2K, 2253.92274) < REL
    dP = tube_dP(duct.fd, N_PASSES, LENGTH, TUBE_ID, 700.0, duct.v_m_s)
    assert _rel(dP, 15237.7172) < REL


def test_u_and_area() -> None:
    """Clean overall U on the outside area and A_o = Nt*pi*Do*L."""
    props = FilmProps(rho_kg_m3=700.0, mu_Pa_s=4.0e-4, k_W_mK=0.12, cp_J_kgK=2300.0)
    duct = tube_duct(12.0, N_TUBES, N_PASSES, TUBE_ID, props, 4.5e-5)
    h_o = shell_h(0.615, 0.0137644071, 10393.6634, 5.43739837)
    u_o = u_outside_tube(h_i=duct.h_W_m2K, h_o=h_o, Do=TUBE_OD, Di=TUBE_ID, k_wall=45.0, R_fi=0.0, R_fo=0.0)
    assert _rel(u_o, 1188.61873) < REL
    a_o = N_TUBES * math.pi * TUBE_OD * LENGTH
    assert _rel(a_o, 46.1163254) < REL
    assert _rel(u_o * a_o, 54814.7284) < REL


def test_shell_friction_below_fit_band_refuses() -> None:
    """The S3 fit is valid for 400 < Re_s <= 1e6; outside it the fit refuses."""
    with pytest.raises(KernRangeError, match="Re_s"):
        shell_friction(399.0)
    with pytest.raises(KernRangeError, match="Re_s"):
        shell_friction(1.0e7)
    # The band edges themselves are exact equality checks, not tolerance checks.
    assert shell_friction(400.0 * (1.0 + 1e-12)) == pytest.approx(
        math.exp(0.576 - 0.19 * math.log(400.0 * (1.0 + 1e-12)))
    )
