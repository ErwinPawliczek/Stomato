"""soft-SAFT row (``soft_saft``) against the source's own published numbers.

Source: J. C. Pamies, PhD thesis, Universitat Rovira i Virgili (2003), open access at
https://repositori.urv.cat/repositori/getDocument/TDX%3A304?ds=Memoria&mime=application/pdf
(retrieved 2026-11-03). The reference fluid is Johnson, Zollweg & Gubbins (1993),
Mol. Phys. 78, 591 (doi:10.1080/00268979300100411).

What is reproduced:

- JZG (1993) p. 605: the MBWR fit is constrained to the critical point T* = 1.313,
  rho* = 0.310. teqp's LJ126_Johnson1993 kind lands on it.
- Pamies Table 4.4 (soft-SAFT column, critical temperatures of n-C12..n-C48) with
  the PVr correlation, eqs 4.2a-c (Tc is independent of sigma, so it tests m and
  epsilon through the reference and chain terms), and Table 4.5 (soft-SAFT critical
  mass densities) with the same correlation (the PVr set is rescaled to Tc and rho_c,
  thesis p. 56).
- What is NOT reproduced: the Table 4.4 soft-SAFT critical pressures. They belong to
  the PVrP set (eq 4.7d, rescaled to Tc and Pc); evaluated with eq 4.7d the kernel
  gives 1.891 / 1.461 / 1.180 / 0.463 MPa for n = 12 / 16 / 20 / 48 against the
  table's 1.814 / 1.415 / 1.150 / 0.458 (1-4 % high). The temperatures for the same
  set match to 0.1 K, so the gap is in the published sigma rescaling, which the
  thesis gives only as the rounded correlation.

The pure-fluid saturation checks compare the shipped Table 4.1 parameters with
CoolProp's reference EOS, pinning the measured deviations recorded in the row.
"""

from __future__ import annotations

import numpy as np
import pytest

teqp = pytest.importorskip("teqp")

from chemicals.elements import molecular_weight  # noqa: E402

from ngdesign.thermo.teqp_bridge import R_GAS, SoftSaftThermo, _SoftSaftKernel  # noqa: E402

#: Pamies (2003) Table 4.4 (soft-SAFT Tc, K) and Table 4.5 (soft-SAFT rho_c, kg/m3).
TABLE_4_4_TC = {
    12: 658.6,
    16: 722.9,
    20: 771.2,
    24: 809.2,
    26: 825.4,
    28: 840.1,
    30: 853.3,
    36: 887.7,
    40: 906.7,
    48: 937.8,
}
TABLE_4_5_RHOC = {12: 227, 16: 217, 20: 209, 24: 201, 26: 197, 28: 194, 30: 191, 36: 182, 40: 177, 48: 169}


def _pvr_kernel(n: int) -> tuple[_SoftSaftKernel, float]:
    """Kernel for n-CnH(2n+2) from the PVr correlation, Pamies (2003) eqs 4.2a-c."""
    mw = molecular_weight({"C": n, "H": 2 * n + 2})
    m = 0.0255 * mw + 0.628
    sigma = ((1.34 * mw + 37.2) / m) ** (1.0 / 3.0)
    eps = (7.17 * mw + 58.1) / m
    params = [{"m": m, "sigma_Angstrom": sigma, "epsilon_over_k": eps}]
    model = teqp.make_model(
        {"kind": "SoftSAFT", "model": {"m": [m], "sigma / m": [sigma * 1e-10], "epsilon/kB / K": [eps]}}
    )
    return _SoftSaftKernel("soft_saft", model, params), mw


def test_jzg_reference_fluid_critical_point() -> None:
    """JZG (1993): "pc = 0.310 and Tc = 1.313 ... in our equation of state"."""
    lj = teqp.make_model({"kind": "LJ126_Johnson1993", "model": {}})
    t_star, rho_star = lj.solve_pure_critical(1.3, 0.3)
    assert t_star == pytest.approx(1.313, abs=5e-4)
    assert rho_star == pytest.approx(0.310, abs=5e-4)


@pytest.mark.parametrize("n", sorted(TABLE_4_4_TC))
def test_critical_point_reproduces_pamies_tables_4_4_and_4_5(n: int) -> None:
    kernel, mw = _pvr_kernel(n)
    eps = kernel.model  # teqp model
    m = float(kernel._m[0])  # noqa: SLF001 - test reads the kernel's own parameters
    sigma = float(kernel._sigma[0])  # noqa: SLF001
    e_over_k = (7.17 * mw + 58.1) / m
    rho_guess = 0.3 / (m * sigma**3 * 6.02214076e23)
    t_c, rho_c = eps.solve_pure_critical(1.4 * e_over_k * m**0.3, rho_guess)
    # Table 4.4 prints 0.1 K; allow one digit of rounding in the correlation constants.
    assert t_c == pytest.approx(TABLE_4_4_TC[n], abs=0.35)
    # Table 4.5 prints whole kg/m3.
    assert rho_c * mw / 1000.0 == pytest.approx(TABLE_4_5_RHOC[n], abs=1.0)
    # The critical point is a genuine inflection of the kernel's own pressure.
    z = np.array([1.0])
    h = 1e-4 * rho_c
    dp = (kernel.pressure(t_c, rho_c + h, z) - kernel.pressure(t_c, rho_c - h, z)) / (2 * h)
    assert abs(dp) < 1e-3 * R_GAS * t_c


