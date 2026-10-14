"""Spec S-27 acceptance tests: centrifugal pump."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed


def _solve(thermo: Thermo, params: dict[str, Any]):
    unit = registry.create("unit", "pump")
    feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return inlets, unit.solve(inlets, params, thermo)


def test_power_matches_q_dp_over_eta_within_one_percent(thermo) -> None:
    inlets, result = _solve(thermo, {"P_out": 1.5e6, "eta": 0.65})
    inlet = inlets["inlet"]
    rho = max(
        (p for p in inlet.phases if p.kind != "vapor"),
        key=lambda p: p.mole_fraction,
    ).density
    Q = inlet.mass_flow / rho
    expected = Q * (1.5e6 - inlet.P) / 0.65
    assert result.power_W == pytest.approx(expected, rel=0.01)
    assert result.info["Q_m3_s"] == pytest.approx(Q, rel=1e-9)


def test_head_consistent_with_its_own_density(thermo) -> None:
    """head_m must equal dP/(rho·g) for the same rho that produced Q_m3_s."""
    inlets, result = _solve(thermo, {"P_out": 1.5e6, "eta": 0.65})
    inlet = inlets["inlet"]
    rho = inlet.mass_flow / result.info["Q_m3_s"]  # density the plugin used
    dP = 1.5e6 - inlet.P
    assert result.info["head_m"] == pytest.approx(dP / (rho * 9.80665), rel=1e-9)


def test_rejects_vapor_inlet(thermo) -> None:
    unit = registry.create("unit", "pump")
    feeds, params = unit.example_case()
    feeds["inlet"]["T"] = 340.0  # above the blend bubble point at 1.0 MPa
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="vapor"):
        unit.solve(inlets, params, thermo)
