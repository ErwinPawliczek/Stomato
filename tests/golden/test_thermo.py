"""Thermo oracle: Peng-Robinson package vs CoolProp reference + self-consistency. LOCKED."""

import math

import pytest
from CoolProp.CoolProp import PropsSI

from ngdesign.contracts.plugins import Thermo

PURE = [("C1", "Methane"), ("C2", "Ethane"), ("N2", "Nitrogen"), ("CO2", "CarbonDioxide")]


@pytest.mark.parametrize(("comp", "cp_name"), PURE)
@pytest.mark.parametrize(("T", "P"), [(300.0, 1.0e6), (320.0, 5.0e6)])
def test_pure_gas_density_vs_coolprop(thermo: Thermo, comp: str, cp_name: str, T: float, P: float) -> None:
    s = thermo.flash_pt({comp: 1.0}, T, P, 1.0)
    ref = PropsSI("D", "T", T, "P", P, cp_name)  # kg/m3, reference EOS
    rho = s.phases[0].density
    assert math.isclose(rho, ref, rel_tol=0.05), f"{comp} {T}K {P}Pa: PR {rho} vs ref {ref}"


def _gas() -> dict[str, float]:
    return {"N2": 0.01, "CO2": 0.02, "C1": 0.85, "C2": 0.07, "C3": 0.03, "nC4": 0.02}


def test_ph_roundtrip(thermo: Thermo) -> None:
    a = thermo.flash_pt(_gas(), 310.0, 4.0e6, 10.0)
    b = thermo.flash_ph(_gas(), 4.0e6, a.enthalpy, 10.0)
    assert math.isclose(b.T, a.T, abs_tol=0.05)


def test_ps_roundtrip(thermo: Thermo) -> None:
    a = thermo.flash_pt(_gas(), 310.0, 4.0e6, 10.0)
    b = thermo.flash_ps(_gas(), 4.0e6, a.entropy, 10.0)
    assert math.isclose(b.T, a.T, abs_tol=0.05)


def test_two_phase_material_balance(thermo: Thermo) -> None:
    z = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}
    s = thermo.flash_pt(z, 300.0, 3.0e6, 1.0)
    assert 0.0 < s.vapor_fraction < 1.0
    for c, zc in z.items():
        back = sum(p.mole_fraction * p.composition.get(c, 0.0) for p in s.phases)
        assert math.isclose(back, zc, abs_tol=1e-6)


def test_free_water_phase(thermo: Thermo) -> None:
    z = {"C1": 0.9, "H2O": 0.1}
    s = thermo.flash_pt(z, 300.0, 3.0e6, 1.0)
    kinds = {p.kind.value for p in s.phases}
    assert "aqueous" in kinds


def test_slice_inlet_three_phase(thermo: Thermo) -> None:
    from ngdesign.flowsheets.slice import INLET_COMPOSITION

    s = thermo.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 1.0)
    kinds = sorted(p.kind.value for p in s.phases)
    assert kinds == ["aqueous", "hc_liquid", "vapor"], kinds


# --- spec P1-01 additions: saturation vs CoolProp --------------------------------

PURE_SAT = [
    ("C1", "Methane", (120.0, 140.0, 160.0)),
    ("C2", "Ethane", (200.0, 250.0, 280.0)),
    ("C3", "n-Propane", (250.0, 300.0, 320.0)),
    ("H2O", "Water", (450.0, 480.0, 500.0)),
]


@pytest.mark.parametrize(("comp", "cp_name", "ts"), PURE_SAT)
def test_pure_bubble_vs_coolprop(thermo: Thermo, comp: str, cp_name: str, ts: tuple[float, ...]) -> None:
    for T in ts:
        point = thermo.bubble_point({comp: 1.0}, T=T)
        ref = PropsSI("P", "T", T, "Q", 0, cp_name)
        assert math.isclose(point.P, ref, rel_tol=0.02), f"{comp} {T}K: PR {point.P} vs ref {ref}"


@pytest.mark.parametrize(("comp", "cp_name", "ts"), PURE_SAT)
def test_pure_dew_vs_coolprop(thermo: Thermo, comp: str, cp_name: str, ts: tuple[float, ...]) -> None:
    for T in ts:
        point = thermo.dew_point({comp: 1.0}, T=T)
        ref = PropsSI("P", "T", T, "Q", 1, cp_name)
        assert math.isclose(point.P, ref, rel_tol=0.02), f"{comp} {T}K: PR {point.P} vs ref {ref}"


@pytest.mark.parametrize(("comp", "ts"), [(c, ts) for c, _cp, ts in PURE_SAT])
def test_pure_dew_equals_bubble(thermo: Thermo, comp: str, ts: tuple[float, ...]) -> None:
    """A pure fluid has one saturation pressure; both solvers converge on the same jump."""
    for T in ts:
        bubble = thermo.bubble_point({comp: 1.0}, T=T)
        dew = thermo.dew_point({comp: 1.0}, T=T)
        assert math.isclose(dew.P, bubble.P, rel_tol=1e-6), f"{comp} {T}K"
