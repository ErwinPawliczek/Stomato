"""Closed-form, identity and refusal tests for pump R1 (spec specs/backend/units/pump.md).

The closed-form chain is written out here from the spec's equations and
evaluated on the spec's measured inlet (pr flash of the R0 example feed,
density via the read-only R0 helper) at full precision. The spec's printed
values are then checked at print precision in ``test_spec_printed_values``:
the spec prints P_out as 1357016.12 Pa, a 2-decimal truncation of
1357016.123745623 (rel 2.8e-9), so the literal printed digits cannot carry
the spec's rel 1e-9 tolerance -- the full-precision chain below does
(independent script: scratchpad/unit-specs/calc_pump.py).

Constants transcribed from the spec Tests section: the curve points and the
printed closed-form values; each is checked against the spec text.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.pump_r1 import (
    PumpCavitationError,
    PumpCurveRangeError,
    PumpR1,
    PumpR1SpecError,
)
from ngdesign.units.pump import G_STD, Pump, _liquid_density
from tests.conftest import flash_feed

#: Spec curve: linear data, PCHIP reproduces it exactly.
CURVE: dict[str, Any] = {
    "flow_m3_s": [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4],
    "head_m": [80.0, 72.0, 64.0, 56.0, 48.0],
    "efficiency": [0.40, 0.50, 0.60, 0.70, 0.80],
}

#: Spec-printed closed-form values (truncated prints; see module docstring).
PRINTED = {
    "Q": 4.79609489e-4,
    "H1": 60.8156204,
    "eta1": 0.639804745,
    "P_out1": 1357016.12,
    "shaft1": 267.6259,
    "Q_eq2": 4.36008627e-4,
    "H2": 75.6971825,
    "eta2": 0.618004313,
    "P_out2": 1444377.85,
    "shaft2": 344.864638,
}


def _measured(thermo: Thermo) -> tuple[float, float, Any]:
    """(rho_L, Q, inlet state) for the R0 example feed, per the spec's measurement."""
    feeds, _ = Pump.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    rho = _liquid_density(inlet)
    return rho, inlet.mass_flow / rho, inlet


def _closed_form(Q: float, rho: float, p_in: float, speed: float = 1.0) -> dict[str, float]:
    """The spec's equations, written out: affinity laws on the linear curve."""
    q_eq = Q / speed
    head = speed**2 * (80.0 - 40000.0 * q_eq)
    eta = 0.40 + 500.0 * q_eq
    dp = rho * G_STD * head
    return {
        "Q_eq": q_eq,
        "H": head,
        "eta": eta,
        "P_out": p_in + dp,
        "shaft": Q * dp / eta,
    }


def _solve(thermo: Thermo, params: dict[str, Any]) -> Any:
    feeds, _ = Pump.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    return PumpR1().solve(inlets, params, thermo)


def test_measured_inlet_flow(thermo: Thermo) -> None:
    """Q from the R0 example feed matches the spec's printed 4.79609489e-4 m3/s."""
    _, Q, _ = _measured(thermo)
    assert Q == pytest.approx(PRINTED["Q"], rel=1e-9)


def test_closed_form_1_speed_1(thermo: Thermo) -> None:
    """Speed 1: the full-precision closed-form chain, at the spec's rel 1e-9."""
    rho, Q, inlet = _measured(thermo)
    exp = _closed_form(Q, rho, inlet.P)
    result = _solve(thermo, {"curve": CURVE})
    assert result.info["Q_m3_s"] == pytest.approx(Q, rel=1e-12)
    assert result.info["Q_equiv_m3_s"] == pytest.approx(exp["Q_eq"], rel=1e-9)
    assert result.info["head_m"] == pytest.approx(exp["H"], rel=1e-9)
    assert result.info["eta"] == pytest.approx(exp["eta"], rel=1e-9)
    assert result.info["P_out_Pa"] == pytest.approx(exp["P_out"], rel=1e-9)
    assert result.power_W == pytest.approx(exp["shaft"], rel=1e-9)
    assert result.info["speed_ratio"] == 1.0
    assert result.duty_W == 0.0


def test_closed_form_2_speed_1_1(thermo: Thermo) -> None:
    """Speed ratio 1.1: affinity laws move the operating point along the curve."""
    rho, Q, inlet = _measured(thermo)
    exp = _closed_form(Q, rho, inlet.P, speed=1.1)
    result = _solve(thermo, {"curve": CURVE, "speed_ratio": 1.1})
    assert result.info["Q_equiv_m3_s"] == pytest.approx(exp["Q_eq"], rel=1e-9)
    assert result.info["head_m"] == pytest.approx(exp["H"], rel=1e-9)
    assert result.info["eta"] == pytest.approx(exp["eta"], rel=1e-9)
    assert result.info["P_out_Pa"] == pytest.approx(exp["P_out"], rel=1e-9)
    assert result.power_W == pytest.approx(exp["shaft"], rel=1e-9)


