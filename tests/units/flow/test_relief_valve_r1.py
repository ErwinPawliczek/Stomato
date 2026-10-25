"""Closed-form, identity and refusal tests for relief_valve R1 (omega method).

Every expected constant was verified before being typed by an independent
scratch script (its own bisection, no brentq and no fluids); the constants
cross-check is listed in the PR body. Tolerances are the spec's: 1e-10
relative, 1e-9 on the brentq-based eta values.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units.flow import relief_valve as r0
from ngdesign.units.flow import relief_valve_r1 as rv1
from tests.conftest import flash_feed


def _v_mix(stream: StreamState) -> float:
    """Mass-weighted mixture specific volume, recomputed from the phases."""
    masses = [p.mole_fraction * p.molecular_weight / 1000.0 for p in stream.phases]
    return sum(m / p.density for m, p in zip(masses, stream.phases, strict=True)) / sum(masses)


def _solve(thermo: Thermo, feeds: dict[str, dict[str, Any]], params: dict[str, Any]) -> Any:
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    return rv1.ReliefValveR1().solve(inlets, params, thermo)


def _two_phase_inlet(thermo: Thermo, molar_flow: float = 100.0) -> StreamState:
    """A 50/50 C3/nC4 mixture flashed at 20 % vapour fraction, P0 = 2 MPa."""
    return thermo.flash_pvf({"C3": 0.5, "nC4": 0.5}, 2.0e6, 0.2, molar_flow)


# --- closed form: eta_c (eq. 2) -------------------------------------------


@pytest.mark.parametrize(
    ("omega", "expected"),
    [
        (0.5, 0.515218981376155),
        (1.0, 0.606530659712634),
        (5.0, 0.790060291109699),
        (20.0, 0.893774347286082),
    ],
)
def test_eta_c_exact(omega: float, expected: float) -> None:
    """eta_c matches the independent bisection to 1e-10 (constants cross-check)."""
    assert rv1.eta_c(omega) == pytest.approx(expected, rel=1e-10)


def test_eta_c_omega_one_is_exp_minus_half() -> None:
    """omega = 1 gives eta_c = exp(-1/2) to 1e-15 (the spec's analytic check)."""
    assert rv1.eta_c(1.0) == pytest.approx(math.exp(-0.5), rel=1e-15)


@pytest.mark.parametrize("omega", [0.5, 1.0, 5.0, 20.0])
def test_eta_c_leung_fit(omega: float) -> None:
    """Leung's explicit fit is within 5e-4 relative of the root at each check point."""
    assert rv1.eta_c_leung_fit(omega) == pytest.approx(rv1.eta_c(omega), rel=5e-4)


# --- closed form: omega and G (eqs. 1, 3) ---------------------------------


def test_omega_two_phase() -> None:
    """omega = 9 (v9/v0 - 1): v9/v0 = 1.55 gives 4.95."""
    assert rv1.omega_two_phase(0.02, 0.02 * 1.55) == pytest.approx(4.95, rel=1e-12)


def test_G_two_phase_critical_TP1() -> None:
    """TP1 (omega 5, P0 1e6, v0 0.02): critical at eta_a 0.5, G = 2498.390..."""
    G, critical = rv1.G_two_phase(1.0e6, 0.02, 5.0, 0.5)
    assert critical == 1
    assert G == pytest.approx(2498.39000876233, rel=1e-10)


def test_G_two_phase_continuity_at_eta_c() -> None:
    """The subcritical form evaluated at eta_a = eta_c gives the critical G to 1e-12."""
    omega, P0, v0 = 5.0, 1.0e6, 0.02
    ec = rv1.eta_c(omega)
    G_sub = (
        math.sqrt(-2.0 * (omega * math.log(ec) + (omega - 1.0) * (1.0 - ec)))
        * math.sqrt(P0 / v0)
        / (omega * (1.0 / ec - 1.0) + 1.0)
    )
    assert G_sub == pytest.approx(2498.39000876233, rel=1e-12)


def test_G_two_phase_subcritical_TP1() -> None:
    """TP1 at Pa/P0 = 0.8 (subcritical): G = 2497.2785..."""
    G, critical = rv1.G_two_phase(1.0e6, 0.02, 5.0, 0.8)
    assert critical == 0
    assert G == pytest.approx(2497.27854469590, rel=1e-10)


def test_area_TP1() -> None:
    """TP1: W 10 kg/s, Kd 0.85 gives A = 4.70891487761794e-3 m2 = 7.29883265797312 in2."""
    A = rv1.area_m2(10.0, 2498.39000876233, 0.85)
    assert A == pytest.approx(4.70891487761794e-3, rel=1e-12)
    assert A * r0.IN2_PER_M2 == pytest.approx(7.29883265797312, rel=1e-12)


# --- closed form: subcooled (eq. 4) ---------------------------------------


def test_eta_st_subcooled() -> None:
    """eta_st = 2 omega_s / (1 + 2 omega_s): omega_s 10 gives 0.952380952380952."""
    assert rv1.eta_st_subcooled(10.0) == pytest.approx(0.952380952380952, rel=1e-12)


def test_subcooled_low() -> None:
    """omega_s 10, eta_s 0.97: eta_c 0.883320897206597, critical G 6947.17538436639."""
    ec = rv1.eta_c_subcooled_low(10.0, 0.97)
    assert ec == pytest.approx(0.883320897206597, rel=1e-9)
    G, regime, critical = rv1.G_subcooled(1.0e6, 600.0, 10.0, 0.97, 0.8e6)
    assert regime == 2
    assert critical == 1
    assert G == pytest.approx(6947.17538436639, rel=1e-9)


def test_subcooled_saturated_limit() -> None:
    """At eta_s = 1 the subcooled root and G equal the saturated omega = 10 forms to 1e-12."""
    eta = rv1.eta_c_subcooled_low(10.0, 1.0)
    assert eta == pytest.approx(0.848568875287966, rel=1e-12)
    assert eta == pytest.approx(rv1.eta_c(10.0), rel=1e-12)
    G, regime, _critical = rv1.G_subcooled(1.0e6, 600.0, 10.0, 1.0, 0.7e6)
    assert regime == 2
    assert G == pytest.approx(6572.98624420048, rel=1e-12)
    G_tp, _ = rv1.G_two_phase(1.0e6, 1.0 / 600.0, 10.0, 0.7)
    assert G == pytest.approx(G_tp, rel=1e-12)


def test_subcooled_high_choked() -> None:
    """High subcooling (eta_s 0.5 < eta_st), Pa < Ps: choked at Ps, G = sqrt(2*600*5e5)."""
    G, regime, critical = rv1.G_subcooled(1.0e6, 600.0, 10.0, 0.5, 0.4e6)
    assert regime == 3
    assert critical == 1
    assert G == pytest.approx(math.sqrt(2.0 * 600.0 * 5.0e5), rel=1e-12)


def test_subcooled_non_flashing() -> None:
    """Pa above Ps: all-liquid, G = sqrt(2 rho (P0 - Pa)) — the API 520 Pt I liquid form."""
    G, regime, critical = rv1.G_subcooled(1.0e6, 600.0, 10.0, 0.5, 0.6e6)
    assert regime == 4
    assert critical == 0
    assert G == pytest.approx(math.sqrt(2.0 * 600.0 * 4.0e5), rel=1e-12)


def test_liquid_non_flashing_api520_example() -> None:
    """API 520 Pt I 10th ed. liquid example arithmetic: G 52821.2752591226, A 3.0660e-3 m2.

    Q 6814 L/min, rho 0.9*999, P1 1.1*1724 kPag + atm, P2 0.2*1724 kPag + atm,
    Kd 0.65, Kw 0.97 (the standard's printed result is 3066 mm2).
    """
    rho = 0.9 * 999.0
    P1 = 1.1 * 1724e3 + 101325.0
    P2 = 0.2 * 1724e3 + 101325.0
    G, regime, _critical = rv1.G_subcooled(P1, rho, 1.0, 0.1, P2)
    assert regime == 4
    assert G == pytest.approx(52821.2752591226, rel=1e-10)
    W = (6814.0 / 60000.0) * rho
    A = rv1.area_m2(W, G, 0.65, Kw=0.97)
    assert A == pytest.approx(3.06594883829264e-3, rel=1e-9)


# --- adapter: identities ----------------------------------------------------


def test_r1_gas_identity_with_r0(thermo: Thermo) -> None:
    """An all-vapour inlet gives R0's result unchanged; info gains regime_code 0."""
    feeds, params = r0.ReliefValve.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    base = r0.ReliefValve().solve(inlets, params, thermo)
    got = rv1.ReliefValveR1().solve(inlets, params, thermo)
    assert got.info["regime_code"] == 0
    for port, state in base.outlets.items():
        other = got.outlets[port]
        for field in ("T", "P", "molar_flow", "vapor_fraction", "enthalpy", "entropy"):
            assert getattr(other, field) == getattr(state, field)
    for key, value in base.info.items():
        assert got.info[key] == value, key


def test_r1_two_phase_omega_recomputed(thermo: Thermo) -> None:
    """A flash_pvf vf-0.2 inlet: omega equals 9 (v9/v0 - 1) recomputed in the test."""
    inlet = _two_phase_inlet(thermo)
    result = rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 6.0e5}, thermo)
    assert result.info["regime_code"] == 1
    z = {"C3": 0.5, "nC4": 0.5}
    flashed = thermo.flash_ps(z, 1.8e6, inlet.entropy, 100.0)
    expected = 9.0 * (_v_mix(flashed) / _v_mix(inlet) - 1.0)
    assert result.info["omega"] == pytest.approx(expected, rel=1e-10)


