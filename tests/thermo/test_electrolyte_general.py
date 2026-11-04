"""eNRTL and extended UNIQUAC as general single-salt forms (charges and stoichiometry as data).

The shipped parameter files carry NaCl only (no open, redistributable parameter
set for another salt was found, see docs/thermo-catalogue-plan.md section 6), so
the charge- and stoichiometry-dependent branches are exercised here with a
SYNTHETIC 2:1 test salt injected for the duration of a test. Its numbers are
not literature values, are never shipped, and only probe identities every
parameter set must satisfy: the Debye-Hueckel limiting law, the Gibbs-Duhem
relation between phi and gamma+-, and the flash surface being the salt's own
a_w.  The NaCl outputs of the generalised code were checked bit-for-bit
against the pre-generalisation code (repr snapshot of the activity functions,
flashes, saturation points, K-values, phase properties and derivatives on all
eight NaCl rows, 2026-11-04).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Iterator
from typing import Any

import pytest

import ngdesign.amine.electrolyte as elec
from ngdesign import registry
from ngdesign.amine.electrolyte import (
    ElectrolyteChemistryError,
    _mw,
    enrtl_mean_gamma,
    enrtl_osmotic,
    enrtl_salt,
    enrtl_salts,
    enrtl_water_activity,
    ext_uniquac_mean_gamma,
    ext_uniquac_osmotic,
    ext_uniquac_salt,
    ext_uniquac_salts,
    pdh_mean_gamma,
    pitzer_salt,
)

T = 298.15
MW_WATER_KG = 0.018015268

#: Test-only salt id: a real 2:1 component of the open registry so the flash can
#: carry it; its eNRTL / extended-UNIQUAC numbers below are SYNTHETIC.
_TEST_SALT = "MgCl2"

_CACHED = (elec.enrtl_salt, elec.ext_uniquac_salt, elec.enrtl_crystallisation_molality)


def _clear() -> None:
    for fn in _CACHED:
        fn.cache_clear()


@pytest.fixture
def synthetic_2_1(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Inject a SYNTHETIC 2:1 salt (not literature; never shipped) into both tables."""
    enrtl = copy.deepcopy(elec._enrtl())
    enrtl["salts"][_TEST_SALT] = {
        "cation": "Mg+2",
        "anion": "Cl-",
        "z_cation": 2,
        "z_anion": 1,
        "nu_cation": 1,
        "nu_anion": 2,
        "alpha": 0.2,
        "tau_ca_w": -4.0,
        "tau_w_ca": 8.0,
        "molality_cap": 3.0,
    }
    eu = copy.deepcopy(elec._ext_uniquac())
    eu["salts"][_TEST_SALT] = {
        "cation": "Mg",
        "anion": "Cl",
        "z_cation": 2,
        "z_anion": 1,
        "nu_cation": 1,
        "nu_anion": 2,
        "molality_cap": 3.0,
    }
    eu["r"]["Mg"], eu["q"]["Mg"] = 1.0, 1.0
    for other, u0 in (("H2O", 500.0), ("Cl", 1500.0), ("Mg", 0.0), ("Na", 1000.0)):
        eu["u0"][f"Mg-{other}"] = u0
        eu["u1"][f"Mg-{other}"] = 0.0
    monkeypatch.setattr(elec, "_enrtl", lambda: enrtl)
    monkeypatch.setattr(elec, "_ext_uniquac", lambda: eu)
    _clear()
    yield
    _clear()


def test_shipped_tables_share_the_ion_pair_keys() -> None:
    """NaCl reads the same stoichiometry and cap from every brine parameter file."""
    assert enrtl_salts() == ("NaCl",)
    assert ext_uniquac_salts() == ("NaCl",)
    ions = enrtl_salt("NaCl").ions
    eu = ext_uniquac_salt("NaCl")
    for s in (ions, eu):
        assert (s.zz, s.nu, s.charge_sum, s.molality_cap) == (1.0, 2.0, 2.0, 6.15)
    assert pitzer_salt("NaCl").molality_cap == ions.molality_cap


@pytest.mark.parametrize(
    ("fn", "match"),
    [
        (lambda: enrtl_mean_gamma(1.0, "KCl"), "no eNRTL parameters for 'KCl'"),
        (lambda: pdh_mean_gamma(0.1, "KCl"), "no eNRTL parameters for 'KCl'"),
        (lambda: ext_uniquac_mean_gamma(1.0, salt="KCl"), "no extended-UNIQUAC parameters for 'KCl'"),
        (lambda: elec.enrtl_saturation_molality("KCl"), "no eNRTL parameters for 'KCl'"),
    ],
)
def test_unknown_salt_refuses(fn: Any, match: str) -> None:
    with pytest.raises(ElectrolyteChemistryError, match=match):
        fn()


@pytest.mark.parametrize("row", ["enrtl_nacl_water", "ext_uniquac_nacl_water", "pitzer_debye_huckel"])
def test_rows_refuse_a_salt_without_parameters(row: str) -> None:
    z = {"H2O": 0.95, "KCl": 0.05}
    with pytest.raises(NotImplementedError, match=r"no verified parameters\s+for \['KCl'\]"):
        registry.create("thermo", row).flash_pt(z, T, 1e5, 1.0)


