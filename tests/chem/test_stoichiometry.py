"""Balancing, reaction spaces and yield accounting."""

from __future__ import annotations

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ngdesign.chem.stoichiometry import (
    EquationSyntaxError,
    IndeterminateBalanceError,
    NoBalanceError,
    StoichiometryError,
    atom_economy,
    balance,
    limiting_reagent,
    parse_equation,
    percent_yield,
    reaction_space,
    reactor_performance,
    theoretical_yield,
    to_reaction,
)
from ngdesign.contracts.reactions import ElementBalanceError, Reaction


@pytest.mark.parametrize(
    ("equation", "expected"),
    [
        ("H2 + O2 -> H2O", "2 H2 + O2 -> 2 H2O"),
        ("C3H8 + O2 -> CO2 + H2O", "C3H8 + 5 O2 -> 3 CO2 + 4 H2O"),
        ("N2 + H2 = NH3", "N2 + 3 H2 -> 2 NH3"),
        ("CH4 + H2O <=> CO + H2", "CH4 + H2O <=> CO + 3 H2"),
        ("KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2", "2 KMnO4 + 16 HCl -> 2 KCl + 2 MnCl2 + 8 H2O + 5 Cl2"),
        ("Fe2(SO4)3 + Ca(OH)2 -> Fe(OH)3 + CaSO4", "Fe2(SO4)3 + 3 Ca(OH)2 -> 2 Fe(OH)3 + 3 CaSO4"),
        ("C6H12O6 -> C2H5OH + CO2", "C6H12O6 -> 2 C2H5OH + 2 CO2"),
        ("MnO4- + Fe+2 + H+ -> Mn+2 + Fe+3 + H2O", "MnO4- + 5 Fe+2 + 8 H+ -> Mn+2 + 5 Fe+3 + 4 H2O"),
        ("Cr2O7^2- + H+ + e- -> Cr+3 + H2O", "Cr2O7^2- + 14 H+ + 6 e- -> 2 Cr+3 + 7 H2O"),
        ("H2+O2->H2O", "2 H2 + O2 -> 2 H2O"),
        ("H2O(l) -> H2O(g)", "H2O(l) -> H2O(g)"),
    ],
)
def test_balance(equation: str, expected: str) -> None:
    assert str(balance(equation)) == expected


def test_large_redox_is_exact() -> None:
    balanced = balance("K4Fe(CN)6 + KMnO4 + H2SO4 -> KHSO4 + Fe2(SO4)3 + MnSO4 + HNO3 + CO2 + H2O")
    assert balanced.is_balanced
    assert [abs(c) for c in balanced.coefficients] == [10, 122, 299, 162, 5, 122, 60, 60, 188]


def test_names_resolve_through_the_database() -> None:
    balanced = balance("n-butane + oxygen -> carbon dioxide + water")
    assert sorted(abs(c) for c in balanced.coefficients) == [2, 8, 10, 13]


def test_given_coefficients_are_kept_by_the_parser() -> None:
    parsed = parse_equation("2 H2 + O2 -> 2 H2O")
    assert parsed.is_balanced
    unbalanced = parse_equation("H2 + O2 -> H2O")
    assert unbalanced.imbalance() == {"O": Fraction(-1)}


def test_fractional_coefficients_parse() -> None:
    assert parse_equation("CO + 1/2 O2 -> CO2").is_balanced
    assert parse_equation("H2 + 0.5 O2 -> H2O").is_balanced


def test_a_catalyst_on_both_sides_nets_out_but_stays_a_term() -> None:
    parsed = parse_equation("O3 + NO -> O2 + NO2")
    assert parsed.is_balanced
    catalysed = parse_equation("CH3CHO + I2 -> CH4 + CO + I2")
    assert catalysed.is_balanced
    assert "I2" not in {k for k, v in catalysed.nu.items() if v != 0.0}
    assert len(catalysed.terms) == 5


def test_no_balance_exists() -> None:
    with pytest.raises(NoBalanceError):
        balance("H2 -> O2")


def test_term_on_the_wrong_side_is_named() -> None:
    with pytest.raises(NoBalanceError, match="other side"):
        balance("H2O + O2 -> H2")


def test_term_that_cannot_participate_is_named() -> None:
    with pytest.raises(NoBalanceError, match="Ar"):
        balance("H2 + O2 + Ar -> H2O")


def test_indeterminate_balance_is_refused_not_guessed() -> None:
    # CO and CO2 both from C + O2: the ratio is free, so no single balance exists.
    with pytest.raises(IndeterminateBalanceError):
        balance("C + O2 -> CO + CO2")


