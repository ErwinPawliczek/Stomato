"""Pitzer single-salt brines beyond NaCl: published 25 C anchors and the package surface.

Parameters: the PHRQPITZ 25 C sets, USGS WRI 88-4153 (Plummer et al. 1988)
Attachment C.6 (data/thermo_params/electrolyte/pitzer.yaml carries the per-value
primary references). Anchors, read from the NIST reprints this session:

* Hamer & Wu (1972), J. Phys. Chem. Ref. Data 1, 1047, doi:10.1063/1.3253108:
  Table 28 (KCl), Table 29 (KBr), Table 9 (LiCl), Table 17 (NaBr) -- osmotic
  coefficient phi and mean activity coefficient gamma at 25 C.
* Goldberg & Nuttall (1978), J. Phys. Chem. Ref. Data 7, 263,
  doi:10.1063/1.555569, Table 17 (MgCl2, printed p. 288): gamma, phi, a_w.

Measured fit quality (2026-11-03): the 1:1 salts reproduce phi within 0.6 % and
gamma within 0.9 % across each salt's capped range; MgCl2 phi within 1.9 % and
a_w within 0.2 %, gamma 1.2-3.2 % low against Goldberg & Nuttall (assessed: the
HMW84 set was fitted to the multicomponent sea-water system, not to the 1978
evaluation; the flash surface is a_w, which is held to 0.5 %).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.amine.electrolyte import (
    ElectrolyteChemistryError,
    _mw,
    pitzer_mean_gamma,
    pitzer_osmotic,
    pitzer_salt,
    pitzer_salts,
    pitzer_water_activity,
)

T = 298.15
MW_WATER_KG = 0.018015268

# (molality, phi, gamma) rows of the cited tables.
_HAMER_WU: dict[str, list[tuple[float, float, float]]] = {
    "KCl": [  # Table 28; 4.803 m is the saturated solution
        (0.1, 0.927, 0.768),
        (0.5, 0.900, 0.649),
        (1.0, 0.898, 0.604),
        (2.0, 0.912, 0.573),
        (3.0, 0.936, 0.568),
        (4.0, 0.965, 0.576),
        (4.803, 0.990, 0.589),
    ],
    "KBr": [  # Table 29
        (0.1, 0.928, 0.771),
        (0.5, 0.906, 0.658),
        (1.0, 0.907, 0.617),
        (2.0, 0.927, 0.593),
        (3.0, 0.954, 0.595),
        (4.0, 0.985, 0.608),
        (5.5, 1.029, 0.637),
    ],
    "LiCl": [  # Table 9
        (0.1, 0.940, 0.789),
        (0.5, 0.964, 0.739),
        (1.0, 1.020, 0.775),
        (2.0, 1.145, 0.924),
        (3.0, 1.284, 1.157),
        (4.0, 1.441, 1.499),
        (5.0, 1.613, 2.00),
        (6.0, 1.794, 2.73),
    ],
    "NaBr": [  # Table 17
        (0.1, 0.935, 0.783),
        (0.5, 0.932, 0.697),
        (1.0, 0.957, 0.687),
        (2.0, 1.027, 0.730),
        (3.0, 1.112, 0.816),
        (4.0, 1.203, 0.934),
        (5.0, 1.296, 1.083),
        (6.0, 1.386, 1.261),
    ],
}
_ONE_ONE_TOL = 0.01

# Goldberg & Nuttall 1978 Table 17: (molality, gamma, phi, a_w).
_GN78_MGCL2: list[tuple[float, float, float, float]] = [
    (0.1, 0.5347, 0.8648, 0.995337),
    (1.0, 0.5769, 1.1292, 0.941815),
    (2.0, 1.0655, 1.5250, 0.848029),
    (3.0, 2.3498, 2.0125, 0.721589),
    (4.0, 5.6692, 2.5313, 0.578552),
    (5.0, 14.3960, 3.0645, 0.436875),
]


def _cases() -> list[tuple[str, float, float, float]]:
    return [(salt, m, phi, gam) for salt, rows in _HAMER_WU.items() for m, phi, gam in rows]


@pytest.mark.parametrize(("salt", "molality", "phi_ref", "gamma_ref"), _cases())
def test_one_one_salts_against_hamer_wu(salt: str, molality: float, phi_ref: float, gamma_ref: float) -> None:
    """Osmotic and mean activity coefficients within 1 % of Hamer & Wu (1972)."""
    assert pitzer_osmotic(molality, salt) == pytest.approx(phi_ref, rel=_ONE_ONE_TOL)
    assert pitzer_mean_gamma(molality, salt) == pytest.approx(gamma_ref, rel=_ONE_ONE_TOL)


@pytest.mark.parametrize(("molality", "gamma_ref", "phi_ref", "aw_ref"), _GN78_MGCL2)
def test_mgcl2_against_goldberg_nuttall(molality: float, gamma_ref: float, phi_ref: float, aw_ref: float) -> None:
    """2:1 salt: a_w within 0.5 %, phi within 2 %, gamma inside its assessed 3.5 % band."""
    assert pitzer_water_activity(molality, "MgCl2") == pytest.approx(aw_ref, rel=0.005)
    assert pitzer_osmotic(molality, "MgCl2") == pytest.approx(phi_ref, rel=0.02)
    gamma = pitzer_mean_gamma(molality, "MgCl2")
    # Measured: 1.2-3.2 % LOW at every row (assessed in the module docstring).
    assert gamma < gamma_ref
    assert gamma == pytest.approx(gamma_ref, rel=0.035)


def test_stoichiometric_weights() -> None:
    """1:1 weights are exactly 1 (so NaCl is bit-for-bit the 1:1 form); MgCl2 is 2:1."""
    nacl = pitzer_salt("NaCl")
    assert (nacl.zz, nacl.nu, nacl.f_b, nacl.f_c, nacl.charge_sum) == (1.0, 2.0, 1.0, 1.0, 2.0)
    mg = pitzer_salt("MgCl2")
    assert (mg.zz, mg.nu, mg.charge_sum) == (2.0, 3.0, 6.0)
    assert mg.f_b == pytest.approx(4.0 / 3.0)
    assert mg.f_c == pytest.approx(2.0 * 2.0**1.5 / 3.0)


def test_mean_gamma_is_the_gibbs_duhem_integral_of_phi() -> None:
    """Gibbs-Duhem: ln gamma = (phi - 1) + int_0^m (phi - 1)/m' dm' (midpoint quadrature in u = sqrt(m))."""
    for salt in ("KCl", "MgCl2"):
        m = 2.0
        # m' = u^2 removes the sqrt(m') singularity: int 2 (phi - 1)/u du.
        n = 4000
        h = math.sqrt(m) / n
        integral = sum(2.0 * (pitzer_osmotic((h * (k + 0.5)) ** 2, salt) - 1.0) / (h * (k + 0.5)) * h for k in range(n))
        ln_g = (pitzer_osmotic(m, salt) - 1.0) + integral
        assert math.log(pitzer_mean_gamma(m, salt)) == pytest.approx(ln_g, abs=1e-6)


def test_unknown_salt_refuses() -> None:
    with pytest.raises(ElectrolyteChemistryError, match="no Pitzer parameters"):
        pitzer_osmotic(1.0, "CaCl2")


def test_shipped_salts_resolve_in_the_component_registry() -> None:
    """Every Pitzer salt is a stream component the flash can carry."""
    pkg = registry.create("thermo", "pitzer_nacl_water")
    for salt in pitzer_salts():
        s = 1.0 * MW_WATER_KG
        z = {"H2O": 1.0 / (1.0 + s), salt: s / (1.0 + s)}
        state = pkg.flash_pt(z, T, 1.0e5, 1.0)
        assert state.vapor_fraction == 0.0


def _z(salt: str, molality: float) -> dict[str, float]:
    s = molality * MW_WATER_KG
    return {"H2O": 1.0 / (1.0 + s), salt: s / (1.0 + s)}


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


@pytest.mark.parametrize("salt", ["KCl", "LiCl", "MgCl2"])
def test_brine_bubble_pressure_is_the_salts_water_activity(salt: str) -> None:
    """Bubble pressure == a_w(m, salt) * Psat_H2O on the Pitzer row, per salt."""
    pkg = _pkg("pitzer_nacl_water")
    z = _z(salt, 2.0)
    m = 1000.0 * z[salt] / (_mw("H2O") * z["H2O"])
    bubble = pkg.bubble_point(z, T=T)
    assert bubble.P == pytest.approx(pitzer_water_activity(m, salt) * pkg.pure_psat("H2O", T), rel=1e-6)


def test_salts_differ_at_equal_molality() -> None:
    """The flash runs on the salt's own surface: LiCl lowers a_w more than KCl at 3 m."""
    pkg = _pkg("pitzer_nacl_water")
    p_licl = pkg.bubble_point(_z("LiCl", 3.0), T=T).P
    p_kcl = pkg.bubble_point(_z("KCl", 3.0), T=T).P
    assert p_licl < p_kcl


