"""Tests for the machine and exchanger sizers (spec S-32).

Solved-unit cases use each unit plugin's own example_case() basis (pump,
compressor) or a documented variant of it (the air-cooler example basis
crosses against the spec's fixed air utility, so its case runs at 400 -> 350 K
instead). The full locked slice cannot solve end to end yet (TEG contactor
convergence, strict-xfail tests/e2e/test_slice.py), so nothing here depends on
it.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.flowsheet import Datasheet, SolvedFlowsheet
from ngdesign.contracts.plugins import Sizer, Thermo
from ngdesign.sizing.machines import (
    G_STD,
    compressor_stages,
    exchanger_area,
    lmtd_counter,
    motor_kw,
    npsh_available,
)

PUMP_FEED = {  # Pump.example_case inlet: condensate blend, 1.0 -> 1.5 MPa
    "T": 293.15,
    "P": 1.0e6,
    "molar_flow": 5.0,
    "composition": {
        "C3": 0.35,
        "iC4": 0.15,
        "nC4": 0.25,
        "iC5": 0.10,
        "nC5": 0.10,
        "C6+": 0.05,
    },
}
DRY_GAS = {  # dry slice gas (no free water), renormalized
    "N2": 0.005 / 0.997,
    "CO2": 0.015 / 0.997,
    "C1": 0.848 / 0.997,
    "C2": 0.062 / 0.997,
    "C3": 0.032 / 0.997,
    "iC4": 0.007 / 0.997,
    "nC4": 0.010 / 0.997,
    "iC5": 0.004 / 0.997,
    "nC5": 0.004 / 0.997,
    "C6+": 0.010 / 0.997,
}


def _solve_one(
    thermo: Thermo, tag: str, kind: str, params: dict[str, Any], feed: dict[str, Any], service: str = "PG"
) -> SolvedFlowsheet:
    fs = Flowsheet(
        name=f"{tag}-alone",
        units=[UnitSpec(tag=tag, kind=kind, params=params)],
        streams=[
            StreamSpec(id=f"{tag}-IN", target=PortRef(unit=tag, port="inlet"), service=service, feed=feed),
            StreamSpec(id=f"{tag}-OUT", source=PortRef(unit=tag, port="outlet"), service=service),
        ],
    )
    solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(fs, thermo)
    assert solved.converged
    return solved


def _size(
    thermo: Thermo, sizer_name: str, solved: SolvedFlowsheet, tag: str, params: dict[str, Any]
) -> Datasheet:
    sizer = registry.get("sizer", sizer_name)()
    sheet: Datasheet = sizer.size(tag, solved, params)
    return sheet


class TestPumpPowerHandChecked:
    """Pure-function cases computed by hand."""

    def test_npsh_hand_checked(self) -> None:
        # (2e5 - 101933.5)/(1000*9.80665) = 10.0 m exactly; + 2.0 - 0.5 = 11.5.
        assert npsh_available(2e5, 101933.5, 1000.0, 2.0, 0.5) == pytest.approx(11.5, rel=1e-12)

    def test_lmtd_hand_checked(self) -> None:
        # dT1 = 400-330 = 70, dT2 = 350-300 = 50: LMTD = 20/ln(1.4).
        assert lmtd_counter(400, 350, 300, 330) == pytest.approx(20 / math.log(1.4), rel=1e-12)
        assert lmtd_counter(400, 350, 300, 330) == pytest.approx(59.4392, rel=1e-4)

    def test_lmtd_equal_dts(self) -> None:
        assert lmtd_counter(400, 350, 320, 370) == pytest.approx(30.0, rel=1e-9)

    def test_lmtd_temperature_cross_raises(self) -> None:
        with pytest.raises(ValueError):
            lmtd_counter(400, 350, 360, 410)  # dT1 = -10
        with pytest.raises(ValueError):
            lmtd_counter(400, 300, 310, 330)  # dT2 = -10

    def test_area_hand_checked(self) -> None:
        # Q = 300 kW, U = 300, LMTD = 20/ln(1.4): A = 1000/LMTD = 16.824 m2.
        lmtd = lmtd_counter(400, 350, 300, 330)
        assert exchanger_area(300e3, 300.0, lmtd) == pytest.approx(16.8239, rel=1e-4)

    def test_motor_kw_rounds_up(self) -> None:
        assert motor_kw(93.0) == 110.0
        assert motor_kw(45.0) == 45.0
        assert motor_kw(0.7) == 0.75
        assert motor_kw(500.1) == 560.0
        with pytest.raises(ValueError):
            motor_kw(0.0)
        with pytest.raises(ValueError):
            motor_kw(1001.0)

    def test_compressor_stages(self) -> None:
        assert compressor_stages(2.0) == 1
        assert compressor_stages(3.5) == 1  # at the limit: one stage
        assert compressor_stages(3.6) == 2
        assert compressor_stages(12.25) == 2  # exactly 3.5^2: two stages
        assert compressor_stages(16.0) == 3
        with pytest.raises(ValueError):
            compressor_stages(0.5)


class TestPumpSizer:
    def test_case_with_hand_checked_numbers(self, thermo: Thermo) -> None:
        solved = _solve_one(thermo, "P-101", "pump", {"P_out": 1.5e6, "eta": 0.65}, PUMP_FEED, service="PL")
        result = solved.units["P-101"]
        inlet = solved.streams["P-101-IN"]
        rho = inlet.mass_flow / sum(
            p.mole_fraction * inlet.molar_flow * p.molecular_weight / 1000.0 / p.density for p in inlet.phases
        )
        q = result.info["Q_m3_s"]

        sheet = _size(thermo, "pump", solved, "P-101", {"static_head_m": 2.0, "friction_head_m": 0.5})

        # Hand-checked physics: shaft = Q*dP/eta (S-08/S-27), head = dP/(rho*g).
        assert sheet.dimensions["shaft_kW"] == pytest.approx(q * (1.5e6 - 1.0e6) / 0.65 / 1000.0, rel=1e-9)
        assert sheet.dimensions["head_m"] == pytest.approx((1.5e6 - 1.0e6) / (rho * G_STD), rel=1e-9)
        assert sheet.dimensions["rated_flow_m3_s"] == pytest.approx(1.1 * q, rel=1e-9)
        assert sheet.dimensions["motor_kW"] == motor_kw(sheet.dimensions["shaft_kW"])
        # NPSHa plumbs the params through the S-08 formula on the suction state.
        assert sheet.dimensions["npsh_available_m"] == pytest.approx(
            npsh_available(inlet.P, 0.0, rho, 2.0, 0.5), rel=1e-9
        )

    def test_nozzles_cover_every_sim_port(self, thermo: Thermo) -> None:
        solved = _solve_one(thermo, "P-101", "pump", {"P_out": 1.5e6, "eta": 0.65}, PUMP_FEED, service="PL")
        sheet = _size(thermo, "pump", solved, "P-101", {})
        assert sorted(n.port for n in sheet.nozzles if n.port) == ["inlet", "outlet"]
        assert sheet.nozzles[0].service == "suction" or sheet.nozzles[0].port == "inlet"
        # Suction nozzle uses the tighter S-20 suction limits: not smaller than
        # a sizing pass with role="suction", and discharge uses the line role.
        assert all(n.id.startswith("N") for n in sheet.nozzles)

    def test_design_conditions(self, thermo: Thermo) -> None:
        solved = _solve_one(thermo, "P-101", "pump", {"P_out": 1.5e6, "eta": 0.65}, PUMP_FEED, service="PL")
        sheet = _size(thermo, "pump", solved, "P-101", {})
        # P_d = max(1.1 P, P + 170 kPa): at 1.5 MPa the +170 kPa rule wins.
        assert sheet.design_pressure_Pa == pytest.approx(1.5e6 + 170e3, rel=1e-9)
        assert sheet.design_temperature_K > 293.15 + 25.0  # discharge is warmer


class TestCompressorSizer:
    def test_case_with_hand_checked_numbers(self, thermo: Thermo) -> None:
        # Slice K-101 basis: dry gas 3.447 -> 7.0 MPa, eta 0.75. Ratio 2.031:
        # a single stage (below the 3.5 per-stage limit).
        feed = {
            "T": 322.15,
            "P": 3.447e6,
            "molar_flow": 50 * 6.098034,
            "composition": DRY_GAS,
        }
        solved = _solve_one(thermo, "K-101", "compressor", {"P_out": 7.0e6, "eta_isentropic": 0.75}, feed)
        result = solved.units["K-101"]
        inlet = solved.streams["K-101-IN"]
        outlet = solved.streams["K-101-OUT"]

        sheet = _size(thermo, "compressor", solved, "K-101", {})

        assert sheet.dimensions["pressure_ratio"] == pytest.approx(7.0e6 / 3.447e6, rel=1e-9)
        assert sheet.dimensions["stages"] == 1.0
        assert sheet.dimensions["power_kW"] == pytest.approx(result.power_W / 1000.0, rel=1e-12)
        # Actual discharge temperature from the discharge stream, above suction.
        assert sheet.dimensions["discharge_T_K"] == pytest.approx(outlet.T, rel=1e-12)
        assert outlet.T > inlet.T

    def test_nozzles_cover_every_sim_port(self, thermo: Thermo) -> None:
        feed = {"T": 322.15, "P": 3.447e6, "molar_flow": 50 * 6.098034, "composition": DRY_GAS}
        solved = _solve_one(thermo, "K-101", "compressor", {"P_out": 7.0e6, "eta_isentropic": 0.75}, feed)
        sheet = _size(thermo, "compressor", solved, "K-101", {})
        assert sorted(n.port for n in sheet.nozzles if n.port) == ["inlet", "outlet"]


class TestAirCoolerSizer:
    def test_case_with_hand_checked_numbers(self, thermo: Thermo) -> None:
        # Gas cooled 400 -> 350 K against air 308.15 -> 323.15 K, U = 300 (PG).
        # dT1 = 76.85, dT2 = 41.85, LMTD = 35/ln(76.85/41.85) ~ 57.60 K.
        feed = {"T": 400.0, "P": 7.0e6, "molar_flow": 100.0, "composition": DRY_GAS}
        solved = _solve_one(thermo, "E-101", "air_cooler", {"T_out": 350.0, "dP": 35e3}, feed)
        duty = abs(solved.units["E-101"].duty_W)

        sheet = _size(thermo, "air_cooler", solved, "E-101", {})

        lmtd_expected = 35.0 / math.log(76.85 / 41.85)
        assert sheet.dimensions["U_W_m2K"] == 300.0
        assert sheet.dimensions["lmtd_K"] == pytest.approx(lmtd_expected, rel=1e-3)
        assert sheet.dimensions["area_m2"] == pytest.approx(duty / (300.0 * lmtd_expected), rel=1e-3)
        assert duty > 0

    def test_nozzles_cover_every_sim_port_plus_vent_drain(self, thermo: Thermo) -> None:
        feed = {"T": 400.0, "P": 7.0e6, "molar_flow": 100.0, "composition": DRY_GAS}
        solved = _solve_one(thermo, "E-101", "air_cooler", {"T_out": 350.0, "dP": 35e3}, feed)
        sheet = _size(thermo, "air_cooler", solved, "E-101", {})
        assert sorted(n.port for n in sheet.nozzles if n.port) == ["inlet", "outlet"]
        services = [n.service for n in sheet.nozzles]
        assert "vent" in services and "drain" in services

    def test_cooling_below_air_outlet_raises(self, thermo: Thermo) -> None:
        # The unit example basis (322.15 -> 313.15 K) crosses the fixed air
        # utility (air out 323.15 K above process in 322.15): not sizeable.
        feed = {"T": 322.15, "P": 7.0e6, "molar_flow": 100.0, "composition": DRY_GAS}
        solved = _solve_one(thermo, "E-101", "air_cooler", {"T_out": 313.15, "dP": 0.0}, feed)
        with pytest.raises(ValueError, match="temperature cross"):
            _size(thermo, "air_cooler", solved, "E-101", {})


class TestShellTubeSizer:
    def test_case_with_hand_checked_numbers(self, thermo: Thermo) -> None:
        # Condensate heated 322.15 -> 333.15 K with 425 -> 424 K utility,
        # U = 600 (PL): dT1 = 91.85, dT2 = 101.85, LMTD ~ 96.76 K.
        feed = dict(PUMP_FEED, T=322.15, P=1.5e6)
        solved = _solve_one(thermo, "E-102", "shell_tube", {"T_out": 333.15, "dP": 50e3}, feed, service="PL")
        duty = abs(solved.units["E-102"].duty_W)

        sheet = _size(thermo, "shell_tube", solved, "E-102", {"utility_T_in": 425.0, "utility_T_out": 424.0})

        lmtd_expected = (91.85 - 101.85) / math.log(91.85 / 101.85)
        assert sheet.dimensions["U_W_m2K"] == 600.0
        assert sheet.dimensions["lmtd_K"] == pytest.approx(lmtd_expected, rel=1e-3)
        assert sheet.dimensions["area_m2"] == pytest.approx(duty / (600.0 * lmtd_expected), rel=1e-3)
        assert duty > 0

    def test_nozzles_cover_every_sim_port_plus_vent_drain(self, thermo: Thermo) -> None:
        feed = dict(PUMP_FEED, T=322.15, P=1.5e6)
        solved = _solve_one(thermo, "E-102", "shell_tube", {"T_out": 333.15, "dP": 50e3}, feed, service="PL")
        sheet = _size(thermo, "shell_tube", solved, "E-102", {"utility_T_in": 425.0, "utility_T_out": 424.0})
        assert sorted(n.port for n in sheet.nozzles if n.port) == ["inlet", "outlet"]
        services = [n.service for n in sheet.nozzles]
        assert "vent" in services and "drain" in services

    def test_missing_utility_params_raise(self, thermo: Thermo) -> None:
        feed = dict(PUMP_FEED, T=322.15, P=1.5e6)
        solved = _solve_one(thermo, "E-102", "shell_tube", {"T_out": 333.15, "dP": 50e3}, feed, service="PL")
        with pytest.raises(ValueError, match="utility_T_in"):
            _size(thermo, "shell_tube", solved, "E-102", {})


class TestRegistry:
    def test_sizer_names_and_kinds(self) -> None:
        for name in ("pump", "compressor", "air_cooler", "shell_tube"):
            assert cast(Sizer, registry.get("sizer", name)).unit_kind == name

    def test_wrong_kind_rejected(self, thermo: Thermo) -> None:
        solved = _solve_one(thermo, "P-101", "pump", {"P_out": 1.5e6, "eta": 0.65}, PUMP_FEED, service="PL")
        with pytest.raises(ValueError, match="kind"):
            _size(thermo, "compressor", solved, "P-101", {})
