"""Spec T-10: a StreamState carrying a SOLID phase round-trips through JSON unchanged.

``PhaseKind.SOLID`` is the T-10 contract change; existing consumers never see it
unless a package emits a solid phase, and the serialised form of every existing
stream is byte-identical (goldens unchanged). This pins the new member's wire
value and the frozen models' equality after a JSON round trip.
"""

from __future__ import annotations

from ngdesign.contracts import Phase, PhaseKind, StreamState


def _solid_liquid_state() -> StreamState:
    liquid = Phase(
        kind=PhaseKind.HC_LIQUID,
        mole_fraction=0.7,
        composition={"benzene": 0.8, "naphthalene": 0.2},
        density=870.0,
        molecular_weight=90.0,
        enthalpy=-1.2e4,
        entropy=-30.0,
        cp=140.0,
        ln_phi={"benzene": -0.1, "naphthalene": -0.5},
    )
    solid = Phase(
        kind=PhaseKind.SOLID,
        mole_fraction=0.3,
        composition={"naphthalene": 1.0},
        density=1140.0,
        molecular_weight=128.17,
        enthalpy=-3.0e4,
        entropy=-80.0,
        cp=165.0,
    )
    return StreamState(
        T=298.15,
        P=101325.0,
        molar_flow=10.0,
        composition={"benzene": 0.56, "naphthalene": 0.44},
        vapor_fraction=0.0,
        enthalpy=-1.74e4,
        entropy=-45.0,
        phases=[liquid, solid],
    )


def test_solid_phase_round_trips_through_json() -> None:
    state = _solid_liquid_state()
    revived = StreamState.model_validate_json(state.model_dump_json())
    assert revived == state
    assert revived.phases[1].kind is PhaseKind.SOLID
    assert '"kind":"solid"' in state.model_dump_json()


def test_solid_counts_as_non_vapour() -> None:
    """All non-vapour phases count as liquid for vapor_fraction (contract docstring)."""
    state = _solid_liquid_state()
    assert state.vapor_fraction == 0.0
    assert sum(p.mole_fraction for p in state.phases) == 1.0
