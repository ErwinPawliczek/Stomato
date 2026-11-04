"""crude_column R2 near the zero-overflash limit: a short Newton from the relaxation.

The catalogue example at 448 mol/s overhead (the limit is 448.72 mol/s,
overflash 1.13 mol/s). Before the relaxation's stage enthalpies were split
into an ideal-gas part exact in composition and a departure line, the
relaxation's AGO stripper ran a 130 K limit cycle for all 80 passes and the
graph Newton started at M ~ 1.0: 8 passes here (5 to 9 across 430-448 mol/s).
Measured since: the relaxation settles, the Newton starts at M ~ 1e-2 and
closes in 3 Jacobian passes plus the gate at every overhead from 430 to 448.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.units.column import specs
from ngdesign.units.refining.crude_column_r2 import CrudeColumnR2
from tests.conftest import flash_feed

pytestmark = [pytest.mark.timeout(600), pytest.mark.xdist_group("crude_column_r2")]

#: Overhead just short of the example's zero-overflash limit (448.72 mol/s).
_NEAR_LIMIT = 448.0
#: Newton passes (the gate pass included) the graph Newton may take: measured 4
#: after the fix at every overhead 430-448 mol/s, 8 here before it.
_PASS_BUDGET = 5
#: The relaxation start's exact M norm the Newton opens on: measured 8.5e-3
#: after the fix, 0.9999 before it.
_START_M = 0.1
_CLOSE = 1e-6


@pytest.fixture(scope="module")
def solved() -> tuple[dict[str, Any], Any, list[tuple[int, list[str]]]]:
    thermo = registry.create("thermo", "pr")
    feeds, params = CrudeColumnR2.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    newton: list[tuple[int, list[str]]] = []
    original = specs._graph_naphtali_sandholm

    def recorded(*args: Any, **kwargs: Any) -> Any:
        prof = args[2]
        try:
            return original(*args, **kwargs)
        finally:
            newton.append((prof.ns_passes, list(prof.ns_trace)))

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(specs, "_graph_naphtali_sandholm", recorded)
        result = CrudeColumnR2().solve(inlets, {**params, "distillate_rate_mol_s": _NEAR_LIMIT}, thermo)
    return inlets, result, newton


def test_near_limit_newton_starts_close_and_converges_in_budget(
    solved: tuple[dict[str, Any], Any, list[tuple[int, list[str]]]],
) -> None:
    _, _, newton = solved
    # One graph Newton: the relaxation-started solve, no fallback start.
    assert len(newton) == 1
    passes, trace = newton[0]
    assert passes <= _PASS_BUDGET, trace
    first_m = float(trace[0].split("exact M=", 1)[1].split()[0])
    assert first_m < _START_M, trace


def test_near_limit_closes_with_a_small_positive_overflash(
    solved: tuple[dict[str, Any], Any, list[tuple[int, list[str]]]],
) -> None:
    inlets, result, _ = solved
    assert result.outlets["overhead"].molar_flow == pytest.approx(_NEAR_LIMIT, rel=1e-9)
    assert 0.0 < result.info["overflash_mol_s"] < 2.0
    flow_in: dict[str, float] = {}
    for s in inlets.values():
        for c, n in s.component_flows().items():
            flow_in[c] = flow_in.get(c, 0.0) + n
    flow_out: dict[str, float] = {}
    for s in result.outlets.values():
        for c, n in s.component_flows().items():
            flow_out[c] = flow_out.get(c, 0.0) + n
    total = sum(flow_in.values())
    for c in set(flow_in) | set(flow_out):
        assert flow_out.get(c, 0.0) == pytest.approx(flow_in.get(c, 0.0), abs=_CLOSE * total), c
    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    condenser = result.info["condenser_duty_W"]
    assert h_in + result.duty_W == pytest.approx(h_out, abs=_CLOSE * abs(condenser))
    assert abs(result.info["closure_residual_W"]) < _CLOSE * abs(condenser)
