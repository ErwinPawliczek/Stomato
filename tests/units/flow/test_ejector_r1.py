"""Closed-form and monotonicity tests for the ejector R1 level (U-R2).

Spec: ``specs/backend/units/ejector.md``. The closed-form check reduces the
spec's equations to a calorically perfect ideal gas and compares against the
spec's printed values (hand-derived here, R = 8.31446261815324 J/mol/K,
cp = kappa/(kappa-1)*R for the test's own lambdas):

s(T,P) = cp ln T - R ln P, h(T) = cp T, hence
h(P,s) = cp exp((s + R ln P)/cp) and s(P,h) = cp ln(h/cp) - R ln P.

- Nozzle: T_is = Tp*(Ps/Pp)**((kappa-1)/kappa) = 400*(1/6)**(2/7)
  = 239.734789884704 K; dh_n = eta_n*cp*(Tp - T_is);
  u_p = sqrt(2*dh_n/M) = 553.111930840640 m/s.
- Momentum: u_m = phi_m*(m_p/(m_p+m_s))*u_p = 0.85*(1/1.5)*u_p
  = 313.430094143029 m/s.
- Mixing energy: h_0 = cp*(m_p*Tp + m_s*Ts)/(m_p + m_s) = cp*1100/3, so the
  stagnation outlet temperature is T_out = 366.666666666667 K;
  h_m = h_0 - M*u_m**2/2 gives T_m = 317.776873958717 K.
- Diffuser: h(P_out, s_m) = h_m + eta_d*M*u_m**2/2 solves to
  P_out = 153749.137554408 Pa.
With all efficiencies = 1 the same chain gives P_out = 212970.469869893 Pa.
Tolerances: 1e-9 relative on P_out (brentq xtol is 1e-9*Ps) and 1e-12
relative on the velocities, per the spec.
"""

from __future__ import annotations

from math import exp, log
from typing import Any

import pytest

from ngdesign.units.flow.ejector import Ejector
from ngdesign.units.flow.ejector_r1 import EjectorR1, EjectorR1Error, ejector_core
from tests.conftest import flash_feed

M_AIR = 0.0289647  # kg/mol
KAPPA = 1.4
R_GAS = 8.31446261815324  # J/(mol K)
CP_MOLAR = KAPPA / (KAPPA - 1.0) * R_GAS  # J/(mol K)

PP, TP, MP = 6.0e5, 400.0, 1.0  # motive: Pa, K, kg/s
PS, TS, MS = 1.0e5, 300.0, 0.5  # suction: Pa, K, kg/s


def _ideal_gas_callables() -> tuple[Any, Any, Any]:
    """(h_at_PS_motive, h_at_PS_mix, s_at_PH_mix) for calorically perfect air."""

    def h_at_PS(P: float, s: float) -> float:
        return CP_MOLAR * exp((s + R_GAS * log(P)) / CP_MOLAR)

    def s_at_PH(P: float, h: float) -> float:
        return CP_MOLAR * log(h / CP_MOLAR) - R_GAS * log(P)

    return h_at_PS, h_at_PS, s_at_PH


def _ideal_gas_inputs(eta_n: float, phi_m: float, eta_d: float) -> dict[str, float]:
    """Core inputs for the spec's ideal-gas case."""
    n_p, n_s = MP / M_AIR, MS / M_AIR
    return {
        "np": n_p,
        "ns": n_s,
        "MWp": M_AIR,
        "MWs": M_AIR,
        "hp": CP_MOLAR * TP,
        "sp": CP_MOLAR * log(TP) - R_GAS * log(PP),
        "hs": CP_MOLAR * TS,
        "Pp": PP,
        "Ps": PS,
        "eta_n": eta_n,
        "phi_m": phi_m,
        "eta_d": eta_d,
        "P_hi": PP,
    }


