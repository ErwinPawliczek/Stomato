"""``initialization: relaxation`` - the wide-boiling cold start (relaxation.py).

The relaxation only replaces the cold start: the mesh is converged by the same
Newton machinery onto the same exact gate. So a column both starts converge
must land on the same MESH root, and a wide-boiling column the standard start
cannot reach must close its balances and its fugacity equalities from the
reported profile alone (fresh thermo calls only).

Measured serial wall times (this machine): C3/iC4 example 5.5 s (standard
2.3 s), vacuum wash column 3.0 s.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import (
    Column,
    ColumnSpecError,
    _build_column,
    _parse_params,
    _solve_mesh,
    _ThermoBox,
)
from ngdesign.units.column.inside_out import _Profile
from ngdesign.units.column.spec import _SPEC_TOL
from ngdesign.units.refining.vacuum_column import VacuumColumn


def _example(thermo: Thermo) -> tuple[StreamState, dict[str, Any]]:
    feeds, params = Column.example_case()
    f = feeds["feed"]
    return thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]), params


def _mesh(thermo: Thermo, feed: StreamState, params: dict[str, Any], tears: tuple[float, float]) -> _Profile:
    port = {"T": feed.T, "P": feed.P, "molar_flow": feed.molar_flow, "composition": dict(feed.composition)}
    parsed = _parse_params(params, port)
    tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
    return _solve_mesh(_build_column(parsed, tb), tb, tears[0], tears[1], None)


def test_relaxation_lands_on_the_standard_root(thermo: Thermo) -> None:
    """The 16-stage C3/iC4 example at fixed tears (reflux 112.5, boilup 150
    mol/s): both cold starts converge the mesh onto one root."""
    feed, params = _example(thermo)
    std = _mesh(thermo, feed, params, (112.5, 150.0))
    rel = _mesh(thermo, feed, {**params, "initialization": "relaxation"}, (112.5, 150.0))
    assert rel.d == pytest.approx(std.d, rel=1e-7)
    for j in range(16):
        assert rel.T[j] == pytest.approx(std.T[j], abs=1e-5)
        assert rel.V[j] == pytest.approx(std.V[j], rel=1e-6)
        for cid, frac in std.x[j].items():
            assert rel.x[j][cid] == pytest.approx(frac, rel=1e-5, abs=1e-10)


def test_relaxation_meets_the_example_specs(thermo: Thermo) -> None:
    """Through the spec loop: the relaxation start meets the example's
    reflux-ratio and distillate specs (the secant starts its boilup at the
    constant-molar-overflow estimate, so it stops at another point inside
    the spec tolerance than the standard start)."""
    feed, params = _example(thermo)
    rel = Column().solve({"feed": feed}, {**params, "initialization": "relaxation"}, thermo)
    assert rel.info["distillate_mol_s"] == pytest.approx(45.0, rel=_SPEC_TOL)
    assert rel.info["reflux_ratio"] == pytest.approx(2.5, rel=_SPEC_TOL)


@pytest.mark.parametrize(
    "extra, match",
    [
        ({"initialization": "fast"}, "initialization must be one of"),
        ({"initialization": "relaxation", "pool_liquids": True}, "pool_liquids"),
    ],
)
def test_relaxation_refusals(thermo: Thermo, extra: dict[str, Any], match: str) -> None:
    feed, params = _example(thermo)
    with pytest.raises(ColumnSpecError, match=match):
        Column().solve({"feed": feed}, {**params, **extra}, thermo)


def _vacuum(thermo: Thermo) -> tuple[StreamState, dict[str, Any], dict[str, Any]]:
    feeds, _ = VacuumColumn.example_case()
    f = feeds["feed_in"]
    feed = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    wash = {"stage": 1, "T": 450.0, "P": f["P"], "molar_flow": 100.0, "composition": f["composition"]}
    params = {
        "n_stages": 6,
        "condenser": "none",
        "reboiler": "none",
        "feed_stage": 6,
        "pressure_profile": f["P"],
        "feeds": [wash],
        "initialization": "relaxation",
    }
    return feed, params, wash


def _fugacity_gap(result: UnitResult, thermo: Thermo) -> float:
    info = result.info
    comps = sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_0_x_"))
    worst = 0.0
    for j in range(int(info["n_stages"])):
        t, p = info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"]
        x = {c: info[f"stage_{j}_x_{c}"] for c in comps}
        y = {c: info[f"stage_{j}_y_{c}"] for c in comps}
        lx = thermo.phase_props(x, t, p, PhaseKind.HC_LIQUID).ln_phi
        ly = thermo.phase_props(y, t, p, PhaseKind.VAPOR).ln_phi
        for c in comps:
            if x[c] > 1e-12 and y[c] > 1e-12:
                worst = max(worst, abs(math.log(x[c]) + lx[c] - math.log(y[c]) - ly[c]))
    return worst


def test_vacuum_wash_column_converges_from_relaxation(thermo: Thermo) -> None:
    """The measured wide-boiling failure: 6 stages, the 19-pseudo vacuum feed
    at 40 mmHg and a 450 K wash of the same oil on stage 1. The standard start
    stalls at M ~ 1.0 (65 s); the relaxation start converges. Checked from
    the result: whole-unit component and energy closure (the reported duty of
    a column without exchangers is the boundary residual) and the stage
    fugacity equalities."""
    feed, params, wash = _vacuum(thermo)
    res = Column().solve({"feed": feed}, params, thermo)
    wash_state = thermo.flash_pt(wash["composition"], wash["T"], wash["P"], wash["molar_flow"])
    inlets = [feed, wash_state]
    outlets = [res.outlets["distillate"], res.outlets["bottoms"]]
    total = sum(s.molar_flow for s in inlets)
    for cid in feed.composition:
        n_in = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in inlets)
        n_out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in outlets)
        assert abs(n_in - n_out) <= 1e-9 * total, cid
    h_in = sum(s.molar_flow * s.enthalpy for s in inlets)
    h_out = sum(s.molar_flow * s.enthalpy for s in outlets)
    assert abs(h_in + res.duty_W - h_out) <= 1e-9 * abs(h_in)
    assert abs(res.duty_W) <= 1e-4 * abs(h_in)  # no exchanger: the stage balances close
    assert _fugacity_gap(res, thermo) < 1e-6
    temps = [res.info[f"stage_{j}_T_K"] for j in range(6)]
    assert 450.0 < temps[0] < temps[-1] < feed.T + 1e-6


def test_registry_column_accepts_the_option(thermo: Thermo) -> None:
    """The option travels through the registered plugin (its level dispatch) untouched."""
    feed, params = _example(thermo)
    unit = registry.create("unit", "column")
    res = unit.solve({"feed": feed}, {**params, "initialization": "relaxation"}, thermo)
    assert res.info["distillate_mol_s"] == pytest.approx(45.0, rel=_SPEC_TOL)
