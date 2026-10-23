"""Spec U-R acceptance: reaction contracts — validation, balances, serialization."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ngdesign.contracts.flowsheet import Flowsheet
from ngdesign.contracts.reactions import Equilibrium, PowerLaw, Reaction, ReactionSet
from ngdesign.data import component_record, register_pseudo

# N2 is inert: it stays on the set's slate but not in the stoichiometry.
COMBUSTION = {
    "CH4": -1.0,
    "O2": -2.0,
    "CO2": 1.0,
    "H2O": 2.0,
}

register_pseudo("test-lump", "Test lump", Tb=500.0, sg=0.8)


def _combustion_reaction(**overrides: object) -> Reaction:
    fields: dict[str, object] = {
        "id": "methane_combustion",
        "stoichiometry": dict(COMBUSTION),
        "base_component": "CH4",
        "provenance": "SVA ch. 4 complete combustion; 3.76 mol N2 per mol O2",
    }
    fields.update(overrides)
    return Reaction(**fields)


def _reaction_set(**overrides: object) -> ReactionSet:
    fields: dict[str, object] = {
        "id": "combustion",
        "reactions": [_combustion_reaction()],
        "components": ["CH4", "O2", "CO2", "H2O", "N2"],
    }
    fields.update(overrides)
    return ReactionSet(**fields)


def _flowsheet(reactions: list[ReactionSet] | None = None) -> Flowsheet:
    return Flowsheet(name="reaction-flowsheet", units=[], streams=[], reactions=reactions or [])


def test_reaction_json_round_trip() -> None:
    reaction = Reaction(
        id="wgsr",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        equilibrium=Equilibrium(form="from_gibbs"),
        kinetics=PowerLaw(
            rate_units="mol/(m3·s)",
            k0=2.77e-3,
            Ea=65432.0,
            orders={"CO": 1.0, "H2O": 1.0},
        ),
        provenance="SVA ch. 13 water-gas shift reaction",
    )
    payload = json.loads(reaction.model_dump_json())
    assert Reaction(**payload) == reaction


def test_reaction_set_json_round_trip() -> None:
    rset = _reaction_set()
    payload = json.loads(rset.model_dump_json())
    assert ReactionSet(**payload) == rset


def test_empty_provenance_is_refused_naming_reaction() -> None:
    with pytest.raises(ValidationError, match="methane_combustion"):
        _combustion_reaction(provenance="   ")


def test_zero_stoichiometry_is_refused_naming_component() -> None:
    with pytest.raises(ValidationError, match="N2"):
        _combustion_reaction(stoichiometry={**COMBUSTION, "N2": 0.0})


def test_base_component_with_positive_nu_is_refused() -> None:
    with pytest.raises(ValidationError, match="must appear with"):
        _combustion_reaction(stoichiometry={k: -v for k, v in COMBUSTION.items()})


def test_base_component_missing_from_stoichiometry_is_refused() -> None:
    with pytest.raises(ValidationError, match="base_component 'CO'"):
        _combustion_reaction(base_component="CO")


def test_unbalanced_stoichiometry_is_refused_naming_element() -> None:
    # H2O removed: the H balance is violated (4 in, 0 out) and refused.
    with pytest.raises(ValidationError, match="balance violated"):
        _combustion_reaction(stoichiometry={"CH4": -1.0, "O2": -2.0, "CO2": 1.0})


def test_reaction_outside_the_slate_is_refused_naming_the_component() -> None:
    # The slate omits H2O; the combustion reaction consumes it, so the set
    # refuses and names the missing component.
    with pytest.raises(ValidationError, match="'H2O'"):
        _reaction_set(components=["CH4", "O2", "CO2"])


def test_duplicate_reaction_ids_are_refused_naming_the_id() -> None:
    with pytest.raises(ValidationError, match="methane_combustion"):
        _reaction_set(reactions=[_combustion_reaction(), _combustion_reaction()])


def test_pseudo_component_requires_lumped_flag() -> None:
    with pytest.raises(ValidationError, match="lump=True"):
        Reaction(
            id="fake_crack",
            stoichiometry={"test-lump": -1.0},
            base_component="test-lump",
            provenance="test-only pseudo refusal",
        )


def test_lumped_reaction_with_violated_mass_balance_is_refused() -> None:
    mw = float(component_record("test-lump")["mw"])
    # A single decomposition product cannot conserve mass: ν·MW = -MW, i.e.
    # 100 % off, far beyond the 2 % tolerance.
    assert mw > 0.0
    with pytest.raises(ValidationError, match="mass balance"):
        ReactionSet(
            id="lumps",
            reactions=[
                Reaction(
                    id="fake_crack",
                    stoichiometry={"test-lump": -1.0},
                    base_component="test-lump",
                    lumped=True,
                    provenance="test-only mass-balance refusal",
                )
            ],
            components=["test-lump"],
        )


def test_ln_keq_polynomial_requires_t_window() -> None:
    with pytest.raises(ValidationError, match="t_window"):
        Equilibrium(form="polynomial", polynomial={0.0: 10.0, -1.0: -2000.0})


def test_flowsheet_with_reactions_serialises_them() -> None:
    rset = _reaction_set()
    fs = _flowsheet([rset])
    payload = json.loads(fs.model_dump_json())
    assert len(payload["reactions"]) == 1
    assert payload["reactions"][0]["id"] == "combustion"
    assert Flowsheet(**payload) == fs


def test_flowsheet_without_reactions_serialises_byte_identically() -> None:
    without = Flowsheet(name="blank", units=[], streams=[], thermo="pr", components=["CH4"])
    with_empty = Flowsheet(name="blank", units=[], streams=[], thermo="pr", components=["CH4"], reactions=[])
    assert without.model_dump_json() == with_empty.model_dump_json()