def test_two_phase_split_conserves_the_salt() -> None:
    pkg = _pkg("pitzer_nacl_water")
    z = _z("KBr", 1.0)
    p = 0.9 * pkg.bubble_point(z, T=T).P
    state = pkg.flash_pt(z, T, p, 1.0)
    vapour, liquid = state.phases
    assert vapour.composition["KBr"] == 0.0
    assert liquid.mole_fraction * liquid.composition["KBr"] == pytest.approx(z["KBr"], rel=1e-9)


def test_past_the_salts_cap_the_flash_refuses() -> None:
    """KCl capped at its 4.803 mol/kg saturated solution: boiling past it refuses."""
    pkg = _pkg("pitzer_nacl_water")
    z = _z("KCl", 4.0)
    with pytest.raises(ElectrolyteChemistryError, match="KCl would precipitate"):
        pkg.flash_pt(z, T, 1000.0, 1.0)


def test_mixed_salts_refuse() -> None:
    """Two salts need theta/psi mixing terms the row does not ship: first-use refusal."""
    pkg = _pkg("pitzer_nacl_water")
    with pytest.raises(NotImplementedError, match="single-salt"):
        pkg.flash_pt({"H2O": 0.9, "NaCl": 0.05, "KCl": 0.05}, T, 1.0e5, 1.0)


def test_other_brine_rows_stay_nacl_only() -> None:
    """eNRTL / extended UNIQUAC carry NaCl parameters only: KCl refuses there."""
    for row in ("enrtl_nacl_water", "ext_uniquac_nacl_water"):
        with pytest.raises(NotImplementedError, match="KCl"):
            _pkg(row).flash_pt(_z("KCl", 1.0), T, 1.0e5, 1.0)


def test_pitzer_hoc_inherits_the_salts() -> None:
    """The real-vapour Pitzer row runs the same salt surfaces."""
    pkg = _pkg("pitzer_hoc")
    assert pkg.bubble_point(_z("NaBr", 1.0), T=T).P < _pkg("pitzer_nacl_water").bubble_point(_z("NaBr", 1.0), T=T).P
