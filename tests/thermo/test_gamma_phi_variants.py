"""T-dependent NRTL and UNIQUAC, NRTL-SAC and the Wilson liquid-reference rows.

Anchors: methanol/water at 101.325 kPa from Gao (2012), x 0.3442, T 349.05 K, y 0.7197
(data/validation/gamma_phi/cases.yaml); the ethanol/water 1-atm azeotrope 351.35 K,
x 0.8947 (the Margules row's fit point, the Edinburgh compilation).
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from thermo.nrtl import NRTL

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo.gamma_phi import _flasher_for
from ngdesign.thermo.ge_models import NRTL_SAC_SEGMENTS, NrtlSac


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


def _sac(cids: tuple[str, str], x1: float, T: float = 298.15) -> NrtlSac:
    flasher = _flasher_for("nrtl_sac", "ideal", tuple(sorted(cids)))
    model = flasher.liquid.GibbsExcessModel if hasattr(flasher, "liquid") else None
    assert isinstance(model, NrtlSac)
    ordered = tuple(sorted(cids))
    xs = [x1, 1.0 - x1] if ordered[0] == cids[0] else [1.0 - x1, x1]
    return model.to_T_xs(T, xs)


def test_nrtl_tdep_near_the_gao_data_and_differs_from_the_two_parameter_row() -> None:
    """Regression pin of the measured point, not an agreement claim.

    Before the phi_sat fix (7c5aca9) this point gave 349.22 K / y 0.7049, inside the
    original 1.0 K / 0.015 bands; that agreement leaned on the missing liquid phi_sat.
    The IUPAC source labels the parameters "NRTL/HOC" (HOC vapour, with the HOC pure
    fugacity), so the phi_sat-carrying pairing is the one they belong to. With it the
    point is 350.249 K / y 0.6947 against Gao's 349.05 K / 0.7197: bubble T inside the
    0.5 % validation band, y 0.025 outside 0.02 (assessed in the row). The shipped
    orientation still lands nearer the Gao isobar than the reversed one (8 points: mean
    |dT| 0.49 vs 1.41 K, mean |dy| 0.012 vs 0.025, measured 2026-11-04).
    """
    z = {"MeOH": 0.3442, "H2O": 0.6558}
    point = _pkg("nrtl_tdep_hoc").bubble_point(z, P=101325.0)
    assert point.T == pytest.approx(350.249, abs=0.01)
    assert point.incipient_composition["MeOH"] == pytest.approx(0.6947, abs=0.001)
    assert _pkg("nrtl_hoc").bubble_point(z, P=101325.0).T != pytest.approx(point.T, abs=1e-3)


def test_nrtl_tdep_tau_moves_with_temperature_in_the_two_terms() -> None:
    flasher = _flasher_for("nrtl_tdep", "hoc", ("H2O", "MeOH"))
    model = flasher.liquid.GibbsExcessModel
    low, high = model.to_T_xs(320.0, [0.5, 0.5]).taus(), model.to_T_xs(380.0, [0.5, 0.5]).taus()
    # ids sort H2O first: tau[1][0] is MeOH -> H2O, a = -5.70743, b = 1538.74.
    assert low[1][0] == pytest.approx(-5.70743 + 1538.74 / 320.0)
    assert high[1][0] == pytest.approx(-5.70743 + 1538.74 / 380.0)


def test_uniquac_tdep_reproduces_the_azeotrope_the_parameters_were_not_fitted_to() -> None:
    """Regressed at 13-33 kPa by the source; 101.325 kPa is outside its data."""
    z = {"EtOH": 0.8947, "H2O": 0.1053}
    point = _pkg("uniquac_tdep_ig").bubble_point(z, P=101325.0)
    assert point.T == pytest.approx(351.35, abs=0.5)
    assert point.incipient_composition["EtOH"] == pytest.approx(0.8947, abs=0.01)


def test_tdep_rows_refuse_a_pair_they_have_no_parameters_for() -> None:
    with pytest.raises(ValueError, match="tdep_pairs.yaml"):
        _pkg("nrtl_tdep_hoc").bubble_point({"EtOH": 0.5, "H2O": 0.5}, P=101325.0)


def test_sac_water_hexane_is_binary_nrtl_on_the_x_z_pair() -> None:
    """r = 1 for both: the segment model collapses to NRTL, combinatorial term zero."""
    x_hexane = 0.3
    model = _sac(("n-hexane", "H2O"), x_hexane)
    nrtl = NRTL(
        T=298.15,
        xs=[x_hexane, 1.0 - x_hexane],
        tau_as=[[0.0, 6.547], [10.949, 0.0]],
        alpha_cs=[[0.0, 0.2], [0.2, 0.0]],
    )
    water_first = model.xs[0] != pytest.approx(x_hexane)
    got = model.ln_gammas()
    ln_gamma = [math.log(g) for g in nrtl.gammas()]
    expected = [ln_gamma[1], ln_gamma[0]] if water_first else ln_gamma
    assert got == pytest.approx(expected, rel=1e-9)


def test_sac_pure_limit_and_gibbs_duhem() -> None:
    model = _sac(("MeOH", "H2O"), 0.4)
    assert model.to_T_xs(298.15, [1.0, 0.0]).ln_gammas()[0] == pytest.approx(0.0, abs=1e-12)
    step = 1e-5
    x1 = 0.4
    up = model.to_T_xs(298.15, [x1 + step, 1.0 - x1 - step]).ln_gammas()
    dn = model.to_T_xs(298.15, [x1 - step, 1.0 - x1 + step]).ln_gammas()
    residual = x1 * (up[0] - dn[0]) + (1.0 - x1) * (up[1] - dn[1])
    assert residual / (2.0 * step) == pytest.approx(0.0, abs=1e-6)


def test_sac_gamma_has_no_temperature_dependence_and_ge_is_entropic() -> None:
    a, b = _sac(("MeOH", "H2O"), 0.4, 300.0), _sac(("MeOH", "H2O"), 0.4, 360.0)
    assert a.ln_gammas() == pytest.approx(b.ln_gammas())
    assert a.dGE_dT() == pytest.approx(a.GE() / 300.0)


def test_sac_segment_table_order_and_refusal() -> None:
    assert NRTL_SAC_SEGMENTS == ("x", "y-", "y+", "z")
    with pytest.raises(ValueError, match="segment numbers"):
        _pkg("nrtl_sac_ig").bubble_point({"nC4": 0.5, "H2O": 0.5}, T=300.0)


def test_sac_is_a_prediction_with_the_right_sign_for_positive_deviation() -> None:
    """Ethanol/water: above Raoult, and within 3 K of the azeotrope bubble point."""
    z = {"EtOH": 0.8947, "H2O": 0.1053}
    point = _pkg("nrtl_sac_ig").bubble_point(z, P=101325.0)
    assert point.T == pytest.approx(351.35, abs=3.0)
    assert _pkg("nrtl_sac_ig").flash_pt({"EtOH": 0.5, "H2O": 0.5}, 355.0, 101325.0, 1.0) != _pkg(
        "nrtl_ig"
    ).flash_pt({"EtOH": 0.5, "H2O": 0.5}, 355.0, 101325.0, 1.0)


@pytest.mark.parametrize("row", ["wilson_lr_ig", "wilson_glr_ig"])
def test_wilson_lr_keeps_the_k_values(row: str) -> None:
    z = {"MeOH": 0.5, "H2O": 0.5}
    a = _pkg("wilson_ig").bubble_point(z, P=101325.0)
    b = _pkg(row).bubble_point(z, P=101325.0)
    assert b.T == pytest.approx(a.T, rel=1e-9)


def test_wilson_lr_liquid_cp_is_the_databank_liquid_cp() -> None:
    """Water at 350 K: 75.5 J/(mol K) (IAPWS-95, read once through CoolProp); plain route misses."""
    z = {"H2O": 1.0}
    lr = _pkg("wilson_lr_ig").phase_props(z, 350.0, 1e5, PhaseKind.AQUEOUS).cp
    plain = _pkg("wilson_ig").phase_props(z, 350.0, 1e5, PhaseKind.AQUEOUS).cp
    assert lr == pytest.approx(75.5, rel=0.01)
    assert abs(lr - 75.5) < abs(plain - 75.5)


def test_wilson_lr_meets_the_plain_route_at_the_reference_temperature() -> None:
    z = {"MeOH": 0.5, "H2O": 0.5}
    lr = _pkg("wilson_lr_ig").phase_props(z, 298.15, 1e5, PhaseKind.AQUEOUS)
    plain = _pkg("wilson_ig").phase_props(z, 298.15, 1e5, PhaseKind.AQUEOUS)
    assert lr.enthalpy == pytest.approx(plain.enthalpy, abs=1e-6)
    assert lr.entropy == pytest.approx(plain.entropy, abs=1e-9)
    away = 340.0
    assert _pkg("wilson_lr_ig").phase_props(z, away, 1e5, PhaseKind.AQUEOUS).enthalpy != pytest.approx(
        _pkg("wilson_ig").phase_props(z, away, 1e5, PhaseKind.AQUEOUS).enthalpy, abs=1.0
    )


def test_wilson_lr_cp_is_the_slope_of_its_enthalpy() -> None:
    z = {"MeOH": 0.5, "H2O": 0.5}
    pkg = _pkg("wilson_lr_ig")
    d_t = 0.1
    hi = pkg.phase_props(z, 330.0 + d_t, 1e5, PhaseKind.AQUEOUS).enthalpy
    lo = pkg.phase_props(z, 330.0 - d_t, 1e5, PhaseKind.AQUEOUS).enthalpy
    assert pkg.phase_props(z, 330.0, 1e5, PhaseKind.AQUEOUS).cp == pytest.approx(
        (hi - lo) / (2.0 * d_t), rel=1e-3
    )


def test_wilson_glr_leaves_light_components_on_the_plain_route() -> None:
    """n-Butane boils below 298.15 K: only MeOH moves to the liquid route under GLR."""
    z = {"MeOH": 0.5, "nC4": 0.5}
    kind = PhaseKind.HC_LIQUID
    T, P = 330.0, 2e6
    plain = _pkg("wilson_ig").phase_props(z, T, P, kind).enthalpy
    lr = _pkg("wilson_lr_ig").phase_props(z, T, P, kind).enthalpy
    glr = _pkg("wilson_glr_ig").phase_props(z, T, P, kind).enthalpy
    assert len({round(plain, 3), round(lr, 3), round(glr, 3)}) == 3
    water = {"MeOH": 0.5, "H2O": 0.5}
    a = _pkg("wilson_lr_ig").phase_props(water, T, 1e5, PhaseKind.AQUEOUS).enthalpy
    assert _pkg("wilson_glr_ig").phase_props(water, T, 1e5, PhaseKind.AQUEOUS).enthalpy == pytest.approx(a)


# Siimer et al. 2002 (doi:10.3176/chem.2002.1.02) Table 3 and Kirss et al. 2002
# (doi:10.3176/chem.2002.4.03) Table 7: the papers' own activity coefficients from their
# Table 4 Wilson coefficients, (x1, x2, T, gamma1, gamma2, gamma3). Siimer's gammas are
# at Tcalc, Kirss's at the experimental T (pressure column computed there).
_SIIMER = (
    ("2-hexanone", "o-xylene", "nonane"),
    1e-3,
    [
        (0.333, 0.334, 365.39, 1.218, 1.022, 1.227),
        (0.756, 0.122, 360.66, 1.028, 1.074, 1.776),
        (0.125, 0.750, 413.58, 1.169, 1.004, 1.222),
        (0.250, 0.250, 410.12, 1.287, 1.043, 1.082),
    ],
)
_KIRSS = (
    ("toluene", "p-xylene", "1,2-dichloroethane"),
    5e-5,
    [
        (0.289, 0.289, 333.92, 0.9946, 0.9811, 1.0076),
        (0.553, 0.277, 343.22, 0.9958, 0.9703, 1.0075),
        (0.133, 0.734, 394.83, 0.9631, 0.9950, 0.9352),
    ],
)


@pytest.mark.parametrize("table", [_SIIMER, _KIRSS])
def test_wilson_tdep_reproduces_the_papers_own_activity_coefficients(table: Any) -> None:
    """With the standard (x_i + Lambda_ij x_j) form; the papers' Eq. 1 prints a minus."""
    names, digits, rows = table  # printed last digit; Siimer 1e-3 also absorbs its rounded Tcalc
    ids = tuple(sorted(names))
    model = _flasher_for("wilson_tdep", "ideal", ids).liquid.GibbsExcessModel
    for x1, x2, T, *gammas in rows:
        x = dict(zip(names, (x1, x2, 1.0 - x1 - x2), strict=True))
        got = dict(zip(ids, model.to_T_xs(T, [x[c] for c in ids]).gammas(), strict=True))
        for name, expected in zip(names, gammas, strict=True):
            assert got[name] == pytest.approx(expected, abs=digits), (name, x1, x2, T)


