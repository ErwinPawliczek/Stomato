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

from ngdesign.units.flow.ejector_r1 import ejector_core

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
