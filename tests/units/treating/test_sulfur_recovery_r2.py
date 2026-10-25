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
from typing import Any

import pytest

from ngdesign.contracts.reactions import ReactionSet
from ngdesign.data.formation import atomic_composition
from ngdesign.registry import create
from ngdesign.units._physics.gibbs import GibbsError
from ngdesign.units._physics.kinetics import apply_extents, ln_keq
from ngdesign.units.treating.sulfur_recovery import (
    SulfurRecovery,
    SulfurRecoveryError,
    _approach_extent,
)
from ngdesign.units.treating.sulfur_recovery_r2 import (
    SulfurRecoveryR2,
    _converter_equilibrium,
)

THERMO = create("thermo", "pr")

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


# ---------------------------------------------------------------------------
# Step 2: the SulfurRecoveryR2 adapter.
# ---------------------------------------------------------------------------


def _r2_setup() -> tuple[Any, dict[str, Any]]:
    """R0's example feed flashed, and R0's params with the stages replaced."""
    feeds, params = SulfurRecovery.example_case()
    f = feeds["acid_gas_in"]
    feed = THERMO.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    # R0's example carries conversion stages; the default here is one Gibbs
    # stage, so refusal tests exercise the refusal they name rather than the
    # conversion-stage rejection.
    return feed, dict(params, catalytic_stages=[{"T": 573.15}])


def _solve(feed: Any, params: dict[str, Any]) -> Any:
    return SulfurRecoveryR2().solve({"acid_gas_in": feed}, params, THERMO)


def _elements(state: Any) -> dict[str, float]:
    totals: dict[str, float] = {}
    for cid, frac in state.composition.items():
        for element, count in atomic_composition(cid).items():
            totals[element] = totals.get(element, 0.0) + count * frac * state.molar_flow
    return totals


def test_r2_reduces_to_r0_approach_mode() -> None:
    """R0 identity (spec, rel 1e-10): with the species set restricted to R0's
    (H2S, SO2, H2O, S8 + the inerts N2, CO2 riding as species), the R2 Gibbs
    minimum over the gas {H2S 2, SO2 1, H2O 4, N2 10, CO2 1} at T_eq 503 K,
    P 1.5e5 Pa equals R0's ``_approach_extent`` + ``apply_extents`` result.
    The one Claus degree of freedom is the Gibbs minimum's only one."""
    gas = {"H2S": 2.0, "SO2": 1.0, "H2O": 4.0, "N2": 10.0, "CO2": 1.0}
    _, params = SulfurRecovery.example_case()
    rset = ReactionSet.model_validate(params["reaction_set"])
    xi, _ln_k = _approach_extent(gas, rset.reactions[1], 473.0, 30.0, 1.5e5)
    n_r0 = apply_extents(gas, rset, [0.0, xi])
    n_r2 = SulfurRecoveryR2()._run_converter(
        gas, 503.0, 1.5e5, _species_override=["H2S", "SO2", "H2O", "S8", "N2", "CO2"]
    )
    for cid in ("H2S", "SO2", "H2O", "S8"):
        assert n_r2[cid] == pytest.approx(n_r0[cid], rel=1e-10), cid


def test_adapter_closes_element_balances_over_the_ports() -> None:
    """V0: every element (S, H, O, N, C) closes in = out at 1e-8 across
    acid_gas_in -> tail_gas_out + sulfur_out on a two-stage Gibbs run."""
    feed, params = _r2_setup()
    result = _solve(feed, {**params, "catalytic_stages": [{"T": 573.15}, {"T": 473.15}]})
    inlet = _elements(feed)
    outlet = _elements(result.outlets["tail_gas_out"])
    for element, amount in _elements(result.outlets["sulfur_out"]).items():
        outlet[element] = outlet.get(element, 0.0) + amount
    for element in sorted(set(inlet) | set(outlet)):
        assert outlet.get(element, 0.0) == pytest.approx(inlet.get(element, 0.0), abs=1e-8), element


def test_adapter_reports_stage_information_and_recovery() -> None:
    """info carries R0's keys plus the per-stage Gibbs keys; the recovery
    fraction counts S atoms through both allotropes (6 and 8)."""
    feed, params = _r2_setup()
    result = _solve(feed, {**params, "catalytic_stages": [{"T": 573.15}, {"T": 473.15}]})
    info = result.info
    assert info["n_catalytic_stages"] == 2.0
    assert 0.0 < info["stage_0_H2S_conversion"] < 1.0
    assert info["stage_0_T_eq_K"] == 573.15
    assert info["stage_1_S6_mol_s"] > 0.0
    assert info["stage_1_S8_mol_s"] > 0.0
    assert 0.0 < info["sulfur_recovery_fraction"] <= 1.0
    # stage_i keys are the incremental condensate of catalytic stage i; the
    # outlet also carries the thermal stage's sulfur, so it is at least the
    # catalytic sum. S-atom closure is checked across the ports.
    s6_sum = sum(info[f"stage_{i}_S6_mol_s"] for i in range(2))
    s8_sum = sum(info[f"stage_{i}_S8_mol_s"] for i in range(2))
    assert info["sulfur_out_mol_s"] >= s6_sum + s8_sum
    assert info["sulfur_out_mol_s"] == pytest.approx(result.outlets["sulfur_out"].molar_flow, rel=1e-12)
    s_in = _elements(feed).get("S", 0.0)
    s_tail = _elements(result.outlets["tail_gas_out"]).get("S", 0.0)
    s_cond = _elements(result.outlets["sulfur_out"]).get("S", 0.0)
    assert s_cond == pytest.approx(s_in - s_tail, rel=1e-8)
    assert 0.0 < s_cond < s_in


