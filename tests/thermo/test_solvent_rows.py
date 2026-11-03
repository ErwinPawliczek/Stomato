"""DGA/AMP Kent-Eisenberg, the tuned TEG-water PR and the DEPG Henry row against their anchors.

Anchors live with the parameters (data/thermo_params/amine/ke_speciation.yaml) or are
quoted: Gironi et al. (2007) on plant regeneration, 200-204 C reboiler at 1-1.2 wt%
water and 1.1-1.2 atm; Burr & Lyddon's solubilities at 25 C.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
import yaml

from ngdesign import registry
from ngdesign.amine.kent_eisenberg import equilibrium_partial_pressures
from ngdesign.amine.mdea_pz import mdea_pz_p_co2
from ngdesign.amine.package import AmineChemistryError
from ngdesign.data import DATA_DIR

DGA, AMP, TEG, DEPG = "929-06-6", "124-68-5", "112-27-6", "143-24-8"
TABLE = yaml.safe_load((DATA_DIR / "thermo_params" / "amine" / "ke_speciation.yaml").read_text())["amines"]


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


def _rms(pairs: list[tuple[float, float]]) -> float:
    return math.sqrt(sum(math.log(a / b) ** 2 for a, b in pairs) / len(pairs))


def test_dga_held_out_points_within_the_recorded_scatter() -> None:
    c = float(TABLE[DGA]["molarity_mol_L"]) * 1000.0
    pairs = [
        (equilibrium_partial_pressures(t + 273.15, c, a, 0.0, amine=DGA)[0], p)
        for t, a, p in TABLE[DGA]["anchors"]["held_out"]
    ]
    assert _rms(pairs) < 0.4


def test_amp_held_out_points_within_the_recorded_scatter() -> None:
    pairs = [
        (equilibrium_partial_pressures(t, m * 1000.0, a, 0.0, amine=AMP)[0], p)
        for t, m, p, a in TABLE[AMP]["anchors"]["held_out"]
    ]
    assert _rms(pairs) < 0.4


def test_dga_carbamate_fit_reproduces_austgen() -> None:
    a, b = TABLE[DGA]["carbamate"]
    for t, km in ((25.0, 0.0822), (40.0, 0.141), (100.0, 0.856)):
        assert math.exp(a + b / (t + 273.15)) == pytest.approx(km, rel=0.02)


def test_amp_binds_co2_differently_from_mdea_and_the_base_row_ignores_it() -> None:
    """No carbamate, so past 0.5 loading AMP keeps absorbing where DGA's carbamate saturates."""
    c = 2800.0
    assert (
        equilibrium_partial_pressures(313.0, c, 0.5, 0.0, amine=AMP)[0]
        < equilibrium_partial_pressures(313.0, c, 0.5, 0.0, amine="MDEA")[0]
    )
    z = {AMP: 0.09, "H2O": 0.89, "CO2": 0.02}
    row = _pkg("amine_ke_dga_amp").flash_pt(z, 313.15, 2e6, 1.0)
    assert not _pkg("amine_ke")._amine_id(tuple(sorted(z)))
    assert row.vapor_fraction < 1e-3  # the CO2 stays in the amine liquid


def test_extended_row_refuses_h2s_and_the_base_amines() -> None:
    with pytest.raises(AmineChemistryError, match="CO2 only"):
        _pkg("amine_ke_dga_amp").flash_pt({DGA: 0.1, "H2O": 0.88, "H2S": 0.02}, 313.15, 1e6, 1.0)
    assert not _pkg("amine_ke_dga_amp")._amine_id(("H2O", "MDEA"))


def test_teg_water_pr_matches_the_plant_reboiler_and_plain_pr_does_not() -> None:
    """1.1 wt% water at 1.15 atm boils near 475 K in regeneration practice."""
    w = 0.011
    n_w, n_t = w / 18.015, (1.0 - w) / 150.17
    z = {"H2O": n_w / (n_w + n_t), TEG: n_t / (n_w + n_t)}
    p = 1.15 * 101325.0
    tuned = _pkg("glycol_pr").bubble_point(z, P=p).T
    plain = _pkg("pr").bubble_point(z, P=p).T
    assert tuned == pytest.approx(475.0, abs=8.0)
    assert abs(tuned - 475.0) < abs(plain - 475.0)


def test_teg_water_is_more_negative_than_plain_pr() -> None:
    """Glycol holds water: its K_w at contactor conditions falls with the negative k_ij."""
    z = {"H2O": 0.1, TEG: 0.9}
    tuned = _pkg("glycol_pr").bubble_point(z, T=310.0).P
    plain = _pkg("pr").bubble_point(z, T=310.0).P
    assert tuned < plain


