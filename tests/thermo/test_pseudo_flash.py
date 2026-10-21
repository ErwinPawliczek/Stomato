"""PR flash over a mixed curated + databank + pseudo support (spec P1-02).

C1/C7+ at 300 K, 30 bar splits into vapor + liquid with the pseudo concentrating
in the liquid - the qualitative signature the merged constants package must
reproduce. The P1-01 enthalpy identity (stream H = mole-weighted phase H) pins
the pseudo correlations into the same state construction as databank species.
"""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import register_pseudo
from ngdesign.thermo.cubic import ThermoSurfaceMixin

_C7P_TB = 372.0
_C7P_SG = 0.73
_Z = {"C1": 0.5, "C7+": 0.5}
_T = 300.0  # K
_P = 30.0e5  # Pa


@pytest.fixture(scope="module", autouse=True)
def _pseudo() -> None:
    register_pseudo("C7+", "C7+ pseudo", Tb=_C7P_TB, sg=_C7P_SG)


@pytest.fixture(scope="module")
def thermo() -> Thermo:
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def test_pseudo_flash_two_phases_pseudo_in_liquid(thermo: Thermo) -> None:
    state: StreamState = thermo.flash_pt(_Z, _T, _P, 100.0)
    assert 0.0 < state.vapor_fraction < 1.0
    assert len(state.phases) == 2

    vapor = next(p for p in state.phases if p.kind == "vapor")
    liquid = next(p for p in state.phases if p.kind != "vapor")
    assert liquid.composition["C7+"] > vapor.composition["C7+"]
    assert liquid.composition["C7+"] > 0.5  # heavier than the feed: splits to the liquid
    assert vapor.composition["C1"] > liquid.composition["C1"]


def test_pseudo_flash_enthalpy_identity_and_balance(thermo: Thermo) -> None:
    """P1-01 identities hold over a support with a pseudo (mole-weighted H, comp sum)."""
    state = thermo.flash_pt(_Z, _T, _P, 100.0)
    enthalpy = sum(p.mole_fraction * p.enthalpy for p in state.phases)
    assert math.isclose(enthalpy, state.enthalpy, rel_tol=1e-9)
    assert math.isclose(sum(p.mole_fraction for p in state.phases), 1.0, abs_tol=1e-9)
    for cid, z in _Z.items():
        back = sum(p.mole_fraction * p.composition[cid] for p in state.phases)
        assert math.isclose(back, z, abs_tol=1e-6)


# ------------------------------------------------------------------ spec P1-07


def test_slate_context_drives_flasher_constants(thermo: ThermoSurfaceMixin) -> None:
    """The package flashes a flowsheet-owned pseudo from the slate's own definition."""
    from ngdesign.contracts.components import PseudoDefinition, resolve_set

    lean = PseudoDefinition(id="C7+", name="lean", Tb=372.0, sg=0.73)
    rich = PseudoDefinition(id="C7+", name="rich", Tb=430.0, sg=0.80)

    thermo.set_component_set(resolve_set([lean]))
    lean_bp = thermo.bubble_point({"C7+": 1.0}, T=400.0).P
    lean_flasher = thermo._build_flasher(("C7+",))

    thermo.set_component_set(resolve_set([rich]))
    rich_bp = thermo.bubble_point({"C7+": 1.0}, T=400.0).P
    rich_flasher = thermo._build_flasher(("C7+",))

    assert lean_bp is not None and rich_bp is not None
    assert lean_bp != pytest.approx(rich_bp)
    assert lean_flasher is not rich_flasher  # the cache key carries the definitions

    thermo.set_component_set(resolve_set([lean]))
    assert thermo._build_flasher(("C7+",)) is lean_flasher  # same context, same cache entry
