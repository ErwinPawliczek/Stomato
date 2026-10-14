"""Recycle-heavy benchmark flowsheet: solve, convergence and balance proof (OQ-3).

The locked slice (``flowsheets/slice.py``) is acyclic, so the sequential-modular
solver's tear + Wegstein machinery never runs there. This companion case keeps
the slice feed basis and adds three recycle loops that merge into one 17-unit
strongly connected component; these tests prove it solves and converges with
the overall material balance intact.

The solve takes tens of seconds (three coupled loops at RTOL 1e-6), so the
end-to-end test declares its own timeout instead of relying on the suite
default.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import SolvedFlowsheet
from ngdesign.contracts.plugins import Solver, Thermo
from ngdesign.flowsheets.recycle_bench import build
from ngdesign.solver.sequential_modular import _condensation_topo, _pick_tears, _stream_edges

#: Recycle tear streams (loops A, B, C in the flowsheet docstring).
_RECYCLE_STREAMS = ("S-216", "S-223", "S-231")

#: Setpoint-anchored tear pressures the docstring's well-posedness rules require.
_ANCHORED_PRESSURES = {"S-216": 7.0e6, "S-223": 6.85e6, "S-231": 3.6e6}

#: Loop closure at RTOL 1e-6 leaves a per-pass residual, amplified by the
#: recirculation-to-feed ratio; 1e-5 relative covers it with margin.
_BALANCE_RTOL = 1e-5
_BALANCE_ATOL = 1e-3  # mol/s


def test_recycle_bench_is_a_single_cyclic_block() -> None:
    """The three recycles must merge into one SCC so tear iteration covers them."""
    fs = build()
    tags = sorted(u.tag for u in fs.units)
    edges = _stream_edges(fs)
    blocks = _condensation_topo(tags, edges)
    cyclic = [b for b in blocks if _pick_tears(fs, set(b))]
    assert len(cyclic) == 1, f"expected exactly one cyclic block, got {len(cyclic)}"
    assert len(cyclic[0]) == 17
    assert len(_pick_tears(fs, set(cyclic[0]))) == 3


@pytest.mark.timeout(600)
def test_recycle_bench_solve_converges(thermo: Thermo) -> None:
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)

    assert solved.converged
    assert 0 < solved.iterations <= 100

    for sid in _RECYCLE_STREAMS:
        state = solved.streams[sid]
        assert state.molar_flow > 0.0, f"recycle {sid} carries no flow"
        assert state.P == pytest.approx(_ANCHORED_PRESSURES[sid], rel=1e-12)

    # The letdown recirculation must reach the suction mixer as vapor: no
    # compressor may ever see an injected two-phase tear guess here.
    assert solved.streams["S-231"].vapor_fraction == pytest.approx(1.0)
    # The sales path delivers real gas.
    assert solved.streams["S-228"].molar_flow > 0.0


@pytest.mark.timeout(600)
def test_recycle_bench_material_balance(thermo: Thermo) -> None:
    """Feeds equal products, overall and per component, at convergence."""
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved: SolvedFlowsheet = solver.solve(fs, thermo)
    assert solved.converged

    feeds = [s for s in fs.streams if s.source is None]
    products = [s for s in fs.streams if s.target is None]
    assert len(feeds) == 3  # rich gas, lean TEG, make-up
    assert len(products) == 9

    def _flowed(sid: str) -> float:
        return solved.streams[sid].molar_flow

    feed_total = sum(_flowed(s.id) for s in feeds)
    product_total = sum(_flowed(s.id) for s in products)
    assert product_total == pytest.approx(feed_total, rel=_BALANCE_RTOL, abs=_BALANCE_ATOL)

    components = sorted({cid for s in fs.streams for cid in _composition_of(solved, s.id)})
    for cid in components:
        inflow = sum(_composition_of(solved, s.id).get(cid, 0.0) * _flowed(s.id) for s in feeds)
        outflow = sum(_composition_of(solved, s.id).get(cid, 0.0) * _flowed(s.id) for s in products)
        assert outflow == pytest.approx(inflow, rel=_BALANCE_RTOL, abs=_BALANCE_ATOL), cid


def _composition_of(solved: SolvedFlowsheet, sid: str) -> dict[str, float]:
    return solved.streams[sid].composition
