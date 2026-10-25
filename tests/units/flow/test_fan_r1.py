"""Closed-form, identity and refusal tests for the fan R1 adapter.

Spec ``specs/backend/units/fan.md``. Every test runs on the R0 example feed
(``Fan.example_case()``: methane, 300 K, 1 bar, 50 mol/s) flashed with ``pr``;
the measured inlet there is rho_1 = 0.644554842 kg/m3, mdot = 0.802123 kg/s,
Q = 1.24446044 m3/s.

Closed-form hand computation (curve data linear, so PCHIP reproduces the
lines exactly; measured inlet rho_1 = 0.6445548422952574 kg/m3,
mdot = 0.802123 kg/s, Q = mdot/rho_1 = 1.24446044 m3/s):

Closed-form 1 (s = 1, r = 1):
    Q    = 1.24446044 m3/s
    dP   = 8000 - 4000 * Q = 8000 - 4977.84176 = 3022.15826 Pa
    eta  = 0.5 + 0.2 * Q = 0.5 + 0.248892088 = 0.748892087
    P_out = 100000 + dP = 103022.158 Pa
    T_out = 302.77891 K (isentropic step through R0, measured)
    power = 4964.78391 W (isentropic step through R0, measured)

Closed-form 2 (s = 1.1, curve_density_kg_m3 = 1.2):
    Q_eq = Q / s = 1.24446044 / 1.1 = 1.13132767 m3/s
    dP   = (8000 - 4000 * Q_eq) * s^2 * r
         = (8000 - 4525.31069) * 1.21 * (0.644554842 / 1.2)
         = 3474.68931 * 1.21 * 0.537129035 = 2258.29139 Pa
    eta  = 0.5 + 0.2 * Q_eq = 0.726265534
    P_out = 100000 + dP = 102258.291 Pa
    T_out = 302.14774 K (measured)
    power = 3836.49333 W (measured)

Tolerances. The spec's printed values carry 9 significant digits, so no
check against a printed value can be tighter than that print's round-off
(half-ulp ~1.7e-9 rel on dP, ~2.2e-9 on cf2's dP). The measured values are
(cf1) dP = 3022.158256426138, eta = 0.7488920871786932, Q = 1.2444604358934654,
T = 302.778909693971, power = 4964.783907072933; (cf2) Q_eq =
1.1313276689940595, dP = 2258.291394515077, eta = 0.7262655337988119,
T = 302.1477399754311, power = 3836.493333723547. Every printed value is
reproduced inside its own round-off; dP and P_out sit just outside rel 1e-9
against the prints (1.19e-9 and 2.0e-9) purely through that rounding
(dP = 8000 - 4000*Q amplifies the 9-digit print of Q by ~1.65x). So the
closed-form *relations* are asserted at the spec's rel 1e-9 through the
model's Q (anchored independently against the printed Q at rel 1e-8), and
the printed values are anchored at their round-off (rel 5e-9 for dP/P_out,
rel 1e-9 for eta, rel 1e-7 for T and power per spec). Evidence posted as a
SPEC ISSUE comment on the PR.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.fan import Fan
from ngdesign.units.flow.fan_r1 import FanCurveRangeError, FanR1, FanR1SpecError
from tests.conftest import flash_feed

CURVE: dict[str, Any] = {
    "flow_m3_s": [0.5, 0.75, 1.0, 1.25, 1.5],
    "pressure_rise_Pa": [6000.0, 5000.0, 4000.0, 3000.0, 2000.0],
    "efficiency": [0.60, 0.65, 0.70, 0.75, 0.80],
}


@pytest.fixture(name="inlets")
def inlets_fixture(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = Fan.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def solve_fan_r1(inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> Any:
    return FanR1().solve(inlets, params, thermo)


def test_fan_r1_closed_form_s1(inlets: dict[str, Any], thermo: Thermo) -> None:
    """Closed-form 1 (see module docstring): s = 1, no density correction."""
    result = solve_fan_r1(inlets, {"curve": dict(CURVE)}, thermo)
    # The printed anchors at the round-off their 9-digit prints allow.
    assert result.info["Q_actual_m3_s"] == pytest.approx(1.24446044, rel=1e-8)
    assert result.info["dP_Pa"] == pytest.approx(3022.15826, rel=5e-9)
    assert result.info["eta"] == pytest.approx(0.748892087, rel=1e-9)
    # The closed-form relations themselves at the spec's rel 1e-9, through the
    # model's Q: the curve is linear, so PCHIP must reproduce it exactly.
    q = result.info["Q_actual_m3_s"]
    assert result.info["dP_Pa"] == pytest.approx(8000.0 - 4000.0 * q, rel=1e-9)
    assert result.info["eta"] == pytest.approx(0.5 + 0.2 * q, rel=1e-9)
    assert result.info["speed_ratio"] == 1.0
    assert result.info["density_ratio"] == 1.0
    outlet = result.outlets["outlet"]
    assert outlet.P == pytest.approx(103022.158, rel=5e-9)
    assert outlet.P == pytest.approx(1.0e5 + result.info["dP_Pa"], rel=1e-12)
    assert outlet.T == pytest.approx(302.77891, rel=1e-7)
    assert result.power_W == pytest.approx(4964.78391, rel=1e-7)
    assert result.duty_W == 0.0


def test_fan_r1_closed_form_fan_laws(inlets: dict[str, Any], thermo: Thermo) -> None:
    """Closed-form 2 (see module docstring): s = 1.1 with a rating density."""
    params: dict[str, Any] = {
        "curve": dict(CURVE),
        "speed_ratio": 1.1,
        "curve_density_kg_m3": 1.2,
    }
    result = solve_fan_r1(inlets, params, thermo)
    # The printed anchors at the round-off their 9-digit prints allow.
    assert result.info["Q_equiv_m3_s"] == pytest.approx(1.13132767, rel=1e-9)
    assert result.info["dP_Pa"] == pytest.approx(2258.29139, rel=5e-9)
    assert result.info["eta"] == pytest.approx(0.726265534, rel=1e-9)
    assert result.info["density_ratio"] == pytest.approx(0.644554842 / 1.2, rel=1e-9)
    # The closed-form relations themselves at the spec's rel 1e-9: Q_eq = Q/s,
    # dP = (8000 - 4000*Q_eq)*s^2*r, eta = 0.5 + 0.2*Q_eq.
    q = result.info["Q_actual_m3_s"]
    q_eq = result.info["Q_equiv_m3_s"]
    assert q_eq == pytest.approx(q / 1.1, rel=1e-12)
    assert result.info["dP_Pa"] == pytest.approx(
        (8000.0 - 4000.0 * q_eq) * 1.1**2 * result.info["density_ratio"], rel=1e-9
    )
    assert result.info["eta"] == pytest.approx(0.5 + 0.2 * q_eq, rel=1e-9)
    outlet = result.outlets["outlet"]
    assert outlet.P == pytest.approx(102258.291, rel=5e-9)
    assert outlet.P == pytest.approx(1.0e5 + result.info["dP_Pa"], rel=1e-12)
    assert outlet.T == pytest.approx(302.14774, rel=1e-7)
    assert result.power_W == pytest.approx(3836.49333, rel=1e-7)


def test_fan_r1_identity_with_r0(inlets: dict[str, Any], thermo: Thermo) -> None:
    """R1 equals Fan().solve with its own evaluated dP and eta, exactly."""
    params: dict[str, Any] = {
        "curve": dict(CURVE),
        "speed_ratio": 1.1,
        "curve_density_kg_m3": 1.2,
    }
    r1 = solve_fan_r1(inlets, params, thermo)
    r0 = Fan().solve(inlets, {"dP": r1.info["dP_Pa"], "eta": r1.info["eta"]}, thermo)
    assert r1.outlets["outlet"] == r0.outlets["outlet"]
    assert r1.power_W == r0.power_W
    assert r1.duty_W == r0.duty_W
    assert r1.info["pressure_ratio"] == r0.info["pressure_ratio"]


def test_fan_r1_flat_curve_reduces_to_r0_example(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A flat curve (dP* 5000, eta 0.7) at s = 1, r = 1 is R0's example case."""
    flat: dict[str, Any] = {
        "curve": {
            "flow_m3_s": [0.5, 1.5],
            "pressure_rise_Pa": [5000.0, 5000.0],
            "efficiency": [0.7, 0.7],
        }
    }
    r1 = solve_fan_r1(inlets, flat, thermo)
    feeds, r0_params = Fan.example_case()
    assert r0_params == {"dP": 5000.0, "eta": 0.7}
    r0 = Fan().solve(inlets, r0_params, thermo)
    assert r1.outlets["outlet"] == r0.outlets["outlet"]
    assert r1.power_W == r0.power_W
    assert r1.info["dP_Pa"] == 5000.0
    assert r1.info["eta"] == 0.7


