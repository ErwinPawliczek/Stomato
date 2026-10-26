"""Catalytic reformer R1 tests (spec ``specs/backend/units/reformer_cat.md``).

Step 1: the ``_smith_to_contract`` conversion check (a unit test on the
function alone) and the refusal-table rows for the feed slate and the
``kinetics`` parameter. Steps 2–3 add the dehydro equilibrium closed form,
the k0 = 0 identity, the three-bed adiabatic V0, and the bed refusals.
"""

from __future__ import annotations

import pytest

from ngdesign.units.refining.reformer_kinetic import (
    ReformerKineticError,
    _ea_from_b,
    _smith_to_contract,
    build_reaction_set,
    kinetics_param,
    validate_slate,
)

#: The spec's test constants (NOT Smith's): K1 = exp(46.15 - 25000/T) atm^3.
A_K1, B_K1 = 46.15, 25000.0


def test_smith_to_contract_conversion() -> None:
    """Spec test, on the function alone: k0' = k0·C_u·P_atm^Σorders.

    With k0 = 1 lb-mol/(h·lb_cat·atm), order 1 and P = 10 atm:
    k0' = 1·(1000/3600)·10 = 2.77777778 mol/(kg_cat·s).
    """
    k0_prime, _ea = _smith_to_contract(1.0, 0.0, 1.0, 10.0)
    assert k0_prime == pytest.approx(1000.0 / 3600.0 * 10.0, rel=1e-9)


def test_smith_to_contract_pressure_cancels_for_hc_rates() -> None:
    """r3 = k3·p_N/P and r4 = k4·p_P/P: p_i/P = y_i, so no atm power (Σorders 0)."""
    k0_prime, _ea = _smith_to_contract(1.0, 0.0, 0.0, 20.0)
    assert k0_prime == pytest.approx(1000.0 / 3600.0, rel=1e-12)


def test_ea_from_deg_r_exponent() -> None:
    """Spec test: with b = 18000 °R, Ea = R·18000/1.8 = 83144.6262 J/mol."""
    assert _ea_from_b(18000.0) == pytest.approx(83144.6262, rel=1e-6)


def test_reaction_set_builds_and_is_element_balanced() -> None:
    """The four Smith reactions build against the contract's element validator.

    Constant check (test constants, not Smith's): K1 = exp(46.15 - 25000/T)
    with T in K gives K1(650 K) = 2183.0135 atm^3, the closed-form case below.
    """
    kin = kinetics_param(
        {
            "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": A_K1, "B_K": B_K1},
            "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 10.0, "B_K": 2000.0},
            "hc_n": {"k0": 1.0, "Ea": 5.0e4},
            "hc_p": {"k0": 1.0, "Ea": 5.0e4},
        }
    )
    rset = build_reaction_set(kin, p_atm=20.0)
    assert rset.id == "reformer_smith_r1"
    assert [r.id for r in rset.reactions] == ["dehydro", "n_to_p", "hc_n", "hc_p"]
    # The contract's element-balance validator ran at construction: every
    # stoichiometry is element-balanced (C and H) without the lumped flag.
    dehydro = rset.reactions[0]
    assert dehydro.stoichiometry == {"methylcyclohexane": -1.0, "toluene": 1.0, "H2": 3.0}
    assert dehydro.base_component == "methylcyclohexane"
    hc_p = rset.reactions[3]
    assert hc_p.stoichiometry["nC7"] == -1.0
    assert hc_p.stoichiometry["H2"] == pytest.approx(-4.0 / 3.0)
    for cid in ("C1", "C2", "C3", "nC4", "nC5"):
        assert hc_p.stoichiometry[cid] == pytest.approx(7.0 / 15.0)
    # Forward + explicit reverse PowerLawRates on the mole-fraction basis,
    # per catalyst mass; the hydrocracking rates are irreversible.
    assert rset.reactions[0].kinetics is not None and rset.reactions[0].kinetics.reverse is not None
    assert rset.reactions[1].kinetics is not None and rset.reactions[1].kinetics.reverse is not None
    assert rset.reactions[2].kinetics is not None and rset.reactions[2].kinetics.reverse is None
    assert rset.reactions[3].kinetics is not None and rset.reactions[3].kinetics.reverse is None


def test_refuses_feed_species_outside_slate() -> None:
    """A pseudo (or any non-slate) species is refused, naming #222 and the slate."""
    with pytest.raises(ReformerKineticError, match="#222"):
        validate_slate({"nC7": 1.0, "some_pseudo": 0.5})
    with pytest.raises(ReformerKineticError, match="slate"):
        validate_slate({"benzene": 1.0})


def test_refuses_kinetics_preset() -> None:
    """``smith1959`` is refused until the constants are transcribed with a citation."""
    with pytest.raises(ReformerKineticError, match="preset"):
        kinetics_param("smith1959")


def test_refuses_kinetics_missing_reaction() -> None:
    """A kinetics object missing a reaction is refused, naming the reaction id."""
    with pytest.raises(ReformerKineticError, match="hc_p"):
        kinetics_param(
            {
                "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "hc_n": {"k0": 1.0, "Ea": 5.0e4},
            }
        )


def test_refuses_kinetics_missing_field() -> None:
    """A kinetics block missing a field is refused, naming the field."""
    with pytest.raises(ReformerKineticError, match="B_K"):
        kinetics_param(
            {
                "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0},
                "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "hc_n": {"k0": 1.0, "Ea": 5.0e4},
                "hc_p": {"k0": 1.0, "Ea": 5.0e4},
            }
        )
