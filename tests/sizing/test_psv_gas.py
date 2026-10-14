"""Tests for the S-09 API 520 gas relief area (critical flow)."""

import math

import pytest

from ngdesign.registry import create
from ngdesign.sizing.psv_gas import api526_orifice, psv_api520_gas

GOLDEN_CASE_1 = dict(W_lb_h=50000, T_R=560, Z=0.9, M=19.0, k=1.27, P1_psia=1100, Kd=0.975, Kb=1.0, Kc=1.0)


def test_hand_checked_case() -> None:
    # k = 1.27: C = 520*sqrt(1.27*(2/2.27)^(2.27/0.27)) = 344.127...
    # A = 50000/(344.127*0.975*1100*1*1)*sqrt(560*0.9/19) = 0.697738 in2
    got = psv_api520_gas(**GOLDEN_CASE_1)
    assert math.isclose(got["C"], 344.12712, rel_tol=1e-6)
    assert math.isclose(got["area_in2"], 0.697738, rel_tol=1e-5)


def test_hand_checked_numbers() -> None:
    # Independent hand check with round numbers:
    # k = 1.4 -> C = 520*sqrt(1.4*(2/2.4)^(2.4/0.4)) = 520*sqrt(1.4*0.6667^6)
    c_14 = 520.0 * math.sqrt(1.4 * (2.0 / 2.4) ** 6)
    # W = C*Kd*P1*A/sqrt(T*Z/M): pick A = 1 in2 and back out W
    got = psv_api520_gas(W_lb_h=1.0, T_R=520.0, Z=1.0, M=29.0, k=1.4, P1_psia=100.0, Kd=1.0, Kb=1.0, Kc=1.0)
    expected_area = 1.0 / (c_14 * 100.0) * math.sqrt(520.0 / 29.0)
    assert math.isclose(got["C"], c_14, rel_tol=1e-12)
    assert math.isclose(got["area_in2"], expected_area, rel_tol=1e-12)


def test_api526_orifice_selects_smallest_fitting_orifice() -> None:
    # Golden case 1 area 0.697738 in2: the standard F orifice is 0.307 in2,
    # G is 0.503 in2, H is 0.785 in2 -> H is the smallest fitting letter.
    assert api526_orifice(0.697738) == "H"
    assert api526_orifice(0.503) == "G"
    assert api526_orifice(0.110) == "D"


def test_api526_orifice_rejects_invalid_and_oversized() -> None:
    with pytest.raises(ValueError):
        api526_orifice(0.0)
    with pytest.raises(ValueError, match="largest API 526 orifice"):
        api526_orifice(100.0)


@pytest.mark.parametrize(
    "overrides",
    [
        {"W_lb_h": 0.0},
        {"W_lb_h": -1.0},
        {"T_R": 0.0},
        {"Z": 0.0},
        {"M": 0.0},
        {"k": 1.0},  # k must be > 1 for critical flow
        {"P1_psia": 0.0},
        {"Kd": 0.0},
        {"Kd": 1.5},
        {"Kb": 0.0},
        {"Kc": 0.0},
    ],
)
def test_invalid_inputs_raise(overrides: dict) -> None:
    kwargs = {**GOLDEN_CASE_1, **overrides}
    with pytest.raises(ValueError):
        psv_api520_gas(**kwargs)


def test_plugin_registered_and_callable() -> None:
    plugin = create("correlation", "psv_api520_gas")
    got = plugin(**GOLDEN_CASE_1)
    assert set(got) == {"C", "area_in2"}