@pytest.mark.parametrize(
    ("etas", "expected_P_out"),
    [
        ((0.95, 0.85, 0.85), 153749.137554408),
        ((1.0, 1.0, 1.0), 212970.469869893),
    ],
    ids=["huang-efficiencies", "all-unity"],
)
def test_closed_form_ideal_gas(etas: tuple[float, float, float], expected_P_out: float) -> None:
    """The core reproduces the hand-derived ideal-gas closed form exactly."""
    h_at_PS_motive, h_at_PS_mix, s_at_PH_mix = _ideal_gas_callables()
    info = ejector_core(
        **_ideal_gas_inputs(*etas),
        h_at_PS_motive=h_at_PS_motive,
        h_at_PS_mix=h_at_PS_mix,
        s_at_PH_mix=s_at_PH_mix,
    )
    assert info["P_out_Pa"] == pytest.approx(expected_P_out, rel=1e-9)
    if etas == (0.95, 0.85, 0.85):
        assert info["u_motive_m_s"] == pytest.approx(553.111930840640, rel=1e-12)
        assert info["u_mix_m_s"] == pytest.approx(313.430094143029, rel=1e-12)
        assert info["h_static_mix_J_mol"] / CP_MOLAR == pytest.approx(317.776873958717, rel=1e-12)
        assert info["h_stag_mix_J_mol"] / CP_MOLAR == pytest.approx(366.666666666667, rel=1e-12)
        # Nozzle isentropic-discharge temperature, via the injected callable.
        T_is = h_at_PS_motive(PS, _ideal_gas_inputs(*etas)["sp"]) / CP_MOLAR
        assert T_is == pytest.approx(239.734789884704, rel=1e-12)


def test_monotonicity_in_phi_mix() -> None:
    """A higher mixing momentum coefficient must give a higher discharge pressure."""
    h_at_PS_motive, h_at_PS_mix, s_at_PH_mix = _ideal_gas_callables()
    low = ejector_core(
        **_ideal_gas_inputs(0.95, 0.80, 0.85),
        h_at_PS_motive=h_at_PS_motive,
        h_at_PS_mix=h_at_PS_mix,
        s_at_PH_mix=s_at_PH_mix,
    )
    high = ejector_core(
        **_ideal_gas_inputs(0.95, 0.90, 0.85),
        h_at_PS_motive=h_at_PS_motive,
        h_at_PS_mix=h_at_PS_mix,
        s_at_PH_mix=s_at_PH_mix,
    )
    assert high["P_out_Pa"] > low["P_out_Pa"] > PS