def test_glycol_row_refuses_meg_and_leaves_dry_gas_alone() -> None:
    with pytest.raises(ValueError, match="TEG-water only"):
        _pkg("glycol_pr").flash_pt({"MEG": 0.5, "H2O": 0.5}, 350.0, 1e5, 1.0)
    dry = {"C1": 0.6, "C3": 0.4}
    assert _pkg("glycol_pr").flash_pt(dry, 250.0, 2e6, 1.0).enthalpy == pytest.approx(
        _pkg("pr").flash_pt(dry, 250.0, 2e6, 1.0).enthalpy
    )


def test_depg_recovers_the_published_co2_solubility_and_selectivity() -> None:
    """3.63 v/v CO2 at 25 C, 1 atm, H2S 8.82 times that: Burr & Lyddon, Table 1."""
    pkg = _pkg("depg_henry")
    for gas, vv in (("CO2", 3.63), ("H2S", 3.63 * 8.82)):
        liquid = pkg.flash_pt({DEPG: 0.5, gas: 0.5}, 298.15, 101325.0, 1.0).phases[1]
        ratio = liquid.composition[gas] / liquid.composition[DEPG]
        assert ratio * 0.024465 / 2.718e-4 == pytest.approx(vv, rel=0.02)


def test_depg_refuses_outside_its_data() -> None:
    pkg = _pkg("depg_henry")
    with pytest.raises(ValueError, match="25 C data only"):
        pkg.flash_pt({DEPG: 0.9, "CO2": 0.1}, 330.0, 1e6, 1.0)
    with pytest.raises(ValueError, match="no DEPG solubility"):
        pkg.flash_pt({DEPG: 0.9, "C3": 0.1}, 298.15, 1e6, 1.0)


def _blend_moles(c_mdea: float, c_pz: float, loading: float) -> tuple[float, float, float, float]:
    """(water, MDEA, PZ, CO2) mol per litre at the 1030 kg/m3 the molarities imply."""
    water = (1030.0 - c_mdea * 119.16 - c_pz * 86.14) / 18.015
    return water, c_mdea, c_pz, loading * (c_mdea + c_pz)


def test_mdea_pz_tracks_bishnoi_table_5_7_within_the_recorded_band() -> None:
    table = yaml.safe_load((DATA_DIR / "thermo_params" / "amine" / "mdea_pz.yaml").read_text())
    pairs = [(mdea_pz_p_co2(t, *_blend_moles(4.0, 0.6, a)), p) for t, a, p in table["anchors"]]
    assert _rms(pairs) < 0.8
    assert all(0.2 < got / p < 3.0 for got, p in pairs)


def test_piperazine_lowers_co2_pressure_at_the_same_co2_content() -> None:
    water, mdea, pz, co2 = _blend_moles(4.0, 0.6, 0.1)
    assert mdea_pz_p_co2(313.0, water, mdea, pz, co2) < 0.5 * mdea_pz_p_co2(313.0, water, mdea, 0.0, co2)


def test_mdea_pz_row_differs_from_amine_ke_and_refuses_h2s() -> None:
    pz = "110-85-0"
    z = {"MDEA": 0.07, pz: 0.01, "H2O": 0.90, "CO2": 0.02}
    p_row = _pkg("amine_mdea_pz").bubble_point(z, T=313.15).P
    base = {"MDEA": 0.08, "H2O": 0.90, "CO2": 0.02}
    p_ke = _pkg("amine_ke").bubble_point(base, T=313.15).P
    # Each bubble point is the liquid's own: sum_i z_i K_i(x = z) = 1 (the
    # incipient vapour of the liquid z). Measured 14291.7 Pa (MDEA + PZ, the
    # Bishnoi set with unit activity coefficients) against 11907.6 Pa (amine_ke).
    # An earlier "p_row < p_ke" read a bubble point the flash placed by a false
    # single-liquid verdict at an overshot loading iterate (and a K read on a
    # piperazine-free seed liquid); the model row carries no data that orders
    # the two, so only the difference is asserted.
    for row, comp, p in (("amine_mdea_pz", z, p_row), ("amine_ke", base, p_ke)):
        k = _pkg(row)._k_values_internal(comp, 313.15, p, comp)
        assert sum(comp[c] * k[c] for c in comp) == pytest.approx(1.0, abs=1e-6)
    assert abs(p_row - p_ke) > 0.1 * p_ke
    with pytest.raises(AmineChemistryError, match="CO2 only"):
        _pkg("amine_mdea_pz").flash_pt({"MDEA": 0.1, "H2O": 0.88, "H2S": 0.02}, 313.15, 1e6, 1.0)
