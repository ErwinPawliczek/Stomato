"""Closed-form, identity and refusal tests for compressor R1.

Spec: specs/backend/units/compressor.md. The expected values are the spec's
measured numbers, reproduced independently by
scratchpad/unit-specs/calc_compressor.py (direct PR flashes plus a 200-step
bisection; no brentq and no R1 code).

Closed-form anchor (spec eqs. 1-5, hand-computed): the example feed flashes
to rho1 = 28.380163 kg/m3, so Q = mdot/rho1 = 0.491529703 m3/s. The spec
map PCHIP at Q gives H = 60508.2178 J/kg and eta = 0.747458911 (linear
data between the 0.40 and 0.50 nodes: 66000 - (Q-0.40)/0.10*6000 =
60508.2, and 0.72 + (Q-0.40)/0.10*0.03 = 0.74746; PCHIP reproduces the
piecewise-linear shape to the printed digits). On the isentropic basis
the operating point solves (h(P2, s1) - h1)/M = H at P2 = 5540987.99 Pa
(ratio 1.60748128), T_out = 364.548325 K, and the power is
mdot*H/eta = 1129254.14 W.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.compressor import Compressor
from ngdesign.units.flow.compressor_r1 import (
    CompressorMapRangeError,
    CompressorR1,
    CompressorR1SpecError,
    CompressorStonewallError,
    CompressorSurgeError,
    CompressorTwoPhaseError,
)
from tests.conftest import flash_feed

MAP: dict[str, Any] = {
    "flow_m3_s": [0.30, 0.40, 0.50, 0.60, 0.70],
    "head_J_kg": [72000.0, 66000.0, 60000.0, 54000.0, 48000.0],
    "efficiency": [0.69, 0.72, 0.75, 0.78, 0.81],
}


def _inlet(thermo: Thermo) -> dict[str, StreamState]:
    feeds, _ = Compressor.example_case()
    return {"inlet": flash_feed(thermo, feeds["inlet"])}


def _params(**over: Any) -> dict[str, Any]:
    map_data = {key: list(values) for key, values in MAP.items()}
    params: dict[str, Any] = {
        "map": map_data,
        # 3.0 keeps the head bracket in the vapour region for the example
        # feed; at the spec default 10 the isentropic head at b evaluates
        # the dense region and turns negative -- see the PR comment.
        "max_pressure_ratio": 3.0,
    }
    params.update(over)
    return params


def test_map_operating_point(thermo: Thermo) -> None:
    """The spec map at the example feed: Q, interpolated head/eta, margins."""
    result = CompressorR1().solve(_inlet(thermo), _params(efficiency_basis="isentropic"), thermo)
    info = result.info
    assert info["Q_actual_m3_s"] == pytest.approx(0.491529703, rel=1e-7)
    assert info["head_J_kg"] == pytest.approx(60508.2178, rel=1e-7)
    assert info["eta"] == pytest.approx(0.747458911, rel=1e-7)
    assert info["surge_margin"] == pytest.approx(0.638432344, rel=1e-7)
    assert info["stonewall_margin"] == pytest.approx(0.29781471, rel=1e-7)
    assert result.duty_W == 0.0
    assert result.power_W > 0.0


def test_closed_form_isentropic(thermo: Thermo) -> None:
    """Isentropic basis reproduces the independent bisection to 1e-7 relative."""
    result = CompressorR1().solve(_inlet(thermo), _params(efficiency_basis="isentropic"), thermo)
    assert result.info["P_out_Pa"] == pytest.approx(5540987.99, rel=1e-7)
    assert result.info["pressure_ratio"] == pytest.approx(1.60748128, rel=1e-7)
    assert result.info["T_out_K"] == pytest.approx(364.548325, rel=1e-7)
    assert result.power_W == pytest.approx(1129254.14, rel=1e-7)


def test_isentropic_reduces_to_r0(thermo: Thermo) -> None:
    """Reduction to the lower level: R1 delegates to R0, so outputs are identical."""
    inlets = _inlet(thermo)
    r1 = CompressorR1().solve(inlets, _params(efficiency_basis="isentropic"), thermo)
    r0 = Compressor().solve(
        inlets,
        {"P_out": r1.info["P_out_Pa"], "eta_isentropic": r1.info["eta"]},
        thermo,
    )
    out_r1, out_r0 = r1.outlets["outlet"], r0.outlets["outlet"]
    assert out_r1.T == out_r0.T
    assert out_r1.P == out_r0.P
    assert out_r1.enthalpy == out_r0.enthalpy
    assert r1.power_W == r0.power_W


# --- refusals: the CompressorR1SpecError rows of the spec's refusal table ---


def test_refuse_liquid_inlet(thermo: Thermo) -> None:
    """A two-phase inlet is refused exactly as in R0."""
    feed = {
        "T": 280.0,
        "P": 3.447e6,
        "molar_flow": 691.706196,
        "composition": Compressor.example_case()[0]["inlet"]["composition"],
    }
    with pytest.raises(CompressorR1SpecError, match="inlet has liquid"):
        CompressorR1().solve({"inlet": flash_feed(thermo, feed)}, _params(), thermo)


def test_refuse_map_missing(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="map"):
        CompressorR1().solve(_inlet(thermo), {}, thermo)


def test_refuse_map_key_missing(thermo: Thermo) -> None:
    params = _params()
    del params["map"]["head_J_kg"]
    with pytest.raises(CompressorR1SpecError, match="map.head_J_kg"):
        CompressorR1().solve(_inlet(thermo), params, thermo)


def test_refuse_map_arrays_unequal(thermo: Thermo) -> None:
    params = _params()
    params["map"]["flow_m3_s"] = [0.30, 0.40, 0.50]
    with pytest.raises(CompressorR1SpecError, match="same length"):
        CompressorR1().solve(_inlet(thermo), params, thermo)


def test_refuse_map_single_point(thermo: Thermo) -> None:
    params = _params()
    for key in params["map"]:
        params["map"][key] = params["map"][key][:1]
    with pytest.raises(CompressorR1SpecError, match="strictly increasing"):
        CompressorR1().solve(_inlet(thermo), params, thermo)


def test_refuse_map_not_increasing(thermo: Thermo) -> None:
    params = _params()
    params["map"]["flow_m3_s"] = [0.50, 0.40, 0.45, 0.60, 0.70]
    with pytest.raises(CompressorR1SpecError, match="strictly increasing"):
        CompressorR1().solve(_inlet(thermo), params, thermo)


def test_refuse_bad_efficiency_basis(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="efficiency_basis"):
        CompressorR1().solve(_inlet(thermo), _params(efficiency_basis="adiabatic"), thermo)


def test_refuse_nonpositive_speed_ratio(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="speed_ratio"):
        CompressorR1().solve(_inlet(thermo), _params(speed_ratio=0.0), thermo)


def test_refuse_degenerate_max_pressure_ratio(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="max_pressure_ratio"):
        CompressorR1().solve(_inlet(thermo), _params(max_pressure_ratio=1.0), thermo)


def test_refuse_surge_outside_map(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="surge_flow_m3_s"):
        CompressorR1().solve(_inlet(thermo), _params(surge_flow_m3_s=0.20), thermo)


def test_refuse_surge_at_or_above_stonewall(thermo: Thermo) -> None:
    with pytest.raises(CompressorR1SpecError, match="surge_flow_m3_s"):
        CompressorR1().solve(
            _inlet(thermo),
            _params(surge_flow_m3_s=0.70, stonewall_flow_m3_s=0.70),
            thermo,
        )


def test_refuse_surge(thermo: Thermo) -> None:
    """speed_ratio 1.8 gives Q_eq = 0.273 < 0.30 m3/s, left of the surge line."""
    with pytest.raises(CompressorSurgeError, match="surge"):
        CompressorR1().solve(_inlet(thermo), _params(speed_ratio=1.8), thermo)


def test_refuse_stonewall(thermo: Thermo) -> None:
    """speed_ratio 0.6 gives Q_eq = 0.819 > 0.70 m3/s, right of the stonewall line."""
    with pytest.raises(CompressorStonewallError, match="stonewall"):
        CompressorR1().solve(_inlet(thermo), _params(speed_ratio=0.6), thermo)


def test_refuse_map_range(thermo: Thermo) -> None:
    """Q_eq above the last map node but inside the set surge/stonewall limits."""
    with pytest.raises(CompressorMapRangeError, match="outside the map"):
        CompressorR1().solve(
            _inlet(thermo),
            _params(surge_flow_m3_s=0.45, stonewall_flow_m3_s=0.80, speed_ratio=0.7),
            thermo,
        )


# --- step 2: the polytropic (Schultz) basis and its remaining refusals ---


def test_closed_form_polytropic(thermo: Thermo) -> None:
    """Polytropic basis reproduces the independent bisection and Schultz pieces."""
    result = CompressorR1().solve(_inlet(thermo), _params(), thermo)
    info = result.info
    assert info["P_out_Pa"] == pytest.approx(5499757.94, rel=1e-7)
    assert info["T_out_K"] == pytest.approx(364.402793, rel=1e-7)
    assert info["schultz_f"] == pytest.approx(0.999768572, rel=1e-6)
    assert info["n_polytropic"] == pytest.approx(1.37543075, rel=1e-6)
    assert info["n_isentropic_path"] == pytest.approx(1.25477227, rel=1e-6)
    assert result.power_W == pytest.approx(1129254.14, rel=1e-7)


def test_power_identity(thermo: Thermo) -> None:
    """power_W = F*(h2 - h1) = mdot*H/eta in both bases (spec eq. 7)."""
    inlets = _inlet(thermo)
    mdot = inlets["inlet"].mass_flow
    for basis in ("isentropic", "polytropic"):
        result = CompressorR1().solve(inlets, _params(efficiency_basis=basis), thermo)
        assert result.power_W == pytest.approx(mdot * result.info["head_J_kg"] / result.info["eta"], rel=1e-9)


def test_speed_105_polytropic(thermo: Thermo) -> None:
    """Fan laws at s = 1.05: H scales by s^2, eta and Q_eq by the map at Q_eq."""
    result = CompressorR1().solve(_inlet(thermo), _params(speed_ratio=1.05), thermo)
    info = result.info
    assert info["Q_equiv_m3_s"] == pytest.approx(0.468123527, rel=1e-7)
    assert info["head_J_kg"] == pytest.approx(68258.6287, rel=1e-7)
    assert info["eta"] == pytest.approx(0.740437058, rel=1e-7)
    assert info["P_out_Pa"] == pytest.approx(5813393.74, rel=1e-7)


def test_polytropic_self_consistency(thermo: Thermo) -> None:
    """Eq. 6 recomputed from the returned outlet state equals the map head."""
    inlet = _inlet(thermo)["inlet"]
    result = CompressorR1().solve({"inlet": inlet}, _params(), thermo)
    outlet = result.outlets["outlet"]
    v1 = 1.0 / inlet.phases[0].density
    v2 = 1.0 / outlet.phases[0].density
    n = math.log(outlet.P / inlet.P) / math.log(v1 / v2)
    head_p = result.info["schultz_f"] * (n / (n - 1.0)) * (outlet.P * v2 - inlet.P * v1)
    assert head_p == pytest.approx(result.info["head_J_kg"], rel=1e-8)


def test_refuse_no_root_up_to_max_pressure_ratio(thermo: Thermo) -> None:
    """max_pressure_ratio 1.2 caps the head below the map head: no root."""
    with pytest.raises(CompressorMapRangeError, match="max_pressure_ratio"):
        CompressorR1().solve(_inlet(thermo), _params(max_pressure_ratio=1.2), thermo)


def test_refuse_two_phase_head_evaluation(thermo: Thermo) -> None:
    """A two-phase state at a head evaluation raises CompressorTwoPhaseError.

    The real PR flasher keeps isentropic compression of a single-phase
    vapour single-phase for every composition and pressure ratio probed
    (dense states are classified as a single phase, not two), so this test
    wires a genuine two-phase StreamState (from flash_pt of the example gas
    at 280 K) into a stubbed flasher to exercise the refusal itself.
    """
    two_phase = thermo.flash_pt(
        Compressor.example_case()[0]["inlet"]["composition"],
        280.0,
        3.447e6,
        691.706196,
    )
    assert len(two_phase.phases) == 2

    class _StubThermo:
        def __getattr__(self, name: str):
            return getattr(thermo, name)

        def flash_ps(self, *args: Any, **kwargs: Any) -> StreamState:
            return two_phase

    with pytest.raises(CompressorTwoPhaseError, match="two-phase"):
        CompressorR1().solve(_inlet(thermo), _params(), _StubThermo())
