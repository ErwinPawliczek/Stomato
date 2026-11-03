"""Pump R1 tests (``specs/backend/units/pump.md``); numbers from the spec's calc_pump.py."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.pump_r1 import PumpCavitationError, PumpCurveRangeError, PumpR1, PumpR1SpecError
from ngdesign.units.pump import Pump

CURVE: dict[str, Any] = {
    "flow_m3_s": [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4],
    "head_m": [80.0, 72.0, 64.0, 56.0, 48.0],
    "efficiency": [0.40, 0.50, 0.60, 0.70, 0.80],
}


def _inlet(thermo: Thermo) -> dict[str, Any]:
    f = Pump.example_case()[0]["inlet"]
    return {"inlet": thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])}


def test_closed_form_at_curve_speed(thermo: Thermo) -> None:
    """H = 80 - 40000*Q = 60.8156204 m; eta = 0.40 + 500*Q = 0.639804745."""
    res = PumpR1().solve(_inlet(thermo), {"curve": CURVE}, thermo)
    assert res.info["head_m"] == pytest.approx(60.8156204, rel=1e-8)
    assert res.info["eta"] == pytest.approx(0.639804745, rel=1e-8)
    assert res.info["P_out_Pa"] == pytest.approx(1357016.12, rel=1e-8)
    assert res.power_W == pytest.approx(267.6259, rel=1e-6)


def test_closed_form_with_affinity(thermo: Thermo) -> None:
    """s = 1.1: Q_eq = 4.36008627e-4; H = 1.21*(80 - 40000*Q_eq) = 75.6971825 m."""
    res = PumpR1().solve(_inlet(thermo), {"curve": CURVE, "speed_ratio": 1.1}, thermo)
    assert res.info["Q_equiv_m3_s"] == pytest.approx(4.36008627e-4, rel=1e-8)
    assert res.info["head_m"] == pytest.approx(75.6971825, rel=1e-8)
    assert res.info["eta"] == pytest.approx(0.618004313, rel=1e-8)
    assert res.info["P_out_Pa"] == pytest.approx(1444377.85, rel=1e-8)
    assert res.power_W == pytest.approx(344.864638, rel=1e-8)


def test_npsha(thermo: Thermo) -> None:
    """(P_in - P_v)/(rho*g) with P_v 391351.429 Pa; +3.0 - 0.5 for the suction terms."""
    params = {"curve": CURVE, "static_head_m": 3.0, "friction_head_m": 0.5}
    plain = PumpR1().solve(_inlet(thermo), {"curve": CURVE}, thermo)
    res = PumpR1().solve(_inlet(thermo), params, thermo)
    assert plain.info["NPSHa_m"] == pytest.approx(103.679744, rel=1e-8)
    assert plain.info["P_vapor_Pa"] == pytest.approx(391351.429, rel=1e-6)
    assert res.info["NPSHa_m"] == pytest.approx(106.179744, rel=1e-8)


def _with_npshr() -> dict[str, Any]:
    return {**CURVE, "npsh_required_m": [2.0, 2.5, 3.0, 3.5, 4.0]}


def test_npshr_margin(thermo: Thermo) -> None:
    res = PumpR1().solve(_inlet(thermo), {"curve": _with_npshr()}, thermo)
    assert res.info["NPSHr_m"] == pytest.approx(3.19902372, rel=1e-8)
    assert res.info["NPSH_margin_m"] == pytest.approx(100.48072, rel=1e-6)


def test_cavitation_refused_or_reported(thermo: Thermo) -> None:
    params = {"curve": _with_npshr(), "static_head_m": -110.0}
    with pytest.raises(PumpCavitationError, match="NPSHa"):
        PumpR1().solve(_inlet(thermo), params, thermo)
    res = PumpR1().solve(_inlet(thermo), {**params, "npsh_check": "report"}, thermo)
    assert res.info["NPSH_margin_m"] == pytest.approx(-9.519280, rel=1e-6)


def test_identity_with_r0(thermo: Thermo) -> None:
    """R1 delegates: the outlet and power equal R0 at R1's P_out and eta, exactly."""
    inlets = _inlet(thermo)
    r1 = PumpR1().solve(inlets, {"curve": CURVE}, thermo)
    r0 = Pump().solve(inlets, {"P_out": r1.info["P_out_Pa"], "eta": r1.info["eta"]}, thermo)
    a, b = r1.outlets["outlet"], r0.outlets["outlet"]
    assert (a.T, a.P, a.enthalpy) == (b.T, b.P, b.enthalpy)
    assert (r1.power_W, r1.duty_W) == (r0.power_W, r0.duty_W)


def test_flat_curve_reduces_to_r0(thermo: Thermo) -> None:
    flat = {"flow_m3_s": CURVE["flow_m3_s"], "head_m": [60.8156204] * 5, "efficiency": [0.639804745] * 5}
    res = PumpR1().solve(_inlet(thermo), {"curve": flat}, thermo)
    assert res.info["P_out_Pa"] == pytest.approx(1357016.12, rel=1e-8)


def test_constant_eta(thermo: Thermo) -> None:
    curve = {k: v for k, v in CURVE.items() if k != "efficiency"}
    res = PumpR1().solve(_inlet(thermo), {"curve": curve, "eta": 0.7}, thermo)
    assert res.info["eta"] == 0.7


def test_outside_the_curve(thermo: Thermo) -> None:
    with pytest.raises(PumpCurveRangeError, match="outside the curve"):
        PumpR1().solve(_inlet(thermo), {"curve": CURVE, "speed_ratio": 0.5}, thermo)


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({}, "curve.flow_m3_s"),
        ({"curve": {"flow_m3_s": [0.0, 1.0]}}, "curve.head_m"),
        ({"curve": {**CURVE, "head_m": [1.0]}}, "same length"),
        ({"curve": {**CURVE, "flow_m3_s": [0.0, 0.0, 1.0, 2.0, 3.0]}}, "strictly increasing"),
        ({"curve": {**CURVE, "npsh_required_m": [1.0]}}, "npsh_required_m"),
        ({"curve": CURVE, "eta": 0.7}, "exactly one of curve.efficiency or eta"),
        ({"curve": {k: v for k, v in CURVE.items() if k != "efficiency"}}, "exactly one of"),
        ({"curve": CURVE, "speed_ratio": 0.0}, "speed_ratio"),
        ({"curve": CURVE, "npsh_check": "warn"}, "npsh_check"),
        ({"curve": {**CURVE, "efficiency": [1.5] * 5}}, "efficiency"),
        ({"curve": {**CURVE, "head_m": [-1.0] * 5}}, "head"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    with pytest.raises(PumpR1SpecError, match=match):
        PumpR1().solve(_inlet(thermo), deepcopy(params), thermo)


def test_vapour_inlet_refused(thermo: Thermo) -> None:
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 1.0e6, 1.0)
    with pytest.raises(PumpR1SpecError, match="inlet has vapor"):
        PumpR1().solve({"inlet": inlet}, {"curve": CURVE}, thermo)