def test_r1_area_matches_eq5(thermo: Thermo) -> None:
    """The reported area equals eq. 5 recomputed from the reported G and all factors."""
    inlet = _two_phase_inlet(thermo)
    params = {"P_back": 6.0e5, "Kb": 0.9, "Kc": 0.95, "Kv": 0.9, "Kw": 0.85}
    result = rv1.ReliefValveR1().solve({"inlet": inlet}, params, thermo)
    info = result.info
    expected = inlet.mass_flow / (
        info["Kd_used"] * params["Kb"] * params["Kc"] * params["Kv"] * params["Kw"] * info["G_kg_m2s"]
    )
    assert info["required_area_m2"] == pytest.approx(expected, rel=1e-12)
    assert info["required_area_in2"] == pytest.approx(expected * r0.IN2_PER_M2, rel=1e-12)
    assert info["required_area_mm2"] == pytest.approx(expected * 1.0e6, rel=1e-12)


def test_r1_subcooled_propane_regimes(thermo: Thermo) -> None:
    """Subcooled propane at T0 300 K, P0 = 2x bubble P: regime 3 or 4 by P_back."""
    z = {"C3": 1.0}
    psat = thermo.bubble_point(z, T=300.0).P
    inlet = flash_feed(thermo, {"T": 300.0, "P": 2.0 * psat, "molar_flow": 5000.0, "composition": z})
    choked = rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 0.2 * psat}, thermo)
    assert choked.info["critical"] == 1
    assert choked.info["regime_code"] in (2, 3)
    non_flashing = rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 1.5 * psat}, thermo)
    assert non_flashing.info["critical"] == 0
    assert non_flashing.info["regime_code"] in (2, 4)


