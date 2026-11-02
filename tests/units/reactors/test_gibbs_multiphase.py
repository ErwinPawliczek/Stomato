"""Multiphase Gibbs reactor: phases decided by the minimum, energy closed across them."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.data.formation import formation_enthalpy_298
from ngdesign.data.species_models import species_thermo
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors.gibbs_multiphase import GibbsMultiphase, GibbsMultiphaseError


def _inlet(
    thermo: Thermo, composition: dict[str, float], T: float, P: float = 1.0e5, flow: float = 1.0
) -> StreamState:
    feed = FeedSpec(T=T, P=P, molar_flow=flow, composition=composition)
    return thermo.flash_pt(feed.composition, feed.T, feed.P, feed.molar_flow)


def _solve(thermo: Thermo, inlet: StreamState, **params: Any) -> Any:
    unit = GibbsMultiphase()
    return unit.solve({"inlet": inlet}, params, thermo)


def test_is_registered() -> None:
    assert "gibbs_multiphase" in registry.available("unit")


def test_methane_cracks_to_carbon_at_the_equilibrium_constant(thermo: Thermo) -> None:
    result = _solve(thermo, _inlet(thermo, {"CH4": 1.0}, 1200.0), species=["CH4", "H2", "C(s)"])
    vapor, condensed = result.outlets["vapor_out"], result.outlets["condensed_out"]
    assert condensed.composition == {"C": 1.0}
    assert condensed.molar_flow > 0.5
    g = {cid: species_thermo(cid).g(1200.0) for cid in ("CH4", "H2")}
    ln_k = -(g["CH4"] - 2.0 * g["H2"] - species_thermo("C", "solid").g(1200.0)) / (8.31446261815324 * 1200.0)
    y = vapor.composition
    assert math.log(y["CH4"] / y["H2"] ** 2) == pytest.approx(ln_k, abs=1e-6)


def test_elements_are_conserved_across_the_phases(thermo: Thermo) -> None:
    result = _solve(thermo, _inlet(thermo, {"CH4": 1.0}, 1200.0), species=["CH4", "H2", "C(s)"])
    vapor, condensed = result.outlets["vapor_out"], result.outlets["condensed_out"]
    n = vapor.component_flows()
    assert n["CH4"] + condensed.molar_flow == pytest.approx(1.0, abs=1e-9)
    assert 4.0 * n["CH4"] + 2.0 * n["H2"] == pytest.approx(4.0, abs=1e-9)


def test_steam_prevents_carbon(thermo: Thermo) -> None:
    species = ["CH4", "H2O", "CO", "CO2", "H2", "C(s)"]
    result = _solve(thermo, _inlet(thermo, {"CH4": 0.25, "H2O": 0.75}, 1100.0), species=species)
    condensed = result.outlets["condensed_out"]
    assert condensed.molar_flow == 0.0


@pytest.mark.parametrize(
    "thermal", ["adiabatic", {"duty_W": 20_000.0}, {"T_out": 1300.0}, "isothermal"], ids=str
)
def test_energy_balance_closes_on_every_thermal_mode(thermo: Thermo, thermal: Any) -> None:
    inlet = _inlet(thermo, {"CH4": 1.0}, 1400.0)
    result = _solve(thermo, inlet, species=["CH4", "H2", "C(s)"], thermal=thermal)
    out = sum(enthalpy_with_formation(s) for s in result.outlets.values())
    assert out == pytest.approx(enthalpy_with_formation(inlet) + result.duty_W, abs=1e-3)


def test_endothermic_cracking_cools_when_adiabatic(thermo: Thermo) -> None:
    result = _solve(
        thermo, _inlet(thermo, {"CH4": 1.0}, 1400.0), species=["CH4", "H2", "C(s)"], thermal="adiabatic"
    )
    assert result.outlets["vapor_out"].T < 1400.0
    assert result.outlets["condensed_out"].molar_flow > 0.0


def test_condensed_enthalpy_is_the_true_element_reference_value(thermo: Thermo) -> None:
    result = _solve(thermo, _inlet(thermo, {"CH4": 1.0}, 1200.0), species=["CH4", "H2", "C(s)"])
    condensed = result.outlets["condensed_out"]
    # graphite: H°(1200 K) on the element reference, not the 717 kJ/mol carbon atom
    expected = condensed.molar_flow * species_thermo("C", "solid").h(1200.0)
    assert enthalpy_with_formation(condensed) == pytest.approx(expected, abs=1e-6)
    assert formation_enthalpy_298("C") > 7e5


def test_inerts_pass_through_and_dilute(thermo: Thermo) -> None:
    plain = _solve(thermo, _inlet(thermo, {"CH4": 1.0}, 1000.0), species=["CH4", "H2", "C(s)"])
    diluted = _solve(
        thermo,
        _inlet(thermo, {"CH4": 0.25, "N2": 0.75}, 1000.0, flow=4.0),
        species=["CH4", "H2", "C(s)"],
        inerts=["N2"],
    )
    assert diluted.outlets["vapor_out"].component_flows()["N2"] == pytest.approx(3.0)
    assert diluted.outlets["condensed_out"].molar_flow > plain.outlets["condensed_out"].molar_flow


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({"species": ["CH4", "H2"]}, "no condensed candidate"),
        ({"species": ["H2", "C(s)"]}, "not listed"),
        ({"species": ["CH4", "H2", "C(s)"], "inerts": ["CH4"]}, "both species and inerts"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    with pytest.raises(GibbsMultiphaseError, match=match):
        _solve(thermo, _inlet(thermo, {"CH4": 1.0}, 1200.0), **params)
