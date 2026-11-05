"""Gamma-phi adapter behaviour tests (T-03): azeotrope reproduction and refusals.

Spec note (documented deviation): the spec's required "NRTL/ideal reproduces
the methanol/water azeotrope" check is unsatisfiable — methanol/water is
zeotropic with no 1-atm azeotrope (Gmehling & Onken vol. 1 pt. 1 documents VLE,
not an azeotrope). This module instead pins the ethanol/water azeotrope on the
rows that reproduce it, cited to the Edinburgh Azeotrope Database.

Rows pinned here must reproduce 78.20 C at 101.325 kPa and an azeotropic
vapour (y == x within 0.01 mole fraction) at the literature composition
(4.40 wt% water). uniquac_ig is deliberately absent: at its ChemSep databank
parameters it reaches 351.97 K with y-EtOH 0.018 above the liquid — inside the
validation-case tolerances (0.5 % T, 0.02 x) but outside this stricter pin.
"""

from __future__ import annotations

import pytest

from ngdesign import registry

AZEOTROPE_T_K = 78.20 + 273.15  # Edinburgh Azeotrope Database, EtOH/H2O at 101.325 kPa
AZEOTROPE_X_WATER = 0.10532  # 4.40 wt% water converted to mole fraction
T_TOL_K = 0.5
X_TOL = 0.01


@pytest.mark.parametrize(
    "model_id",
    [
        "wilson_ig",
        "vanlaar_ig",
        "margules_ig",
        "unifac_ig",
        "unifac_dortmund_ig",
        "unifac_psrk_ig",
    ],
)
def test_reproduces_etoh_h2o_azeotrope(model_id: str) -> None:
    """At the literature azeotrope composition the row boils at 78.20 C with y == x."""
    pkg = registry.create("thermo", model_id)
    b = pkg.bubble_point({"EtOH": 1.0 - AZEOTROPE_X_WATER, "H2O": AZEOTROPE_X_WATER}, P=101325.0)
    assert float(b.T) == pytest.approx(AZEOTROPE_T_K, abs=T_TOL_K)
    y_water = float(b.incipient_composition["H2O"])
    assert y_water == pytest.approx(AZEOTROPE_X_WATER, abs=X_TOL)


def test_missing_parameters_error_names_the_pair() -> None:
    """A support without parameters refuses naming the pair — never ideal fallback."""
    pkg = registry.create("thermo", "vanlaar_ig")
    pair_pattern = r"MeOH \(67-56-1\) / H2O \(7732-18-5\)|H2O \(7732-18-5\) / MeOH \(67-56-1\)"
    with pytest.raises(ValueError, match=pair_pattern):
        pkg.bubble_point({"MeOH": 0.5, "H2O": 0.5}, P=101325.0)


# Regression (val-gphi-unifac, 2026-11-04): with a real vapour the liquid must carry the
# pure-component saturation fugacity coefficient (PhiSat basis), otherwise a near-pure feed
# bubbles far from the pure feed's Psat short-circuit (measured before the fix: n-butane with
# 1e-4 EtOH at 333.2 K on unifac_rk bubbled at 742 kPa vs Psat 639 kPa, +16 %).
REAL_VAPOUR_ROWS = ["unifac_rk", "unifac_pr", "nrtl_rk", "unifac_hoc", "unifac_nothnagel"]


@pytest.mark.parametrize("model_id", REAL_VAPOUR_ROWS)
def test_near_pure_bubble_matches_pure_psat(model_id: str) -> None:
    """A trace of a second component moves the bubble pressure continuously off the pure Psat."""
    pkg = registry.create("thermo", model_id)
    # The virial pairings stay at low pressure (their density-form vapour has no root above
    # -RT/(4B), which a near-pure n-butane bubble bracket would probe).
    low_p = model_id.startswith("nrtl") or model_id.endswith(("_hoc", "_nothnagel"))
    heavy, light, T = ("H2O", "MeOH", 330.0) if low_p else ("EtOH", "nC4", 300.0)
    p_pure = float(pkg.bubble_point({light: 1.0}, T=T).P)
    p_trace = float(pkg.bubble_point({light: 1.0 - 1e-6, heavy: 1e-6}, T=T).P)
    assert p_trace == pytest.approx(p_pure, rel=1e-3)


@pytest.mark.parametrize("model_id", ["unifac_rk", "unifac_pr"])
def test_real_vapour_bubble_close_to_ideal_pairing_at_moderate_pressure(model_id: str) -> None:
    """At 0.6 MPa the cubic-vapour pairing stays within a few % of the ideal-gas one.

    phi_V and phi_sat largely cancel for a nearly ideal vapour mixture; without
    phi_sat the RK/PR pairing sat 16 % above the ideal-gas pairing here.
    """
    z = {"EtOH": 0.2452, "nC4": 0.7548}
    p_ig = float(registry.create("thermo", "unifac_ig").bubble_point(z, T=333.2).P)
    p_real = float(registry.create("thermo", model_id).bubble_point(z, T=333.2).P)
    assert p_real == pytest.approx(p_ig, rel=0.03)
