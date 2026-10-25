"""Closed-form, identity and refusal tests: multi-stream R1 (spec Tests).

Closed-form reference numbers from an independent RK4 + shooting calculation
(``calc_multi_stream.py``, not the module's own output). With constant heat
capacity rates the common-wall model is exactly counter-current epsilon-NTU
with 1/UA = 1/(hA)_h + 1/(hA)_c; the test tables are the constant-C enthalpy
tables T = H/C + T_ref of the spec.

MS1: one hot (C = 1500 W/K, hA = 4000 W/K, 400 K) against one cold
(C = 2500 W/K, hA = 4000 W/K, 300 K). UA = 1/(1/4000 + 1/4000) = 2000 W/K,
NTU = UA/C_min = 4/3, Cr = 0.6:

    epsilon = (1 - exp(-NTU (1 - Cr))) / (1 - Cr exp(-NTU (1 - Cr)))
    Q = epsilon * C_min * (400 - 300) = 95681.934 W

    T_hot,out = 400 - Q/1500 = 336.212044 K
    T_cold,out = 300 + Q/2500 = 338.272774 K

MS2: hot1 (C = 1000, hA = 3000, 400 K), hot2 (C = 800, hA = 2000, 380 K),
cold (C = 2500, hA = 5000, 300 K). The printed reference: hot1 out
332.809133 K, hot2 out 334.749305 K, cold out 341.356569 K; duties
Qh1 = 67190.8674 W, Qh2 = 36200.5559 W, Qc = 103391.423 W
(Qh1 + Qh2 = Qc exactly, an independent consistency check).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from scipy.interpolate import PchipInterpolator

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.multi_stream_r1 import (
    CommonWallResult,
    MultiStreamR1,
    MultiStreamRatingError,
    RatingConvergenceError,
    StreamLayer,
    check_wall_order,
    min_approach_K,
    solve_common_wall,
    wall_mediated_UA_W_K,
)


def _constant_c_table(C: float, T_ref: float = 0.0) -> PchipInterpolator:
    """T = H/C + T_ref over a wide span (PCHIP through two points is linear)."""
    return PchipInterpolator([-1.0e9, 1.0e9], [-1.0e9 / C + T_ref, 1.0e9 / C + T_ref])


def _layer(C: float, hA: float, T_in: float, T_far: float, is_hot: bool) -> StreamLayer:
    return StreamLayer(
        hA_W_K=hA,
        H_in_W=C * (T_in - 0.0),
        H_far_W=C * (T_far - 0.0),
        T_of_H=_constant_c_table(C),
        is_hot=is_hot,
    )


def test_ms1_reduces_to_counter_current_eps_ntu() -> None:
    """MS1: Q equals the epsilon-NTU value at UA = 2000 (rel 1e-7)."""
    layers = (
        _layer(1500.0, 4000.0, 400.0, 300.0, is_hot=True),
        _layer(2500.0, 4000.0, 300.0, 400.0, is_hot=False),
    )
    result = solve_common_wall(layers)

    H_hot_out, H_cold_out = result.outlet_enthalpy_flows()
    q_hot = 600000.0 - H_hot_out
    q_cold = H_cold_out - 750000.0
    assert q_hot == pytest.approx(q_cold, rel=1e-9)
    assert q_hot == pytest.approx(95681.934, rel=1e-7)

    ntu = 2000.0 / 1500.0
    cr = 1500.0 / 2500.0
    effectiveness = (1.0 - math.exp(-ntu * (1.0 - cr))) / (1.0 - cr * math.exp(-ntu * (1.0 - cr)))
    assert q_hot == pytest.approx(effectiveness * 1500.0 * 100.0, rel=1e-7)

    assert result.T[0][-1] == pytest.approx(336.212044, abs=1e-5)
    assert result.T[1][0] == pytest.approx(338.272774, abs=1e-5)
    check_wall_order(result)


def test_ms2_three_streams_closed_form() -> None:
    """MS2: two hots against one cold, printed reference numbers (abs 1e-5 K)."""
    layers = (
        _layer(1000.0, 3000.0, 400.0, 300.0, is_hot=True),
        _layer(800.0, 2000.0, 380.0, 300.0, is_hot=True),
        _layer(2500.0, 5000.0, 300.0, 400.0, is_hot=False),
    )
    result = solve_common_wall(layers)

    H_out = result.outlet_enthalpy_flows()
    assert H_out[0] == pytest.approx(1000.0 * 332.809133, abs=1e-2)
    assert result.T[0][-1] == pytest.approx(332.809133, abs=1e-5)
    assert result.T[1][-1] == pytest.approx(334.749305, abs=1e-5)
    assert result.T[2][0] == pytest.approx(341.356569, abs=1e-5)

    qh1 = 1000.0 * (400.0 - result.T[0][-1])
    qh2 = 800.0 * (380.0 - result.T[1][-1])
    qc = 2500.0 * (result.T[2][0] - 300.0)
    assert qh1 == pytest.approx(67190.8674, abs=1e-2)
    assert qh2 == pytest.approx(36200.5559, abs=1e-2)
    assert qc == pytest.approx(103391.423, abs=1e-2)
    assert qh1 + qh2 == pytest.approx(qc, rel=1e-9)
    check_wall_order(result)


def test_ms1_wall_sits_between_and_ua_is_series() -> None:
    """T_w lies between T_hot and T_cold; UA_total is the series combination."""
    layers = (
        _layer(1500.0, 4000.0, 400.0, 300.0, is_hot=True),
        _layer(2500.0, 4000.0, 300.0, 400.0, is_hot=False),
    )
    result = solve_common_wall(layers)

    assert (result.T[0] >= result.T_wall - 1e-9).all()
    assert (result.T[1] <= result.T_wall + 1e-9).all()
    assert min_approach_K(result) > 0.0
    assert wall_mediated_UA_W_K(result) == pytest.approx(2000.0, rel=1e-12)


def test_wall_order_violation_raises() -> None:
    """A hand-built result with a stream through the wall raises TemperatureCross."""
    bad = CommonWallResult(
        x=np.linspace(0.0, 1.0, 3),
        H=np.array([[100.0, 50.0, 0.0], [200.0, 250.0, 300.0]]),
        T=np.array([[400.0, 395.0, 389.0], [380.0, 385.0, 390.5]]),
        T_wall=np.array([390.0, 390.0, 390.0]),
        hA_W_K=(4000.0, 4000.0),
        is_hot=(True, False),
    )
    with pytest.raises(TemperatureCross, match="ordering violated"):
        check_wall_order(bad)


# --- adapter (R1 level): flash tables, pass-through, dP, info, refusals -------


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _feeds() -> dict[str, dict[str, Any]]:
    """The R0 example feeds (Smith Table 16.2 streams 1 and 3, second pair idle)."""
    feeds, _ = MultiStreamExchanger.example_case()
    return feeds


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> dict[str, StreamState]:
    return {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for port, f in feeds.items()
    }


def test_adapter_example_case_duty_closes_and_passes_through() -> None:
    """Net duty is round-off; per-port duties mirror (hot releases, cold
    absorbs); zero-flow ports pass through untouched."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    result = MultiStreamR1().solve(inlets, MultiStreamR1.example_case()[1], thermo)

    assert result.duty_W == pytest.approx(0.0, abs=1e-6)
    assert result.power_W == 0.0
    q_hot = result.info["duty_hot_in_1_W"]
    q_cold = result.info["duty_cold_in_1_W"]
    assert q_hot == pytest.approx(q_cold, rel=1e-9)
    assert q_hot > 0.0
    assert result.outlets["hot_out_2"] is inlets["hot_in_2"]
    assert result.outlets["cold_out_2"] is inlets["cold_in_2"]
    assert result.outlets["hot_out_1"].P == inlets["hot_in_1"].P  # dP defaults to 0
    assert result.info["UA_total_W_K"] == pytest.approx(30000.0, rel=1e-12)
    assert result.info["min_approach_K"] > 0.0
    assert result.info["bvp_nodes"] >= 41