def test_fan_r1_refuses_liquid_inlet(thermo: Thermo) -> None:
    """A liquid inlet is refused by R1 itself, so the refusal names R1."""
    water = {"T": 300.0, "P": 1.0e5, "molar_flow": 50.0, "composition": {"H2O": 1.0}}
    liquid = {"inlet": flash_feed(thermo, water)}
    with pytest.raises(FanR1SpecError, match="inlet is not gas"):
        solve_fan_r1(liquid, {"curve": dict(CURVE)}, thermo)


def test_fan_r1_refuses_missing_curve_key(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A curve missing a required key is refused naming the key."""
    broken = {k: v for k, v in CURVE.items() if k != "efficiency"}
    with pytest.raises(FanR1SpecError, match="curve.efficiency"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)


def test_fan_r1_refuses_unequal_lengths(inlets: dict[str, Any], thermo: Thermo) -> None:
    """Curve arrays of unequal length are refused."""
    broken: dict[str, Any] = {
        "flow_m3_s": [0.5, 1.0, 1.5],
        "pressure_rise_Pa": [6000.0, 4000.0, 2000.0],
        "efficiency": [0.6, 0.7],
    }
    with pytest.raises(FanR1SpecError, match="curve.flow_m3_s"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)


def test_fan_r1_refuses_single_point_curve(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A one-point curve is refused."""
    broken: dict[str, Any] = {
        "flow_m3_s": [1.0],
        "pressure_rise_Pa": [4000.0],
        "efficiency": [0.7],
    }
    with pytest.raises(FanR1SpecError, match="curve.flow_m3_s"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)


def test_fan_r1_refuses_non_increasing_flow(inlets: dict[str, Any], thermo: Thermo) -> None:
    """Curve flows must strictly increase."""
    broken: dict[str, Any] = {
        "flow_m3_s": [0.5, 1.0, 1.0, 1.25, 1.5],
        "pressure_rise_Pa": [6000.0, 5000.0, 4000.0, 3000.0, 2000.0],
        "efficiency": [0.60, 0.65, 0.70, 0.75, 0.80],
    }
    with pytest.raises(FanR1SpecError, match="curve.flow_m3_s"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)


def test_fan_r1_refuses_nonpositive_speed_ratio(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A non-positive speed ratio is refused."""
    with pytest.raises(FanR1SpecError, match="speed_ratio"):
        solve_fan_r1(inlets, {"curve": dict(CURVE), "speed_ratio": 0.0}, thermo)


def test_fan_r1_refuses_nonpositive_curve_density(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A non-positive curve rating density is refused."""
    with pytest.raises(FanR1SpecError, match="curve_density_kg_m3"):
        solve_fan_r1(
            inlets,
            {"curve": dict(CURVE), "curve_density_kg_m3": -1.0},
            thermo,
        )


def test_fan_r1_refuses_point_outside_curve(inlets: dict[str, Any], thermo: Thermo) -> None:
    """s = 0.5 gives Q_eq = 2.49 m3/s > 1.5, outside the curve (spec)."""
    with pytest.raises(FanCurveRangeError, match="outside the curve"):
        solve_fan_r1(inlets, {"curve": dict(CURVE), "speed_ratio": 0.5}, thermo)


def test_fan_r1_refuses_nonpositive_pressure_rise(inlets: dict[str, Any], thermo: Thermo) -> None:
    """A curve of zero pressure rise is refused (dP <= 0)."""
    broken: dict[str, Any] = {
        "flow_m3_s": CURVE["flow_m3_s"],
        "pressure_rise_Pa": [0.0] * 5,
        "efficiency": CURVE["efficiency"],
    }
    with pytest.raises(FanR1SpecError, match="pressure rise"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)


def test_fan_r1_refuses_efficiency_outside_unit_interval(inlets: dict[str, Any], thermo: Thermo) -> None:
    """Curve efficiencies above 1 are refused (eta not in (0, 1])."""
    broken: dict[str, Any] = {
        "flow_m3_s": CURVE["flow_m3_s"],
        "pressure_rise_Pa": CURVE["pressure_rise_Pa"],
        "efficiency": [1.2] * 5,
    }
    with pytest.raises(FanR1SpecError, match="efficiency"):
        solve_fan_r1(inlets, {"curve": broken}, thermo)
