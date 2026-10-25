"""Closed-form, identity and refusal tests for the expander R1 (spec expander.md).

Inlet for every test: the R0 example feed ``Expander.example_case()``
(dry separator gas, 322.15 K, 7.0 MPa), flashed with ``pr``; P_out 2.0 MPa.

Closed-form (spec's hand-computed values, script
``scratchpad/unit-specs/calc_expander.py``):
  D = 0.30 m, N = 20000 rpm  ->  u = pi*D*N/60 = 314.159265 m/s (exact pi*100).
  M = mdot/F = 0.0201670784 kg/mol (from the flashed inlet).
  dh_s = (h1 - h(P2, s1))/M = 125823.613 J/kg  (pr flash).
  c0 = sqrt(2*dh_s) = sqrt(251647.226) = 501.644521 m/s.
  nu = u/c0 = 314.159265/501.644521 = 0.626258739.
  eta = map(nu): the test map is linear, eta = 0.30 + 0.70*nu, which PCHIP
  reproduces exactly -> eta = 0.30 + 0.70*0.626258739 = 0.738381118.
  Outlet from R0 at that efficiency: T_out = 264.634943 K,
  power_W = -1296007.11 W, outlet vapor_fraction = 0.973902259
  (two-phase cryogenic outlet, allowed as in R0).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.expander import Expander
from ngdesign.units.flow.expander_r1 import (
    ExpanderFlowRangeError,
    ExpanderMapRangeError,
    ExpanderR1,
    ExpanderR1SpecError,
)
from tests.conftest import flash_feed

MAP: dict[str, Any] = {
    "velocity_ratio": [0.40, 0.50, 0.60, 0.70, 0.80],
    "efficiency": [0.58, 0.65, 0.72, 0.79, 0.86],
}


def base_params(**over: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "P_out": 2.0e6,
        "rotor_diameter_m": 0.30,
        "speed_rpm": 20000.0,
        "map": MAP,
    }
    params.update(over)
    return params


def example_inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = Expander.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def test_closed_form(thermo: Thermo) -> None:
    """The spec's worked point, to the stated tolerances (docstring above)."""
    result = ExpanderR1().solve(example_inlets(thermo), base_params(), thermo)
    # u, c0, dh_s are printed source values without a stated tolerance; the
    # check is the print's own rounding (u to 1e-6, c0 to 1e-6, dh_s to 1e-3).
    assert result.info["tip_speed_m_s"] == pytest.approx(314.159265, abs=1e-6)
    assert result.info["dh_isentropic_J_kg"] == pytest.approx(125823.613, abs=1e-3)
    assert result.info["spouting_velocity_m_s"] == pytest.approx(501.644521, abs=1e-6)
    assert result.info["velocity_ratio"] == pytest.approx(0.626258739, rel=1e-9)
    assert result.info["eta"] == pytest.approx(0.738381118, rel=1e-9)
    assert result.info["T_out"] == pytest.approx(264.634943, rel=1e-7)
    assert result.power_W == pytest.approx(-1296007.11, rel=1e-7)
    assert result.power_W < 0.0 and result.duty_W == 0.0
    outlet = result.outlets["gas_out"]
    assert outlet.vapor_fraction == pytest.approx(0.973902259, abs=1e-8)
    # The mapped efficiency reached R0 under its own key.
    assert result.info["power_recovered_w"] == pytest.approx(1296007.11, rel=1e-7)


def test_identity_delegates_exactly_to_r0(thermo: Thermo) -> None:
    """R1 == Expander().solve(...) with eta_isentropic = info['eta'], exactly."""
    inlets = example_inlets(thermo)
    r1 = ExpanderR1().solve(inlets, base_params(), thermo)
    r0 = Expander().solve(inlets, {"P_out": 2.0e6, "eta_isentropic": r1.info["eta"]}, thermo)
    assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
    assert r1.power_W == r0.power_W
    assert r1.duty_W == r0.duty_W
    for key, value in r0.info.items():
        assert r1.info[key] == value


def test_flat_map_reduces_to_r0_example(thermo: Thermo) -> None:
    """A flat map at eta = 0.80 reproduces R0's own example result exactly."""
    feeds, r0_params = Expander.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    flat = dict(base_params(map={"velocity_ratio": [0.3, 0.9], "efficiency": [0.80, 0.80]}))
    r1 = ExpanderR1().solve(inlets, flat, thermo)
    r0 = Expander().solve(inlets, r0_params, thermo)
    assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
    assert r1.power_W == r0.power_W
    assert r1.info["eta"] == 0.80


def test_refuse_liquid_inlet(thermo: Thermo) -> None:
    """The R0 outlet is two-phase (vf < 0.999); feeding it back refuses."""
    feeds, _ = Expander.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    r0 = Expander().solve(inlets, {"P_out": 2.0e6, "eta_isentropic": 0.80}, thermo)
    two_phase = r0.outlets["gas_out"]
    assert two_phase.vapor_fraction < 0.999
    with pytest.raises(ExpanderR1SpecError, match="inlet has liquid"):
        ExpanderR1().solve({"gas_in": two_phase}, base_params(), thermo)


