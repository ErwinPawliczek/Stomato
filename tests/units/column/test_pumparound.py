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
from ngdesign.units.column.spec import ColumnConvergenceError, ColumnSpecError


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


def test_return_below_draw_refused() -> None:
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


def test_condenser_stage_pumparound_refused() -> None:
    """A pumparound draw or return on the condenser stage is refused (PR #238 review item 2).

    The condenser's own stage balance defines the condenser duty and carries
    no pumparound terms, so a loop touching it would report wrong duties.
    Both endpoints are checked.
    """
    for kwargs in ({"draw_stage": 1, "return_stage": 5}, {"draw_stage": 5, "return_stage": 1}):
        with pytest.raises(ColumnSpecError, match="condenser stage"):
            _parse_only(
                {
                    **_base_params(),
                    "pumparounds": [{"name": "top", **kwargs, "flow_mol_s": 25.0, "duty_W": -1.0e3}],
                }
            )


def test_reboiler_stage_pumparound_refused() -> None:
    """A pumparound draw or return on the kettle-reboiler stage is refused (PR #238 review item 2)."""
    for kwargs in ({"draw_stage": 16, "return_stage": 8}, {"draw_stage": 8, "return_stage": 16}):
        with pytest.raises(ColumnSpecError, match="reboiler stage"):
            _parse_only(
                {
                    **_base_params(),
                    "pumparounds": [{"name": "bot", **kwargs, "flow_mol_s": 25.0, "duty_W": -1.0e3}],
                }
            )


def test_unimplemented_feature_keys_refused() -> None:
    """S0-1 features 2 and 3 refuse their keys instead of ignoring them (PR #238 review item 7)."""
    with pytest.raises(ColumnSpecError, match="side_strippers.*not implemented"):
        _parse_only({**_base_params(), "side_strippers": []})
    with pytest.raises(ColumnSpecError, match="condenser_water_decant.*not implemented"):
        _parse_only({**_base_params(), "condenser_water_decant": True})


def test_pumparound_flow_exceeding_internal_liquid_refused() -> None:
    """A pumparound flow far above the column's internal traffic fails loudly (PR #238 review item 4).

    500 mol/s recirculated through a column whose internal liquid is tens of
    mol/s cannot run: the fixed-return-temperature loop pulls the draw stage
    below its bubble regime and the solve raises a typed error instead of
    returning a column with a silently clamped profile.
    """
    unit = registry.create("unit", "column")
    thermo = registry.create("thermo", "pr")
    feed = thermo.flash_pt(_feed()["composition"], 330.0, 1.5e6, 100.0)
    with pytest.raises((ColumnSpecError, ColumnConvergenceError)):
        unit.solve(
            {"feed": feed},
            {
                **_base_params(),
                "pumparounds": [
                    {
                        "name": "huge",
                        "draw_stage": 12,
                        "return_stage": 8,
                        "flow_mol_s": 500.0,
                        "return_T_K": 335.0,
                    }
                ],
            },
            thermo,
        )


# ---------------------------------------------------------------------------
# Whole-unit energy closure (PR #238 review item 1)
# ---------------------------------------------------------------------------
#
# The reported duty set must satisfy, with enthalpies recomputed
# INDEPENDENTLY from the thermo plugin over the reported boundary states,
#
#     H_in + Q_reb + Sum(Q_pumparound) - Q_cond - H_out = 0
#
# to 1e-8 relative to the largest term. The pre-fix code defined the
# reboiler duty as that closure value WITHOUT subtracting the pumparound
# cooler duties, so any pumparound column failed this identity by exactly
# the pumparound heat.


def _closure_residual(
    thermo: Thermo, result: Any, feed_dict: dict[str, Any]
) -> tuple[float, float]:
    """Recompute the boundary enthalpies independently and return (residual, scale)."""
    h_in = (
        thermo.flash_pt(
            dict(feed_dict["composition"]), feed_dict["T"], feed_dict["P"], feed_dict["molar_flow"]
        ).enthalpy
        * feed_dict["molar_flow"]
    )
    h_out = 0.0
    for state in result.outlets.values():
        if state.molar_flow:
            h_out += (
                thermo.flash_pt(dict(state.composition), state.T, state.P, state.molar_flow).enthalpy
                * state.molar_flow
            )
    q_reb = result.info["reboiler_duty_W"]
    q_cond = result.info["condenser_duty_W"]
    q_pa = sum(v for k, v in result.info.items() if k.startswith("pa_") and k.endswith("_duty_W"))
    residual = h_in + q_reb + q_pa - q_cond - h_out
    scale = max(abs(h_in), abs(h_out), abs(q_reb), abs(q_cond), abs(q_pa), 1.0)
    return residual, scale


