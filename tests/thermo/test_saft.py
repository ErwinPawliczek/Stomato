"""teqp bridge tests (spec T-07): registration, construction contract, named spot checks.

Environment-independent tests (registration, the no-teqp refusal) run everywhere; the
construction-contract and numerical spot checks importorskip teqp and reference CoolProp
HEOS in-process (the same NIST-aligned reference the validation cases use).
"""

from __future__ import annotations

import sys

import pytest

from ngdesign.thermo import catalogue
from ngdesign.thermo.teqp_bridge import SaftDependencyMissing

SAFT_IDS = (
    "cpa_pr",
    "cpa_srk",
    "gerg2008_teqp",
    "multifluid",
    "multifluid_pure",
    "pc_saft",
    "pc_saft_assoc",
    "pc_saft_polar",
    "saft_vr_mie",
    "soft_saft",
)
# Rows teqp 0.23.2 cannot serve; each refuses to build with the engine named (spec
# requirement). Their l0 declarations are empty and the refusal reason is recorded in
# the row's l0_excluded.
REFUSING_IDS = ("pc_saft_assoc", "pc_saft_polar", "soft_saft")
BUILDABLE_IDS = (
    "cpa_pr",
    "cpa_srk",
    "gerg2008_teqp",
    "multifluid",
    "multifluid_pure",
    "pc_saft",
    "saft_vr_mie",
)


def test_saft_rows_register_with_status() -> None:
    """The ten saft rows load with the real catalogue. T-15c promoted pc_saft and
    cpa_srk to provisional (all bound cases measured, every miss assessed per case);
    T-17 promoted cpa_pr the same way (Sorensen 2018 parameters); the remaining rows
    stay experimental (T-07)."""
    rows = catalogue.load_catalogue()
    for rid in ("pc_saft", "cpa_srk", "cpa_pr"):
        assert rows[rid].status == "provisional", f"{rid}: row must stay provisional"
    for rid in SAFT_IDS:
        if rid in ("pc_saft", "cpa_srk", "cpa_pr"):
            continue
        assert rows[rid].status == "experimental", f"{rid}: row must stay experimental"


