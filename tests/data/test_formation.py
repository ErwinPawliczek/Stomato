"""Spec U-R acceptance: databank-backed standard formation properties."""

from __future__ import annotations

import pytest

from ngdesign.data.formation import (
    MissingFormationData,
    formation_enthalpy,
    formation_gibbs,
    is_element,
)


def test_methane_formation_enthalpy_matches_janaf() -> None:
    # JANAF ΔfH°298(CH4, g) = -74.6 kJ/mol; the databank ships the same tables.
    assert formation_enthalpy("CH4", 298.15) == pytest.approx(-74_600.0, rel=0.01)


def test_methane_formation_gibbs_matches_janaf() -> None:
    # JANAF ΔfG°298(CH4, g) = -50.5 kJ/mol.
    assert formation_gibbs("CH4", 298.15) == pytest.approx(-50_500.0, rel=0.02)


def test_water_vapour_formation_enthalpy_matches_janaf() -> None:
    # JANAF ΔfH°298(H2O, g) = -241.8 kJ/mol (gas-phase standard state).
    assert formation_enthalpy("H2O", 298.15) == pytest.approx(-241_800.0, rel=0.01)


def test_elements_have_exactly_zero_formation_properties() -> None:
    for cid in ("N2", "O2", "H2"):
        assert is_element(cid)
        assert formation_enthalpy(cid, 298.15) == 0.0
        assert formation_gibbs(cid, 600.0) == 0.0


def test_formation_gibbs_temperature_trend_exothermic_formation() -> None:
    # CO2 formation gets more favourable (more negative ΔfG) as T rises past
    # the reference: ΔS°f < 0 makes −T·ΔS°f grow in magnitude.
    g298 = formation_gibbs("CO2", 298.15)
    g800 = formation_gibbs("CO2", 800.0)
    assert g800 < g298


def test_missing_formation_data_names_the_component() -> None:
    with pytest.raises(MissingFormationData, match="no-such-component"):
        formation_enthalpy("no-such-component", 298.15)


def test_formation_data_come_from_the_cited_database() -> None:
    from ngdesign.data import chemdb
    from ngdesign.data.formation import formation_enthalpy_298, standard_entropy_298

    assert formation_enthalpy_298("CH4") == chemdb.value("methane", "Hf_gas").value
    assert standard_entropy_298("CO2") == chemdb.value("CO2", "S0_gas").value


def test_nothing_is_estimated_for_a_species_without_a_gas_model() -> None:
    with pytest.raises(MissingFormationData):
        formation_enthalpy("sodium chloride dihydrate", 298.15)


def test_formation_enthalpy_needs_no_heat_capacity_model() -> None:
    """Regression: n-C24 states ΔfH° but has no Cp(T); only T-dependent calls need one."""
    from ngdesign.data import chemdb
    from ngdesign.data.formation import formation_enthalpy_298

    assert formation_enthalpy_298("nC24") == chemdb.value("nC24", "Hf_gas").value
    with pytest.raises(MissingFormationData):
        formation_enthalpy("nC24", 600.0)
