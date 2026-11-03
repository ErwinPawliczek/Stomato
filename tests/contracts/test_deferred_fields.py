"""DeferredModel: deferred fields read, dump and compare exactly like eager ones.

Phase and PhaseProps carry transport properties that thermo packages compute on
first read. Every reader must see the record an eager build would give.
"""

from __future__ import annotations

import copy
import pickle
from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.stream import Phase, PhaseKind
from ngdesign.contracts.thermo import PhaseProps

_KW: dict[str, Any] = {
    "kind": PhaseKind.VAPOR,
    "mole_fraction": 1.0,
    "composition": {"C1": 1.0},
    "density": 5.0,
    "molecular_weight": 16.0,
}
_MU = 1.5e-5


class _Counter:
    def __init__(self, value: float | None) -> None:
        self.value = value
        self.calls = 0

    def __call__(self) -> float | None:
        self.calls += 1
        return self.value


def _stream(phase: Phase) -> StreamState:
    return StreamState(
        T=300.0,
        P=1e5,
        molar_flow=1.0,
        composition={"C1": 1.0},
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[phase],
    )


def test_not_computed_until_read() -> None:
    mu = _Counter(_MU)
    phase = Phase.deferred({"viscosity": mu}, **_KW)
    assert mu.calls == 0
    assert phase.density == 5.0
    assert mu.calls == 0
    assert phase.viscosity == _MU
    assert phase.viscosity == _MU
    assert mu.calls == 1


@pytest.mark.parametrize("value", [_MU, None])
def test_every_reader_sees_the_eager_record(value: float | None) -> None:
    eager = Phase(viscosity=value, **_KW)

    def lazy() -> Phase:
        return Phase.deferred({"viscosity": lambda: value}, **_KW)

    assert lazy() == eager
    assert eager == lazy()
    assert lazy().model_dump() == eager.model_dump()
    assert lazy().model_dump_json() == eager.model_dump_json()
    assert repr(lazy()) == repr(eager)
    assert dict(lazy()) == dict(eager)
    assert lazy().model_fields_set == eager.model_fields_set
    assert pickle.loads(pickle.dumps(lazy())) == eager
    assert copy.deepcopy(lazy()) == eager
    # Nested: the parent's serializer must resolve the child (same JSON bytes).
    assert _stream(lazy()).model_dump_json() == _stream(eager).model_dump_json()
    assert _stream(lazy()).model_copy(deep=True) == _stream(eager)


def test_copies_resolve_independently() -> None:
    mu = _Counter(_MU)
    base = PhaseProps.deferred(
        {"viscosity": mu, "thermal_conductivity": lambda: 0.03},
        **_KW,
        enthalpy=1.0,
        entropy=2.0,
        cp=30.0,
        gibbs=0.0,
        z_factor=1.0,
    )
    changed = base.model_copy(update={"enthalpy": 9.0})
    assert base.viscosity == _MU
    assert changed.viscosity == _MU
    assert changed.thermal_conductivity == 0.03
    assert changed.enthalpy == 9.0
    assert list(changed.model_dump()) == list(PhaseProps.model_fields)


def test_assignment_keeps_the_record_whole() -> None:
    props = PhaseProps.deferred(
        {"viscosity": lambda: _MU},
        **_KW,
        enthalpy=1.0,
        entropy=2.0,
        cp=30.0,
        gibbs=0.0,
        z_factor=1.0,
    )
    props.enthalpy = 3.0
    assert props.viscosity == _MU
    assert props.enthalpy == 3.0


def test_unknown_field_refused() -> None:
    with pytest.raises(ValueError, match="no field"):
        Phase.deferred({"not_a_field": lambda: 1.0}, **_KW)


def test_schema_unchanged_by_the_resolving_serializer() -> None:
    for model in (Phase, PhaseProps):
        assert model.model_json_schema(mode="serialization") == model.model_json_schema(mode="validation")
