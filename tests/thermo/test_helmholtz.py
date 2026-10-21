"""Helmholtz-family adapter checks the T-04 spec names (added in review of PR #152).

Reference values:
- IAPWS-95 (Wagner & Pruss, J. Phys. Chem. Ref. Data 31, 387, 2002): saturation
  pressure at 373.15 K = 101.418 kPa; liquid density at 300 K / 0.1 MPa =
  996.556 kg/m3.
- IAPWS-IF97 (IAPWS R7-97(2012)) agrees with IAPWS-95 to better than 1e-3 in
  these quantities by construction.
- Methane density at 300 K / 10 MPa = 75.18 kg/m3 (NIST Webbook, Setzmann &
  Wagner reference EOS, J. Phys. Chem. Ref. Data 20, 1061, 1991).
- CoolProp is the harness's own reference backend, so the CoolProp rows must
  reproduce PropsSI exactly (same library, same state).
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind
from ngdesign.thermo.helmholtz import coolprop_available

pytestmark = pytest.mark.skipif(not coolprop_available(), reason="CoolProp not installed")

_WATER = {"H2O": 1.0}
_C1 = {"C1": 1.0}


def test_iapws95_matches_the_iapws_tables() -> None:
    pkg = registry.create("thermo", "iapws95")
    assert pkg.pure_psat("H2O", 373.15) == pytest.approx(101418.0, rel=1e-4)
    rho = pkg.phase_props(_WATER, 300.0, 1e5, PhaseKind.AQUEOUS).density
    assert rho == pytest.approx(996.556, rel=1e-4)


def test_if97_agrees_with_iapws95() -> None:
    full = registry.create("thermo", "iapws95")
    industrial = registry.create("thermo", "iapws_if97")
    assert industrial.pure_psat("H2O", 373.15) == pytest.approx(full.pure_psat("H2O", 373.15), rel=1e-3)
    rho_full = full.phase_props(_WATER, 300.0, 1e5, PhaseKind.AQUEOUS).density
    rho_ind = industrial.phase_props(_WATER, 300.0, 1e5, PhaseKind.AQUEOUS).density
    assert rho_ind == pytest.approx(rho_full, rel=1e-3)


def test_coolprop_rows_reproduce_propssi_exactly() -> None:
    import CoolProp.CoolProp as CP

    heos = registry.create("thermo", "coolprop_heos")
    assert heos.pure_psat("C1", 150.0) == CP.PropsSI("P", "T", 150.0, "Q", 0, "Methane")
    rho = heos.phase_props(_C1, 300.0, 1e7, PhaseKind.VAPOR).density
    assert rho == CP.PropsSI("D", "T", 300.0, "P", 1e7, "Methane")


def test_bwrs_methane_density_within_one_percent_of_nist() -> None:
    pkg = registry.create("thermo", "bwrs")
    rho = pkg.phase_props(_C1, 300.0, 1e7, PhaseKind.VAPOR).density
    # measured on this branch: 75.64 kg/m3 (+0.62 %)
    assert rho == pytest.approx(75.18, rel=1e-2)


def test_gerg_row_is_the_coolprop_multifluid_model() -> None:
    """The gerg2008 row evaluates through CoolProp's multifluid HEOS path (the row says so);
    until the teqp bridge (T-07) lands it must agree with coolprop_heos exactly."""
    z = {"C1": 0.90, "C2": 0.05, "C3": 0.02, "N2": 0.02, "CO2": 0.01}
    gerg = registry.create("thermo", "gerg2008")
    heos = registry.create("thermo", "coolprop_heos")
    assert gerg.phase_props(z, 300.0, 1e7, PhaseKind.VAPOR).density == pytest.approx(
        heos.phase_props(z, 300.0, 1e7, PhaseKind.VAPOR).density, rel=1e-12
    )
