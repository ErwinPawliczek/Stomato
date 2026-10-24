"""Adapter tests: plate and double-pipe two-stream exchangers (spec U-C 4/5)."""

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


def _ss(thermo: Thermo, z: dict[str, float], T: float, n: float, P_: float = P) -> StreamState:
    return thermo.flash_pt(z, T, P_, n)


def _cp_span(
    thermo: Thermo, cid: str, T_in: float, T_out: float, cp_W_per_K: float, P_: float = P
) -> StreamState:
    """Feed sized so the span releases/absorbs exactly cp*dT at the mean cp."""
    z = {cid: 1.0}
    dh = thermo.flash_pt(z, T_out, P_, 1.0).enthalpy - thermo.flash_pt(z, T_in, P_, 1.0).enthalpy
    return thermo.flash_pt(z, T_in, P_, cp_W_per_K * abs(T_out - T_in) / abs(dh))


def test_plate_duty_spec_smith_table_16_1_basis() -> None:
    """Smith Table 16.1 streams at an 11 MW duty: 323.15/368.15 K, 10 K approach.

    Hot water CP 0.1 MW/K (433.15 K), cold CP 0.2 MW/K (313.15 K): the hot
    drops 110 K, the cold rises 55 K, and the cold-end approach is exactly
    hot_out - cold_in = 10 K.
    """
    thermo = _thermo()
    unit = registry.create("unit", "plate_exchanger")
    result = unit.solve(
        {
            "hot_in": _ss(thermo, {"H2O": 1.0}, 433.15, 1202.379, 1.0e6),
            "cold_in": _ss(thermo, {"H2O": 1.0}, 313.15, 2451.658, 1.0e6),
        },
        {"duty_W": 1.1e7},
        thermo,
    )
    assert result.outlets["hot_out"].T == pytest.approx(323.15, abs=0.1)
    assert result.outlets["cold_out"].T == pytest.approx(368.15, abs=0.1)
    assert result.info["duty_W"] == pytest.approx(1.1e7, rel=1e-6)
    assert result.info["min_approach_K"] == pytest.approx(10.0, abs=0.01)
    # The unit-level duty (the enthalpy residual) is rounding-level: both
    # streams are internal and the transferred heat is in info.
    assert abs(result.duty_W) <= 1e-6 * abs(1.1e7)


def test_double_pipe_hot_T_out_spec_kern_example_6_1() -> None:
    """Kern Ex 6.1 basis: toluene spec'd to 310.928 K; duty and benzene outlet.

    The measured duty carries the package cp gap (documented as the V2082
    assessed note); here the exact balance is asserted against the package's
    own arithmetic.
    """
    thermo = _thermo()
    unit = registry.create("unit", "double_pipe")
    result = unit.solve(
        {
            "hot_in": _ss(thermo, {"TOLUENE": 1.0}, 363.15, 5.0),
            "cold_in": _ss(thermo, {"BENZENE": 1.0}, 299.817, 15.0),
        },
        {"hot_T_out": 310.928},
        thermo,
    )
    assert result.outlets["hot_out"].T == pytest.approx(310.928, abs=0.1)
    assert result.outlets["cold_out"].T == pytest.approx(322.4837, abs=0.1)
    assert result.info["duty_W"] == pytest.approx(41660.5, rel=1e-4)
    assert result.info["min_approach_K"] == pytest.approx(11.111, abs=0.01)
    assert result.info["lmtd_valid"] == 1.0


def test_exchangers_refuse_two_specs() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "plate_exchanger")
    with pytest.raises(ValueError, match="exactly one"):
        unit.solve(
            {
                "hot_in": _ss(thermo, {"H2O": 1.0}, 433.15, 100.0, 1.0e6),
                "cold_in": _ss(thermo, {"H2O": 1.0}, 313.15, 100.0, 1.0e6),
            },
            {"duty_W": 1.0e6, "hot_T_out": 350.0},
            thermo,
        )


def test_exchangers_refuse_crossing_spec() -> None:
    """A cold_T_out spec above the hot inlet crosses and is refused."""
    thermo = _thermo()
    unit = registry.create("unit", "double_pipe")
    with pytest.raises(TemperatureCross, match="temperature cross"):
        unit.solve(
            {
                "hot_in": _cp_span(thermo, "N2", 400.0, 350.0, 1000.0, 1.0e6),
                "cold_in": _cp_span(thermo, "N2", 280.0, 370.0, 3000.0, 1.0e6),
            },
            {"cold_T_out": 410.0},
            thermo,
        )


def test_exchangers_min_approach_spec_bisects_duty() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "plate_exchanger")
    result = unit.solve(
        {
            "hot_in": _cp_span(thermo, "H2O", 400.0, 350.0, 1000.0, 1.0e6),
            "cold_in": _cp_span(thermo, "H2O", 280.0, 330.0, 1000.0, 1.0e6),
        },
        {"min_approach_K": 50.0},
        thermo,
    )
    assert result.info["duty_W"] == pytest.approx(70_000.0, rel=0.01)  # water cp(T) variation
    assert result.info["min_approach_K"] == pytest.approx(50.0, abs=0.05)


def test_exchangers_dP_drops_outlet_pressures() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "plate_exchanger")
    result = unit.solve(
        {
            "hot_in": _ss(thermo, {"H2O": 1.0}, 433.15, 100.0, 1.0e6),
            "cold_in": _ss(thermo, {"H2O": 1.0}, 313.15, 100.0, 1.0e6),
        },
        {"hot_T_out": 353.15, "dP_hot": 2.0e4, "dP_cold": 2.0e4},
        thermo,
    )
    assert result.outlets["hot_out"].P == pytest.approx(1.0e6 - 2.0e4, rel=1e-9)
    assert result.outlets["cold_out"].P == pytest.approx(1.0e6 - 2.0e4, rel=1e-9)


def test_exchangers_report_lmtd_and_ua() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "plate_exchanger")
    result = unit.solve(
        {
            "hot_in": _ss(thermo, {"H2O": 1.0}, 433.15, 100.0, 1.0e6),
            "cold_in": _ss(thermo, {"H2O": 1.0}, 313.15, 100.0, 1.0e6),
        },
        {"hot_T_out": 353.15},
        thermo,
    )
    duty = result.info["duty_W"]
    lmtd = result.info["LMTD_K"]
    assert lmtd > 0.0
    assert result.info["UA_W_K"] == pytest.approx(duty / lmtd, rel=1e-9)
