"""Closed-form tests for control_valve R1 (spec specs/backend/units/control_valve.md).

Every expected value below is hand-computed from the spec's IEC 60534-2-1:2011
equations, independent of fluids; tolerance 1e-10 relative.

Hand computation (liquid, eqs. 1-4, Q in m3/h, dP in kPa, N1 = 0.1,
rho0 = 999.10329 kg/m3):
- L1: rho1/rho0 = 965.4/999.10329 = 0.9662562...; dP = 680 - 220 = 460 kPa;
  FF = 0.96 - 0.28*sqrt(70.1/22120) = 0.944237522523330;
  dP_choke = 0.9^2*(680 - 0.944237522523330*70.1) kPa = 497.185249233603 kPa
  > 460 kPa, so not choked;
  Kv = 360/0.1*sqrt(0.9662562.../460) = 164.995476370496; Cv = Kv/0.865.
- L2: same basis, P2 = 100 kPa, dP = 580 kPa > 497.185... kPa, choked;
  Kv = 360/(0.1*0.9)*sqrt(0.9662562.../(680 - 0.944237522523330*70.1))
    = 158.705448111403.

Hand computation (gas, eqs. 5/8/10/13, Q in m3/h, P in kPa, N9 = 24.6):
- Q_std = 50 mol/s * 0.0224139695450141 m3/mol = 1.12069847725071 m3/s
  = 4034.5145181 m3/h;
- G1: x = 230/680 = 0.338235294117647 < Fgamma*xT = (1.3/1.4)*0.6
  = 0.557142857142857, not choked; Y = 1 - x/(3*Fgamma*xT)
  = 0.797637003519357;
  Kv = 4034.5145181/(24.6*680*0.797637003519357)
       *sqrt(44.01*433*0.988/0.338235294117647) = 71.3395905795846.
- G2: x = 480/680 = 0.705882352941176 >= 0.557142857142857, choked;
  choke P2 = 680*(1 - 0.557142857142857) = 301.142857142857 kPa;
  x is replaced by Fgamma*xT and Y = 2/3;
  Kv = 4034.5145181/(24.6*680*(2/3))*sqrt(44.01*433*0.988/0.557142857142857)
     = 66.5048538035932.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

import ngdesign.units.flow.control_valve_r1 as cvr1_module
from ngdesign.contracts import PhaseKind
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.control_valve import ControlValve as ControlValveR0
from ngdesign.units.flow.control_valve import ControlValveSpecError
from ngdesign.units.flow.control_valve_r1 import (
    KV_PER_CV,
    VMOL_STD,
    ChokedCapacityError,
    ControlValveR1,
    ControlValveRatingError,
    characteristic,
    characteristic_inverse,
    kv_gas,
    kv_liquid,
)
from tests.conftest import flash_feed

REL = 1e-10

# L1/L2 basis (IEC 60534-2-1 Annex D example 1 inputs, printed in the spec).
L_Q = 0.1  # m3/s = 360 m3/h
L_RHO = 965.4  # kg/m3
L_MU = 3.1472e-4  # Pa s
L_PSAT = 70.1e3  # Pa
L_PC = 22120e3  # Pa
L_P1 = 680e3  # Pa
L_FL = 0.9
L_FD = 1.0

# G1/G2 basis (IEC 60534-2-1 Annex D example 3 inputs, printed in the spec).
G_N = 50.0  # mol/s
G_MW = 44.01  # g/mol
G_MU = 1.4665e-4  # Pa s
G_GAMMA = 1.30
G_Z = 0.988
G_T = 433.0  # K
G_P1 = 680e3  # Pa
G_XT = 0.60
G_FL = 0.9
G_FD = 1.0


def test_vmol_std_conversion() -> None:
    """Eq. 5: the molar volume behind N9 is exactly R*273.15/101325."""
    assert VMOL_STD == pytest.approx(0.0224139695450141, rel=1e-12)
    assert G_N * VMOL_STD == pytest.approx(1.12069847725071, rel=1e-12)


def test_liquid_non_choked_L1() -> None:
    """L1: eq. 1, far from choke."""
    d = kv_liquid(
        Q_m3_s=L_Q,
        rho=L_RHO,
        mu=L_MU,
        Psat=L_PSAT,
        Pc=L_PC,
        P1=L_P1,
        P2=220e3,
        FL=L_FL,
        Fd=L_FD,
    )
    assert d["Kv"] == pytest.approx(164.995476370496, rel=REL)
    assert d["Kv"] / KV_PER_CV == pytest.approx(190.746215457220, rel=REL)
    assert d["choked"] == 0.0
    assert d["FR"] == 1.0 and d["FP"] == 1.0


def test_liquid_choked_L2() -> None:
    """L2: eq. 3, dP beyond the choked drop."""
    d = kv_liquid(
        Q_m3_s=L_Q,
        rho=L_RHO,
        mu=L_MU,
        Psat=L_PSAT,
        Pc=L_PC,
        P1=L_P1,
        P2=100e3,
        FL=L_FL,
        Fd=L_FD,
    )
    assert d["Kv"] == pytest.approx(158.705448111403, rel=REL)
    assert d["choked"] == 1.0


def test_gas_non_choked_G1() -> None:
    """G1: eqs. 8 and 10, x below Fgamma*xT."""
    d = kv_gas(
        n_mol_s=G_N,
        MW=G_MW,
        mu=G_MU,
        gamma=G_GAMMA,
        Z=G_Z,
        T=G_T,
        P1=G_P1,
        P2=450e3,
        xT=G_XT,
        FL=G_FL,
        Fd=G_FD,
    )
    assert d["Kv"] == pytest.approx(71.3395905795846, rel=REL)
    assert d["Y"] == pytest.approx(0.797637003519357, rel=REL)
    assert d["choked"] == 0.0


def test_gas_choked_G2() -> None:
    """G2: x beyond Fgamma*xT; x replaced by Fgamma*xT, Y = 2/3."""
    d = kv_gas(
        n_mol_s=G_N,
        MW=G_MW,
        mu=G_MU,
        gamma=G_GAMMA,
        Z=G_Z,
        T=G_T,
        P1=G_P1,
        P2=200e3,
        xT=G_XT,
        FL=G_FL,
        Fd=G_FD,
    )
    assert d["Kv"] == pytest.approx(66.5048538035932, rel=REL)
    assert d["choked"] == 1.0
    assert d["Y"] == pytest.approx(2.0 / 3.0, rel=REL)


def test_characteristic_equal_percentage() -> None:
    """phi = R^(l-1) at the spec's printed points."""
    assert characteristic(0.25, "equal_percentage", 50.0) == pytest.approx(0.0531829589694499, rel=REL)
    assert characteristic(0.5, "equal_percentage", 50.0) == pytest.approx(0.141421356237310, rel=REL)
    assert characteristic(0.8, "equal_percentage", 50.0) == pytest.approx(0.457305051927326, rel=REL)