def test_adapter_is_deterministic() -> None:
    feed, params = _r2_setup()
    stages = [{"T": 573.15}, {"T": 473.15, "approach_K": 0.0}]
    first = _solve(feed, {**params, "catalytic_stages": stages})
    second = _solve(feed, {**params, "catalytic_stages": stages})
    assert first.info == second.info
    assert first.duty_W == second.duty_W
    for port in ("tail_gas_out", "sulfur_out"):
        assert first.outlets[port] == second.outlets[port]


def test_sulfur_out_flashes_the_s6_s8_mixture() -> None:
    """sulfur_out carries both allotropes at their summed composition."""
    feed, params = _r2_setup()
    result = _solve(feed, {**params, "catalytic_stages": [{"T": 573.15}]})
    sulfur = result.outlets["sulfur_out"]
    assert set(sulfur.composition) == {"S6", "S8"}
    assert sulfur.molar_flow > 0.0


def _refuses(params: dict[str, Any], feed: Any, pattern: str) -> str:
    with pytest.raises(SulfurRecoveryError, match=pattern) as excinfo:
        _solve(feed, params)
    return str(excinfo.value)


def test_refusal_conversion_stage_is_rejected() -> None:
    """R2 has no conversion path: a stage carrying 'conversion' is refused,
    naming both the parameter and the level."""
    feed, params = _r2_setup()
    message = _refuses({**params, "catalytic_stages": [{"T": 573.15, "conversion": 0.5}]}, feed, "conversion")
    assert "R2" in message


def test_refusal_nonpositive_stage_temperature() -> None:
    feed, params = _r2_setup()
    _refuses({**params, "catalytic_stages": [{"T": 0.0}]}, feed, r"catalytic_stages\[0\]")


def test_refusal_negative_approach() -> None:
    feed, params = _r2_setup()
    _refuses(
        {**params, "catalytic_stages": [{"T": 573.15, "approach_K": -5.0}]},
        feed,
        r"catalytic_stages\[0\]",
    )


def test_refusal_extra_species_outside_the_enum() -> None:
    feed, params = _r2_setup()
    _refuses({**params, "extra_species": ["S2"]}, feed, "extra_species")


def test_refusal_species_without_formation_data() -> None:
    """A converter species without databank formation data is refused, naming
    the species (internal function; the public enum keeps bad extras out)."""
    with pytest.raises(SulfurRecoveryError, match="Zz9"):
        _converter_equilibrium(GAS, 550.0, P, [*SPECIES, "Zz9"])


def test_refusal_gibbs_failure_is_wrapped_with_the_stage_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A GibbsError from the solver surfaces as SulfurRecoveryError naming the
    catalytic stage."""
    import ngdesign.units.treating.sulfur_recovery_r2 as r2

    def _boom(gas: Any, T: float, P_: float, species: Any) -> dict[str, float]:
        raise GibbsError("synthetic solver failure")

    monkeypatch.setattr(r2, "_converter_equilibrium", _boom)
    feed, params = _r2_setup()
    with pytest.raises(SulfurRecoveryError, match="catalytic stage 0"):
        _solve(feed, {**params, "catalytic_stages": [{"T": 573.15}]})


def test_refusal_oxygen_lean_feed() -> None:
    """R0's own refusal, unchanged: the burner mixture must carry the air."""
    feed, params = _r2_setup()
    lean = THERMO.flash_pt({"H2S": 0.30, "O2": 0.05, "N2": 0.65}, 320.0, 1.5e5, 100.0)
    _refuses({**params, "catalytic_stages": [{"T": 573.15}]}, lean, "O2")


def test_refusal_feed_without_h2s() -> None:
    feed, params = _r2_setup()
    sour = THERMO.flash_pt({"CO2": 0.5, "N2": 0.5}, 320.0, 1.5e5, 100.0)
    _refuses({**params, "catalytic_stages": [{"T": 573.15}]}, sour, "no H2S")


def test_refusal_bad_reaction_set() -> None:
    feed, params = _r2_setup()
    single = {
        **params,
        "reaction_set": dict(params["reaction_set"], reactions=[params["reaction_set"]["reactions"][0]]),
    }
    _refuses(single, feed, "exactly 2 reactions")
