"""Regression tests for the teqp bridge's saturation machinery (val-saft, 2026-11-04).

Each test pins one root-cause fix with the measured before/after numbers:

* bubble/dew K-sum: the incipient phase is converged before the K-sum classifies a
  trial pressure (a half-converged composition put a bracket end on the wrong side);
* Wilson K-values use (1 - Tc/T) (the reciprocal argument crashed every isobaric
  bubble-T solve of MeOH/H2O on the 101.325 kPa isobar);
* gerg2008_teqp runs teqp's exact GERG-2008 kind, not the CoolProp fluid library;
* the multi-fluid root scan resolves the dense range and pure Psat comes from teqp's
  Newton pure-VLE solve (the reference EOS's in-dome oscillations fooled the hunt);
* near-critical incipient vapour (Z < 0.5) still votes in the bubble K-sum.
"""

from __future__ import annotations

import numpy as np
import pytest

from ngdesign.contracts.thermo import SaturationError
from ngdesign.thermo import catalogue

pytest.importorskip("teqp")


def _pkg(row: str) -> object:
    return catalogue.build(catalogue.load_catalogue()[row])


def test_dew_point_converges_incipient_liquid_before_bracketing() -> None:
    """GERG-2008 50/50 C1/N2 dew at 153.41 K: AGA8 check value 2658444 Pa.

    Before the fix the bracket closed on 2799037 Pa (+5.3 %); the converged K-sum
    crosses 1 at the check value (the residual 2e-4 is the check table's 0.01 K
    rounding of T on a ~80 kPa/K dew line).
    """
    sp = _pkg("gerg2008_teqp").dew_point({"C1": 0.5, "N2": 0.5}, T=153.41)  # type: ignore[attr-defined]
    assert sp.P == pytest.approx(2_658_444.0, rel=5e-4)
    assert sp.incipient_composition["C1"] > 0.75  # methane-rich incipient liquid


def test_gerg2008_teqp_is_the_exact_gerg_formulation() -> None:
    """p(T, rho, z) of the row's kernel reproduces the AGA8 GERG-2008 check value.

    NIST AGA8 distribution test data (50/50 C1/N2, 134.02 K, 1.0 mol/l: 953319.19 Pa);
    the CoolProp-library multi-fluid build the row used before gives a different
    residual Helmholtz energy at the same state.
    """
    from ngdesign.thermo.teqp_bridge import _build_kernel

    kernel = _build_kernel("gerg2008_teqp", ("C1", "N2"))
    p = kernel.pressure(134.02, 1000.0, np.array([0.5, 0.5]))
    assert p == pytest.approx(953_319.19, rel=1e-5)


def test_wilson_k_matches_wilson_bubble_pressure() -> None:
    """sum z_i K_i = 1 at the Wilson bubble pressure: both use (1 - Tc/T)."""
    pkg = _pkg("cpa_srk")
    z = {"MeOH": 0.238, "H2O": 0.762}
    ids = ("H2O", "MeOH")
    p = pkg._wilson_p(z, ids, 353.25, bubble=True)  # type: ignore[attr-defined]
    k = pkg._wilson_k(z, ids, 353.25, p)  # type: ignore[attr-defined]
    assert float(np.dot(k, [0.762, 0.238])) == pytest.approx(1.0, rel=1e-12)


def test_isobaric_bubble_t_meoh_water_no_longer_crashes() -> None:
    """CPA-SRK MeOH/H2O bubble T at 101.325 kPa (Gao 2012: 353.25 K for x = 0.238).

    The inverted Wilson argument seeded the solve at 179.68 K and raised
    SaturationError; measured after the fix: 351.12 K (-0.6 %).
    """
    sp = _pkg("cpa_srk").bubble_point({"MeOH": 0.238, "H2O": 0.762}, P=101_325.0)  # type: ignore[attr-defined]
    assert sp.T == pytest.approx(351.12, abs=0.2)


@pytest.mark.parametrize(
    ("row", "T", "ref"), [("multifluid_pure", 285.0, 4_712_303.46), ("gerg2008_teqp", 300.0, 6_713_078.06)]
)
def test_pure_co2_psat_near_critical(row: str, T: float, ref: float) -> None:
    """Near-critical CO2 Psat (reference: CoolProp Span-Wagner).

    Before: multifluid_pure returned 196479 Pa at 285 K (and "at/above Tc" at 265 K);
    gerg2008_teqp returned 6.4975 MPa at 300 K. GERG-2008's own CO2 equation differs
    from Span-Wagner by < 2e-4 here.
    """
    sp = _pkg(row).bubble_point({"CO2": 1.0}, T=T)  # type: ignore[attr-defined]
    assert sp.P == pytest.approx(ref, rel=5e-4)


def test_pure_psat_refused_above_model_critical_temperature() -> None:
    """305 K is above CO2's Tc (304.13 K): no vapour pressure (the hunt used to invent one)."""
    with pytest.raises(SaturationError):
        _pkg("multifluid_pure").bubble_point({"CO2": 1.0}, T=305.0)  # type: ignore[attr-defined]


def test_multifluid_root_scan_finds_the_liquid_branch() -> None:
    """Span-Wagner CO2 at 250 K, 5 MPa: one compressed-liquid root (~24 mol/l).

    The scan iterated only the first 70 of its grid points, and with them alone the
    liquid crossing hid inside a 40 %-wide cell.
    """
    from ngdesign.thermo.teqp_bridge import _build_kernel

    kernel = _build_kernel("multifluid_pure", ("CO2",))
    roots = kernel.roots(250.0, 5.0e6, np.array([1.0]))
    assert roots
    assert 23_000.0 < roots[-1] < 26_000.0


def test_near_critical_incipient_vapour_votes() -> None:
    """SAFT-VR-Mie C1/CO2 bubble at 298.142 K (Petropoulou 2018: 6.9755 MPa).

    The incipient vapour sits at Z ~ 0.49 against a liquid 2.9x denser; the Z > 0.5
    bar rejected it and the solve raised. Measured after the fix: 7.0008 MPa.
    """
    sp = _pkg("saft_vr_mie").bubble_point({"C1": 0.02145, "CO2": 0.97855}, T=298.142)  # type: ignore[attr-defined]
    assert sp.P == pytest.approx(7.0008e6, rel=1e-3)
