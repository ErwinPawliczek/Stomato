"""Closed-form, identity and refusal tests for pump R1 (spec specs/backend/units/pump.md).

Closed-form 1 (speed_ratio 1), hand-computed from the spec's equations on the
R0 example feed flashed with `pr` (independent script:
scratchpad/unit-specs/calc_pump.py). Measured inlet: rho_L = 598.62109 kg/m3,
mdot = 0.287104355 kg/s, Q = 4.79609489e-4 m3/s. The curve is linear, which
PCHIP reproduces exactly:
  H = 80 - 40000*Q = 60.8156204 m
  eta = 0.40 + 500*Q = 0.639804745
  dP = rho*g*H = 357016.124 Pa  ->  P_out = 1357016.12 Pa
  shaft = Q*dP/eta = 267.6259 W
Closed-form 2 (speed_ratio 1.1):
  Q_eq = 4.36008627e-4 m3/s; H = 1.21*(80 - 40000*Q_eq) = 75.6971825 m;
  eta = 0.618004313; dP = 444377.85 Pa -> P_out = 1444377.85 Pa;
  shaft = 344.864638 W.
Constants transcribed here: the curve points (spec Tests section) and the
closed-form expectations above; each is checked against the spec text.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.pump_r1 import (
    PumpCurveRangeError,
    PumpR1,
    PumpR1SpecError,
)
from ngdesign.units.pump import Pump
from tests.conftest import flash_feed

#: Spec curve: linear data, PCHIP reproduces it exactly.
CURVE: dict[str, Any] = {
    "flow_m3_s": [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4],
    "head_m": [80.0, 72.0, 64.0, 56.0, 48.0],
    "efficiency": [0.40, 0.50, 0.60, 0.70, 0.80],
}


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = Pump.example_case()
    return {"inlet": flash_feed(thermo, feeds["inlet"])}


def _solve(thermo: Thermo, params: dict[str, Any]) -> Any:
    return PumpR1().solve(_inlets(thermo), params, thermo)


def test_measured_inlet_flow(thermo: Thermo) -> None:
    """Q from the R0 example feed matches the spec's measured 4.79609489e-4 m3/s."""
    result = _solve(thermo, {"curve": CURVE})
    assert result.info["Q_m3_s"] == pytest.approx(4.79609489e-4, rel=1e-9)


def test_closed_form_1_speed_1(thermo: Thermo) -> None:
    """Speed 1 on the linear curve: H 60.8156204 m, P_out 1357016.12 Pa, 267.6259 W."""
    result = _solve(thermo, {"curve": CURVE})
    assert result.info["P_out_Pa"] == pytest.approx(1357016.12, rel=1e-9)
    assert result.info["eta"] == pytest.approx(0.639804745, rel=1e-9)
    assert result.info["head_m"] == pytest.approx(60.8156204, rel=1e-9)
    assert result.power_W == pytest.approx(267.6259, rel=1e-9)
    assert result.info["speed_ratio"] == 1.0
    assert result.info["Q_equiv_m3_s"] == pytest.approx(result.info["Q_m3_s"], rel=1e-12)
    assert result.duty_W == 0.0


def test_closed_form_2_speed_1_1(thermo: Thermo) -> None:
    """Speed ratio 1.1: affinity laws move the operating point along the curve."""
    result = _solve(thermo, {"curve": CURVE, "speed_ratio": 1.1})
    assert result.info["Q_equiv_m3_s"] == pytest.approx(4.36008627e-4, rel=1e-9)
    assert result.info["head_m"] == pytest.approx(75.6971825, rel=1e-9)
    assert result.info["eta"] == pytest.approx(0.618004313, rel=1e-9)
    assert result.info["P_out_Pa"] == pytest.approx(1444377.85, rel=1e-9)
    assert result.power_W == pytest.approx(344.864638, rel=1e-9)


def test_identity_reduces_to_r0(thermo: Thermo) -> None:
    """For ANY curve, R1 == R0 at (P_out_Pa, eta): 0.0 difference, not a tolerance."""
    result = _solve(thermo, {"curve": CURVE})
    r0 = Pump().solve(
        _inlets(thermo),
        {"P_out": result.info["P_out_Pa"], "eta": result.info["eta"]},
        thermo,
    )
    assert result.outlets["outlet"].T == r0.outlets["outlet"].T
    assert result.outlets["outlet"].P == r0.outlets["outlet"].P
    assert result.outlets["outlet"].enthalpy == r0.outlets["outlet"].enthalpy
    assert result.power_W == r0.power_W
    assert result.duty_W == r0.duty_W


def test_flat_curve_is_r0(thermo: Thermo) -> None:
    """A flat curve with constant eta is R0 solved at P_in + rho*g*H*."""
    flat = {
        "flow_m3_s": [0.0, 4.0e-4, 8.0e-4],
        "head_m": [60.8156204, 60.8156204, 60.8156204],
        "efficiency": [0.639804745, 0.639804745, 0.639804745],
    }
    result = _solve(thermo, {"curve": flat})
    assert result.info["P_out_Pa"] == pytest.approx(1357016.12, rel=1e-9)


