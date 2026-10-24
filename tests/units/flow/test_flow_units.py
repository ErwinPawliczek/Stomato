"""Closed-form and refusal tests for the U-B flow adapters (plan §2 U-B)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.psv_gas import psv_api520_gas
from ngdesign.units.flow import (
    control_valve,
    ejector,
    fan,
    orifice,
    pipe_segment,
    reciprocating_compressor,
    relief_valve,
)
from tests.conftest import flash_feed

UNITS = [
    reciprocating_compressor.ReciprocatingCompressor,
    control_valve.ControlValve,
    relief_valve.ReliefValve,
    pipe_segment.PipeSegment,
    orifice.Orifice,
    ejector.Ejector,
    fan.Fan,
]


@pytest.mark.parametrize("cls", UNITS, ids=lambda c: c.__name__)
def test_example_case_solves(cls: type[Any], thermo: Thermo) -> None:
    """Every adapter solves its own example to a fully specified outlet."""
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.T > 0.0 and outlet.P > 0.0 and outlet.molar_flow > 0.0


def test_reciprocating_compressor_isentropic_stages(thermo: Thermo) -> None:
    """Two stages with intercooling beat one stage to the same discharge."""
    cls = reciprocating_compressor.ReciprocatingCompressor
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    two = cls().solve(inlets, params, thermo)
    assert two.info["pressure_ratio_per_stage"] == pytest.approx(
        (params["P_out"] / inlets["inlet"].P) ** 0.5, rel=1e-9
    )
    one = cls().solve(inlets, {**params, "n_stages": 1}, thermo)
    assert one.power_W > two.power_W > 0.0


def test_control_valve_isenthalpic(thermo: Thermo) -> None:
    """A letdown preserves enthalpy: the outlet state flashes at inlet h."""
    cls = control_valve.ControlValve
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.enthalpy == pytest.approx(inlets["inlet"].enthalpy, rel=1e-12)
    assert outlet.P == pytest.approx(params["P_out"], rel=1e-12)


def test_control_valve_reports_no_cv_for_vapor(thermo: Thermo) -> None:
    """A vapour letdown throttles isenthalpically and reports no liquid Cv."""
    cls = control_valve.ControlValve
    gas = {
        "T": 348.15,
        "P": 670170.408,
        "molar_flow": 130.128,
        "composition": {"C3": 0.45, "nC4": 0.55},
    }
    inlets = {"inlet": flash_feed(thermo, gas)}
    result = cls().solve(inlets, {"P_out": 3.0e5}, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.enthalpy == pytest.approx(inlets["inlet"].enthalpy, rel=1e-12)
    assert result.info["cv_reported"] == 0.0


def test_relief_valve_selects_api526_letter(thermo: Thermo) -> None:
    """The selected orifice area is the smallest API 526 area at or above the requirement."""
    cls = relief_valve.ReliefValve
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    required = result.info["required_area_in2"]
    selected = result.info["selected_orifice_area_in2"]
    assert selected >= required
    assert selected == pytest.approx(
        min(
            a * relief_valve.IN2_PER_M2
            for a in __import__("fluids").API526_A
            if a * relief_valve.IN2_PER_M2 >= required
        ),
        rel=1e-12,
    )


def test_relief_valve_refuses_oversized_requirement(thermo: Thermo) -> None:
    """A required area beyond the T orifice raises a typed spec error."""
    cls = relief_valve.ReliefValve
    feeds, params = cls.example_case()
    feeds = {port: {**feed, "molar_flow": feed["molar_flow"] * 10.0} for port, feed in feeds.items()}
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(relief_valve.ReliefValveSpecError, match="API 526"):
        cls().solve(inlets, params, thermo)


def test_pipe_segment_hydrostatic_head(thermo: Thermo) -> None:
    """Raising the elevation adds rho*g*z to the pressure the fixed dP consumed."""
    cls = pipe_segment.PipeSegment
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    inlet = inlets["inlet"]
    rho = max(inlet.phases, key=lambda p: p.mole_fraction).density
    up = cls().solve(inlets, {**params, "elevation_m": 100.0}, thermo)
    flat = cls().solve(inlets, {**params, "elevation_m": 0.0}, thermo)
    assert up.outlets["outlet"].P == pytest.approx(flat.outlets["outlet"].P - rho * 9.80665 * 100.0, rel=1e-9)


def test_pipe_segment_refuses_negative_outlet_pressure(thermo: Thermo) -> None:
    """A dP larger than the inlet pressure is a typed refusal, not a negative pressure."""
    cls = pipe_segment.PipeSegment
    feeds, params = cls.example_case()
    params = {**params, "dP": 5.0e6}
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(pipe_segment.PipeSegmentSpecError, match="must be > 0"):
        cls().solve(inlets, params, thermo)


def test_orifice_mass_balance(thermo: Thermo) -> None:
    """The orifice consumes its dP without changing the stream's mass or enthalpy."""
    cls = orifice.Orifice
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    inlet, outlet = inlets["inlet"], result.outlets["outlet"]
    assert outlet.molar_flow == pytest.approx(inlet.molar_flow, rel=1e-12)
    assert outlet.enthalpy == pytest.approx(inlet.enthalpy, rel=1e-12)


