"""Sour-gas amine loop: solve, convergence, determinism and balance proof.

The golden end-to-end amine case for the expansion spec's sour-gas train: one
lean-solvent recycle through the MDEA absorber and regenerator, converged by
the solver's existing tear + Wegstein machinery (no solver work in the amine
expansion). The solve takes seconds (one loop, five units), so the
end-to-end test declares its own timeout instead of relying on the suite
default.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Solver, Thermo
from ngdesign.flowsheets.amine_loop import build
from ngdesign.solver.sequential_modular import _condensation_topo, _pick_tears, _stream_edges

#: Loop closure at RTOL 1e-6 leaves a per-pass residual; 1e-5 relative covers
#: it with margin.
_BALANCE_RTOL = 1e-5
_BALANCE_ATOL = 1e-3  # mol/s

_FEEDS = ("S-001", "S-009", "S-010")
_PRODUCTS = ("S-002", "S-004", "S-008")


def test_amine_loop_is_a_single_cyclic_block() -> None:
    """The lean recycle must be one SCC with exactly one tear stream."""
    fs = build()
    tags = sorted(u.tag for u in fs.units)
    edges = _stream_edges(fs)
    blocks = _condensation_topo(tags, edges)
    cyclic = [b for b in blocks if _pick_tears(fs, set(b))]
    assert len(cyclic) == 1, f"expected exactly one cyclic block, got {len(cyclic)}"
    assert len(cyclic[0]) == 5
    assert _pick_tears(fs, set(cyclic[0])) == ["S-003"]


@pytest.mark.timeout(600)
def test_solve_converges_deterministically(thermo: Thermo) -> None:
    """The loop converges and a byte-identical double-run reproduces the solve."""
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)
    again = solver.solve(fs, thermo)

    assert solved.converged
    assert 0 < solved.iterations <= 100
    assert again == solved


@pytest.mark.timeout(600)
def test_loop_component_balances_close(thermo: Thermo) -> None:
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)

    components = set(solved.streams["S-001"].composition)
    for comp in components:
        feed_total = sum(
            solved.streams[sid].composition.get(comp, 0.0) * solved.streams[sid].molar_flow for sid in _FEEDS
        )
        product_total = sum(
            solved.streams[sid].composition.get(comp, 0.0) * solved.streams[sid].molar_flow
            for sid in _PRODUCTS
        )
        assert product_total == pytest.approx(feed_total, rel=_BALANCE_RTOL, abs=_BALANCE_ATOL), comp


@pytest.mark.timeout(600)
def test_treated_gas_meets_pipeline_specs(thermo: Thermo) -> None:
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)
    gas = solved.streams["S-002"]

    assert gas.composition["CO2"] * 100.0 == pytest.approx(2.0, rel=1e-3)
    assert gas.composition["H2S"] * 1e6 <= 4.0 + 1e-6


@pytest.mark.timeout(600)
def test_recycle_lean_solvent_hits_the_regenerator_targets(thermo: Thermo) -> None:
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)
    lean = solved.streams["S-003"]
    z = lean.composition

    assert lean.molar_flow > 0.0
    assert z["CO2"] / z["MDEA"] == pytest.approx(0.005, rel=1e-3)
    assert z["H2S"] / z["MDEA"] == pytest.approx(0.002, rel=1e-3)


@pytest.mark.timeout(600)
def test_purge_exports_the_solvent_makeup(thermo: Thermo) -> None:
    """At the fixed point the purge removes exactly what the make-up adds."""
    fs = build()
    solver: Solver = registry.create("solver", "sequential_modular")
    solved = solver.solve(fs, thermo)
    makeup_mdea = solved.streams["S-009"].composition["MDEA"] * solved.streams["S-009"].molar_flow
    purge_mdea = solved.streams["S-008"].composition["MDEA"] * solved.streams["S-008"].molar_flow

    assert purge_mdea == pytest.approx(makeup_mdea, rel=1e-3)
