"""Closed-form tests for the R2 Claus sulfur-recovery level (step 1).

The R2 catalytic converter is a Gibbs minimum over its species set. These
tests check it against an independent extent-space solve of the two Claus
routes 2 H2S + SO2 -> 2 H2O + (3/6) S6 and 2 H2S + SO2 -> 2 H2O + (3/8) S8
(``calc_sulfur_recovery.py``: ``scipy.optimize.fsolve`` on ln K with mu0 from
the data layer, ``ngdesign.units._physics.kinetics.ln_keq`` path); the expected
table below is that solve's output, quoted in the unit spec. With 4 reacting
species (H2S, SO2, H2O and the total sulfur pool split between S6 and S8 over
one H/O/S budget) the system has exactly the Claus extent as its one degree of
freedom, so the Gibbs result and the extent-space solve must agree to round-off.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.contracts.reactions import ReactionSet
from ngdesign.units._physics.kinetics import ln_keq
from ngdesign.units.treating.sulfur_recovery_r2 import _converter_equilibrium

P = 1.3e5
GAS = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0}
SPECIES = ["H2S", "SO2", "H2O", "S6", "S8", "N2"]

# Expected outlet flows, mol/s, from the spec's independent extent-space solve
# (rel 1e-7): the Gibbs minimum over SPECIES at P must reproduce each row.
EXPECTED_TABLE: dict[float, dict[str, float]] = {
    500.0: {
        "H2S": 0.1484047,
        "SO2": 0.0742023499,
        "H2O": 5.8515953,
        "S6": 0.0510661578,
        "S8": 0.3088745,
    },
    550.0: {
        "H2S": 0.300279162,
        "SO2": 0.150139581,
        "H2O": 5.69972084,
        "S6": 0.0789358317,
        "S8": 0.259495783,
    },
    600.0: {
        "H2S": 0.524034079,
        "SO2": 0.26201704,
        "H2O": 5.47596592,
        "S6": 0.103411603,
        "S8": 0.199184908,
    },
}


def _h2s_conversion(n_out: dict[str, float]) -> float:
    return 1.0 - n_out["H2S"] / GAS["H2S"]


def test_closed_form_gibbs_converter_isothermal() -> None:
    """Spec table (extent-space solve, rel 1e-7) at 500/550/600 K, P = 1.3e5 Pa."""
    for T, expected in EXPECTED_TABLE.items():
        n_out = _converter_equilibrium(GAS, T, P, SPECIES)
        for cid, value in expected.items():
            assert n_out[cid] == pytest.approx(value, rel=1e-7), (T, cid)


def test_closed_form_h2s_conversion_matches_the_table() -> None:
    """The spec's conversion column: 1 - n_H2S,out / n_H2S,in."""
    expected_conversions = {500.0: 0.92579765, 550.0: 0.849860419, 600.0: 0.73798296}
    for T, expected in expected_conversions.items():
        n_out = _converter_equilibrium(GAS, T, P, SPECIES)
        assert _h2s_conversion(n_out) == pytest.approx(expected, rel=1e-7), T


def test_ln_keq_cross_check_at_550_k() -> None:
    """The extent-space solve's ln K at 550 K: S6 route 7.78370127, S8 route
    8.86491862. The Gibbs minimum is built on the same mu0 assembly, so its
    equilibrium must sit where these reaction constants say."""
    rset = ReactionSet.model_validate(
        {
            "id": "claus_routes",
            "components": ["H2S", "SO2", "H2O", "S6", "S8"],
            "reactions": [
                {
                    "id": "claus_s6",
                    "stoichiometry": {"H2S": -2.0, "SO2": -1.0, "H2O": 2.0, "S6": 0.5},
                    "base_component": "SO2",
                    "provenance": "standard Claus reaction to S6",
                    "equilibrium": {"form": "from_gibbs"},
                },
                {
                    "id": "claus_s8",
                    "stoichiometry": {"H2S": -2.0, "SO2": -1.0, "H2O": 2.0, "S8": 0.375},
                    "base_component": "SO2",
                    "provenance": "standard Claus reaction to S8",
                    "equilibrium": {"form": "from_gibbs"},
                },
            ],
        }
    )
    r6, r8 = rset.reactions
    assert ln_keq(r6, 550.0) == pytest.approx(7.78370127, rel=1e-7)
    assert ln_keq(r8, 550.0) == pytest.approx(8.86491862, rel=1e-7)


def test_conversion_falls_as_converter_temperature_rises() -> None:
    """Direction: the exothermic Claus equilibrium converts less H2S as the
    (isothermal) converter gets hotter -- strictly decreasing over the table."""
    conversions = [
        _h2s_conversion(_converter_equilibrium(GAS, T, P, SPECIES)) for T in sorted(EXPECTED_TABLE)
    ]
    assert all(conversions[i] > conversions[i + 1] for i in range(len(conversions) - 1)), conversions


def test_species_set_carries_inert_atoms_as_species() -> None:
    """N2 rides as an ordinary species (inerts=[]): the element-potential method
    counts its atoms in the budget, and dropping it from the species set must
    be refused rather than silently dropping the nitrogen."""
    from ngdesign.units._physics.gibbs import GibbsError

    with pytest.raises(GibbsError, match="'N'"):
        _converter_equilibrium(GAS, 550.0, P, ["H2S", "SO2", "H2O", "S6", "S8"])


def test_converter_equilibrium_is_deterministic() -> None:
    """Same inputs, same numbers run to run (fsolve from a fixed start)."""
    first = _converter_equilibrium(GAS, 550.0, P, SPECIES)
    second = _converter_equilibrium(GAS, 550.0, P, SPECIES)
    assert first.keys() == second.keys()
    for cid in first:
        assert math.isclose(first[cid], second[cid], rel_tol=0.0, abs_tol=0.0)
