"""Control valve R1 tests; expected values from the spec's calc_control_valve.py,
which reproduces the IEC equations independently of fluids."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.control_valve import ControlValve, ControlValveSpecError
from ngdesign.units.flow.control_valve_r1 import (
    VM_STD,
    ChokedCapacityError,
    ControlValveR1,
    ControlValveRatingError,
    characteristic,
    characteristic_inverse,
    kv_gas,
    kv_liquid,
)

L1: dict[str, float] = {
    "Q_m3_s": 0.1,
    "rho": 965.4,
    "mu": 3.1472e-4,
    "Psat": 70.1e3,
    "Pc": 22120e3,
    "P1": 680e3,
    "FL": 0.9,
    "Fd": 1.0,
}
G1: dict[str, float] = {
    "n_mol_s": 50.0,
    "MW": 44.01,
    "mu": 1.4665e-4,
    "gamma": 1.30,
    "Z": 0.988,
    "T": 433.0,
    "P1": 680e3,
    "xT": 0.60,
    "FL": 0.9,
    "Fd": 1.0,
}


def test_liquid_not_choked() -> None:
    out = kv_liquid(**L1, P2=220e3)
    assert out["Kv"] == pytest.approx(164.995476370496, rel=1e-10)
    assert out["choked"] == 0.0


def test_liquid_choked() -> None:
    out = kv_liquid(**L1, P2=100e3)
    assert out["Kv"] == pytest.approx(158.705448111403, rel=1e-10)
    assert out["choked"] == 1.0


def test_gas_not_choked() -> None:
    out = kv_gas(**G1, P2=450e3)
    assert VM_STD == pytest.approx(0.0224139695450141, rel=1e-12)
    assert out["Y"] == pytest.approx(0.797637003519357, rel=1e-10)
    assert out["Kv"] == pytest.approx(71.3395905795846, rel=1e-10)
    assert out["choked"] == 0.0


def test_gas_choked() -> None:
    out = kv_gas(**G1, P2=200e3)
    assert out["Kv"] == pytest.approx(66.5048538035932, rel=1e-10)
    assert out["choked"] == 1.0


def test_characteristics() -> None:
    assert characteristic(0.25, "equal_percentage", 50.0) == pytest.approx(0.0531829589694499, rel=1e-12)
    assert characteristic(0.5, "equal_percentage", 50.0) == pytest.approx(0.141421356237310, rel=1e-12)
    assert characteristic(0.8, "equal_percentage", 50.0) == pytest.approx(0.457305051927326, rel=1e-12)
    assert characteristic(0.5, "quick_opening", 50.0) == pytest.approx(0.707106781186548, rel=1e-12)
    assert characteristic(0.4, "linear", 50.0) == 0.4
    assert characteristic_inverse(0.2, "equal_percentage", 50.0) == pytest.approx(
        0.588591910067779, rel=1e-12
    )
    assert characteristic_inverse(0.25, "quick_opening", 50.0) == pytest.approx(0.0625, rel=1e-12)


def _propane(thermo: Thermo) -> tuple[dict[str, Any], dict[str, Any]]:
    feeds, params = ControlValve.example_case()
    f = feeds["inlet"]
    return {"inlet": thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])}, params


MU = {"mu_liquid": 1.0e-4}


def test_sizing_reduces_to_r0(thermo: Thermo) -> None:
    inlets, params = _propane(thermo)
    r0 = ControlValve().solve(inlets, {**params, **MU}, thermo)
    r1 = ControlValveR1().solve(inlets, {"P_out": params["P_out"], **MU}, thermo)
    assert r1.info["Cv"] == pytest.approx(r0.info["Cv"], rel=1e-12)
    a, b = r1.outlets["outlet"], r0.outlets["outlet"]
    assert (a.T, a.P, a.enthalpy) == (b.T, b.P, b.enthalpy)


def test_rating_inverts_sizing(thermo: Thermo) -> None:
    inlets, params = _propane(thermo)
    sized = ControlValveR1().solve(inlets, {"P_out": params["P_out"], **MU}, thermo)
    rated = ControlValveR1().solve(inlets, {"Cv_rated": sized.info["Cv"], "opening": 1.0, **MU}, thermo)
    assert rated.info["P_out_Pa"] == pytest.approx(params["P_out"], rel=1e-8)


def test_rating_residual_equal_percentage(thermo: Thermo) -> None:
    inlets, params = _propane(thermo)
    sized = ControlValveR1().solve(inlets, {"P_out": params["P_out"], **MU}, thermo)
    cv = sized.info["Cv"] * 3.0
    res = ControlValveR1().solve(
        inlets, {"Cv_rated": cv, "opening": 0.6, "characteristic": "equal_percentage", **MU}, thermo
    )
    available = 0.865 * cv * 50.0 ** (0.6 - 1.0)
    assert res.info["Kv_m3h_bar05"] == pytest.approx(available, rel=1e-8)
    assert res.info["opening"] == 0.6


def test_travel_reported_in_sizing(thermo: Thermo) -> None:
    inlets, params = _propane(thermo)
    sized = ControlValveR1().solve(inlets, {"P_out": params["P_out"], **MU}, thermo)
    res = ControlValveR1().solve(
        inlets, {"P_out": params["P_out"], "Cv_rated": 2.0 * sized.info["Cv"], **MU}, thermo
    )
    assert res.info["travel"] == pytest.approx(0.5, rel=1e-10)


def test_gas_units_conversion(thermo: Thermo) -> None:
    """Methane at 300 K, 5 to 3 MPa: the unit equals kv_gas on its own reported state."""
    inlet = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e6, 50.0)
    params = {"P_out": 3.0e6, "mu_gas": 1.2e-5}
    res = ControlValveR1().solve({"inlet": inlet}, params, thermo)
    assert res.info["phase_code"] == 1.0
    phase = inlet.phases[0]
    cp = float(thermo.phase_props(dict(inlet.composition), inlet.T, inlet.P, phase.kind).cp)
    gamma = cp / (cp - 8.31446261815324)
    mu = phase.viscosity if phase.viscosity is not None else 1.2e-5
    direct = kv_gas(
        50.0,
        phase.molecular_weight,
        mu,
        gamma,
        float(phase.z_factor or 0.0),
        300.0,
        5.0e6,
        3.0e6,
        0.7,
        0.9,
        1.0,
    )
    assert res.info["Kv_m3h_bar05"] == pytest.approx(direct["Kv"], rel=1e-12)
    assert res.info["x"] == pytest.approx(0.4, rel=1e-12)


def test_choked_capacity_refused(thermo: Thermo) -> None:
    """Rated at 0.9 of the Cv that passes the flow at choke."""
    inlets, _ = _propane(thermo)
    probe = ControlValveR1().solve(inlets, {"P_out": 1.0e5, **MU}, thermo)
    assert probe.info["choked"] == 1.0
    with pytest.raises(ChokedCapacityError, match="choked capacity"):
        ControlValveR1().solve(inlets, {"Cv_rated": 0.9 * probe.info["Cv"], "opening": 1.0, **MU}, thermo)


def test_rating_failure_is_typed() -> None:
    """An inconsistent Kv function fails the bracket; the failure is named."""
    with pytest.raises(ControlValveRatingError, match="did not converge"):
        ControlValveR1._rate(1.0e6, 10.0, 5.0e5, 1.0, lambda _p: 1.0)


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({"P_out": 2.0e6, "dP": 1.0e5}, "exactly one of"),
        ({"Cv_rated": 10.0}, "rating mode needs Cv_rated and opening"),
        ({"Cv_rated": 1.0e3, "opening": 1.5}, "opening"),
        ({"dP": 1.0e5, "characteristic": "parabolic"}, "characteristic"),
        ({"dP": 1.0e5, "rangeability": 1.0}, "rangeability"),
        ({"dP": 1.0e5, "FL": 0.0}, "FL"),
        ({"dP": 1.0e5, "Fd": 2.0}, "Fd"),
        ({"dP": 1.0e5, "xT": 0.0}, "xT"),
        ({"dP": 1.0e5, "D1_m": 0.1}, "D1_m, D2_m, d_m"),
        ({"dP": 1.0e5, "D1_m": 0.1, "D2_m": 0.1, "d_m": 0.2}, "D1_m, D2_m, d_m"),
        ({"Cv_rated": 1.0e3, "opening": 1.0, "D1_m": 0.1, "D2_m": 0.1, "d_m": 0.1}, "sizing mode only"),
        ({"dP": 0.0}, "zero pressure drop"),
        ({"dP": 1.0e5, "Cv_rated": 1.0e-6}, "exceeds Cv_rated"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    inlets, _ = _propane(thermo)
    with pytest.raises(ControlValveSpecError, match=match):
        ControlValveR1().solve(inlets, {**MU, **params}, thermo)


def test_two_phase_refused(thermo: Thermo) -> None:
    inlet = thermo.flash_pt({"nC4": 0.5, "iC4": 0.5}, 300.0, 3.08e5, 1.0)
    assert 0.1 < inlet.vapor_fraction < 0.9
    with pytest.raises(ControlValveSpecError, match="two-phase"):
        ControlValveR1().solve({"inlet": inlet}, {"dP": 1.0e4}, thermo)


class _NoTransport:
    """Removes viscosity and z_factor from a package's flashes."""

    def __init__(self, inner: Thermo) -> None:
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def test_missing_viscosities_refused(thermo: Thermo) -> None:
    inlets, params = _propane(thermo)
    phases = [p.model_copy(update={"viscosity": None}) for p in inlets["inlet"].phases]
    bare = {"inlet": inlets["inlet"].model_copy(update={"phases": phases})}
    with pytest.raises(ControlValveSpecError, match="mu_liquid"):
        ControlValveR1().solve(bare, {"P_out": params["P_out"]}, thermo)
    gas = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e6, 50.0)
    phases = [p.model_copy(update={"viscosity": None}) for p in gas.phases]
    with pytest.raises(ControlValveSpecError, match="mu_gas"):
        ControlValveR1().solve({"inlet": gas.model_copy(update={"phases": phases})}, {"P_out": 3.0e6}, thermo)
    phases = [p.model_copy(update={"z_factor": None}) for p in gas.phases]
    with pytest.raises(ControlValveSpecError, match="z_factor"):
        ControlValveR1().solve(
            {"inlet": gas.model_copy(update={"phases": phases})},
            {"P_out": 3.0e6, "mu_gas": 1.2e-5},
            thermo,
        )


def test_gamma_refused_when_not_above_one(thermo: Thermo) -> None:
    class ColdCp(_NoTransport):
        def phase_props(self, *args: Any, **kwargs: Any) -> Any:
            return self.inner.phase_props(*args, **kwargs).model_copy(update={"cp": 1.0})

    gas = thermo.flash_pt({"C1": 1.0}, 300.0, 5.0e6, 50.0)
    with pytest.raises(ControlValveSpecError, match="gamma"):
        ControlValveR1().solve({"inlet": gas}, {"P_out": 3.0e6, "mu_gas": 1.2e-5}, ColdCp(thermo))


def test_piping_factor_reported(thermo: Thermo) -> None:
    """Reducers cost capacity: FP < 1 raises the required Kv."""
    inlets, params = _propane(thermo)
    plain = ControlValveR1().solve(inlets, {"P_out": params["P_out"], **MU}, thermo)
    reduced = ControlValveR1().solve(
        inlets, {"P_out": params["P_out"], "D1_m": 0.3, "D2_m": 0.3, "d_m": 0.1, **MU}, thermo
    )
    assert reduced.info["FP"] < 1.0
    assert reduced.info["Cv"] > plain.info["Cv"]
    assert math.isfinite(reduced.info["Cv"])
