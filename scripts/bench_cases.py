"""Benchmark cases: the slice solve and the golden thermo surfaces (C-7).

Each case mirrors an oracle surface so profile timings map onto tests:

- ``thermo.*`` cases mirror ``tests/golden/test_thermo.py`` (PR flash PT/PH/PS,
  two-phase material balance, free-water split, slice inlet three-phase).
- ``solver.slice_sequential_modular`` is the end-to-end slice solve driven by
  ``tests/e2e/test_slice.py`` and ``python -m ngdesign.cli slice``.

Pure case builders: no I/O, no globals mutated, no prints. The expensive
objects (thermo package, solver, flowsheet) are built once, outside the timed
callable, so the benchmarks time simulation work only.
"""

from __future__ import annotations

from collections.abc import Callable

from ngdesign import registry
from ngdesign.contracts.plugins import Solver, Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.flowsheets import slice as slice_fs

# Compositions and conditions lifted from the oracle tests they mirror.
_GAS_MIX = {"N2": 0.01, "CO2": 0.02, "C1": 0.85, "C2": 0.07, "C3": 0.03, "nC4": 0.02}
_TWO_PHASE = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}
_FREE_WATER = {"C1": 0.9, "H2O": 0.1}


def _ph_roundtrip(thermo: Thermo) -> Callable[[], StreamState]:
    def run() -> StreamState:
        a = thermo.flash_pt(dict(_GAS_MIX), 310.0, 4.0e6, 10.0)
        return thermo.flash_ph(dict(_GAS_MIX), 4.0e6, a.enthalpy, 10.0)

    return run


def _ps_roundtrip(thermo: Thermo) -> Callable[[], StreamState]:
    def run() -> StreamState:
        a = thermo.flash_pt(dict(_GAS_MIX), 310.0, 4.0e6, 10.0)
        return thermo.flash_ps(dict(_GAS_MIX), 4.0e6, a.entropy, 10.0)

    return run


def default_cases() -> dict[str, Callable[[], object]]:
    """Build the benchmark case set. Registration order is fixed: the pyperf
    worker processes re-execute this module and must register the same cases
    in the same order as the manager."""
    thermo: Thermo = registry.create("thermo", "pr")
    solver: Solver = registry.create("solver", "sequential_modular")
    flowsheet = slice_fs.build()
    return {
        # Golden thermo cases (tests/golden/test_thermo.py).
        "thermo.flash_pt_pure_c1": lambda: thermo.flash_pt({"C1": 1.0}, 300.0, 1.0e6, 1.0),
        "thermo.flash_pt_pure_co2": lambda: thermo.flash_pt({"CO2": 1.0}, 320.0, 5.0e6, 1.0),
        "thermo.flash_pt_gas_mix": lambda: thermo.flash_pt(dict(_GAS_MIX), 310.0, 4.0e6, 10.0),
        "thermo.flash_ph_roundtrip_gas": _ph_roundtrip(thermo),
        "thermo.flash_ps_roundtrip_gas": _ps_roundtrip(thermo),
        "thermo.flash_two_phase_c1_c3_nc5": lambda: thermo.flash_pt(dict(_TWO_PHASE), 300.0, 3.0e6, 1.0),
        "thermo.flash_free_water_c1_h2o": lambda: thermo.flash_pt(dict(_FREE_WATER), 300.0, 3.0e6, 1.0),
        "thermo.flash_slice_inlet_three_phase": lambda: thermo.flash_pt(
            dict(slice_fs.INLET_COMPOSITION), 293.15, 3.447e6, 1.0
        ),
        # End-to-end slice solve (tests/e2e/test_slice.py, ngdesign.cli slice).
        "solver.slice_sequential_modular": lambda: solver.solve(flowsheet, thermo),
    }