def test_characteristic_quick_opening() -> None:
    """phi = sqrt(l)."""
    assert characteristic(0.5, "quick_opening") == pytest.approx(0.707106781186548, rel=REL)


def test_characteristic_linear() -> None:
    """phi = l."""
    assert characteristic(0.3, "linear") == pytest.approx(0.3, rel=REL)


def test_characteristic_inverse_equal_percentage() -> None:
    """l = 1 + ln(phi)/ln(R) at the spec's printed point."""
    assert characteristic_inverse(0.2, "equal_percentage", 50.0) == pytest.approx(0.588591910067779, rel=REL)


def test_characteristic_round_trip() -> None:
    """Each kind's inverse undoes its characteristic."""
    for kind in ("linear", "equal_percentage", "quick_opening"):
        for travel in (0.05, 0.4, 1.0):
            assert characteristic_inverse(characteristic(travel, kind, 50.0), kind, 50.0) == (
                pytest.approx(travel, rel=1e-12)
            )


def test_bad_characteristic_refused() -> None:
    with pytest.raises(ValueError, match="characteristic"):
        characteristic(0.5, "equal-percentage")


def test_bad_travel_refused() -> None:
    with pytest.raises(ValueError, match="opening"):
        characteristic(0.0, "linear")
    with pytest.raises(ValueError, match="phi"):
        characteristic_inverse(1.5, "linear")


