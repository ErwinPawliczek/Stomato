"""Spec U-D acceptance tests: flash_drum, decanter, tank, adsorption_bed, hydrate_check."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed


def _solve(
    thermo: Thermo,
    unit_id: str,
    params: dict[str, Any] | None = None,
    feed_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, StreamState], UnitResult]:
    unit = registry.create("unit", unit_id)
    feeds, defaults = unit.example_case()
    if feed_overrides:
        for port, patch in feed_overrides.items():
            feeds[port].update(patch)
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return inlets, unit.solve(inlets, {**defaults, **(params or {})}, thermo)


# --- flash_drum -----------------------------------------------------------


def test_flash_drum_vf_spec_matches_independent_flash(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "flash_drum", {"duty_W": None, "vapor_fraction": 0.5, "outlet_P": 3.0e6})
    feed = inlets["inlet"]
    flashed = thermo.flash_pvf(feed.composition, 3.0e6, 0.5, feed.molar_flow)
    assert result.info["T_out_K"] == pytest.approx(flashed.T, rel=1e-9)
    assert result.outlets["gas_out"].molar_flow == pytest.approx(0.5 * feed.molar_flow, rel=1e-6)


def test_flash_drum_duty_case_matches_independent_flash(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "flash_drum")  # example: 500 kW duty
    feed = inlets["inlet"]
    h_mix = feed.enthalpy + 5.0e5 / feed.molar_flow
    flashed = thermo.flash_ph(feed.composition, 3.0e6, h_mix, feed.molar_flow)
    assert result.info["T_out_K"] == pytest.approx(flashed.T, rel=1e-9)


def test_flash_drum_molar_balance(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "flash_drum")
    feed = inlets["inlet"]
    total = sum(s.molar_flow for s in result.outlets.values())
    assert total == pytest.approx(feed.molar_flow, rel=1e-9)


def test_flash_drum_rejects_two_specs(thermo: Thermo) -> None:
    unit = registry.create("unit", "flash_drum")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="not both"):
        unit.solve(inlets, {**params, "vapor_fraction": 0.5}, thermo)


# --- decanter -------------------------------------------------------------


def test_decanter_splits_water_and_pentane(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "decanter")
    light, heavy = result.outlets["light_out"], result.outlets["heavy_out"]
    assert light.composition["nC5"] > 0.99
    assert heavy.composition["H2O"] > 0.99
    assert light.molar_flow + heavy.molar_flow == pytest.approx(inlets["inlet"].molar_flow, rel=1e-9)


def test_decanter_dP_sets_outlet_pressure(thermo: Thermo) -> None:
    _, result = _solve(thermo, "decanter", {"dP": 5.0e3})
    for outlet in result.outlets.values():
        assert outlet.P == pytest.approx(1.0e5 - 5.0e3, rel=1e-9)


def test_decanter_rejects_single_liquid(thermo: Thermo) -> None:
    unit = registry.create("unit", "decanter")
    feeds, _params = unit.example_case()
    feeds["inlet"]["composition"] = {"H2O": 1.0}
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="liquid phase"):
        unit.solve(inlets, {}, thermo)


# --- tank -----------------------------------------------------------------


def test_tank_residence_time_and_pressure(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "tank", {"volume_m3": 5.0})
    outlet = result.outlets["outlet"]
    assert outlet.P == pytest.approx(inlets["inlet"].P, rel=1e-9)
    expected = 5.0 / result.info["liquid_vol_flow_m3_s"]
    assert result.info["residence_time_s"] == pytest.approx(expected, rel=1e-9)


def test_tank_rejects_negative_volume(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="volume_m3"):
        _solve(thermo, "tank", {"volume_m3": -1.0})


# --- adsorption_bed -------------------------------------------------------


def test_adsorption_bed_removes_95pct_water(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "adsorption_bed")
    feed, regen = inlets["feed_in"], result.outlets["regen_out"]
    n_h2o_in = feed.composition["H2O"] * feed.molar_flow
    n_h2o_regen = regen.composition["H2O"] * regen.molar_flow
    assert n_h2o_regen == pytest.approx(0.95 * n_h2o_in, rel=1e-6)
    total = sum(s.molar_flow for s in result.outlets.values())
    assert total == pytest.approx(feed.molar_flow, rel=1e-9)


def test_adsorption_bed_cycle_time_closed_form(thermo: Thermo) -> None:
    _, result = _solve(thermo, "adsorption_bed")
    rate = result.info["adsorbate_mass_rate_kg_s"]
    assert result.info["cycle_time_s"] == pytest.approx(0.10 * 500.0 / rate, rel=1e-9)


def test_adsorption_bed_rejects_unknown_component(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="not in the feed"):
        _solve(thermo, "adsorption_bed", {"removal_fraction": {"H2S": 0.9}})


def test_adsorption_bed_rejects_out_of_range_fraction(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match=r"outside \[0, 1\]"):
        _solve(thermo, "adsorption_bed", {"removal_fraction": {"H2O": 1.5}})


# --- hydrate_check --------------------------------------------------------


def test_hydrate_check_required_dose_matches_gpsa_20_10(thermo: Thermo) -> None:
    """GPSA SI Sect. 20 Example 20-10 (with SI errata): 14 K depression needs
    27.5 wt% MeOH in the aqueous phase (Nielsen-Bucklin; Hammerschmidt 25.5)."""
    unit = registry.create("unit", "hydrate_check")
    feeds, params = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    base = unit.solve(inlets, {}, thermo)
    hydrate_T = base.info["hydrate_T_K"]
    dosed = unit.solve(inlets, {"T_operating_K": hydrate_T - 14.0}, thermo)
    assert dosed.info["required_inhibitor_mass_fraction"] == pytest.approx(0.275, abs=0.005)
    assert dosed.info["hydrate_T_K"] == pytest.approx(hydrate_T, rel=1e-9)


def test_hydrate_check_zero_dose_above_hydrate_T(thermo: Thermo) -> None:
    _, result = _solve(thermo, "hydrate_check", {"T_operating_K": 400.0})
    assert result.info["required_inhibitor_mass_fraction"] == 0.0


def test_hydrate_check_rejects_dose_without_inhibitor(thermo: Thermo) -> None:
    unit = registry.create("unit", "hydrate_check")
    feeds, params = unit.example_case()
    comp = {**{k: v for k, v in feeds["inlet"]["composition"].items() if k != "H2O"}, "H2O": 0.03}
    total = sum(comp.values())
    feeds["inlet"]["composition"] = {k: v / total for k, v in comp.items()}
    feeds["inhibitor_in"]["molar_flow"] = 0.0  # port must exist; zero flow = no dose
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ValueError, match="inhibitor"):
        unit.solve(inlets, {"T_operating_K": 273.15}, thermo)


def test_hydrate_check_dose_basis_is_water_plus_inhibitor() -> None:
    """Nielsen-Bucklin's w is defined on water + inhibitor alone.

    A 10 / 80 / 10 mol% MeOH / H2O / CH4 aqueous phase has w = 0.182 on that
    basis (0.234 if dissolved methane were wrongly counted in the denominator).
    """
    from ngdesign.units.separation.hydrate_check import _inhibitor_mass_fraction

    w = _inhibitor_mass_fraction({"MeOH": 0.1, "H2O": 0.8, "CH4": 0.1}, "MeOH")
    assert w == pytest.approx(0.1820, abs=0.0005)


# --- hydrocyclone -----------------------------------------------------------


def test_hydrocyclone_splits_water_to_underflow(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "hydrocyclone")
    under, over = result.outlets["underflow"], result.outlets["overflow"]
    feed = inlets["inlet"]
    n_h2o_under = under.composition["H2O"] * under.molar_flow
    assert n_h2o_under == pytest.approx(
        0.95 * feed.composition["H2O"] * feed.molar_flow, rel=1e-9
    )
    n_oil_over = over.composition["nC5"] * over.molar_flow
    assert n_oil_over == pytest.approx(feed.composition["nC5"] * feed.molar_flow, rel=1e-9)


def test_hydrocyclone_dP_on_overflow_only(thermo: Thermo) -> None:
    _, result = _solve(thermo, "hydrocyclone", {"dP": 2.0e4})
    assert result.outlets["underflow"].P == pytest.approx(5.0e5, rel=1e-9)
    assert result.outlets["overflow"].P == pytest.approx(5.0e5 - 2.0e4, rel=1e-9)


# --- filter -----------------------------------------------------------------


def test_filter_sends_solids_to_cake(thermo: Thermo) -> None:
    inlets, result = _solve(thermo, "filter")
    cake, filtrate = result.outlets["cake"], result.outlets["filtrate"]
    feed = inlets["inlet"]
    n_si_cake = cake.composition["SiO2"] * cake.molar_flow
    assert n_si_cake == pytest.approx(feed.composition["SiO2"] * feed.molar_flow, rel=1e-9)
    assert filtrate.composition["SiO2"] == pytest.approx(0.0, abs=1e-12)
    assert cake.molar_flow + filtrate.molar_flow == pytest.approx(feed.molar_flow, rel=1e-9)


def test_filter_dP_on_filtrate_only(thermo: Thermo) -> None:
    _, result = _solve(thermo, "filter", {"dP": 3.0e4})
    assert result.outlets["cake"].P == pytest.approx(3.0e5, rel=1e-9)
    assert result.outlets["filtrate"].P == pytest.approx(3.0e5 - 3.0e4, rel=1e-9)


# --- membrane ---------------------------------------------------------------


def test_membrane_stage_cut_matches_geankoplis_13_4_2(thermo: Thermo) -> None:
    """Geankoplis Ex. 13.4-2 (p. 767, 4th ed.): Weller-Steiner complete mixing.

    Air (z_O2 = 0.209) at a 10:1 pressure ratio, alpha = 10, stage cut 0.2
    gives a permeate y_O2 = 0.5068 and a reject x_O2 = 0.1345.
    """
    inlets, result = _solve(thermo, "membrane")
    permeate, residue = result.outlets["permeate"], result.outlets["residue"]
    assert permeate.composition["O2"] == pytest.approx(0.5068, abs=0.001)
    assert residue.composition["O2"] == pytest.approx(0.1345, abs=0.001)
    assert permeate.molar_flow == pytest.approx(0.2 * inlets["feed_in"].molar_flow, rel=1e-9)
    assert permeate.molar_flow + residue.molar_flow == pytest.approx(
        inlets["feed_in"].molar_flow, rel=1e-9
    )
    assert permeate.P == pytest.approx(2.533125e4, rel=1e-9)
    assert residue.P == pytest.approx(2.533125e5, rel=1e-9)


def test_membrane_rejects_stage_cut_of_one(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="stage cut"):
        _solve(thermo, "membrane", {"stage_cut": 1.0})


def test_membrane_rejects_permeate_pressure_above_feed(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="P_permeate"):
        _solve(thermo, "membrane", {"P_permeate": 3.0e5})


# --- flash_drum multi-inlet -------------------------------------------------


def test_flash_drum_mixes_two_inlets(thermo: Thermo) -> None:
    unit = registry.create("unit", "flash_drum")
    feeds, _params = unit.example_case()
    feeds["inlet_2"] = dict(feeds["inlet"])
    feeds["inlet_2"]["molar_flow"] = 50.0
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = unit.solve(inlets, {"duty_W": None, "vapor_fraction": 0.5}, thermo)
    total = sum(s.molar_flow for s in result.outlets.values())
    assert total == pytest.approx(inlets["inlet"].molar_flow + 50.0, rel=1e-9)


def test_flash_drum_zero_flow_second_inlet_unchanged(thermo: Thermo) -> None:
    _inlets, single = _solve(thermo, "flash_drum", {"duty_W": None, "vapor_fraction": 0.5})
    unit = registry.create("unit", "flash_drum")
    feeds, params = unit.example_case()
    feeds["inlet_2"] = dict(feeds["inlet"])
    feeds["inlet_2"]["molar_flow"] = 0.0
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = unit.solve(inlets, {"duty_W": None, "vapor_fraction": 0.5}, thermo)
    assert result.info["T_out_K"] == pytest.approx(single.info["T_out_K"], rel=1e-9)


# --- tank refusal -----------------------------------------------------------


def test_tank_rejects_pressure_above_lowest_inlet(thermo: Thermo) -> None:
    with pytest.raises(ValueError, match="does not raise pressure"):
        _solve(thermo, "tank", {"P": 4.0e6})
