"""Whole-unit energy closure for plain side-draw columns (PR #239 review item 1).

The reported duty set must satisfy, with enthalpies recomputed INDEPENDENTLY
from the thermo plugin over the reported boundary states,

    H_in + Q_reb - Q_cond - H_out = 0

to 1e-8 relative to the largest term, where ``H_out`` includes every side
draw. The pre-fix code left the draws out of the boundary stream table, so
their enthalpy was silently absorbed by ``reboiler_duty_W``.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import ColumnProducts, _solve_column_full


def _feed() -> dict[str, Any]:
    return {
        "T": 330.0,
        "P": 1.5e6,
        "molar_flow": 100.0,
        "composition": {"C3": 0.4, "iC4": 0.3, "nC4": 0.3},
    }


def _params(draws: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n_stages": 12,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 6,
        "pressure_profile": 1.5e6,
        "specs": {"reflux_ratio": 2.0, "distillate_rate": 35.0},
        "draws": draws,
    }


def _h_in(thermo: Thermo) -> float:
    feed = _feed()
    t: float = feed["T"]
    p: float = feed["P"]
    flow: float = feed["molar_flow"]
    state = thermo.flash_pt(dict(feed["composition"]), t, p, flow)
    return float(state.enthalpy) * flow


def _h_out(thermo: Thermo, states: list[StreamState]) -> float:
    h = 0.0
    for state in states:
        entry = thermo.flash_pt(dict(state.composition), state.T, state.P, state.molar_flow)
        h += float(entry.enthalpy) * state.molar_flow
    return h


def _assert_closed(thermo: Thermo, h_in: float, states: list[StreamState], info: dict[str, float]) -> None:
    h_out = _h_out(thermo, states)
    q_reb = info["reboiler_duty_W"]
    q_cond = info["condenser_duty_W"]
    residual = h_in + q_reb - q_cond - h_out
    scale = max(abs(h_in), abs(h_out), abs(q_reb), abs(q_cond), 1.0)
    assert abs(residual) <= 1e-8 * scale, f"energy closure off by {residual:.6g} W (scale {scale:.6g})"


def test_whole_unit_energy_closure_with_side_draw(thermo: Thermo) -> None:
    """A drawn column closes on the whole unit: the draw is a boundary outlet."""
    unit = registry.create("unit", "column")
    feed = _feed()
    feed_state = thermo.flash_pt(dict(feed["composition"]), feed["T"], feed["P"], feed["molar_flow"])
    result: UnitResult = unit.solve(
        {"feed": feed_state},
        _params([{"stage": 4, "phase": "liquid", "flow_mol_s": 10.0}]),
        thermo,
    )

    _assert_closed(thermo, _h_in(thermo), list(result.outlets.values()), result.info)

    # Material balance over the same boundary (no pumparound, no strippers).
    total_out = sum(state.molar_flow for state in result.outlets.values())
    assert total_out == pytest.approx(feed["molar_flow"], rel=1e-8)

    # No pumparound: the net unit duty is Q_reb - Q_cond exactly.
    assert result.duty_W == pytest.approx(result.info["reboiler_duty_W"] - result.info["condenser_duty_W"])


def test_whole_unit_closure_with_named_extra_draws(thermo: Thermo) -> None:
    """Named extra draws are boundary outlets of the full product set too."""
    feed = _feed()
    feed_state = thermo.flash_pt(dict(feed["composition"]), feed["T"], feed["P"], feed["molar_flow"])
    products: ColumnProducts = _solve_column_full(
        {"feed": feed_state},
        _params(
            [
                {"stage": 4, "phase": "liquid", "flow_mol_s": 10.0},
                {"stage": 9, "phase": "liquid", "flow_mol_s": 5.0, "name": "kero"},
            ]
        ),
        thermo,
    )

    states = [products.distillate, products.bottoms, products.side_draw, *products.internal.values()]
    _assert_closed(thermo, _h_in(thermo), states, products.info)

    # Material balance: feed = D + B + both draws (no strippers, no decant).
    total_out = (
        products.distillate.molar_flow
        + products.bottoms.molar_flow
        + products.side_draw.molar_flow
        + sum(s.molar_flow for s in products.internal.values())
    )
    assert total_out == pytest.approx(feed["molar_flow"], rel=1e-8)