CP_NAMES = {
    "C1": "Methane",
    "C2": "Ethane",
    "C3": "Propane",
    "nC4": "n-Butane",
    "nC5": "n-Pentane",
    "nC6": "n-Hexane",
    "nC7": "n-Heptane",
    "nC8": "n-Octane",
    "CO2": "CarbonDioxide",
}


def _reference(cid: str, tr: float) -> tuple[float, float, float]:
    import CoolProp.CoolProp as CP  # noqa: PLC0415 - reference only in tests

    fluid = CP_NAMES[cid]
    t = tr * CP.PropsSI("Tcrit", fluid)
    return t, CP.PropsSI("P", "T", t, "Q", 0, fluid), CP.PropsSI("Dmass", "T", t, "Q", 0, fluid)


@pytest.mark.parametrize("cid", ["nC4", "nC5", "nC6", "nC7", "nC8"])
@pytest.mark.parametrize("tr", [0.6, 0.75, 0.9])
def test_pv_set_saturation_butane_to_octane(cid: str, tr: float) -> None:
    """Table 4.1 parameters, n-butane..n-octane: measured within 5 % Psat, 2.5 % rho_L."""
    t, p_ref, rho_ref = _reference(cid, tr)
    pkg = SoftSaftThermo()
    p = pkg.pure_psat(cid, t)
    assert p is not None
    assert p == pytest.approx(p_ref, rel=0.05)
    state = pkg.flash_tvf({cid: 1.0}, t, 0.0, 1.0)
    rho_l = next(ph.density for ph in state.phases if ph.kind.value != "vapor")
    assert rho_l == pytest.approx(rho_ref, rel=0.025)


@pytest.mark.parametrize("cid", ["C1", "C2", "C3"])
def test_pv_set_light_alkanes_overpredict_psat(cid: str) -> None:
    """Measured, recorded in the row: the PV set fits densities more than vapour
    pressures (thesis p. 33), and for C1-C3 Psat runs 5-25 % high at Tr 0.6-0.9."""
    pkg = SoftSaftThermo()
    for tr in (0.6, 0.75, 0.9):
        t, p_ref, _ = _reference(cid, tr)
        p = pkg.pure_psat(cid, t)
        assert p is not None
        assert 1.03 < p / p_ref < 1.26, (cid, tr, p / p_ref)


def test_co2_table_4_10_saturation() -> None:
    """CO2, Table 4.10 (non-associating row): Psat within 3 % at 240-280 K."""
    import CoolProp.CoolProp as CP  # noqa: PLC0415

    pkg = SoftSaftThermo()
    for t in (240.0, 260.0, 280.0):
        p = pkg.pure_psat("CO2", t)
        assert p is not None
        assert p == pytest.approx(CP.PropsSI("P", "T", t, "Q", 0, "CO2"), rel=0.03)


def test_mixture_flash_splits_methane_butane() -> None:
    """A light binary splits; Lorentz-Berthelot unlike pairs, no binary parameter."""
    state = SoftSaftThermo().flash_pt({"C1": 0.5, "nC4": 0.5}, 300.0, 3.0e6, 1.0)
    assert 0.0 < state.vapor_fraction < 1.0
    vap = next(ph for ph in state.phases if ph.kind.value == "vapor")
    assert vap.composition["C1"] > 0.5


def test_table_4_6_hydrogen_and_decane_saturation() -> None:
    """Table 4.6: H2 (fitted) within 5 % of CoolProp Psat at 20-30 K; n-C10 (from the
    PV correlation, not fitted) runs 10-20 % low at Tr 0.6-0.9 (measured, recorded)."""
    import CoolProp.CoolProp as CP  # noqa: PLC0415

    pkg = SoftSaftThermo()
    for t in (20.0, 25.0, 30.0):
        p = pkg.pure_psat("H2", t)
        assert p is not None
        assert p == pytest.approx(CP.PropsSI("P", "T", t, "Q", 0, "Hydrogen"), rel=0.05)
    tc = CP.PropsSI("Tcrit", "n-Decane")
    for tr in (0.6, 0.75, 0.9):
        p = pkg.pure_psat("nC10", tr * tc)
        assert p is not None
        ratio = p / CP.PropsSI("P", "T", tr * tc, "Q", 0, "n-Decane")
        assert 0.80 < ratio < 0.90, (tr, ratio)


def test_mixture_ln_phi_matches_finite_difference() -> None:
    """The kernel's exact (teqp AD) mixture ln phi agrees with the base class's
    finite-difference chemical potential to its noise floor."""
    from ngdesign.thermo.teqp_bridge import _build_kernel, _TeqpKernel  # noqa: PLC0415

    kernel = _build_kernel("soft_saft", ("C3", "nC6"))
    assert isinstance(kernel, _SoftSaftKernel)
    z = np.array([0.5, 0.5])
    rho = kernel.roots(300.0, 5.0e6, z)[-1]
    exact = kernel.ln_phi(300.0, rho, z)
    fd = _TeqpKernel.ln_phi(kernel, 300.0, rho, z)
    assert np.allclose(exact, fd, atol=1e-6)
