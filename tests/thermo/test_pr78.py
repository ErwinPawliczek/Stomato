"""Tests for the Peng-Robinson 1978 thermo plugin (expansion spec, item 2).

Oracles are computed per-EOS from the thermo library directly in this file —
never copied from the pr tests' expected values.

Note on PR78 vs PR: the 1978 variant modifies the alpha correlation for
acentric factors above ~0.491, so for light natural-gas components PR78 and PR
coincide (verified this session: identical slice output) and only methanol/
MEG/TEG-bearing cases diverge. The different-from-pr assertions below target a
methanol-bearing case for exactly that reason.
"""

from __future__ import annotations

import json
import math
from typing import Any, cast

import pytest
from thermo import PR78MIX, CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVLN
from thermo.interaction_parameters import IPDB

from ngdesign import registry
from ngdesign.contracts import Flowsheet, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.flowsheets.slice import INLET_COMPOSITION
from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.thermo.pr78 import PengRobinson78Thermo

GAS = {"N2": 0.01, "CO2": 0.02, "C1": 0.85, "C2": 0.07, "C3": 0.03, "nC4": 0.02}
VLE = {"C1": 0.6, "nC5": 0.4}  # two-phase at 300 K / 3 MPa
MEOH_VAPOR = {"C1": 0.9, "MeOH": 0.1}  # MeOH omega 0.565 > 0.491: PR78 alpha differs


@pytest.fixture(scope="module")
def thermo() -> Thermo:
    """The plugin, resolved through the registry (validates self-registration)."""
    assert "pr78" in registry.available("thermo"), "pr78 thermo plugin not discovered"
    impl: Thermo = registry.create("thermo", "pr78")
    return impl


def _reference_flasher(cas: list[str]) -> FlashVLN:
    """A FlashVLN over PR78MIX built in this file, independent of the plugin module."""
    constants, correlations = ChemicalConstantsPackage.from_IDs(cas)
    kijs = IPDB.get_ip_symmetric_matrix(name="ChemSep PR", CASs=cas, ip="kij")
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    heat_caps = correlations.HeatCapacityGases
    gas = CEOSGas(PR78MIX, eos_kwargs, HeatCapacityGases=heat_caps)
    liquids = [
        CEOSLiquid(PR78MIX, eos_kwargs, HeatCapacityGases=heat_caps),
        CEOSLiquid(PR78MIX, eos_kwargs, HeatCapacityGases=heat_caps),
    ]
    return FlashVLN(constants, correlations, liquids=liquids, gas=gas)


def _cas(ids: list[str]) -> list[str]:
    from ngdesign.data import components

    table = components()
    return [str(table[cid]["cas"]) for cid in ids]


def _canonical(state: StreamState) -> str:
    """Byte-stable serialization for the determinism double-run comparison."""
    return json.dumps(
        {
            "T": state.T,
            "P": state.P,
            "vapor_fraction": state.vapor_fraction,
            "enthalpy": state.enthalpy,
            "entropy": state.entropy,
            "phases": [
                {
                    "kind": p.kind.value,
                    "mole_fraction": p.mole_fraction,
                    "composition": sorted(p.composition.items()),
                    "density": p.density,
                    "viscosity": p.viscosity,
                    "z_factor": p.z_factor,
                    "molecular_weight": p.molecular_weight,
                }
                for p in state.phases
            ],
        },
        sort_keys=True,
    )


def test_plugin_satisfies_thermo_protocol() -> None:
    assert isinstance(PengRobinson78Thermo(), Thermo)


def test_flowsheet_selection_resolves(thermo: Thermo) -> None:
    """Flowsheet(thermo='pr78') resolves to a working plugin through the registry."""
    fs = Flowsheet(name="x", units=[], streams=[], thermo="pr78")
    assert fs.thermo == "pr78"
    resolved: Thermo = registry.create("thermo", fs.thermo)
    assert isinstance(resolved, PengRobinson78Thermo)


