"""hcu R0 and R1 tests: series closed form, element closure, reduction, refusals."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.refining.hcu import HcuR0, HcuR1, HcuSpecError


def _inlets(thermo: Thermo, hydrogen: float = 10.0) -> dict[str, Any]:
    feeds, _ = HcuR0.example_case()
    v, h = feeds["vgo_in"], feeds["hydrogen_in"]
    return {
        "vgo_in": thermo.flash_pt(v["composition"], v["T"], v["P"], v["molar_flow"]),
        "hydrogen_in": thermo.flash_pt(h["composition"], h["T"], h["P"], hydrogen),
    }


def _chain(k1: float, k2: float, k3: float) -> dict[str, Any]:
    """Only the three chain paths, Ea = 0, one hour of contact."""
    zero = {"k0_per_s": 0.0, "Ea_J_mol": 0.0}

    def on(k: float) -> dict[str, float]:
        return {"k0_per_s": k, "Ea_J_mol": 0.0}

    _, params = HcuR1.example_case()
    params["kinetics"] = {
        "vgo_to_diesel": on(k1),
        "vgo_to_naphtha": zero,
        "vgo_to_gas": zero,
        "diesel_to_naphtha": on(k2),
        "diesel_to_gas": zero,
        "naphtha_to_gas": on(k3),
    }
    return params


def test_r1_series_reactions_match_bateman(thermo: Thermo) -> None:
    """A -> 2B -> 4C first order: n_B = 2*A0*k1/(k2 - k1)*(e1 - e2) by hand."""
    k1, k2 = 2.0e-4, 5.0e-4
    res = HcuR1().solve(_inlets(thermo), _chain(k1, k2, 0.0), thermo)
    tau = 3600.0
    e1, e2 = math.exp(-k1 * tau), math.exp(-k2 * tau)
    assert res.outlets["unconverted_out"].molar_flow == pytest.approx(e1, rel=1e-10)
    diesel = 2.0 * k1 / (k2 - k1) * (e1 - e2)
    assert res.outlets["diesel_out"].molar_flow == pytest.approx(diesel, rel=1e-10)
    # Conservation of chain carbon: 24*A + 12*B + 6*C = 24.
    naphtha = res.outlets["naphtha_out"].molar_flow
    assert 24.0 * e1 + 12.0 * diesel + 6.0 * naphtha == pytest.approx(24.0, rel=1e-10)


def test_r1_elements_and_mass_close_with_all_paths(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    _, params = HcuR1.example_case()
    res = HcuR1().solve(inlets, params, thermo)
    mass_in, atoms_in = mass_and_atoms(inlets.values())
    mass_out, atoms_out = mass_and_atoms(res.outlets.values())
    assert mass_out == pytest.approx(mass_in, rel=1e-10)
    for element, value in atoms_in.items():
        assert atoms_out[element] == pytest.approx(value, rel=1e-10)


def test_r1_reduces_to_r0_at_its_own_yields(thermo: Thermo) -> None:
    """Direct paths are chain sums, so R0 given R1's yields reproduces R1 exactly."""
    inlets = _inlets(thermo)
    _, params = HcuR1.example_case()
    r1 = HcuR1().solve(inlets, params, thermo)
    x = r1.info["conversion_wt_pct"]
    table = {
        "conversion_wt_pct": [x - 1.0, x + 1.0],
        "diesel_wt_pct": [r1.info["diesel_wt_pct"]] * 2,
        "naphtha_wt_pct": [r1.info["naphtha_wt_pct"]] * 2,
    }
    r0 = HcuR0().solve(
        inlets,
        {"conversion_wt_pct": x, "yield_table": table, "T_out": params["T_out"], "P_out": params["P_out"]},
        thermo,
    )
    for port, state in r1.outlets.items():
        assert r0.outlets[port].molar_flow == pytest.approx(state.molar_flow, rel=1e-9)
    assert r0.duty_W == pytest.approx(r1.duty_W, rel=1e-8)


def test_r1_zero_rates_leave_the_feed_split(thermo: Thermo) -> None:
    res = HcuR1().solve(_inlets(thermo), _chain(0.0, 0.0, 0.0), thermo)
    assert res.outlets["unconverted_out"].molar_flow == pytest.approx(1.0)
    assert res.outlets["naphtha_out"].molar_flow == 0.0
    assert res.info["h2_consumed_mol_s"] == pytest.approx(0.0, abs=1e-12)


def test_r1_arrhenius_and_lhsv(thermo: Thermo) -> None:
    """k = k0*exp(-Ea/RT) over tau = 3600/LHSV: A = exp(-k*tau) with k*tau = 1."""
    params = _chain(0.0, 0.0, 0.0)
    params["kinetics"]["vgo_to_diesel"] = {"k0_per_s": 1.0 / 3600.0, "Ea_J_mol": 0.0}
    res = HcuR1().solve(_inlets(thermo), {**params, "lhsv_per_h": 0.5}, thermo)
    assert res.outlets["unconverted_out"].molar_flow == pytest.approx(math.exp(-2.0), rel=1e-10)


