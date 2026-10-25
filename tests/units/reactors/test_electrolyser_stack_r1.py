"""Electrolyser stack R1: closed-form voltage and polarisation oracles (step 1).

Hand-computed from the spec's equations (``specs/backend/units/electrolyser_stack.md``),
never from model output:

**Reversible voltage at 298.15 K.** The databank formation data (verified in
this session against ``ngdesign.data.formation``) are H2O(g)
ΔfH°298 = −241822 J/mol and S°298 = 188.8 J/(mol·K); H2 S°298 = 130.7;
O2 S°298 = 205.2 J/(mol·K). For H2O(g) → H2 + ½O2 at 298.15 K the
``from_gibbs`` ∫ΔCp terms vanish (T = 298.15 K is the formation reference),
so

    ΔS° = 130.7 + 205.2/2 − 188.8 = 44.5 J/(mol·K)
    ΔG° = 241822 − 298.15·44.5 = 228554.325 J/mol
    U_rev,g = ΔG°/(2F) = 228554.325/192970.66424 = 1.18439933 V

(the JANAF printed textbook value 1.229 V is the liquid-water number below,
not this vapour value; it is a sanity check, not the assertion). With the
saturation correction, p_sat(H2O, 298.15 K) = 3169.92934 Pa read from the
thermo package in the test as an input:

    ΔG_l = ΔG° − R·T·ln(p_sat/P°) = 237110.348 J/mol
    U_rev,l = 1.22873779 V

**Polarisation (test coefficients, not data).** r1 = 8.0e-5 Ω·m²,
r2 = −2.5e-7 Ω·m²/°C, s = 0.185 V, t1 = −0.1 m²/A, t2 = 8.4 m²·°C/A,
t3 = 247.0 m²·°C²/A. With I = 2000 A, A = 0.25 m², N = 10 and a liquid-water
feed at 298.15 K (T_C = 25 °C): i = 8000 A/m²,

    ohmic  = (8.0e-5 − 2.5e-7·25)·8000 = 0.59 V
    act arg = (−0.1 + 8.4/25 + 247.0/625)·8000 + 1 = 5050.6
    activation = 0.185·log10(5050.6) = 0.68511845 V
    U_cell = 1.22873779 + 0.59 + 0.68511845 = 2.50385624 V

and with f1 = 2.5e4 A²/m⁴, f2 = 0.96 (Ulleberg eq. 9 form):

    η_F = 0.96·8000²/(2.5e4 + 8000²) = 0.959625146
"""

from __future__ import annotations

import math

from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.reactors.electrolyser import FARADAY
from ngdesign.units.reactors.electrolyser_r1 import (
    faradaic_efficiency,
    overpotentials,
    reversible_voltage,
    reversible_voltage_gibbs,
)

THERMO = PengRobinsonThermo()

#: Databank printed values behind the closed form (see module docstring).
DELTA_G_298 = 241822.0 - 298.15 * 44.5  # = 228554.325 J/mol, exact on those inputs

TEST_POLARISATION = {
    "r1": 8.0e-5,
    "r2": -2.5e-7,
    "s": 0.185,
    "t1": -0.1,
    "t2": 8.4,
    "t3": 247.0,
}


def test_reversible_voltage_vapour_closed_form() -> None:
    # ΔG°/(2F) from the printed databank numbers; U_rev,g = 1.18439933 V.
    expected = DELTA_G_298 / (2.0 * FARADAY)
    got = reversible_voltage_gibbs(298.15)
    assert math.isclose(got, expected, rel_tol=1e-9)
    assert math.isclose(got, 1.18439933, rel_tol=1e-8)  # printed sanity value


def test_reversible_voltage_liquid_closed_form() -> None:
    # p_sat enters the expected value as an INPUT (read from the package),
    # exactly as the spec prescribes; the closed form is still hand-computed.
    p_sat = THERMO.pure_psat("H2O", 298.15)
    assert p_sat is not None
    delta_g_liquid = DELTA_G_298 - R * 298.15 * math.log(p_sat / 1.0e5)
    expected = delta_g_liquid / (2.0 * FARADAY)
    got = reversible_voltage(THERMO, 298.15, 3.0e6, liquid_reactant=True)
    assert math.isclose(got, expected, rel_tol=1e-9)
    assert math.isclose(got, 1.22873779, rel_tol=1e-8)  # printed sanity value


def test_polarisation_closed_form() -> None:
    # i = 8000 A/m2, T_C = 25 degC: ohmic 0.59 V, activation 0.68511845 V.
    i = 2000.0 / 0.25
    ohmic, activation = overpotentials(0.0, i, 25.0, TEST_POLARISATION)
    assert math.isclose(ohmic, (8.0e-5 - 2.5e-7 * 25.0) * i, rel_tol=1e-12)
    assert math.isclose(ohmic, 0.59, rel_tol=1e-9)
    arg = (-0.1 + 8.4 / 25.0 + 247.0 / 25.0**2) * i + 1.0
    assert math.isclose(activation, 0.185 * math.log10(arg), rel_tol=1e-9)
    assert math.isclose(activation, 0.68511845, rel_tol=1e-8)
    # U_cell = U_rev,l + ohmic + activation = 2.50385624 V, expected computed
    # end to end from the printed inputs (closed-form oracle at 1e-9; the
    # printed 9-digit literal is rounded past 1e-9 relative, so it is the
    # 1e-8 sanity check).
    p_sat = THERMO.pure_psat("H2O", 298.15)
    assert p_sat is not None
    u_rev_l_hand = (DELTA_G_298 - R * 298.15 * math.log(p_sat / 1.0e5)) / (2.0 * FARADAY)
    u_cell_expected = u_rev_l_hand + (8.0e-5 - 2.5e-7 * 25.0) * i + 0.185 * math.log10(arg)
    u_rev_l = reversible_voltage(THERMO, 298.15, 3.0e6, liquid_reactant=True)
    u_cell = u_rev_l + ohmic + activation
    assert math.isclose(u_cell, u_cell_expected, rel_tol=1e-9)
    assert math.isclose(u_cell, 2.50385624, rel_tol=1e-8)


def test_faradaic_efficiency_closed_form() -> None:
    # eta_F = 0.96·8000^2/(2.5e4 + 8000^2) = 0.959625146.
    eta = faradaic_efficiency(8000.0, {"f1": 2.5e4, "f2": 0.96})
    assert math.isclose(eta, 0.96 * 8000.0**2 / (2.5e4 + 8000.0**2), rel_tol=1e-12)
    assert math.isclose(eta, 0.959625146, rel_tol=1e-9)
    assert faradaic_efficiency(8000.0, None) == 1.0


def test_log_base_is_ten() -> None:
    # s·log10(arg) and s·ln(arg) differ by ~2.3x: the base is pinned by
    # checking activation == 0.185·log10(arg) against ln to 1e-9.
    i = 8000.0
    arg = (-0.1 + 8.4 / 25.0 + 247.0 / 25.0**2) * i + 1.0
    _, activation = overpotentials(0.0, i, 25.0, TEST_POLARISATION)
    assert math.isclose(activation, 0.185 * math.log10(arg), rel_tol=1e-12)
    assert not math.isclose(activation, 0.185 * math.log(arg), rel_tol=1e-3)
