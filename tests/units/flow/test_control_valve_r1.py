"""Closed-form tests for control_valve R1 (spec specs/backend/units/control_valve.md).

Every expected value below is hand-computed from the spec's IEC 60534-2-1:2011
equations, independent of fluids; tolerance 1e-10 relative.

Hand computation (liquid, eqs. 1-4, Q in m3/h, dP in kPa, N1 = 0.1,
rho0 = 999.10329 kg/m3):
- L1: rho1/rho0 = 965.4/999.10329 = 0.9662562...; dP = 680 - 220 = 460 kPa;
  FF = 0.96 - 0.28*sqrt(70.1/22120) = 0.944237522523330;
  dP_choke = 0.9^2*(680 - 0.944237522523330*70.1) kPa = 497.185249233603 kPa
  > 460 kPa, so not choked;
  Kv = 360/0.1*sqrt(0.9662562.../460) = 164.995476370496; Cv = Kv/0.865.
- L2: same basis, P2 = 100 kPa, dP = 580 kPa > 497.185... kPa, choked;
  Kv = 360/(0.1*0.9)*sqrt(0.9662562.../(680 - 0.944237522523330*70.1))
    = 158.705448111403.

Hand computation (gas, eqs. 5/8/10/13, Q in m3/h, P in kPa, N9 = 24.6):
- Q_std = 50 mol/s * 0.0224139695450141 m3/mol = 1.12069847725071 m3/s
  = 4034.5145181 m3/h;
- G1: x = 230/680 = 0.338235294117647 < Fgamma*xT = (1.3/1.4)*0.6
  = 0.557142857142857, not choked; Y = 1 - x/(3*Fgamma*xT)
  = 0.797637003519357;
  Kv = 4034.5145181/(24.6*680*0.797637003519357)
       *sqrt(44.01*433*0.988/0.338235294117647) = 71.3395905795846.
- G2: x = 480/680 = 0.705882352941176 >= 0.557142857142857, choked;
  choke P2 = 680*(1 - 0.557142857142857) = 301.142857142857 kPa;
  x is replaced by Fgamma*xT and Y = 2/3;
  Kv = 4034.5145181/(24.6*680*(2/3))*sqrt(44.01*433*0.988/0.557142857142857)
     = 66.5048538035932.
"""

from __future__ import annotations

import pytest

from ngdesign.units.flow.control_valve_r1 import (
    KV_PER_CV,
    VMOL_STD,
    characteristic,
    characteristic_inverse,
    kv_gas,
    kv_liquid,
)

REL = 1e-10

# L1/L2 basis (IEC 60534-2-1 Annex D example 1 inputs, printed in the spec).
L_Q = 0.1  # m3/s = 360 m3/h
L_RHO = 965.4  # kg/m3
L_MU = 3.1472e-4  # Pa s
L_PSAT = 70.1e3  # Pa
L_PC = 22120e3  # Pa
L_P1 = 680e3  # Pa
L_FL = 0.9
L_FD = 1.0

# G1/G2 basis (IEC 60534-2-1 Annex D example 3 inputs, printed in the spec).
G_N = 50.0  # mol/s
G_MW = 44.01  # g/mol
G_MU = 1.4665e-4  # Pa s
G_GAMMA = 1.30
G_Z = 0.988
G_T = 433.0  # K
G_P1 = 680e3  # Pa
G_XT = 0.60
G_FL = 0.9
G_FD = 1.0


def test_vmol_std_conversion() -> None:
    """Eq. 5: the molar volume behind N9 is exactly R*273.15/101325."""
    assert VMOL_STD == pytest.approx(0.0224139695450141, rel=1e-12)
    assert G_N * VMOL_STD == pytest.approx(1.12069847725071, rel=1e-12)


