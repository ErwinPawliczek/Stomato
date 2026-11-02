"""The Wohl three-suffix gE model: both classic forms are its limits, and the row differs."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.thermo.ge_models import (
    BinaryOnlyModelError,
    Margules,
    VanLaar,
    WohlThreeSuffix,
    gammas_from_ge,
)

A12, A21 = 3622.67, 2883.17  # data/thermo_params/margules/pairs.yaml, EtOH/H2O
V_RATIO = 58.7 / 18.07
T = 350.0
H = 1e-6


@pytest.mark.parametrize("x1", [0.05, 0.3, 0.5, 0.9])
def test_equal_q_is_margules_and_q_ratio_a12_a21_is_van_laar(x1: float) -> None:
    xs = [x1, 1.0 - x1]
    margules = Margules(xs=xs, T=T, A12=A12, A21=A21)
    van_laar = VanLaar(xs=xs, T=T, A12=A12, A21=A21)
    assert WohlThreeSuffix(xs=xs, T=T, A12=A12, A21=A21, q1=2.0, q2=2.0).GE() == pytest.approx(margules.GE())
    assert WohlThreeSuffix(xs=xs, T=T, A12=A12, A21=A21, q1=A12, q2=A21).GE() == pytest.approx(van_laar.GE())


def test_published_ln_gamma_form() -> None:
    """ln gamma_1 = z2^2 [A + 2 z1 (B q1/q2 - A)] (Prausnitz et al., sec. 6.10)."""
    x1, q1, q2 = 0.3, V_RATIO, 1.0
    model = WohlThreeSuffix(xs=[x1, 1.0 - x1], T=T, A12=A12, A21=A21, q1=q1, q2=q2)
    rt = 8.31446261815324 * T
    s = q1 * x1 + q2 * (1.0 - x1)
    z1, z2 = q1 * x1 / s, q2 * (1.0 - x1) / s
    a, b = A12 / rt, A21 / rt
    assert math.log(gammas_from_ge(model)[0]) == pytest.approx(z2**2 * (a + 2.0 * z1 * (b * q1 / q2 - a)))
    assert math.log(gammas_from_ge(model)[1]) == pytest.approx(z1**2 * (b + 2.0 * z2 * (a * q2 / q1 - b)))


def test_infinite_dilution_limits_are_a12_and_a21() -> None:
    rt = 8.31446261815324 * T
    dilute_1 = WohlThreeSuffix(xs=[1e-9, 1.0 - 1e-9], T=T, A12=A12, A21=A21, q1=V_RATIO, q2=1.0)
    dilute_2 = WohlThreeSuffix(xs=[1.0 - 1e-9, 1e-9], T=T, A12=A12, A21=A21, q1=V_RATIO, q2=1.0)
    assert math.log(gammas_from_ge(dilute_1)[0]) == pytest.approx(A12 / rt, rel=1e-6)
    assert math.log(gammas_from_ge(dilute_2)[1]) == pytest.approx(A21 / rt, rel=1e-6)


@pytest.mark.parametrize("x1", [0.1, 0.5, 0.8])
def test_analytic_derivatives_match_finite_differences(x1: float) -> None:
    def make(a: float, b: float) -> WohlThreeSuffix:
        return WohlThreeSuffix(xs=[a, b], T=T, A12=A12, A21=A21, q1=V_RATIO, q2=1.0)

    x2 = 1.0 - x1
    model = make(x1, x2)
    grad = model.dGE_dxs()
    hess = model.d2GE_dxixjs()
    third = model.d3GE_dxixjxks()
    assert grad[0] == pytest.approx((make(x1 + H, x2).GE() - make(x1 - H, x2).GE()) / (2 * H), rel=1e-6)
    assert grad[1] == pytest.approx((make(x1, x2 + H).GE() - make(x1, x2 - H).GE()) / (2 * H), rel=1e-6)
    up, dn = make(x1 + H, x2), make(x1 - H, x2)
    for j in range(2):
        assert hess[0][j] == pytest.approx((up.dGE_dxs()[j] - dn.dGE_dxs()[j]) / (2 * H), rel=1e-5)
        for k in range(2):
            fd = (up.d2GE_dxixjs()[j][k] - dn.d2GE_dxixjs()[j][k]) / (2 * H)
            assert third[0][j][k] == pytest.approx(fd, rel=1e-5, abs=1e-3)


def test_ternary_refuses() -> None:
    with pytest.raises(BinaryOnlyModelError, match="Wohl"):
        WohlThreeSuffix(xs=[0.3, 0.3, 0.4], A12=A12, A21=A21, q1=1.0, q2=1.0)


def test_row_differs_from_both_base_rows_at_the_same_parameters() -> None:
    """At x = 0.5 the row's volume ratio moves the bubble point; the pure limits do not."""
    z = {"EtOH": 0.5, "H2O": 0.5}
    wohl = registry.create("thermo", "wohl3_ig").bubble_point(z, T=350.0).P
    margules = registry.create("thermo", "margules_ig").bubble_point(z, T=350.0).P
    assert abs(wohl / margules - 1.0) > 0.005
    pure = {"EtOH": 1.0, "H2O": 0.0}
    assert registry.create("thermo", "wohl3_ig").bubble_point(pure, T=350.0).P == pytest.approx(
        registry.create("thermo", "margules_ig").bubble_point(pure, T=350.0).P, rel=1e-9
    )
