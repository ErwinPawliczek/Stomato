"""Spec P2-02: a unit that raises yields a partial SolvedFlowsheet, not an abort.

A three-unit chain whose middle unit raises: the raiser records one UnitError
(stage="solve", its exception type and message), the third unit is skipped with
upstream=True because its inlet never got a state, and the first unit's result is
present in the partial sheet (status "failed", converged False). Test-only unit
kinds are registered inside the test's fixture with unique names and removed
afterwards, so the locked balance oracle never sees them.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitResult, UnitSpec
from ngdesign.contracts.plugins import Thermo
from ngdesign.solver.sequential_modular import SequentialModular

#: The message the raising unit raises with; the UnitError must carry it verbatim.
BOOM_MESSAGE = "boom: two-phase inlet not accepted"

#: Test-only registry names, registered per test and popped afterwards.
PASS_KIND = "p2_passthrough"
BOOM_KIND = "p2_boom"


class _PassThrough:
    """Copies its single inlet to its single outlet."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out",)

    def solve(self, inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        return UnitResult(outlets={"out": inlets["inlet"].model_copy()})


class _Boom:
    """A plugin bug: raises instead of returning outlets."""

    inlet_ports = ("inlet",)
    outlet_ports = ("out",)

    def solve(self, inlets: dict[str, Any], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        raise RuntimeError(BOOM_MESSAGE)


@pytest.fixture()
def _test_units() -> Iterator[None]:
    registry.register("unit", PASS_KIND)(_PassThrough)
    registry.register("unit", BOOM_KIND)(_Boom)
    yield
    for name in (PASS_KIND, BOOM_KIND):
        registry._REGISTRY["unit"].pop(name, None)  # no public unregister


def _chain(kinds: list[str] | None = None) -> Flowsheet:
    """feed -> U-101 -> U-102 -> U-103 -> product; U-102 raises unless re-kinded."""
    used = kinds if kinds is not None else [PASS_KIND, BOOM_KIND, PASS_KIND]

    def port(unit: str, name: str) -> PortRef:
        return PortRef(unit=unit, port=name)

    return Flowsheet(
        name="partial",
        units=[
            UnitSpec(tag="U-101", kind=used[0]),
            UnitSpec(tag="U-102", kind=used[1]),
            UnitSpec(tag="U-103", kind=used[2]),
        ],
        streams=[
            StreamSpec(
                id="S-001",
                target=port("U-101", "inlet"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=100.0, composition={"C1": 1.0}),
            ),
            StreamSpec(id="S-002", source=port("U-101", "out"), target=port("U-102", "inlet")),
            StreamSpec(id="S-003", source=port("U-102", "out"), target=port("U-103", "inlet")),
            StreamSpec(id="S-004", source=port("U-103", "out")),
        ],
    )


def test_raising_unit_yields_partial_results(_test_units: None, thermo: Thermo) -> None:
    solved = SequentialModular().solve(_chain(), thermo)
    assert solved.status == "failed"
    assert solved.converged is False

    # Exactly two error records: the raiser and the skipped downstream unit.
    assert len(solved.errors) == 2
    raiser, skipped = solved.errors
    assert (raiser.tag, raiser.kind, raiser.stage) == ("U-102", BOOM_KIND, "solve")
    assert raiser.error_type == "RuntimeError"
    assert raiser.message == BOOM_MESSAGE
    assert raiser.upstream is False
    assert (skipped.tag, skipped.stage) == ("U-103", "solve")
    assert skipped.upstream is True
    assert skipped.error_type == ""

    # The first unit solved normally; the raiser's outlets are unset; the third
    # unit was skipped, so it has no result. Present streams: the feed and the
    # first unit's outlet - both S-003 (the raiser's outlet) and S-004 (the
    # skipped unit's outlet) are left unset, which is exactly why U-103 skipped.
    assert "U-101" in solved.units
    assert "U-103" not in solved.units
    assert set(solved.streams) == {"S-001", "S-002"}
    assert solved.streams["S-001"].molar_flow == pytest.approx(100.0)

    # History: the chain is three singleton SCCs, one record each in execution
    # order. U-101 ran cleanly; U-102 failed outright; U-103 could not run
    # (blocked inlet), so its block is not converged either even though the
    # skip itself is not a failure in the status derivation.
    assert [b.units for b in solved.history] == [["U-101"], ["U-102"], ["U-103"]]
    assert [b.converged for b in solved.history] == [True, False, False]
    assert all(b.tears == [] and b.iterations == 1 and b.records == [] for b in solved.history)


def test_healthy_chain_stays_clean(_test_units: None, thermo: Thermo) -> None:
    """Behaviour-preserving for converging flowsheets: no errors, status derived."""
    solved = SequentialModular().solve(_chain(kinds=[PASS_KIND, PASS_KIND, PASS_KIND]), thermo)
    assert solved.status == "converged"
    assert solved.converged is True
    assert solved.errors == []
    assert set(solved.units) == {"U-101", "U-102", "U-103"}
    assert set(solved.streams) == {"S-001", "S-002", "S-003", "S-004"}
