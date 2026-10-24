"""Closed-form tests for the R0 Claus sulfur-recovery adapter (spec U-G).

The row is registered at R0 provisional; the V1 case lives in
data/validation_units/treating/cases.yaml and these tests import the adapter
class directly for the closed-form assertions.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.data.formation import atomic_composition
from ngdesign.registry import create
from ngdesign.units.treating.sulfur_recovery import SulfurRecovery, SulfurRecoveryError

THERMO = create("thermo", "pr")


def _example() -> tuple[Any, dict[str, Any]]:
    feeds, params = SulfurRecovery.example_case()
    f = feeds["acid_gas_in"]
    feed = THERMO.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    return feed, params


def _solve(feed: Any, params: dict[str, Any]) -> Any:
    return SulfurRecovery().solve({"acid_gas_in": feed}, params, THERMO)


def _elements(state: Any) -> dict[str, float]:
    totals: dict[str, float] = {}
    for cid, frac in state.composition.items():
        for element, count in atomic_composition(cid).items():
            totals[element] = totals.get(element, 0.0) + count * frac * state.molar_flow
    return totals


def test_full_conversion_closes_the_stoichiometry_by_hand() -> None:
    """Burn 1/3 of 30 mol/s H2S, then 100 % Claus conversion on each side:

    burn:   10 H2S + 15 O2 -> 10 SO2 + 10 H2O
    claus:  10 SO2 + 20 H2S -> 20 H2O + 3.75 S8
    tail:   H2O 30, N2 50, CO2 5 -- no H2S, SO2 or O2 left.
    """
    feed, params = _example()
    full = dict(params)
    full["thermal_conversion"] = 1.0
    full["catalytic_stages"] = [{"T": 573.15, "conversion": 1.0}]
    result = _solve(feed, full)
    assert result.info["sulfur_out_mol_s"] == pytest.approx(3.75, abs=1e-9)
    assert result.info["sulfur_recovery_fraction"] == pytest.approx(1.0, abs=1e-9)
    tail_flows = {
        cid: frac * result.outlets["tail_gas_out"].molar_flow
        for cid, frac in result.outlets["tail_gas_out"].composition.items()
    }
    assert tail_flows.get("H2O", 0.0) == pytest.approx(30.0, abs=1e-9)
    assert tail_flows.get("N2", 0.0) == pytest.approx(50.0, abs=1e-9)
    assert tail_flows.get("CO2", 0.0) == pytest.approx(5.0, abs=1e-9)
    assert tail_flows.get("H2S", 0.0) == pytest.approx(0.0, abs=1e-9)
    assert tail_flows.get("SO2", 0.0) == pytest.approx(0.0, abs=1e-9)
    assert tail_flows.get("O2", 0.0) == pytest.approx(0.0, abs=1e-9)


def test_example_case_element_balances_close_over_the_ports() -> None:
    """No air port exists (U-00 row): the burner mixture rides acid_gas_in, and
    every element must close between the inlet port and the two outlets."""
    feed, params = _example()
    result = _solve(feed, params)
    inlet = _elements(feed)
    outlet = _elements(result.outlets["tail_gas_out"])
    for element, amount in _elements(result.outlets["sulfur_out"]).items():
        outlet[element] = outlet.get(element, 0.0) + amount
    for element in sorted(set(inlet) | set(outlet)):
        assert outlet.get(element, 0.0) == pytest.approx(inlet.get(element, 0.0), abs=1e-8), element


def test_example_case_recovery_is_high_and_o2_excess_is_zero() -> None:
    """Stoichiometric burner mixture: no O2 slack, ~99 % two-stage recovery."""
    feed, params = _example()
    result = _solve(feed, params)
    assert result.info["o2_excess_mol_s"] == pytest.approx(0.0, abs=1e-9)
    assert 0.95 <= result.info["sulfur_recovery_fraction"] <= 1.0
    assert 0.0 < result.info["sulfur_out_mol_s"] < feed.molar_flow


def test_larger_approach_recovers_less_sulfur() -> None:
    """A colder equilibrium target (bigger approach) must drive a smaller
    Claus extent on the last stage."""
    feed, params = _example()
    near = dict(params)
    near["catalytic_stages"] = [
        {"T": 573.15, "conversion": 0.7},
        {"T": 473.15, "approach_K": 5.0},
    ]
    far = dict(params)
    far["catalytic_stages"] = [
        {"T": 573.15, "conversion": 0.7},
        {"T": 473.15, "approach_K": 60.0},
    ]
    assert _solve(feed, near).info["stage_1_extent_mol_s"] > _solve(feed, far).info["stage_1_extent_mol_s"]


def test_oxygen_lean_feed_is_refused() -> None:
    """The burner mixture must carry the stoichiometric air: typed refusal
    naming O2."""
    feed, params = _example()
    lean_feed = THERMO.flash_pt({"H2S": 0.30, "O2": 0.05, "N2": 0.65}, 320.0, 1.5e5, 100.0)
    with pytest.raises(SulfurRecoveryError, match="O2"):
        _solve(lean_feed, params)


def test_reaction_set_shape_is_validated() -> None:
    """Wrong reaction count, wrong base components: typed refusals."""
    feed, params = _example()
    single = dict(params)
    single["reaction_set"] = dict(params["reaction_set"], reactions=[params["reaction_set"]["reactions"][0]])
    with pytest.raises(SulfurRecoveryError, match="exactly 2 reactions"):
        _solve(feed, single)
    swapped = dict(params)
    swapped["reaction_set"] = dict(
        params["reaction_set"], reactions=list(reversed(params["reaction_set"]["reactions"]))
    )
    with pytest.raises(SulfurRecoveryError, match="base_component"):
        _solve(feed, swapped)


def test_stage_must_choose_one_extent_mode() -> None:
    """A catalytic stage with both or neither of conversion/approach_K is
    refused, naming the stage."""
    feed, params = _example()
    both = dict(params)
    both["catalytic_stages"] = [{"T": 573.15, "conversion": 0.5, "approach_K": 10.0}]
    with pytest.raises(SulfurRecoveryError, match=r"catalytic_stages\[0\]"):
        _solve(feed, both)
    neither = dict(params)
    neither["catalytic_stages"] = [{"T": 573.15}]
    with pytest.raises(SulfurRecoveryError, match=r"catalytic_stages\[0\]"):
        _solve(feed, neither)


def test_solve_is_deterministic() -> None:
    feed, params = _example()
    first = _solve(feed, params)
    second = _solve(feed, params)
    assert first.info == second.info
    assert first.duty_W == second.duty_W
    for port in ("tail_gas_out", "sulfur_out"):
        assert first.outlets[port] == second.outlets[port]
