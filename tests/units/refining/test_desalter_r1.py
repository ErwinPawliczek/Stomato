"""desalter R1 tests (``specs/backend/units/desalter.md``, option B: user properties)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining._cuts import RefiningSpecError
from ngdesign.units.refining.desalter import Desalter
from ngdesign.units.refining.desalter_r1 import DesalterR1, _splits


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = DesalterR1.example_case()
    return {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}


def test_splits_closed_form() -> None:
    """Spec calc_desalter.py: Q 0.1, A 200, rho 850/935, mu 2e-3, d50 300/20 um, n 2.5."""
    u, d_c, c_m, c_f, carry, salt = _splits(
        0.1, 200.0, 850.0, 935.0, 2.0e-3, 300e-6, 20e-6, 2.5, 0.9, 10.0, 50.0
    )
    assert u == pytest.approx(0.0005, rel=1e-10)
    assert d_c == pytest.approx(1.46948938045e-4, rel=1e-10)
    assert c_m == pytest.approx(0.109877430067, rel=1e-10)
    assert c_f == pytest.approx(1.0, rel=1e-10)
    assert carry == pytest.approx(0.124712806232, rel=1e-10)
    assert salt == pytest.approx(0.80111031294, rel=1e-10)


def test_identity_with_r0(thermo: Thermo) -> None:
    """R0 owns the outlets: R1 equals R0 at R1's computed fractions, field for field."""
    inlets = _inlets(thermo)
    _, params = DesalterR1.example_case()
    r1 = DesalterR1().solve(inlets, params, thermo)
    r0 = Desalter().solve(
        inlets,
        {
            "T": params["T"],
            "dP": params["dP"],
            "water_carryover_frac": r1.info["water_carryover_frac"],
            "salt_removal": r1.info["salt_removal"],
        },
        thermo,
    )
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W


def test_more_area_never_carries_more(thermo: Thermo) -> None:
    _, params = DesalterR1.example_case()
    small = DesalterR1().solve(_inlets(thermo), {**params, "settling_area_m2": 50.0}, thermo)
    large = DesalterR1().solve(_inlets(thermo), {**params, "settling_area_m2": 500.0}, thermo)
    assert large.info["water_carryover_frac"] <= small.info["water_carryover_frac"]


def test_thinner_oil_carries_less(thermo: Thermo) -> None:
    """Under option B the temperature effect arrives through mu_oil_Pa_s."""
    _, params = DesalterR1.example_case()
    thick = DesalterR1().solve(_inlets(thermo), {**params, "mu_oil_Pa_s": 4.0e-3}, thermo)
    thin = DesalterR1().solve(_inlets(thermo), {**params, "mu_oil_Pa_s": 1.0e-3}, thermo)
    assert thin.info["water_carryover_frac"] < thick.info["water_carryover_frac"]


def test_infinite_area_limit() -> None:
    _, _, _, _, carry, salt = _splits(0.1, 1.0e9, 850.0, 935.0, 2.0e-3, 300e-6, 20e-6, 2.5, 0.9, 10.0, 50.0)
    assert carry < 1e-12
    assert salt > 1.0 - 1e-12


def test_full_mixing_limit() -> None:
    """eps = 1: salt removal = 1 - c_m."""
    _, _, c_m, _, _, salt = _splits(0.1, 200.0, 850.0, 935.0, 2.0e-3, 300e-6, 20e-6, 2.5, 1.0, 10.0, 50.0)
    assert salt == pytest.approx(1.0 - c_m, rel=1e-14)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"settling_area_m2": 0.0}, "settling_area_m2"),
        ({"d50_mixed_um": 0.0}, "d50"),
        ({"d50_fine_um": -1.0}, "d50"),
        ({"rosin_rammler_n": 0.0}, "rosin_rammler_n"),
        ({"mixing_efficiency": 1.5}, "mixing_efficiency"),
        ({"water_carryover_frac": 0.1}, "computed at R1"),
        ({"salt_removal": 0.9}, "computed at R1"),
        ({"rho_water_kg_m3": 800.0}, "density"),
        ({"mu_oil_Pa_s": 0.0}, "mu_oil_Pa_s"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {**DesalterR1.example_case()[1], **change}
    with pytest.raises(RefiningSpecError, match=match):
        DesalterR1().solve(_inlets(thermo), params, thermo)


@pytest.mark.parametrize("key", ["rho_oil_kg_m3", "rho_water_kg_m3", "mu_oil_Pa_s", "settling_area_m2", "T"])
def test_no_physical_default(thermo: Thermo, key: str) -> None:
    params = dict(DesalterR1.example_case()[1])
    del params[key]
    with pytest.raises(RefiningSpecError, match=key):
        DesalterR1().solve(_inlets(thermo), params, thermo)


def test_no_water_refused(thermo: Thermo) -> None:
    inlets = {
        "crude_in": thermo.flash_pt({"nC7": 1.0}, 403.15, 1.0e6, 1.0),
        "wash_in": thermo.flash_pt({"nC6": 1.0}, 403.15, 1.0e6, 1.0),
    }
    with pytest.raises(RefiningSpecError, match="water"):
        DesalterR1().solve(inlets, DesalterR1.example_case()[1], thermo)
