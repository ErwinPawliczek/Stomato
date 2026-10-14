"""Tests for the S-04 counter-current LMTD correlation."""

import math

import pytest

from ngdesign.registry import create
from ngdesign.sizing.lmtd import lmtd_counter, ua_required


def test_hand_checked_case() -> None:
    # dT1 = 420 - 340 = 80, dT2 = 360 - 300 = 60
    # LMTD = (80 - 60)/ln(80/60) = 20/0.28768207... = 69.52119... K
    assert math.isclose(lmtd_counter(420.0, 360.0, 300.0, 340.0), 69.52119, rel_tol=1e-6)


def test_equal_approaches_return_dT1() -> None:
    # dT1 = dT2 = 50 -> LMTD = 50 exactly (no log(1) division)
    assert lmtd_counter(400.0, 350.0, 300.0, 350.0) == 50.0


def test_equal_within_tolerance() -> None:
    # dT1 = 50 + 5e-10 is within 1e-9 of dT2 = 50 -> the limit value dT1 is returned
    assert lmtd_counter(400.0 + 5e-10, 350.0, 300.0, 350.0) == pytest.approx(50.0 + 5e-10, rel=1e-12)


@pytest.mark.parametrize(
    "Th_in,Th_out,Tc_in,Tc_out",
    [
        (400.0, 350.0, 300.0, 410.0),  # dT1 < 0: hot outlet below cold outlet
        (400.0, 280.0, 300.0, 340.0),  # dT2 < 0: cold inlet above hot outlet
        (400.0, 350.0, 300.0, 400.0),  # dT1 == 0: pinch (cold outlet equals hot inlet)
    ],
)
def test_temperature_cross_raises(Th_in: float, Th_out: float, Tc_in: float, Tc_out: float) -> None:
    with pytest.raises(ValueError, match="temperature cross"):
        lmtd_counter(Th_in, Th_out, Tc_in, Tc_out)


def test_ua_required_hand_checked() -> None:
    # Q = 1000 W at LMTD = 50 K, F = 1 -> UA = 20 W/K
    assert math.isclose(ua_required(1000.0, 50.0), 20.0, rel_tol=1e-12)
    # F = 0.9 correction factor -> UA = 1000/(0.9*50) = 22.222... W/K
    assert math.isclose(ua_required(1000.0, 50.0, F=0.9), 1000.0 / 45.0, rel_tol=1e-12)


@pytest.mark.parametrize(
    "Q,lmtd,F",
    [
        (-1.0, 50.0, 1.0),  # negative duty
        (1000.0, 0.0, 1.0),  # zero LMTD
        (1000.0, -50.0, 1.0),  # negative LMTD
        (1000.0, 50.0, 0.0),  # zero correction factor
        (1000.0, 50.0, -1.0),  # negative correction factor
    ],
)
def test_ua_required_invalid_inputs(Q: float, lmtd: float, F: float) -> None:
    with pytest.raises(ValueError):
        ua_required(Q, lmtd, F=F)


def test_plugin_registered_and_callable() -> None:
    plugin = create("correlation", "lmtd_counter")
    got = plugin(Th_in=420, Th_out=360, Tc_in=300, Tc_out=340)
    assert set(got) == {"lmtd_K"}
    assert math.isclose(got["lmtd_K"], 69.52119, rel_tol=1e-6)