# --------------------------------------------------------------------------
R_UNIVERSAL = 8.31446261815324

PROPANE_FEED = {
    "T": 294.261,
    "P": 2.16978e6,
    "molar_flow": 574.66,
    "composition": {"C3": 1.0},
}
PROPANE_PARAMS = {"P_out": 1.997411e6, "mu_liquid": 1.0371e-4}
METHANE_FEED = {
    "T": 300.0,
    "P": 5.0e6,
    "molar_flow": 100.0,
    "composition": {"C1": 1.0},
}


def _propane_liquid(thermo: Thermo) -> Any:
    return flash_feed(thermo, PROPANE_FEED)


def test_adapter_example_case_solves(thermo: Thermo) -> None:
    """The R1 example (R0's propane basis plus Cv_rated) solves to a real outlet."""
    feeds, params = ControlValveR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    result = ControlValveR1().solve(inlets, params, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.P == params["P_out"]
    assert result.duty_W == 0.0 and result.power_W == 0.0
    assert result.info["phase_code"] == 0.0
    assert result.info["FP"] == 1.0
    assert result.info["Cv"] > 0.0 and result.info["Kv_m3h_bar05"] > 0.0
    assert "dP_choke_Pa" in result.info and "travel" in result.info


def test_sizing_identity_to_r0(thermo: Thermo) -> None:
    """Sizing on an all-liquid inlet, no diameters, FL=0.9, Fd=1: R1 == R0."""
    inlets = {"inlet": _propane_liquid(thermo)}
    r0 = ControlValveR0().solve(inlets, {"P_out": 1.997411e6, "Fp": 1.0, "mu_liquid": 1.0371e-4}, thermo)
    r1 = ControlValveR1().solve(inlets, dict(PROPANE_PARAMS), thermo)
    assert r1.info["Cv"] == pytest.approx(r0.info["Cv"], rel=1e-12)
    o0 = r0.outlets["outlet"]
    o1 = r1.outlets["outlet"]
    assert o1.T == o0.T and o1.P == o0.P and o1.enthalpy == o0.enthalpy


def test_gas_sizing_wiring(thermo: Thermo) -> None:
    """Gas Kv equals kv_gas called with the unit's own reported properties."""
    inlet = flash_feed(thermo, METHANE_FEED)
    result = ControlValveR1().solve({"inlet": inlet}, {"P_out": 3.0e6, "mu_gas": 1.2e-5}, thermo)
    vapor = next(p for p in inlet.phases if p.kind is PhaseKind.VAPOR)
    props = thermo.phase_props(vapor.composition, inlet.T, inlet.P, PhaseKind.VAPOR)
    gamma = props.cp / (props.cp - R_UNIVERSAL)
    mu = vapor.viscosity if vapor.viscosity is not None else 1.2e-5
    kv = kv_gas(
        n_mol_s=inlet.molar_flow,
        MW=vapor.molecular_weight,
        mu=mu,
        gamma=gamma,
        Z=float(vapor.z_factor) if vapor.z_factor is not None else 1.0,
        T=inlet.T,
        P1=inlet.P,
        P2=3.0e6,
        xT=0.7,
        FL=0.9,
        Fd=1.0,
    )
    assert result.info["phase_code"] == 1.0
    assert result.info["Kv_m3h_bar05"] == pytest.approx(kv["Kv"], rel=1e-12)
    assert result.info["Y"] == pytest.approx(kv["Y"], rel=1e-12)
    assert result.info["x"] == pytest.approx((inlet.P - 3.0e6) / inlet.P, rel=1e-12)
    # the Q_std conversion behind eq. 5
    assert inlet.molar_flow * VMOL_STD == pytest.approx(inlet.molar_flow * 0.0224139695450141, rel=1e-12)


def _refuse(thermo: Thermo, inlet: Any, params: dict[str, Any], match: str) -> None:
    with pytest.raises(ControlValveSpecError, match=match):
        ControlValveR1().solve({"inlet": inlet}, params, thermo)


def test_refuse_two_phase(thermo: Thermo) -> None:
    """A two-phase inlet is refused: IEC 60534-2-1 is single-phase."""
    inlet = thermo.flash_tvf({"C3": 0.5, "C1": 0.5}, 280.0, 0.5, 100.0)
    _refuse(thermo, inlet, {"P_out": 2.0e6}, "two-phase flow is outside IEC 60534-2-1")


def test_refuse_outlet_pressure_modes(thermo: Thermo) -> None:
    """The P_out/dP mode rules are R0's, reused read-only."""
    inlet = _propane_liquid(thermo)
    _refuse(thermo, inlet, {"P_out": 1.0e6, "dP": 1.0e5}, "exactly one of P_out / dP")
    _refuse(thermo, inlet, {"P_out": 3.0e6}, "above the inlet pressure")
    _refuse(thermo, inlet, {"P_out": -1.0}, "must be > 0")
    _refuse(thermo, inlet, {"dP": -5.0}, "must be >= 0")
    _refuse(thermo, inlet, {"P_out": inlet.P}, "zero pressure drop")


def test_refuse_rating_needs_params(thermo: Thermo) -> None:
    """Rating mode without Cv_rated and opening is refused."""
    _refuse(thermo, _propane_liquid(thermo), {}, "rating mode needs Cv_rated and opening")
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"Cv_rated": 125.0},
        "rating mode needs Cv_rated and opening",
    )


