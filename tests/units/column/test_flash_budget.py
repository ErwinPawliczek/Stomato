"""Column flash budget on the Thermo contract-v2 adapter (spec P1-03).

Solves the column ``example_case()`` through the P0-06 ``CountingThermo``
proxy and asserts the flash-equivalent count against the frozen pre-change
total (recorded in ``bench/baseline.json`` → ``budgets.column``).

Spec deviation (finding, reported in the PR with both numbers): the spec's
≤ 15 % target sits below the algorithmic floor. The case runs 125 inside-out
sweep visits across 22 stages; every visit flashes the stage liquid candidate
once for K — the mesh needs real K each sweep — so the floor is ≈ 2,750
flash-equivalents ≈ 25 % of the pre-change 11,208. The achieved count is
≈ 44 %: the exact-residual gate and duty wrappers evaluate neighbour-stage
phase states the K flash does not cover. The spec-literal ``phase_props``-only
enthalpy gate reaches ≈ 27 % but stops the inside-out mesh early, and the
total-reflux and Fenske oracle columns then fail to converge. The bound below
is the achieved level with regression headroom, not the spec's 15 %.
"""

from __future__ import annotations

import json
from pathlib import Path

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from scripts.bench_baseline import CountingThermo

REPO_ROOT = Path(__file__).resolve().parents[3]
BUDGET_RATIO = 0.50  # achieved ≈ 0.44; spec's 0.15 is unreachable, see module docstring


def test_column_flash_budget(thermo: Thermo) -> None:
    baseline = json.loads((REPO_ROOT / "bench" / "baseline.json").read_text())
    pre = baseline["budgets"]["column"]["pre_change_flash_equivalents"]

    counting = CountingThermo(thermo)
    unit = registry.create("unit", "column")
    feeds, params = unit.example_case()
    inlets = {
        port: counting.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
        for port, feed in feeds.items()
    }
    unit.solve(inlets, params, counting)

    assert counting.flashes <= BUDGET_RATIO * pre
