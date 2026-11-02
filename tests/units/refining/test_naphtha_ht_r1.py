"""naphtha_ht R1 tests (``specs/backend/units/naphtha_ht.md``)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.reactors.plug_flow import PlugFlowError
from ngdesign.units.refining.hdt_kinetic import HdtKineticError, NaphthaHydrotreaterR1
from ngdesign.units.refining.reactors_hdt import NaphthaHydrotreater


def _law(k0: float, *orders: str, units: str = "mol/(kg_cat·s)") -> dict[str, Any]:
    return {
        "rate_units": units,
        "k0": k0,
        "Ea": 0.0,
        "orders": dict.fromkeys(orders, 1.0),
        "basis": "mole_fraction",
    }


def _hds_inlets(thermo: Thermo) -> dict[str, Any]:
    z = {"thiophene": 0.01 / 1.01, "nC7": 1.0 / 1.01}
    return {
        "naphtha_in": thermo.flash_pt(z, 620.0, 3.0e6, 1.01),
        "h2_in": thermo.flash_pt({"H2": 1.0}, 620.0, 3.0e6, 5.0),
    }


def _bed(mass: float, **more: Any) -> dict[str, Any]:
    return {"catalyst_mass_kg": mass, "thermal": "isothermal", **more}


def _flows(res: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for state in res.outlets.values():
        for cid, n in state.component_flows().items():
            out[cid] = out.get(cid, 0.0) + n
    return out


def test_first_order_with_mole_change_closed_form(thermo: Thermo) -> None:
    """thiophene + 4 H2 -> nC4 + H2S, r' = k*y_T, F_tot = F0 - 3*xi:
    W(X) = [3*xi + (F0 - 3*F_T0)*ln(F_T0/(F_T0 - xi))]/k.  With k = 0.02, F0 = 6.01,
    F_T0 = 0.01 and X = 0.9, W = 689.822943 kg; W is the input and X the output."""
    f0, ft0, k, x = 6.01, 0.01, 0.02, 0.9
    xi = x * ft0
    w = (3.0 * xi + (f0 - 3.0 * ft0) * math.log(ft0 / (ft0 - xi))) / k
    assert w == pytest.approx(689.822943, rel=1e-8)
    params = {
        "beds": [_bed(w)],
        "bulk_density_kg_m3": 800.0,
        "kinetics": {"hds_thiophene": _law(k, "thiophene")},
    }
    res = NaphthaHydrotreaterR1().solve(_hds_inlets(thermo), params, thermo)
    flows = _flows(res)
    assert flows["thiophene"] == pytest.approx(0.001, rel=1e-6)
    assert flows["H2"] == pytest.approx(4.964, rel=1e-7)
    assert flows["nC4"] == pytest.approx(0.009, rel=1e-7)
    assert flows["H2S"] == pytest.approx(0.009, rel=1e-7)


def test_reduces_to_r0_at_full_conversion(thermo: Thermo) -> None:
    """Spec reduction at k*W/F = 25: the spec's 60 would cross the integrator's terminal
    depletion event (1e-14 of F), so conversion stops at 1 - 1.4e-11."""
    feeds, _ = NaphthaHydrotreater.example_case()
    z = {"nC7": 0.97, "thiophene": 0.02, "pyridine": 0.01}
    inlets = {
        "naphtha_in": thermo.flash_pt(z, 620.0, 3.0e6, 1.0),
        "h2_in": thermo.flash_pt({"H2": 1.0}, 620.0, 3.0e6, 3.0),
    }
    k = 1.0e4
    res1 = NaphthaHydrotreaterR1().solve(
        inlets,
        {
            "beds": [_bed(25.0 * 4.0 / k * 1.02)],
            "bulk_density_kg_m3": 800.0,
            "kinetics": {"hds_thiophene": _law(k, "thiophene"), "hdn_pyridine": _law(k, "pyridine")},
        },
        thermo,
    )
    res0 = NaphthaHydrotreater().solve(
        inlets,
        {
            "sulfur_removal_frac": 1.0,
            "nitrogen_removal_frac": 1.0,
            "pentene_conversion": 0.0,
            "benzene_conversion": 0.0,
            "T_out": 620.0,
            "P_out": 3.0e6,
        },
        thermo,
    )
    a, b = _flows(res1), _flows(res0)
    for cid, n in b.items():
        if n > 1.0e-9:
            assert a[cid] == pytest.approx(n, rel=1e-8), cid
    assert res1.duty_W == pytest.approx(res0.duty_W, rel=1e-6)


def test_two_adiabatic_beds_close(thermo: Thermo) -> None:
    feeds, params = NaphthaHydrotreaterR1.example_case()
    inlets = {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}
    res = NaphthaHydrotreaterR1().solve(inlets, params, thermo)
    info = res.info
    t_mix = 610.0
    assert info["bed_T_out_b0_K"] > t_mix - 5.0
    parts = sum(info[k] for k in info if k.startswith(("heater_duty_", "bed_duty_")))
    assert parts == pytest.approx(res.duty_W - info["split_enthalpy_W"], rel=1e-9)
    mass_in, atoms_in = mass_and_atoms(inlets.values())
    mass_out, atoms_out = mass_and_atoms(res.outlets.values())
    assert mass_out == pytest.approx(mass_in, rel=1e-9)
    for element, value in atoms_in.items():
        assert atoms_out[element] == pytest.approx(value, rel=1e-9), element


def test_omitted_reaction_is_inactive(thermo: Thermo) -> None:
    params = {
        "beds": [_bed(10.0)],
        "bulk_density_kg_m3": 800.0,
        "kinetics": {"hds_thiophene": _law(0.02, "thiophene")},
    }
    res = NaphthaHydrotreaterR1().solve(_hds_inlets(thermo), params, thermo)
    assert res.info["inactive_arom_sat"] == 1.0
    assert "inactive_hds_thiophene" not in res.info


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"beds": []}, "beds"),
        ({"beds": [{"catalyst_mass_kg": 0.0}]}, "catalyst_mass_kg"),
        ({"beds": [{"catalyst_mass_kg": 1.0, "thermal": "cooled"}]}, "thermal"),
        ({"beds": [{"catalyst_mass_kg": 1.0, "inlet_T_K": 0.0}]}, "inlet_T_K"),
        ({"bulk_density_kg_m3": 0.0}, "bulk_density_kg_m3"),
        ({"kinetics": {}}, "at least one"),
        ({"kinetics": {"invented": _law(1.0, "H2")}}, "kinetics"),
        ({"kinetics": {"hds_thiophene": {"k0": 1.0}}}, "kinetics"),
        ({"kinetics": {"hds_thiophene": _law(1.0, "thiophene", units="mol/(m3·s)")}}, "kinetics"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {"beds": [_bed(1.0)], "bulk_density_kg_m3": 800.0, "kinetics": {}, **change}
    with pytest.raises(HdtKineticError, match=match):
        NaphthaHydrotreaterR1().solve(_hds_inlets(thermo), params, thermo)


def test_missing_bulk_density(thermo: Thermo) -> None:
    with pytest.raises(HdtKineticError, match="bulk_density_kg_m3"):
        NaphthaHydrotreaterR1().solve(_hds_inlets(thermo), {"beds": [_bed(1.0)]}, thermo)


def test_pseudo_refused(thermo: Thermo) -> None:
    feeds, _ = NaphthaHydrotreater.example_case()
    inlets = {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}
    with pytest.raises(HdtKineticError, match="#222"):
        NaphthaHydrotreaterR1().solve(inlets, NaphthaHydrotreaterR1.example_case()[1], thermo)


def test_empty_gas_outlet_refused(thermo: Thermo) -> None:
    """Hydrogen fully consumed by a fast saturation and no H2S, NH3 formed cannot occur
    without excess H2; a feed with no H2 and no reaction leaves gas_out empty."""
    inlets = {
        "naphtha_in": thermo.flash_pt({"nC7": 0.99, "1-pentene": 0.01}, 620.0, 3.0e6, 1.0),
        "h2_in": thermo.flash_pt({"nC7": 1.0}, 620.0, 3.0e6, 1.0),
    }
    params = {
        "beds": [_bed(1.0)],
        "bulk_density_kg_m3": 800.0,
        "kinetics": {"hds_thiophene": _law(0.0, "thiophene")},
    }
    with pytest.raises(HdtKineticError, match="gas_out"):
        NaphthaHydrotreaterR1().solve(inlets, params, thermo)


def test_integration_failure_propagates(thermo: Thermo) -> None:
    """Zero-order hydrogen uptake depletes the thiophene: pfr's refusal, unchanged."""
    params = {
        "beds": [_bed(1.0e4)],
        "bulk_density_kg_m3": 800.0,
        "kinetics": {"hds_thiophene": _law(1.0)},
    }
    with pytest.raises(PlugFlowError, match="depletes"):
        NaphthaHydrotreaterR1().solve(_hds_inlets(thermo), params, thermo)
