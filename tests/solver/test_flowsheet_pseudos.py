"""Flowsheet-owned pseudo-component definitions (spec P1-07).

Two flowsheets in one process define the same pseudo id differently: each solve
resolves the slate through the flowsheet's own definitions, hands the resolved
ComponentSet to the thermo package, and the package's flasher and Psat caches
key on the definitions - so the two solves never share constants or a flasher.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.components import PseudoDefinition
from ngdesign.data import register_pseudo
from ngdesign.solver.sequential_modular import SequentialModular


def _flowsheet(definition: PseudoDefinition) -> Flowsheet:
    return Flowsheet(
        name=f"owned-{definition.Tb}",
        units=[UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [0.5, 0.5]})],
        streams=[
            StreamSpec(
                id="F1",
                target=PortRef(unit="SPL-101", port="inlet"),
                feed=FeedSpec(T=300.0, P=20.0e5, molar_flow=100.0, composition={"C7+": 1.0}),
            ),
            StreamSpec(id="P1", source=PortRef(unit="SPL-101", port="outlet_1")),
            StreamSpec(id="P2", source=PortRef(unit="SPL-101", port="outlet_2")),
        ],
        components=[definition],
    )


def test_two_flowsheets_own_conflicting_c7_definitions() -> None:
    thermo = registry.create("thermo", "pr")
    lean = PseudoDefinition(id="C7+", name="lean C7+", Tb=372.0, sg=0.73)
    rich = PseudoDefinition(id="C7+", name="rich C7+", Tb=430.0, sg=0.80)

    lean_solved = SequentialModular().solve(_flowsheet(lean), thermo)
    lean_bp = thermo.bubble_point({"C7+": 1.0}, T=400.0).P
    rich_solved = SequentialModular().solve(_flowsheet(rich), thermo)
    rich_bp = thermo.bubble_point({"C7+": 1.0}, T=400.0).P

    assert lean_solved.converged and rich_solved.converged
    assert lean_bp is not None and rich_bp is not None
    assert lean_bp != pytest.approx(rich_bp)
    # The two solves flash the same feed at the same (T, P) but with different
    # pseudo constants: the states cannot be identical.
    assert lean_solved.streams["F1"].enthalpy != pytest.approx(rich_solved.streams["F1"].enthalpy)


def test_flowsheet_pseudo_differs_from_the_registered_default() -> None:
    """The owned definition wins over the module-level register_pseudo default.

    The registered default (Tb 372 K, sg 0.73 - the P1-02 tests' C7+) is what a
    package without slate context flashes; the same id owned by the flowsheet
    with Tb 430 K must give a different bubble pressure inside the solve's own
    package context.
    """
    register_pseudo("C7+", "C7+ pseudo", Tb=372.0, sg=0.73)
    default_pkg = registry.create("thermo", "pr")
    default_bp = default_pkg.bubble_point({"C7+": 1.0}, T=450.0).P

    thermo = registry.create("thermo", "pr")
    owned = PseudoDefinition(id="C7+", name="owned C7+", Tb=430.0, sg=0.80)
    solved = SequentialModular().solve(_flowsheet(owned), thermo)
    assert solved.converged
    owned_bp = thermo.bubble_point({"C7+": 1.0}, T=450.0).P

    assert default_bp is not None and owned_bp is not None
    assert owned_bp != pytest.approx(default_bp)
    assert owned_bp < default_bp  # the heavier cut (higher Tb) is less volatile
