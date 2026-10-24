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
    # JANAF printed log Kf(1100 K): CO2 18.805, CO 9.928, H2O 8.881
    # -> log K(WGS) = -0.004 -> X = sqrt(K)/(1+sqrt(K)) = 0.498846
    assert r.info["extent_wgsr"] == pytest.approx(0.498846, abs=1e-3)
    assert out.composition["CO"] == pytest.approx(0.250577, abs=1e-3)
    assert out.composition["CO2"] == pytest.approx(0.249423, abs=1e-3)


def test_wgs_approach_K_shifts_conversion_and_reports_lnK() -> None:
    feeds, params = EquilibriumReactor.example_case()
    inlet = flash_feed(feeds["inlet"])
    eq = EquilibriumReactor().solve({"inlet": inlet}, params, THERMO)
    # WGS is mildly exothermic near 1100 K: approaching from the cold side
    # (approach_K = -50 -> K at 1150 K) must REDUCE conversion and report the
    # lower equilibrium constant at the evaluated temperature.
    app = EquilibriumReactor().solve({"inlet": inlet}, params | {"approach_K": -50.0}, THERMO)
    assert app.info["extent_wgsr"] < eq.info["extent_wgsr"]
    assert app.info["lnK_wgsr"] < eq.info["lnK_wgsr"]
    # full equilibrium (approach 0) reproduces the isothermal result
    zero = EquilibriumReactor().solve({"inlet": inlet}, params | {"approach_K": 0.0}, THERMO)
    assert zero.info["extent_wgsr"] == pytest.approx(eq.info["extent_wgsr"], rel=1e-9)


def test_gibbs_rejects_h2_or_o2_mixture_spec() -> None:
    with pytest.raises(ValueError, match="species"):
        GibbsReactor().solve(
            {"inlet": flash_feed({"T": 300.0, "P": 101325.0, "molar_flow": 1.0, "composition": {"H2": 1.0}})},
            {"species": ["H2O", "CO2"]},
            THERMO,
        )


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
    # Thermoneutral voltage from the actual stream balance (H_out − H_in)/(2F·n_H2)
    # at the 298.15 K liquid-water feed. The printed check is 1.481 V (Züttel,
    # Borgschulte & Schlapbach 2008, ch. 1 §1.1, p. 5, ISBN 978-3-527-30817-0); the
    # databank measures 1.48953 V (+0.58 %) — the printed-value comparison with the
    # recorded miss lives in the V1-ELECTROLYSER case's assessed note, and this
    # assertion is only a 1 % regression guard around the JANAF HHV anchor.
    assert r.info["thermoneutral_voltage_V"] == pytest.approx(1.4812, rel=0.01)


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


def test_equilibrium_rejects_clipped_extent(monkeypatch: pytest.MonkeyPatch) -> None:
    # A strongly-depleted solve can only be represented by fsolve as an extent
    # beyond the depletion limit (past it, ln Q sits on the flat boundary
    # sentinel). Inject exactly that solver outcome — extent 2.0 on the 2 mol/s
    # equimolar feed, whose depletion limit is 1.0 — with a success flag: the
    # adapter must refuse, never clip silently and pass.
    import ngdesign.units.reactors.equilibrium_reactor as eq_mod

    def fake_fsolve(system: Any, x0: Any, **kw: Any) -> tuple[list[float], dict[str, Any], int, str]:
        return [2.0], {}, 1, "converged"

    monkeypatch.setattr(eq_mod, "fsolve", fake_fsolve)
    feeds, params = EquilibriumReactor.example_case()
    with pytest.raises(ValueError, match="clipped"):
        EquilibriumReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def test_equilibrium_rejects_unconverged_residual(monkeypatch: pytest.MonkeyPatch) -> None:
    # fsolve reporting success at a non-root (residual ≈ −0.4, far outside the
    # 1e-6 tolerance and not the depletion sentinel) must be refused by the
    # residual guard, not returned as an equilibrium.
    import ngdesign.units.reactors.equilibrium_reactor as eq_mod

    def fake_fsolve(system: Any, x0: Any, **kw: Any) -> tuple[list[float], dict[str, Any], int, str]:
        return [0.45], {}, 1, "converged"

    monkeypatch.setattr(eq_mod, "fsolve", fake_fsolve)
    feeds, params = EquilibriumReactor.example_case()
    with pytest.raises(ValueError, match="residuals"):
        EquilibriumReactor().solve({"inlet": flash_feed(feeds["inlet"])}, params, THERMO)


def test_gibbs_duty_mode_returns_q_and_closes_formation_energy() -> None:
    from ngdesign.units._physics.kinetics import enthalpy_with_formation

    feeds, params = GibbsReactor.example_case()
    inlet = flash_feed(feeds["inlet"])
    q = -5000.0
    r = GibbsReactor().solve({"inlet": inlet}, params | {"thermal": {"duty_W": q}}, THERMO)
    # the requested duty is returned as requested, and the outlet temperature is
    # solved so the formation-enthalpy balance closes on exactly that duty
    assert r.duty_W == q
    closed = enthalpy_with_formation(r.outlets["outlet"]) - enthalpy_with_formation(inlet)
    assert closed == pytest.approx(q, rel=1e-6)
    # WGS is exothermic: removing only 5 kW of the ~19 kW released leaves the
    # outlet hotter than the inlet
    assert r.outlets["outlet"].T > inlet.T


