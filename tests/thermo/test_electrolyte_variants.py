"""The electrolyte variant rows: real water vapours, the bare PDH term, and solid NaCl.

Anchors: Pitzer, Peiper & Busey (1984), Table A-8 gamma+- at 25 C and the 6.146 mol/kg
solubility; the second virial coefficient of water at 298.15 K, -1241 cm3/mol from
IAPWS-95 (read once through CoolProp's Bvirial).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.amine.electrolyte import (
    ElectrolyteChemistryError,
    enrtl_crystallisation_molality,
    pdh_mean_gamma,
    pitzer_mean_gamma,
)
from ngdesign.contracts.stream import PhaseKind

T = 298.15
MW_WATER_KG = 0.018015268
IAPWS_B_298 = -1241.0e-6  # m3/mol
R = 8.31446261815324


def _z(molality: float) -> dict[str, float]:
    s = molality * MW_WATER_KG
    return {"H2O": 1.0 / (1.0 + s), "NaCl": s / (1.0 + s)}


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


def _effective_b(pkg: Any) -> float:
    """B from the slope of ln phi of pure water vapour in P."""
    lo, hi = 1000.0, 3000.0
    ln_phi = [pkg._vapour.phase_props({"H2O": 1.0}, T, p, PhaseKind.VAPOR).ln_phi["H2O"] for p in (lo, hi)]
    return float((ln_phi[1] - ln_phi[0]) / (hi - lo) * R * T)


@pytest.mark.parametrize(
    ("base", "row"),
    [
        ("enrtl_nacl_water", "enrtl_rk"),
        ("enrtl_nacl_water", "enrtl_hoc"),
        ("pitzer_nacl_water", "pitzer_hoc"),
    ],
)
def test_real_vapour_lowers_the_bubble_pressure_and_keeps_fugacities_equal(base: str, row: str) -> None:
    """Below Psat, B < 0 makes phi_sat < phi_V(P), so the brine boils at a lower pressure."""
    z = _z(1.0)
    p_base = _pkg(base).bubble_point(z, T=T).P
    pkg = _pkg(row)
    p_row = pkg.bubble_point(z, T=T).P
    assert p_row < p_base
    assert p_row > p_base * (1.0 - 2e-3)
    state = pkg.flash_pt(z, T, p_row * 0.998, 1.0)
    vapour, liquid = state.phases
    assert vapour.kind == PhaseKind.VAPOR
    assert liquid.ln_phi["H2O"] == pytest.approx(vapour.ln_phi["H2O"], abs=1e-9)


def test_hoc_sits_nearer_the_iapws_virial_than_rk() -> None:
    """HOC keeps water's dimerisation, RK cannot.

    The in-house kernel overshoots by 44 % at 298 K (-1783 vs -1241 cm3/mol, measured),
    well outside the 3 % test_virial.py pins at 373 K; the bound here records that.
    """
    hoc = _effective_b(_pkg("enrtl_hoc"))
    rk = _effective_b(_pkg("enrtl_rk"))
    assert abs(hoc - IAPWS_B_298) < abs(rk - IAPWS_B_298)
    assert hoc == pytest.approx(IAPWS_B_298, rel=0.5)


def test_vapour_properties_come_from_the_vapour_model() -> None:
    z = _z(1.0)
    p = 2900.0
    base = _pkg("enrtl_nacl_water").flash_pt(z, T, p, 1.0).phases[0]
    hoc = _pkg("enrtl_hoc").flash_pt(z, T, p, 1.0).phases[0]
    assert hoc.density > base.density


def test_ideal_vapour_rows_keep_their_k_value() -> None:
    pkg = _pkg("enrtl_nacl_water")
    assert pkg._water_fugacity_ratio(T, 2000.0) == 1.0


@pytest.mark.parametrize(("molality", "gamma_ref"), [(0.1, 0.778)])
def test_pdh_is_close_in_the_dilute_limit_and_short_of_the_full_model(
    molality: float, gamma_ref: float
) -> None:
    """Table A-8: within 2 % at 0.1 m, and the missing short-range term shows at 1 m."""
    assert pdh_mean_gamma(molality) == pytest.approx(gamma_ref, rel=0.02)
    assert pdh_mean_gamma(molality) < pitzer_mean_gamma(molality)
    assert pdh_mean_gamma(1.0) < 0.9 * pitzer_mean_gamma(1.0)


def test_pdh_limiting_law_at_extreme_dilution() -> None:
    """ln gamma+- -> -3 A_phi sqrt(I), the Debye-Hueckel limiting law, as m -> 0."""
    m = 1e-4
    assert math.log(pdh_mean_gamma(m)) == pytest.approx(-3.0 * 0.392 * math.sqrt(m), rel=0.03)


def test_pdh_refuses_above_its_cap() -> None:
    with pytest.raises(ElectrolyteChemistryError, match="dilute-solution model"):
        _pkg("pitzer_debye_huckel").flash_pt(_z(1.0), T, 1e5, 1.0)
    assert _pkg("pitzer_debye_huckel").flash_pt(_z(0.1), T, 1e5, 1.0).phases[0].kind == PhaseKind.AQUEOUS


def test_pdh_bubble_point_refuses_above_its_cap() -> None:
    """The bubble-point liquid is the feed: the flash's 0.2 mol/kg cap applies to it too."""
    pkg = _pkg("pitzer_debye_huckel")
    with pytest.raises(ElectrolyteChemistryError, match="dilute-solution model"):
        pkg.bubble_point(_z(1.0), T=T)
    assert pkg.bubble_point(_z(0.1), T=T).P > 0.0


