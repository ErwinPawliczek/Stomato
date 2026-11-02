"""batch_reactor tests: closed forms, the PFR equivalence and refusals."""

from __future__ import annotations

import math
from typing import Any

import pytest
from scipy.integrate import quad

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.reactors.batch_reactor import BatchReactor, BatchReactorError
from ngdesign.units.reactors.pfr import PfrR1
from ngdesign.units.reactors.plug_flow import PlugFlowError


def _charge(thermo: Thermo, flow: float = 1.0) -> Any:
    return thermo.flash_pt({"nC4": 1.0}, 500.0, 2.0e5, flow)


def _isom(**change: Any) -> dict[str, Any]:
    params = dict(BatchReactor.example_case()[1])
    params.update(change)
    return params


def test_first_order_closed_form(thermo: Thermo) -> None:
    """X = 1 - exp(-k*t) with k = 1e3*exp(-5e4/(R*500)) = 5.97912989e-3 1/s."""
    k = 1.0e3 * math.exp(-5.0e4 / (R * 500.0))
    res = BatchReactor().solve({"charge_in": _charge(thermo)}, _isom(turnaround_s=0.0), thermo)
    expected = 1.0 - math.exp(-k * 96.0)
    assert res.info["conversion_nC4_isom"] == pytest.approx(expected, rel=1e-7)
    assert res.outlets["outlet"].component_flows()["iC4"] == pytest.approx(expected, rel=1e-7)


def test_turnaround_sets_the_batch_size_not_the_conversion(thermo: Thermo) -> None:
    """Same intensive trajectory; the charge is F*t_cycle."""
    res = BatchReactor().solve({"charge_in": _charge(thermo, 2.0)}, _isom(), thermo)
    assert res.info["charge_mol"] == pytest.approx(2.0 * 120.0)
    assert res.info["cycle_time_s"] == 120.0
    k = 1.0e3 * math.exp(-5.0e4 / (R * 500.0))
    assert res.info["conversion_nC4_isom"] == pytest.approx(1.0 - math.exp(-k * 96.0), rel=1e-7)
    assert res.info["extent_isom_mol"] == pytest.approx(240.0 * (1.0 - math.exp(-k * 96.0)), rel=1e-7)
    assert res.outlets["outlet"].molar_flow == pytest.approx(2.0)


def test_equals_the_isobaric_pfr_at_equal_residence_time(thermo: Thermo) -> None:
    """Delta n = 0: batch time t maps onto V = F*t/c.  Reduction to pfr R1, whose
    spec value X = 0.437463482 at t = 2*48.108942 s is independent of this unit."""
    feeds, pfr_params = PfrR1.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    pfr = PfrR1().solve({"inlet": inlet}, pfr_params, thermo)
    c = 2.0e5 / (R * 500.0)
    batch = BatchReactor().solve({"charge_in": inlet}, _isom(batch_time_s=2.0 * c, turnaround_s=0.0), thermo)
    assert batch.outlets["outlet"].component_flows()["iC4"] == pytest.approx(
        pfr.outlets["outlet"].component_flows()["iC4"], rel=1e-7
    )
    assert batch.info["conversion_nC4_isom"] == pytest.approx(0.437463482, rel=1e-7)
    assert batch.duty_W == pytest.approx(pfr.duty_W, rel=1e-7)


