"""Closed-form tests: the multi-stream R1 common-wall BVP core (spec step 1).

Hand-computed reference numbers from an independent RK4 + shooting calculation
(``calc_multi_stream.py``, not the module's own output). With constant heat
capacity rates the common-wall model is exactly counter-current epsilon-NTU
with 1/UA = 1/(hA)_h + 1/(hA)_c; the test tables are the constant-C enthalpy
tables T = H/C + T_ref of the spec.

MS1: one hot (C = 1500 W/K, hA = 4000 W/K, 400 K) against one cold
(C = 2500 W/K, hA = 4000 W/K, 300 K). UA = 1/(1/4000 + 1/4000) = 2000 W/K,
NTU = UA/C_min = 4/3, Cr = 0.6:

    epsilon = (1 - exp(-NTU (1 - Cr))) / (1 - Cr exp(-NTU (1 - Cr)))
            = (1 - exp(-8/15)) / (1 - 0.6 exp(-8/15))
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

import numpy as np
import pytest
from scipy.interpolate import PchipInterpolator

from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream_r1 import (
    CommonWallResult,
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
