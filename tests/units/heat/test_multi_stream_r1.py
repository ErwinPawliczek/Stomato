"""multi_stream R1 tests; MS1 and MS2 come from the spec's calc_multi_stream.py
(its own RK4 plus shooting), independent of the BVP here."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat import multi_stream_r1
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.multi_stream_r1 import (
    MultiStreamR1,
    MultiStreamRatingError,
    WallStream,
    solve_common_wall,
    uniform,
)
from ngdesign.units.heat.rating import RatingConvergenceError


def _stream(c: float, t_in: float, t_far: float, is_hot: bool) -> WallStream:
    """A constant-C stream: H = C*T, so T = H/C (the spec's test table)."""
    return WallStream(
        is_hot=is_hot, H_in_W=c * t_in, H_far_W=c * t_far, T_of_H=lambda h: np.asarray(h, dtype=float) / c
    )


def test_ms1_is_counterflow() -> None:
    """Two streams: exactly epsilon-NTU with 1/UA = 1/4000 + 1/4000, Q = 95681.934 W."""
    hot = _stream(1500.0, 400.0, 300.0, True)
    cold = _stream(2500.0, 300.0, 400.0, False)
    sol = solve_common_wall([hot, cold], uniform([4000.0, 4000.0]))
    assert sol.H_out_W[0] / 1500.0 == pytest.approx(336.212044, rel=1e-7)
    assert sol.H_out_W[1] / 2500.0 == pytest.approx(338.272774, rel=1e-7)
    assert hot.H_in_W - sol.H_out_W[0] == pytest.approx(95681.934, rel=1e-7)


def test_ms2_two_hot_streams() -> None:
    streams = [
        _stream(1000.0, 400.0, 300.0, True),
        _stream(800.0, 380.0, 300.0, True),
        _stream(2500.0, 300.0, 400.0, False),
    ]
    sol = solve_common_wall(streams, uniform([3000.0, 2000.0, 5000.0]))
    assert sol.H_out_W[0] / 1000.0 == pytest.approx(332.809133, abs=1e-5)
    assert sol.H_out_W[1] / 800.0 == pytest.approx(334.749305, abs=1e-5)
    assert sol.H_out_W[2] / 2500.0 == pytest.approx(341.356569, abs=1e-5)
    assert streams[0].H_in_W - sol.H_out_W[0] == pytest.approx(67190.8674, abs=1e-1)
    assert streams[1].H_in_W - sol.H_out_W[1] == pytest.approx(36200.5559, abs=1e-1)
    assert sol.H_out_W[2] - streams[2].H_in_W == pytest.approx(103391.423, abs=1e-1)


def test_a_cooler_hot_stream_may_sit_below_the_wall() -> None:
    """Reheating is the model: the unit's composite check must not refuse it."""
    streams = [
        _stream(1000.0, 500.0, 300.0, True),
        _stream(5000.0, 340.0, 300.0, True),
        _stream(2000.0, 300.0, 500.0, False),
    ]
    sol = solve_common_wall(streams, uniform([3000.0, 200.0, 3000.0]))
    assert float((sol.T_wall_K - sol.T_K[1]).max()) > 0.0


def _inlets(thermo: Thermo, **flows: float) -> dict[str, Any]:
    feeds, _ = MultiStreamExchanger.example_case()
    out = {}
    for port, f in feeds.items():
        flow = flows.get(port, f["molar_flow"])
        out[port] = thermo.flash_pt(f["composition"], f["T"], f["P"], flow)
    return out


def test_reduces_to_r0_at_its_own_outlets(thermo: Thermo) -> None:
    """Feed R1's hot outlet T to R0 as a spec: R0's balance stream lands on R1's cold outlet."""
    inlets = _inlets(thermo)
    r1 = MultiStreamR1().solve(inlets, MultiStreamR1.example_case()[1], thermo)
    t_out = r1.outlets["hot_out_1"].T
    r0 = MultiStreamExchanger().solve(inlets, {"T_out_hot_in_1": t_out}, thermo)
    assert r0.outlets["hot_out_1"].T == pytest.approx(t_out, abs=1e-9)
    assert r0.outlets["cold_out_1"].T == pytest.approx(r1.outlets["cold_out_1"].T, abs=1e-6)


def test_zero_flow_ports_pass_through(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    res = MultiStreamR1().solve(inlets, MultiStreamR1.example_case()[1], thermo)
    assert res.outlets["hot_out_2"].molar_flow == 0.0
    assert res.outlets["cold_out_2"].T == inlets["cold_in_2"].T
    assert res.info["duty_hot_in_1_W"] == pytest.approx(res.info["duty_cold_in_1_W"], rel=1e-7)


def test_condensing_hot_stream_uses_the_plateau(thermo: Thermo) -> None:
    """Pure propane condenses at constant T: the hot stream ends two-phase at T_sat."""
    inlets = {
        "hot_in_1": thermo.flash_pt({"C3": 1.0}, 330.0, 1.0e6, 1.0),
        "hot_in_2": thermo.flash_pt({"C3": 1.0}, 330.0, 1.0e6, 0.0),
        "cold_in_1": thermo.flash_pt({"N2": 1.0}, 280.0, 1.0e6, 30.0),
        "cold_in_2": thermo.flash_pt({"N2": 1.0}, 280.0, 1.0e6, 0.0),
    }
    params = {"hA_hot_in_1_W_K": 2000.0, "hA_cold_in_1_W_K": 2000.0}
    res = MultiStreamR1().solve(inlets, params, thermo)
    out = res.outlets["hot_out_1"]
    assert 0.0 < out.vapor_fraction < 1.0
    assert out.T == pytest.approx(thermo.bubble_point({"C3": 1.0}, P=1.0e6).T, abs=1e-3)


def test_pressure_drop_is_applied(thermo: Thermo) -> None:
    params = {**MultiStreamR1.example_case()[1], "dP_hot_in_1": 5.0e4}
    res = MultiStreamR1().solve(_inlets(thermo), params, thermo)
    assert res.outlets["hot_out_1"].P == pytest.approx(9.5e5)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"hA_hot_in_1_W_K": None}, "hA_hot_in_1_W_K"),
        ({"hA_cold_in_1_W_K": 0.0}, "hA_cold_in_1_W_K"),
        ({"dP_hot_in_1": 2.0e6}, "non-positive outlet pressure"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = dict(MultiStreamR1.example_case()[1])
    params.update(change)
    params = {k: v for k, v in params.items() if v is not None}
    with pytest.raises(MultiStreamRatingError, match=match):
        MultiStreamR1().solve(_inlets(thermo), params, thermo)


def test_one_sided_exchanger_refused(thermo: Thermo) -> None:
    with pytest.raises(MultiStreamRatingError, match="at least one hot and one cold"):
        MultiStreamR1().solve(_inlets(thermo, cold_in_1=0.0), MultiStreamR1.example_case()[1], thermo)


def test_no_driving_force_refused(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    inlets["hot_in_1"] = thermo.flash_pt({"N2": 1.0}, 280.0, 1.0e6, 10.0)
    with pytest.raises(TemperatureCross, match="inlet temperatures"):
        MultiStreamR1().solve(inlets, MultiStreamR1.example_case()[1], thermo)


def test_stiff_conductances_solve() -> None:
    """NTU near 500 once hit the node cap: unscaled H left round-off above the tolerance."""
    streams = [
        _stream(100.0, 500.0, 300.0, True),
        _stream(5000.0, 340.0, 300.0, True),
        _stream(2000.0, 300.0, 500.0, False),
    ]
    sol = solve_common_wall(streams, uniform([50000.0, 10.0, 50000.0]))
    released = sum(s.H_in_W - h for s, h in zip(streams[:2], sol.H_out_W[:2], strict=True))
    assert sol.H_out_W[2] - streams[2].H_in_W == pytest.approx(released, rel=1e-7)


def test_bvp_failure_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Failed:
        status = 1
        message = "The maximum number of mesh nodes is exceeded."

    monkeypatch.setattr(multi_stream_r1, "solve_bvp", lambda *_a, **_k: Failed)
    streams = [_stream(1500.0, 400.0, 300.0, True), _stream(2500.0, 300.0, 400.0, False)]
    with pytest.raises(RatingConvergenceError, match="did not converge"):
        solve_common_wall(streams, uniform([4000.0, 4000.0]))
