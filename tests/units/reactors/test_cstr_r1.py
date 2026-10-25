"""Closed-form tests for the kinetic CSTR, level R1 (units/cstr.md, tests).

R1-A — isothermal first order, gas (through the adapter, against the hand
solution): nC4 -> iC4, k0 = 1.0e3 1/s, Ea = 5.0e4 J/mol, feed pure nC4 at
1.0 mol/s, 500 K, 2.0e5 Pa, V = 2.0 m3. Constant T and total flow (delta n
= 0), so y_nC4,out = 1 - X and the CSTR design equation gives

    Da = k(T)·V·c_tot/F_A0 = 0.575299226,  X = Da/(1 + Da) = 0.365199967,

with k(500 K) = k0·exp(-Ea/(R·500 K)) and c_tot = P/(R·T) = 48.11 mol/m3.
Expected F_nC4 = 0.634800033 mol/s. Tolerance 1e-9 relative.

R1-B — isothermal second order with delta n != 0: 2 C2H4 -> 1-butene, base
C2H4 (nu = -2), k0 = 5.0e-3 m3/(mol s), Ea = 0, order 2 in C2H4,
concentration basis. Feed pure C2H4 at 1.0 mol/s, 600 K, 5.0e5 Pa, V = 0.5
m3 (units/cstr.md, tests). Component ids per the orchestrator's ruling on
the SPEC ISSUE: `ethylene` and `1-butene` resolve in the databank
(ngdesign.data.component_record) with formation data, so the energy closure
runs. The hand equation is 2·xi = V·k·(y_A·P/(R·T))^2 with
y_A = (F0 - 2·xi)/(F0 - xi), solved independently by brentq. Expected
c_tot = P/(R·T) = 100.226963 mol/m3, xi = 0.447862522 mol/s
(X = 0.895725045), F_C2H4 = 0.104274955, F_1-butene = 0.447862522.
Tolerance 1e-9 relative.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from scipy.optimize import brentq

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R, enthalpy_with_formation
from ngdesign.units.reactors.cstr import (
    CstrConvergenceError,
    CstrError,
    CstrPhaseError,
    CstrR1,
)
from tests.conftest import flash_feed


def _isom_params(volume_m3: float = 2.0, **overrides: Any) -> dict[str, Any]:
    """The R1-A parameter set: first-order nC4 -> iC4, concentration basis."""
    params: dict[str, Any] = {
        "reaction_set": {
            "id": "cstr_isom_case",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "n-butane isomerization, first-order gas-phase lump "
                    "(Fogler, Elements of CRE, 4th ed., CSTR design equation)",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 1.0e3,
                        "Ea": 5.0e4,
                        "orders": {"nC4": 1.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "volume_m3": volume_m3,
        "thermal": "isothermal",
    }
    params.update(overrides)
    return params


def test_r1a_isothermal_first_order_closed_form(thermo: Thermo) -> None:
    """R1-A: the adapter reproduces Da/(1 + Da) to 1e-9 relative."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    unit = CstrR1()
    result = unit.solve({"inlet": inlet}, _isom_params(), thermo)

    k = 1.0e3 * math.exp(-5.0e4 / (R * 500.0))
    c_tot = 2.0e5 / (R * 500.0)
    da = k * 2.0 * c_tot / 1.0
    x_expected = da / (1.0 + da)
    # The spec's printed digits carry their own rounding (9 decimals): the
    # exact X is 0.36519996748..., printed as 0.365199967.
    assert math.isclose(x_expected, 0.365199967, abs_tol=5e-10)

    n_out = result.outlets["outlet"].component_flows()
    assert math.isclose(n_out["nC4"], 1.0 - x_expected, rel_tol=1e-9)
    assert math.isclose(n_out["iC4"], x_expected, rel_tol=1e-9)
    assert math.isclose(n_out["nC4"], 0.634800033, abs_tol=5e-10)
    assert math.isclose(n_out["iC4"], 0.365199967, abs_tol=5e-10)
    assert math.isclose(result.info["conversion_nC4_isom"], x_expected, rel_tol=1e-9)
    assert math.isclose(result.info["extent_isom_mol_s"], x_expected, rel_tol=1e-9)
    # Isothermal: the outlet stays at the inlet temperature and the closure gap is 0.
    assert result.outlets["outlet"].T == pytest.approx(500.0, rel=1e-12)
    assert abs(result.info["T_closure_gap_K"]) < 1e-9
    # The isothermal duty carries the reaction heat (exothermic: removed).
    assert result.duty_W < 0.0


