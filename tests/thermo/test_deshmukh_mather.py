"""MacGregor 1988 modified Deshmukh-Mather model (MDEA + sulfolane + water) and its package."""

from __future__ import annotations

import math
from typing import Any

import pytest
import yaml

from ngdesign.amine import deshmukh_mather as dm
from ngdesign.amine.enrtl import _a_phi, debye_huckel_a_phi, water_density_permittivity
from ngdesign.amine.package import AmineChemistryError, AmineSulfinolPackage
from ngdesign.data import DATA_DIR

TABLE: dict[str, Any] = yaml.safe_load(
    (DATA_DIR / "thermo_params" / "amine" / "sulfinol_macgregor1988.yaml").read_text()
)
SULFOLANE = "126-33-0"
T40 = 313.15
#: Table 1.1 solvent, mol per 100 g solution.
N_MDEA, N_SULF, N_WATER = 0.1754, 0.2538, 2.6976
X_W_SOLVENT = N_WATER / (N_WATER + N_SULF)


def _a_water(a_co2: float, a_h2s: float) -> float:
    return N_WATER / (N_MDEA + N_SULF + N_WATER + N_MDEA * (a_co2 + a_h2s))


def _feed(a_co2: float, a_h2s: float) -> dict[str, float]:
    n = {"MDEA": N_MDEA, SULFOLANE: N_SULF, "H2O": N_WATER, "CO2": N_MDEA * a_co2, "H2S": N_MDEA * a_h2s}
    total = sum(n.values())
    return {k: v / total for k, v in n.items()}


def _speciate(a_co2: float, a_h2s: float) -> dm.Speciation:
    return dm.fugacities(T40, 2.217, a_co2, a_h2s, X_W_SOLVENT, _a_water(a_co2, a_h2s))


def test_refuses_every_temperature_but_the_isotherms() -> None:
    for T in (298.15, 313.0, 320.0, 343.15, 400.0):
        with pytest.raises(dm.DeshmukhMatherError, match="does not interpolate"):
            dm.fugacities(T, 2.217, 0.3, 0.0, X_W_SOLVENT, 0.85)
    # 100 C has constants but no cited sulfolane permittivity: refused, not estimated.
    with pytest.raises(dm.DeshmukhMatherError, match="permittivity"):
        dm.fugacities(373.15, 2.217, 0.3, 0.0, X_W_SOLVENT, 0.85)
    assert dm.fugacities(T40 + 0.009, 2.217, 0.3, 0.0, X_W_SOLVENT, 0.85).f_co2 > 0.0


def test_dielectric_constant_is_eq_6_3() -> None:
    _d, eps_w = water_density_permittivity(T40)
    x_w = 0.9
    want = 0.1 * 42.2 + 0.9 * eps_w - 4.341 * 0.9 - 70.940 * 0.81 + 74.683 * 0.729
    assert dm.dielectric_constant(T40, x_w) == pytest.approx(want, rel=1e-12)


def test_a_phi_refactor_is_byte_identical() -> None:
    d, eps = water_density_permittivity(298.15)
    assert debye_huckel_a_phi(298.15, d, eps) == _a_phi(298.15)
    assert _a_phi(298.15) == pytest.approx(0.392, abs=1e-3)


def test_speciation_closes_charge_and_mass_balances() -> None:
    s = _speciate(0.4, 0.3)
    m = s.molality
    m_a = 2.217
    assert m["MDEA"] + m["MDEAH+"] == pytest.approx(m_a, rel=1e-12)
    assert m["CO2"] + m["HCO3-"] + m["CO3--"] == pytest.approx(0.4 * m_a, rel=1e-12)
    assert m["H2S"] + m["HS-"] + m["S--"] == pytest.approx(0.3 * m_a, rel=1e-12)
    cations = m["H+"] + m["MDEAH+"]
    anions = m["OH-"] + m["HCO3-"] + 2 * m["CO3--"] + m["HS-"] + 2 * m["S--"]
    assert cations == pytest.approx(anions, rel=1e-9)


def test_activity_coefficients_satisfy_eq_6_2() -> None:
    s = _speciate(0.4, 0.3)
    m = s.molality
    # CO2 is neutral: ln gamma = beta(CO2, MDEAH+) m(MDEAH+) only (Chakravarty column).
    assert s.ln_gamma["CO2"] == pytest.approx(-0.08868 * m["MDEAH+"], abs=1e-9)
    assert s.ln_gamma["H2S"] == pytest.approx(-0.0934 * m["MDEAH+"], abs=1e-9)


def test_reproduces_the_fitted_single_gas_tables_to_the_recorded_scatter() -> None:
    """Regression pin of the reconstruction on the data Table 6.4 was fitted to (not validation)."""
    co2 = [math.log(_speciate(a, 0.0).f_co2 / (p * 1e3)) for a, p in TABLE["fitted_co2_40C"]]
    h2s = [math.log(_speciate(0.0, a).f_h2s / (p * 1e3)) for a, p in TABLE["fitted_h2s_40C"]]
    assert sum(map(abs, co2)) / len(co2) == pytest.approx(0.548, abs=0.005)
    assert sum(map(abs, h2s)) / len(h2s) == pytest.approx(0.287, abs=0.005)


def test_solvent_stripped_liquid_still_speciates() -> None:
    """Up to the package's stripped-solvent cutoff (2x the thesis molality) the solve converges."""
    s = dm.fugacities(T40, 2.0 * 2.217, 0.42, 0.13, 0.914, 0.7)
    assert math.isfinite(s.f_co2) and math.isfinite(s.f_h2s)


@pytest.fixture(scope="module")
def pkg() -> AmineSulfinolPackage:
    return AmineSulfinolPackage()


def test_package_refusals(pkg: AmineSulfinolPackage) -> None:
    with pytest.raises(AmineChemistryError, match="no sulfolane"):
        pkg.flash_pt({"MDEA": 0.05, "H2O": 0.93, "CO2": 0.02}, T40, 1e6, 1.0)
    off = _feed(0.3, 0.0)
    off["H2O"] *= 1.3
    with pytest.raises(AmineChemistryError, match="outside"):
        pkg.flash_pt(off, T40, 1e6, 1.0)
    with pytest.raises(AmineChemistryError, match="does not interpolate"):
        pkg.flash_pt(_feed(0.3, 0.1), 330.0, 5e6, 1.0)
    with pytest.raises(AmineChemistryError, match="no loading inverse"):
        pkg.equilibrium_loadings(_feed(0.3, 0.1), T40, 1e4, 1e3)


def test_package_flash_identity_and_bubble_point(pkg: AmineSulfinolPackage) -> None:
    z = _feed(0.36, 0.108)
    bubble = pkg.bubble_point(z, T=T40).P
    p_eq = pkg.equilibrium_pressures(z, T40, 0.36, 0.108)
    # the bubble pressure carries the acid gases' equilibrium pressures plus the solvent's
    assert p_eq["CO2"] + p_eq["H2S"] < bubble < p_eq["CO2"] + p_eq["H2S"] + 1e4
    k = pkg.k_values(z, T40, 0.999 * bubble)
    assert k is not None
    assert k["CO2"] * z["CO2"] * 0.999 * bubble == pytest.approx(p_eq["CO2"], rel=2e-3)
    single = pkg.flash_pt(z, T40, 5e6, 1.0)
    assert single.vapor_fraction == 0.0