def test_crystallisation_solubility_is_a_prediction_near_the_anchor() -> None:
    assert enrtl_crystallisation_molality() == pytest.approx(6.146, rel=0.05)


def test_solubility_surface_is_the_saturated_liquid_composition() -> None:
    """solubility(salt, T) is the salt fraction of the liquid a supersaturated flash leaves."""
    pkg = _pkg("enrtl_crystallisation")
    x_sat = pkg.solubility("NaCl", T)
    s = enrtl_crystallisation_molality() * MW_WATER_KG
    assert x_sat == pytest.approx(s / (1.0 + s), rel=1e-6)
    liquid, _solid = pkg.flash_pt(_z(8.0), T, 1e5, 1.0).phases
    assert liquid.composition["NaCl"] == x_sat
    with pytest.raises(ElectrolyteChemistryError, match="window"):
        pkg.solubility("NaCl", 320.0)
    with pytest.raises(ElectrolyteChemistryError, match="not a salt"):
        pkg.solubility("H2O", T)


def test_supersaturated_feed_splits_into_saturated_liquid_and_solid() -> None:
    m_sat = enrtl_crystallisation_molality()
    z = _z(8.0)
    state = _pkg("enrtl_crystallisation").flash_pt(z, T, 1e5, 1.0)
    liquid, solid = state.phases
    assert (liquid.kind, solid.kind) == (PhaseKind.AQUEOUS, PhaseKind.SOLID)
    assert solid.density == pytest.approx(2165.0, rel=0.01)  # CRC Handbook, halite
    assert solid.composition["NaCl"] == 1.0
    m_liquid = liquid.composition["NaCl"] / (liquid.composition["H2O"] * MW_WATER_KG)
    assert m_liquid == pytest.approx(m_sat)
    salt = liquid.mole_fraction * liquid.composition["NaCl"] + solid.mole_fraction
    assert salt == pytest.approx(z["NaCl"])
    # The base row reports the same feed as one supersaturated liquid.
    assert len(_pkg("enrtl_nacl_water").flash_pt(z, T, 1e5, 1.0).phases) == 1


def test_undersaturated_feed_is_the_base_row() -> None:
    z = _z(3.0)
    a = _pkg("enrtl_nacl_water").flash_pt(z, T, 2700.0, 1.0)
    b = _pkg("enrtl_crystallisation").flash_pt(z, T, 2700.0, 1.0)
    assert b.vapor_fraction == pytest.approx(a.vapor_fraction)
    assert b.enthalpy == pytest.approx(a.enthalpy)


def test_below_the_saturated_bubble_pressure_water_leaves_the_salt_dry() -> None:
    z = _z(3.0)
    state = _pkg("enrtl_crystallisation").flash_pt(z, T, 1000.0, 1.0)
    vapour, solid = state.phases
    assert (vapour.kind, solid.kind) == (PhaseKind.VAPOR, PhaseKind.SOLID)
    assert vapour.mole_fraction == pytest.approx(z["H2O"])
    with pytest.raises(ElectrolyteChemistryError, match="precipitate"):
        _pkg("enrtl_nacl_water").flash_pt(z, T, 1000.0, 1.0)


def test_brine_split_uses_the_rows_own_water_activity() -> None:
    """Each brine row boils on its own a_w, not on the Pitzer surface."""
    z = _z(3.0)
    vf = {
        r: _pkg(r).flash_pt(z, T, 2800.0, 1.0).vapor_fraction
        for r in ("enrtl_nacl_water", "pitzer_nacl_water")
    }
    assert vf["enrtl_nacl_water"] != vf["pitzer_nacl_water"]
