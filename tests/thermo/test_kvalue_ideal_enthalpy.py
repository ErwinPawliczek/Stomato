"""BK10 with ideal enthalpies against the Lee-Kesler braun-k10 row.

Anchor: n-pentane heat of vaporisation 25.79 kJ/mol at its normal boiling point (NIST
WebBook, Majer & Svoboda 1985 selection).
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind

Z = {"n-pentane": 1.0}


def test_k_values_are_the_base_rows() -> None:
    feed = {"n-butane": 0.5, "n-pentane": 0.5}
    a = registry.create("thermo", "braun-k10").flash_pt(feed, 300.0, 1.5e5, 1.0)
    b = registry.create("thermo", "braun-k10-ideal").flash_pt(feed, 300.0, 1.5e5, 1.0)
    assert b.vapor_fraction == a.vapor_fraction
    assert b.phases[0].composition == a.phases[0].composition
    assert b.enthalpy != a.enthalpy


def test_vapour_enthalpy_has_no_pressure_departure() -> None:
    ideal = registry.create("thermo", "braun-k10-ideal")
    lk = registry.create("thermo", "braun-k10")
    assert ideal.phase_props(Z, 400.0, 5e5, PhaseKind.VAPOR).enthalpy == pytest.approx(
        ideal.phase_props(Z, 400.0, 1e4, PhaseKind.VAPOR).enthalpy, rel=1e-12
    )
    assert (
        lk.phase_props(Z, 400.0, 5e5, PhaseKind.VAPOR).enthalpy
        < lk.phase_props(Z, 400.0, 1e4, PhaseKind.VAPOR).enthalpy
    )


def test_latent_heat_matches_the_published_value_and_entropy_is_consistent() -> None:
    """The Lee-Kesler basis misses both: 3.5 % low, and dS != dH / T at equilibrium."""
    ideal = registry.create("thermo", "braun-k10-ideal")
    T = ideal.bubble_point(Z, P=101325.0).T
    vap = ideal.phase_props(Z, T, 101325.0, PhaseKind.VAPOR)
    liq = ideal.phase_props(Z, T, 101325.0, PhaseKind.HC_LIQUID)
    assert vap.enthalpy - liq.enthalpy == pytest.approx(25790.0, rel=0.005)
    assert vap.entropy - liq.entropy == pytest.approx((vap.enthalpy - liq.enthalpy) / T, rel=1e-9)

    lk = registry.create("thermo", "braun-k10")
    d_h = (
        lk.phase_props(Z, T, 101325.0, PhaseKind.VAPOR).enthalpy
        - lk.phase_props(Z, T, 101325.0, PhaseKind.HC_LIQUID).enthalpy
    )
    assert abs(d_h - 25790.0) > 3.0 * abs(vap.enthalpy - liq.enthalpy - 25790.0)


def test_liquid_above_tc_refuses() -> None:
    ideal = registry.create("thermo", "braun-k10-ideal")
    with pytest.raises(ValueError, match="above its critical temperature"):
        ideal.phase_props({"methane": 1.0}, 300.0, 1e5, PhaseKind.HC_LIQUID)
