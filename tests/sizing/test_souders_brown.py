"""Tests for the Souders-Brown correlation (spec S-03)."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.sizing.souders_brown import souders_brown


def test_hand_checked_case() -> None:
    """K=0.1, rhoL=700, rhoG=30, Q=1.2: v = 0.1*sqrt(670/30), D = sqrt(4*1.2/(pi*v))."""
    got = souders_brown(K_m_s=0.1, rho_liquid=700, rho_gas=30, gas_flow_m3_s=1.2)
    assert math.isclose(got["v_max_m_s"], 0.4725815626252608, rel_tol=1e-12)
    assert math.isclose(got["min_diameter_m"], 1.7980728992285826, rel_tol=1e-12)


def test_first_golden_case() -> None:
    """Inputs of data/golden/souders_brown.yaml case 0, expected values from the file."""
    got = souders_brown(K_m_s=0.107, rho_liquid=650, rho_gas=50, gas_flow_m3_s=2.0)
    assert math.isclose(got["v_max_m_s"], 0.370659, rel_tol=1e-5)
    assert math.isclose(got["min_diameter_m"], 2.621096, rel_tol=1e-5)


def test_zero_flow_gives_zero_diameter() -> None:
    got = souders_brown(K_m_s=0.1, rho_liquid=700, rho_gas=30, gas_flow_m3_s=0.0)
    assert got["min_diameter_m"] == 0.0
    assert got["v_max_m_s"] > 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"K_m_s": 0.0, "rho_liquid": 700, "rho_gas": 30, "gas_flow_m3_s": 1.0},
        {"K_m_s": -0.1, "rho_liquid": 700, "rho_gas": 30, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 0, "rho_gas": 30, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 700, "rho_gas": 0, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 700, "rho_gas": -30, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 30, "rho_gas": 700, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 700, "rho_gas": 700, "gas_flow_m3_s": 1.0},
        {"K_m_s": 0.1, "rho_liquid": 700, "rho_gas": 30, "gas_flow_m3_s": -1.0},
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        souders_brown(**kwargs)


def test_plugin_registered() -> None:
    """The plugin is discoverable and reproduces the golden-file inputs."""
    assert "souders_brown" in registry.available("correlation")
    plugin = registry.create("correlation", "souders_brown")
    got = plugin(**{"K_m_s": 0.107, "rho_liquid": 650, "rho_gas": 50, "gas_flow_m3_s": 2.0})
    assert math.isclose(got["v_max_m_s"], 0.370659, rel_tol=1e-5)
    assert math.isclose(got["min_diameter_m"], 2.621096, rel_tol=1e-5)
