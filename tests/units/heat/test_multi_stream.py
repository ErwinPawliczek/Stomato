"""Adapter tests: the multi-stream exchanger (spec U-C 6)."""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross

P = 1.01325e5


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _ss(thermo: Thermo, z: dict[str, float], T: float, n: float, P_: float = 1.0e6) -> StreamState:
    return thermo.flash_pt(z, T, P_, n)


def _cp_span(thermo: Thermo, T_in: float, T_out: float, cp_W_per_K: float, P_: float = 1.0e6) -> StreamState:
    """N2 feed sized so the span releases/absorbs exactly cp*dT."""
    z = {"N2": 1.0}
    dh = thermo.flash_pt(z, T_out, P_, 1.0).enthalpy - thermo.flash_pt(z, T_in, P_, 1.0).enthalpy
    return thermo.flash_pt(z, T_in, P_, cp_W_per_K * abs(T_out - T_in) / abs(dh))


def test_smith_table_16_2_streams_1_and_3() -> None:
    """The V2084 basis: hot spec'd to 313.15 K, cold as the balance stream."""
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    result = unit.solve(
        {
            "hot_in_1": _ss(thermo, {"N2": 1.0}, 523.15, 5068.172),
            "hot_in_2": _ss(thermo, {"N2": 1.0}, 523.15, 0.0),
            "cold_in_1": _ss(thermo, {"N2": 1.0}, 293.15, 6767.022),
            "cold_in_2": _ss(thermo, {"N2": 1.0}, 293.15, 0.0),
        },
        {"T_out_hot_in_1": 313.15},
        thermo,
    )
    assert result.outlets["cold_out_1"].T == pytest.approx(450.65, abs=0.5)
    assert result.outlets["hot_out_1"].T == pytest.approx(313.15, abs=0.05)
    assert result.info["duty_cold_in_1_W"] == pytest.approx(31.5e6, rel=1e-5)
    assert result.info["pinch_T_hot_K"] == pytest.approx(313.15, abs=0.5)
    assert result.info["pinch_T_cold_K"] == pytest.approx(293.15, abs=0.5)


def test_duty_sign_convention_hot_releases_cold_absorbs() -> None:
    """Both duty keys are positive: hot ports release, cold ports absorb."""
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    result = unit.solve(
        {
            "hot_in_1": _ss(thermo, {"N2": 1.0}, 523.15, 5068.172),
            "hot_in_2": _ss(thermo, {"N2": 1.0}, 523.15, 0.0),
            "cold_in_1": _ss(thermo, {"N2": 1.0}, 293.15, 6767.022),
            "cold_in_2": _ss(thermo, {"N2": 1.0}, 293.15, 0.0),
        },
        {"T_out_hot_in_1": 313.15},
        thermo,
    )
    assert result.info["duty_hot_in_1_W"] > 0.0
    assert result.info["duty_cold_in_1_W"] > 0.0
    assert result.info["duty_hot_in_1_W"] == pytest.approx(result.info["duty_cold_in_1_W"], rel=1e-9)
    # The unit closes at zero net duty (the balance stream absorbs the residual).
    assert abs(result.duty_W) <= 1e-6 * 31.5e6


def test_balance_stream_absorbs_residual_duty() -> None:
    """Hand case: hot releases 100 kW, cold_1 absorbs 25 kW, cold_2 gets 75 kW."""
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    hot = _cp_span(thermo, 500.0, 400.0, 1000.0)
    cold_1 = _cp_span(thermo, 300.0, 350.0, 500.0)
    cold_2 = _ss(thermo, {"N2": 1.0}, 300.0, 100.0)
    result = unit.solve(
        {
            "hot_in_1": hot,
            "hot_in_2": _ss(thermo, {"N2": 1.0}, 500.0, 0.0),
            "cold_in_1": cold_1,
            "cold_in_2": cold_2,
        },
        {"T_out_hot_in_1": 400.0, "T_out_cold_in_1": 350.0},
        thermo,
    )
    assert result.info["duty_cold_in_2_W"] == pytest.approx(75_000.0, rel=1e-6)
    # 75 kW into 100 mol/s N2 at ~29.2 J/mol/K: about 25.7 K of rise.
    assert result.outlets["cold_out_2"].T == pytest.approx(325.7, abs=1.0)


def test_zero_flow_sides_pass_through_positional_outlets() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    zero_hot = _ss(thermo, {"N2": 1.0}, 523.15, 0.0)
    zero_cold = _ss(thermo, {"N2": 1.0}, 293.15, 0.0)
    result = unit.solve(
        {
            "hot_in_1": _ss(thermo, {"N2": 1.0}, 523.15, 5068.172),
            "hot_in_2": zero_hot,
            "cold_in_1": _ss(thermo, {"N2": 1.0}, 293.15, 6767.022),
            "cold_in_2": zero_cold,
        },
        {"T_out_hot_in_1": 313.15},
        thermo,
    )
    # Positional outlets: hot_out_2 pairs hot_in_2 (NOT a mirrored name).
    assert result.outlets["hot_out_2"].molar_flow == 0.0
    assert result.outlets["hot_out_2"].T == pytest.approx(523.15, abs=1e-9)
    assert result.outlets["cold_out_2"].T == pytest.approx(293.15, abs=1e-9)


def test_two_balance_streams_refused() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    with pytest.raises(ValueError, match="exactly one active stream must be the balance stream"):
        unit.solve(
            {
                "hot_in_1": _ss(thermo, {"N2": 1.0}, 500.0, 100.0),
                "hot_in_2": _ss(thermo, {"N2": 1.0}, 500.0, 100.0),
                "cold_in_1": _ss(thermo, {"N2": 1.0}, 300.0, 100.0),
                "cold_in_2": _ss(thermo, {"N2": 1.0}, 300.0, 100.0),
            },
            {"T_out_cold_in_1": 350.0, "T_out_cold_in_2": 350.0},
            thermo,
        )


def test_crossing_arrangement_refused() -> None:
    """A hot stream spec'd to fall below the cold inlet crosses and is refused."""
    thermo = _thermo()
    unit = registry.create("unit", "multi_stream")
    with pytest.raises(TemperatureCross, match="temperature cross"):
        unit.solve(
            {
                "hot_in_1": _cp_span(thermo, 400.0, 350.0, 1000.0),
                "hot_in_2": _ss(thermo, {"N2": 1.0}, 400.0, 0.0),
                "cold_in_1": _cp_span(thermo, 280.0, 370.0, 3000.0),
                "cold_in_2": _ss(thermo, {"N2": 1.0}, 280.0, 0.0),
            },
            {"T_out_hot_in_1": 250.0},
            thermo,
        )