def test_gibbs_t_out_mode() -> None:
    from ngdesign.units._physics.kinetics import enthalpy_with_formation

    feeds, params = GibbsReactor.example_case()
    inlet = flash_feed(feeds["inlet"])
    r = GibbsReactor().solve({"inlet": inlet}, params | {"thermal": {"T_out": 1200.0}}, THERMO)
    out = r.outlets["outlet"]
    assert out.T == pytest.approx(1200.0, abs=1e-9)
    # duty closes on the formation basis
    closed = enthalpy_with_formation(out) - enthalpy_with_formation(inlet)
    assert r.duty_W == pytest.approx(closed, rel=1e-9)
    # same physics, different route: the equilibrium reactor at the same T_out
    # (V2 cross-check holds at 1200 K too)
    eq_feeds, eq_params = EquilibriumReactor.example_case()
    eq = EquilibriumReactor().solve(
        {"inlet": flash_feed(eq_feeds["inlet"])}, eq_params | {"thermal": {"T_out": 1200.0}}, THERMO
    )
    eq_out = eq.outlets["outlet"]
    for cid in ("CO", "H2O", "CO2", "H2"):
        assert abs(out.composition[cid] - eq_out.composition[cid]) < 1e-6


def test_equilibrium_t_out_mode_matches_isothermal_at_that_t() -> None:
    # the equilibrium composition depends on (T_eq, P), not on the inlet T, so a
    # {"T_out": 1000} run on the 1100 K example feed must equal an isothermal
    # run fed at 1000 K
    feeds, params = EquilibriumReactor.example_case()
    r = EquilibriumReactor().solve(
        {"inlet": flash_feed(feeds["inlet"])}, params | {"thermal": {"T_out": 1000.0}}, THERMO
    )
    ref = EquilibriumReactor().solve({"inlet": flash_feed(feeds["inlet"] | {"T": 1000.0})}, params, THERMO)
    assert r.outlets["outlet"].T == pytest.approx(1000.0, abs=1e-9)
    assert r.info["extent_wgsr"] == pytest.approx(ref.info["extent_wgsr"], rel=1e-9)
    assert r.info["lnK_wgsr"] == pytest.approx(ref.info["lnK_wgsr"], rel=1e-9)


def test_sequential_conversion_closed_form_two_reactions_sharing_a_reactant() -> None:
    # 10 CH4 + 40 H2O: SMR at X = 0.5 (extent 5, Δν = +2), then WGS at X = 0.8
    # applied to the running amounts (not the inlet basis): after SMR, 5 CH4 +
    # 35 H2O + 5 CO + 15 H2 (total 60); WGS consumes 4 of the 5 CO -> 5 CH4 +
    # 31 H2O + 1 CO + 4 CO2 + 19 H2 (total still 60 mol/s).
    feed = {
        "T": 700.0,
        "P": 3000000.0,
        "molar_flow": 50.0,
        "composition": {"CH4": 0.2, "H2O": 0.8},
    }
    rset = {
        "id": "seq_case",
        "components": ["CH4", "H2O", "CO", "CO2", "H2"],
        "reactions": [
            {
                "id": "smr",
                "stoichiometry": {"CH4": -1.0, "H2O": -1.0, "CO": 1.0, "H2": 3.0},
                "base_component": "CH4",
                "provenance": "steam-methane reforming, lumped",
                "equilibrium": {"form": "from_gibbs"},
            },
            {
                "id": "wgs",
                "stoichiometry": {"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
                "base_component": "CO",
                "provenance": "water-gas shift",
                "equilibrium": {"form": "from_gibbs"},
            },
        ],
    }
    params = {
        "reaction_set": rset,
        "conversion": {"smr": 0.5, "wgs": 0.8},
        "sequential": True,
        "thermal": "isothermal",
    }
    r = ConversionReactor().solve({"inlet": flash_feed(feed)}, params, THERMO)
    out = r.outlets["outlet"]
    want = {"CH4": 5.0, "H2O": 31.0, "CO": 1.0, "CO2": 4.0, "H2": 19.0}
    for cid, n in want.items():
        assert math.isclose(out.molar_flow * out.composition[cid], n, abs_tol=1e-9), cid


def test_equilibrium_adiabatic_outlet_is_at_equilibrium_at_outlet_t() -> None:
    from ngdesign.contracts.reactions import Reaction
    from ngdesign.units._physics.kinetics import ln_keq

    feeds, params = EquilibriumReactor.example_case()
    inlet = flash_feed(feeds["inlet"])
    r = EquilibriumReactor().solve({"inlet": inlet}, params | {"thermal": "adiabatic"}, THERMO)
    out = r.outlets["outlet"]
    assert r.duty_W == pytest.approx(0.0, abs=1e-6)
    # WGS is exothermic: the coupled adiabatic outlet is hotter than the inlet
    assert out.T > inlet.T
    # the coupling is real: the outlet composition must sit AT equilibrium at
    # the outlet temperature (ln Q(out, T_out) = ln K(T_out) within the solve
    # tolerance), not at equilibrium at the inlet temperature
    reaction = Reaction.model_validate(WGS_SET["reactions"][0])
    ln_q = (
        math.log(out.composition["CO2"])
        + math.log(out.composition["H2"])
        - math.log(out.composition["CO"])
        - math.log(out.composition["H2O"])
    )  # Δν = 0 for WGS: the (P/P°)^ν factor cancels
    assert ln_q == pytest.approx(ln_keq(reaction, out.T), abs=1e-6)
    # and it is NOT the inlet-temperature equilibrium (which the isothermal
    # example pins at extent 0.4988): the hotter outlet converts less
    iso = EquilibriumReactor().solve({"inlet": inlet}, params, THERMO)
    assert r.info["extent_wgsr"] < iso.info["extent_wgsr"]