def _example_inlets(thermo: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    feeds, params = EjectorR1.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return inlets, params


def test_example_case_rates(thermo: Any) -> None:
    """The R0 basis rates to a discharge between the suction and motive pressures."""
    inlets, params = _example_inlets(thermo)
    result = EjectorR1().solve(inlets, params, thermo)
    P_out = result.info["P_out_Pa"]
    assert inlets["suction_in"].P < P_out < inlets["motive_in"].P
    assert result.info["compression_ratio"] == pytest.approx(P_out / inlets["suction_in"].P, rel=1e-12)
    assert result.info["entrainment_kg_kg"] == pytest.approx(
        inlets["suction_in"].mass_flow / inlets["motive_in"].mass_flow, rel=1e-12
    )
    assert result.duty_W == 0.0 and result.power_W == 0.0
    assert result.outlets["outlet"].molar_flow == pytest.approx(
        inlets["motive_in"].molar_flow + inlets["suction_in"].molar_flow, rel=1e-12
    )


def test_identity_with_r0(thermo: Any) -> None:
    """R0 run at R1's computed P_out and achieved entrainment gives the identical outlet."""
    inlets, params = _example_inlets(thermo)
    r1 = EjectorR1().solve(inlets, params, thermo)
    P_out = r1.info["P_out_Pa"]
    entrainment = inlets["suction_in"].mass_flow / inlets["motive_in"].mass_flow
    r0 = Ejector().solve(inlets, {"P_out": P_out, "entrainment": entrainment}, thermo)
    out_r1, out_r0 = r1.outlets["outlet"], r0.outlets["outlet"]
    assert out_r1.T == out_r0.T
    assert out_r1.P == out_r0.P
    assert out_r1.enthalpy == pytest.approx(out_r0.enthalpy, rel=1e-12)


def test_p_out_required_reporting(thermo: Any) -> None:
    """P_out_required only reports: the outlet stays at the computed discharge."""
    inlets, params = _example_inlets(thermo)
    base = EjectorR1().solve(inlets, params, thermo)
    P_out = base.info["P_out_Pa"]
    assert "meets_discharge" not in base.info and "discharge_margin_Pa" not in base.info
    below = EjectorR1().solve(inlets, {**params, "P_out_required": P_out * 0.9}, thermo)
    assert below.info["meets_discharge"] == 1.0
    assert below.info["discharge_margin_Pa"] == pytest.approx(0.1 * P_out, rel=1e-12)
    above = EjectorR1().solve(inlets, {**params, "P_out_required": P_out * 1.1}, thermo)
    assert above.info["meets_discharge"] == 0.0
    assert above.info["discharge_margin_Pa"] == pytest.approx(-0.1 * P_out, rel=1e-12)
    assert above.outlets["outlet"].P == base.outlets["outlet"].P


def test_refuse_motive_not_above_suction(thermo: Any) -> None:
    """Pp <= Ps is refused: the motive must expand to the suction pressure."""
    feeds, params = EjectorR1.example_case()
    feeds["motive_in"]["P"] = 2000.0
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(EjectorR1Error, match="motive pressure"):
        EjectorR1().solve(inlets, params, thermo)


@pytest.mark.parametrize("name", ["eta_nozzle", "phi_mix", "eta_diffuser"])
def test_refuse_efficiency_out_of_range(thermo: Any, name: str) -> None:
    """Each efficiency must lie in (0, 1]; zero is refused by name."""
    inlets, params = _example_inlets(thermo)
    with pytest.raises(EjectorR1Error, match=name):
        EjectorR1().solve(inlets, {**params, name: 0.0}, thermo)


def test_refuse_no_nozzle_drop() -> None:
    """The dh_n <= 0 refusal, exercised at the core with injected callables.

    Real feeds cannot reach this refusal: a compressed-liquid motive still
    yields a small isentropic drop (about v*dP, ~9 kJ/kg from 100 bar to
    1 bar for water), and PR's flash at the liquid's entropy at the suction
    pressure is single-phase, so the adapter proceeds instead of refusing.
    The refusal is a property of the injected callables, so it is tested
    there.
    """

    def h_at_PS_no_drop(P: float, s: float) -> float:
        return CP_MOLAR * TP  # h_is not below hp: no enthalpy drop available

    _, h_at_PS_mix, s_at_PH_mix = _ideal_gas_callables()
    with pytest.raises(EjectorR1Error, match="no nozzle enthalpy drop"):
        ejector_core(
            **_ideal_gas_inputs(0.95, 0.85, 0.85),
            h_at_PS_motive=h_at_PS_no_drop,
            h_at_PS_mix=h_at_PS_mix,
            s_at_PH_mix=s_at_PH_mix,
        )


def test_refuse_discharge_above_motive(thermo: Any) -> None:
    """With perfect efficiencies the kinetic energy would recompress above Pp.

    Basis found by search: on R0's example basis even perfect efficiencies stay
    below the motive pressure; a 5 MPa / 500 K motive on a 20 kPa suction is a
    measured case where ``g(Pp) < 0`` and the refusal fires.
    """
    feeds = {
        "motive_in": {"T": 500.0, "P": 5.0e6, "molar_flow": 146.873, "composition": {"H2O": 1.0}},
        "suction_in": {"T": 300.0, "P": 2.0e4, "molar_flow": 48.958, "composition": {"H2O": 1.0}},
    }
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    defaults = {"eta_nozzle": 0.95, "phi_mix": 0.85, "eta_diffuser": 0.85}
    rated = EjectorR1().solve(inlets, defaults, thermo)
    assert inlets["suction_in"].P < rated.info["P_out_Pa"] < inlets["motive_in"].P
    perfect = {"eta_nozzle": 1.0, "phi_mix": 1.0, "eta_diffuser": 1.0}
    with pytest.raises(EjectorR1Error, match="exceeds the motive pressure"):
        EjectorR1().solve(inlets, perfect, thermo)


def test_refuse_zero_molar_flow(thermo: Any) -> None:
    """A zero-flow inlet is refused."""
    feeds, params = EjectorR1.example_case()
    feeds["suction_in"]["molar_flow"] = 0.0
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(EjectorR1Error, match="molar_flow"):
        EjectorR1().solve(inlets, params, thermo)


def test_refuse_bad_p_out_required(thermo: Any) -> None:
    """A non-positive P_out_required is refused by name."""
    inlets, params = _example_inlets(thermo)
    with pytest.raises(EjectorR1Error, match="P_out_required"):
        EjectorR1().solve(inlets, {**params, "P_out_required": -1.0}, thermo)
