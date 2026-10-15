"""Tests for the electrolyte-NRTL module (opt-in CO2-only chemistry).

The module's validity band and parameter provenance live in its docstring;
these tests pin the invariants (mass balance, electroneutrality, inverse
consistency, determinism, evidence-based rejection of unsupported service)
and one inter-model agreement band against the Kent-Eisenberg module that
the repo validated against NeqSim (PRs #59/#60/#65).

Literature-point goldens for the Zhang-Chen (MDEA) and Zhang-Que-Chen
(MEA) published CO2 solubility data are NOT included: the parameter tables
were extracted from the open OSTI 1963954 report (its own symmetric
formulation), not from the two pinned papers, whose row-level VLE data
could not be retrieved in this session. The honest validation anchors are
the in-repo KE cross-check below plus the invariant suite.
"""

from __future__ import annotations

import pytest

from ngdesign.amine import enrtl
from ngdesign.units.mdea_equilibrium import (
    equilibrium_partial_pressures as ke_pressures,
)

# The KE-validated MDEA anchor state (PR #60 golden family): ~46 wt% MDEA
# at absorber conditions.
_T = 313.15
_MOLARITY = 5270.0
_LOADING = 0.1


def test_h2s_service_is_rejected_with_evidence() -> None:
    """No citable e-NRTL parameter set covers H2S amine chemistry."""
    with pytest.raises(ValueError, match="H2S|electrolyte-NRTL") as exc:
        enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.001, "MDEA")
    assert "kent_eisenberg" in str(exc.value)
    with pytest.raises(ValueError, match="H2S|electrolyte-NRTL"):
        enrtl.equilibrium_loadings(_T, _MOLARITY, 1000.0, 50.0, "MDEA")


def test_dea_is_rejected_as_outside_the_published_sets() -> None:
    with pytest.raises(ValueError, match="DEA|supported"):
        enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.0, "DEA")


def test_unknown_amine_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported amine"):
        enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.0, "PIPPAZINE")


def test_window_is_enforced() -> None:
    with pytest.raises(ValueError, match="temperature"):
        enrtl.equilibrium_partial_pressures(280.0, _MOLARITY, _LOADING, 0.0, "MDEA")
    with pytest.raises(ValueError, match="molarity"):
        enrtl.equilibrium_partial_pressures(_T, 0.0, _LOADING, 0.0, "MDEA")
    with pytest.raises(ValueError, match="loading"):
        enrtl.equilibrium_partial_pressures(_T, _MOLARITY, 1.6, 0.0, "MDEA")


def test_speciation_satisfies_carbon_and_charge_balances() -> None:
    """At fixed total loading the speciated carbon must equal CO2 fed in."""
    spec = enrtl._solve_speciation(
        _T,
        _MOLARITY / 1000.0,
        _LOADING,
        1.0,  # kg water per litre at the apparent-basis boundary
        enrtl.MDEA_CHEMISTRY,
    )
    carbon = spec.co2_free + spec.hco3 + spec.co3 + spec.carbamate
    # Every absorbed mol of CO2 is bound to one N (carbamate/protonated
    # amine bookkeeping keeps the amine balance) or dissolved as free CO2,
    # bicarbonate, or carbonate; the loading fixes carbon per amine.
    assert carbon / (spec.amine + spec.amineh) == pytest.approx(_LOADING, rel=1e-6)
    # Electroneutrality: h + amineh = oh + hco3 + 2 co3.
    cations = spec.h + spec.amineh
    anions = spec.oh + spec.hco3 + 2.0 * spec.co3
    assert cations == pytest.approx(anions, rel=1e-6)


def test_pressures_and_loadings_are_inverse_at_the_anchor() -> None:
    p_co2, _ = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.0, "MDEA")
    back, _ = enrtl.equilibrium_loadings(_T, _MOLARITY, p_co2, 0.0, "MDEA")
    assert back == pytest.approx(_LOADING, rel=1e-4)


def test_determinism_double_run_is_byte_identical() -> None:
    first = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.0, "MDEA")
    second = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, _LOADING, 0.0, "MDEA")
    assert first == second


def test_isotherm_is_monotonic_in_loading() -> None:
    low = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, 0.05, 0.0, "MDEA")[0]
    mid = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, 0.20, 0.0, "MDEA")[0]
    high = enrtl.equilibrium_partial_pressures(_T, _MOLARITY, 0.35, 0.0, "MDEA")[0]
    assert 0.0 < low < mid < high


@pytest.mark.parametrize("amine", ["MDEA", "MEA"])
def test_enrtl_agrees_with_ke_within_a_factor_band(amine: str) -> None:
    """Inter-model consistency at the low-loading anchor (not a golden).

    e-NRTL and Kent-Eisenberg are independent chemistry models; the repo's
    citable anchor for KE is its NeqSim/Jou regression (PRs #59/#60/#65).
    The two models should agree within a factor of 2 at the anchor state;
    grosser disagreement indicates a basis or convention error.
    """
    molarity = _MOLARITY if amine == "MDEA" else 5150.0
    enrtl_p = enrtl.equilibrium_partial_pressures(_T, molarity, _LOADING, 0.0, amine)[0]
    ke_p = ke_pressures(_T, molarity, _LOADING, 0.0, amine)[0]
    assert 0.5 < enrtl_p / ke_p < 2.0, f"{amine}: enrtl={enrtl_p} ke={ke_p}"
