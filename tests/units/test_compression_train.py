"""Wave-2 acceptance tests: multistage compression train with interstage cooling."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.compression_train import stage_plan
from tests.conftest import flash_feed

P_IN = 3.447e6


def _solve(thermo: Thermo, params: dict[str, Any] | None = None) -> UnitResult:
    unit = registry.create("unit", "compression_train")
    feeds, defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result: UnitResult = unit.solve(inlets, params or defaults, thermo)
    return result


# --- stage-ratio split golden, including the non-integer rounding rule ----


def test_stage_plan_two_stage_split() -> None:
    n, r = stage_plan(P_IN, 15.0e6, 3.5)
    ratio = 15.0e6 / P_IN
    assert n == 2
    assert r == pytest.approx(math.sqrt(ratio), rel=1e-12)
    assert r <= 3.5


def test_stage_plan_single_stage_when_ratio_fits() -> None:
    n, r = stage_plan(P_IN, 7.0e6, 3.5)
    assert n == 1
    assert r == pytest.approx(7.0e6 / P_IN, rel=1e-12)


def test_stage_plan_exact_stage_cap_counts_once() -> None:
    n, r = stage_plan(P_IN, P_IN * 3.5, 3.5)
    assert n == 1
    assert r == pytest.approx(3.5, rel=1e-12)


def test_stage_plan_exact_two_stage_boundary_not_rounded_up() -> None:
    # ln(max**2)/ln(max) can exceed 2.0 by one ulp; the physically exact
    # two-stage case must not round up to 3.
    n, r = stage_plan(P_IN, P_IN * 3.5**2, 3.5)
    assert n == 2
    assert r == pytest.approx(3.5, rel=1e-12)


def test_stage_plan_just_above_boundary_rounds_up() -> None:
    n, _r = stage_plan(P_IN, P_IN * 3.5**2 * (1 + 1e-6), 3.5)
    assert n == 3


def test_stage_plan_rejects_letdown() -> None:
    with pytest.raises(ValueError, match="P_discharge"):
        stage_plan(P_IN, 1.0e6, 3.5)


def test_stage_plan_rejects_degenerate_cap() -> None:
    with pytest.raises(ValueError, match="max_ratio_per_stage"):
        stage_plan(P_IN, 15.0e6, 1.0)


# --- solve: golden per-stage discharge pressures and readouts --------------


def test_two_stage_golden_discharge_pressures(thermo: Thermo) -> None:
    result = _solve(thermo)
    ratio = 15.0e6 / P_IN
    assert result.info["stages"] == 2
    assert result.info["stage_1_P_discharge"] == pytest.approx(P_IN * math.sqrt(ratio), rel=1e-6)
    assert result.info["stage_2_P_discharge"] == pytest.approx(15.0e6, rel=1e-6)
    # one intercooler, after stage 1 only (no cooler after the final stage)
    assert "stage_1_intercooler_duty_W" in result.info
    assert "stage_2_intercooler_duty_W" not in result.info
    assert result.info["stage_1_intercooler_duty_W"] < 0
    assert result.info["total_power_W"] == pytest.approx(result.power_W, rel=1e-12)
    assert result.info["total_intercooler_duty_W"] == pytest.approx(result.duty_W, rel=1e-12)


def test_single_stage_has_no_intercooler_duty(thermo: Thermo) -> None:
    result = _solve(thermo, {"P_discharge": 7.0e6})
    assert result.info["stages"] == 1
    assert result.outlets["gas_out"].P == pytest.approx(7.0e6, rel=1e-6)
    assert not any(k.endswith("_intercooler_duty_W") and k != "total_intercooler_duty_W" for k in result.info)


def test_energy_balance_across_the_train(thermo: Thermo) -> None:
    result = _solve(thermo)
    unit = registry.create("unit", "compression_train")
    feeds, _params = unit.example_case()
    inlet = flash_feed(thermo, feeds["gas_in"])
    outlet = result.outlets["gas_out"]
    scale = max(abs(inlet.enthalpy * inlet.molar_flow), abs(outlet.enthalpy * outlet.molar_flow), 1.0)
    assert math.isclose(
        inlet.enthalpy * inlet.molar_flow + result.duty_W + result.power_W,
        outlet.enthalpy * outlet.molar_flow,
        rel_tol=1e-4,
        abs_tol=1e-4 * scale,
    )


def test_determinism_double_run(thermo: Thermo) -> None:
    first = _solve(thermo)
    second = _solve(thermo)
    assert second == first


# --- validation -------------------------------------------------------------


def test_rejects_liquid_inlet(thermo: Thermo) -> None:
    unit = registry.create("unit", "compression_train")
    feeds, params = unit.example_case()
    feeds["gas_in"]["T"] = 293.15  # the dry gas is two-phase here (vf ~ 0.99)
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="liquid"):
        unit.solve(inlets, params, thermo)


def test_rejects_eta_out_of_range(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="eta_isentropic"):
        _solve(thermo, {"P_discharge": 15.0e6, "eta_isentropic": 1.5})


def test_rejects_negative_interstage_temperature(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="T_interstage_out"):
        _solve(thermo, {"P_discharge": 15.0e6, "T_interstage_out": -1.0})
