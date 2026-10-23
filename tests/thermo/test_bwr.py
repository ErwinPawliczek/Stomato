"""BWR-family packages (spec T-16b): MBWR-32 and the provisional Lee-Starling."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from ngdesign.contracts import PhaseKind
from ngdesign.thermo.bwr import MBWR32Package, _ls_mix
from ngdesign.thermo.helmholtz import ComponentNotSupported, _bwrs_mix

_CASES = Path(__file__).resolve().parents[2] / "data" / "validation" / "helmholtz" / "cases.yaml"


@pytest.fixture(scope="module")
def mbwr() -> MBWR32Package:
    return MBWR32Package()


def test_mbwr_pure_flash_liquid_vapor_branches(mbwr: MBWR32Package) -> None:
    """Below the dome the two-phase split reports both phases; outside it, one."""
    st = mbwr.flash_pt({"C1": 1.0}, 150.0, 3e6, 1.0)
    kinds = [p.kind for p in st.phases]
    assert kinds == [PhaseKind.HC_LIQUID, PhaseKind.VAPOR]
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