def test_liquid_non_choked_L1() -> None:
    """L1: eq. 1, far from choke."""
    d = kv_liquid(
        Q_m3_s=L_Q,
        rho=L_RHO,
        mu=L_MU,
        Psat=L_PSAT,
        Pc=L_PC,
        P1=L_P1,
        P2=220e3,
        FL=L_FL,
        Fd=L_FD,
    )
    assert d["Kv"] == pytest.approx(164.995476370496, rel=REL)
    assert d["Kv"] / KV_PER_CV == pytest.approx(190.746215457220, rel=REL)
    assert d["choked"] == 0.0
    assert d["FR"] == 1.0 and d["FP"] == 1.0


def test_liquid_choked_L2() -> None:
    """L2: eq. 3, dP beyond the choked drop."""
    d = kv_liquid(
        Q_m3_s=L_Q,
        rho=L_RHO,
        mu=L_MU,
        Psat=L_PSAT,
        Pc=L_PC,
        P1=L_P1,
        P2=100e3,
        FL=L_FL,
        Fd=L_FD,
    )
    assert d["Kv"] == pytest.approx(158.705448111403, rel=REL)
    assert d["choked"] == 1.0


def test_gas_non_choked_G1() -> None:
    """G1: eqs. 8 and 10, x below Fgamma*xT."""
    d = kv_gas(
        n_mol_s=G_N,
        MW=G_MW,
        mu=G_MU,
        gamma=G_GAMMA,
        Z=G_Z,
        T=G_T,
        P1=G_P1,
        P2=450e3,
        xT=G_XT,
        FL=G_FL,
        Fd=G_FD,
    )
    assert d["Kv"] == pytest.approx(71.3395905795846, rel=REL)
    assert d["Y"] == pytest.approx(0.797637003519357, rel=REL)
    assert d["choked"] == 0.0


def test_gas_choked_G2() -> None:
    """G2: x beyond Fgamma*xT; x replaced by Fgamma*xT, Y = 2/3."""
    d = kv_gas(
        n_mol_s=G_N,
        MW=G_MW,
        mu=G_MU,
        gamma=G_GAMMA,
        Z=G_Z,
        T=G_T,
        P1=G_P1,
        P2=200e3,
        xT=G_XT,
        FL=G_FL,
        Fd=G_FD,
    )
    assert d["Kv"] == pytest.approx(66.5048538035932, rel=REL)
    assert d["choked"] == 1.0
    assert d["Y"] == pytest.approx(2.0 / 3.0, rel=REL)


def test_characteristic_equal_percentage() -> None:
    """phi = R^(l-1) at the spec's printed points."""
    assert characteristic(0.25, "equal_percentage", 50.0) == pytest.approx(0.0531829589694499, rel=REL)
    assert characteristic(0.5, "equal_percentage", 50.0) == pytest.approx(0.141421356237310, rel=REL)
    assert characteristic(0.8, "equal_percentage", 50.0) == pytest.approx(0.457305051927326, rel=REL)


def test_characteristic_quick_opening() -> None:
    """phi = sqrt(l)."""
    assert characteristic(0.5, "quick_opening") == pytest.approx(0.707106781186548, rel=REL)


def test_characteristic_linear() -> None:
    """phi = l."""
    assert characteristic(0.3, "linear") == pytest.approx(0.3, rel=REL)


def test_characteristic_inverse_equal_percentage() -> None:
    """l = 1 + ln(phi)/ln(R) at the spec's printed point."""
    assert characteristic_inverse(0.2, "equal_percentage", 50.0) == pytest.approx(0.588591910067779, rel=REL)


def test_characteristic_round_trip() -> None:
    """Each kind's inverse undoes its characteristic."""
    for kind in ("linear", "equal_percentage", "quick_opening"):
        for travel in (0.05, 0.4, 1.0):
            assert characteristic_inverse(characteristic(travel, kind, 50.0), kind, 50.0) == (
                pytest.approx(travel, rel=1e-12)
            )


def test_bad_characteristic_refused() -> None:
    with pytest.raises(ValueError, match="characteristic"):
        characteristic(0.5, "equal-percentage")


def test_bad_travel_refused() -> None:
    with pytest.raises(ValueError, match="opening"):
        characteristic(0.0, "linear")
    with pytest.raises(ValueError, match="phi"):
        characteristic_inverse(1.5, "linear")
