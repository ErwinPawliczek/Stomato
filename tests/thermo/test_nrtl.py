"""Own tests for the NRTL thermo plugin (expansion spec: selectable thermodynamics)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from thermo import PRMIX, CEOSGas, ChemicalConstantsPackage, FlashVL, GibbsExcessLiquid
from thermo.interaction_parameters import IPDB
from thermo.nrtl import NRTL

from ngdesign import registry
from ngdesign.contracts import Flowsheet, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.thermo.nrtl import NrtlThermo

# The one multi-component support the ChemSep NRTL databank covers besides pure
# components (verified against thermo 0.6.1 in-session): H2O/MeOH, bij fitted in
# both directions. Sorted order matches the plugin's support key.
_IDS = ("H2O", "MeOH")
_T = 350.0  # K - inside the two-phase VLE region for 50/50 at 1 atm
_P = 101325.0  # Pa abs
_Z = {"H2O": 0.5, "MeOH": 0.5}


def _cas_list(ids: tuple[str, ...]) -> list[str]:
    comps = components()
    return [str(comps[cid]["cas"]) for cid in ids]


@pytest.fixture(scope="module")
def thermo() -> Thermo:
    """The plugin, resolved through the registry (validates self-registration)."""
    assert "nrtl" in registry.available("thermo"), "nrtl thermo plugin not discovered"
    impl: Thermo = registry.create("thermo", "nrtl")
    return impl


def _reference_flasher() -> Any:
    """Independently built FlashVL over the same databank parameters.

    Shares no code with the plugin - single GE liquid, no stability re-split, no
    phase classification - so agreement pins the plugin's FlashVLN wiring rather
    than itself. bij is fetched asymmetrically (tau_ij != tau_ji); mirroring it
    symmetrically would silently produce different non-ideality.
    """
    cas_list = _cas_list(_IDS)
    constants, correlations = ChemicalConstantsPackage.from_IDs(cas_list)
    tau_bs = IPDB.get_ip_asymmetric_matrix(name="ChemSep NRTL", CASs=cas_list, ip="bij")
    alpha_cs = IPDB.get_ip_asymmetric_matrix(name="ChemSep NRTL", CASs=cas_list, ip="alphaij")
    heat_caps = correlations.HeatCapacityGases
    model = NRTL(xs=[1.0 / len(_IDS)] * len(_IDS), T=_T, tau_bs=tau_bs, alpha_cs=alpha_cs)
    liquid = GibbsExcessLiquid(
        VaporPressures=correlations.VaporPressures,
        HeatCapacityGases=heat_caps,
        HeatCapacityLiquids=correlations.HeatCapacityLiquids,
        EnthalpyVaporizations=correlations.EnthalpyVaporizations,
        VolumeLiquids=correlations.VolumeLiquids,
        GibbsExcessModel=model,
    )
    gas = CEOSGas(
        PRMIX,
        {
            "Tcs": constants.Tcs,
            "Pcs": constants.Pcs,
            "omegas": constants.omegas,
            "kijs": IPDB.get_ip_symmetric_matrix(name="ChemSep PR", CASs=cas_list, ip="kij"),
        },
        HeatCapacityGases=heat_caps,
    )
    return FlashVL(constants, correlations, gas=gas, liquid=liquid)


def test_plugin_satisfies_thermo_protocol() -> None:
    assert isinstance(NrtlThermo(), Thermo)


def test_thermo_field_resolves_nrtl_plugin(thermo: Thermo) -> None:
    """Flowsheet.thermo='nrtl' resolves through the registry seam the solve API uses."""
    fs = Flowsheet(name="nrtl-resolution", units=[], streams=[], thermo="nrtl")
    assert registry.get("thermo", fs.thermo) is NrtlThermo
    assert registry.create("thermo", fs.thermo) is not None
    s = thermo.flash_pt(_Z, _T, _P, 10.0)
    assert isinstance(s, StreamState)


def test_water_methanol_vle_matches_independent_library_flash(thermo: Thermo) -> None:
    """Plugin VLE equals an independently constructed FlashVL over the same BIPs."""
    s = thermo.flash_pt(_Z, _T, _P, 10.0)
    reference = _reference_flasher().flash(zs=[0.5, 0.5], T=_T, P=_P)

    vapor = next(p for p in s.phases if p.kind == "vapor")
    assert vapor.mole_fraction == pytest.approx(float(reference.VF), abs=1e-8)
    assert vapor.composition["MeOH"] == pytest.approx(float(reference.gas.zs[1]), abs=1e-8)

    liquid = next(p for p in s.phases if p.kind != "vapor")
    assert liquid.composition["H2O"] == pytest.approx(float(reference.liquids[0].zs[0]), abs=1e-8)

    # Vapour enriched in the more volatile methanol, liquid in water - the
    # direction the fitted parameters demand.
    assert vapor.composition["MeOH"] > 0.5 > liquid.composition["MeOH"]


def test_water_methanol_vle_deviates_from_raoult_ideal(thermo: Thermo) -> None:
    """A zero-filled BIP matrix returns exactly Raoult-ideal vapour; fitted BIPs must not.

    With every bij = 0 the NRTL residual term vanishes and y equals the ideal-K
    prediction, so measurable deviation from it is the anti-silent-ideal assertion
    (observed delta ~ 0.107 mole fraction for methanol at these conditions).
    """
    s = thermo.flash_pt(_Z, _T, _P, 10.0)
    vapor = next(p for p in s.phases if p.kind == "vapor")

    _constants, correlations = ChemicalConstantsPackage.from_IDs(_cas_list(_IDS))
    psat = [float(vp.T_dependent_property(_T)) for vp in correlations.VaporPressures]
    k_times_x = [ps / _P * _Z[cid] for ps, cid in zip(psat, _IDS, strict=True)]
    y_ideal_meoh = k_times_x[1] / sum(k_times_x)
    assert abs(vapor.composition["MeOH"] - y_ideal_meoh) > 0.02


def test_missing_pair_raises_at_construction() -> None:
    """ChemSep NRTL has no fitted H2O/TEG pair: constructing over that support raises."""
    with pytest.raises(ValueError, match=r"H2O.*TEG"):
        NrtlThermo(components=("H2O", "TEG"))


def test_missing_pair_support_never_flashes(thermo: Thermo) -> None:
    """A flash over a support with a databank-missing pair raises before any state."""
    with pytest.raises(ValueError, match=r"H2O.*TEG"):
        thermo.flash_pt({"H2O": 0.5, "TEG": 0.5}, _T, _P, 10.0)


def test_pure_water_is_aqueous(thermo: Thermo) -> None:
    """A pure component has no pairs: the support flashes without the databank check."""
    s = thermo.flash_pt({"H2O": 1.0}, 350.0, _P, 10.0)
    assert s.vapor_fraction == pytest.approx(0.0)
    assert [p.kind for p in s.phases] == ["aqueous"]
    assert s.phases[0].composition == {"H2O": 1.0}
    assert s.phases[0].z_factor is None  # z_factor is a vapor-only field
    assert s.phases[0].viscosity is not None


def test_zero_fraction_component_dropped_then_mapped_back(thermo: Thermo) -> None:
    """A zero-fraction component never reaches thermo but maps back with 0.0."""
    z = {"H2O": 0.5, "MeOH": 0.5, "TEG": 0.0}
    s = thermo.flash_pt(z, _T, _P, 10.0)
    assert s.composition == z
    assert all(p.composition["TEG"] == 0.0 for p in s.phases)


def test_compressed_liquid_is_stability_resolved(thermo: Thermo) -> None:
    """A single-phase result is re-decided by the Michelsen-style stability test."""
    s = thermo.flash_pt({"H2O": 0.7, "MeOH": 0.3}, 300.0, _P, 10.0)
    assert s.vapor_fraction == pytest.approx(0.0)
    assert len(s.phases) == 1
    assert s.phases[0].kind == "aqueous"  # water fraction 0.7 > 0.5
    assert s.phases[0].density > 800.0  # kg/m3, water-rich liquid
    assert math.isclose(sum(p.mole_fraction for p in s.phases), 1.0, abs_tol=1e-9)


def test_ph_ps_roundtrip_and_material_balance(thermo: Thermo) -> None:
    """PH/PS return to the PT state, and the phase split preserves composition."""
    a = thermo.flash_pt(_Z, _T, _P, 10.0)
    assert math.isclose(thermo.flash_ph(_Z, _P, a.enthalpy, 10.0).T, a.T, abs_tol=0.05)
    assert math.isclose(thermo.flash_ps(_Z, _P, a.entropy, 10.0).T, a.T, abs_tol=0.05)

    assert math.isclose(sum(p.mole_fraction for p in a.phases), 1.0, abs_tol=1e-9)
    for c, zc in _Z.items():
        back = sum(p.mole_fraction * p.composition[c] for p in a.phases)
        assert math.isclose(back, zc, abs_tol=1e-6)
