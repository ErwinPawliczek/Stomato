"""Reactor adapter tests (U-F): closed-form oracles, refusals, solver resolution."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import Flowsheet, StreamSpec
from ngdesign.contracts.flowsheet import FeedSpec, PortRef, UnitSpec
from ngdesign.solver.sequential_modular import SequentialModular
from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.units.reactors import (
    ConversionReactor,
    ElectrolyserStack,
    EquilibriumReactor,
    GibbsReactor,
    YieldReactor,
)

THERMO = PengRobinsonThermo()

#: The conversion example's closed-form outlet amounts (mol/s), shared with
#: the yield twin: 10 CH4 + 40 H2O + 5 N2 at X = 0.7.
SMR_AMOUNTS = {"CH4": 3.0, "H2O": 33.0, "CO": 7.0, "H2": 21.0, "N2": 5.0}

WGS_SET = {
    "id": "wgs_case",
    "components": ["CO", "H2O", "CO2", "H2"],
    "reactions": [
        {
            "id": "wgsr",
            "stoichiometry": {"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
            "base_component": "CO",
            "provenance": "water-gas shift, standard reference (e.g. SVA App. C)",
            "equilibrium": {"form": "from_gibbs"},
        }
    ],
}


def flash_feed(feed: dict[str, Any]) -> Any:
    return THERMO.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


def test_conversion_example_closed_form_amounts() -> None:
    feeds, params = ConversionReactor.example_case()
    r = ConversionReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)
    out = r.outlets["outlet"]
    for cid, want in SMR_AMOUNTS.items():
        assert math.isclose(out.molar_flow * out.composition[cid], want, abs_tol=1e-9)
    assert r.duty_W == pytest.approx(0.0, abs=1e-6)


def test_yield_twin_matches_conversion_amounts() -> None:
    feeds, params = YieldReactor.example_case()
    r = YieldReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)
    out = r.outlets["outlet"]
    for cid, want in SMR_AMOUNTS.items():
        assert math.isclose(out.molar_flow * out.composition[cid], want, abs_tol=1e-9)


def test_wgs_equilibrium_closed_form() -> None:
    feeds, params = EquilibriumReactor.example_case()
    r = EquilibriumReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)
    out = r.outlets["outlet"]
    # ln K(1100 K) = -0.007436 -> X = sqrt(K)/(1+sqrt(K)) ~ 0.49907
    assert r.info["extent_wgsr"] == pytest.approx(0.499071, abs=1e-5)
    assert out.composition["CO"] == pytest.approx(0.250465, abs=1e-5)
    assert out.composition["CO2"] == pytest.approx(0.249535, abs=1e-5)


def test_gibbs_matches_equilibrium_to_1e6() -> None:
    feeds, params = GibbsReactor.example_case()
    gb = GibbsReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)
    eq_feeds, eq_params = EquilibriumReactor.example_case()
    eq = EquilibriumReactor().solve({"inlet": flash_feed(eq_feeds["inlet"])}, eq_params, THERMO)
    g_out, e_out = gb.outlets["outlet"], eq.outlets["outlet"]
    for cid in ("CO", "H2O", "CO2", "H2"):
        assert abs(g_out.composition[cid] - e_out.composition[cid]) < 1e-6


def test_electrolyser_faraday_and_power() -> None:
    feeds, params = ElectrolyserStack.example_case()
    r = ElectrolyserStack().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)
    h2 = r.outlets["h2_out"].molar_flow
    assert h2 == pytest.approx(0.98 * 2000.0 * 100.0 / (2 * 96485.33212), rel=1e-12)
    o2 = r.outlets["o2_out"]
    assert o2.molar_flow * o2.composition["O2"] == pytest.approx(0.5 * h2, rel=1e-12)
    assert r.power_W == 350_000.0
    assert r.info["thermoneutral_voltage_V"] == pytest.approx(1.253154, abs=1e-4)


def test_all_reactors_close_element_balances() -> None:
    from ngdesign.data.formation import atomic_composition

    def atoms(state: Any) -> dict[str, float]:
        acc: dict[str, float] = {}
        for cid, y in state.composition.items():
            for el, count in atomic_composition(cid).items():
                acc[el] = acc.get(el, 0.0) + count * state.molar_flow * y
        return acc

    for cls in (ConversionReactor, YieldReactor, EquilibriumReactor, GibbsReactor, ElectrolyserStack):
        feeds, params = cls.example_case()
        inlet = flash_feed(feeds["inlet"])
        r = cls().solve({"inlet": inlet}, params, THERMO)
        a_in = atoms(inlet)
        a_out: dict[str, float] = {}
        for state in r.outlets.values():
            for el, v in atoms(state).items():
                a_out[el] = a_out.get(el, 0.0) + v
        worst = max(abs(a_out.get(el, 0.0) - v) for el, v in a_in.items())
        assert worst < 1e-8, f"{cls.__name__} element residual {worst}"


def test_conversion_rejects_invalid_reaction_set_before_solving() -> None:
    feeds, params = ConversionReactor.example_case()
    params["reaction_set"]["reactions"][0]["stoichiometry"]["H2S"] = -1.0
    # ReactionSet validation refuses the unbalanced/unknown-species reaction
    # (element H balance fires before the slate check — the slate rule itself
    # is covered by tests/contracts/test_reactions.py).
    with pytest.raises(ValueError, match="balance violated"):
        ConversionReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def test_conversion_rejects_infeasible_adiabatic_balance() -> None:
    feeds, params = ConversionReactor.example_case()
    feeds["inlet"]["T"] = 298.15  # reaction heat uptake exceeds all sensible heat
    with pytest.raises(ValueError, match="adiabatic"):
        ConversionReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def test_yield_rejects_bad_yield_sum() -> None:
    feeds, params = YieldReactor.example_case()
    params["yields_mass"] = [y * 1.01 for y in params["yields_mass"]]
    with pytest.raises(ValueError, match="sum"):
        YieldReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def test_electrolyser_rejects_h2_or_o2_in_feed() -> None:
    feeds, params = ElectrolyserStack.example_case()
    feeds["inlet"]["composition"] = {"H2O": 0.999, "H2": 0.001}
    with pytest.raises(ValueError, match="H2"):
        ElectrolyserStack().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def _smr_flowsheet() -> Flowsheet:
    feed = {
        "T": 1000.0,
        "P": 3000000.0,
        "molar_flow": 55.0,
        "composition": {"CH4": 10 / 55, "H2O": 40 / 55, "N2": 5 / 55},
    }
    return Flowsheet(
        name="smr-slice",
        units=[
            UnitSpec(
                tag="R-101",
                kind="conversion_reactor",
                params={"reaction_set": "smr_case", "conversion": {"ref": 0.7}, "thermal": "isothermal"},
            )
        ],
        streams=[
            StreamSpec(
                id="F1",
                target=PortRef(unit="R-101", port="inlet"),
                feed=FeedSpec(
                    T=feed["T"], P=feed["P"], molar_flow=feed["molar_flow"], composition=feed["composition"]
                ),
            ),
            StreamSpec(id="P1", source=PortRef(unit="R-101", port="outlet")),
        ],
        reactions=[
            WGS_SET
            | {
                "id": "smr_case",
                "components": ["CH4", "H2O", "CO", "H2", "N2"],
                "reactions": [
                    {
                        "id": "ref",
                        "stoichiometry": {"CH4": -1.0, "H2O": -1.0, "CO": 1.0, "H2": 3.0},
                        "base_component": "CH4",
                        "provenance": "steam-methane reforming, lumped",
                        "equilibrium": {"form": "from_gibbs"},
                    }
                ],
            }
        ],
    )


def test_solver_resolves_flowsheet_owned_reaction_set() -> None:
    r = SequentialModular().solve(_smr_flowsheet(), THERMO)
    assert r.converged and not r.errors
    out = r.streams["P1"]
    for cid, want in SMR_AMOUNTS.items():
        assert math.isclose(out.molar_flow * out.composition[cid], want, abs_tol=1e-6)


def test_solver_names_unknown_reaction_set_id() -> None:
    fs = _smr_flowsheet()
    fs.units[0].params["reaction_set"] = "nope"
    r = SequentialModular().solve(fs, THERMO)
    assert any("nope" in e.message and "smr_case" in e.message for e in r.errors)