# --- refusals ---------------------------------------------------------------


def test_r1_refuses_p_back_out_of_range(thermo: Thermo) -> None:
    """P_back at or above the relieving pressure is refused (R0's own check)."""
    feeds, _ = r0.ReliefValve.example_case()
    with pytest.raises(r0.ReliefValveSpecError, match="P_back"):
        _solve(thermo, feeds, {"P_back": 5.0e7})


def test_r1_refuses_k_factors(thermo: Thermo) -> None:
    """Each correction factor must be in (0, 1]; the error names it."""
    inlet = _two_phase_inlet(thermo)
    with pytest.raises(rv1.ReliefValveSpecError, match="Kd"):
        rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 6.0e5, "Kd": 1.5}, thermo)
    with pytest.raises(rv1.ReliefValveSpecError, match="Kw"):
        rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 6.0e5, "Kw": 0.0}, thermo)


def test_omega_refusal() -> None:
    """omega <= 0 is refused (adapter-level unreachable: decompression raises v)."""
    with pytest.raises(rv1.ReliefValveR1Error, match="omega"):
        rv1.omega_two_phase(1.0, 1.0)


def test_eta_c_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed root-find is a typed refusal, not a scipy ValueError."""

    def boom(*args: Any, **kwargs: Any) -> None:
        raise ValueError("no bracket")

    monkeypatch.setattr(rv1, "brentq", boom)
    with pytest.raises(rv1.ReliefValveR1Error, match="critical pressure ratio did not converge"):
        rv1.eta_c(5.0)


def test_r1_refuses_oversized_area(thermo: Thermo) -> None:
    """A required area above the API 526 T orifice is refused by R0's selector."""
    inlet = _two_phase_inlet(thermo, molar_flow=1.0e6)
    with pytest.raises(r0.ReliefValveSpecError, match="API 526"):
        rv1.ReliefValveR1().solve({"inlet": inlet}, {"P_back": 6.0e5}, thermo)