def test_refuse_opening_range(thermo: Thermo) -> None:
    _refuse(thermo, _propane_liquid(thermo), {"Cv_rated": 125.0, "opening": 1.5}, "opening")


def test_refuse_characteristic(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"P_out": 1.997411e6, "characteristic": "equal-percentage"},
        "characteristic",
    )


def test_refuse_rangeability(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"P_out": 1.997411e6, "rangeability": 0.5},
        "rangeability",
    )


@pytest.mark.parametrize("name,value", [("FL", 1.5), ("Fd", 0.0), ("xT", -0.1)])
def test_refuse_factor_ranges(thermo: Thermo, name: str, value: float) -> None:
    _refuse(thermo, _propane_liquid(thermo), {"P_out": 1.997411e6, name: value}, name)


def test_refuse_partial_diameters(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"P_out": 1.997411e6, "D1_m": 0.15},
        "D1_m, D2_m, d_m",
    )


def test_refuse_bad_diameters(thermo: Thermo) -> None:
    inlet = _propane_liquid(thermo)
    _refuse(
        thermo,
        inlet,
        {"P_out": 1.997411e6, "D1_m": -0.15, "D2_m": 0.15, "d_m": 0.1},
        "D1_m, D2_m, d_m",
    )
    _refuse(
        thermo,
        inlet,
        {"P_out": 1.997411e6, "D1_m": 0.15, "D2_m": 0.15, "d_m": 0.2},
        "D1_m, D2_m, d_m",
    )


def test_refuse_diameters_in_rating(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"Cv_rated": 125.0, "opening": 1.0, "D1_m": 0.15, "D2_m": 0.15, "d_m": 0.1},
        "sizing mode only",
    )


def test_refuse_liquid_viscosity(thermo: Thermo) -> None:
    """No phase viscosity and no mu_liquid: refuse, naming mu_liquid."""
    inlet = _propane_liquid(thermo)
    dry = [p.model_copy(update={"viscosity": None}) for p in inlet.phases]
    inlet = inlet.model_copy(update={"phases": dry})
    _refuse(thermo, inlet, {"P_out": 1.997411e6}, "mu_liquid")


