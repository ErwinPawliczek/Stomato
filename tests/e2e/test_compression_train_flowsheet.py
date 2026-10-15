"""Two-stage compression-train flowsheet: sequential-modular solve end to end.

The wave-2 train as a one-node flowsheet unit -- acyclic, one pass per unit,
no solver work. Determinism and discharge-pressure checks at the flowsheet
layer.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts.flowsheet import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.plugins import Solver, Thermo
from ngdesign.flowsheets.slice import INLET_COMPOSITION, MMSCFD_TO_MOL_S

_P_IN = 3.447e6
_P_DISCHARGE = 15.0e6


def _build() -> Flowsheet:
    dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
    total = sum(dry.values())
    composition = {cid: x / total for cid, x in dry.items()}
    return Flowsheet(
        name="compression_train_e2e",
        units=[
            UnitSpec(
                tag="K-100",
                kind="compression_train",
                params={"P_discharge": _P_DISCHARGE, "eta_isentropic": 0.75, "T_interstage_out": 322.15},
            ),
        ],
        streams=[
            StreamSpec(
                id="S-001",
                target=PortRef(unit="K-100", port="gas_in"),
                feed=FeedSpec(T=322.15, P=_P_IN, molar_flow=50 * MMSCFD_TO_MOL_S, composition=composition),
            ),
            StreamSpec(id="S-002", source=PortRef(unit="K-100", port="gas_out")),
        ],
    )


@pytest.mark.timeout(600)
def test_two_stage_flowsheet_solves_deterministically(thermo: Thermo) -> None:
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(_build(), thermo)
    again = solver.solve(_build(), thermo)

    assert solved.converged
    assert again == solved


@pytest.mark.timeout(600)
def test_two_stage_flowsheet_discharge_pressure_and_info(thermo: Thermo) -> None:
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(_build(), thermo)

    assert solved.streams["S-002"].P == pytest.approx(_P_DISCHARGE, rel=1e-6)
    unit_result = solved.units["K-100"]
    assert unit_result.info["stages"] == 2
    assert unit_result.info["stage_2_P_discharge"] == pytest.approx(_P_DISCHARGE, rel=1e-6)
    assert unit_result.power_W > 0
    assert unit_result.duty_W < 0  # the intercooler removes heat
