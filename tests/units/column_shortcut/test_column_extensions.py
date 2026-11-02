"""Column extensions R2: heaters, a second feed port and a draw port on one MESH.

Independent checks: a stage-by-stage audit from the reported profile, and
reductions to the plain column (a zero-duty heater; one feed cut into two
identical streams on one stage).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.spec import ColumnSpecError
from ngdesign.units.column_shortcut.column_extensions import ColumnExtensions, ColumnExtensionsError
from tests.conftest import flash_feed
from tests.units.column.stage_audit import (
    energy_residuals,
    equilibrium_residuals,
    material_residuals,
    read_stages,
)

COMPS = ["C3", "iC4"]
FEED = {"T": 330.0, "P": 1.5e6, "molar_flow": 100.0, "composition": {"C3": 0.5, "iC4": 0.5}}


def _plain() -> dict[str, Any]:
    return {
        "n_stages": 16,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 8,
        "pressure_profile": 1.5e6,
        "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
    }


def test_all_extensions_stage_audit(thermo: Thermo) -> None:
    feeds, params = ColumnExtensions.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    res = ColumnExtensions().solve(inlets, params, thermo)
    d, b, s = res.outlets["distillate"], res.outlets["bottoms"], res.outlets["side_draw"]
    assert s.molar_flow == pytest.approx(8.0, rel=1e-9)
    assert d.molar_flow + b.molar_flow + s.molar_flow == pytest.approx(120.0, rel=1e-9)

    stages = read_stages(res.info, COMPS)
    audit_feeds = {8: [inlets["feed"]], 4: [inlets["feed_2"]]}
    draws: dict[int, list[tuple[bool, float]]] = {2: [(False, 8.0)]}
    # The pumparound enters as a draw at stage 12 and a same-composition return
    # at stage 8, so stage 12's draw and stage 8's return close the loop.
    pa = 30.0
    pa_state = thermo.flash_pt({c: stages[11].x[c] for c in COMPS}, stages[11].T, 1.5e6, pa)
    audit_with_pa = {**audit_feeds, 7: [pa_state]}
    reflux = res.info["reflux_ratio"] * d.molar_flow
    residuals = material_residuals(
        stages, COMPS, audit_with_pa, draws={**draws, 11: [(False, pa)]}, reflux=reflux
    )
    assert max(residuals) < 1e-5
    # Bound = the plain two-tear column's own floor, not a property of the
    # extensions: the M/H gate does not read the summation row, so stage T sits
    # up to 1.5 mol% (in y) off the bubble point on the plain 16-stage column
    # (measured 0.0148 at the kettle; 0.0141 with a pumparound; P1-13 territory).
    assert max(equilibrium_residuals(thermo, stages)) < 0.02
    assert res.info["heater_14_duty_W"] == 2.0e4


def test_heater_enters_the_overall_energy_balance(thermo: Thermo) -> None:
    feed = flash_feed(thermo, FEED)
    params = {**_plain(), "stage_heaters": [{"stage": 13, "duty_W": 3.0e4}]}
    res = registry.create("unit", "column").solve({"feed": feed}, params, thermo)
    h_in = feed.enthalpy * feed.molar_flow
    h_out = sum(s.enthalpy * s.molar_flow for s in res.outlets.values() if s.molar_flow)
    q = res.info["reboiler_duty_W"] - res.info["condenser_duty_W"] + 3.0e4
    assert h_in + q == pytest.approx(h_out, abs=1e-6)
    assert res.duty_W == pytest.approx(q)


def test_heater_closes_on_its_own_stage(thermo: Thermo) -> None:
    feed = flash_feed(thermo, FEED)
    params = {**_plain(), "stage_heaters": [{"stage": 13, "duty_W": 3.0e4}]}
    res = registry.create("unit", "column").solve({"feed": feed}, params, thermo)
    stages = read_stages(res.info, COMPS)
    feeds = {7: [feed]}
    with_duty = energy_residuals(thermo, stages, feeds, duties={12: 3.0e4}, skip=frozenset({0, 15}))
    without = energy_residuals(thermo, stages, feeds, skip=frozenset({0, 15}))
    assert max(with_duty) < 2e-3
    # Audit sensitivity: leaving the heater out must break exactly that stage.
    assert without[12] > 5.0 * max(with_duty)


def test_interreboiler_saves_kettle_duty(thermo: Thermo) -> None:
    """Heat added below the feed replaces kettle duty; the condenser barely moves."""
    feed = flash_feed(thermo, FEED)
    column = registry.create("unit", "column")
    base = column.solve({"feed": feed}, _plain(), thermo)
    heated = column.solve(
        {"feed": feed}, {**_plain(), "stage_heaters": [{"stage": 13, "duty_W": 3.0e4}]}, thermo
    )
    saved = base.info["reboiler_duty_W"] - heated.info["reboiler_duty_W"]
    assert saved == pytest.approx(3.0e4, rel=0.05)
    assert heated.info["condenser_duty_W"] == pytest.approx(base.info["condenser_duty_W"], rel=0.02)


def test_zero_duty_heater_is_the_plain_column(thermo: Thermo) -> None:
    feed = flash_feed(thermo, FEED)
    column = registry.create("unit", "column")
    plain = column.solve({"feed": feed}, _plain(), thermo)
    zero = column.solve({"feed": feed}, {**_plain(), "stage_heaters": [{"stage": 12, "duty_W": 0.0}]}, thermo)
    for key, value in plain.info.items():
        assert zero.info[key] == pytest.approx(value, rel=1e-9), key


def test_split_feed_reduces_to_one_feed(thermo: Thermo) -> None:
    """One feed cut in two identical streams on one stage is the plain column."""
    feed = flash_feed(thermo, FEED)
    half = flash_feed(thermo, {**FEED, "molar_flow": 50.0})
    params = {**_plain(), "feed_2_stage": 8}
    two = ColumnExtensions().solve({"feed": half, "feed_2": half}, params, thermo)
    one = registry.create("unit", "column").solve({"feed": feed}, _plain(), thermo)
    for j in range(16):
        assert two.info[f"stage_{j}_T_K"] == pytest.approx(one.info[f"stage_{j}_T_K"], abs=1e-4), j
    assert two.outlets["distillate"].composition["C3"] == pytest.approx(
        one.outlets["distillate"].composition["C3"], rel=1e-6
    )


@pytest.mark.parametrize(
    ("heaters", "match"),
    [
        ("x", "must be a list"),
        ([{"stage": 1, "duty_W": 1.0}], "condenser stage"),
        ([{"stage": 16, "duty_W": 1.0}], "reboiler stage"),
        ([{"stage": 5, "duty_W": "hot"}], "must be a number"),
        ([{"stage": 5, "duty_W": 1.0}, {"stage": 5, "duty_W": 2.0}], "duplicate stage"),
    ],
)
def test_heater_refusals(thermo: Thermo, heaters: Any, match: str) -> None:
    feed = flash_feed(thermo, FEED)
    with pytest.raises(ColumnSpecError, match=match):
        registry.create("unit", "column").solve(
            {"feed": feed}, {**_plain(), "stage_heaters": heaters}, thermo
        )


@pytest.mark.parametrize(
    "params",
    [
        {**_plain(), "unknown": 1},
        {**_plain(), "feed_2_stage": 4},
        {**_plain(), "side_draw": [{"stage": 3, "flow_mol_s": 1.0}]},
    ],
)
def test_adapter_refusals(thermo: Thermo, params: dict[str, Any]) -> None:
    with pytest.raises(ColumnExtensionsError):
        ColumnExtensions().solve({"feed": flash_feed(thermo, FEED)}, params, thermo)