def test_mu_liquid_fallback_used(thermo: Thermo) -> None:
    """mu_liquid is used when the phase carries no viscosity."""
    inlet = _propane_liquid(thermo)
    dry = [p.model_copy(update={"viscosity": None}) for p in inlet.phases]
    inlet = inlet.model_copy(update={"phases": dry})
    result = ControlValveR1().solve({"inlet": inlet}, {"P_out": 1.997411e6, "mu_liquid": 1.0371e-4}, thermo)
    assert result.info["Cv"] > 0.0


def test_refuse_gas_viscosity(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, METHANE_FEED)
    dry = [p.model_copy(update={"viscosity": None}) for p in inlet.phases]
    inlet = inlet.model_copy(update={"phases": dry})
    _refuse(thermo, inlet, {"P_out": 3.0e6}, "mu_gas")


def test_refuse_gas_z_none(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, METHANE_FEED)
    naked = [p.model_copy(update={"z_factor": None}) for p in inlet.phases]
    inlet = inlet.model_copy(update={"phases": naked})
    _refuse(thermo, inlet, {"P_out": 3.0e6, "mu_gas": 1.2e-5}, "z_factor")


class _LowCpThermo:
    """Delegating stub whose vapour cp gives gamma <= 1 (tests the refusal)."""

    def __init__(self, inner: Thermo) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> Any:
        props = self._inner.phase_props(composition, T, P, kind)
        return props.model_copy(update={"cp": 0.5 * R_UNIVERSAL})


def test_refuse_gamma_at_most_one(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, METHANE_FEED)
    stub = cast(Thermo, _LowCpThermo(thermo))
    _refuse(stub, inlet, {"P_out": 3.0e6, "mu_gas": 1.2e-5}, "gamma")


def test_refuse_cv_exceeds_rated(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"P_out": 1.997411e6, "mu_liquid": 1.0371e-4, "Cv_rated": 1.0},
        "exceeds Cv_rated",
    )


# --------------------------------------------------------------------------
# Step 3: rating mode (Cv_rated + opening -> solved outlet pressure).
# --------------------------------------------------------------------------


def test_rating_roundtrip(thermo: Thermo) -> None:
    """Opening the valve at the sized travel recovers the sized outlet pressure."""
    feeds, params = ControlValveR1.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    sized = ControlValveR1().solve({"inlet": inlet}, params, thermo)
    opening = sized.info["travel"]
    r = ControlValveR1().solve({"inlet": inlet}, {"Cv_rated": 125.0, "opening": opening}, thermo)
    assert r.info["P_out_Pa"] == pytest.approx(1.997411e6, rel=1e-9)
    assert r.info["opening"] == pytest.approx(opening, rel=1e-9)
    assert r.info["choked"] == 0.0
    assert r.outlets["outlet"].P == pytest.approx(1.997411e6, rel=1e-9)
    assert r.duty_W == 0.0 and r.power_W == 0.0


def test_rating_gas_roundtrip(thermo: Thermo) -> None:
    """Rating a gas valve with just enough capacity recovers a consistent outlet.

    Capacity 1/0.99 above the requirement at 3.0 MPa throttles less, so the
    solved outlet pressure sits above 3.0 MPa; sizing back at the solved
    pressure must return exactly the rated capacity.
    """
    inlet = flash_feed(thermo, METHANE_FEED)
    sized = ControlValveR1().solve({"inlet": inlet}, {"P_out": 3.0e6, "mu_gas": 1.2e-5}, thermo)
    Cv_rated = sized.info["Cv"] / 0.99
    r = ControlValveR1().solve(
        {"inlet": inlet},
        {"Cv_rated": Cv_rated, "opening": 1.0, "mu_gas": 1.2e-5},
        thermo,
    )
    P2 = float(r.info["P_out_Pa"])
    assert 3.0e6 < P2 < 3.3e6
    sized_back = ControlValveR1().solve({"inlet": inlet}, {"P_out": P2, "mu_gas": 1.2e-5}, thermo)
    assert sized_back.info["Cv"] == pytest.approx(Cv_rated, rel=1e-9)


