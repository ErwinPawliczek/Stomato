"""Own tests for the Peng-Robinson thermo plugin (spec S-01)."""

from __future__ import annotations

import math
import time

import pytest
from CoolProp.CoolProp import PropsSI

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets.slice import LEAN_TEG_COMPOSITION
from ngdesign.thermo.pr import PengRobinsonThermo


@pytest.fixture(scope="module")
def thermo() -> Thermo:
    """The plugin, resolved through the registry (validates self-registration)."""
    assert "pr" in registry.available("thermo"), "pr thermo plugin not discovered"
    return registry.create("thermo", "pr")


def test_plugin_satisfies_thermo_protocol() -> None:
    assert isinstance(PengRobinsonThermo(), Thermo)


def test_single_component_methane_vapor(thermo: Thermo) -> None:
    s = thermo.flash_pt({"C1": 1.0}, 300.0, 1.0e6, 100.0)
    assert isinstance(s, StreamState)
    assert s.vapor_fraction == pytest.approx(1.0)
    assert [p.kind for p in s.phases] == ["vapor"]
    ref = PropsSI("D", "T", 300.0, "P", 1.0e6, "Methane")
    assert s.phases[0].density == pytest.approx(ref, rel=0.05)
    assert 0.9 < s.phases[0].z_factor < 1.1  # methane at 300 K / 1 MPa is near-ideal
    assert s.phases[0].molecular_weight == pytest.approx(16.0425, abs=1e-3)
    assert s.phases[0].composition == {"C1": 1.0}
    assert s.phases[0].viscosity is not None
    assert math.isfinite(s.enthalpy) and math.isfinite(s.entropy)


def test_single_component_water_is_aqueous(thermo: Thermo) -> None:
    """Water mole fraction > 0.5 classifies a liquid as AQUEOUS (spec rule)."""
    s = thermo.flash_pt({"H2O": 1.0}, 320.0, 1.0e6, 100.0)
    assert s.vapor_fraction == pytest.approx(0.0)
    assert [p.kind for p in s.phases] == ["aqueous"]
    assert s.phases[0].z_factor is None  # z_factor is a vapor-only field
    assert s.phases[0].viscosity is not None


def test_zero_fraction_component_dropped_then_mapped_back(thermo: Thermo) -> None:
    """A zero-fraction component must not reach thermo but must map back with 0.0."""
    z = {"C1": 1.0, "H2O": 0.0}
    s = thermo.flash_pt(z, 300.0, 1.0e6, 100.0)
    assert s.composition == z
    assert all("H2O" in p.composition and p.composition["H2O"] == 0.0 for p in s.phases)


def test_lean_teg_all_liquid(thermo: Thermo) -> None:
    """Slice lean-glycol feed at its contactor inlet conditions is all liquid."""
    s = thermo.flash_pt(LEAN_TEG_COMPOSITION, 325.15, 7.1e6, 3.2)
    assert s.vapor_fraction == pytest.approx(0.0)
    assert len(s.phases) == 1
    kind = s.phases[0].kind
    assert kind == "hc_liquid"  # water fraction 0.0989 <= 0.5 per the spec's rule
    assert s.phases[0].density > 800.0  # kg/m3, glycol-rich liquid
    assert math.isclose(sum(p.mole_fraction for p in s.phases), 1.0, abs_tol=1e-9)


def test_c6plus_and_h2s_ph_ps_roundtrip(thermo: Thermo) -> None:
    """C6+ (n-hexane) and H2S map through CAS and survive PH/PS round-trips."""
    z = {"C1": 0.60, "nC5": 0.20, "C6+": 0.20}
    a = thermo.flash_pt(z, 400.0, 2.0e6, 50.0)
    assert math.isclose(thermo.flash_ph(z, 2.0e6, a.enthalpy, 50.0).T, a.T, abs_tol=0.05)
    assert math.isclose(thermo.flash_ps(z, 2.0e6, a.entropy, 50.0).T, a.T, abs_tol=0.05)

    z2 = {"C1": 0.84, "CO2": 0.08, "H2S": 0.05, "N2": 0.03}
    b = thermo.flash_pt(z2, 310.0, 4.0e6, 50.0)
    assert math.isclose(thermo.flash_ph(z2, 4.0e6, b.enthalpy, 50.0).T, b.T, abs_tol=0.05)
    assert math.isclose(thermo.flash_ps(z2, 4.0e6, b.entropy, 50.0).T, b.T, abs_tol=0.05)


def test_phase_fractions_and_material_balance(thermo: Thermo) -> None:
    """Phase mole fractions sum to 1 and composition is preserved through the split."""
    z = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}
    s = thermo.flash_pt(z, 300.0, 3.0e6, 10.0)
    assert math.isclose(sum(p.mole_fraction for p in s.phases), 1.0, abs_tol=1e-9)
    assert s.vapor_fraction == pytest.approx(sum(p.mole_fraction for p in s.phases if p.kind == "vapor"))
    for c, zc in z.items():
        back = sum(p.mole_fraction * p.composition[c] for p in s.phases)
        assert math.isclose(back, zc, abs_tol=1e-6)


def test_slice_inlet_flash_under_one_second(thermo: Thermo) -> None:
    """Flash of the slice inlet takes < 1 s on a warm cache (spec criterion)."""
    from ngdesign.flowsheets.slice import INLET_COMPOSITION

    thermo.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 10.0)  # warm the cached flasher
    t0 = time.perf_counter()
    s = thermo.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 10.0)
    assert time.perf_counter() - t0 < 1.0
    assert 0.0 < s.vapor_fraction < 1.0
    assert sorted(p.kind for p in s.phases) == ["aqueous", "hc_liquid", "vapor"]
