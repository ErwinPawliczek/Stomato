"""phase_props: single-phase properties consistent with flash-built phases (P1-01)."""

from __future__ import annotations

import math

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind

Z = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}
T = 300.0
P = 3.0e6


def test_phase_props_match_flash_phases(thermo: Thermo) -> None:
    """phase_props recomputes the same numbers a flash phase carries at its own state."""
    s = thermo.flash_pt(dict(Z), T, P, 1.0)
    assert 0.0 < s.vapor_fraction < 1.0
    for ph in s.phases:
        pp = thermo.phase_props(ph.composition, T, P, ph.kind)
        assert math.isclose(pp.enthalpy, ph.enthalpy, rel_tol=1e-9), ph.kind
        assert math.isclose(pp.entropy, ph.entropy, rel_tol=1e-9), ph.kind
        assert math.isclose(pp.cp, ph.cp, rel_tol=1e-9), ph.kind
        assert math.isclose(pp.molecular_weight, ph.molecular_weight, rel_tol=1e-9)
        assert math.isclose(pp.density, ph.density, rel_tol=1e-9)
        for cid, v in ph.ln_phi.items():
            if ph.composition[cid] > 0.0:
                assert math.isclose(pp.ln_phi[cid], v, rel_tol=1e-9, abs_tol=1e-12), (ph.kind, cid)


def test_mixture_enthalpy_from_phases(thermo: Thermo) -> None:
    """H, S of the stream are the mole-weighted phase sums (mass balance)."""
    s = thermo.flash_pt(dict(Z), T, P, 1.0)
    enthalpy = sum(p.mole_fraction * p.enthalpy for p in s.phases)
    entropy = sum(p.mole_fraction * p.entropy for p in s.phases)
    assert math.isclose(enthalpy, s.enthalpy, rel_tol=1e-9)
    assert math.isclose(entropy, s.entropy, rel_tol=1e-9)


def test_phase_props_gas_law_consistency(thermo: Thermo) -> None:
    """The built (non-flashed) phase's compressibility matches its density."""
    pp = thermo.phase_props(dict(Z), T, P, PhaseKind.VAPOR)
    v_molar = pp.molecular_weight / (1000.0 * pp.density)
    assert math.isclose(pp.z_factor, P * v_molar / (8.31446261815324 * T), rel_tol=1e-9)


def test_phase_props_fresh_package(thermo: Thermo) -> None:
    """Same numbers from a freshly built package (no dependence on prior state)."""
    fresh: Thermo = registry.create("thermo", "pr")
    a = fresh.phase_props(dict(Z), T, P, PhaseKind.HC_LIQUID)
    b = thermo.phase_props(dict(Z), T, P, PhaseKind.HC_LIQUID)
    assert a == b


def test_nrtl_phase_props() -> None:
    """GE-liquid and gas phases expose the same surface on the NRTL package."""
    nrtl: Thermo = registry.create("thermo", "nrtl")
    gas = nrtl.phase_props({"H2O": 0.5, "MeOH": 0.5}, 400.0, 1.0e5, PhaseKind.VAPOR)
    liquid = nrtl.phase_props({"H2O": 0.5, "MeOH": 0.5}, 400.0, 1.0e5, PhaseKind.HC_LIQUID)
    assert gas.density > 0.0 and liquid.density > 0.0
    assert math.isclose(gas.z_factor, 1.0, rel_tol=0.1)
    assert set(liquid.ln_phi) == {"H2O", "MeOH"}
