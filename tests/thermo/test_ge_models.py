"""Analytic gE derivatives for the in-house van Laar and Margules models (T-03).

Ports the T-03 probe self-check: the closed-form GE/dGE/d2GE must agree with
central finite differences of GE(), and the gammas built through the analytic
route must agree with thermo's numerically differentiated route
(`GibbsExcess.gammas_numerical`, thermo 0.6.1 activity.py). Pure feeds are
ideal; more than two components refuses.
"""

from __future__ import annotations

import pytest

from ngdesign.thermo.ge_models import BinaryOnlyModelError, Margules, VanLaar, gammas_from_ge

#: Fitted parameter sets shipped in data/thermo_params/<model>/pairs.yaml.
PARAM_CASES: list[tuple[type, dict[str, float]]] = [
    (VanLaar, {"A12": 3813.05, "A21": 2885.16}),  # EtOH/H2O azeotrope fit
    (VanLaar, {"A12": 3127.03, "A21": 8023.90}),  # MeOH/nC4 fit
    (Margules, {"A12": 3622.67, "A21": 2883.17}),  # EtOH/H2O azeotrope fit
    (Margules, {"A12": -477.87, "A21": 484.47}),  # MEG/H2O fit
    (Margules, {"A12": -2262.34, "A21": 7945.79}),  # MeOH/nC4
]
FEEDS: list[tuple[float, float]] = [(0.05, 0.95), (0.24, 0.76), (0.5, 0.5), (0.89, 0.11)]
H = 1e-6


@pytest.mark.parametrize("cls,params", PARAM_CASES)
@pytest.mark.parametrize("x1,x2", FEEDS)
def test_dGE_dxs_matches_central_difference(
    cls: type, params: dict[str, float], x1: float, x2: float
) -> None:
    """dGE_dxs is the unconstrained partial d(GE)/dx_i at fixed composition."""
    m = cls(xs=[x1, x2], T=350.0, **params)
    up = cls(xs=[x1 + H, x2], T=350.0, **params).GE()
    dn = cls(xs=[x1 - H, x2], T=350.0, **params).GE()
    fd = (up - dn) / (2 * H)
    assert m.dGE_dxs()[0] == pytest.approx(fd, rel=1e-5, abs=1e-6)


@pytest.mark.parametrize("cls,params", PARAM_CASES)
@pytest.mark.parametrize("x1,x2", FEEDS)
def test_d2GE_dxixjs_matches_second_difference(
    cls: type, params: dict[str, float], x1: float, x2: float
) -> None:
    m = cls(xs=[x1, x2], T=350.0, **params)

    def slope(x1s: float) -> float:
        return float(cls(xs=[x1s, 1.0 - x1s], T=350.0, **params).dGE_dxs()[0])

    fd = (slope(x1 + H) - slope(x1 - H)) / (2 * H)
    # dGE_dxs[0] along the binary line is d(GE)/dx1 - d(GE)/dx2 up to the line
    # derivative; the Hessian entry d2GE/dx1^2 at fixed x2 differs by sign and
    # mixed terms, so compare against the Hessian's linear form directly.
    hess = m.d2GE_dxixjs()
    analytic = hess[0][0] - hess[0][1]
    assert analytic == pytest.approx(fd, rel=1e-5, abs=1e-6)


@pytest.mark.parametrize("cls,params", PARAM_CASES)
@pytest.mark.parametrize("x1,x2", FEEDS)
def test_gammas_match_thermo_numerical(cls: type, params: dict[str, float], x1: float, x2: float) -> None:
    m = cls(xs=[x1, x2], T=350.0, **params)
    assert gammas_from_ge(m) == pytest.approx(list(m.gammas_numerical()), rel=1e-6)


@pytest.mark.parametrize("cls,params", PARAM_CASES)
def test_pure_feed_is_ideal(cls: type, params: dict[str, float]) -> None:
    """The pure component has gamma 1; the absent one shows the finite gamma-infinity."""
    for feed, pure_idx in (([1.0, 0.0], 0), ([0.0, 1.0], 1)):
        m = cls(xs=feed, T=350.0, **params)
        gammas = gammas_from_ge(m)
        assert gammas[pure_idx] == pytest.approx(1.0, rel=1e-10)
        other = gammas[1 - pure_idx]
        assert other > 0.0
        assert m.GE() == pytest.approx(0.0, abs=1e-10)


@pytest.mark.parametrize("cls,name", [(VanLaar, "van Laar"), (Margules, "Margules")])
def test_ternary_support_refused(cls: type, name: str) -> None:
    with pytest.raises(BinaryOnlyModelError, match=name):
        cls(xs=[0.34, 0.33, 0.33], T=350.0, A12=1000.0, A21=2000.0)
