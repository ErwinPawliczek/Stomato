"""Total-condenser outlet state of the rigorous column (R2).

A total condenser returns reflux and distillate as saturated liquid at the
condenser pressure, and its duty condenses the stage-1 vapour to that liquid
(Seader, Henley & Roper, Separation Process Principles 3rd ed., §10.3). The
distillate used to be flashed at the vapour-fraction-0.5 seed crossing
(``_ThermoBox.bubble_temperature``), leaving it half vapour.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, solve_column_full
from tests.conftest import flash_feed

Solved = tuple[Thermo, UnitResult, dict[str, StreamState]]


@pytest.fixture(scope="module")
def solved(thermo_module: Thermo) -> Solved:
    feeds, params = Column.example_case()
    inlets = {port: flash_feed(thermo_module, f) for port, f in feeds.items()}
    res, _ = solve_column_full(inlets, params, thermo_module)
    return thermo_module, res, inlets


@pytest.fixture(scope="module")
def thermo_module() -> Thermo:
    names = registry.available("thermo")
    if "pr" not in names:
        pytest.skip("no Peng-Robinson package registered")
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def test_distillate_is_saturated_liquid_at_its_bubble_point(solved: Solved) -> None:
    thermo, res, _ = solved
    d = res.outlets["distillate"]
    t_bub = thermo.bubble_point(dict(d.composition), P=d.P).T
    assert d.T == pytest.approx(t_bub, rel=1e-12)
    assert d.vapor_fraction <= 1e-9
    # Below the stage-1 (dew) temperature of the overhead vapour.
    assert d.T < res.info["stage_0_T_K"]


def test_condenser_duty_condenses_stage1_vapour_to_saturated_liquid(solved: Solved) -> None:
    thermo, res, _ = solved
    info = res.info
    d = res.outlets["distillate"]
    y0 = {k.removeprefix("stage_0_y_"): v for k, v in info.items() if k.startswith("stage_0_y_")}
    total = sum(y0.values())
    y0 = {k: v / total for k, v in y0.items()}
    # The distillate IS the condensate composition.
    for cid, frac in y0.items():
        assert d.composition[cid] == pytest.approx(frac, rel=1e-10, abs=1e-14)
    p = d.P
    h_v = thermo.phase_props(y0, info["stage_0_T_K"], p, PhaseKind.VAPOR).enthalpy
    h_l = thermo.phase_props(y0, thermo.bubble_point(y0, P=p).T, p, PhaseKind.HC_LIQUID).enthalpy
    expected = info["stage_0_V_mol_s"] * (h_v - h_l)
    assert info["condenser_duty_W"] == pytest.approx(expected, rel=1e-8)
    # The saturated-liquid enthalpy is the distillate's own.
    assert d.enthalpy == pytest.approx(h_l, rel=1e-8)


def test_component_and_energy_closure(solved: Solved) -> None:
    _, res, inlets = solved
    feed = inlets["feed"]
    outs = [res.outlets["distillate"], res.outlets["bottoms"], res.outlets["side_draw"]]
    for cid, z in feed.composition.items():
        n_in = feed.molar_flow * z
        n_out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in outs)
        assert abs(n_out - n_in) <= 1e-8 * feed.molar_flow
    h_in = feed.molar_flow * feed.enthalpy
    h_out = sum(s.molar_flow * s.enthalpy for s in outs)
    scale = max(abs(h_in), abs(h_out), res.info["reboiler_duty_W"])
    assert abs(h_in + res.duty_W - h_out) <= 1e-8 * scale
    assert res.duty_W == pytest.approx(res.info["reboiler_duty_W"] - res.info["condenser_duty_W"], rel=1e-12)