def test_r1_to_r0_identity() -> None:
    """R0 fed the R1 outlet temperatures reproduces every R1 outlet (1e-6 K on
    the balance stream, exact on the specified one)."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    r1 = MultiStreamR1().solve(inlets, MultiStreamR1.example_case()[1], thermo)

    r0 = MultiStreamExchanger().solve(inlets, {"T_out_hot_in_1": r1.outlets["hot_out_1"].T}, thermo)
    assert r0.outlets["hot_out_1"].T == pytest.approx(r1.outlets["hot_out_1"].T, abs=1e-9)
    assert r0.outlets["cold_out_1"].T == pytest.approx(r1.outlets["cold_out_1"].T, abs=1e-6)
    assert r0.outlets["hot_out_2"] is r1.outlets["hot_out_2"]
    assert r0.outlets["cold_out_2"] is r1.outlets["cold_out_2"]
    assert r0.info["duty_hot_in_1_W"] == pytest.approx(r1.info["duty_hot_in_1_W"], rel=1e-7)


def test_dP_applied_per_stream() -> None:
    """A per-stream dP lowers that stream's outlet pressure, others unchanged."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    params = {**MultiStreamR1.example_case()[1], "dP_hot_in_1": 5.0e4, "dP_cold_in_1": 1.0e4}
    result = MultiStreamR1().solve(inlets, params, thermo)

    assert result.outlets["hot_out_1"].P == pytest.approx(1.0e6 - 5.0e4, rel=1e-12)
    assert result.outlets["cold_out_1"].P == pytest.approx(1.0e6 - 1.0e4, rel=1e-12)