@pytest.mark.parametrize(
    ("z", "P", "T_exp"),
    [
        ({"2-hexanone": 0.522, "o-xylene": 0.478}, 101320.0, 406.23),
        ({"2-hexanone": 0.503, "nonane": 0.497}, 26660.0, 362.18),
        ({"toluene": 0.499, "p-xylene": 0.501}, 101320.0, 395.64),
        ({"toluene": 0.475, "1,2-dichloroethane": 0.525}, 101320.0, 366.49),
        ({"2-hexanone": 0.333, "o-xylene": 0.334, "nonane": 0.333}, 101320.0, 408.03),
    ],
)
def test_wilson_tdep_bubble_point_lands_on_the_measured_boiling_point(
    z: dict[str, float], P: float, T_exp: float
) -> None:
    """Measured T-x points (Siimer Tables 2-3, Kirss Table 2) through the package, with the
    databank vapour pressures instead of the papers' Antoine fits: within 0.3 K (measured
    -0.11 to +0.26 K). The ternary point is a prediction from the three binaries."""
    assert _pkg("wilson_tdep_ig").bubble_point(z, P=P).T == pytest.approx(T_exp, abs=0.3)


def test_wilson_tdep_refuses_a_pair_outside_its_table() -> None:
    with pytest.raises(ValueError, match="tdep_pairs.yaml"):
        _pkg("wilson_tdep_ig").bubble_point({"toluene": 0.5, "nonane": 0.5}, P=101325.0)
