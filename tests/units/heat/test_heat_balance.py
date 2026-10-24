"""Hand-arithmetic and refusal tests for the shared heat-balance physics.

Pure-arithmetic problem-table tests are exact. Thermo-backed two-stream /
multi-stream tests use N2 stand-ins with span-sized flows (n set so
``n * (h(T_out) - h(T_in)) == CP * dT`` holds exactly at the span mean cp),
so the reported duties and end approaches are hand-checkable without
assuming a constant cp. The condensation test uses the IF97 steam package:
the PR package's pure-water PH flash fails inside the two-phase dome
(ZeroDivisionError) and flash_tvf does not honour a requested quality.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import (
    MultiStreamSide,
    ProblemStream,
    TemperatureCross,
    TwoStreamSpec,
    multi_stream,
    problem_table,
    two_stream,
)

P = 1.01325e5


def _thermo(package: str = "pr") -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", package)
    return impl


def _n2(thermo: Thermo, T: float, n: float, P_: float = P) -> StreamState:
    return thermo.flash_pt({"N2": 1.0}, T, P_, n)


def _cp_span_n2(thermo: Thermo, T_in: float, T_out: float, cp_W_per_K: float, P_: float = P) -> StreamState:
    """N2 feed sized so the span releases/absorbs exactly cp*dT."""
    z = {"N2": 1.0}
    dh = thermo.flash_pt(z, T_out, P_, 1.0).enthalpy - thermo.flash_pt(z, T_in, P_, 1.0).enthalpy
    n = cp_W_per_K * abs(T_out - T_in) / abs(dh)
    return thermo.flash_pt(z, T_in, P_, n)


# ---------------------------------------------------------------------------
# Problem table (pure arithmetic - exact hand values)
# ---------------------------------------------------------------------------


def test_problem_table_kemp_targets() -> None:
    """Kemp four-stream basis: QHmin 20 kW, QCmin 60 kW, pinch 90/80 C.

    Hand cascade on shifted temps (dTmin 10, half 5): shifted ends
    H1 165->55, H2 145->25, C1 25->140, C2 85->145; breakpoints
    165/145/140/85/55/25; cumulative 60, 62.5, -20, 55, 130 kW; the minimum
    -20 sits in zone [140, 85] whose BOTTOM breakpoint is the pinch.
    """
    result = problem_table(
        (
            ProblemStream(T_supply=443.15, T_target=333.15, cp_W_per_K=3000.0, is_hot=True),
            ProblemStream(T_supply=423.15, T_target=303.15, cp_W_per_K=1500.0, is_hot=True),
            ProblemStream(T_supply=293.15, T_target=408.15, cp_W_per_K=2000.0, is_hot=False),
            ProblemStream(T_supply=353.15, T_target=413.15, cp_W_per_K=4000.0, is_hot=False),
        ),
        10.0,
    )
    assert result.qh_min_W == pytest.approx(20000.0, rel=1e-9)
    assert result.qc_min_W == pytest.approx(60000.0, rel=1e-9)
    # The pinch is the BOTTOM breakpoint of the argmin zone (85 shifted ->
    # 90/80 C). The top breakpoint would report 145 shifted (145/135 C) - the
    # classic off-by-one this test locks out.
    assert result.pinch_T_hot_K == pytest.approx(363.15, abs=1e-9)
    assert result.pinch_T_cold_K == pytest.approx(353.15, abs=1e-9)


def test_problem_table_no_deficit_reports_hot_inlet_pinch() -> None:
    """Balanced counter-current pair: QHmin = QCmin = 0, pinch at the hot inlet."""
    result = problem_table(
        (
            ProblemStream(T_supply=400.0, T_target=300.0, cp_W_per_K=1000.0, is_hot=True),
            ProblemStream(T_supply=280.0, T_target=380.0, cp_W_per_K=1000.0, is_hot=False),
        ),
        10.0,
    )
    assert result.qh_min_W == 0.0
    assert result.qc_min_W == 0.0
    # Cascade never dips negative: pinch at the cascade start = the top
    # breakpoint (the hot supply, shifted +5 -> 395; real temps 400/390).
    assert result.pinch_T_hot_K == pytest.approx(400.0, abs=1e-9)
    assert result.pinch_T_cold_K == pytest.approx(390.0, abs=1e-9)


def test_problem_table_refuses_backward_hot() -> None:
    with pytest.raises(ValueError, match="heats up"):
        problem_table((ProblemStream(300.0, 400.0, 1000.0, is_hot=True),), 10.0)


def test_problem_table_refuses_backward_cold() -> None:
    with pytest.raises(ValueError, match="cools down"):
        problem_table((ProblemStream(400.0, 300.0, 1000.0, is_hot=False),), 10.0)


def test_problem_table_refuses_nonpositive_dtmin() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        problem_table((ProblemStream(400.0, 300.0, 1000.0, is_hot=True),), 0.0)


# ---------------------------------------------------------------------------
# Two-stream balance (N2 stand-ins, span-sized flows)
# ---------------------------------------------------------------------------


def test_two_stream_duty_spec_outlets_and_end_approaches() -> None:
    """Duty spec on equal span-sized CPs: 50 kW moves hot 400->350, cold 280->330.

    Both end approaches are exactly 70 K (span sizing makes n*cp_mean == CP);
    the minimum approach equals them to within the cp(T) variation.
    """
    thermo = _thermo()
    hot = _cp_span_n2(thermo, 400.0, 350.0, 1000.0)
    cold = _cp_span_n2(thermo, 280.0, 330.0, 1000.0)
    result = two_stream(hot, cold, TwoStreamSpec(duty_W=50_000.0), thermo)
    assert result.duty_W == pytest.approx(50_000.0, rel=1e-9)
    assert result.hot_out.T == pytest.approx(350.0, abs=0.05)
    assert result.cold_out.T == pytest.approx(330.0, abs=0.05)
    assert result.hot_out.T - cold.T == pytest.approx(70.0, abs=0.05)
    assert hot.T - result.cold_out.T == pytest.approx(70.0, abs=0.05)
    assert result.min_approach_K == pytest.approx(70.0, abs=2.0)
    assert result.min_approach_K <= min(70.0, 70.0) + 1e-6


def test_two_stream_hot_T_out_spec_solves_duty() -> None:
    thermo = _thermo()
    hot = _cp_span_n2(thermo, 400.0, 350.0, 1000.0)
    cold = _cp_span_n2(thermo, 280.0, 330.0, 1000.0)
    result = two_stream(hot, cold, TwoStreamSpec(hot_T_out=350.0), thermo)
    assert result.duty_W == pytest.approx(50_000.0, rel=1e-9)
    assert result.cold_out.T == pytest.approx(330.0, abs=0.05)


def test_two_stream_min_approach_bisection() -> None:
    """min_approach_K spec solves the duty by bisection: 70 K gap <-> 70 kW."""
    thermo = _thermo()
    hot = _cp_span_n2(thermo, 400.0, 350.0, 1000.0)
    cold = _cp_span_n2(thermo, 280.0, 330.0, 1000.0)
    result = two_stream(hot, cold, TwoStreamSpec(min_approach_K=50.0), thermo)
    # Equal span-sized CPs: the approach is uniform at 120 K - duty/1000, so
    # a 50 K minimum approach means a 70 kW duty.
    assert result.duty_W == pytest.approx(70_000.0, rel=1e-3)  # cp(T) variation shifts it ~0.04%
    assert result.min_approach_K == pytest.approx(50.0, abs=0.05)


def test_two_stream_temperature_cross_refusal_names_pinch() -> None:
    """A duty that drives the hot outlet below the cold inlet is refused.

    Hot CP 1000 (400->250 at 150 kW), cold CP 3000 (280->330): the hot outlet
    250 K sits 30 K below the cold inlet 280 K.
    """
    thermo = _thermo()
    hot = _cp_span_n2(thermo, 400.0, 350.0, 1000.0)
    cold = _cp_span_n2(thermo, 280.0, 370.0, 3000.0)
    with pytest.raises(TemperatureCross) as excinfo:
        two_stream(hot, cold, TwoStreamSpec(duty_W=150_000.0), thermo)
    message = str(excinfo.value)
    assert "temperature cross" in message
    assert "K at hot T =" in message  # names the pinch temperatures


def test_two_stream_spec_mutex() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        TwoStreamSpec(duty_W=1.0, hot_T_out=350.0)
    with pytest.raises(ValueError, match="got none"):
        TwoStreamSpec()


def test_two_stream_zero_flow_passthrough_and_refusal() -> None:
    thermo = _thermo()
    hot = _n2(thermo, 400.0, 0.0)
    cold = _n2(thermo, 280.0, 100.0)
    result = two_stream(hot, cold, TwoStreamSpec(duty_W=0.0), thermo, dP_cold=1.0e4)
    assert result.hot_out.T == pytest.approx(400.0, abs=1e-9)
    assert result.cold_out.T == pytest.approx(280.0, abs=1e-9)
    assert result.cold_out.P == pytest.approx(P - 1.0e4, rel=1e-9)
    assert result.duty_W == pytest.approx(0.0, abs=1e-6)
    with pytest.raises(ValueError, match="needs both streams flowing"):
        two_stream(hot, cold, TwoStreamSpec(duty_W=50_000.0), thermo)


def test_two_stream_refuses_bad_dP() -> None:
    thermo = _thermo()
    hot = _n2(thermo, 400.0, 100.0)
    cold = _n2(thermo, 280.0, 100.0)
    with pytest.raises(ValueError, match="must be >= 0"):
        two_stream(hot, cold, TwoStreamSpec(duty_W=0.0), thermo, dP_hot=-1.0)
    with pytest.raises(ValueError, match="non-positive"):
        two_stream(hot, cold, TwoStreamSpec(duty_W=0.0), thermo, dP_hot=2.0 * P)


def test_multi_stream_disjoint_hot_spans_plateau_at_real_knots() -> None:
    """Regression: composites plateau outside their own span (no phantom pinch).

    Two disjoint hot spans (500->450 and 350->300, CP 1000 each) with one
    balanced cold stream (CP 2000, 280->330): between the hot spans the hot
    composite is a plateau. Hand pinch: 20 K, at either real knot pair
    (350/330 or 300/280). The pre-fix grid paired plateau knots against the
    OTHER composite's temperatures and reported ~0 or a phantom cross.
    """
    thermo = _thermo()
    hots = (
        MultiStreamSide(_cp_span_n2(thermo, 500.0, 450.0, 1000.0), T_out=450.0),
        MultiStreamSide(_cp_span_n2(thermo, 350.0, 300.0, 1000.0), T_out=300.0),
    )
    colds = (MultiStreamSide(_cp_span_n2(thermo, 280.0, 330.0, 2000.0)),)
    result = multi_stream(hots, colds, thermo)
    assert result.min_approach_K == pytest.approx(20.0, abs=0.5)
    real_hot_knots = (350.0, 300.0)
    assert any(result.pinch_T_hot_K == pytest.approx(k, abs=0.5) for k in real_hot_knots)
    assert result.pinch_T_cold_K == pytest.approx(result.pinch_T_hot_K - 20.0, abs=1.0)


# ---------------------------------------------------------------------------
# Condensation (IF97 steam package: PR's PH flash fails in the two-phase dome)
# ---------------------------------------------------------------------------


def test_two_stream_condensing_hot_side_pinch() -> None:
    """Condensing steam (isothermal plateau) against sensible water.

    IF97 throughout: saturated steam at 1 atm condensing to saturated liquid
    releases n*dh_vap exactly; the cold side is sized to leave at 343.15 K,
    so the minimum approach is exactly 373.15 - 343.15 = 30 K at the cold
    outlet end.
    """
    thermo = _thermo("iapws_if97")
    z = {"H2O": 1.0}
    steam = thermo.flash_pt(z, 373.15, P, 100.0)
    assert steam.vapor_fraction == pytest.approx(1.0, abs=1e-6)
    dh_vap = steam.enthalpy - _sat_liq_h(thermo)
    cold_h_out = thermo.flash_pt(z, 343.15, P, 1.0).enthalpy
    cold_h_in = thermo.flash_pt(z, 293.15, P, 1.0).enthalpy
    duty_expected = 100.0 * dh_vap
    n_cold = duty_expected / (cold_h_out - cold_h_in)
    cold = thermo.flash_pt(z, 293.15, P, n_cold)
    # The duty spec is the only way to express an isothermal condensation span:
    # a hot_T_out spec on a 373.15 K saturated inlet solves to zero duty.
    result = two_stream(steam, cold, TwoStreamSpec(duty_W=duty_expected), thermo)
    assert result.duty_W == pytest.approx(duty_expected, rel=0.005)
    assert result.cold_out.T == pytest.approx(343.15, abs=0.5)
    assert result.min_approach_K == pytest.approx(30.0, abs=0.5)


def _sat_liq_h(thermo: Thermo) -> float:
    """Saturated-liquid enthalpy per mol at 1 atm (IF97 dome flash)."""
    return thermo.flash_tvf({"H2O": 1.0}, 373.15, 0.0, 1.0).enthalpy