def test_no_active_hot_or_cold_refused() -> None:
    """Both table rows: no active hot (or cold) stream is refused."""
    thermo = _thermo()
    feeds = _feeds()
    no_hot = {**feeds, "hot_in_1": {**feeds["hot_in_1"], "molar_flow": 0.0}}
    with pytest.raises(MultiStreamRatingError, match="at least one hot and one cold"):
        MultiStreamR1().solve(_inlets(thermo, no_hot), MultiStreamR1.example_case()[1], thermo)

    no_cold = {**feeds, "cold_in_1": {**feeds["cold_in_1"], "molar_flow": 0.0}}
    with pytest.raises(MultiStreamRatingError, match="at least one hot and one cold"):
        MultiStreamR1().solve(_inlets(thermo, no_cold), MultiStreamR1.example_case()[1], thermo)


def test_missing_or_nonpositive_hA_refused() -> None:
    """An active stream without hA, or with hA <= 0, is refused naming the param."""
    thermo = _thermo()
    inlets = _inlets(thermo, _feeds())
    with pytest.raises(MultiStreamRatingError, match="hA_hot_in_1_W_K"):
        MultiStreamR1().solve(inlets, {}, thermo)
    with pytest.raises(MultiStreamRatingError, match="hA_hot_in_1_W_K"):
        MultiStreamR1().solve(inlets, {"hA_hot_in_1_W_K": -1.0, "hA_cold_in_1_W_K": 60000.0}, thermo)


def test_nonpositive_outlet_pressure_refused() -> None:
    """dP that drives the outlet pressure to zero or below is refused."""
    thermo = _thermo()
    inlets = _inlets(thermo, _feeds())
    params = {**MultiStreamR1.example_case()[1], "dP_hot_in_1": 2.0e6}
    with pytest.raises(MultiStreamRatingError, match="non-positive outlet pressure"):
        MultiStreamR1().solve(inlets, params, thermo)


def test_inlet_temperature_cross_refused() -> None:
    """The hottest cold inlet at or above the coldest hot inlet is refused."""
    thermo = _thermo()
    feeds = _feeds()
    crossed = {
        **feeds,
        "hot_in_1": {**feeds["hot_in_1"], "T": 300.0},
        "cold_in_1": {**feeds["cold_in_1"], "T": 310.0},
    }
    with pytest.raises(TemperatureCross, match="inlet temperatures"):
        MultiStreamR1().solve(_inlets(thermo, crossed), MultiStreamR1.example_case()[1], thermo)


def test_bvp_failure_maps_to_convergence_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A solver that reports status != 0 surfaces as RatingConvergenceError."""
    from types import SimpleNamespace

    from ngdesign.units.heat import multi_stream_r1

    def failing_solve_bvp(*args: Any, **kwargs: Any) -> Any:
        return SimpleNamespace(status=1, message="diverged")

    monkeypatch.setattr(multi_stream_r1, "solve_bvp", failing_solve_bvp)
    thermo = _thermo()
    with pytest.raises(RatingConvergenceError, match="did not converge"):
        MultiStreamR1().solve(_inlets(thermo, _feeds()), MultiStreamR1.example_case()[1], thermo)
