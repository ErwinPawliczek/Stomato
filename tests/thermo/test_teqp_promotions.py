"""T-18 promotion pins: one published (or CoolProp-generated) check value per row
promoted from experimental to provisional.

The four rows keep one pinned point each so a promotion cannot silently regress the
backend: the numbers below are the `expected` values of the bound validation cases
(data/validation/saft/cases-teqp.yaml), which carry their full citations. Deviating
properties stay assessed per case in data/thermo_models/saft.yaml — these pins guard
the flash path, not the parameter-fit quality.
"""

from __future__ import annotations

import pytest

from ngdesign.thermo import catalogue


def test_saft_vr_mie_pure_methane_95k() -> None:
    """Lafitte (2013) Table III parameter set on the harness's coldest CH4 psat point.

    The reference value is CoolProp-generated (the case's expected field); the model
    passes the case tolerances here, and its known rho_V/Cp drift at warmer points
    stays assessed in the row (saft.yaml).
    """
    pytest.importorskip("teqp")
    pkg = catalogue.build(catalogue.load_catalogue()["saft_vr_mie"])
    sp = pkg.bubble_point({"C1": 1.0}, T=95.3)
    assert sp.P == pytest.approx(20_516.96, rel=0.03)


def test_saft_vr_mie_pure_co2_216k() -> None:
    """The CO2 parameter row added in T-18 (Table III, p. 154504-25) at 216.7 K."""
    pytest.importorskip("teqp")
    pkg = catalogue.build(catalogue.load_catalogue()["saft_vr_mie"])
    sp = pkg.bubble_point({"CO2": 1.0}, T=216.7)
    assert sp.P == pytest.approx(520_401.26, rel=0.03)


def test_multifluid_c1co2_bubble_293k() -> None:
    """teqp multifluid (CoolProp library) on the Petropoulou C1/CO2 bubble point."""
    pytest.importorskip("teqp")
    pkg = catalogue.build(catalogue.load_catalogue()["multifluid"])
    sp = pkg.bubble_point({"C1": 0.01528, "CO2": 0.98472}, T=293.130)
    assert sp.P == pytest.approx(6_134_800.0, rel=0.02)


def test_multifluid_pure_co2_psat_216k() -> None:
    """teqp multifluid pure-fluid surface on CO2 at 216.7 K.

    The bridge's saturation scan loses the CO2 loop above ~250 K on this surface
    (measured in T-18; the 265/285/288.9 K cases are therefore unbound), so the pin
    sits at the coldest point where the scan is sound.
    """
    pytest.importorskip("teqp")
    pkg = catalogue.build(catalogue.load_catalogue()["multifluid_pure"])
    sp = pkg.bubble_point({"CO2": 1.0}, T=216.7)
    assert sp.P == pytest.approx(520_401.26, rel=0.02)


def test_gerg2008_teqp_c1n2_dew_134k() -> None:
    """Exact-backend GERG-2008 on the AGA8 distribution's 50/50 C1/N2 dew point.

    Check value from the NIST AGA8 supplementary tables (GERG-2008 column) — the
    open, public-domain source for the Kunz & Wagner (2012) formulation.
    """
    pytest.importorskip("teqp")
    pkg = catalogue.build(catalogue.load_catalogue()["gerg2008_teqp"])
    sp = pkg.dew_point({"C1": 0.5, "N2": 0.5}, T=134.02)
    assert sp.P == pytest.approx(953_319.19, rel=0.02)