def _dimer_params(volume_m3: float = 0.5, **overrides: Any) -> dict[str, Any]:
    """The R1-B parameter set: second-order 2 C2H4 -> 1-butene, delta n != 0."""
    params: dict[str, Any] = {
        "reaction_set": {
            "id": "cstr_dimer_case",
            "components": ["ethylene", "1-butene"],
            "reactions": [
                {
                    "id": "dimer",
                    "stoichiometry": {"ethylene": -2.0, "1-butene": 1.0},
                    "base_component": "ethylene",
                    "provenance": "ethylene dimerization to 1-butene, second-order "
                    "gas-phase lump (units/cstr.md closed-form case R1-B)",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 5.0e-3,
                        "Ea": 0.0,
                        "orders": {"ethylene": 2.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "volume_m3": volume_m3,
        "thermal": "isothermal",
    }
    params.update(overrides)
    return params


def _r1b_hand_extents() -> tuple[float, float]:
    """The hand solution of 2·xi = V·k·(y_A·P/(R·T))^2 by brentq.

    Returns (xi, c_tot) with c_tot = P/(R·T); y_A = (F0 - 2·xi)/(F0 - xi).
    """

    def f(xi: float) -> float:
        y_a = (1.0 - 2.0 * xi) / (1.0 - xi)
        return 2.0 * xi - 0.5 * 5.0e-3 * (y_a * 5.0e5 / (R * 600.0)) ** 2

    c_tot = 5.0e5 / (R * 600.0)
    return float(brentq(f, 1e-6, 0.499)), c_tot


def test_r1b_isothermal_second_order_delta_n_closed_form(thermo: Thermo) -> None:
    """R1-B: the adapter reproduces the brentq hand solution to 1e-9 relative."""
    feed = {"T": 600.0, "P": 5.0e5, "molar_flow": 1.0, "composition": {"ethylene": 1.0}}
    inlet = flash_feed(thermo, feed)

    result = CstrR1().solve({"inlet": inlet}, _dimer_params(), thermo)
    outlet = result.outlets["outlet"]

    xi_hand, c_tot = _r1b_hand_extents()
    # The spec's printed digits carry their own rounding (9 decimals):
    # c_tot = 100.226963 mol/m3, xi = 0.447862522 mol/s, X = 0.895725045.
    assert math.isclose(c_tot, 100.226963, abs_tol=5e-7)
    assert math.isclose(xi_hand, 0.447862522, abs_tol=5e-10)

    n_out = outlet.component_flows()
    assert math.isclose(result.info["extent_dimer_mol_s"], xi_hand, rel_tol=1e-9)
    assert math.isclose(result.info["conversion_ethylene_dimer"], 2.0 * xi_hand, rel_tol=1e-9)
    assert math.isclose(n_out["ethylene"], 1.0 - 2.0 * xi_hand, rel_tol=1e-9)
    assert math.isclose(n_out["ethylene"], 0.104274955, abs_tol=5e-10)
    assert math.isclose(n_out["1-butene"], xi_hand, rel_tol=1e-9)
    assert math.isclose(n_out["1-butene"], 0.447862522, abs_tol=5e-10)
    # Isothermal: the outlet stays at the inlet temperature; single-phase vapour.
    assert outlet.T == pytest.approx(600.0, rel=1e-12)
    assert outlet.vapor_fraction == pytest.approx(1.0)
    assert abs(result.info["T_closure_gap_K"]) < 1e-9


# --- Step 2: adapter behaviours and refusals -------------------------------


def test_r1_k0_zero_identity(thermo: Thermo) -> None:
    """k0 = 0 kills the rate: the outlet is the inlet re-flashed, duty ~ 0."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)
    params = _isom_params()
    params["reaction_set"]["reactions"][0]["kinetics"]["k0"] = 0.0

    result = CstrR1().solve({"inlet": inlet}, params, thermo)

    n_out = result.outlets["outlet"].component_flows()
    assert math.isclose(n_out["nC4"], 1.0, rel_tol=1e-12)
    assert n_out.get("iC4", 0.0) == pytest.approx(0.0, abs=1e-12)
    assert result.duty_W == pytest.approx(0.0, abs=1e-9)
    assert result.outlets["outlet"].T == pytest.approx(500.0, rel=1e-12)


def test_r1_adiabatic_energy_closure(thermo: Thermo) -> None:
    """Adiabatic: V0 closes at 1e-8 and the Newton/closure temperatures agree."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    result = CstrR1().solve({"inlet": inlet}, _isom_params(thermal="adiabatic"), thermo)
    outlet = result.outlets["outlet"]

    h_in = enthalpy_with_formation(inlet)
    h_out = enthalpy_with_formation(outlet)
    assert h_in + result.duty_W == pytest.approx(h_out, rel=1e-8)  # duty 0, adiabatic
    assert abs(result.info["T_closure_gap_K"]) < 1e-6
    # The isomerization is exothermic: the adiabatic outlet heats up.
    assert outlet.T > 500.0
    assert 0.0 < result.info["conversion_nC4_isom"] < 1.0


def test_r1_duty_zero_matches_adiabatic(thermo: Thermo) -> None:
    """{'duty_W': 0.0} is the same physics as 'adiabatic'."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    adiabatic = CstrR1().solve({"inlet": inlet}, _isom_params(thermal="adiabatic"), thermo)
    zero_duty = CstrR1().solve({"inlet": inlet}, _isom_params(thermal={"duty_W": 0.0}), thermo)

    assert zero_duty.outlets["outlet"].T == pytest.approx(adiabatic.outlets["outlet"].T, rel=1e-9)


def test_r1_fixed_outlet_temperature(thermo: Thermo) -> None:
    """{'T_out': 520.0} pins the outlet temperature and the Newton solution."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    result = CstrR1().solve({"inlet": inlet}, _isom_params(thermal={"T_out": 520.0}), thermo)

    assert result.outlets["outlet"].T == pytest.approx(520.0, rel=1e-12)
    assert result.info["T_newton_K"] == pytest.approx(520.0, rel=1e-12)
    assert abs(result.info["T_closure_gap_K"]) < 1e-9
    # Hotter than the 500 K isothermal case: conversion rises (Arrhenius).
    assert result.info["conversion_nC4_isom"] > 0.365199967


def test_r1_liquid_phase_p_eff_hand_value(thermo: Thermo) -> None:
    """Liquid reaction: P_eff = P − P_vap(z,T) = P (single liquid), and the
    concentration c = x·c_tot with c_tot = 1000·ρ_liq/MW_liq reproduces the
    hand solution X = Da/(1+Da), Da = k(T)·V·c_tot/F_A0."""
    feed = {"T": 300.0, "P": 3.0e6, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    result = CstrR1().solve({"inlet": inlet}, _isom_params(reacting_phase="liquid"), thermo)
    outlet = result.outlets["outlet"]
    liquid = [p for p in outlet.phases if p.kind != "vapor"][0]

    k = 1.0e3 * math.exp(-5.0e4 / (R * 300.0))
    c_tot = 1000.0 * liquid.density / liquid.molecular_weight
    da = k * 2.0 * c_tot / 1.0
    assert math.isclose(result.info["conversion_nC4_isom"], da / (1.0 + da), rel_tol=1e-9)


def test_r1_two_phase_vessel_refusal(thermo: Thermo) -> None:
    """A feed that condenses in the vessel is refused at level R1."""
    feed = {"T": 300.0, "P": 1.0e6, "molar_flow": 2.0, "composition": {"C1": 0.5, "nC4": 0.5}}
    inlet = flash_feed(thermo, feed)

    with pytest.raises(CstrPhaseError, match="use level R2") as excinfo:
        CstrR1().solve({"inlet": inlet}, _isom_params(), thermo)
    assert "T = 300" in str(excinfo.value) and "1000000.0" in str(excinfo.value)


def test_r1_liquid_mode_vapor_refusal(thermo: Thermo) -> None:
    """reacting_phase='liquid' refuses a fully vaporized vessel."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    with pytest.raises(CstrPhaseError, match="use level R2"):
        CstrR1().solve({"inlet": inlet}, _isom_params(reacting_phase="liquid"), thermo)


def test_r1_refusals(thermo: Thermo) -> None:
    """The refusal table's first five rows, one case each."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)
    unit = CstrR1()

    with pytest.raises(CstrError, match="volume_m3"):
        unit.solve({"inlet": inlet}, _isom_params(volume_m3=-1.0), thermo)
    with pytest.raises(CstrError, match="volume_m3"):
        unit.solve({"inlet": inlet}, _isom_params(volume_m3=0.0), thermo)

    bad_units = _isom_params()
    bad_units["reaction_set"]["reactions"][0]["kinetics"]["rate_units"] = "mol/(kg_cat·s)"
    with pytest.raises(CstrError, match="rate_units"):
        unit.solve({"inlet": inlet}, bad_units, thermo)

    no_bulk = _isom_params()
    no_bulk["reaction_set"]["reactions"][0]["kinetics"]["rate_units"] = "mol/(kg_cat·s)"
    with pytest.raises(CstrError, match="bulk_density_kg_m3"):
        unit.solve({"inlet": inlet}, no_bulk, thermo)

    no_kin = _isom_params()
    del no_kin["reaction_set"]["reactions"][0]["kinetics"]
    with pytest.raises(CstrError, match="has no kinetics"):
        unit.solve({"inlet": inlet}, no_kin, thermo)

    equil = _isom_params()
    equil["reaction_set"]["reactions"][0]["equilibrium"] = {"form": "from_gibbs"}
    with pytest.raises(CstrError, match="explicit reverse"):
        unit.solve({"inlet": inlet}, equil, thermo)

    with pytest.raises(ValueError, match="thermal mode"):
        unit.solve({"inlet": inlet}, _isom_params(thermal="geothermal"), thermo)

    with pytest.raises(CstrError, match="reacting_phase"):
        unit.solve({"inlet": inlet}, _isom_params(reacting_phase="plasma"), thermo)


def test_r1_newton_cap_refusal(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """The iteration cap: CstrConvergenceError naming the iteration count."""
    monkeypatch.setattr("ngdesign.units.reactors.cstr._MAX_ITERATIONS", 2)
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    with pytest.raises(CstrConvergenceError, match="did not converge in 2 Newton iterations"):
        CstrR1().solve({"inlet": inlet}, _isom_params(thermal="adiabatic"), thermo)


def test_r1_singular_jacobian_refusal(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """A singular Newton Jacobian is translated: LinAlgError becomes a
    CstrConvergenceError naming the Jacobian (units/cstr.md step 4)."""
    import numpy as np

    def _singular(*_args: object, **_kwargs: object) -> None:
        raise np.linalg.LinAlgError("Singular matrix")

    monkeypatch.setattr(np.linalg, "solve", _singular)
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    with pytest.raises(CstrConvergenceError, match="singular"):
        CstrR1().solve({"inlet": inlet}, _isom_params(), thermo)


def test_r1_example_case_roundtrip(thermo: Thermo) -> None:
    """example_case feeds and params solve and report the documented keys."""
    feeds, params = CstrR1.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])

    result = CstrR1().solve({"inlet": inlet}, params, thermo)

    for key in (
        "extent_isom_mol_s",
        "conversion_nC4_isom",
        "newton_iterations",
        "T_newton_K",
        "T_closure_gap_K",
    ):
        assert key in result.info