def test_r0_chain_stoichiometry_by_hand(thermo: Thermo) -> None:
    """70 wt%: xi1 = 0.7; 40 wt% diesel on 338.6538 g/mol VGO is 0.795 mol/s nC12."""
    _, params = HcuR0.example_case()
    res = HcuR0().solve(_inlets(thermo), params, thermo)
    diesel = 0.40 * 338.6538 / 170.33484
    naphtha = 0.20 * 338.6538 / 86.17536
    xi1 = 0.7
    xi2 = 2.0 * xi1 - diesel
    xi3 = 2.0 * xi2 - naphtha
    assert res.outlets["diesel_out"].molar_flow == pytest.approx(diesel, rel=1e-10)
    assert res.info["h2_consumed_mol_s"] == pytest.approx(xi1 + xi2 + xi3, rel=1e-10)
    assert res.outlets["gas_out"].composition["C3"] * res.outlets["gas_out"].molar_flow == pytest.approx(
        2.0 * xi3, rel=1e-10
    )


def test_cracking_is_exothermic_on_the_formation_basis(thermo: Thermo) -> None:
    """Isothermal bed: paraffin hydrocracking releases heat, so duty < 0."""
    inlets = _inlets(thermo)
    _, params = HcuR1.example_case()
    assert HcuR1().solve(inlets, params, thermo).duty_W < 0.0


@pytest.mark.parametrize("key", ["yield_table", "conversion_wt_pct", "T_out", "P_out"])
def test_r0_refuses_a_missing_input(thermo: Thermo, key: str) -> None:
    _, params = HcuR0.example_case()
    del params[key]
    with pytest.raises(HcuSpecError, match=key):
        HcuR0().solve(_inlets(thermo), params, thermo)


@pytest.mark.parametrize("key", ["kinetics", "T_bed_K", "lhsv_per_h", "T_out", "P_out"])
def test_r1_refuses_a_missing_input(thermo: Thermo, key: str) -> None:
    _, params = HcuR1.example_case()
    del params[key]
    with pytest.raises(HcuSpecError, match=key):
        HcuR1().solve(_inlets(thermo), params, thermo)


def test_r1_refuses_incomplete_and_unknown_paths(thermo: Thermo) -> None:
    _, params = HcuR1.example_case()
    kinetics = dict(params["kinetics"])
    del kinetics["naphtha_to_gas"]
    with pytest.raises(HcuSpecError, match="naphtha_to_gas"):
        HcuR1().solve(_inlets(thermo), {**params, "kinetics": kinetics}, thermo)
    kinetics = {**params["kinetics"], "invented": {"k0_per_s": 1.0, "Ea_J_mol": 1.0}}
    with pytest.raises(HcuSpecError, match="unknown paths"):
        HcuR1().solve(_inlets(thermo), {**params, "kinetics": kinetics}, thermo)


def test_r0_refuses_extrapolation_and_impossible_yields(thermo: Thermo) -> None:
    _, params = HcuR0.example_case()
    with pytest.raises(HcuSpecError, match="no extrapolation"):
        HcuR0().solve(_inlets(thermo), {**params, "conversion_wt_pct": 95.0}, thermo)
    table = {**params["yield_table"], "naphtha_wt_pct": [80.0, 90.0]}
    with pytest.raises(HcuSpecError, match="negative gas yield"):
        HcuR0().solve(_inlets(thermo), {**params, "yield_table": table}, thermo)
    table = {**params["yield_table"], "diesel_wt_pct": [35.0]}
    with pytest.raises(HcuSpecError, match="same length"):
        HcuR0().solve(_inlets(thermo), {**params, "yield_table": table}, thermo)


def test_too_little_hydrogen_is_refused(thermo: Thermo) -> None:
    _, params = HcuR1.example_case()
    with pytest.raises(HcuSpecError, match="hydrogen"):
        HcuR1().solve(_inlets(thermo, hydrogen=0.01), params, thermo)


def test_a_pseudo_vgo_is_refused(thermo: Thermo) -> None:
    import ngdesign.units.refining.fcc  # noqa: F401  (registers the fcc_vgo pseudo)

    inlets = _inlets(thermo)
    inlets["vgo_in"] = thermo.flash_pt({"fcc_vgo": 1.0}, 650.0, 1.5e7, 1.0)
    with pytest.raises(HcuSpecError, match="#222"):
        HcuR0().solve(inlets, HcuR0.example_case()[1], thermo)


def test_impure_hydrogen_is_refused(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    inlets["hydrogen_in"] = thermo.flash_pt({"H2": 0.9, "C1": 0.1}, 650.0, 1.5e7, 10.0)
    with pytest.raises(HcuSpecError, match="pure H2"):
        HcuR0().solve(inlets, HcuR0.example_case()[1], thermo)
