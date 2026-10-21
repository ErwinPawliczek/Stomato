"""Design-spec outer loop (spec P2-01)."""

import math

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet
from ngdesign.contracts.components import resolve_set
from ngdesign.contracts.flowsheet import SolvedFlowsheet
from ngdesign.contracts.specs import DesignSpec
from ngdesign.flowsheets import recycle_bench
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.solver.design_specs import solve_with_specs
from ngdesign.solver.sequential_modular import RTOL, SequentialModular, _tear_vector


def _spec(**kw: object) -> DesignSpec:
    base: dict[str, object] = {
        "id": "DS-001",
        "target": "S-003.T",
        "value": 390.0,
        "manipulated": "K-101.params.P_out",
        "lower": 6e6,
        "upper": 14e6,
    }
    return DesignSpec(**{**base, **kw})


def _fs(*specs: DesignSpec) -> Flowsheet:
    fs = slice_fs.build()
    return Flowsheet(**{**fs.model_dump(), "design_specs": [s.model_dump() for s in specs]})


def _solve(fs: Flowsheet) -> SolvedFlowsheet:
    thermo = registry.create("thermo", "pr")
    return solve_with_specs(fs, thermo, SequentialModular())


def test_single_spec_converges() -> None:
    solved = _solve(_fs(_spec()))
    r = solved.design_spec_results[0]
    assert r.converged
    assert abs(r.achieved - 390.0) <= 1e-4 * 390.0
    assert 6e6 <= r.manipulated_value <= 14e6
    assert r.iterations <= 12
    # the returned sheet carries the manipulated value its result reports
    assert solved.flowsheet.unit("K-101").params["P_out"] == r.manipulated_value
    assert abs(solved.streams["S-003"].T - 390.0) <= 1e-4 * 390.0


def test_unreachable_target_reports_closest() -> None:
    # 320 K sits below T(6 MPa) ~ 341 K: nothing inside the bounds reaches it.
    spec = _spec(id="DS-002", value=320.0, max_iterations=8)
    solved = _solve(_fs(spec))
    r = solved.design_spec_results[0]
    assert not r.converged
    assert abs(r.achieved - min(h[1] for h in r.history)) < 1e-9
    manipulated = [h[0] for h in r.history]
    assert min(manipulated) == pytest.approx(spec.lower)
    assert max(manipulated) == pytest.approx(spec.upper)


def test_two_specs_converge_with_broyden() -> None:
    s1 = _spec(id="DS-001")  # S-003.T -> 390 K via discharge pressure
    s2 = DesignSpec(  # S-001.vapor_fraction -> 0.984 via feed pressure
        id="DS-002",
        target="S-001.vapor_fraction",
        value=0.984,
        manipulated="S-001.feed.P",
        lower=2e6,
        upper=6e6,
    )
    solved = _solve(_fs(s1, s2))
    r1, r2 = solved.design_spec_results
    assert r1.converged
    assert r2.converged
    assert r1.iterations <= 20
    assert r2.iterations <= 20
    assert abs(solved.streams["S-001"].vapor_fraction - 0.984) <= 1e-4 * 0.984


def test_failed_inner_aborts_with_partial_result() -> None:
    # T 500 K needs P_out above 14 MPa (verified unreachable), and at 40 MPa the
    # compressor fails: P2-02's failure contract, seen through the outer loop.
    spec = _spec(id="DS-003", value=500.0, upper=40e6)
    solved = _solve(_fs(spec))
    assert solved.status == "failed"
    assert any(e.tag == "K-101" for e in solved.errors)
    r = solved.design_spec_results[0]
    assert not r.converged
    assert r.history  # the bracket end that solved is recorded
    assert math.isfinite(r.achieved)


def test_no_specs_delegates_unchanged() -> None:
    thermo = registry.create("thermo", "pr")
    fs = slice_fs.build()
    bare = SequentialModular().solve(fs, thermo)
    via_plugin = registry.create("solver", "sequential_modular").solve(fs, thermo)
    assert via_plugin == bare


def test_registry_name_runs_specs_automatically() -> None:
    thermo = registry.create("thermo", "pr")
    solved = registry.create("solver", "sequential_modular").solve(_fs(_spec()), thermo)
    assert solved.design_spec_results[0].converged


def test_warm_start_reproduces_the_same_converged_sheet() -> None:
    """Acyclic sheet: a warm start changes nothing (no tears to seed)."""
    thermo = registry.create("thermo", "pr")
    fs = slice_fs.build()
    first = SequentialModular().solve(fs, thermo)
    components = tuple(resolve_set(fs.components).ids)
    warm = {sid: _tear_vector(st, components) for sid, st in first.streams.items()}
    again = SequentialModular().solve(fs, thermo, warm_start=warm)
    assert again.converged
    assert again == first


def test_warm_start_skips_the_recycle_iterations() -> None:
    """Cyclic sheet: tears seeded from a converged solve are already converged.

    recycle_bench converges its one torn block in 20 passes from the mean-of-
    feeds guess; warm-started from that solve's tear vectors the block must
    accept on far fewer passes and land on the same streams within the solver's
    tolerance - this is the point of the design-spec outer loop's warm start.
    """
    thermo = registry.create("thermo", "pr")
    fs = recycle_bench.build()
    cold = SequentialModular().solve(fs, thermo)
    assert cold.converged
    components = tuple(resolve_set(fs.components).ids)
    warm = {sid: _tear_vector(st, components) for sid, st in cold.streams.items()}
    hot = SequentialModular().solve(fs, thermo, warm_start=warm)
    assert hot.converged
    assert hot.iterations < cold.iterations
    assert hot.iterations <= 3
    for sid, state in cold.streams.items():
        other = hot.streams[sid]
        assert other.T == pytest.approx(state.T, rel=10 * RTOL)
        assert other.P == pytest.approx(state.P, rel=10 * RTOL)
        assert other.molar_flow == pytest.approx(state.molar_flow, rel=10 * RTOL)


def test_deterministic_double_run() -> None:
    fs = _fs(_spec())
    assert _solve(fs) == _solve(fs)
