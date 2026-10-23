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

