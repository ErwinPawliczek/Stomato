"""Closed-form tests for the R0 TEG regenerator (spec U-G)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import component_record
from ngdesign.registry import create
from ngdesign.units.teg_activity import activity_equilibrium_slope
from ngdesign.units.treating.teg_regen import DEFAULT_P, DEFAULT_T_REBOILER, TEGRegen, TEGRegenError

THERMO: Thermo = create("thermo", "pr")
PARAMS: dict[str, Any] = {"T_reboiler": DEFAULT_T_REBOILER, "P": DEFAULT_P}


def _feed(
    composition: dict[str, float], T: float = 422.15, P: float = 1.5e5, molar_flow: float = 100.0
) -> StreamState:
    return THERMO.flash_pt(composition, T, P, molar_flow)


def _solve(feed: StreamState, params: dict[str, Any] | None = None) -> UnitResult:
    return TEGRegen().solve({"rich_in": feed}, params or dict(PARAMS), THERMO)


def test_lean_water_mole_fraction_sits_on_the_boiling_line() -> None:
    """At the solved purity the owner's equilibrium condition holds exactly:
    the overhead water is saturated (gamma_w * x_w * Psat = P)."""
    result = _solve(_feed({"TEG": 0.95, "H2O": 0.05}))
    x_w = result.info["lean_water_mole_fraction"]
    slope_x = activity_equilibrium_slope(DEFAULT_T_REBOILER, DEFAULT_P, x_w) * x_w
    assert slope_x == pytest.approx(1.0, abs=1e-10)


def test_water_split_matches_the_closed_form() -> None:
    """n_water_lean = n_TEG * x_w / (1 - x_w); the rest leaves overhead."""
    feed = _feed({"TEG": 0.85, "H2O": 0.15})  # wetter than the cap
    result = _solve(feed)
    n_teg = 85.0
    x_w = result.info["lean_water_mole_fraction"]
    expected_lean_water = n_teg * x_w / (1.0 - x_w)
    assert result.info["water_held_in_lean_mol_s"] == pytest.approx(expected_lean_water, abs=1e-9)
    assert result.info["water_stripped_mol_s"] == pytest.approx(15.0 - expected_lean_water, abs=1e-9)
    assert result.outlets["lean_out"].molar_flow == pytest.approx(n_teg + expected_lean_water, abs=1e-9)
    assert result.outlets["water_out"].molar_flow == pytest.approx(15.0 - expected_lean_water, abs=1e-9)


def test_lean_mass_fraction_matches_the_hand_formula() -> None:
    """wt% TEG = n_TEG * MW_TEG / (n_TEG * MW_TEG + n_water_lean * MW_H2O)."""
    result = _solve(_feed({"TEG": 0.85, "H2O": 0.15}))
    n_teg = 85.0
    n_water = result.info["water_held_in_lean_mol_s"]
    mw_teg = float(component_record("TEG")["mw"])
    mw_water = float(component_record("H2O")["mw"])
    expected = n_teg * mw_teg / (n_teg * mw_teg + n_water * mw_water)
    assert result.info["lean_teg_mass_fraction"] == pytest.approx(expected, abs=1e-9)


def test_absorbed_light_components_leave_entirely_overhead() -> None:
    """Every mole of C1 and CO2 in the rich feed reaches the overhead port."""
    feed = _feed({"TEG": 0.93, "H2O": 0.06, "C1": 0.008, "CO2": 0.002})
    result = _solve(feed)
    overhead_flows = {
        cid: frac * result.outlets["water_out"].molar_flow
        for cid, frac in result.outlets["water_out"].composition.items()
    }
    assert overhead_flows["C1"] == pytest.approx(0.8, abs=1e-12)
    assert overhead_flows["CO2"] == pytest.approx(0.2, abs=1e-12)
    lean = result.outlets["lean_out"]
    assert "C1" not in lean.composition and "CO2" not in lean.composition


def test_positive_stripping_gas_is_refused_not_ignored() -> None:
    """The GPSA Fig. 20-x enhancement is not citable at R0: typed refusal."""
    feed = _feed({"TEG": 0.95, "H2O": 0.05})
    gas = THERMO.flash_pt({"N2": 1.0}, 422.15, 1.5e5, 5.0)
    with pytest.raises(TEGRegenError, match="stripping_gas_in"):
        TEGRegen().solve({"rich_in": feed, "stripping_gas_in": gas}, dict(PARAMS), THERMO)


def test_pressure_above_water_saturation_is_refused() -> None:
    """A reboiler that cannot boil water regenerates nothing: typed refusal
    naming the pressure."""
    feed = _feed({"TEG": 0.95, "H2O": 0.05})
    with pytest.raises(TEGRegenError, match="saturation pressure"):
        _solve(feed, {"T_reboiler": 477.15, "P": 3.0e6})


def test_feed_drier_than_the_equilibrium_purity_keeps_its_water() -> None:
    """The boiling line is a purity cap: a feed drier than the equilibrium
    water content cannot boil water, so the lean carries every mole of feed
    water and nothing but lights strips."""
    feed = _feed({"TEG": 0.95, "H2O": 0.05})  # x_w 0.05 sits below the cap
    result = _solve(feed)
    assert result.info["water_stripped_mol_s"] == pytest.approx(0.0, abs=1e-12)
    assert result.outlets["lean_out"].molar_flow == pytest.approx(100.0, abs=1e-9)
    overhead_flows = {
        cid: frac * result.outlets["water_out"].molar_flow
        for cid, frac in result.outlets["water_out"].composition.items()
    }
    assert overhead_flows.get("H2O", 0.0) == pytest.approx(0.0, abs=1e-12)


def test_pure_teg_feed_is_refused() -> None:
    """No water and no lights: the regenerator has nothing to strip."""
    feed = _feed({"TEG": 1.0})
    with pytest.raises(TEGRegenError, match="nothing to regenerate"):
        _solve(feed)


def test_feed_without_teg_is_refused() -> None:
    feed = _feed({"H2O": 1.0})
    with pytest.raises(TEGRegenError, match="no TEG"):
        _solve(feed)


def test_solve_is_deterministic() -> None:
    feed = _feed({"TEG": 0.95, "H2O": 0.05})
    first = _solve(feed)
    second = _solve(feed)
    assert first.info == second.info
    assert first.duty_W == second.duty_W
    for port in ("lean_out", "water_out"):
        assert first.outlets[port] == second.outlets[port]


def test_example_case_solves_on_the_pr_package() -> None:
    """The V0 example: 97.5 wt% rich glycol, 204 C reboiler, 1 atm."""
    feeds, params = TEGRegen.example_case()
    feed = _feed(**{k: feeds["rich_in"][k] for k in ("composition", "T", "P", "molar_flow")})
    result = _solve(feed, params)
    assert result.info["rich_teg_mass_fraction"] == pytest.approx(0.975, abs=1e-6)
    assert 0.98 <= result.info["lean_teg_mass_fraction"] <= 1.0
    assert result.outlets["lean_out"].molar_flow > 0.0
    assert result.outlets["water_out"].molar_flow > 0.0
