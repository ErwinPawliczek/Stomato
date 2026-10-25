"""Closed-form tests for the shared rating core (spec double_pipe R1, "Tests").

Every expected number is an independent hand-computed value (from
``calc_double_pipe.py``, carried in the spec), checked at rel 1e-8.
Case 1 basis: water-like film at ~320 K (rho 990, mu 5.77e-4, k 0.637,
cp_mass 4180) in the inner pipe D_i = 0.0266 m at 0.5 kg/s - hand arithmetic
gives v = 0.5/(990*pi*0.0266^2/4) = 0.908827909 m/s,
Re = 990*0.908827909*0.0266/5.77e-4 = 41478.4647,
Pr = 4180*5.77e-4/0.637 = 3.78627943; the turbulent numbers then come from
the same Colebrook + Gnielinski equations the module calls.
"""

from __future__ import annotations

import math
from typing import cast

import pytest

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import PhaseProps
from ngdesign.contracts.stream import Phase
from ngdesign.units.heat.rating import (
    rate_two_stream,
    FilmProps,
    darcy_dP,
    duct_h,
    nu_tube,
    u_outside_tube,
)

REL = 1e-8


def _film(rho: float, mu: float, k: float, cp_mass: float) -> FilmProps:
    return FilmProps(rho_kg_m3=rho, mu_Pa_s=mu, k_W_mK=k, cp_J_kgK=cp_mass)


def test_closed_form_tube_turbulent() -> None:
    """Case 1: turbulent water-like film, D_i = 0.0266 m, 0.5 kg/s, eps 4.5e-5 m."""
    props = _film(990.0, 5.77e-4, 0.637, 4180.0)
    area = math.pi * 0.0266**2 / 4.0
    r = duct_h(0.5, area, 0.0266, props, 4.5e-5)
    assert r.v_m_s == pytest.approx(0.908827909, rel=REL)
    assert r.Re == pytest.approx(41478.4647, rel=REL)
    assert props.Pr == pytest.approx(3.78627943, rel=REL)
    assert r.fd == pytest.approx(0.0263385704, rel=REL)
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(247.163932, rel=REL)
    assert r.h_W_m2K == pytest.approx(5918.92574, rel=REL)
    assert darcy_dP(r.fd, 6.0, 0.0266, 990.0, r.v_m_s) == pytest.approx(2429.0157, rel=REL)


def test_closed_form_laminar() -> None:
    """Case 2: laminar oil-like film in the same pipe; Nu = 3.66, f = 64/Re."""
    props = _film(900.0, 0.05, 0.13, 2000.0)
    area = math.pi * 0.0266**2 / 4.0
    r = duct_h(0.02, area, 0.0266, props, 4.5e-5)
    assert r.Re == pytest.approx(19.1464593, rel=REL)
    assert r.fd == pytest.approx(3.34265458, rel=REL)  # 64/Re
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(3.66, rel=REL)
    assert r.h_W_m2K == pytest.approx(17.887218, rel=REL)  # 3.66*0.13/0.0266


def test_closed_form_annulus() -> None:
    """Case 3: annulus, D_tube,o 0.0334 / D_shell,i 0.0525, N2 film, 0.3 kg/s.

    A = pi*(0.0525^2 - 0.0334^2)/4 = 0.00128859491 m2, Dh = 0.0191 m
    (hydraulic diameter, Incropera 7th ed. section 8.7; the Gnielinski 2009
    annulus correction is deliberately omitted).
    """
    props = _film(8.41, 2.22e-5, 0.0330, 1053.7)
    area = math.pi * (0.0525**2 - 0.0334**2) / 4.0
    assert area == pytest.approx(0.00128859491, rel=REL)
    r = duct_h(0.3, area, 0.0191, props, 4.5e-5)
    assert r.Re == pytest.approx(200301.977, rel=REL)
    assert r.fd == pytest.approx(0.0252700562, rel=REL)
    assert nu_tube(r.Re, props.Pr, r.fd) == pytest.approx(522.74325, rel=REL)
    assert r.h_W_m2K == pytest.approx(903.168965, rel=REL)


def test_closed_form_u_outside_tube() -> None:
    """Case 4: U_o from case 1 (inner) and case 3 (annulus) films plus fouling.

    1/U_o = 1/h_o + R_fo + Do*ln(Do/Di)/(2*k_wall) + R_fi*Do/Di + Do/(Di*h_i)
    with h_i = 5918.92574, h_o = 903.168965, Do = 0.0334, Di = 0.0266,
    k_wall = 45, R_fi = 1.8e-4, R_fo = 3.5e-4.
    """
    u = u_outside_tube(
        h_i=5918.92574,
        h_o=903.168965,
        Do=0.0334,
        Di=0.0266,
        k_wall=45.0,
        R_fi=1.8e-4,
        R_fo=3.5e-4,
    )
    assert u == pytest.approx(505.089091, rel=REL)