def test_rating_identity(thermo: Thermo) -> None:
    """Plan's rating identity: rating at the sizing Cv, linear, opening 1.0 recovers P_out.

    With Cv_rated equal to the sizing Cv and the linear characteristic at full
    opening, the available Kv equals the sized Kv, so the solved P2 equals the
    sizing P_out to 1e-8 relative.
    """
    feeds, _ = ControlValveR1.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    sized = ControlValveR1().solve({"inlet": inlet}, {"P_out": 1.997411e6, "mu_liquid": 1.0371e-4}, thermo)
    r = ControlValveR1().solve(
        {"inlet": inlet},
        {
            "Cv_rated": float(sized.info["Cv"]),
            "opening": 1.0,
            "characteristic": "linear",
            "mu_liquid": 1.0371e-4,
        },
        thermo,
    )
    assert r.info["P_out_Pa"] == pytest.approx(1.997411e6, rel=1e-8)
    assert r.info["opening"] == pytest.approx(1.0, rel=1e-9)


def test_rating_eqpercent_residual(thermo: Thermo) -> None:
    """Plan's residual check: eq% rating at opening 0.8 solves kv_liquid(P2) = Kv_avail (1e-9)."""
    feeds, _ = ControlValveR1.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    r = ControlValveR1().solve(
        {"inlet": inlet},
        {
            "Cv_rated": 125.0,
            "opening": 0.8,
            "characteristic": "equal_percentage",
            "mu_liquid": 1.0371e-4,
        },
        thermo,
    )
    P2 = float(r.info["P_out_Pa"])
    liquid = cvr1_module._liquid_phase(inlet)
    rho = float(liquid.density)
    mu = liquid.viscosity if liquid.viscosity is not None else 1.0371e-4
    Kv = float(
        cvr1_module.kv_liquid(
            inlet.mass_flow / rho,
            rho,
            mu,
            cvr1_module._psat(inlet, thermo),
            cvr1_module._average_Pc(inlet),
            inlet.P,
            P2,
            FL=0.9,
            Fd=1.0,
        )["Kv"]
    )
    Kv_avail = KV_PER_CV * 125.0 * cvr1_module.characteristic(0.8, "equal_percentage", 50.0)
    assert Kv == pytest.approx(Kv_avail, rel=1e-9)


def test_rating_choked_capacity_refused(thermo: Thermo) -> None:
    """Below the choked capacity the refusal is typed, naming the fragment.

    The spec pins the construction: the L2-like liquid (water at the Annex D
    printed basis, choked at P2 = 100 kPa) with Cv_rated set to 0.9 x the
    choked Cv at opening 1.
    """
    inlet = flash_feed(
        thermo,
        {"T": 363.15, "P": 680e3, "molar_flow": 5359.3, "composition": {"H2O": 1.0}},
    )
    choked = ControlValveR1().solve({"inlet": inlet}, {"P_out": 100e3}, thermo)
    Cv_rated = 0.9 * choked.info["Cv"]
    with pytest.raises(ChokedCapacityError, match="choked capacity"):
        ControlValveR1().solve({"inlet": inlet}, {"Cv_rated": Cv_rated, "opening": 1.0}, thermo)


def test_rating_convergence_refused(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing root finder surfaces as ControlValveRatingError, not raw scipy."""

    def boom(*args: Any, **kwargs: Any) -> float:
        raise RuntimeError("boom")

    monkeypatch.setattr(cvr1_module, "brentq", boom)
    inlet = _propane_liquid(thermo)
    with pytest.raises(ControlValveRatingError, match="did not converge"):
        ControlValveR1().solve({"inlet": inlet}, {"Cv_rated": 125.0, "opening": 0.9}, thermo)


def test_refuse_cv_rated_not_positive(thermo: Thermo) -> None:
    _refuse(
        thermo,
        _propane_liquid(thermo),
        {"Cv_rated": 0.0, "opening": 1.0},
        "Cv_rated",
    )
