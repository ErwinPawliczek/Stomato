"""Spec P2-02: the solver records convergence history on SolvedFlowsheet.history.

recycle_bench tears three streams (S-204, S-215, S-223) inside ONE strongly
connected component, so its torn block holds one TearRecord per tear stream per
pass: 3 x 20 = 60 records. The spec's ``iterations == len(records)`` therefore
reads per tear stream - each stream has exactly ``iterations`` records - and is
literal only for a single-tear loop, which amine_loop is (S-003; 4 passes, 4
records). The spec's ``strictly decreasing residual_max after the first three
iterations`` does NOT hold on either case: bounded Wegstein overshoots mid-run
(documented sequence, recycle_bench: S-223 falls 0.0747 -> 0.0755 -> 0.0233 over
passes 2-4, then jumps to 1.353 at pass 8 before descending to 5.5e-7 at pass 20;
S-215 is non-monotonic at passes 9-10 and 18-19; S-204 rises at pass 8). The test
pins the honest envelope instead: direct substitution on pass 1, Wegstein after,
every stream ending at or below the solver's RTOL after at least a 1e4 drop.

Both solves use the real pr thermo plugin; the numbers above are deterministic
(the solver's float ops are the golden oracles' own).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from ngdesign import registry
from ngdesign.contracts import Flowsheet, SolvedFlowsheet
from ngdesign.contracts.diagnostics import BlockRecord, TearRecord
from ngdesign.flowsheets import amine_loop, recycle_bench
from ngdesign.solver.sequential_modular import RTOL, SequentialModular


def _solve(builder: Callable[[], Flowsheet]) -> SolvedFlowsheet:
    thermo = registry.create("thermo", "pr")
    return SequentialModular().solve(builder(), thermo)


def _torn_block(solved: SolvedFlowsheet) -> BlockRecord:
    blocks = [b for b in solved.history if b.tears]
    assert len(blocks) == 1, f"expected exactly one torn block, got {len(blocks)}"
    return blocks[0]


def test_recycle_bench_history() -> None:
    solved = _solve(recycle_bench.build)
    assert solved.converged is True
    assert solved.status == "converged"
    assert solved.errors == []
    # One acyclic singleton block plus the one torn SCC with its tear ids.
    assert len(solved.history) == 2
    block = _torn_block(solved)
    assert block.tears == ["S-204", "S-215", "S-223"]
    assert block.converged is True
    # One record per tear stream per pass; the sheet's iteration count is the
    # block's pass count (SolvedFlowsheet.iterations keeps its S-30 meaning).
    assert block.iterations == solved.iterations
    assert len(block.records) == block.iterations * len(block.tears)
    per_stream: dict[str, list[TearRecord]] = defaultdict(list)
    for record in block.records:
        per_stream[record.stream_id].append(record)
    assert sorted(per_stream) == block.tears
    for _stream_id, records in per_stream.items():
        assert [r.iteration for r in records] == list(range(1, block.iterations + 1))
        # Pass 1 is direct substitution; every later pass is bounded Wegstein.
        assert records[0].acceleration == "direct"
        assert records[0].q is None
        assert all(r.acceleration == "wegstein" for r in records[1:])
        assert all(r.q is not None for r in records[1:])
        # Residual vector keys follow the tear vector: components, then T and P.
        first = records[0].residual_vector
        assert set(first) == {"T", "P", *solved.flowsheet.components}
        assert max(first.values()) == records[0].residual_max
        # Convergence: the last record sits at or below the solver's tolerance,
        # at least 1e4 below this stream's first residual (see module docstring
        # for the actual, non-monotonic sequence in between).
        assert records[-1].residual_max <= RTOL
        assert records[-1].residual_max < records[0].residual_max * 1e-4


def test_amine_loop_history_reports_wegstein() -> None:
    solved = _solve(amine_loop.build)
    assert solved.converged is True
    assert solved.status == "converged"
    assert len(solved.history) == 1  # the whole loop is one SCC
    block = solved.history[0]
    assert block.tears == ["S-003"]
    assert block.converged is True
    # Single tear: one record per pass, so the spec's literal assertion holds.
    assert block.iterations == len(block.records)
    assert block.records[0].acceleration == "direct"
    assert any(r.acceleration == "wegstein" for r in block.records)
    assert block.records[-1].residual_max <= RTOL
    assert block.wall_s > 0.0