def test_spec_printed_values(thermo: Thermo) -> None:
    """The spec's printed digits, at print precision (P_out is 2-decimal truncated)."""
    result = _solve(thermo, {"curve": CURVE})
    assert result.info["head_m"] == pytest.approx(PRINTED["H1"], rel=1e-8)
    assert result.info["eta"] == pytest.approx(PRINTED["eta1"], rel=1e-8)
    assert result.info["P_out_Pa"] == pytest.approx(PRINTED["P_out1"], rel=1e-8)
    assert result.power_W == pytest.approx(PRINTED["shaft1"], rel=1e-8)
    result2 = _solve(thermo, {"curve": CURVE, "speed_ratio": 1.1})
    assert result2.info["Q_equiv_m3_s"] == pytest.approx(PRINTED["Q_eq2"], rel=1e-8)
    assert result2.info["head_m"] == pytest.approx(PRINTED["H2"], rel=1e-8)
    assert result2.info["eta"] == pytest.approx(PRINTED["eta2"], rel=1e-8)
    assert result2.info["P_out_Pa"] == pytest.approx(PRINTED["P_out2"], rel=1e-8)
    assert result2.power_W == pytest.approx(PRINTED["shaft2"], rel=1e-8)


def test_identity_reduces_to_r0(thermo: Thermo) -> None:
    """For ANY curve, R1 == R0 at (P_out_Pa, eta): 0.0 difference, not a tolerance."""
    result = _solve(thermo, {"curve": CURVE})
    feeds, _ = Pump.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    r0 = Pump().solve(
        inlets,
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
    rho, Q, inlet = _measured(thermo)
    exp = _closed_form(Q, rho, inlet.P)
    flat = {
        "flow_m3_s": [0.0, 4.0e-4, 8.0e-4],
        "head_m": [exp["H"]] * 3,
        "efficiency": [exp["eta"]] * 3,
    }
    result = _solve(thermo, {"curve": flat})
    assert result.info["P_out_Pa"] == pytest.approx(exp["P_out"], rel=1e-9)


def test_constant_eta_param(thermo: Thermo) -> None:
    """eta as a scalar param instead of curve.efficiency: same P_out, scalar eta used."""
    rho, Q, inlet = _measured(thermo)
    exp = _closed_form(Q, rho, inlet.P)
    head_only = {k: v for k, v in CURVE.items() if k != "efficiency"}
    result = _solve(thermo, {"curve": head_only, "eta": 0.65})
    assert result.info["eta"] == 0.65
    assert result.info["P_out_Pa"] == pytest.approx(exp["P_out"], rel=1e-9)


# --- refusals: one test per row of the spec's refusal table (step-1 rows).
# The curve checks run after the inlet check, so each test uses the real
# liquid example inlet and a deliberately bad curve/param side. ---


def test_refuse_vapor_inlet(thermo: Thermo) -> None:
    """vf > 0.001 (the R0 threshold) is refused, naming the inlet."""
    feeds, _ = Pump.example_case()
    feed = feeds["inlet"]
    two_phase = thermo.flash_tvf(feed["composition"], feed["T"], 0.5, feed["molar_flow"])
    with pytest.raises(PumpR1SpecError, match="inlet has vapor"):
        PumpR1().solve({"inlet": two_phase}, {"curve": CURVE}, thermo)


def test_refuse_curve_missing(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="curve.flow_m3_s"):
        _solve(thermo, {"eta": 0.6})


def test_refuse_flow_missing(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="curve.flow_m3_s"):
        _solve(thermo, {"curve": {"head_m": [60.0, 50.0]}})


def test_refuse_head_missing(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="curve.head_m"):
        _solve(thermo, {"curve": {"flow_m3_s": [0.0, 4.0e-4]}})


def test_refuse_unequal_length(thermo: Thermo) -> None:
    bad = {**CURVE, "head_m": [80.0, 72.0]}
    with pytest.raises(PumpR1SpecError, match="same length"):
        _solve(thermo, {"curve": bad})


def test_refuse_single_point(thermo: Thermo) -> None:
    bad = {**CURVE, "flow_m3_s": [4.0e-4], "head_m": [64.0], "efficiency": [0.6]}
    with pytest.raises(PumpR1SpecError, match="strictly increasing"):
        _solve(thermo, {"curve": bad})


def test_refuse_flow_not_increasing(thermo: Thermo) -> None:
    bad = {**CURVE, "flow_m3_s": [0.0, 4.0e-4, 2.0e-4, 6.0e-4, 8.0e-4]}
    with pytest.raises(PumpR1SpecError, match="strictly increasing"):
        _solve(thermo, {"curve": bad})


def test_refuse_both_efficiency_and_eta(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="exactly one of curve.efficiency or eta"):
        _solve(thermo, {"curve": CURVE, "eta": 0.65})


def test_refuse_neither_efficiency_nor_eta(thermo: Thermo) -> None:
    head_only = {k: v for k, v in CURVE.items() if k != "efficiency"}
    with pytest.raises(PumpR1SpecError, match="exactly one of curve.efficiency or eta"):
        _solve(thermo, {"curve": head_only})


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


def test_refuse_head_not_positive(thermo: Thermo) -> None:
    bad = {**CURVE, "head_m": [80.0, 72.0, 64.0, 56.0, 0.0]}
    with pytest.raises(PumpR1SpecError, match="head"):
        _solve(thermo, {"curve": bad})


def test_refuse_efficiency_out_of_range(thermo: Thermo) -> None:
    bad = {**CURVE, "efficiency": [0.40, 0.50, 0.60, 0.70, 1.5]}
    with pytest.raises(PumpR1SpecError, match="efficiency"):
        _solve(thermo, {"curve": bad})


def test_curve_fraction(thermo: Thermo) -> None:
    """curve_fraction is (Q_eq - Q_min)/(Q_max - Q_min), dimensionless."""
    result = _solve(thermo, {"curve": CURVE})
    _, Q, _ = _measured(thermo)
    assert result.info["curve_fraction"] == pytest.approx(Q / 8.0e-4, rel=1e-9)


# --- NPSH (spec eqs. 6-8): the spec's measured P_v and NPSHa/NPSHr values. ---

NPSHR_CURVE = {**CURVE, "npsh_required_m": [2.0, 2.5, 3.0, 3.5, 4.0]}


def test_npsha_static_zero(thermo: Thermo) -> None:
    """Static 0, friction 0: P_v 391351.429 Pa, NPSHa 103.679744 m (spec print).

    Full-precision chain check at rel 1e-9 (like the closed-form tests); the
    spec prints NPSHa to 8 significant digits, so the printed value is checked
    at print precision.
    """
    result = _solve(thermo, {"curve": CURVE})
    rho, _, inlet = _measured(thermo)
    assert result.info["P_vapor_Pa"] == pytest.approx(391351.429, rel=1e-8)
    npsha_chain = (inlet.P - result.info["P_vapor_Pa"]) / (rho * G_STD)
    assert result.info["NPSHa_m"] == pytest.approx(npsha_chain, rel=1e-9)
    assert result.info["NPSHa_m"] == pytest.approx(103.679744, rel=1e-8)


def test_npsha_static_friction(thermo: Thermo) -> None:
    """Static 3.0, friction 0.5: NPSHa 106.179744 m (spec print precision)."""
    result = _solve(thermo, {"curve": CURVE, "static_head_m": 3.0, "friction_head_m": 0.5})
    assert result.info["NPSHa_m"] == pytest.approx(106.179744, rel=1e-8)


def test_npshr_and_margin(thermo: Thermo) -> None:
    """NPSHr 2 + 2500*Q_eq at speed 1: 3.19902372 m; margin 100.48072 m (rel 1e-9)."""
    result = _solve(thermo, {"curve": NPSHR_CURVE})
    _, Q, _ = _measured(thermo)
    npshr_exp = 2.0 + 2500.0 * Q
    assert result.info["NPSHr_m"] == pytest.approx(npshr_exp, rel=1e-9)
    assert result.info["NPSHr_m"] == pytest.approx(3.19902372, rel=1e-8)
    assert result.info["NPSH_margin_m"] == pytest.approx(100.48072, rel=1e-8)


def test_npshr_affinity_speed(thermo: Thermo) -> None:
    """NPSHr(Q) = s^2 * NPSHr_c(Q_eq) — s^2 on the interpolant at the equivalent point."""
    result = _solve(thermo, {"curve": NPSHR_CURVE, "speed_ratio": 1.1})
    _, Q, _ = _measured(thermo)
    s = 1.1
    npshr_exp = s**2 * (2.0 + 2500.0 * Q / s)
    assert result.info["NPSHr_m"] == pytest.approx(npshr_exp, rel=1e-9)


def test_refuse_cavitation(thermo: Thermo) -> None:
    """static_head_m -110: NPSHa -6.320256 m < NPSHr, refused with npsh_check refuse."""
    with pytest.raises(PumpCavitationError, match="NPSHa"):
        _solve(thermo, {"curve": NPSHR_CURVE, "static_head_m": -110.0})


def test_report_cavitation(thermo: Thermo) -> None:
    """npsh_check report: the negative margin is returned in info (-9.519280, rel 1e-6)."""
    result = _solve(
        thermo,
        {"curve": NPSHR_CURVE, "static_head_m": -110.0, "npsh_check": "report"},
    )
    assert result.info["NPSH_margin_m"] == pytest.approx(-9.519280, rel=1e-6)


def test_refuse_npsh_length(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="npsh_required_m"):
        _solve(thermo, {"curve": {**CURVE, "npsh_required_m": [2.0, 2.5]}})


def test_refuse_npsh_check_value(thermo: Thermo) -> None:
    with pytest.raises(PumpR1SpecError, match="npsh_check"):
        _solve(thermo, {"curve": CURVE, "npsh_check": "ignore"})


def test_refuse_negative_friction_head(thermo: Thermo) -> None:
    """friction_head_m < 0 is refused (documented extra guard, outside the plan table)."""
    with pytest.raises(PumpR1SpecError, match="friction_head_m"):
        _solve(thermo, {"curve": CURVE, "friction_head_m": -0.5})