def test_ejector_discharge_pressure(thermo: Thermo) -> None:
    """At the required entrainment the momentum balance lands exactly on P_out."""
    cls = ejector.Ejector
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    motive, suction = inlets["motive"], inlets["suction"]
    assert result.info["motive_to_suction_required"] == pytest.approx(
        motive.mass_flow / suction.mass_flow, rel=1e-4
    )
    assert result.outlets["outlet"].P == pytest.approx(params["P_out"], rel=1e-9)


def test_psv_api520_gas_api520_example() -> None:
    """Pins the sizing layer to the API 520 gas example's printed inputs and area.

    Basis: API RP 520 Part I Example 3.6.2.2, p. 44 (2000-edition numbering) —
    W = 53500 lb/h, T = 627 R, P1 = 97.2 psia, M = 65, Z = 0.84, k = 1.09,
    Kd = 0.975, Kb = Kc = 1.0 (critical flow, no rupture disk), C = 326
    (Table 8); the published required area is 3179 mm2 = 4.93 in2. Inputs and
    the published result are read from FluidFlow's results-verified
    reproduction ("Sizing Pressure Relief Valves", webinar deck and Case 3.9).
    The exact-C correlation lands within 0.2 percent of the print.
    """
    result = psv_api520_gas(
        W_lb_h=53500.0,
        T_R=627.0,
        Z=0.84,
        M=65.0,
        k=1.09,
        P1_psia=97.2,
        Kd=0.975,
        Kb=1.0,
        Kc=1.0,
    )
    assert result["C"] == pytest.approx(326.0, rel=0.002)
    # printed 3179 mm2 (4.928 in2); the exact C gives +0.14 %
    assert result["area_in2"] == pytest.approx(3179.0 / 645.16, rel=0.002)


def test_control_valve_refuses_pressure_rise(thermo: Thermo) -> None:
    """P_out above the inlet pressure is a typed refusal, not an invented pressure gain."""
    cls = control_valve.ControlValve
    feeds, _ = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(control_valve.ControlValveSpecError, match="cannot raise pressure"):
        cls().solve(inlets, {"P_out": inlets["inlet"].P * 2.0}, thermo)


def test_control_valve_skips_cv_at_zero_drop(thermo: Thermo) -> None:
    """A zero-dP spec solves isenthalpically but reports no Cv (nothing to size)."""
    cls = control_valve.ControlValve
    feeds, _ = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    inlet = inlets["inlet"]
    result = cls().solve(inlets, {"P_out": inlet.P}, thermo)
    assert result.info["cv_reported"] == 0.0
    assert result.outlets["outlet"].P == pytest.approx(inlet.P, rel=1e-12)
    assert result.outlets["outlet"].enthalpy == pytest.approx(inlet.enthalpy, rel=1e-12)


