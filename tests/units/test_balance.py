"""Balance-basis rules shared by the V0 harness and the property test (spec U-01, U-01b)."""

from __future__ import annotations

import pytest

from ngdesign.contracts.stream import StreamState
from ngdesign.data import component_record, register_pseudo
from ngdesign.units.balance import (
    SENSIBLE_ONLY_FLAG,
    BalanceBasisError,
    energy_basis,
    mass_and_atoms,
    species_without_formation,
    stream_enthalpy,
)

PSEUDO = "u01b_test_pseudo"
register_pseudo(PSEUDO, "U-01b balance-basis test lump", Tb=450.0, sg=0.78)


def _state(composition: dict[str, float], flow: float = 2.0, h: float = -100.0) -> StreamState:
    return StreamState(
        T=300.0,
        P=1.0e5,
        molar_flow=flow,
        composition=composition,
        vapor_fraction=1.0,
        enthalpy=h,
        entropy=0.0,
    )


def test_mass_and_atoms_counts_formula_species_and_pseudo_mass() -> None:
    """2 mol/s of CH4/pseudo 50/50: C 1, H 4 mol/s; mass from both MWs."""
    s = _state({"C1": 0.5, PSEUDO: 0.5})
    mass, atoms = mass_and_atoms([s])
    assert atoms == pytest.approx({"C": 1.0, "H": 4.0})
    expected = 1.0 * float(component_record("C1")["mw"]) + 1.0 * float(component_record(PSEUDO)["mw"])
    assert mass == pytest.approx(expected, rel=1e-15)


def test_species_without_formation_names_the_pseudo_only() -> None:
    assert species_without_formation([_state({"C1": 0.5, PSEUDO: 0.5})]) == [PSEUDO]
    assert species_without_formation([_state({"C1": 1.0, PSEUDO: 0.0})]) == []


def test_molar_rows_close_on_the_package_enthalpy() -> None:
    s = _state({"C1": 0.5, PSEUDO: 0.5})
    assert energy_basis("molar", [s], [s], {}) == "sensible"
    assert stream_enthalpy([s], "sensible") == pytest.approx(-200.0)


def test_reactive_rows_with_formation_data_close_on_formation_basis() -> None:
    s = _state({"C1": 0.5, "H2": 0.5})
    assert energy_basis("mass_elements", [s], [s], {}) == "formation"
    # the formation lift moves the stream enthalpy by n * sum(y * dHf)
    assert stream_enthalpy([s], "formation") != pytest.approx(stream_enthalpy([s], "sensible"))


def test_pseudo_needs_the_declared_flag() -> None:
    feed = _state({PSEUDO: 1.0})
    product = _state({"C1": 0.5, PSEUDO: 0.5})
    with pytest.raises(BalanceBasisError, match=PSEUDO):
        energy_basis("mass_elements", [feed], [product], {})
    with pytest.raises(BalanceBasisError, match=SENSIBLE_ONLY_FLAG):
        energy_basis("mass_elements", [feed], [product], {SENSIBLE_ONLY_FLAG: 0.0})
    assert energy_basis("mass_elements", [feed], [product], {SENSIBLE_ONLY_FLAG: 1.0}) == "sensible_declared"
