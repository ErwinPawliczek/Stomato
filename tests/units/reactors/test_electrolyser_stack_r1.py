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
    n_H2 = η_F·I·N/(2F) = 0.0994581379 mol/s,  P_el = U_cell·I·N = 50077.1249 W

Printed 9-digit literals are rounded past 1e-9 relative, so each carries a
1e-8 sanity assertion while the closed-form expressions carry the 1e-9
spec tolerance.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.reactors.electrolyser import FARADAY, ElectrolyserStack
from ngdesign.units.reactors.electrolyser_r1 import (
    P_REF,
    ElectrolyserError,
    ElectrolyserStackR1,
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

ZERO_POLARISATION = {key: 0.0 for key in TEST_POLARISATION}

EXAMPLE_FEED = {
    "T": 298.15,
    "P": 3.0e6,
    "molar_flow": 50.0,
    "composition": {"H2O": 1.0},
}


class NoPsatThermo(PengRobinsonThermo):
    """The PR package with the saturation pressure unavailable (refusal path)."""

    def pure_psat(self, cid: str, T: float) -> float | None:
        return None


def flash_feed(feed: dict[str, Any]) -> StreamState:
    return THERMO.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


# --- Step 1: the voltage and efficiency functions. --------------------------


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
    # end to end from the printed inputs.
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


# --- Step 2: the adapter — delegation to R0, the reduction identity, refusals.


def test_adapter_closed_form_solve() -> None:
    # The spec's polarisation closed form through the full adapter, N = 10:
    # U_cell = 2.50385624 V, eta_F = 0.959625146, n_H2 = 0.0994581379 mol/s,
    # P_el = 50077.1249 W.
    inlet = flash_feed(EXAMPLE_FEED)
    result = ElectrolyserStackR1().solve(
        {"inlet": inlet},
        {
            "current_A": 2000.0,
            "n_cells": 10.0,
            "area_m2": 0.25,
            "polarisation": TEST_POLARISATION,
            "faradaic": {"f1": 2.5e4, "f2": 0.96},
        },
        THERMO,
    )
    info = result.info
    assert math.isclose(info["U_rev_V"], 1.22873779, rel_tol=1e-8)
    assert math.isclose(info["eta_ohmic_V"], 0.59, rel_tol=1e-9)
    assert math.isclose(info["eta_activation_V"], 0.68511845, rel_tol=1e-8)
    assert math.isclose(info["cell_voltage_V"], 2.50385624, rel_tol=1e-8)
    assert math.isclose(info["current_density_A_m2"], 8000.0, rel_tol=1e-12)
    assert math.isclose(info["faradaic_efficiency"], 0.959625146, rel_tol=1e-9)
    expected_n_h2 = 0.959625146 * 2000.0 * 10.0 / (2.0 * FARADAY)
    assert math.isclose(info["h2_production_mol_s"], expected_n_h2, rel_tol=1e-9)
    assert math.isclose(info["h2_production_mol_s"], 0.0994581379, rel_tol=1e-8)
    assert math.isclose(result.power_W, 50077.1249, rel_tol=1e-8)
    # efficiency_HHV is the thermoneutral voltage R0 reports over U_cell.
    assert info["efficiency_HHV"] == pytest.approx(
        info["thermoneutral_voltage_V"] / info["cell_voltage_V"], rel=1e-12
    )


def test_adapter_reduces_to_r0_identity() -> None:
    # With all six polarisation coefficients 0, no faradaic block and no
    # pressure correction, U_cell = U_rev and eta_F = 1, and the R1 result
    # equals the R0 solve at cell_voltage_V = U_rev exactly (1e-12): the
    # same code path.
    inlet = flash_feed(EXAMPLE_FEED)
    r1 = ElectrolyserStackR1().solve(
        {"inlet": inlet},
        {
            "current_A": 2000.0,
            "n_cells": 100.0,
            "area_m2": 0.25,
            "polarisation": ZERO_POLARISATION,
        },
        THERMO,
    )
    u_rev = r1.info["U_rev_V"]
    r0 = ElectrolyserStack().solve(
        {"inlet": inlet},
        {
            "current_A": 2000.0,
            "n_cells": 100.0,
            "cell_voltage_V": u_rev,
            "faradaic_efficiency": 1.0,
        },
        THERMO,
    )
    assert r1.info["cell_voltage_V"] == u_rev
    assert r1.info["faradaic_efficiency"] == 1.0
    assert r1.duty_W == pytest.approx(r0.duty_W, rel=1e-12)
    assert r1.power_W == pytest.approx(r0.power_W, rel=1e-12)
    for port in ("h2_out", "o2_out"):
        a, b = r1.outlets[port], r0.outlets[port]
        assert a.T == pytest.approx(b.T, rel=1e-12)
        assert a.P == pytest.approx(b.P, rel=1e-12)
        assert a.molar_flow == pytest.approx(b.molar_flow, rel=1e-12)
        assert a.vapor_fraction == pytest.approx(b.vapor_fraction, rel=1e-12)
        for cid, x in b.composition.items():
            assert a.composition[cid] == pytest.approx(x, rel=1e-12)


def test_vapour_feed_uses_gibbs_path() -> None:
    # Superheated steam (T above saturation at 1 bar): equation 1, no
    # saturation correction — U_rev equals the pure Gibbs value.
    steam = flash_feed({"T": 400.0, "P": 1.0e5, "molar_flow": 20.0, "composition": {"H2O": 1.0}})
    assert steam.vapor_fraction == 1.0
    result = ElectrolyserStackR1().solve(
        {"inlet": steam},
        {
            "current_A": 1000.0,
            "n_cells": 10.0,
            "area_m2": 0.25,
            "polarisation": ZERO_POLARISATION,
        },
        THERMO,
    )
    assert math.isclose(result.info["U_rev_V"], reversible_voltage_gibbs(400.0), rel_tol=1e-12)


def test_pressure_correction_nernst_term() -> None:
    # The Nernst term of equation 3 at P = 30 bar, checked against the
    # hand-computed (R·T/2F)·ln[(P/P°)^1.5].
    inlet = flash_feed(EXAMPLE_FEED)
    result_off = ElectrolyserStackR1().solve(
        {"inlet": inlet},
        {"current_A": 2000.0, "n_cells": 10.0, "area_m2": 0.25, "polarisation": ZERO_POLARISATION},
        THERMO,
    )
    result_on = ElectrolyserStackR1().solve(
        {"inlet": inlet},
        {
            "current_A": 2000.0,
            "n_cells": 10.0,
            "area_m2": 0.25,
            "polarisation": ZERO_POLARISATION,
            "pressure_correction": True,
        },
        THERMO,
    )
    expected_shift = (R * 298.15 / (2.0 * FARADAY)) * 1.5 * math.log(3.0e6 / P_REF)
    assert result_on.info["U_rev_V"] == pytest.approx(result_off.info["U_rev_V"] + expected_shift, rel=1e-12)


# --- Refusals: one test per refusal-table row of the spec. ------------------


def test_refuses_nonpositive_area() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    with pytest.raises(ElectrolyserError, match="area_m2"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 10.0,
                "area_m2": 0.0,
                "polarisation": TEST_POLARISATION,
            },
            THERMO,
        )


