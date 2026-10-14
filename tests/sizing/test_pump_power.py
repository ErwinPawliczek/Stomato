"""Tests for the S-08 pump power correlation."""

import math

import pytest

from ngdesign.registry import create
from ngdesign.sizing.pump_power import G, npsh_available, pump_power


def test_hand_checked_case() -> None:
    # Golden case 1: P_hyd = 0.02*1.2e6 = 24000 W; P_shaft = 24000/0.65 = 36923.0769 W
    got = pump_power(Q_m3_s=0.02, dP_Pa=1.2e6, eta=0.65)
    assert math.isclose(got["hydraulic_power_W"], 24000.0, rel_tol=1e-6)
    assert math.isclose(got["shaft_power_W"], 36923.0769, rel_tol=1e-6)


def test_eta_one_means_no_losses() -> None:
    got = pump_power(Q_m3_s=0.01, dP_Pa=5e5, eta=1.0)
    assert math.isclose(got["hydraulic_power_W"], 5000.0, rel_tol=1e-12)
    assert math.isclose(got["shaft_power_W"], got["hydraulic_power_W"], rel_tol=1e-12)


@pytest.mark.parametrize(
    "Q,dP,eta",
    [
        (0.0, 1e5, 0.7),  # zero flow
        (-0.01, 1e5, 0.7),  # negative flow
        (0.01, 0.0, 0.7),  # zero pressure rise
        (0.01, -1e5, 0.7),  # negative pressure rise
        (0.01, 1e5, 0.0),  # zero efficiency
        (0.01, 1e5, -0.5),  # negative efficiency
        (0.01, 1e5, 1.5),  # efficiency above 100 %
    ],
)
def test_pump_power_invalid_inputs(Q: float, dP: float, eta: float) -> None:
    with pytest.raises(ValueError):
        pump_power(Q_m3_s=Q, dP_Pa=dP, eta=eta)


def test_npsh_available_hand_checked() -> None:
    # (101325 - 5000)/(998*9.80665) + 2 - 0.5 = 9.8725... + 1.5
    got = npsh_available(
        P_suction_Pa=101325.0, P_vapor_Pa=5000.0, rho=998.0, static_head_m=2.0, friction_head_m=0.5
    )
    expected = (101325.0 - 5000.0) / (998.0 * G) + 2.0 - 0.5
    assert math.isclose(got, expected, rel_tol=1e-12)
    assert got > 10  # sanity: suction above vapor pressure gives healthy NPSH


def test_npsh_available_can_be_negative() -> None:
    got = npsh_available(
        P_suction_Pa=30000.0, P_vapor_Pa=90000.0, rho=800.0, static_head_m=0.0, friction_head_m=1.0
    )
    assert got < 0


@pytest.mark.parametrize(
    "P_s,Pv,rho,hf",
    [
        (101325.0, 5000.0, 0.0, 0.5),  # zero density
        (101325.0, -1.0, 998.0, 0.5),  # negative vapor pressure
        (101325.0, 5000.0, 998.0, -1.0),  # negative friction head
    ],
)
def test_npsh_available_invalid_inputs(P_s: float, Pv: float, rho: float, hf: float) -> None:
    with pytest.raises(ValueError):
        npsh_available(P_suction_Pa=P_s, P_vapor_Pa=Pv, rho=rho, static_head_m=2.0, friction_head_m=hf)


def test_plugin_registered_and_callable() -> None:
    plugin = create("correlation", "pump_power")
    got = plugin(Q_m3_s=0.02, dP_Pa=1200000.0, eta=0.65)
    assert set(got) == {"hydraulic_power_W", "shaft_power_W"}
