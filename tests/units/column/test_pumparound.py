"""Fixed pumparounds (spec S0-1 feature 1).

The acceptance identity: a pumparound with ``duty_W = 0`` and
``draw_stage == return_stage`` is exactly the column without it - equal
in/out at one stage is a no-op in every balance. The positive tests pin
the two operating modes (fixed return temperature, fixed cooler duty),
the reported loop state, and the overall material balance (a pumparound
is an internal loop: feed = distillate + bottoms regardless of it).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.spec import ColumnSpecError


def _base_params() -> dict[str, Any]:
    return {
        "n_stages": 16,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 8,
        "pressure_profile": 1.5e6,
        "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
    }


def _feed() -> dict[str, Any]:
    return {
        "T": 330.0,
        "P": 1.5e6,
        "molar_flow": 100.0,
        "composition": {"C3": 0.5, "iC4": 0.5},
    }


def _solve(thermo: Thermo, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
    unit = registry.create("unit", "column")
    feed = thermo.flash_pt(_feed()["composition"], 330.0, 1.5e6, 100.0)
    result = unit.solve({"feed": feed}, params, thermo)
    outlets = {
        name: (state.T, state.P, state.molar_flow, dict(state.composition))
        for name, state in result.outlets.items()
    }
    return outlets, result.info


def _without_pa(info: dict[str, float]) -> dict[str, float]:
    return {k: v for k, v in info.items() if not k.startswith("pa_")}


def _flatten(outlets: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for name, state in outlets.items():
        t, pr, flow, comp = state
        flat[f"{name}.T"], flat[f"{name}.P"], flat[f"{name}.F"] = t, pr, flow
        for cid, v in comp.items():
            flat[f"{name}.{cid}"] = v
    return flat


def test_zero_duty_identity_loop_equals_plain_column(thermo: Thermo) -> None:
    """Acceptance: duty_W = 0 with draw = return is the column without it (1e-10)."""
    pa = {
        "name": "identity",
        "draw_stage": 10,
        "return_stage": 10,
        "flow_mol_s": 25.0,
        "duty_W": 0.0,
    }
    plain_out, plain_info = _solve(thermo, _base_params())
    pa_out, pa_info = _solve(thermo, {**_base_params(), "pumparounds": [pa]})

    # Flat scalar compares: pytest.approx cannot repr nested tuple/dict outlets.
    for k, v in _flatten(plain_out).items():
        assert v == pytest.approx(_flatten(pa_out)[k], rel=1e-10), k
    for k, v in _without_pa(plain_info).items():
        assert v == pytest.approx(_without_pa(pa_info)[k], rel=1e-10), k
    assert pa_info["pa_identity_flow_mol_s"] == pytest.approx(25.0, abs=1e-10)
    assert pa_info["pa_identity_duty_W"] == pytest.approx(0.0, abs=1e-10)


def test_fixed_return_temperature_loop(thermo: Thermo) -> None:
    """A subcooled return (return_T_K below the draw T) converges and reports state."""
    pa = {
        "name": "mid_pa",
        "draw_stage": 12,
        "return_stage": 8,
        "flow_mol_s": 30.0,
        "return_T_K": 335.0,
    }
    outlets, info = _solve(thermo, {**_base_params(), "pumparounds": [pa]})
    assert info["pa_mid_pa_flow_mol_s"] == pytest.approx(30.0, abs=1e-8)
    assert info["pa_mid_pa_return_T_K"] == pytest.approx(335.0, abs=1e-8)
    # The cooler removes heat: the draw liquid is subcooled to the return T.
    assert info["pa_mid_pa_duty_W"] < 0.0
    assert info["pa_mid_pa_draw_T_K"] > 335.0
    # The loop is internal: the overall material balance is untouched.
    assert outlets["distillate"][2] + outlets["bottoms"][2] == pytest.approx(100.0, rel=1e-8)


def test_fixed_duty_loop_reports_return_temperature(thermo: Thermo) -> None:
    """A fixed cooler duty leaves the loop flow untouched and bisects the return T."""
    pa = {
        "name": "duty_pa",
        "draw_stage": 12,
        "return_stage": 8,
        "flow_mol_s": 30.0,
        "duty_W": -5.0e3,
    }
    _, info = _solve(thermo, {**_base_params(), "pumparounds": [pa]})

    assert info["pa_duty_pa_flow_mol_s"] == pytest.approx(30.0, abs=1e-8)
    assert info["pa_duty_pa_duty_W"] == pytest.approx(-5.0e3, rel=1e-8)
    # Subcooled below the draw: the return temperature sits under the draw T.
    assert info["pa_duty_pa_return_T_K"] < info["pa_duty_pa_draw_T_K"]


def test_return_above_draw_refused() -> None:
    """A pumparound returns cooled liquid at or above the draw, never below."""
    with pytest.raises(ColumnSpecError, match="return_stage"):
        _parse_only(
            {
                **_base_params(),
                "pumparounds": [{"draw_stage": 8, "return_stage": 12, "flow_mol_s": 25.0, "duty_W": -1.0e3}],
            }
        )


def test_positive_duty_refused() -> None:
    with pytest.raises(ColumnSpecError, match="<= 0"):
        _parse_only(
            {
                **_base_params(),
                "pumparounds": [{"draw_stage": 12, "return_stage": 8, "flow_mol_s": 25.0, "duty_W": 1.0e3}],
            }
        )


def test_both_fixed_variables_refused() -> None:
    with pytest.raises(ColumnSpecError, match="exactly one"):
        _parse_only(
            {
                **_base_params(),
                "pumparounds": [
                    {
                        "draw_stage": 12,
                        "return_stage": 8,
                        "flow_mol_s": 25.0,
                        "duty_W": -1.0e3,
                        "return_T_K": 310.0,
                    }
                ],
            }
        )


def _parse_only(params: dict[str, Any]) -> None:
    """Run just the param parsing (no solve) to assert typed refusals."""
    from ngdesign.units.column.spec import _parse_params

    _parse_params({**params, "feeds": [{**_feed(), "stage": 8}]}, None)
