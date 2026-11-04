"""BWR-family packages (spec T-16b): MBWR-32 and the provisional Lee-Starling."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from ngdesign.contracts import PhaseKind
from ngdesign.thermo.bwr import _YE_FLUIDS, MBWR32Package, _ls_mix
from ngdesign.thermo.helmholtz import ComponentNotSupported, _bwrs_mix

_CASES = Path(__file__).resolve().parents[2] / "data" / "validation" / "helmholtz" / "cases.yaml"


@pytest.fixture(scope="module")
def mbwr() -> MBWR32Package:
    return MBWR32Package()


def test_mbwr_pure_flash_liquid_vapor_branches(mbwr: MBWR32Package) -> None:
    """Outside the saturation line each flash reports the branch phase."""
    # pure fluid: the two-phase region is the saturation line itself, so every
    # (T, P) state resolves to a single phase - liquid above psat, vapor below.
    st = mbwr.flash_pt({"C1": 1.0}, 150.0, 3e6, 1.0)
    assert [p.kind for p in st.phases] == [PhaseKind.HC_LIQUID]
    gas = mbwr.phase_props({"C1": 1.0}, 300.0, 1e6, PhaseKind.VAPOR)
    liq = mbwr.phase_props({"C1": 1.0}, 150.0, 10e6, PhaseKind.HC_LIQUID)
    assert gas.density < liq.density


def test_mbwr_saturation_matches_coolprop(mbwr: MBWR32Package) -> None:
    """Vapour pressure against the bound case references (CoolProp 8.0.0, 3 %)."""
    import yaml

    raw = yaml.safe_load(_CASES.read_text())
    for case in raw["pure_cases"]:
        if case["package"] != "mbwr" or case["T"] > 180.0:
            continue
        p = mbwr.pure_psat(case["fluid"], case["T"])
        assert p is not None
        assert math.isclose(p, case["expected"]["bubble_P"], rel_tol=0.03), case["id"]


def test_mbwr_saturation_dome_endpoints(mbwr: MBWR32Package) -> None:
    """Above the critical temperature no saturation pressure exists."""
    assert mbwr.pure_psat("C1", 190.53 + 10.0) is None
    assert mbwr.pure_psat("C1", 160.0) is not None


def test_mbwr_refuses_mixtures(mbwr: MBWR32Package) -> None:
    with pytest.raises(ComponentNotSupported):
        mbwr.flash_pt({"C1": 0.5, "C3": 0.5}, 250.0, 2e6, 1.0)


def test_mbwr_unsupported_component(mbwr: MBWR32Package) -> None:
    with pytest.raises(ComponentNotSupported):
        mbwr.pure_psat("CO2", 250.0)


def test_bwr_ls_reduces_to_bwrs() -> None:
    """The shipped empty-k_ij table makes every mixed parameter equal BWRS mixing."""
    from ngdesign.thermo.bwr import BWRLeeStarlingPackage
    from ngdesign.thermo.helmholtz import BWRSPackage

    ids = ("N2", "C1", "CO2")
    xs = (0.05, 0.9, 0.05)
    ls = _ls_mix(ids, xs)
    bwrs = _bwrs_mix(ids, xs)
    assert ls == bwrs
    a = BWRSPackage().flash_pt({"N2": 0.05, "C1": 0.9, "CO2": 0.05}, 300.0, 5e6, 1.0)
    b = BWRLeeStarlingPackage().flash_pt({"N2": 0.05, "C1": 0.9, "CO2": 0.05}, 300.0, 5e6, 1.0)
    for pa, pb in zip(a.phases, b.phases, strict=True):
        assert math.isclose(pa.density, pb.density, rel_tol=1e-12)
        assert math.isclose(pa.cp, pb.cp, rel_tol=1e-9)


def test_mbwr_densities_match_validation_cases(mbwr: MBWR32Package) -> None:
    """Branch-wise saturated densities against the bound references, as the harness does."""
    import yaml

    raw = yaml.safe_load(_CASES.read_text())
    checked = 0
    for case in raw["pure_cases"]:
        if case["package"] != "mbwr" or case["T"] > 180.0:
            continue
        p_sat = case["expected"]["bubble_P"]
        liq = mbwr.phase_props({case["fluid"]: 1.0}, case["T"], p_sat, PhaseKind.HC_LIQUID)
        vap = mbwr.phase_props({case["fluid"]: 1.0}, case["T"], p_sat, PhaseKind.VAPOR)
        assert math.isclose(liq.density, case["expected"]["rho_L"], rel_tol=0.03), case["id"]
        assert math.isclose(vap.density, case["expected"]["rho_V"], rel_tol=0.08), case["id"]
        checked += 1
    assert checked >= 3


def test_mbwr_coefficients_match_appendix_j() -> None:
    """Spot-anchor the printed Appendix J values (Younglove & Ely 1987, pp. 794-796).

    The full 96-entry digit check ran in the T-16b verification pass; these are the
    entries the OCR pass misread or flagged, held in the suite so a regression in
    transcription cannot pass the internal-consistency tests unnoticed (the
    2026-10-22 lesson).
    """
    expected = {
        "C1": {5: -0.2234398926e4, 32: 0.6766926453e-6},  # methane p. 794
        "C2": {3: -0.1669704591e1, 32: 0.2239717230e-2},  # ethane p. 795; G(3) was mistranscribed once
        "C3": {25: 0.9936666689e3, 29: 0.1108612343e1},  # propane p. 796
    }
    for cid, spots in expected.items():
        g = _YE_FLUIDS[cid].g
        for i, want in spots.items():
            assert g[i - 1] == want, f"{cid} G({i}): {g[i - 1]!r} != printed {want!r}"


def test_bwrs_enthalpy_departure_is_dimensionless() -> None:
    """Regression: _bwrs_h_dep returned H_res in psia-ft3/lbmol while every caller read H_res/(RT).

    The departure must equal the thermodynamic identity -T (d a_res/dT)_rho + Z - 1 on the
    verified a_res surface (the bug inflated saturated-liquid Cp to about -4e4 J/(mol K)).
    """
    from ngdesign.thermo.helmholtz import _BWRS_R, _bwrs_a_res, _bwrs_h_dep, _bwrs_pressure

    p = _bwrs_mix(("C1", "C3"), (0.6, 0.4))
    for rho, t_r in ((0.08, 279.0), (1.2, 279.0), (0.05, 540.0)):
        d_t = 1e-3
        da_dt = (_bwrs_a_res(rho, t_r + d_t, p) - _bwrs_a_res(rho, t_r - d_t, p)) / (2.0 * d_t)
        z = _bwrs_pressure(rho, t_r, p) / (rho * _BWRS_R * t_r)
        assert math.isclose(_bwrs_h_dep(rho, t_r, p), -t_r * da_dt + z - 1.0, rel_tol=1e-7)


@pytest.mark.parametrize("row", ["bwrs", "bwr_ls", "mbwr"])
@pytest.mark.parametrize(("cid", "T"), [("C1", 155.0), ("C3", 300.0)])
def test_bwr_family_saturation_clapeyron_consistency(row: str, cid: str, T: float) -> None:
    """Regression: at a pure saturation state H_V - H_L must equal T (S_V - S_L).

    Before the fix the entropy departure lacked the ln Z term (ideal-gas reference at
    (T, P), not (T, rho)) and the BWRS rows used -2 a_res: T dS missed dH by >50 %.
    """
    from ngdesign.registry import create

    pkg = create("thermo", row)
    z = {cid: 1.0}
    p_sat = pkg.bubble_point(z, T=T).P
    vap = pkg.phase_props(z, T, p_sat, PhaseKind.VAPOR)
    liq = pkg.phase_props(z, T, p_sat, PhaseKind.HC_LIQUID)
    d_h = vap.enthalpy - liq.enthalpy
    assert d_h > 0.0
    assert math.isclose(d_h, T * (vap.entropy - liq.entropy), rel_tol=1e-5)


@pytest.mark.parametrize("row", ["bwrs", "bwr_ls"])
def test_bwrs_saturated_liquid_cp_matches_reference(row: str) -> None:
    """Regression: saturated-liquid methane Cp at 155 K within 5 % of the bound reference case."""
    import yaml

    from ngdesign.registry import create

    raw = yaml.safe_load(_CASES.read_text())
    case = next(c for c in raw["pure_cases"] if c["id"] == "bwr_ls-C1-155.0K")
    pkg = create("thermo", row)
    cp = pkg.phase_props({"C1": 1.0}, 155.0, case["expected"]["bubble_P"], PhaseKind.HC_LIQUID).cp
    assert math.isclose(cp, case["expected"]["Cp"], rel_tol=0.05)


def test_bwrs_ideal_mixing_entropy() -> None:
    """Regression: the BWRS ideal-gas entropy carries -R sum x ln x (it was missing)."""
    from ngdesign.thermo.helmholtz import BWRSPackage

    pkg = BWRSPackage()
    ids, T, P = ("C1", "N2"), 300.0, 1e5
    pure = 0.5 * pkg._s_ig(("C1",), (1.0,), T, P) + 0.5 * pkg._s_ig(("N2",), (1.0,), T, P)
    mixed = pkg._s_ig(ids, (0.5, 0.5), T, P)
    assert math.isclose(mixed - pure, 8.314462618 * math.log(2.0), rel_tol=1e-6)


def test_bwrs_mixture_saturation_successive_substitution() -> None:
    """Regression: the shared SS solver for mixtures (bubble/dew pressure and incipient phase).

    Before the fix the dew branch evaluated the liquid at the feed composition and stepped
    P the wrong way (dew pressures came out ABOVE the bubble pressures, e.g. 3.34 vs
    1.81 MPa at 160 K), and the bubble incipient vapour was a one-step K at the feed
    composition, so at higher pressure it returned the liquid composition itself
    (y_C1 = 0.1695 at 277.59 K for a measured 0.7677).
    """
    from ngdesign.thermo.helmholtz import BWRSPackage

    pkg = BWRSPackage()
    gas = {"C1": 0.9, "CO2": 0.05, "N2": 0.05}
    for T in (140.0, 160.0, 180.0):
        assert pkg.dew_point(gas, T=T).P < pkg.bubble_point(gas, T=T).P
    sat = pkg.bubble_point({"C1": 0.1695, "C3": 0.8305}, T=277.59)
    y_c1 = sat.incipient_composition["C1"]
    assert y_c1 > 0.7  # measured 0.7677 (Reamer, Sage & Lacey 1950); the bug gave 0.1695
    # the incipient vapour is in equilibrium: sum of liquid K x equals 1 at the converged state
    dew = pkg.dew_point({"C1": y_c1, "C3": 1.0 - y_c1}, T=277.59)
    assert math.isclose(dew.P, sat.P, rel_tol=1e-6)
    assert math.isclose(dew.incipient_composition["C1"], 0.1695, abs_tol=1e-6)


def test_bwrs_ph_flash_above_cricondenbar_inverts_pt_flash() -> None:
    """Regression: with no saturation boundary at P the PH flash inverts flash_pt."""
    from ngdesign.thermo.helmholtz import BWRSPackage

    pkg = BWRSPackage()
    gas = {"C1": 0.9, "CO2": 0.05, "N2": 0.05}
    ref = pkg.flash_pt(gas, 300.0, 5e6, 1.0)
    back = pkg.flash_ph(gas, 5e6, ref.enthalpy, 1.0)
    assert math.isclose(back.T, 300.0, abs_tol=1e-6)