def test_methane_vapor_vs_library_reference(thermo: Thermo) -> None:
    ref = _reference_flasher(_cas(["C1"])).flash(T=300.0, P=1.0e6, zs=[1.0])
    s = thermo.flash_pt({"C1": 1.0}, 300.0, 1.0e6, 100.0)
    assert isinstance(s, StreamState)
    assert s.vapor_fraction == pytest.approx(1.0)
    assert [p.kind for p in s.phases] == ["vapor"]
    assert s.phases[0].density == pytest.approx(float(cast(float, ref.phases[0].rho_mass())), rel=1e-6)
    assert s.enthalpy == pytest.approx(float(ref.H()), rel=1e-6)
    assert s.phases[0].molecular_weight == pytest.approx(16.0425, abs=1e-3)
    assert s.phases[0].composition == {"C1": 1.0}
    z = s.phases[0].z_factor
    assert z is not None and 0.9 < z < 1.1  # near-ideal at 300 K / 1 MPa


def test_two_phase_flash_vs_library_reference(thermo: Thermo) -> None:
    ref = _reference_flasher(_cas(["C1", "nC5"])).flash(T=300.0, P=3.0e6, zs=[0.6, 0.4])
    s = thermo.flash_pt(VLE, 300.0, 3.0e6, 1.0)
    assert 0.0 < s.vapor_fraction < 1.0
    assert s.vapor_fraction == pytest.approx(float(cast(float, ref.phases[0].beta)), rel=1e-6)
    gas_ref = next(p for p in ref.phases if isinstance(p, CEOSGas))
    gas_got = next(p for p in s.phases if p.kind.value == "vapor")
    assert gas_got.density == pytest.approx(float(gas_ref.rho_mass()), rel=1e-6)
    for c, zc in VLE.items():  # material balance
        back = sum(p.mole_fraction * p.composition.get(c, 0.0) for p in s.phases)
        assert math.isclose(back, zc, abs_tol=1e-6)


def test_free_water_phase(thermo: Thermo) -> None:
    """Water mole fraction > 0.5 classifies a liquid as AQUEOUS (spec rule)."""
    s = thermo.flash_pt({"C1": 0.9, "H2O": 0.1}, 300.0, 3.0e6, 1.0)
    assert "aqueous" in {p.kind.value for p in s.phases}


def test_ph_roundtrip(thermo: Thermo) -> None:
    a = thermo.flash_pt(GAS, 310.0, 4.0e6, 10.0)
    b = thermo.flash_ph(GAS, 4.0e6, a.enthalpy, 10.0)
    assert math.isclose(b.T, a.T, abs_tol=0.05)


def test_ps_roundtrip(thermo: Thermo) -> None:
    a = thermo.flash_pt(GAS, 310.0, 4.0e6, 10.0)
    b = thermo.flash_ps(GAS, 4.0e6, a.entropy, 10.0)
    assert math.isclose(b.T, a.T, abs_tol=0.05)


def test_slice_determinism_double_run(thermo: Thermo) -> None:
    """The sample slice solves deterministically under PR78.

    The slice is all light components (omega < 0.491), where the 1978 alpha
    modification is inactive — so its stream table legitimately matches PR's
    byte for byte; the PR78-vs-PR divergence is asserted on the MeOH case below.
    """
    a = _canonical(thermo.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 1.0))
    b = _canonical(thermo.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 1.0))
    assert a == b  # byte-identical across runs

    pr = PengRobinsonThermo()
    c = _canonical(pr.flash_pt(INLET_COMPOSITION, 293.15, 3.447e6, 1.0))
    assert a == c  # expected: identical physics on omega < 0.491 components


def test_methanol_case_differs_from_pr(thermo: Thermo) -> None:
    """With MeOH present (omega > 0.491) PR78's alpha changes the gas density."""
    s = thermo.flash_pt(MEOH_VAPOR, 320.0, 1.0e6, 1.0)
    p = PengRobinsonThermo().flash_pt(MEOH_VAPOR, 320.0, 1.0e6, 1.0)
    rho_78 = next(x for x in s.phases if x.kind.value == "vapor").density
    rho_pr = next(x for x in p.phases if x.kind.value == "vapor").density
    assert not math.isclose(rho_78, rho_pr, rel_tol=1e-3)


def test_unknown_selection_lists_registered_plugins() -> None:
    """The registry seam under the API's 501 names every registered thermo plugin."""
    with pytest.raises(KeyError) as excinfo:
        registry.create("thermo", "no_such_thermo")
    message = str(excinfo.value)
    for name in registry.available("thermo"):
        assert name in message