@pytest.mark.parametrize(
    "over",
    [
        pytest.param({"P_out": 7.0e6}, id="P_out_at_or_above_P_in"),
        pytest.param({"P_out": -1.0}, id="P_out_negative"),
    ],
)
def test_refuse_bad_p_out(thermo: Thermo, over: dict[str, Any]) -> None:
    """P_out below P_in and positive, as in R0."""
    with pytest.raises(ExpanderR1SpecError, match="P_out"):
        ExpanderR1().solve(example_inlets(thermo), base_params(**over), thermo)


def test_refuse_missing_p_out(thermo: Thermo) -> None:
    """P_out is required."""
    params = base_params()
    del params["P_out"]
    with pytest.raises(ExpanderR1SpecError, match="P_out"):
        ExpanderR1().solve(example_inlets(thermo), params, thermo)


@pytest.mark.parametrize(
    "over",
    [
        pytest.param({"rotor_diameter_m": 0.0}, id="rotor_diameter_m_zero"),
        pytest.param({"rotor_diameter_m": -0.30}, id="rotor_diameter_m_negative"),
        pytest.param({"speed_rpm": 0.0}, id="speed_rpm_zero"),
        pytest.param({"speed_rpm": -1.0}, id="speed_rpm_negative"),
    ],
)
def test_refuse_nonpositive_geometry(thermo: Thermo, over: dict[str, Any]) -> None:
    """rotor_diameter_m and speed_rpm must be > 0; the error names the param."""
    with pytest.raises(ExpanderR1SpecError, match=next(iter(over))):
        ExpanderR1().solve(example_inlets(thermo), base_params(**over), thermo)


@pytest.mark.parametrize(
    "map_over",
    [
        pytest.param({"velocity_ratio": None}, id="velocity_ratio_missing"),
        pytest.param(
            {"velocity_ratio": [0.4, 0.5], "efficiency": [0.58]},
            id="unequal_lengths",
        ),
        pytest.param(
            {"velocity_ratio": [0.40], "efficiency": [0.58]},
            id="single_point",
        ),
        pytest.param(
            {"velocity_ratio": [0.50, 0.40], "efficiency": [0.58, 0.65]},
            id="not_increasing",
        ),
    ],
)
def test_refuse_bad_map(thermo: Thermo, map_over: dict[str, Any]) -> None:
    """map.velocity_ratio / map.efficiency malformed in any way refuses."""
    map_params = {**MAP, **map_over}
    map_params = {k: v for k, v in map_params.items() if v is not None}
    with pytest.raises(ExpanderR1SpecError, match="map.velocity_ratio"):
        ExpanderR1().solve(example_inlets(thermo), base_params(map=map_params), thermo)


def test_refuse_efficiency_out_of_range(thermo: Thermo) -> None:
    """Map efficiency values outside (0, 1] refuse, naming the parameter."""
    bad = {**MAP, "efficiency": [0.58, 0.65, 1.20, 0.79, 0.86]}
    with pytest.raises(ExpanderR1SpecError, match="efficiency"):
        ExpanderR1().solve(example_inlets(thermo), base_params(map=bad), thermo)


def test_refuse_velocity_ratio_outside_map(thermo: Thermo) -> None:
    """speed_rpm = 10000 gives nu = 0.313 < 0.40, outside the map: typed refusal."""
    with pytest.raises(ExpanderMapRangeError, match="velocity ratio"):
        ExpanderR1().solve(example_inlets(thermo), base_params(speed_rpm=10000.0), thermo)


def test_refuse_flow_limits_inconsistent(thermo: Thermo) -> None:
    """Inconsistent flow limits refuse, naming flow_min_m3_s."""
    inlets = example_inlets(thermo)
    with pytest.raises(ExpanderR1SpecError, match="flow_min_m3_s"):
        ExpanderR1().solve(
            inlets,
            base_params(flow_min_m3_s=0.3, flow_max_m3_s=0.2),
            thermo,
        )
    with pytest.raises(ExpanderR1SpecError, match="flow_min_m3_s"):
        ExpanderR1().solve(inlets, base_params(flow_min_m3_s=-0.1, flow_max_m3_s=0.3), thermo)


def test_flow_capacity_range(thermo: Thermo) -> None:
    """Q = 0.222477211 m3/s: above flow_max = 0.1 refuses; [0.2, 0.3] passes."""
    inlets = example_inlets(thermo)
    with pytest.raises(ExpanderFlowRangeError, match="flow"):
        ExpanderR1().solve(inlets, base_params(flow_max_m3_s=0.1), thermo)
    passed = ExpanderR1().solve(inlets, base_params(flow_min_m3_s=0.2, flow_max_m3_s=0.3), thermo)
    assert passed.info["Q_actual_m3_s"] == pytest.approx(0.22247721127879216, rel=1e-9)
    # No limits given: Q is still reported, nothing is refused.
    unlimited = ExpanderR1().solve(inlets, base_params(), thermo)
    assert unlimited.info["Q_actual_m3_s"] == pytest.approx(0.22247721127879216, rel=1e-9)