def test_ext_uniquac_refuses_a_salt_whose_ions_lack_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    eu = copy.deepcopy(elec._ext_uniquac())
    eu["salts"]["KCl"] = {
        "cation": "K",
        "anion": "Cl",
        "z_cation": 1,
        "z_anion": 1,
        "nu_cation": 1,
        "nu_anion": 1,
        "molality_cap": 4.8,
    }
    monkeypatch.setattr(elec, "_ext_uniquac", lambda: eu)
    _clear()
    try:
        with pytest.raises(ElectrolyteChemistryError, match="lacks species parameters"):
            ext_uniquac_salt("KCl")
    finally:
        _clear()


@pytest.mark.parametrize("salt", ["NaCl", _TEST_SALT])
@pytest.mark.usefixtures("synthetic_2_1")
def test_limiting_laws_carry_the_charges(salt: str) -> None:
    """ln gamma+- -> -|z_c z_a| A sqrt(I) as m -> 0, I = m (nu_c z_c^2 + nu_a z_a^2)/2.

    PDH (Chen et al. 1982): A = 3 A_phi; extended UNIQUAC (Thomsen DH term,
    Leal et al. 2025 eq. 40): A = A(T) of the parameter file.  Both short-range
    terms vanish at infinite dilution, so the full eNRTL obeys the same law.
    """
    ions = enrtl_salt(salt).ions
    # eNRTL/PDH at 1e-4 m with the 3 % band of the NaCl limiting-law test
    # (test_electrolyte_variants.py): the numeric derivative's infinite-dilution
    # reference is biased below ~1e-5 m, and rho sqrt(I_x) is ~2 % at 1e-4 m.
    m = 1e-4
    sq = math.sqrt(0.5 * m * ions.charge_sum)
    dh_pdh = -ions.zz * 3.0 * 0.392 * sq
    assert math.log(pdh_mean_gamma(m, salt)) == pytest.approx(dh_pdh, rel=0.03)
    assert math.log(enrtl_mean_gamma(m, salt)) == pytest.approx(dh_pdh, rel=0.03)
    # Extended UNIQUAC is closed-form: 1e-6 m, where b sqrt(I) is 0.3 %.
    m = 1e-6
    sq = math.sqrt(0.5 * m * ions.charge_sum)
    dh_eu = -ions.zz * elec._eu_a_dh(T) * sq
    assert math.log(ext_uniquac_mean_gamma(m, T, salt)) == pytest.approx(dh_eu, rel=0.005)


@pytest.mark.parametrize("model", ["enrtl", "ext_uniquac"])
@pytest.mark.usefixtures("synthetic_2_1")
def test_gibbs_duhem_holds_for_a_2_1_salt(model: str) -> None:
    """ln gamma+- = (phi - 1) + int_0^m (phi - 1)/m' dm' with nu = 3 (u = sqrt(m') quadrature)."""

    def phi(m: float) -> float:
        if model == "enrtl":
            return enrtl_osmotic(m, _TEST_SALT)
        return ext_uniquac_osmotic(m, T, _TEST_SALT)

    def gamma(m: float) -> float:
        if model == "enrtl":
            return enrtl_mean_gamma(m, _TEST_SALT)
        return ext_uniquac_mean_gamma(m, T, _TEST_SALT)

    # eNRTL: the forward-difference infinite-dilution reference of the numeric
    # derivative carries a ~2 |z_c z_a| A_phi sqrt(I(h)) bias in ln gamma+-
    # (h = 1e-6 m): 1.1e-3 for NaCl at 2 m, 3.8e-3 for this 2:1 salt (measured).
    # Extended UNIQUAC is closed-form and holds to the quadrature error.
    tol = 5e-3 if model == "enrtl" else 1e-4
    for m in (0.5, 2.0):
        n = 400
        h = math.sqrt(m) / n
        integral = sum(2.0 * (phi((h * (k + 0.5)) ** 2) - 1.0) / (h * (k + 0.5)) * h for k in range(n))
        assert math.log(gamma(m)) == pytest.approx((phi(m) - 1.0) + integral, abs=tol)


@pytest.mark.usefixtures("synthetic_2_1")
def test_flash_runs_on_the_salts_own_surface() -> None:
    """Bubble pressure == a_w(m, salt) * Psat on the eNRTL row; past the salt's cap it refuses."""
    pkg = registry.create("thermo", "enrtl_nacl_water")
    s = 1.0 * MW_WATER_KG
    z = {"H2O": 1.0 / (1.0 + s), _TEST_SALT: s / (1.0 + s)}
    m = 1000.0 * z[_TEST_SALT] / (_mw("H2O") * z["H2O"])
    bubble = pkg.bubble_point(z, T=T)
    assert bubble.P == pytest.approx(enrtl_water_activity(m, _TEST_SALT) * pkg.pure_psat("H2O", T), rel=1e-6)
    with pytest.raises(ElectrolyteChemistryError, match=f"{_TEST_SALT} would precipitate"):
        pkg.flash_pt(z, T, 1000.0, 1.0)
    with pytest.raises(NotImplementedError, match="salt-salt NRTL pairs"):
        pkg.flash_pt({"H2O": 0.9, "NaCl": 0.05, _TEST_SALT: 0.05}, T, 1e5, 1.0)