def test_second_order_with_mole_change_by_quadrature(thermo: Thermo) -> None:
    """2 C2H4 -> 1-butene, isobaric: the volume shrinks with the moles.

    With v = N*R*T/P: d(xi)/dt = (k/2)*(N0 - 2*xi)**2*P/((N0 - xi)*R*T), so
    t(xi) = (2*R*T/(k*P)) * integral (N0 - xi)/(N0 - 2*xi)**2 d(xi), by quadrature
    here, independent of the unit's ODE.
    """
    k, temp, p = 5.0e-3, 600.0, 5.0e5
    xi_target = 0.3

    def integrand(xi: float) -> float:
        return (1.0 - xi) / (1.0 - 2.0 * xi) ** 2

    t_end = 2.0 * R * temp / (k * p) * quad(integrand, 0.0, xi_target, epsabs=1e-12, epsrel=1e-12)[0]
    params = {
        "reaction_set": {
            "id": "dimer",
            "components": ["C2H4", "1-butene"],
            "reactions": [
                {
                    "id": "dim",
                    "stoichiometry": {"C2H4": -2.0, "1-butene": 1.0},
                    "base_component": "C2H4",
                    "provenance": "test kinetics, cstr spec R1-B",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": k,
                        "Ea": 0.0,
                        "orders": {"C2H4": 2.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "batch_time_s": t_end,
    }
    charge = thermo.flash_pt({"C2H4": 1.0}, temp, p, 1.0)
    res = BatchReactor().solve({"charge_in": charge}, params, thermo)
    # rate() is the base-component rate k*c**2; the extent divides it by |nu| = 2.
    assert res.info["extent_dim_mol"] / res.info["charge_mol"] == pytest.approx(xi_target, rel=1e-6)


def test_adiabatic_temperature_and_closure() -> None:
    """Adiabatic isobaric: the ODE and the exact closure agree on an ideal package."""
    registry.discover()
    thermo: Thermo = registry.create("thermo", "ideal-raoult")
    res = BatchReactor().solve({"charge_in": _charge(thermo)}, _isom(thermal="adiabatic"), thermo)
    assert res.duty_W == pytest.approx(0.0, abs=1e-8)
    assert res.outlets["outlet"].T > 500.0
    assert abs(res.info["T_closure_gap_K"]) < 1.0e-4


def test_fixed_duty_is_averaged_over_the_cycle(thermo: Thermo) -> None:
    res = BatchReactor().solve({"charge_in": _charge(thermo)}, _isom(thermal={"duty_W": 200.0}), thermo)
    assert res.duty_W == pytest.approx(200.0 * 96.0 / 120.0)
    assert res.info["batch_duty_J"] == pytest.approx(200.0 * 96.0)
    assert res.info["T_max_K"] > 500.0


def test_all_zero_rates_leave_the_charge(thermo: Thermo) -> None:
    params = _isom()
    rs = params["reaction_set"]
    kin = {**rs["reactions"][0]["kinetics"], "k0": 0.0}
    params["reaction_set"] = {**rs, "reactions": [{**rs["reactions"][0], "kinetics": kin}]}
    charge = _charge(thermo)
    res = BatchReactor().solve({"charge_in": charge}, params, thermo)
    out = res.outlets["outlet"]
    assert out.T == charge.T
    assert out.component_flows()["nC4"] == pytest.approx(1.0, rel=1e-12)
    assert res.duty_W == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"batch_time_s": 0.0}, "batch_time_s"),
        ({"turnaround_s": -1.0}, "turnaround_s"),
        ({"thermal": {"T_out": 300.0}}, "thermal mode"),
        ({"reacting_phase": "plasma"}, "reacting_phase"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    with pytest.raises(BatchReactorError, match=match):
        BatchReactor().solve({"charge_in": _charge(thermo)}, _isom(**change), thermo)


def test_batch_time_is_required(thermo: Thermo) -> None:
    params = _isom()
    del params["batch_time_s"]
    with pytest.raises(BatchReactorError, match="batch_time_s"):
        BatchReactor().solve({"charge_in": _charge(thermo)}, params, thermo)


def test_a_two_phase_vessel_is_refused(thermo: Thermo) -> None:
    """A charge inside the two-phase dome (vf 0.449 on pr) is refused, not half-reacted."""
    charge = thermo.flash_pt({"nC4": 0.5, "iC4": 0.5}, 300.0, 3.08e5, 1.0)
    assert 0.0 < float(charge.vapor_fraction) < 1.0
    with pytest.raises(PlugFlowError, match="two-phase"):
        BatchReactor().solve({"charge_in": charge}, _isom(), thermo)


def test_kinetics_are_required(thermo: Thermo) -> None:
    params = _isom()
    rs = params["reaction_set"]
    reaction = {k: v for k, v in rs["reactions"][0].items() if k != "kinetics"}
    params["reaction_set"] = {**rs, "reactions": [reaction]}
    with pytest.raises(PlugFlowError, match="has no kinetics"):
        BatchReactor().solve({"charge_in": _charge(thermo)}, params, thermo)
