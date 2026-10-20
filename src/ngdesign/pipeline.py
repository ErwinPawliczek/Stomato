"""Deliverables pipeline: solved flowsheet -> sizers -> P&ID -> rules -> routing.

The single library owner of the S-35 deliverables chain (P0-03): the CLI, the
export and the API routes are callers. Everything here is a pure function of
its inputs — no I/O, no globals — so the same solved flowsheet produces the
same P&ID, routing and deliverables everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ngdesign import registry
from ngdesign.contracts import PID, PipingNetwork, SolvedFlowsheet
from ngdesign.contracts.plugins import PidRule
from ngdesign.pid_rules.builder import sizer_for
from ngdesign.pid_rules.psv_sizing import relief_basis

#: Rule fixed-point cap; matches the S-35 spec and the locked e2e oracle.
MAX_RULE_PASSES = 5

#: Heat-capacity ratio of the relieving vapour. The StreamState contract
#: does not carry it, so S-34 assigns it to the caller; same value the S-33
#: composition tests use.
DEFAULT_K_GAS = 1.24


def run_sizers(solved: SolvedFlowsheet) -> SolvedFlowsheet:
    """Run the registered sizer per unit kind and attach the datasheets.

    The builder adopts attached datasheets verbatim and falls back to its
    internal sizing when none is attached; running them here makes the
    sizing step an observable pipeline stage. Units without a sizer (the
    sample's jt_valve) are skipped and get the builder's default nozzles.
    Sizer errors propagate: callers stop rather than draw unsized equipment.
    """
    for spec in solved.flowsheet.units:
        if spec.tag in solved.datasheets:
            continue
        sizer = sizer_for(spec.kind)
        if sizer is not None:
            solved.datasheets[spec.tag] = sizer.size(spec.tag, solved, spec.params)
    return solved


def rule_set(solved: SolvedFlowsheet, *, k_gas: float) -> list[PidRule]:
    """Every registered P&ID rule, psv_sizing given the full relief basis."""
    rules: list[PidRule] = []
    for name in registry.available("pid_rule"):
        if name == "psv_sizing":
            rule: PidRule = registry.create("pid_rule", name, basis=relief_basis(solved, k_gas=k_gas))
        else:
            rule = registry.create("pid_rule", name)
        rules.append(rule)
    return rules


def apply_rules(pid: PID, rules: list[PidRule]) -> PID:
    """Apply every rule repeatedly to a fixed point, capped at MAX_RULE_PASSES."""
    for _ in range(MAX_RULE_PASSES):
        before = pid.model_dump()
        for rule in rules:
            pid = rule.apply(pid)
        if pid.model_dump() == before:
            break
    return pid


def build_pid(solved: SolvedFlowsheet, *, k_gas: float) -> PID:
    """Sizers -> S-33 builder -> every rule to a fixed point: the full P&ID."""
    sized = run_sizers(solved)
    pid = registry.create("pid_builder", "default").build(sized)
    return apply_rules(pid, rule_set(sized, k_gas=k_gas))


def route(pid: PID, layout: dict[str, Any]) -> PipingNetwork:
    """The S-21 orthogonal router over the built P&ID and the given placements."""
    net: PipingNetwork = registry.create("router", "orthogonal").route(pid, layout)
    return net


@dataclass(frozen=True)
class Deliverables:
    """The stages callers that need several of them compute once."""

    solved: SolvedFlowsheet
    pid: PID
    network: PipingNetwork


def deliverables(solved: SolvedFlowsheet, layout: dict[str, Any], *, k_gas: float) -> Deliverables:
    """Sizers -> P&ID (builder + rules) -> routing, computed in one pass."""
    pid = build_pid(solved, k_gas=k_gas)
    network = route(pid, layout)
    return Deliverables(solved=solved, pid=pid, network=network)