def test_orifice_outlet_at_permanent_loss(thermo: Thermo) -> None:
    """The outlet flashes at P1 - delta_varpi, below the tap differential dP.

    Closed form at the example's beta = 0.5, C = 0.61: the ISO 5167-2
    permanent-loss ratio is 0.7307, independent of the flowing state.
    """
    cls = orifice.Orifice
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    ratio = result.info["permanent_loss_Pa"] / result.info["dP_Pa"]
    assert ratio == pytest.approx(0.7307, rel=1e-3)
    assert result.info["permanent_loss_Pa"] < result.info["dP_Pa"]
    assert result.outlets["outlet"].P == pytest.approx(
        inlets["inlet"].P - result.info["permanent_loss_Pa"], rel=1e-9
    )


def test_orifice_refuses_liquid_inlet_without_dense_phase(thermo: Thermo) -> None:
    """A non-gas inlet carrying only a vapour phase is refused, not a TypeError."""
    gas_feed = {
        "T": 348.15,
        "P": 670170.408,
        "molar_flow": 130.128,
        "composition": {"C3": 0.45, "nC4": 0.55},
    }
    inlet = flash_feed(thermo, gas_feed)
    assert inlet.vapor_fraction > 0.999  # the flash reports a single vapour phase
    mislabelled = inlet.model_copy(update={"vapor_fraction": 0.5})
    _, params = orifice.Orifice.example_case()
    with pytest.raises(orifice.OrificeSpecError, match="no dense phase"):
        orifice.Orifice().solve({"inlet": mislabelled}, params, thermo)


def test_ejector_refuses_outlet_pressure_outside_band(thermo: Thermo) -> None:
    """A discharge above the motive or below the suction pressure is a typed refusal."""
    cls = ejector.Ejector
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    motive, suction = inlets["motive"], inlets["suction"]
    with pytest.raises(ejector.EjectorSpecError, match="above the motive pressure"):
        cls().solve(inlets, {**params, "P_out": motive.P * 2.0}, thermo)
    with pytest.raises(ejector.EjectorSpecError, match="below the suction pressure"):
        cls().solve(inlets, {**params, "P_out": suction.P / 2.0}, thermo)


def test_ejector_reports_entrainment_spec_met(thermo: Thermo) -> None:
    """The example's rounded flows land on the specified entrainment within 1e-5."""
    cls = ejector.Ejector
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    assert result.info["entrainment_spec_met"] == 1.0


def test_reciprocating_compressor_refuses_two_phase_stage_suction(thermo: Thermo) -> None:
    """Intercooling that condenses liquid into the next stage's suction is refused, naming the stage."""
    feed = {
        "T": 300.0,
        "P": 1.0e6,
        "molar_flow": 10.0,
        "composition": {"C2": 0.5, "C3": 0.5},
    }
    inlet = flash_feed(thermo, feed)
    assert inlet.vapor_fraction > 0.999  # single-phase at the machine inlet
    params = {"P_out": 3.0e6, "efficiency": 0.75, "n_stages": 2, "T_intercool": 290.0}
    with pytest.raises(reciprocating_compressor.ReciprocatingCompressorSpecError, match="stage 2"):
        reciprocating_compressor.ReciprocatingCompressor().solve({"inlet": inlet}, params, thermo)


def test_fan_power_positive_on_pressure_rise(thermo: Thermo) -> None:
    """A fan raising dP consumes shaft power; a looser efficiency consumes more."""
    cls = fan.Fan
    feeds, params = cls.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = cls().solve(inlets, params, thermo)
    inlet = inlets["inlet"]
    assert result.power_W > 0.0
    assert result.duty_W == 0.0
    assert result.info["pressure_ratio"] == pytest.approx((inlet.P + params["dP"]) / inlet.P, rel=1e-9)
    assert result.outlets["outlet"].P == pytest.approx(inlet.P + params["dP"], rel=1e-9)
    ideal = cls().solve(inlets, {**params, "eta": 1.0}, thermo)
    assert ideal.power_W < result.power_W
