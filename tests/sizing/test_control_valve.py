"""Tests for the S-10 liquid control-valve Cv correlation."""

import math

import pytest

from ngdesign.registry import create
from ngdesign.sizing.control_valve import cv_liquid, cv_liquid_isa


def test_hand_checked_case() -> None:
    # Cv = 100*sqrt(0.7/25) = 16.7332
    assert math.isclose(cv_liquid(100.0, 0.7, 25.0), 16.733201, rel_tol=1e-6)


def test_water_reference_case() -> None:
    # Cv = 400*sqrt(1/10) = 126.4911
    assert math.isclose(cv_liquid(400.0, 1.0, 10.0), 126.491106, rel_tol=1e-6)


def test_cv_scales_with_flow_at_fixed_conditions() -> None:
    base = cv_liquid(100.0, 1.0, 10.0)
    assert math.isclose(cv_liquid(200.0, 1.0, 10.0), 2 * base, rel_tol=1e-12)


@pytest.mark.parametrize(
    "Q,SG,dP",
    [
        (0.0, 1.0, 10.0),  # zero flow
        (-100.0, 1.0, 10.0),  # negative flow
        (100.0, 0.0, 10.0),  # zero specific gravity
        (100.0, -0.7, 10.0),  # negative specific gravity
        (100.0, 1.0, 0.0),  # zero pressure drop
        (100.0, 1.0, -25.0),  # negative pressure drop
    ],
)
def test_invalid_inputs_raise(Q: float, SG: float, dP: float) -> None:
    with pytest.raises(ValueError):
        cv_liquid(Q, SG, dP)


def test_isa_wrapper_agrees_with_simple_formula() -> None:
    # 100 gpm (6.309e-3 m3/s) of water through a 25 psi (172369 Pa) drop.
    # Non-choked turbulent case: P2 far above the water vapor pressure.
    cv_isa = cv_liquid_isa(
        Q_m3_s=6.309e-3,
        rho=998.0,
        Psat_Pa=2300.0,
        Pc_Pa=22.064e6,
        mu=1e-3,
        P1_Pa=700000.0,
        P2_Pa=700000.0 - 172369.0,
    )
    cv_simple = cv_liquid(100.0, 1.0, 25.0)
    assert math.isclose(cv_isa, cv_simple, rel_tol=0.05)


def test_isa_wrapper_invalid_inputs_raise() -> None:
    with pytest.raises(ValueError, match="P1_Pa > P2_Pa"):
        cv_liquid_isa(
            Q_m3_s=6.309e-4,
            rho=998.0,
            Psat_Pa=2300.0,
            Pc_Pa=22.064e6,
            mu=1e-3,
            P1_Pa=100000.0,
            P2_Pa=200000.0,
        )
    with pytest.raises(ValueError):
        cv_liquid_isa(
            Q_m3_s=0.0,
            rho=998.0,
            Psat_Pa=2300.0,
            Pc_Pa=22.064e6,
            mu=1e-3,
            P1_Pa=700000.0,
            P2_Pa=600000.0,
        )


def test_plugin_registered_and_callable() -> None:
    plugin = create("correlation", "cv_liquid")
    got = plugin(Q_gpm=100, SG=0.7, dP_psi=25)
    assert set(got) == {"Cv"}
