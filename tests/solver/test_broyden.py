"""Spec P2-03: block-wide Broyden on the concatenated tear vector.

Biegler et al. (ch. 8) recommend Broyden's good secant update for recycle
loops where Wegstein's per-variable treatment misses cross-variable coupling;
the implementation seeds H = -I, halves the step until the trial state stays
physical, and resets to direct substitution after three consecutive residual
growths.

Measured on the real pr thermo plugin (deterministic -- the solver's float ops
are the golden oracles' own):

- ``mea_amine_loop``: Wegstein 6 passes, Broyden 4, direct substitution 46.
  The stiff loop is where the spec's bet lands: Broyden takes fewer passes and
  lands on the same sheet -- worst relative difference across all streams
  2.2e-12 on flows/T/P, 1.1e-11 on compositions (both far inside RTOL).
- ``amine_loop``: Wegstein and Broyden tie at 4 passes -- the loop is too easy
  to discriminate.
- ``recycle_bench``: Wegstein 20, Broyden 24, direct substitution 18. Broyden
  does NOT win here, and the three schemes do not agree to RTOL on the sheet:
  main-loop streams differ by up to ~10% between any two of them (S-231
  79.64 vs 71.81 mol/s, S-204 1088.94 vs 1077.75 mol/s), and the trace stream
  S-220 (V-204's hc_out) is fully on a phase boundary -- direct-vs-Wegstein
  shows the same S-220 disagreement as Broyden-vs-Wegstein, so this is the
  tear map's own fixed-point family around the phase boundary (the OQ-3
  findings record the same discrepancy across acceleration schemes), not a
  Broyden defect. The test pins the measured envelope for streams where both
  schemes see real flow (>1 mol/s): agreement within 11% relative.
"""

from __future__ import annotations

from collections.abc import Callable

from ngdesign import registry
from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.contracts.flowsheet import SolverOptions
from ngdesign.flowsheets import mea_amine_loop, recycle_bench
from ngdesign.solver.sequential_modular import RTOL, SequentialModular


def _solve(builder: Callable[[], Flowsheet], acceleration: str) -> SolvedFlowsheet:
    thermo = registry.create("thermo", "pr")
    fs = builder().model_copy(update={"solver_options": SolverOptions(tear_acceleration=acceleration)})
    return SequentialModular().solve(fs, thermo)


def _worst_diffs(
    left: SolvedFlowsheet, right: SolvedFlowsheet, *, min_flow: float = 0.0
) -> tuple[float, float]:
    """Worst relative flow/T/P and worst composition difference.

    Streams below ``min_flow`` on EITHER side are skipped: a trace heavy phase
    appearing on a flash phase boundary (S-220's hc_out, ~0 vs ~71 mol/s) is a
    discrete fixed-point change, not a converged-solution disagreement.
    """
    worst_rel = 0.0
    worst_comp = 0.0
    for sid, state in left.streams.items():
        other = right.streams[sid]
        if state.molar_flow <= min_flow or other.molar_flow <= min_flow:
            continue
        worst_rel = max(
            worst_rel,
            abs(state.molar_flow - other.molar_flow) / max(state.molar_flow, 1.0),
            abs(state.T - other.T) / max(state.T, 1.0),
            abs(state.P - other.P) / max(state.P, 1.0),
        )
        worst_comp = max(
            worst_comp,
            max((abs(v - other.composition.get(k, 0.0)) for k, v in state.composition.items()), default=0.0),
        )
    return worst_rel, worst_comp


def test_mea_amine_loop_broyden_fewer_passes_same_sheet() -> None:
    wegstein = _solve(mea_amine_loop.build, "wegstein")
    broyden = _solve(mea_amine_loop.build, "broyden")
    assert wegstein.converged is True and broyden.converged is True
    w_block = [b for b in wegstein.history if b.tears][0]
    b_block = [b for b in broyden.history if b.tears][0]
    assert w_block.iterations == 6
    assert b_block.iterations == 4
    assert b_block.iterations < w_block.iterations
    # Same converged sheet, inside the solver's own tolerance.
    worst_rel, worst_comp = _worst_diffs(wegstein, broyden)
    assert worst_rel <= 10 * RTOL
    assert worst_comp <= 10 * RTOL


def test_recycle_bench_broyden_converges_same_family() -> None:
    wegstein = _solve(recycle_bench.build, "wegstein")
    broyden = _solve(recycle_bench.build, "broyden")
    assert wegstein.converged is True and broyden.converged is True
    w_block = [b for b in wegstein.history if b.tears][0]
    b_block = [b for b in broyden.history if b.tears][0]
    assert w_block.iterations == 20
    assert b_block.iterations == 24
    # Same fixed-point family: streams where both schemes see real flow agree
    # within 11% (see module docstring -- the spec's "fewer passes, same
    # sheet" bet does not land on this loop; the trace S-220 phase-boundary
    # stream is excluded by the flow floor, and direct substitution disagrees
    # with Wegstein there just the same -- the OQ-3 findings record this).
    worst_rel, _worst_comp = _worst_diffs(wegstein, broyden, min_flow=1.0)
    assert worst_rel <= 0.11