def _assert_closed(thermo: Thermo, result: Any, feed_dict: dict[str, Any]) -> None:
    residual, scale = _closure_residual(thermo, result, feed_dict)
    assert abs(residual) <= 1e-8 * scale, f"energy closure off by {residual:.6g} W (scale {scale:.6g})"
    # The net unit duty closes the boundary stream table on its own.
    net = result.duty_W
    assert net == pytest.approx(
        result.info["reboiler_duty_W"]
        - result.info["condenser_duty_W"]
        + sum(v for k, v in result.info.items() if k.startswith("pa_") and k.endswith("_duty_W"))
    ), "UnitResult.duty_W must be the net unit duty (Q_reb + Sum Q_PA - Q_cond)"


@pytest.mark.parametrize(
    "pumparound",
    [
        pytest.param(
            {"name": "mid", "draw_stage": 12, "return_stage": 8, "flow_mol_s": 30.0, "duty_W": -5.0e3},
            id="fixed-duty",
        ),
        pytest.param(
            {"name": "mid", "draw_stage": 12, "return_stage": 8, "flow_mol_s": 30.0, "return_T_K": 335.0},
            id="fixed-return-T",
        ),
    ],
)
def test_whole_unit_energy_closure_with_pumparound(pumparound: dict[str, Any]) -> None:
    """Pumparound duties fold into the reboiler at the overall balance, not into qr."""
    unit = registry.create("unit", "column")
    thermo = registry.create("thermo", "pr")
    feed = thermo.flash_pt(_feed()["composition"], 330.0, 1.5e6, 100.0)
    result = unit.solve({"feed": feed}, {**_base_params(), "pumparounds": [pumparound]}, thermo)
    q_pa = result.info["pa_mid_duty_W"]
    assert q_pa < 0.0, "a pumparound cooler must report a negative (heat-removed) duty"
    _assert_closed(thermo, result, _feed())


def test_whole_unit_energy_closure_no_condenser_no_reboiler() -> None:
    """No-hardware column: item 1's failure mode is the reported reboiler duty itself.

    With condenser 'none' and reboiler 'none' the pre-fix closure reported
    the pumparound heat AS the reboiler duty (qr = closure without the PA
    subtraction, i.e. qr ~ Sum Q_PA, a large negative number for absent
    hardware). The fixed code reports a reboiler duty that is the converged
    residual only, and the full duty set closes the stream table.
    """
    params = {
        "n_stages": 8,
        "condenser": "none",
        "reboiler": "none",
        "feed_stage": 5,
        "pressure_profile": 1.5e6,
        "specs": {},
        "pumparounds": [{"name": "mid", "draw_stage": 7, "return_stage": 5,
                         "flow_mol_s": 20.0, "return_T_K": 330.0}],
    }
    unit = registry.create("unit", "column")
    thermo = registry.create("thermo", "pr")
    feed_dict = {"T": 340.0, "P": 1.5e6, "molar_flow": 100.0, "composition": {"C3": 0.5, "iC4": 0.5}}
    feed = thermo.flash_pt(feed_dict["composition"], 340.0, 1.5e6, 100.0)
    result = unit.solve({"feed": feed}, params, thermo)
    q_pa = result.info["pa_mid_duty_W"]
    assert q_pa < 0.0
    # The reboiler duty is NOT the pumparound heat dumped into a phantom
    # reboiler: it sits at the converged-residual level, orders of magnitude
    # below the pumparound duty.
    assert abs(result.info["reboiler_duty_W"]) < 0.1 * abs(q_pa)
    _assert_closed(thermo, result, feed_dict)


def test_default_pumparound_name_is_bare_index() -> None:
    """An unnamed pumparound reports as pa_1_* (not pa_pa_1_*) in info (PR #238 review item 8)."""
    unit = registry.create("unit", "column")
    thermo = registry.create("thermo", "pr")
    feed = thermo.flash_pt(_feed()["composition"], 330.0, 1.5e6, 100.0)
    result = unit.solve(
        {"feed": feed},
        {
            **_base_params(),
            "pumparounds": [{"draw_stage": 12, "return_stage": 8, "flow_mol_s": 30.0, "duty_W": -5.0e3}],
        },
        thermo,
    )
    assert "pa_1_duty_W" in result.info
    assert "pa_1_flow_mol_s" in result.info
    assert not any(k.startswith("pa_pa_") for k in result.info)
