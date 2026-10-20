"""Saturation solvers: CoolProp agreement, self-consistency, supercritical errors (P1-01)."""

from __future__ import annotations

import math

import pytest
from CoolProp.CoolProp import PropsSI

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import SaturationError

PURE = [
    ("C1", "Methane", (120.0, 140.0, 160.0)),
    ("C2", "Ethane", (200.0, 250.0, 280.0)),
    ("C3", "n-Propane", (250.0, 300.0, 320.0)),
    ("H2O", "Water", (450.0, 480.0, 500.0)),
]
Z_C1_C3 = {"C1": 0.5, "C3": 0.5}
Z_SLICE_LIKE = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}


@pytest.mark.parametrize(("comp", "cp_name", "ts"), PURE)
def test_pure_bubble_pressure_vs_coolprop(
    thermo: Thermo, comp: str, cp_name: str, ts: tuple[float, ...]
) -> None:
    for T in ts:
        point = thermo.bubble_point({comp: 1.0}, T=T)
        ref = PropsSI("P", "T", T, "Q", 0, cp_name)
        assert math.isclose(point.P, ref, rel_tol=0.02), f"{comp} {T}K: PR {point.P} vs ref {ref}"
        assert point.kind == "bubble"
        assert math.isclose(point.incipient_composition[comp], 1.0, abs_tol=1e-9)


@pytest.mark.parametrize(("comp", "ts"), [(c, ts) for c, _cp, ts in PURE])
def test_pure_dew_equals_bubble(thermo: Thermo, comp: str, ts: tuple[float, ...]) -> None:
    """A pure fluid has one saturation pressure: both solvers converge on the same jump."""
    for T in ts:
        bubble = thermo.bubble_point({comp: 1.0}, T=T)
        dew = thermo.dew_point({comp: 1.0}, T=T)
        assert math.isclose(dew.P, bubble.P, rel_tol=1e-6), f"{comp} {T}K"


def test_pure_temperature_solve(thermo: Thermo) -> None:
    """P-given saturation: PR bubble T for water at 101325 Pa, 2% of CoolProp."""
    point = thermo.bubble_point({"H2O": 1.0}, P=101325.0)
    ref = PropsSI("T", "P", 101325.0, "Q", 0, "Water")
    assert math.isclose(point.T, ref, rel_tol=0.02)


def test_binary_brackets_the_pt_flash(thermo: Thermo) -> None:
    """Bubble T below dew T at fixed P; the PT flash is single-phase outside the bracket."""
    bubble = thermo.bubble_point(dict(Z_C1_C3), P=1.0e6)
    dew = thermo.dew_point(dict(Z_C1_C3), P=1.0e6)
    assert bubble.T < dew.T
    assert thermo.flash_pt(dict(Z_C1_C3), bubble.T - 0.01, 1.0e6, 1.0).vapor_fraction == 0.0
    assert thermo.flash_pt(dict(Z_C1_C3), dew.T + 0.01, 1.0e6, 1.0).vapor_fraction == 1.0
    assert bubble.incipient_composition != dict(Z_C1_C3)


def test_flash_tvf_roundtrip(thermo: Thermo) -> None:
    s = thermo.flash_tvf(dict(Z_SLICE_LIKE), 300.0, 0.5, 1.0)
    assert math.isclose(s.vapor_fraction, 0.5, abs_tol=1e-6)


def test_flash_pvf_roundtrip(thermo: Thermo) -> None:
    s = thermo.flash_pvf(dict(Z_SLICE_LIKE), 3.0e6, 0.5, 1.0)
    assert math.isclose(s.vapor_fraction, 0.5, abs_tol=1e-6)


def test_flash_tvf_material_balance(thermo: Thermo) -> None:
    s = thermo.flash_tvf(dict(Z_SLICE_LIKE), 300.0, 0.5, 1.0)
    for c, zc in Z_SLICE_LIKE.items():
        back = sum(p.mole_fraction * p.composition.get(c, 0.0) for p in s.phases)
        assert math.isclose(back, zc, abs_tol=1e-6)


@pytest.mark.parametrize("T", [300.0, 320.0])
def test_water_feed_saturation_on_full_flasher(thermo: Thermo, T: float) -> None:
    """Water-containing feeds saturate on the full flasher (no VL fast path).

    The hydrocarbon must be subcritical at T (propane, not methane): above its
    Tc the C1-rich vapour never condenses and the feed has no bubble point.
    """
    z = {"C3": 0.9, "H2O": 0.1}
    point = thermo.bubble_point(dict(z), T=T)
    assert point.P > 0.0
    assert thermo.bubble_point(dict(z), P=point.P).T == pytest.approx(T, rel=1e-6)


def test_supercritical_feed_raises_saturation_error(thermo: Thermo) -> None:
    """Above every component's critical point there is no two-phase region: raise."""
    with pytest.raises(SaturationError):
        thermo.bubble_point({"C1": 1.0}, T=200.0)  # methane Tc = 190.6 K
    with pytest.raises(SaturationError):
        thermo.bubble_point(dict(Z_C1_C3), P=30.0e6)  # above both critical pressures


def test_saturation_rejects_ambiguous_spec(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        thermo.bubble_point(dict(Z_C1_C3), T=300.0, P=1.0e6)
    with pytest.raises(ValueError, match="exactly one"):
        thermo.dew_point(dict(Z_C1_C3))


def test_pure_psat_matches_bubble_point(thermo: Thermo) -> None:
    for comp, _cp, ts in PURE:
        for T in ts:
            psat = thermo.pure_psat(comp, T)
            assert psat is not None
            assert math.isclose(psat, thermo.bubble_point({comp: 1.0}, T=T).P, rel_tol=0.02)


def test_pure_psat_supercritical_is_none(thermo: Thermo) -> None:
    assert thermo.pure_psat("C1", 200.0) is None
