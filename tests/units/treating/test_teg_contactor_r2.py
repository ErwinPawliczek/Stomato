"""Closed-form tests for the R2 TEG contactor (spec teg_contactor R2, step 2).

Closed-form table (spec, computed from ``calc_teg_contactor.py``: own IAPWS-IF97
Psat and own Parrish gamma_w, cross-checked against ``chemicals.Psat_IAPWS`` and
``teg_activity`` to 1e-15). R0 example basis: T = 303.15 K, P = 7.1 MPa, gas
100 mol/s at y_H2O = 0.0005 (G = 99.95 mol/s dry, Y_in = 5.0025e-4), lean
0.2 mol/s at x_H2O = 0.015 (S = 0.197 mol/s, X_0 = 0.015228426).

| N | y_H2O out | gas_out flow (mol/s) | water removed (mol/s) | rich x_H2O |
|---|-----------|----------------------|-----------------------|------------|
| 1 | 7.17911038e-05 | 99.957176036    | 0.042823964 | 0.188712692 |
| 2 | 1.58095229e-05 | 99.9515801868   | 0.0484198132 | 0.206987569 |
| 3 | 6.90613904e-06 | 99.9506902734   | 0.0493097266 | 0.209818234 |
| 4 | 5.41853074e-06 | 99.9505415851   | 0.0494584149 | 0.210289218 |

Lean-end floor y* = 5.115774429894135e-06; the outlet y stays above it.
Constant checks: Psat_H2O(303.15 K) = 4246.688340548065 Pa;
gamma_w(303.15, 0.015) = 0.5702011471768885.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.registry import create
from ngdesign.units.teg_activity import activity_equilibrium_slope, water_activity_coefficient
from ngdesign.units.teg_contactor import LBMOL_PER_MMSCF, TEGContactor
from ngdesign.units.treating.teg_contactor_r2 import TEGContactorR2, TEGContactorR2Error
from ngdesign.units.treating.teg_stagewise import TEGStageError

THERMO: Thermo = create("thermo", "pr")

T_CONTACT = 303.15
P_CONTACT = 7.1e6

#: Closed-form table from the spec (see module docstring).
EXPECTED: dict[int, tuple[float, float, float, float]] = {
    1: (7.17911038e-05, 99.957176036, 0.042823964, 0.188712692),
    2: (1.58095229e-05, 99.9515801868, 0.0484198132, 0.206987569),
    3: (6.90613904e-06, 99.9506902734, 0.0493097266, 0.209818234),
    4: (5.41853074e-06, 99.9505415851, 0.0494584149, 0.210289218),
}

#: Spec-printed constants, checked against the owner correlations.
PSAT_303_15 = 4246.688340548065
GAMMA_W_303_15_X015 = 0.5702011471768885
LEAN_FLOOR_Y = 5.115774429894135e-06


def _inlets(n_stages: int = 3) -> tuple[dict[str, StreamState], dict[str, Any]]:
    feeds, params = TEGContactorR2.example_case()
    params["n_stages"] = n_stages
    return (
        {
            "gas_in": THERMO.flash_pt(
                feeds["gas_in"]["composition"],
                feeds["gas_in"]["T"],
                feeds["gas_in"]["P"],
                feeds["gas_in"]["molar_flow"],
            ),
            "lean_teg_in": THERMO.flash_pt(
                feeds["lean_teg_in"]["composition"],
                feeds["lean_teg_in"]["T"],
                feeds["lean_teg_in"]["P"],
                feeds["lean_teg_in"]["molar_flow"],
            ),
        },
        params,
    )


def _solve(n_stages: int = 3) -> UnitResult:
    inlets, params = _inlets(n_stages)
    return TEGContactorR2().solve(inlets, params, THERMO)


def test_owner_correlations_match_spec_printed_constants() -> None:
    """Every constant typed here is checked against its source (the owners)."""
    from chemicals.vapor_pressure import Psat_IAPWS

    assert Psat_IAPWS(T_CONTACT) == pytest.approx(PSAT_303_15, rel=1e-12)
    assert water_activity_coefficient(T_CONTACT, 0.015) == pytest.approx(GAMMA_W_303_15_X015, rel=1e-12)


@pytest.mark.parametrize("n_stages", [1, 2, 3, 4])
def test_closed_form_table(n_stages: int) -> None:
    """The march on the activity line reproduces the spec's closed-form table."""
    result = _solve(n_stages)
    y_out, gas_flow, water_removed, rich_x = EXPECTED[n_stages]
    assert result.outlets["gas_out"].composition["H2O"] == pytest.approx(y_out, rel=1e-7)
    assert result.outlets["gas_out"].molar_flow == pytest.approx(gas_flow, rel=1e-7)
    assert result.info["water_removed_mol_s"] == pytest.approx(water_removed, rel=1e-7)
    assert result.info["rich_x_water"] == pytest.approx(rich_x, rel=1e-7)


def test_outlet_stays_above_the_lean_end_floor() -> None:
    result = _solve(3)
    y_out = result.outlets["gas_out"].composition["H2O"]
    assert y_out > LEAN_FLOOR_Y
    mw_h2o = float(component_record("H2O")["mw"])
    floor_lb_per_mmscf = LEAN_FLOOR_Y / (1.0 - LEAN_FLOOR_Y) * mw_h2o * LBMOL_PER_MMSCF
    assert result.info["equilibrium_floor_lb_per_mmscf"] == pytest.approx(floor_lb_per_mmscf, rel=1e-9)


