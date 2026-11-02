"""fcc R0 and R1 tests: closed forms, table refusals, the riser heat balance."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

import pytest
from scipy.integrate import quad

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.refining.fcc import FccR0, FccR1, FccSpecError


def _feed(thermo: Thermo, cls: Any) -> Any:
    feeds = cls.example_case()[0]["feed_in"]
    return thermo.flash_pt(feeds["composition"], feeds["T"], feeds["P"], feeds["molar_flow"])


def _iso(k12: float, k13: float, k23: float, *, k14: float = 0.0, k24: float = 0.0) -> dict[str, Any]:
    """Isothermal kinetics with Ea = 0: k_ij are the constants themselves."""
    _, params = FccR1.example_case()
    params = {
        key: value
        for key, value in params.items()
        if key
        not in (
            "catalyst_to_oil",
            "cp_cat_J_kgK",
            "T_regen_K",
            "heat_of_cracking_J_kg",
            "coke_heat_of_combustion_J_kg",
        )
    }
    params["isothermal_T_K"] = 800.0
    params["kinetics"] = {
        "gasoil_to_gasoline": {"k0_per_s": k12, "Ea_J_mol": 0.0},
        "gasoil_to_gases": {"k0_per_s": k13, "Ea_J_mol": 0.0},
        "gasoil_to_coke": {"k0_per_s": k14, "Ea_J_mol": 0.0},
        "gasoline_to_gases": {"k0_per_s": k23, "Ea_J_mol": 0.0},
        "gasoline_to_coke": {"k0_per_s": k24, "Ea_J_mol": 0.0},
    }
    return params


def test_r0_interpolates_the_table_linearly(thermo: Thermo) -> None:
    """Midpoint of the test table: the mean of the two rows, summing to 100."""
    _, params = FccR0.example_case()
    res = FccR0().solve({"feed_in": _feed(thermo, FccR0)}, params, thermo)
    assert res.info["gasoline_wt_pct"] == pytest.approx(48.0)
    assert res.info["coke_wt_pct"] == pytest.approx(5.0)
    assert res.info["lco_wt_pct"] + res.info["slurry_wt_pct"] == pytest.approx(30.0)


def test_r0_mass_goes_where_the_table_says(thermo: Thermo) -> None:
    feed = _feed(thermo, FccR0)
    _, params = FccR0.example_case()
    res = FccR0().solve({"feed_in": feed}, params, thermo)
    mass_in = feed.mass_flow
    assert res.outlets["gasoline_out"].mass_flow / mass_in == pytest.approx(0.48, rel=1e-9)
    assert res.outlets["coke_out"].mass_flow / mass_in == pytest.approx(0.05, rel=1e-9)
    assert sum(s.mass_flow for s in res.outlets.values()) == pytest.approx(mass_in, rel=1e-12)


def test_r1_second_order_gas_oil_closed_form(thermo: Thermo) -> None:
    """Weekman: y1 = 1/(1 + K*t) for constant phi, K = k12 + k13."""
    params = _iso(0.5, 0.2, 0.0)
    params.update(contact_time_s=3.0, deactivation_alpha_per_s=0.0)
    res = FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)
    y1 = 1.0 / (1.0 + 0.7 * 3.0)
    assert res.info["conversion_wt_pct"] == pytest.approx(100.0 * (1.0 - y1), rel=1e-8)


def test_r1_decay_maps_to_the_undecayed_clock(thermo: Thermo) -> None:
    """phi = exp(-alpha*t) substitutes theta = (1 - exp(-alpha*t))/alpha into y1."""
    alpha = 0.3
    params = _iso(0.5, 0.2, 0.0)
    params.update(contact_time_s=3.0, deactivation_alpha_per_s=alpha)
    res = FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)
    theta = (1.0 - math.exp(-alpha * 3.0)) / alpha
    assert res.info["conversion_wt_pct"] == pytest.approx(100.0 * 0.7 * theta / (1.0 + 0.7 * theta), rel=1e-8)


def test_r1_gasoline_integral_by_quadrature(thermo: Thermo) -> None:
    """y2(t) = k12*integral(y1(s)**2*exp(-k2*(t - s)), s = 0..t), independent of the ODE."""
    k12, k13, k23, t = 0.5, 0.2, 0.3, 3.0
    big_k = k12 + k13

    def integrand(s: float) -> float:
        return float(math.exp(-k23 * (t - s)) / (1.0 + big_k * s) ** 2)

    gasoline = k12 * quad(integrand, 0.0, t, epsabs=1e-12, epsrel=1e-12)[0]
    params = _iso(k12, k13, k23)
    params.update(contact_time_s=t, deactivation_alpha_per_s=0.0)
    res = FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)
    assert res.info["gasoline_wt_pct"] == pytest.approx(100.0 * gasoline, rel=1e-7)


def test_r1_four_lumps_share_the_mass(thermo: Thermo) -> None:
    """k14, k24 divert to coke; gas-oil loss is unchanged when the total K is."""
    params = _iso(0.5, 0.1, 0.2, k14=0.1, k24=0.1)
    params.update(contact_time_s=3.0, deactivation_alpha_per_s=0.0)
    res = FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)
    assert res.info["conversion_wt_pct"] == pytest.approx(100.0 * 0.7 * 3.0 / (1.0 + 0.7 * 3.0), rel=1e-8)
    assert res.info["coke_wt_pct"] > 0.0
    total = sum(res.info[f"{k}_wt_pct"] for k in ("dry_gas", "lpg", "gasoline", "lco", "slurry", "coke"))
    assert total == pytest.approx(100.0, rel=1e-12)


def test_r1_arrhenius_uses_the_given_temperature(thermo: Thermo) -> None:
    params = _iso(1.0, 0.0, 0.0)
    params["kinetics"]["gasoil_to_gasoline"] = {"k0_per_s": 2.0, "Ea_J_mol": R * 800.0 * math.log(2.0)}
    params.update(contact_time_s=2.0, deactivation_alpha_per_s=0.0)
    res = FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)
    assert res.info["conversion_wt_pct"] == pytest.approx(100.0 * 2.0 / 3.0, rel=1e-8)


def test_r1_heat_balance_closes_and_cools_along_the_riser(thermo: Thermo) -> None:
    """Catalyst heat = stream sensible rise + heat of cracking, with T_mix > T_out."""
    feed = _feed(thermo, FccR1)
    _, params = FccR1.example_case()
    res = FccR1().solve({"feed_in": feed}, params, thermo)
    i = res.info
    assert feed.T < i["T_out_K"] < i["T_mix_K"] < params["T_regen_K"]
    assert i["catalyst_heat_W"] == pytest.approx(res.duty_W + i["reaction_heat_W"], rel=1e-8)
    expected = feed.mass_flow * i["coke_wt_pct"] / 100.0 * params["coke_heat_of_combustion_J_kg"]
    assert i["coke_burn_heat_W"] == pytest.approx(expected, rel=1e-9)
    assert abs(i["T_closure_gap_K"]) < 5.0


@pytest.mark.parametrize("key", ["yield_table", "conversion_wt_pct", "T_out", "P_out"])
def test_r0_refuses_a_missing_input(thermo: Thermo, key: str) -> None:
    _, params = FccR0.example_case()
    del params[key]
    with pytest.raises(FccSpecError, match=key):
        FccR0().solve({"feed_in": _feed(thermo, FccR0)}, params, thermo)


@pytest.mark.parametrize(
    ("column", "value", "match"),
    [
        ("coke_wt_pct", [4.0, 7.0], "sums to"),
        ("coke_wt_pct", [4.0], "same length"),
        ("lpg_wt_pct", [-1.0, 18.0], "negative"),
        ("conversion_wt_pct", [60.0, 60.0], "strictly increasing"),
    ],
)
def test_r0_refuses_a_bad_table(thermo: Thermo, column: str, value: list[float], match: str) -> None:
    _, params = FccR0.example_case()
    table = deepcopy(params["yield_table"])
    table[column] = value
    with pytest.raises(FccSpecError, match=match):
        FccR0().solve({"feed_in": _feed(thermo, FccR0)}, {**params, "yield_table": table}, thermo)


def test_r0_checks_the_conversion_definition(thermo: Thermo) -> None:
    _, params = FccR0.example_case()
    table = deepcopy(params["yield_table"])
    table["lco_wt_pct"] = [27.0, 16.0]
    table["gasoline_wt_pct"] = [45.0, 52.0]
    with pytest.raises(FccSpecError, match="100 - conversion"):
        FccR0().solve({"feed_in": _feed(thermo, FccR0)}, {**params, "yield_table": table}, thermo)


def test_r0_never_extrapolates(thermo: Thermo) -> None:
    _, params = FccR0.example_case()
    with pytest.raises(FccSpecError, match="no extrapolation"):
        FccR0().solve({"feed_in": _feed(thermo, FccR0)}, {**params, "conversion_wt_pct": 85.0}, thermo)


@pytest.mark.parametrize(
    "key",
    [
        "kinetics",
        "contact_time_s",
        "deactivation_alpha_per_s",
        "dry_gas_fraction",
        "lco_fraction",
        "P_out",
        "catalyst_to_oil",
        "cp_cat_J_kgK",
        "T_regen_K",
        "heat_of_cracking_J_kg",
        "coke_heat_of_combustion_J_kg",
    ],
)
def test_r1_refuses_a_missing_input(thermo: Thermo, key: str) -> None:
    _, params = FccR1.example_case()
    del params[key]
    with pytest.raises(FccSpecError, match=key):
        FccR1().solve({"feed_in": _feed(thermo, FccR1)}, params, thermo)


def test_r1_refuses_incomplete_and_unknown_paths(thermo: Thermo) -> None:
    _, params = FccR1.example_case()
    kinetics = dict(params["kinetics"])
    del kinetics["gasoline_to_coke"]
    with pytest.raises(FccSpecError, match="gasoline_to_coke"):
        FccR1().solve({"feed_in": _feed(thermo, FccR1)}, {**params, "kinetics": kinetics}, thermo)
    kinetics = {**params["kinetics"], "invented": {"k0_per_s": 1.0, "Ea_J_mol": 1.0}}
    with pytest.raises(FccSpecError, match="unknown paths"):
        FccR1().solve({"feed_in": _feed(thermo, FccR1)}, {**params, "kinetics": kinetics}, thermo)


def test_r1_refuses_a_fraction_outside_the_unit_interval(thermo: Thermo) -> None:
    _, params = FccR1.example_case()
    with pytest.raises(FccSpecError, match="lco_fraction"):
        FccR1().solve({"feed_in": _feed(thermo, FccR1)}, {**params, "lco_fraction": 1.5}, thermo)


def test_a_cold_regenerator_is_refused(thermo: Thermo) -> None:
    _, params = FccR1.example_case()
    with pytest.raises(FccSpecError, match="T_regen_K"):
        FccR1().solve({"feed_in": _feed(thermo, FccR1)}, {**params, "T_regen_K": 450.0}, thermo)


def test_a_feed_with_a_formula_is_refused(thermo: Thermo) -> None:
    feed = thermo.flash_pt({"nC7": 1.0}, 700.0, 3.0e5, 1.0)
    with pytest.raises(FccSpecError, match="#222"):
        FccR0().solve({"feed_in": feed}, FccR0.example_case()[1], thermo)
