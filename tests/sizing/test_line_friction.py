"""Tests for the S-06 Darcy-Weisbach / Colebrook correlation."""

import math
from typing import Any

import pytest

from ngdesign.registry import create
from ngdesign.sizing.line_friction import darcy_colebrook


def test_turbulent_hand_checked_case() -> None:
    # Golden case 1 values; intermediates hand-checked:
    # A = pi*0.1541^2/4 = 0.0186416... -> v = 0.05/A = 2.680864 m/s
    # Re = 700*2.680864*0.1541/0.0005 = 578369.68
    got = darcy_colebrook(Q_m3_s=0.05, D_m=0.1541, rho=700.0, mu=0.0005, roughness_m=4.57e-5, L_m=100.0)
    assert math.isclose(got["velocity_m_s"], 2.680864, rel_tol=1e-6)
    assert math.isclose(got["Re"], 578369.68, rel_tol=1e-6)
    assert math.isclose(got["darcy_f"], 0.01609053, rel_tol=1e-6)
    # dP = f*(L/D)*rho*v^2/2 with the friction factor above
    expected_dP = got["darcy_f"] * (100.0 / 0.1541) * 700.0 * got["velocity_m_s"] ** 2 / 2
    assert math.isclose(got["dP_Pa"], expected_dP, rel_tol=1e-12)


def test_turbulent_friction_satisfies_colebrook_equation() -> None:
    got = darcy_colebrook(Q_m3_s=1e-3, D_m=0.1, rho=1000.0, mu=1e-3, roughness_m=1e-5, L_m=10.0)
    re, ed, f = got["Re"], 1e-5 / 0.1, got["darcy_f"]
    assert re > 2300
    # 1/sqrt(f) = -2*log10(ed/3.7 + 2.51/(Re*sqrt(f)))
    lhs = 1.0 / math.sqrt(f)
    rhs = -2.0 * math.log10(ed / 3.7 + 2.51 / (re * math.sqrt(f)))
    assert math.isclose(lhs, rhs, rel_tol=1e-9)


def test_laminar_uses_64_over_re() -> None:
    # Re = 1000*(5.0929e-3)*0.05/0.1 = 2.5465 < 2300 -> f = 64/Re
    got = darcy_colebrook(Q_m3_s=1e-5, D_m=0.05, rho=1000.0, mu=0.1, roughness_m=4.57e-5, L_m=1.0)
    re = got["Re"]
    assert re < 2300
    assert math.isclose(got["darcy_f"], 64.0 / re, rel_tol=1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"Q_m3_s": 0.0},  # zero flow
        {"Q_m3_s": -1e-3},  # negative flow
        {"D_m": 0.0},  # zero diameter
        {"D_m": -0.1},
        {"rho": 0.0},
        {"mu": 0.0},
        {"roughness_m": -1e-5},  # negative roughness (zero is physical: smooth)
        {"L_m": 0.0},
        {"L_m": -10.0},
    ],
)
def test_invalid_inputs_raise(kwargs: dict[str, Any]) -> None:
    full = {"Q_m3_s": 0.05, "D_m": 0.1541, "rho": 700.0, "mu": 0.0005, "roughness_m": 0.0, "L_m": 100.0}
    with pytest.raises(ValueError):
        darcy_colebrook(**{**full, **kwargs})


def test_plugin_registered_and_callable() -> None:
    plugin = create("correlation", "darcy_colebrook")
    got = plugin(Q_m3_s=0.05, D_m=0.1541, rho=700, mu=0.0005, roughness_m=4.57e-05, L_m=100)
    assert set(got) == {"velocity_m_s", "Re", "darcy_f", "dP_Pa"}
