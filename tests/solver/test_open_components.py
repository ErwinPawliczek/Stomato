"""Real-unit recycle over an open slate, including a pseudo-component (spec P1-02).

Feed -> mixer -> splitter, with the splitter's second outlet torn back into the
mixer. The slate mixes a curated id (C1), a databank name (n-heptane) and a
registered pseudo (C7+) - exactly the mixed support the merged thermo constants
package has to flash. Component balance closure is the acceptance check: at
steady state the external product carries every fed component.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import (
    FeedSpec,
    Flowsheet,
    PortRef,
    SolvedFlowsheet,
    StreamSpec,
    UnitSpec,
)
from ngdesign.data import register_pseudo
from ngdesign.solver.sequential_modular import SequentialModular

_C7P_TB = 372.0
_C7P_SG = 0.73
_SLATE = ["C1", "n-heptane", "C7+"]
_COMPOSITION = {"C1": 0.5, "n-heptane": 0.3, "C7+": 0.2}
_FEED_FLOW = 100.0  # mol/s
_TRIM_FLOW = 10.0  # mol/s of pure C1 into inlet_3 (the mixer requires all three inlets)


def _expected_product_flows() -> dict[str, float]:
    """Steady-state component flows: both boundary feeds, recycle internal."""
    expected = {c: z * _FEED_FLOW for c, z in _COMPOSITION.items()}
    expected["C1"] += _TRIM_FLOW
    return expected


@pytest.fixture(scope="module", autouse=True)
def _pseudo() -> None:
    register_pseudo("C7+", "C7+ pseudo", Tb=_C7P_TB, sg=_C7P_SG)


def _flowsheet() -> Flowsheet:
    return Flowsheet(
        name="open-slate-recycle",
        units=[
            UnitSpec(tag="MIX-101", kind="mixer"),
            UnitSpec(tag="SPL-101", kind="splitter", params={"fractions": [0.6, 0.4]}),
        ],
        streams=[
            StreamSpec(
                id="S-001",
                target=PortRef(unit="MIX-101", port="inlet_1"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=_FEED_FLOW, composition=_COMPOSITION),
            ),
            StreamSpec(
                id="S-005",
                target=PortRef(unit="MIX-101", port="inlet_3"),
                feed=FeedSpec(T=300.0, P=1.0e6, molar_flow=10.0, composition={"C1": 1.0}),
            ),
            StreamSpec(
                id="S-002",
                source=PortRef(unit="MIX-101", port="outlet"),
                target=PortRef(unit="SPL-101", port="inlet"),
            ),
            StreamSpec(id="S-003", source=PortRef(unit="SPL-101", port="outlet_1")),
            StreamSpec(
                id="S-004",
                source=PortRef(unit="SPL-101", port="outlet_2"),
                target=PortRef(unit="MIX-101", port="inlet_2"),
            ),
        ],
        components=_SLATE,
    )


def test_pr_registered() -> None:
    assert "pr" in registry.available("thermo")


def test_recycle_with_pseudo_converges_and_closes_balance() -> None:
    thermo: Any = registry.create("thermo", "pr")
    solved: SolvedFlowsheet = SequentialModular().solve(_flowsheet(), thermo)

    assert solved.converged
    product = solved.streams["S-003"]
    assert product.molar_flow == pytest.approx(_FEED_FLOW + _TRIM_FLOW, rel=1e-6)

    product_flows = product.component_flows()
    for cid, flow in _expected_product_flows().items():
        assert product_flows[cid] == pytest.approx(flow, rel=1e-5), f"component {cid} not closed"

    # The recycle stream sees the mixed composition at the mixer outlet.
    recycle = solved.streams["S-004"]
    assert math.isclose(sum(recycle.composition.values()), 1.0, abs_tol=1e-9)
