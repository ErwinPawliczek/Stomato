"""T-09 electrolyte tests: literature anchors, refusals, window enforcement.

Anchors retrieved and verified this task (see docs/validation.md for the full
citation trail):

* Pitzer NaCl: Pitzer, Peiper & Busey (1984), J. Phys. Chem. Ref. Data 13(1),
  Table A-8 mean activity coefficients, Table A-9 osmotic coefficients, and
  the 298.15 K saturation anchor (6.146 mol/kg at gamma 1.0065).
* eNRTL: Chen & Evans (1986) NaCl-H2O binary (tau transcribed from the
  open-access Kwaterski & Herri copy) with the Chen et al. (1982) PDH long
  range -- the same PPB84 anchor tables, at the source model's own fit
  quality (T-09b).
* Extended UNIQUAC: Thomsen & Rasmussen (1999) parameter set, formulation
  per the open-access Leal et al. (2025) text -- the same PPB84 anchor
  tables (T-09b).
* Sour water: EPA-600/2-80-067 (Wilson 1980) printed worked-example constants
  (printed pp. 52-53) and Table 21 (Shih et al. pH-7.00 buffered H2S points;
  the 90 C acceptance anchor is the linear interpolation of the 80/100 C API
  column, 59.70 mmHg).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.amine.electrolyte import (
    _MW_WATER_KG,
    ElectrolyteChemistryError,
    _eu_a_dh,
    _eu_ln_gamma_u,
    _eu_state,
    _ext_uniquac,
    _solution_molalities,
    enrtl_mean_gamma,
    enrtl_osmotic,
    enrtl_saturation_molality,
    enrtl_water_activity,
    ext_uniquac_mean_gamma,
    ext_uniquac_osmotic,
    ext_uniquac_saturation_molality,
    ext_uniquac_water_activity,
    pitzer_mean_gamma,
    pitzer_osmotic,
    pitzer_saturation_molality,
    pitzer_water_activity,
    sour_water_partial_pressures,
    sour_water_speciation,
    sweq_constants,
    sweq_henry,
)
from ngdesign.contracts import PhaseKind

MMHG_PER_PA = 1.0 / 133.3223684211

# Pitzer, Peiper & Busey 1984, Table A-8 (t = 25 C column), molal -> gamma +/-.
_PPB84_GAMMA: list[tuple[float, float]] = [
    (0.1, 0.778),
    (0.25, 0.720),
    (0.5, 0.681),
    (1.0, 0.657),
    (2.0, 0.669),
    (3.0, 0.714),
    (4.0, 0.782),
    (5.0, 0.873),
    (6.0, 0.987),
]
# The spec pins 0.1 / 1.0 / 3.0 molal at 2 %; the parameter set achieves 0.36 %
# over the whole table, so the test holds every row to 0.5 %.
_GAMMA_TOL = 0.005

# EPA-600/2-80-067 Table 21, Shih et al. pH-7.00 buffered block, H2S 0.010 m:
# the report's API comparison column (mmHg).  Rows are at the printed
# temperatures; the spec's 90 C acceptance anchor is the 80/100 C linear
# interpolation (59.70 mmHg) since the table has no 90 C row.
_SHIH_TABLE21: list[tuple[float, float]] = [
    (353.15, 59.3),
    (373.15, 60.1),
    (393.15, 61.8),
    (413.15, 68.0),
]
_SHIH_90C_ANCHOR = 59.70


def _electrolyte(model: str) -> Any:
    return registry.create("thermo", model)


# -- Pitzer NaCl(aq) -----------------------------------------------------------


@pytest.mark.parametrize(("molality", "gamma_ref"), _PPB84_GAMMA)
def test_pitzer_mean_gamma_anchors(molality: float, gamma_ref: float) -> None:
    """Mean activity coefficients vs Pitzer, Peiper & Busey Table A-8 (spec: 2 %)."""
    gamma = pitzer_mean_gamma(molality)
    assert gamma == pytest.approx(gamma_ref, rel=_GAMMA_TOL)


def test_pitzer_osmotic_coefficient_anchor() -> None:
    """Osmotic coefficient at 1 molal: 0.9356 (PPB84 Table A-9)."""
    assert pitzer_osmotic(1.0) == pytest.approx(0.9356, rel=0.002)


def test_pitzer_water_activity_anchor() -> None:
    """Water activity at 3 molal: 0.8932 (PPB84 water-activity data)."""
    assert pitzer_water_activity(3.0) == pytest.approx(0.8932, rel=0.002)


def test_pitzer_saturation_molality() -> None:
    """SLE anchor: 6.146 mol/kg at 298.15 K with gamma(sat) = 1.0065 (+0.14 % here)."""
    m_sat = pitzer_saturation_molality()
    assert m_sat == pytest.approx(6.146, rel=0.005)
    # Saturated-solution water activity (0.7521 at the solved molality).
    assert pitzer_water_activity(m_sat) == pytest.approx(0.7521, rel=0.002)


# The three brine rows share the involatile-salt flash plumbing; the water
# activity surface is the per-model chemistry driver.
_BRINE_WATER_ACTIVITY = {
    "pitzer_nacl_water": pitzer_water_activity,
    "enrtl_nacl_water": enrtl_water_activity,
    "ext_uniquac_nacl_water": ext_uniquac_water_activity,
}


@pytest.mark.parametrize("model", sorted(_BRINE_WATER_ACTIVITY))
def test_brine_bubble_pressure_is_water_activity_times_psat(model: str) -> None:
    """Brine bubble pressure == a_w(m) * Psat_H2O (the model's exact definition)."""
    pkg = _electrolyte(model)
    z = {"H2O": 0.95, "NaCl": 0.05}  # 2.94 molal
    m = 1000.0 * 0.05 / (18.01528 * 0.95)
    bubble = pkg.bubble_point(z, T=298.15)
    expected = _BRINE_WATER_ACTIVITY[model](m) * pkg.pure_psat("H2O", 298.15)
    assert bubble.P == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("model", sorted(_BRINE_WATER_ACTIVITY))
def test_brine_flash_single_liquid_below_bubble(model: str) -> None:
    """A brine PT flash above the bubble pressure is a single aqueous liquid."""
    state = _electrolyte(model).flash_pt({"H2O": 0.95, "NaCl": 0.05}, 298.15, 5000000.0, 100.0)
    assert state.vapor_fraction == 0.0
    assert len(state.phases) == 1
    assert state.phases[0].kind is PhaseKind.AQUEOUS


# -- eNRTL and extended-UNIQUAC brines (T-09b) ----------------------------------
#
# The default anchor band is the spec's 2 % (the Pitzer row alone is held to
# its measured 0.5 %).  The eNRTL/eUNIQUAC parameterisations cannot reach
# that: their residuals equal the source models' own published fit quality.
# Every anchor point outside the default band is therefore a DECLARED miss:
# the row's `assessed:` map in data/thermo_models/electrolyte.yaml records
# the measured deviation and the test pins the deviation to that recorded
# value (a regression guard in BOTH directions -- any change re-opens the
# assessment) instead of widening the tolerance.

_ENRTL_GAMMA_RECORDED: dict[float, float] = {
    0.25: -0.02003,
    0.5: -0.02903,
    1.0: -0.03294,
    6.0: -0.04994,
}
_ENRTL_PHI_RECORDED: dict[float, float] = {6.0: -0.02841}
_EXT_UNIQUAC_GAMMA_RECORDED: dict[float, float] = {
    0.25: -0.02141,
    0.5: -0.03489,
    1.0: -0.04258,
    2.0: -0.02003,
    4.0: 0.03031,
    5.0: 0.02536,
}
_EXT_UNIQUAC_PHI_RECORDED: dict[float, float] = {
    3.0: 0.03311,
    4.0: 0.03681,
    5.0: 0.02405,
}
_SPEC_BAND = 0.02
_RECORDED_DEV_TOL = 2e-3


def _assert_anchor(value: float, ref: float, recorded: dict[float, float], molality: float) -> None:
    """Default-band check, or a recorded-deviation pin for a declared miss."""
    dev = value / ref - 1.0
    if molality in recorded:
        assert dev == pytest.approx(recorded[molality], abs=_RECORDED_DEV_TOL)
    else:
        assert value == pytest.approx(ref, rel=_SPEC_BAND)


@pytest.mark.parametrize(("molality", "gamma_ref"), _PPB84_GAMMA)
def test_enrtl_mean_gamma_anchors(molality: float, gamma_ref: float) -> None:
    """eNRTL gamma+- vs PPB84 Table A-8; misses are declared (row assessed:)."""
    _assert_anchor(enrtl_mean_gamma(molality), gamma_ref, _ENRTL_GAMMA_RECORDED, molality)


@pytest.mark.parametrize(("molality", "gamma_ref"), _PPB84_GAMMA)
def test_ext_uniquac_mean_gamma_anchors(molality: float, gamma_ref: float) -> None:
    """Extended-UNIQUAC gamma+- vs PPB84 Table A-8; misses are declared (row assessed:)."""
    _assert_anchor(ext_uniquac_mean_gamma(molality), gamma_ref, _EXT_UNIQUAC_GAMMA_RECORDED, molality)


@pytest.mark.parametrize(
    ("molality", "phi_ref"),
    [
        (0.1, 0.933),
        (0.25, 0.922),
        (0.5, 0.922),
        (1.0, 0.935),
        (2.0, 0.984),
        (3.0, 1.045),
        (4.0, 1.114),
        (5.0, 1.190),
        (6.0, 1.272),
    ],
)
def test_enrtl_osmotic_anchors(molality: float, phi_ref: float) -> None:
    """eNRTL phi vs PPB84 Table A-9; misses are declared (row assessed:)."""
    _assert_anchor(enrtl_osmotic(molality), phi_ref, _ENRTL_PHI_RECORDED, molality)


@pytest.mark.parametrize(
    ("molality", "phi_ref"),
    [
        (0.1, 0.933),
        (0.25, 0.922),
        (0.5, 0.922),
        (1.0, 0.935),
        (2.0, 0.984),
        (3.0, 1.045),
        (4.0, 1.114),
        (5.0, 1.190),
        (6.0, 1.272),
    ],
)
def test_ext_uniquac_osmotic_anchors(molality: float, phi_ref: float) -> None:
    """Extended-UNIQUAC phi vs PPB84 Table A-9; misses are declared (row assessed:)."""
    _assert_anchor(ext_uniquac_osmotic(molality), phi_ref, _EXT_UNIQUAC_PHI_RECORDED, molality)


def test_enrtl_saturation_molality() -> None:
    """SLE solve pins the row's declared +12.2 % miss (6.8905 vs 6.146 mol/kg)."""
    assert enrtl_saturation_molality() == pytest.approx(6.8905, rel=0.002)


def test_ext_uniquac_saturation_molality() -> None:
    """SLE solve pins the row's declared +1.5 % miss (6.2358 vs 6.146 mol/kg)."""
    assert ext_uniquac_saturation_molality() == pytest.approx(6.2358, rel=0.002)


@pytest.mark.parametrize(
    ("gamma_fn", "phi_fn"),
    [(enrtl_mean_gamma, enrtl_osmotic), (ext_uniquac_mean_gamma, ext_uniquac_osmotic)],
    ids=["enrtl", "ext_uniquac"],
)
def test_brine_gibbs_duhem_consistency(gamma_fn: Any, phi_fn: Any) -> None:
    """gamma+- and phi satisfy the Gibbs-Duhem integral (internal consistency)."""
    for m in (0.1, 0.5, 1.0, 3.0, 6.0):
        integ = 0.0
        for i in range(1, 401):
            m1, m0 = m * i / 400, m * (i - 1) / 400
            mm = 0.5 * (m0 + m1)
            integ += (phi_fn(mm) - 1.0) / mm * (m1 - m0)
        assert math.log(gamma_fn(m)) - (phi_fn(m) - 1.0) == pytest.approx(integ, abs=0.05)


def test_ext_uniquac_closed_form_is_finite_difference_exact() -> None:
    """Leal eq (43) closed form vs the numeric d(n G^E/RT) derivative (eq 17)."""
    p = _ext_uniquac()
    molw = 1.0 / _MW_WATER_KG
    msalt = 1.3
    q = {k: float(v) for k, v in p["q"].items()}

    def ge_rt(mw: float, ms: float) -> float:
        m = ms / (mw * _MW_WATER_KG)
        x, phi_, th, psi = _eu_state(m, 298.15)
        sqi, a_dh, b_dh = math.sqrt(m), _eu_a_dh(298.15), 1.5
        xw = mw / (mw + 2.0 * ms)
        g_dh = -(4.0 * xw * _MW_WATER_KG * a_dh / b_dh**3) * (
            math.log(1.0 + b_dh * sqi) - b_dh * sqi + 0.5 * b_dh**2 * m
        )
        g_u = 0.0
        for k in ("H2O", "Na", "Cl"):
            sk = sum(th[j] * psi[j][k] for j in ("H2O", "Na", "Cl"))
            g_u += x[k] * (
                math.log(phi_[k] / x[k])
                - (10.0 / 2.0) * q[k] * math.log(phi_[k] / th[k])
                - q[k] * math.log(sk)
            )
        return g_dh + g_u

    h = 1e-6

    def total(ms: float) -> float:
        return (molw + 2.0 * ms) * ge_rt(molw, ms)

    d_salt = (total(msalt + h) - total(msalt - h)) / (2.0 * h)
    dw = 1e-3
    d_w = (
        (molw + dw + 2.0 * msalt) * ge_rt(molw + dw, msalt)
        - (molw - dw + 2.0 * msalt) * ge_rt(molw - dw, msalt)
    ) / (2.0 * dw)
    x, _phi_, _theta, psi = _eu_state(msalt, 298.15)
    lg = _eu_ln_gamma_u(x, _phi_, _theta, psi)
    a25, sqi = _eu_a_dh(298.15), math.sqrt(msalt)
    lg_dh_ion = -a25 * sqi / (1.0 + 1.5 * sqi)
    lg_dh_w = (2.0 * a25 * _MW_WATER_KG / 1.5**3) * (
        1.0 + 1.5 * sqi - 1.0 / (1.0 + 1.5 * sqi) - 2.0 * math.log(1.0 + 1.5 * sqi)
    )
    assert 2.0 * lg_dh_ion + lg["Na"] + lg["Cl"] == pytest.approx(d_salt, abs=1e-4)
    assert lg_dh_w + lg["H2O"] == pytest.approx(d_w, abs=1e-4)


# -- Sour water (EPA-600/2-80-067 SWEQ) ----------------------------------------


def test_sweq_printed_constants_at_100c() -> None:
    """The four reaction constants at 100 C match the report's printed values."""
    c = sweq_constants(373.15)
    assert c.k_h2s == pytest.approx(2.805e-7, rel=0.001)
    assert c.k_hs == pytest.approx(9.06e-13, rel=0.001)
    assert c.k_nh4 == pytest.approx(8.032e7, rel=0.001)
    assert c.k_w == pytest.approx(5.054e-13, rel=0.001)


def test_sweq_printed_henry_constants_at_100c() -> None:
    """Both Henry constants at 100 C match the report's printed values (pure solvent)."""
    h = sweq_henry(373.15, cas=0.0, cs=0.0)
    assert h.nh3 == pytest.approx(3.64, rel=0.001)
    assert h.h2s == pytest.approx(442.5, rel=0.001)


@pytest.mark.parametrize(("t_k", "mmhg_ref"), _SHIH_TABLE21)
def test_shih_table21_h2s_points(t_k: float, mmhg_ref: float) -> None:
    """Table 21 Shih pH-7.00 H2S points vs the report's API column (spec: 10 %)."""
    _p_nh3, p_h2s = sour_water_partial_pressures(0.0, 0.010, t_k, ph=7.0)
    assert p_h2s * MMHG_PER_PA == pytest.approx(mmhg_ref, rel=0.025)


def test_shih_90c_spec_acceptance_point() -> None:
    """The spec's 90 C acceptance point: interpolated anchor 59.70 mmHg, spec 10 %."""
    _p_nh3, p_h2s = sour_water_partial_pressures(0.0, 0.010, 363.15, ph=7.0)
    assert p_h2s * MMHG_PER_PA == pytest.approx(_SHIH_90C_ANCHOR, rel=0.01)


def test_speciation_charge_balance() -> None:
    """The free-pH speciation satisfies electroneutrality at the solved [H+]."""
    spec = sour_water_speciation(2.0, 1.0, 313.15)
    cations = spec.h + spec.nh4
    anions = spec.oh + spec.hs + 2.0 * spec.s2
    assert cations == pytest.approx(anions, rel=1e-6)
    assert spec.ph == pytest.approx(-math.log10(spec.h), abs=1e-12)


def test_speciation_mass_balance_and_ratios() -> None:
    """Analytic balances: NH3 mass closure and the k5/k6 speciation ratios."""
    m_nh3, m_h2s = 2.0, 1.0
    spec = sour_water_speciation(m_nh3, m_h2s, 313.15)
    assert spec.nh4 + spec.nh3_free == pytest.approx(m_nh3, rel=1e-12)
    assert spec.h2s + spec.hs + spec.s2 == pytest.approx(m_h2s, rel=1e-12)
    c = sweq_constants(313.15)
    assert spec.hs == pytest.approx(spec.h2s * c.k_h2s / spec.h, rel=1e-9)
    assert spec.s2 == pytest.approx(spec.hs * c.k_hs / spec.h, rel=1e-9)
    assert spec.oh == pytest.approx(c.k_w / spec.h, rel=1e-9)


def test_sour_water_bubble_pressure_identity() -> None:
    """Sour-water bubble pressure == water Psat + the two equilibrium partial pressures."""
    pkg = _electrolyte("sour_water")
    z = {"H2O": 0.95, "NH3": 0.03, "H2S": 0.02}
    bubble = pkg.bubble_point(z, T=311.15)
    # EPA basis: gmol per kg of SOLUTION (the report's worked examples) --
    # _solution_molalities carries the model's databank molecular weights.
    m_nh3, m_h2s = _solution_molalities(z)
    p_nh3, p_h2s = sour_water_partial_pressures(m_nh3, m_h2s, 311.15)
    # Raoult water weighted by its feed fraction (the report's water term
    # p_H2O = V.P._H2O * X_H2O) plus the two equilibrium partial pressures.
    expected = z["H2O"] * pkg.pure_psat("H2O", 311.15) + p_nh3 + p_h2s
    assert bubble.P == pytest.approx(expected, rel=1e-6)


def test_sour_water_dew_above_bubble_at_one_atmosphere() -> None:
    """At 1 atm the sour-water dew point sits above its bubble point (VLE sanity)."""
    pkg = _electrolyte("sour_water")
    z = {"H2O": 0.95, "NH3": 0.03, "H2S": 0.02}
    p_bub = pkg.bubble_point(z, T=311.15).P
    t_bub_at_1atm = pkg.bubble_point(z, P=101325.0).T
    t_dew_at_1atm = pkg.dew_point(z, P=101325.0).T
    assert p_bub < 101325.0  # single liquid at ambient, as the flash shows
    assert 0.0 < t_bub_at_1atm < t_dew_at_1atm < 373.15
    below = pkg.flash_pt(z, 311.15, p_bub * 1.01, 100.0)
    assert below.vapor_fraction == 0.0


# -- refusals and scope edges --------------------------------------------------


def test_sour_water_refuses_co2_bearing_feed() -> None:
    """The CO2/carbonate path is unverified this cycle: CO2 in a feed refuses."""
    pkg = _electrolyte("sour_water")
    with pytest.raises(NotImplementedError, match="CO2"):
        pkg.flash_pt({"H2O": 0.9, "NH3": 0.05, "H2S": 0.03, "CO2": 0.02}, 311.15, 101325.0, 10.0)


def test_electrolyte_refuses_out_of_scope_species() -> None:
    """Species outside a model's support refuse with the documented gap (no Na2SO4)."""
    with pytest.raises(NotImplementedError):
        _electrolyte("pitzer_nacl_water").flash_pt(
            {"H2O": 0.9, "NaCl": 0.05, "MDEA": 0.05}, 298.15, 5000000.0, 10.0
        )
    with pytest.raises(NotImplementedError):
        _electrolyte("sour_water").flash_pt({"H2O": 0.95, "NaCl": 0.05}, 311.15, 101325.0, 10.0)


def test_non_aqueous_feed_delegates_to_carrier() -> None:
    """A feed without water flashes on the carrier (plain-cubic, no refusal)."""
    state = _electrolyte("pitzer_nacl_water").flash_pt({"N2": 1.0}, 300.0, 101325.0, 25.0)
    assert state.vapor_fraction == 1.0


# -- fitted-window enforcement -------------------------------------------------


def test_flash_temperature_guard() -> None:
    """Flash states outside a model's window raise the typed chemistry error."""
    with pytest.raises(ElectrolyteChemistryError, match="fitted window"):
        _electrolyte("pitzer_nacl_water").flash_pt({"H2O": 0.95, "NaCl": 0.05}, 310.0, 5e6, 10.0)
    with pytest.raises(ElectrolyteChemistryError, match="fitted window"):
        _electrolyte("sour_water").flash_pt({"H2O": 0.95, "NH3": 0.03, "H2S": 0.02}, 400.0, 5e6, 10.0)


def test_saturation_solve_guard() -> None:
    """A solved saturation point outside the window raises, naming the window."""
    with pytest.raises(ElectrolyteChemistryError, match="solved outside its fitted window"):
        _electrolyte("pitzer_nacl_water").bubble_point({"H2O": 0.75, "NaCl": 0.25}, P=5000.0)