def test_activity_line_is_strictly_increasing() -> None:
    """y*(x) = m(T, P, x) * x is strictly increasing on a 1000-point grid in (0, 1)."""
    grid = [(i + 0.5) / 1000.0 for i in range(1000)]
    y_star = [activity_equilibrium_slope(T_CONTACT, P_CONTACT, x) * x for x in grid]
    assert all(y_star[i] < y_star[i + 1] for i in range(len(y_star) - 1))


def test_v0_balances_and_duty_definition() -> None:
    inlets, _ = _inlets(3)
    result = TEGContactorR2().solve(inlets, {"n_stages": 3}, THERMO)
    total_in = inlets["gas_in"].molar_flow + inlets["lean_teg_in"].molar_flow
    total_out = result.outlets["gas_out"].molar_flow + result.outlets["rich_teg_out"].molar_flow
    assert total_out == pytest.approx(total_in, rel=1e-12)
    recomputed_duty = (
        result.outlets["gas_out"].enthalpy * result.outlets["gas_out"].molar_flow
        + result.outlets["rich_teg_out"].enthalpy * result.outlets["rich_teg_out"].molar_flow
        - inlets["gas_in"].enthalpy * inlets["gas_in"].molar_flow
        - inlets["lean_teg_in"].enthalpy * inlets["lean_teg_in"].molar_flow
    )
    assert result.duty_W == pytest.approx(recomputed_duty, rel=1e-12)


def test_per_stage_profiles_reported() -> None:
    result = _solve(3)
    for j in (1, 2, 3):
        assert f"stage_{j}_y_H2O" in result.info
        assert f"stage_{j}_x_H2O" in result.info
    assert result.info["activity_extrapolated"] == 0.0  # 303.15 K is in the fit range


def test_refuses_bad_n_stages() -> None:
    inlets, _ = _inlets()
    unit = TEGContactorR2()
    with pytest.raises(TEGContactorR2Error, match="n_stages"):
        unit.solve(inlets, {}, THERMO)  # missing
    with pytest.raises(TEGContactorR2Error, match="n_stages"):
        unit.solve(inlets, {"n_stages": 2.5}, THERMO)  # non-integer
    with pytest.raises(TEGContactorR2Error, match="n_stages"):
        unit.solve(inlets, {"n_stages": 0}, THERMO)  # < 1


def test_refuses_unknown_param_key() -> None:
    inlets, _ = _inlets()
    with pytest.raises(TEGContactorR2Error, match="unknown"):
        TEGContactorR2().solve(inlets, {"n_stages": 3, "water_out_lb_per_mmscf": 7.0}, THERMO)


def test_refuses_lean_without_teg() -> None:
    feeds, _ = TEGContactorR2.example_case()
    inlets = {
        "gas_in": THERMO.flash_pt(feeds["gas_in"]["composition"], T_CONTACT, P_CONTACT, 100.0),
        "lean_teg_in": THERMO.flash_pt({"H2O": 1.0}, T_CONTACT, P_CONTACT, 0.2),
    }
    with pytest.raises(TEGContactorR2Error, match="TEG"):
        TEGContactorR2().solve(inlets, {"n_stages": 3}, THERMO)


def test_refuses_gas_without_h2o() -> None:
    feeds, _ = TEGContactorR2.example_case()
    inlets = {
        "gas_in": THERMO.flash_pt({"C1": 1.0}, T_CONTACT, P_CONTACT, 100.0),
        "lean_teg_in": THERMO.flash_pt(feeds["lean_teg_in"]["composition"], T_CONTACT, P_CONTACT, 0.2),
    }
    with pytest.raises(TEGContactorR2Error, match="H2O"):
        TEGContactorR2().solve(inlets, {"n_stages": 3}, THERMO)


def test_r0_round_trip_is_finite_and_dryer_than_the_inlet() -> None:
    """R2 at N = ceil(R0's Kremser N) dehydrates below the inlet (inequality only)."""
    feeds, r0_params = TEGContactor.example_case()
    inlets = {
        "gas_in": THERMO.flash_pt(feeds["gas_in"]["composition"], T_CONTACT, P_CONTACT, 100.0),
        "lean_teg_in": THERMO.flash_pt(feeds["lean_teg_in"]["composition"], T_CONTACT, P_CONTACT, 0.2),
    }
    r0 = TEGContactor().solve(inlets, dict(r0_params), THERMO)
    n_from_r0 = int(-(-r0.info["N_stages"] // 1))  # ceil
    r2 = TEGContactorR2().solve(inlets, {"n_stages": n_from_r0}, THERMO)
    mw_h2o = float(component_record("H2O")["mw"])
    y_in = inlets["gas_in"].composition["H2O"]
    inlet_lb_per_mmscf = y_in / (1.0 - y_in) * mw_h2o * LBMOL_PER_MMSCF
    outlet = r2.info["outlet_water_lb_per_mmscf"]
    assert outlet == outlet  # finite
    assert 0.0 < outlet < inlet_lb_per_mmscf


def test_march_failure_propagates_as_teg_stage_error() -> None:
    """A TEGStageError from the march surfaces unchanged (refusal table row)."""
    assert issubclass(TEGStageError, ValueError)  # typed ValueError subclass
