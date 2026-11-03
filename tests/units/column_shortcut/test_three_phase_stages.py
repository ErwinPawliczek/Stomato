"""Three-phase stages R2: hand physics on the heterogeneous stages, and a full audit.

Oracles independent of the solver:
- isofugacity of the three reported phases on every heterogeneous stage, from
  single-phase ``phase_props`` builds, a path the column never takes;
- a stage-by-stage material and enthalpy audit from the reported profile, with
  fresh three-phase flashes for the pooled liquid;
- a dry feed makes no second liquid, so the unit is the plain column.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import ColumnConvergenceError
from ngdesign.units.column_shortcut.three_phase_stages import (
    ThreePhaseStages,
    ThreePhaseStagesError,
    split_report,
)
from tests.conftest import flash_feed
from tests.units.column.stage_audit import material_residuals, read_stages

COMPS = ["H2O", "nC6", "nC7"]


def _solved(thermo: Thermo) -> tuple[StreamState, Any]:
    feeds, params = ThreePhaseStages.example_case()
    feed = flash_feed(thermo, feeds["feed"])
    return feed, ThreePhaseStages().solve({"feed": feed}, params, thermo)


@pytest.fixture(name="solved", scope="module")
def solved_fixture() -> tuple[Thermo, StreamState, Any]:
    thermo: Thermo = registry.create("thermo", "pr")
    return (thermo, *_solved(thermo))


def test_free_water_stages_exist_and_vanish_toward_the_kettle(solved: Any) -> None:
    _, _, res = solved
    n_liquids = [res.info[f"stage_{j}_n_liquids"] for j in range(6)]
    assert n_liquids[0] == 2.0
    assert n_liquids[-1] == 1.0
    assert res.info["two_liquid_stages"] >= 2.0


def test_three_phases_are_isofugacious_on_heterogeneous_stages(solved: Any) -> None:
    """f_i^V = f_i^L1 (all i) and f_w^V = f_w^L2, from single-phase builds at the report."""
    thermo, _, res = solved
    checked = 0
    for j in range(6):
        if res.info[f"stage_{j}_n_liquids"] != 2.0:
            continue
        t, p = res.info[f"stage_{j}_T_K"], res.info[f"stage_{j}_P_Pa"]
        y = {c: res.info[f"stage_{j}_y_{c}"] for c in COMPS}
        x1 = {c: res.info[f"stage_{j}_x1_{c}"] for c in COMPS}
        x2 = {c: res.info[f"stage_{j}_x2_{c}"] for c in COMPS}
        hc, aq = (x1, x2) if x2["H2O"] > x1["H2O"] else (x2, x1)
        assert aq["H2O"] > 0.99  # the second liquid is the free water
        ln_v = thermo.phase_props(y, t, p, PhaseKind.VAPOR).ln_phi
        ln_hc = thermo.phase_props(hc, t, p, PhaseKind.HC_LIQUID).ln_phi
        ln_aq = thermo.phase_props({"H2O": 1.0}, t, p, PhaseKind.AQUEOUS).ln_phi
        for c in COMPS:
            assert math.log(y[c]) + ln_v[c] == pytest.approx(math.log(hc[c]) + ln_hc[c], abs=2e-3), (j, c)
        assert math.log(y["H2O"]) + ln_v["H2O"] == pytest.approx(ln_aq["H2O"], abs=2e-3), j
        checked += 1
    assert checked >= 2


def test_stage_audit(solved: Any) -> None:
    thermo, feed, res = solved
    stages = read_stages(res.info, COMPS)
    assert max(material_residuals(stages, COMPS, {0: [feed]})) < 1e-5

    hv: list[float] = []
    hl: list[float] = []
    for st in stages:
        total = st.L + st.V
        z = {c: (st.L * st.x[c] + st.V * st.y[c]) / total for c in COMPS}
        state = thermo.flash_pt(z, st.T, st.P, total)
        vap = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
        liquids = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
        share = sum(p.mole_fraction for p in liquids)
        # Pooled liquid composition from the flash, against the reported xbar.
        for c in COMPS:
            pooled = sum(p.composition.get(c, 0.0) * p.mole_fraction for p in liquids) / share
            assert pooled == pytest.approx(st.x[c], abs=2e-3), c
        hv.append(vap.enthalpy)
        hl.append(sum(p.enthalpy * p.mole_fraction for p in liquids) / share)
    for j in range(5):  # the kettle stage's balance defines its duty
        h_in = (stages[j + 1].V * hv[j + 1]) + (stages[j - 1].L * hl[j - 1] if j else feed.enthalpy * 100.0)
        h_out = stages[j].L * hl[j] + stages[j].V * hv[j]
        assert h_in == pytest.approx(h_out, rel=2e-3), j


def test_single_liquid_feed_is_the_plain_column(thermo: Thermo) -> None:
    """No second liquid on any stage: the pooled path IS the plain column."""
    feed = thermo.flash_pt({"nC4": 0.9, "iC4": 0.1}, 330.0, 1.0e6, 100.0)
    params = {
        "n_stages": 8,
        "condenser": "none",
        "reboiler": "kettle",
        "feed_stage": 1,
        "pressure_profile": 1.0e6,
        "specs": {"boilup_rate": 40.0},
    }
    res = ThreePhaseStages().solve({"feed": feed}, params, thermo)
    plain = registry.create("unit", "column").solve({"feed": feed}, params, thermo)
    assert res.info["two_liquid_stages"] == 0.0
    for j in range(8):
        assert res.info[f"stage_{j}_T_K"] == pytest.approx(plain.info[f"stage_{j}_T_K"], abs=0.01)


def test_gate_refuses_a_profile_off_equilibrium(solved: Any) -> None:
    thermo, _, res = solved
    bad = dict(res.info)
    bad["stage_0_y_nC6"] += 0.1
    bad["stage_0_y_nC7"] -= 0.1
    with pytest.raises(ColumnConvergenceError, match="not at phase equilibrium"):
        split_report(bad, COMPS, thermo)


def test_unknown_parameter_refused(thermo: Thermo) -> None:
    feeds, params = ThreePhaseStages.example_case()
    with pytest.raises(ThreePhaseStagesError):
        ThreePhaseStages().solve({"feed": flash_feed(thermo, feeds["feed"])}, {**params, "x": 1}, thermo)