def test_constant_eta_param(thermo: Thermo) -> None:
    """eta as a scalar param instead of curve.efficiency: same P_out, scalar eta used."""
    head_only = {k: v for k, v in CURVE.items() if k != "efficiency"}
    result = _solve(thermo, {"curve": head_only, "eta": 0.65})
    assert result.info["eta"] == 0.65
    assert result.info["P_out_Pa"] == pytest.approx(1357016.12, rel=1e-9)


# --- refusals: one test per row of the spec's refusal table (step-1 rows) ---


def test_refuse_vapor_inlet(thermo: Thermo) -> None:
    """vf > 0.001 (the R0 threshold) is refused, naming the inlet."""
    feeds, _ = Pump.example_case()
    feed = feeds["inlet"]
    two_phase = thermo.flash_tvf(feed["composition"], feed["T"], 0.5, feed["molar_flow"])
    with pytest.raises(PumpR1SpecError, match="inlet has vapor"):
        PumpR1().solve({"inlet": two_phase}, {"curve": CURVE}, thermo)


def test_refuse_curve_missing() -> None:
    with pytest.raises(PumpR1SpecError, match="curve.flow_m3_s"):
        PumpR1().solve({}, {"eta": 0.6}, thermo=None)  # type: ignore[arg-type]


def test_refuse_flow_missing() -> None:
    with pytest.raises(PumpR1SpecError, match="curve.flow_m3_s"):
        PumpR1().solve({}, {"curve": {"head_m": [60.0, 50.0]}}, thermo=None)  # type: ignore[arg-type]


def test_refuse_head_missing() -> None:
    with pytest.raises(PumpR1SpecError, match="curve.head_m"):
        PumpR1().solve({}, {"curve": {"flow_m3_s": [0.0, 4.0e-4]}}, thermo=None)  # type: ignore[arg-type]


def test_refuse_unequal_length() -> None:
    bad = {**CURVE, "head_m": [80.0, 72.0]}
    with pytest.raises(PumpR1SpecError, match="same length"):
        PumpR1().solve({}, {"curve": bad}, thermo=None)  # type: ignore[arg-type]


def test_refuse_single_point() -> None:
    bad = {**CURVE, "flow_m3_s": [4.0e-4], "head_m": [64.0], "efficiency": [0.6]}
    with pytest.raises(PumpR1SpecError, match="strictly increasing"):
        PumpR1().solve({}, {"curve": bad}, thermo=None)  # type: ignore[arg-type]


def test_refuse_flow_not_increasing() -> None:
    bad = {**CURVE, "flow_m3_s": [0.0, 4.0e-4, 2.0e-4, 6.0e-4, 8.0e-4]}
    with pytest.raises(PumpR1SpecError, match="strictly increasing"):
        PumpR1().solve({}, {"curve": bad}, thermo=None)  # type: ignore[arg-type]


def test_refuse_both_efficiency_and_eta(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="exactly one of curve.efficiency or eta"):
        _solve(thermo, {"curve": CURVE, "eta": 0.65})


def test_refuse_neither_efficiency_nor_eta() -> None:
    head_only = {k: v for k, v in CURVE.items() if k != "efficiency"}
    with pytest.raises(PumpR1SpecError, match="exactly one of curve.efficiency or eta"):
        PumpR1().solve({}, {"curve": head_only}, thermo=None)  # type: ignore[arg-type]


def test_refuse_speed_ratio_zero(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="speed_ratio"):
        _solve(thermo, {"curve": CURVE, "speed_ratio": 0.0})


def test_refuse_speed_ratio_negative(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="speed_ratio"):
        _solve(thermo, {"curve": CURVE, "speed_ratio": -0.5})


def test_refuse_outside_curve(thermo: Thermo) -> None:
    """speed_ratio 0.5 gives Q_eq = 9.59e-4 m3/s > 8.0e-4: outside the curve."""
    with pytest.raises(PumpCurveRangeError, match="outside the curve"):
        _solve(thermo, {"curve": CURVE, "speed_ratio": 0.5})


def test_refuse_head_not_positive() -> None:
    bad = {**CURVE, "head_m": [80.0, 72.0, 64.0, 56.0, 0.0]}
    with pytest.raises(PumpR1SpecError, match="head"):
        PumpR1().solve({}, {"curve": bad}, thermo=None)  # type: ignore[arg-type]


def test_refuse_efficiency_out_of_range() -> None:
    bad = {**CURVE, "efficiency": [0.40, 0.50, 0.60, 0.70, 1.5]}
    with pytest.raises(PumpR1SpecError, match="efficiency"):
        PumpR1().solve({}, {"curve": bad}, thermo=None)  # type: ignore[arg-type]


def test_curve_fraction(thermo: Thermo) -> None:
    """curve_fraction is (Q_eq - Q_min)/(Q_max - Q_min), dimensionless."""
    result = _solve(thermo, {"curve": CURVE})
    assert result.info["curve_fraction"] == pytest.approx(4.79609489e-4 / 8.0e-4, rel=1e-9)