@pytest.mark.parametrize(
    "bad", ["H2 O2", "-> H2O", "H2 ->", "H2 -> O2 -> H2O", "H2 + H2 -> H4", "Zzz + O2 -> CO2"]
)
def test_equation_syntax_is_refused(bad: str) -> None:
    with pytest.raises(EquationSyntaxError):
        parse_equation(bad)


def test_reaction_space_of_steam_reforming() -> None:
    # C = 5 species, rank 3 (C, H, O): two independent reactions (classic reforming + WGS).
    space = reaction_space(["CH4", "H2O", "CO", "CO2", "H2"])
    assert space.rank == 3
    assert space.n_independent == 2
    assert all(eq.is_balanced for eq in space.reactions)


def test_reaction_space_with_no_reaction() -> None:
    assert reaction_space(["N2", "CH4"]).n_independent == 0


@given(st.integers(1, 12), st.integers(0, 2))
def test_alkane_and_alcohol_combustion_always_balances(carbons: int, oxygens: int) -> None:
    fuel = f"C{carbons}H{2 * carbons + 2}O{oxygens}"
    balanced = (
        balance(f"{fuel} + O2 -> CO2 + H2O")
        if oxygens
        else balance(f"C{carbons}H{2 * carbons + 2} + O2 -> CO2 + H2O")
    )
    assert balanced.is_balanced
    assert all(c.denominator == 1 for c in balanced.coefficients)


def test_limiting_reagent() -> None:
    result = limiting_reagent("N2 + 3 H2 -> 2 NH3", {"N2": 1.0, "H2": 2.0})
    assert result.limiting == "H2"
    assert result.extent == pytest.approx(2.0 / 3.0)
    assert result.final == pytest.approx({"N2": 1.0 / 3.0, "H2": 0.0, "NH3": 4.0 / 3.0})


def test_limiting_reagent_refuses_a_missing_reactant_and_negative_feed() -> None:
    with pytest.raises(StoichiometryError):
        limiting_reagent("N2 + 3 H2 -> 2 NH3", {"N2": 1.0})
    with pytest.raises(StoichiometryError):
        limiting_reagent("N2 + 3 H2 -> 2 NH3", {"N2": -1.0, "H2": 1.0})


def test_yield_and_percent() -> None:
    assert theoretical_yield("2 H2 + O2 -> 2 H2O", {"H2": 4.0, "O2": 1.0}, "H2O") == pytest.approx(2.0)
    assert percent_yield(1.5, 2.0) == pytest.approx(75.0)
    with pytest.raises(StoichiometryError):
        theoretical_yield("2 H2 + O2 -> 2 H2O", {"H2": 4.0, "O2": 1.0}, "O2")


def test_atom_economy_of_a_pure_addition_is_100() -> None:
    assert atom_economy("C2H4 + H2 -> C2H6", "C2H6") == pytest.approx(100.0)
    assert 0.0 < atom_economy("CH4 + H2O -> CO + 3 H2", "H2") < 100.0


def test_reactor_performance() -> None:
    perf = reactor_performance({"A": 10.0}, {"A": 2.0, "B": 4.0}, "A", "B")
    assert perf.conversion == pytest.approx(0.8)
    assert perf.selectivity == pytest.approx(0.5)
    assert perf.yield_ == pytest.approx(0.4)


def test_to_reaction_builds_a_validated_contract() -> None:
    reaction = to_reaction("CH4 + H2O -> CO + 3 H2", reaction_id="smr", provenance="test")
    assert isinstance(reaction, Reaction)
    assert reaction.stoichiometry["74-82-8"] == -1.0
    assert reaction.stoichiometry["1333-74-0"] == 3.0
    assert reaction.base_component == "74-82-8"


def test_to_reaction_maps_onto_a_slate() -> None:
    reaction = to_reaction(
        "CH4 + 2 O2 -> CO2 + 2 H2O",
        reaction_id="burn",
        provenance="test",
        ids={"CH4": "C1"},
    )
    assert reaction.base_component == "C1"


def test_contract_still_refuses_an_unbalanced_reaction() -> None:
    with pytest.raises(ValueError, match="element"):
        Reaction(id="x", stoichiometry={"C1": -1.0, "CO2": 1.0}, base_component="C1", provenance="t")
    assert issubclass(ElementBalanceError, ValueError)


def test_a_catalyst_is_not_the_limiting_reagent() -> None:
    """Regression: NO, regenerated each turnover, limited the reaction and ended at zero."""
    result = limiting_reagent(
        parse_equation("2 SO2 + O2 + 2 NO -> 2 SO3 + 2 NO"), {"SO2": 10.0, "O2": 10.0, "NO": 1.0}
    )
    assert result.limiting == "SO2"
    assert result.extent == pytest.approx(5.0)
    assert result.final["NO"] == pytest.approx(1.0)
