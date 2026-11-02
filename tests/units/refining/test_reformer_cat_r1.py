"""reformer_cat R1 tests (``specs/backend/units/reformer_cat.md``)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.reactors.plug_flow import PlugFlowError
from ngdesign.units.refining.reformer_kinetic import (
    CatalyticReformerR1,
    ReformerKineticError,
    _smith_to_contract,
)

MCH, TOL, HYD = "methylcyclohexane", "toluene", "H2"
OFF = {"k0": 0.0, "Ea": 0.0}


def _feed(thermo: Thermo, cls: Any = None) -> dict[str, Any]:
    f = CatalyticReformerR1.example_case()[0]["naphtha_in"]
    return {"naphtha_in": thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])}


def test_conversion_unit_factors() -> None:
    """1 lb-mol/(h lb_cat atm) at 10 atm: 1*(1000/3600)*10 = 2.77777778 mol/(kg_cat s);
    b = 18000 R: Ea = R*18000/1.8 = 83144.6262 J/mol."""
    k0, ea = _smith_to_contract(1.0, 18000.0, 1.0, 10.0)
    assert k0 == pytest.approx(2.77777778, rel=1e-8)
    assert ea == pytest.approx(83144.6262, rel=1e-8)


def test_dehydrogenation_reaches_the_hand_equilibrium(thermo: Thermo) -> None:
    """MCH <-> toluene + 3 H2 at 650 K, 20 atm; K1 = exp(46.15 - 25000/T) = 2183.0135 atm3
    (test values, NOT Smith's).  y_A*y_H**3*P**3/y_N = K solves by hand, from feed MCH 1 +
    H2 5, to xi = 0.303678901 mol/s, y_MCH 0.100754942, y_tol 0.0439411501, y_H2 0.855303908."""
    p = 2026500.0
    inlet = thermo.flash_pt({MCH: 1.0 / 6.0, HYD: 5.0 / 6.0}, 650.0, p, 6.0)
    params = {
        "beds": [{"catalyst_mass_kg": 1.0e4, "inlet_T_K": 650.0, "thermal": "isothermal"}],
        "bulk_density_kg_m3": 600.0,
        "kinetics": {
            "dehydro": {"k0": 2.0, "Ea": 0.0, "A_K": 46.15, "B_K": 25000.0},
            "n_to_p": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
            "hc_n": OFF,
            "hc_p": OFF,
        },
    }
    res = CatalyticReformerR1().solve({"naphtha_in": inlet}, params, thermo)
    xi = res.info["extent_dehydro_b0_mol_s"]
    assert xi == pytest.approx(0.303678901, rel=1e-6)
    total = 6.0 + 3.0 * xi
    q = (xi / total) * ((5.0 + 3.0 * xi) / total) ** 3 * 20.0**3 / ((1.0 - xi) / total)
    assert q == pytest.approx(math.exp(46.15 - 25000.0 / 650.0), rel=1e-5)


def test_zero_rates_leave_only_heaters_and_split(thermo: Thermo) -> None:
    inlets = _feed(thermo)
    _, params = CatalyticReformerR1.example_case()
    zero = {
        "dehydro": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
        "n_to_p": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
        "hc_n": OFF,
        "hc_p": OFF,
    }
    res = CatalyticReformerR1().solve(inlets, {**params, "kinetics": zero}, thermo)
    info = res.info
    heaters = sum(v for k, v in info.items() if k.startswith("heater_duty_"))
    assert res.duty_W == pytest.approx(heaters + info["split_enthalpy_W"], rel=1e-9)
    for key in ("bed_dT_b0_K", "bed_dT_b1_K", "bed_dT_b2_K"):
        assert info[key] == pytest.approx(0.0, abs=1e-6)
    assert info["heater_duty_b1_W"] == pytest.approx(0.0, abs=1e-6)


def test_three_adiabatic_beds_cool_and_close(thermo: Thermo) -> None:
    inlets = _feed(thermo)
    res = CatalyticReformerR1().solve(inlets, CatalyticReformerR1.example_case()[1], thermo)
    info = res.info
    assert all(info[f"bed_dT_b{k}_K"] < 0.0 for k in range(3))
    assert sum(info[f"heater_duty_b{k}_W"] for k in range(3)) > 0.0
    mass_in, atoms_in = mass_and_atoms(inlets.values())
    mass_out, atoms_out = mass_and_atoms(res.outlets.values())
    assert mass_out == pytest.approx(mass_in, rel=1e-9)
    for element, value in atoms_in.items():
        assert atoms_out[element] == pytest.approx(value, rel=1e-9), element
    assert 0.0 < info["aromatics_out_mol_frac_C6plus"] < 1.0
    assert set(res.outlets["h2_out"].composition) <= {"H2", "C1", "C2", "C3", "nC4"}


def test_the_preset_is_refused(thermo: Thermo) -> None:
    params = {**CatalyticReformerR1.example_case()[1], "kinetics": "smith1959"}
    with pytest.raises(ReformerKineticError, match="preset"):
        CatalyticReformerR1().solve(_feed(thermo), params, thermo)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"beds": []}, "beds"),
        ({"beds": [{"catalyst_mass_kg": 0.0, "inlet_T_K": 700.0}]}, "catalyst_mass_kg"),
        ({"beds": [{"catalyst_mass_kg": 1.0, "inlet_T_K": 0.0}]}, "inlet_T_K"),
        ({"beds": [{"catalyst_mass_kg": 1.0, "inlet_T_K": 700.0, "thermal": "cooled"}]}, "thermal"),
        ({"bulk_density_kg_m3": 0.0}, "bulk_density_kg_m3"),
        ({"kinetics": {}}, "dehydro"),
        ({"kinetics": None}, "explicit"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {**CatalyticReformerR1.example_case()[1], **change}
    with pytest.raises(ReformerKineticError, match=match):
        CatalyticReformerR1().solve(_feed(thermo), params, thermo)


def test_missing_field_named(thermo: Thermo) -> None:
    _, params = CatalyticReformerR1.example_case()
    kinetics = {**params["kinetics"], "dehydro": {"k0": 1.0, "Ea": 0.0, "A_K": 1.0}}
    with pytest.raises(ReformerKineticError, match="B_K"):
        CatalyticReformerR1().solve(_feed(thermo), {**params, "kinetics": kinetics}, thermo)


def test_feed_outside_the_slate_refused(thermo: Thermo) -> None:
    inlet = thermo.flash_pt({"nC6": 1.0}, 700.0, 2.0e6, 1.0)
    with pytest.raises(ReformerKineticError, match="#222"):
        CatalyticReformerR1().solve({"naphtha_in": inlet}, CatalyticReformerR1.example_case()[1], thermo)


def test_hydrogen_starved_cracking_depletes(thermo: Thermo) -> None:
    """No H2 in the feed while cracking consumes it: pfr's refusal."""
    inlet = thermo.flash_pt({"nC7": 1.0}, 770.0, 2.0e6, 1.0)
    _, params = CatalyticReformerR1.example_case()
    kinetics = {
        "dehydro": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
        "n_to_p": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
        "hc_n": OFF,
        "hc_p": {"k0": 1.0, "Ea": 0.0},
    }
    with pytest.raises(PlugFlowError, match="depletes"):
        CatalyticReformerR1().solve({"naphtha_in": inlet}, {**params, "kinetics": kinetics}, thermo)
