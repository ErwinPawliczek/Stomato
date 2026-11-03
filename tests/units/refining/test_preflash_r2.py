"""Preflash column R2: a partial-condenser rectifier on the crude slate.

Every check reads the result and fresh thermo calls only: whole-unit
component and energy closure, each stage re-flashed to its own phases, and the
rectification itself (the vapour product lighter than the feed, more so with
more stages). Measured ~13 s per solve serial.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import component_record
from ngdesign.units.refining._cuts import RefiningSpecError
from ngdesign.units.refining.preflash_r2 import PreflashR2
from tests.conftest import flash_feed


def _feed(thermo: Thermo) -> StreamState:
    feeds, _ = PreflashR2.example_case()
    return flash_feed(thermo, feeds["feed_in"])


@pytest.fixture(scope="module")
def solved(thermo: Thermo) -> tuple[StreamState, UnitResult]:
    feed = _feed(thermo)
    _, params = PreflashR2.example_case()
    return feed, PreflashR2().solve({"feed_in": feed}, params, thermo)


def test_closes_components_and_energy(solved: tuple[StreamState, UnitResult]) -> None:
    feed, res = solved
    out = list(res.outlets.values())
    for cid, frac in feed.composition.items():
        n_out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in out)
        assert abs(feed.molar_flow * frac - n_out) <= 1e-9 * feed.molar_flow, cid
    h_out = sum(s.molar_flow * s.enthalpy for s in out)
    assert abs(feed.molar_flow * feed.enthalpy + res.duty_W - h_out) <= 1e-9 * abs(h_out)
    # No reboiler: the boundary closure and the condenser's stage balance agree
    # (the pooled liquid carries the package's second liquid - see the module).
    assert res.duty_W == pytest.approx(-res.info["condenser_duty_W"], rel=1e-7)


def test_vapour_product_meets_the_spec_at_its_dew_point(solved: tuple[StreamState, UnitResult]) -> None:
    _, res = solved
    vap, liq = res.outlets["vapor_out"], res.outlets["liquid_out"]
    assert vap.molar_flow == pytest.approx(150.0, rel=1e-9)
    assert vap.vapor_fraction == pytest.approx(1.0)
    assert liq.vapor_fraction == pytest.approx(0.0)
    assert vap.T == pytest.approx(res.info["stage_0_T_K"])
    assert liq.T == pytest.approx(res.info["stage_4_T_K"])


def test_stages_reflash_to_their_own_phases(solved: tuple[StreamState, UnitResult], thermo: Thermo) -> None:
    """Every stage's contents L x + V y, flashed at the stage (T, P), hand
    back the stage's own vapour and pooled liquid; the bottom stage carries
    the package's second (heavy-end) liquid, which the pooled formulation
    holds inside x."""
    _, res = solved
    info = res.info
    comps = sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_0_x_"))
    for j in range(5):
        liq, vap = info[f"stage_{j}_L_mol_s"], info[f"stage_{j}_V_mol_s"]
        x = {c: info[f"stage_{j}_x_{c}"] for c in comps}
        y = {c: info[f"stage_{j}_y_{c}"] for c in comps}
        z = {c: (liq * x[c] + vap * y[c]) / (liq + vap) for c in comps}
        state = thermo.flash_pt(
            {c: v for c, v in z.items() if v > 0.0}, info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"], 1.0
        )
        vapour = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
        liquids = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
        share = sum(p.mole_fraction for p in liquids)
        pooled = {c: sum(p.composition.get(c, 0.0) * p.mole_fraction for p in liquids) / share for c in comps}
        assert max(abs(vapour.composition.get(c, 0.0) - y[c]) for c in comps) < 1e-6, j
        assert max(abs(pooled[c] - x[c]) for c in comps) < 1e-6, j
        assert len(liquids) == (2 if j == 4 else 1), j


def _mean_tb(state: StreamState) -> float:
    return float(sum(frac * component_record(cid)["Tb"] for cid, frac in state.composition.items()))


def test_rectification_lightens_the_vapour(solved: tuple[StreamState, UnitResult], thermo: Thermo) -> None:
    """The column profile cools upward, the vapour boils lighter than the
    feed, and more trays at the same vapour rate lighten it further - what
    the R0 drum (one stage) cannot show."""
    feed, res = solved
    temps = [res.info[f"stage_{j}_T_K"] for j in range(5)]
    assert temps == sorted(temps)
    assert _mean_tb(res.outlets["vapor_out"]) < _mean_tb(feed)
    short = PreflashR2().solve({"feed_in": feed}, {"n_stages": 2, "distillate_rate_mol_s": 150.0}, thermo)
    assert _mean_tb(res.outlets["vapor_out"]) < _mean_tb(short.outlets["vapor_out"])


@pytest.mark.parametrize(
    "params, match",
    [
        ({"n_stages": 5, "distillate_rate_mol_s": 150.0, "condenser": "total"}, "unknown parameter"),
        ({"n_stages": 1, "distillate_rate_mol_s": 150.0}, "n_stages"),
        ({"n_stages": 5, "distillate_rate_mol_s": 1000.0}, "distillate_rate_mol_s"),
        ({"n_stages": 5}, "distillate_rate_mol_s"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    with pytest.raises(RefiningSpecError, match=match):
        PreflashR2().solve({"feed_in": _feed(thermo)}, params, thermo)


def test_registered_level_dispatch(thermo: Thermo) -> None:
    """The catalogue routes model R2 of the preflash row to this adapter."""
    _, params = PreflashR2.example_case()
    unit = registry.create("unit", "preflash")
    res = unit.solve({"feed_in": _feed(thermo)}, {**params, "model": "R2"}, thermo)
    assert res.outlets["vapor_out"].molar_flow == pytest.approx(150.0, rel=1e-9)
