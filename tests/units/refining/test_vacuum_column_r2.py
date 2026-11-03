"""Vacuum column R2: zero-tear MESH with a top pumparound and a VGO draw.

Every check reads the result and fresh thermo calls only: whole-unit
component and energy closure (the pumparound cooler is the only duty), the
pumparound's own enthalpy balance, the stage fugacity equalities, and the
fractionation (overhead lighter than VGO lighter than bottoms). Measured
~2.5 s per solve serial.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import component_record
from ngdesign.units.refining._cuts import RefiningSpecError
from ngdesign.units.refining.vacuum_column_r2 import VacuumColumnR2
from tests.conftest import flash_feed


def _feed(thermo: Thermo) -> StreamState:
    feeds, _ = VacuumColumnR2.example_case()
    return flash_feed(thermo, feeds["feed_in"])


@pytest.fixture(scope="module")
def solved(thermo: Thermo) -> tuple[StreamState, UnitResult]:
    feed = _feed(thermo)
    _, params = VacuumColumnR2.example_case()
    return feed, VacuumColumnR2().solve({"feed_in": feed}, params, thermo)


def test_closes_components_and_energy(solved: tuple[StreamState, UnitResult]) -> None:
    feed, res = solved
    out = list(res.outlets.values())
    for cid, frac in feed.composition.items():
        n_out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in out)
        assert abs(feed.molar_flow * frac - n_out) <= 1e-9 * feed.molar_flow, cid
    h_out = sum(s.molar_flow * s.enthalpy for s in out)
    assert abs(feed.molar_flow * feed.enthalpy + res.duty_W - h_out) <= 1e-9 * abs(h_out)
    assert res.duty_W == pytest.approx(res.info["pa_duty_W"], rel=1e-6)
    assert res.duty_W < 0.0


def test_pumparound_cooler_balance(solved: tuple[StreamState, UnitResult], thermo: Thermo) -> None:
    """The cooler duty is the drawn liquid's enthalpy drop to the 450 K return,
    recomputed from single-phase builds at the reported draw state."""
    _, res = solved
    info = res.info
    comps = sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_1_x_"))
    x = {c: info[f"stage_1_x_{c}"] for c in comps if info[f"stage_1_x_{c}"] > 0.0}
    p = info["stage_1_P_Pa"]
    h_draw = thermo.phase_props(x, info["pa_draw_T_K"], p, PhaseKind.HC_LIQUID).enthalpy
    h_ret = thermo.phase_props(x, 450.0, p, PhaseKind.HC_LIQUID).enthalpy
    assert info["pa_duty_W"] == pytest.approx(600.0 * (h_ret - h_draw), rel=1e-6)


def test_stage_fugacities_are_equal(solved: tuple[StreamState, UnitResult], thermo: Thermo) -> None:
    _, res = solved
    info = res.info
    comps = sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_0_x_"))
    worst = 0.0
    for j in range(6):
        t, p = info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"]
        x = {c: info[f"stage_{j}_x_{c}"] for c in comps}
        y = {c: info[f"stage_{j}_y_{c}"] for c in comps}
        lx = thermo.phase_props(x, t, p, PhaseKind.HC_LIQUID).ln_phi
        ly = thermo.phase_props(y, t, p, PhaseKind.VAPOR).ln_phi
        for c in comps:
            if x[c] > 1e-12 and y[c] > 1e-12:
                worst = max(worst, abs(math.log(x[c]) + lx[c] - math.log(y[c]) - ly[c]))
    assert worst < 1e-6


def _mean_tb(state: StreamState) -> float:
    return float(sum(frac * component_record(cid)["Tb"] for cid, frac in state.composition.items()))


def test_products_fractionate(solved: tuple[StreamState, UnitResult]) -> None:
    """Overhead lighter than VGO lighter than bottoms (mean normal boiling
    point), the VGO draw at its rate, the profile cooling upward to the
    pumparound."""
    _, res = solved
    over, vgo, bot = (res.outlets[p] for p in ("overhead", "vgo_out", "bottoms"))
    assert vgo.molar_flow == pytest.approx(300.0, rel=1e-9)
    assert _mean_tb(over) < _mean_tb(vgo) < _mean_tb(bot)
    temps = [res.info[f"stage_{j}_T_K"] for j in range(6)]
    assert temps == sorted(temps)
    assert 450.0 < temps[0]


@pytest.mark.parametrize(
    "over, match",
    [
        ({"vgo_stage": 1}, "vgo_stage"),
        ({"vgo_stage": 6}, "vgo_stage"),
        ({"n_stages": 2}, "n_stages"),
        ({"pumparound_return_T_K": -1.0}, "pumparound_return_T_K"),
        ({"wash_oil": 1.0}, "unknown parameter"),
    ],
)
def test_refusals(thermo: Thermo, over: dict[str, Any], match: str) -> None:
    _, params = VacuumColumnR2.example_case()
    with pytest.raises(RefiningSpecError, match=match):
        VacuumColumnR2().solve({"feed_in": _feed(thermo)}, {**params, **over}, thermo)


def test_registered_level_dispatch(thermo: Thermo) -> None:
    _, params = VacuumColumnR2.example_case()
    unit = registry.create("unit", "vacuum_column")
    res = unit.solve({"feed_in": _feed(thermo)}, {**params, "model": "R2"}, thermo)
    assert res.outlets["vgo_out"].molar_flow == pytest.approx(300.0, rel=1e-9)