class _LinearCpThermo:
    """Fake constant-cp thermo for the solve test: h = cp_mol*T exactly.

    Hot and cold sides are keyed by composition ({"H2O"} vs {"N2"}), so the
    same fake serves both streams. Only what rate_two_stream touches is
    implemented; it is used through ``cast(Thermo, ...)``, never registered.
    """

    def __init__(self, cp_hot: float, cp_cold: float) -> None:
        self._cp = {frozenset({"H2O"}): cp_hot, frozenset({"N2"}): cp_cold}

    def _cp_for(self, z: dict[str, float]) -> float:
        return self._cp[frozenset(z)]

    def _state(self, z: dict[str, float], T: float, P: float, F: float, H: float) -> StreamState:
        phase = Phase(
            kind=PhaseKind.VAPOR, mole_fraction=1.0, composition=z, density=1.0, molecular_weight=18.0
        )
        return StreamState(
            T=T, P=P, molar_flow=F, composition=z, vapor_fraction=0.0, enthalpy=H, entropy=0.0, phases=[phase]
        )

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        cp = self._cp_for(z)
        return self._state(z, T, P, molar_flow, cp * T)

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        cp = self._cp_for(z)
        return self._state(z, H / cp, P, molar_flow, H)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        cp = self._cp_for(composition)
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition=composition,
            molecular_weight=18.0,
            density=1.0,
            enthalpy=cp * T,
            entropy=0.0,
            cp=cp,
            gibbs=0.0,
            z_factor=1.0,
            viscosity=1e-4,
            thermal_conductivity=0.1,
        )


def test_closed_form_eps_ntu_solve() -> None:
    """Case 5: the counter-current epsilon-NTU solve on the fake constant-cp thermo.

    UA = 2000 W/K (constant ua_of), hot C = 1500 W/K, cold C = 2500 W/K
    (F = 10 mol/s, cp 150 / 250 J/(mol K)), T_h,in = 400 K, T_c,in = 300 K:
    NTU = 2000/1500 = 1.3333, Cr = 0.6, and the counter-current effectiveness
    eps = (1 - e^(-NTU(1-Cr))) / (1 - Cr e^(-NTU(1-Cr))) = 0.63787956 (hand
    value), so the analytic duty Q = eps*C_min*dT_imax = 0.63787956*1500*100 =
    95681.934 W. h = cp*T inverts exactly, so the solver's enthalpy-derived
    heat-capacity rates are exact here and the solve must reproduce the
    in-test analytic duty to rel 1e-9 (the solve, not the formula, is under
    test); the hand-printed anchors are checked at rel 1e-8 (print precision).
    The counter-current identity Q = UA*LMTD then closes on the solver's own
    outlet temperatures to rel 1e-12.
    """
    thermo = cast(Thermo, _LinearCpThermo(cp_hot=150.0, cp_cold=250.0))
    hot = StreamState(
        T=400.0,
        P=5e5,
        molar_flow=10.0,
        composition={"H2O": 1.0},
        vapor_fraction=0.0,
        enthalpy=150.0 * 400.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.VAPOR,
                mole_fraction=1.0,
                composition={"H2O": 1.0},
                density=1.0,
                molecular_weight=18.0,
            )
        ],
    )
    cold = StreamState(
        T=300.0,
        P=5e5,
        molar_flow=10.0,
        composition={"N2": 1.0},
        vapor_fraction=0.0,
        enthalpy=250.0 * 300.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.VAPOR,
                mole_fraction=1.0,
                composition={"N2": 1.0},
                density=1.0,
                molecular_weight=18.0,
            )
        ],
    )

    def eps_counterflow(NTU: float, Cr: float) -> float:
        ex = math.exp(-NTU * (1.0 - Cr))
        return (1.0 - ex) / (1.0 - Cr * ex)

    NTU_hand, Cr_hand = 2000.0 / 1500.0, 0.6
    eps_hand = eps_counterflow(NTU_hand, Cr_hand)
    Q_analytic = eps_hand * 1500.0 * (400.0 - 300.0)

    r = rate_two_stream(
        hot,
        cold,
        thermo,
        P_h_out=5e5,
        P_c_out=5e5,
        ua_of=lambda hot_out, cold_out: 2000.0,
        eps_of=eps_counterflow,
    )
    assert r.duty_W == pytest.approx(Q_analytic, rel=1e-9)
    assert r.duty_W == pytest.approx(95681.934, rel=1e-8)  # spec's hand anchor
    assert r.effectiveness == pytest.approx(0.63787956, rel=1e-8)
    assert r.NTU == pytest.approx(4.0 / 3.0, rel=1e-8)
    # Q = UA*LMTD on the solver's own terminals (constant cp, counter-current).
    dT1 = hot.T - r.cold_out.T
    dT2 = r.hot_out.T - cold.T
    lmtd = (dT1 - dT2) / math.log(dT1 / dT2)
    assert 2000.0 * lmtd == pytest.approx(r.duty_W, rel=1e-12)
