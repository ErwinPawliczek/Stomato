"""Formula parsing: nesting, hydrates, charges and phases."""

from __future__ import annotations

import pytest

from ngdesign.chem.formula import FormulaError, parse_formula


@pytest.mark.parametrize(
    ("token", "atoms"),
    [
        ("H2O", {"H": 2, "O": 1}),
        ("Ca(OH)2", {"Ca": 1, "O": 2, "H": 2}),
        ("Fe2(SO4)3", {"Fe": 2, "S": 3, "O": 12}),
        ("K4[Fe(CN)6]", {"K": 4, "Fe": 1, "C": 6, "N": 6}),
        ("(NH4)2SO4", {"N": 2, "H": 8, "S": 1, "O": 4}),
        ("CH3COOH", {"C": 2, "H": 4, "O": 2}),
        ("CuSO4·5H2O", {"Cu": 1, "S": 1, "O": 9, "H": 10}),
        ("CuSO4.5H2O", {"Cu": 1, "S": 1, "O": 9, "H": 10}),
    ],
)
def test_atoms(token: str, atoms: dict[str, int]) -> None:
    assert parse_formula(token).composition == atoms


@pytest.mark.parametrize(
    ("token", "charge"),
    [
        ("Na+", 1),
        ("Cl-", -1),
        ("Fe+3", 3),
        ("SO4-2", -2),
        ("SO4^2-", -2),
        ("SO4--", -2),
        ("NH4+", 1),
        ("H2O", 0),
        ("e-", -1),
    ],
)
def test_charge(token: str, charge: int) -> None:
    assert parse_formula(token).charge == charge


@pytest.mark.parametrize(
    ("token", "phase"),
    [("H2O(l)", "liquid"), ("CO2(g)", "gas"), ("C(s)", "solid"), ("C(cr)", "solid"), ("NaCl(aq)", "aqueous")],
)
def test_phase_suffix(token: str, phase: str) -> None:
    assert parse_formula(token).phase == phase


def test_electron_has_no_atoms_and_no_mass() -> None:
    electron = parse_formula("e-")
    assert electron.composition == {}
    assert electron.molar_mass == 0.0


def test_hill_order_and_molar_mass() -> None:
    assert parse_formula("C2H5OH").hill == "C2H6O"
    assert parse_formula("NH3").hill == "H3N"
    # the same formula written two ways weighs the same
    assert parse_formula("CH3COOH").molar_mass == pytest.approx(parse_formula("C2H4O2").molar_mass)


@pytest.mark.parametrize("bad", ["", "water", "h2o", "123", "Xx2", "()"])
def test_not_a_formula(bad: str) -> None:
    with pytest.raises(FormulaError):
        parse_formula(bad)


@pytest.mark.parametrize(
    ("token", "atoms", "charge"),
    [
        ("Fe3+", {"Fe": 1}, 3),
        ("Cu2+", {"Cu": 1}, 2),
        ("[Fe(CN)6]3-", {"Fe": 1, "C": 6, "N": 6}, -3),
        ("NH4+", {"N": 1, "H": 4}, 1),
        ("NO3-", {"N": 1, "O": 3}, -1),
        ("MnO4-", {"Mn": 1, "O": 4}, -1),
    ],
)
def test_a_digit_before_a_sign_is_read_by_context(token: str, atoms: dict[str, int], charge: int) -> None:
    parsed = parse_formula(token)
    assert parsed.composition == atoms
    assert parsed.charge == charge


@pytest.mark.parametrize("bad", ["SO42-", "O2-", "H2+", "Fe0.95O", "CaSO4.0.5H2O"])
def test_what_cannot_be_read_safely_is_refused(bad: str) -> None:
    with pytest.raises(FormulaError):
        parse_formula(bad)
