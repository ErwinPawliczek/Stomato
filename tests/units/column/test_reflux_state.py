"""The total-condenser reflux enters stage 1 at the condenser's outlet state.

A total condenser returns reflux and distillate as one saturated liquid at its
bubble point (Seader, Henley & Roper, Separation Process Principles 3rd ed.,
§10.3). The stage-1 energy balance used to take the reflux as a hypothetical
liquid at the stage-1 (dew) temperature - 2.1 K too hot on the example, so
stage 1 and the condenser balanced different liquids and the reported
reboiler duty absorbed the 34 kW gap. ``_reflux_state`` is now the one owner
of that liquid for every solver path, the duty and the distillate.

Independent checks from the reported result and fresh thermo calls only.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, _build_column, _parse_params, _seed_profile, solve_column_full
from ngdesign.units.column.inside_out import (
    _enthalpy_at,
    _equilibrium_vapour,
    _reflux_state,
    _refresh_model,
    _stage_equilibrium,
)
from ngdesign.units.column.thermo_adapter import _ThermoBox
from tests.conftest import flash_feed
from tests.units.column.test_s0_1c_strippers import _comps, _h, _stage

Solved = tuple[Thermo, UnitResult, dict[str, StreamState]]


@pytest.fixture(scope="module")
def pr() -> Thermo:
    if "pr" not in registry.available("thermo"):
        pytest.skip("no Peng-Robinson package registered")
    impl: Thermo = registry.create("thermo", "pr")
    return impl


@pytest.fixture(scope="module")
def solved(pr: Thermo) -> Solved:
    feeds, params = Column.example_case()
    inlets = {port: flash_feed(pr, f) for port, f in feeds.items()}
    res, _ = solve_column_full(inlets, params, pr)
    return pr, res, inlets


def _top(thermo: Thermo, res: UnitResult) -> dict[str, Any]:
    """Stage 1 and 2 states, the reflux (= distillate) state and their enthalpy flows."""
    info = res.info
    comps = _comps(info)
    s0, s1 = _stage(info, 0, comps), _stage(info, 1, comps)
    d = res.outlets["distillate"]
    l0 = info["reflux_ratio"] * info["distillate_mol_s"]
    return {
        "s0": s0,
        "d": d,
        "l0": l0,
        "hv0": s0["V"] * _h(thermo, s0["y"], s0["T"], s0["P"], PhaseKind.VAPOR),
        "hl0": s0["L"] * _h(thermo, s0["x"], s0["T"], s0["P"], PhaseKind.HC_LIQUID),
        "hv1": s1["V"] * _h(thermo, s1["y"], s1["T"], s1["P"], PhaseKind.VAPOR),
        "h_reflux": _h(thermo, dict(d.composition), d.T, d.P, PhaseKind.HC_LIQUID),
    }


def test_reflux_is_the_saturated_condensate(solved: Solved) -> None:
    """The liquid returned is the overhead vapour's composition at its bubble
    point (the package's), strictly below the stage-1 temperature."""
    thermo, res, _ = solved
    top = _top(thermo, res)
    s0, d = top["s0"], top["d"]
    total = sum(s0["y"].values())
    y0 = {c: v / total for c, v in s0["y"].items()}
    assert d.T == pytest.approx(thermo.bubble_point(y0, P=s0["P"]).T, rel=1e-12)
    assert d.T < s0["T"] - 1.0  # measured 2.04 K below the dew-point stage


def test_stage1_balance_closes_with_the_saturated_reflux(solved: Solved) -> None:
    """V_2 H_V2 + L_0 h_L(x_D, T_D) = V_1 H_V1 + L_1 h_L1 (measured 7.5e-9 of
    the scale; with the reflux at the stage-1 temperature it read 1.6e-2)."""
    thermo, res, _ = solved
    top = _top(thermo, res)
    h_in = top["hv1"] + top["l0"] * top["h_reflux"]
    h_out = top["hv0"] + top["hl0"]
    scale = max(abs(h_in), abs(h_out), res.info["condenser_duty_W"])
    assert abs(h_in - h_out) <= 1e-8 * scale


def test_condenser_balance_is_stage1s(solved: Solved) -> None:
    """The condenser condenses V_1 to the liquid stage 1 receives:
    Q_c = V_1 H_V1 - (L_0 + D) h_L(x_D, T_D), and the envelope around stage 1
    and the condenser closes with that Q_c."""
    thermo, res, _ = solved
    top = _top(thermo, res)
    info = res.info
    d = info["distillate_mol_s"]
    q_c = info["condenser_duty_W"]
    assert q_c == pytest.approx(top["hv0"] - (top["l0"] + d) * top["h_reflux"], rel=1e-8)
    envelope = top["hv1"] - top["hl0"] - d * top["h_reflux"] - q_c
    assert abs(envelope) <= 1e-8 * q_c


def test_overall_closure_and_kettle_duty(solved: Solved) -> None:
    """Whole column: F h_F + Q_r = D h_D + B h_B + Q_c, and the reported
    reboiler duty (closed over the boundary streams) is the kettle's own stage
    balance - nothing left for it to absorb."""
    thermo, res, inlets = solved
    info = res.info
    feed = inlets["feed"]
    d, b = res.outlets["distillate"], res.outlets["bottoms"]
    h_in = feed.molar_flow * feed.enthalpy
    h_out = d.molar_flow * d.enthalpy + b.molar_flow * b.enthalpy
    q_r, q_c = info["reboiler_duty_W"], info["condenser_duty_W"]
    assert abs(h_in + q_r - q_c - h_out) <= 1e-8 * max(abs(h_in), abs(h_out), q_r)
    comps = _comps(info)
    n = int(info["n_stages"])
    kettle, above = _stage(info, n - 1, comps), _stage(info, n - 2, comps)
    q_kettle = (
        kettle["V"] * _h(thermo, kettle["y"], kettle["T"], kettle["P"], PhaseKind.VAPOR)
        + kettle["L"] * _h(thermo, kettle["x"], kettle["T"], kettle["P"], PhaseKind.HC_LIQUID)
        - above["L"] * _h(thermo, above["x"], above["T"], above["P"], PhaseKind.HC_LIQUID)
    )
    assert q_r == pytest.approx(q_kettle, rel=1e-6)


def test_inner_model_reads_the_live_reflux_enthalpy(pr: Thermo) -> None:
    """The inside-out condensate line and the live residual (the Newton's and
    the gate's) evaluate one reflux state: at the profile the line was fitted
    on, h_cond(T_1 + cond_dt) is ``_reflux_state``'s enthalpy at the live
    y_1 = K_1 x_1, at its bubble point."""
    feeds, params = Column.example_case()
    feed = flash_feed(pr, feeds["feed"])
    parsed = _parse_params(
        params,
        {"T": feed.T, "P": feed.P, "molar_flow": feed.molar_flow, "composition": dict(feed.composition)},
    )
    tb = _ThermoBox(pr, min(parsed.pressures), max(parsed.pressures))
    col = _build_column(parsed, tb)
    prof = _seed_profile(col, tb, 315.0, 355.0)
    model = _refresh_model(col, tb, prof, None)
    k_stages, y_eq = _stage_equilibrium(col, tb, prof.l0, prof.x, prof.T, prof.V, list(prof.y))
    assert k_stages[0] is not None
    assert _equilibrium_vapour(col, k_stages[0], prof.x[0]) == y_eq[0]
    state = _reflux_state(col, tb, y_eq[0], prof.T[0])
    assert state.T == pytest.approx(pr.bubble_point(state.x, P=col.pressures[0]).T, rel=1e-12)
    assert model.h_cond is not None
    assert prof.T[0] + model.cond_dt == pytest.approx(state.T, rel=1e-12)
    assert _enthalpy_at(model.h_cond, prof.T[0] + model.cond_dt) == pytest.approx(state.h, rel=1e-12)