def test_refuses_nonpositive_current() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    with pytest.raises(ElectrolyserError, match="current_A"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 0.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": TEST_POLARISATION,
            },
            THERMO,
        )


def test_refuses_fewer_than_one_cell() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    with pytest.raises(ElectrolyserError, match="n_cells"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 0.5,
                "area_m2": 0.25,
                "polarisation": TEST_POLARISATION,
            },
            THERMO,
        )


def test_refuses_T_C_at_or_below_zero_with_t2_t3() -> None:
    # T = 273.15 K -> T_C = 0 degC; the t2/T_C + t3/T_C^2 terms diverge.
    inlet = flash_feed({"T": 273.15, "P": 1.0e5, "molar_flow": 10.0, "composition": {"H2O": 1.0}})
    with pytest.raises(ElectrolyserError, match="T_C"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 1000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": TEST_POLARISATION,  # t2 = 8.4, t3 = 247.0 nonzero
            },
            THERMO,
        )


def test_refuses_nonpositive_activation_argument() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    # t1 = -1 m^2/A at i = 8000 A/m^2: (t1 + 0 + 0)·i + 1 = -7999 < 0.
    with pytest.raises(ElectrolyserError, match="activation term"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": {"r1": 0.0, "r2": 0.0, "s": 0.185, "t1": -1.0, "t2": 0.0, "t3": 0.0},
            },
            THERMO,
        )


def test_refuses_two_phase_inlet() -> None:
    # A directly assembled two-phase state (a pure-component PT flash sits on
    # the saturation line only at exactly the two-phase boundary, so the
    # refusal branch is reached by stating the quality).
    inlet = StreamState(
        T=400.0,
        P=2.4e5,
        molar_flow=20.0,
        composition={"H2O": 1.0},
        vapor_fraction=0.5,
        enthalpy=0.0,
        entropy=0.0,
    )
    with pytest.raises(ElectrolyserError, match="two-phase"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 1000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": ZERO_POLARISATION,
            },
            THERMO,
        )


def test_refuses_liquid_inlet_without_saturation_pressure() -> None:
    inlet = flash_feed(EXAMPLE_FEED)  # liquid at 298.15 K, 3 MPa
    with pytest.raises(ElectrolyserError, match="saturation pressure"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": ZERO_POLARISATION,
            },
            NoPsatThermo(),
        )


def test_refuses_T_K_different_from_inlet() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    with pytest.raises(ElectrolyserError, match="T_K"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": ZERO_POLARISATION,
                "T_K": 350.0,
            },
            THERMO,
        )


def test_refuses_ungated_ulleberg2003_preset() -> None:
    inlet = flash_feed(EXAMPLE_FEED)
    with pytest.raises(ElectrolyserError, match="preset"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 2000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": "ulleberg2003",
            },
            THERMO,
        )


def test_r0_refusals_propagate() -> None:
    # H2 already in the feed: R0's refusal, unchanged, as a plain ValueError.
    feed = {"T": 400.0, "P": 1.0e5, "molar_flow": 20.0, "composition": {"H2O": 0.9, "H2": 0.1}}
    inlet = flash_feed(feed)
    with pytest.raises(ValueError, match="H2"):
        ElectrolyserStackR1().solve(
            {"inlet": inlet},
            {
                "current_A": 1000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": ZERO_POLARISATION,
            },
            THERMO,
        )
    # Water short: 0.01 mol/s H2O cannot feed 1000 A at N = 10.
    tiny = flash_feed({"T": 298.15, "P": 3.0e6, "molar_flow": 0.01, "composition": {"H2O": 1.0}})
    with pytest.raises(ValueError, match="H2O"):
        ElectrolyserStackR1().solve(
            {"inlet": tiny},
            {
                "current_A": 1000.0,
                "n_cells": 10.0,
                "area_m2": 0.25,
                "polarisation": ZERO_POLARISATION,
            },
            THERMO,
        )