def test_saft_packages_require_the_extra_at_first_use(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without teqp the rows load AND construct; the first property call refuses, naming the extra.

    Construction never touches the optional backend (the CoolProp and virial rows set the
    pattern, and the thermo-protocol contract test instantiates every registered row), so
    the failure surfaces as SaftDependencyMissing on the first call, never as an ImportError
    leaking out of the package.
    """
    monkeypatch.setitem(sys.modules, "teqp", None)
    from ngdesign import registry

    pkg = registry.create("thermo", "pc_saft")
    with pytest.raises(SaftDependencyMissing, match="optional extra"):
        pkg.pure_psat("C1", 150.0)


def test_refusing_rows_raise_at_first_use_naming_the_engine() -> None:
    """Rows teqp cannot serve construct, then refuse at the first call with the engine named."""
    from ngdesign import registry

    for rid in REFUSING_IDS:
        pkg = registry.create("thermo", rid)
        with pytest.raises(NotImplementedError, match="teqp"):
            pkg.pure_psat("H2O", 373.15)


class TestConstructionContract:
    """Construction behaviour with the optional backend installed."""

    def test_buildable_rows_create_through_registry(self) -> None:
        pytest.importorskip("teqp")
        from ngdesign import registry
        from ngdesign.thermo.teqp_bridge import (
            CpaPrThermo,
            CpaSrkThermo,
            Gerg2008TeqpThermo,
            MultifluidPureThermo,
            MultifluidThermo,
            PCSaftThermo,
            SaftVrMieThermo,
        )

        expected = {
            "pc_saft": PCSaftThermo,
            "saft_vr_mie": SaftVrMieThermo,
            "cpa_srk": CpaSrkThermo,
            "cpa_pr": CpaPrThermo,
            "multifluid": MultifluidThermo,
            "multifluid_pure": MultifluidPureThermo,
            "gerg2008_teqp": Gerg2008TeqpThermo,
        }
        for rid, cls in expected.items():
            assert type(registry.create("thermo", rid)) is cls, rid


class TestNamedSpotChecks:
    """The spec's named numbers; CoolProp HEOS as the in-process NIST-aligned reference."""

    def test_pc_saft_methane_psat_and_liquid_density_150k(self) -> None:
        pytest.importorskip("teqp")
        import CoolProp.CoolProp as CP

        pkg = catalogue.build(catalogue.load_catalogue()["pc_saft"])
        sp = pkg.bubble_point({"C1": 1.0}, T=150.0)
        ref_p = CP.PropsSI("P", "T", 150.0, "Q", 0, "Methane")
        assert sp.P == pytest.approx(ref_p, rel=0.02), "spec: Psat within 2 % of NIST"
        st = pkg.flash_pt({"C1": 1.0}, 150.0, sp.P, 1.0)
        rho_l = max(phase.density for phase in st.phases)
        ref_rho = CP.PropsSI("D", "T", 150.0, "Q", 0, "Methane")
        assert rho_l == pytest.approx(ref_rho, rel=0.02), "spec: liquid density within 2 % of NIST"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "spec T-07 names 1 %; the published Kontogeorgis et al. water 4C set measures "
            "-1.15 % against IAPWS-95 (reported on the PR and issue #140; the band is not widened)"
        ),
    )
    def test_cpa_srk_water_psat_373k(self) -> None:
        pytest.importorskip("teqp")
        pkg = catalogue.build(catalogue.load_catalogue()["cpa_srk"])
        sp = pkg.bubble_point({"H2O": 1.0}, T=373.15)
        assert sp.P == pytest.approx(101_417.997, rel=0.01)

    def test_cpa_srk_water_psat_373k_measured_capability(self) -> None:
        """Regression pin at the measured -1.15 %: a drift past 2 % is a defect."""
        pytest.importorskip("teqp")
        pkg = catalogue.build(catalogue.load_catalogue()["cpa_srk"])
        sp = pkg.bubble_point({"H2O": 1.0}, T=373.15)
        assert sp.P == pytest.approx(101_417.997, rel=0.02)

    def test_cpa_pr_water_and_methanol_psat(self) -> None:
        """CPA-PR (T-17): the Sorensen et al. (2018) Table 6 set measures -0.9 % on
        water Psat at 373.15 K and -0.8 % on methanol at its normal boiling point
        against CoolProp HEOS/IAPWS — the PR variant beats the SRK variant's -1.15 %
        water miss. The 2 % band guards the kernel against drift; the parameters are
        pinned by data/thermo_params/saft/pure.yaml."""
        pytest.importorskip("teqp")
        pkg = catalogue.build(catalogue.load_catalogue()["cpa_pr"])
        water = pkg.bubble_point({"H2O": 1.0}, T=373.15)
        assert water.P == pytest.approx(101_417.997, rel=0.02)
        methanol = pkg.bubble_point({"MeOH": 1.0}, T=337.65)
        assert methanol.P == pytest.approx(101_325.0, rel=0.02)

    def test_pc_saft_c1co2_bubble_293k(self) -> None:
        pytest.importorskip("teqp")
        pkg = catalogue.build(catalogue.load_catalogue()["pc_saft"])
        # Spec names 230 K; the cited published source (Petropoulou et al. 2018,
        # Fluid Phase Equilib. 462, 44-58, via NIST ThermoML) covers 293.13-303.14 K
        # isotherms, so the named check is anchored at the cited 293.13 K bubble point
        # (documented deviation in the PR body; 5 % tolerance per the spec).
        sp = pkg.bubble_point({"C1": 0.01528, "CO2": 0.98472}, T=293.130)
        assert sp.P == pytest.approx(6_134_800.0, rel=0.05)

    def test_gerg2008_teqp_c1n2_bubble_130k(self) -> None:
        """The exact-GERG backend on the rebound T-04 cross-check case (issue #164).

        Literature: 613.7 kPa (Janisch et al. 2007). The Kunz-Wagner (2012) parameter
        set measures -5.77 % there — the same value CoolProp's HEOS gives, so the pin
        guards the flash against drift while the parameter miss stays assessed in the
        row's assessed map (data/thermo_models/saft.yaml), never hidden by a band.
        """
        pytest.importorskip("teqp")
        import CoolProp.CoolProp as CP

        pkg = catalogue.build(catalogue.load_catalogue()["gerg2008_teqp"])
        sp = pkg.bubble_point({"C1": 0.9539, "N2": 0.0461}, T=130.079)
        assert sp.P == pytest.approx(578_280.0, rel=0.02)
        # Backend agreement: the teqp path must keep matching CoolProp HEOS.
        ref_p = CP.PropsSI("P", "T", 130.079, "Q", 0, "HEOS::Methane[0.9539]&Nitrogen[0.0461]")
        assert sp.P == pytest.approx(ref_p, rel=0.01)
