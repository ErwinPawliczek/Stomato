"""Tests for the API RP 14E erosional velocity correlation (spec S-07)."""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.sizing.erosional import erosional_api14e


def test_hand_checked_case() -> None:
    """rho=100 kg/m3, C=100: v_e = 100/sqrt(6.24279606) ft/s converted to m/s."""
    got = erosional_api14e(rho_mix_kg_m3=100, C=100)
    assert math.isclose(got["v_erosional_m_s"], 12.199032514920544, rel_tol=1e-12)


def test_first_golden_case() -> None:
    """Inputs of data/golden/erosional_api14e.yaml case 0, expected value from the file."""
    got = erosional_api14e(rho_mix_kg_m3=50, C=100)
    assert math.isclose(got["v_erosional_m_s"], 17.25204, rel_tol=1e-4)


def test_scales_as_inverse_sqrt_density() -> None:
    """Quadrupling density halves the erosional velocity."""
    lo = erosional_api14e(rho_mix_kg_m3=50, C=100)["v_erosional_m_s"]
    hi = erosional_api14e(rho_mix_kg_m3=200, C=100)["v_erosional_m_s"]
    assert math.isclose(lo, 2.0 * hi, rel_tol=1e-12)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rho_mix_kg_m3": 0, "C": 100},
        {"rho_mix_kg_m3": -50, "C": 100},
        {"rho_mix_kg_m3": 50, "C": 0},
        {"rho_mix_kg_m3": 50, "C": -100},
    ],
)
def test_invalid_inputs_raise(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        erosional_api14e(**kwargs)


def test_plugin_registered() -> None:
    """The plugin is discoverable and reproduces the golden-file inputs."""
    assert "erosional_api14e" in registry.available("correlation")
    plugin = registry.create("correlation", "erosional_api14e")
    got = plugin(**{"rho_mix_kg_m3": 50, "C": 100})
    assert math.isclose(got["v_erosional_m_s"], 17.25204, rel_tol=1e-4)
