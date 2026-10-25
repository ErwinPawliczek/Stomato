"""Typed refusals for side strippers and condenser water decant (S0-1c step 1).

Step 1 wires the parsing and the stage graph; the simultaneous stripper
solve is step 3 and the condenser decant is step 4. Every parse-time
refusal fires in ``_parse_params``; every solve-time refusal fires in
``Column.solve`` before any thermo work.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.spec import ColumnSpecError, _parse_params


def _base_params() -> dict[str, Any]:
    return {
        "n_stages": 16,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 8,
        "pressure_profile": 1.5e6,
        "feeds": [
            {
                "stage": 8,
                "T": 330.0,
                "P": 1.5e6,
                "molar_flow": 100.0,
                "composition": {"C3": 0.5, "iC4": 0.5},
            }
        ],
        "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
    }


def _steam_stripper(**over: Any) -> dict[str, Any]:
    """One valid steam stripper (draw 6, return 3, 4 stages, bottoms rate)."""
    st: dict[str, Any] = {
        "name": "s1",
        "draw_stage": 6,
        "return_stage": 3,
        "n_stages": 4,
        "steam": {"flow_mol_s": 2.0, "T_K": 450.0, "P_Pa": 5.0e5},
        "product_rate_mol_s": 20.0,
    }
    st.update(over)
    return st


def _parse_only(params: dict[str, Any]) -> None:
    """Run just the param parsing (no solve) to assert typed refusals."""
    _parse_params(params, None)


def test_parse_accepts_valid_stripper() -> None:
    """A well-formed steam stripper parses into _Params (no refusal)."""
    params = {**_base_params(), "side_strippers": [_steam_stripper()]}
    parsed = _parse_params(params, None)
    assert len(parsed.side_strippers) == 1
    st = parsed.side_strippers[0]
    assert st.name == "s1"
    assert st.draw_stage == 6
    assert st.return_stage == 3
    assert st.n_stages == 4
    assert st.steam_flow == 2.0
    assert st.product_rate == 20.0
    assert parsed.condenser_water_decant is False


def test_parse_accepts_reboiled_stripper() -> None:
    """The reboiler option (duty instead of steam) parses too."""
    st = _steam_stripper()
    del st["steam"]
    st["reboiler_duty_W"] = 5.0e3
    params = {**_base_params(), "side_strippers": [st]}
    parsed = _parse_params(params, None)
    assert parsed.side_strippers[0].steam_flow is None
    assert parsed.side_strippers[0].reboiler_duty_W == 5.0e3


def test_solve_with_strippers_refused_step3(thermo: Thermo) -> None:
    """A solve requesting strippers refuses: not implemented (S0-1c step 3)."""
    params = {**_base_params(), "side_strippers": [_steam_stripper()]}
    unit = registry.create("unit", "column")
    feed = thermo.flash_pt(_base_params()["feeds"][0]["composition"], 330.0, 1.5e6, 100.0)
    with pytest.raises(ColumnSpecError, match="not implemented \\(S0-1c step 3\\)"):
        unit.solve({"feed": feed}, params, thermo)


def test_solve_with_decant_refused_step4(thermo: Thermo) -> None:
    """A solve requesting decant refuses: not implemented (S0-1c step 4)."""
    params = {**_base_params(), "condenser_water_decant": True}
    unit = registry.create("unit", "column")
    feed = thermo.flash_pt(_base_params()["feeds"][0]["composition"], 330.0, 1.5e6, 100.0)
    with pytest.raises(ColumnSpecError, match="not implemented \\(S0-1c step 4\\)"):
        unit.solve({"feed": feed}, params, thermo)


def test_return_stage_below_draw_required() -> None:
    """The stripped overhead returns at or above the draw."""
    params = {**_base_params(), "side_strippers": [_steam_stripper(return_stage=9, draw_stage=6)]}
    with pytest.raises(ColumnSpecError, match="return_stage 9 must be at or above"):
        _parse_only(params)


def test_draw_on_condenser_stage_refused() -> None:
    """A stripper draw on the condenser stage would report wrong duties."""
    params = {**_base_params(), "side_strippers": [_steam_stripper(draw_stage=1, return_stage=1)]}
    with pytest.raises(ColumnSpecError, match="draw_stage 1 is the condenser stage"):
        _parse_only(params)


def test_draw_on_kettle_stage_refused() -> None:
    """A stripper draw on the kettle stage would report wrong duties."""
    params = {**_base_params(), "side_strippers": [_steam_stripper(draw_stage=16, return_stage=14)]}
    with pytest.raises(ColumnSpecError, match="draw_stage 16 is the reboiler stage"):
        _parse_only(params)


@pytest.mark.parametrize("n", [None, 1, -2, "three"])
def test_bad_n_stages_refused(n: Any) -> None:
    """n_stages is required, integer, >= 0, and never 1 (1 stage is unsolvable)."""
    params = {**_base_params(), "side_strippers": [_steam_stripper(n_stages=n)]}
    with pytest.raises(ColumnSpecError, match="n_stages"):
        _parse_only(params)


def test_steam_and_reboiler_mutually_exclusive() -> None:
    """Exactly one of steam / reboiler_duty_W per stripper."""
    st = _steam_stripper(reboiler_duty_W=5.0e3)
    params = {**_base_params(), "side_strippers": [st]}
    with pytest.raises(ColumnSpecError, match="exactly one of steam"):
        _parse_only(params)


def test_neither_steam_nor_reboiler_refused() -> None:
    """A stripper with no stripping agent refuses."""
    st = _steam_stripper()
    del st["steam"]
    params = {**_base_params(), "side_strippers": [st]}
    with pytest.raises(ColumnSpecError, match="exactly one of steam"):
        _parse_only(params)


def test_negative_steam_flow_refused() -> None:
    """Steam flow is >= 0 (0 = no steam)."""
    st = _steam_stripper(steam={"flow_mol_s": -1.0, "T_K": 450.0, "P_Pa": 5.0e5})
    params = {**_base_params(), "side_strippers": [st]}
    with pytest.raises(ColumnSpecError, match="steam.flow_mol_s must be >= 0"):
        _parse_only(params)


def test_missing_product_rate_refused() -> None:
    """A stripper draw without its product_rate driver refuses at parse."""
    st = _steam_stripper()
    del st["product_rate_mol_s"]
    params = {**_base_params(), "side_strippers": [st]}
    with pytest.raises(ColumnSpecError, match="no driver"):
        _parse_only(params)


def test_duplicate_stripper_names_refused() -> None:
    """Two strippers with one name would collide in the info keys."""
    params = {
        **_base_params(),
        "side_strippers": [_steam_stripper(), _steam_stripper(draw_stage=10, return_stage=8)],
    }
    with pytest.raises(ColumnSpecError, match="duplicate name 's1'"):
        _parse_only(params)


def test_stripper_name_colliding_with_draw_refused() -> None:
    """A stripper name that is also a named draw collides in the info keys."""
    params = {
        **_base_params(),
        "draws": [{"stage": 12, "vapor": False, "flow_mol_s": 5.0, "name": "s1"}],
        "side_strippers": [_steam_stripper()],
    }
    with pytest.raises(ColumnSpecError, match="collides with a named draw"):
        _parse_only(params)


def test_decant_requires_bool() -> None:
    """condenser_water_decant is a bool flag."""
    params = {**_base_params(), "condenser_water_decant": "yes"}
    with pytest.raises(ColumnSpecError, match="condenser_water_decant must be a bool"):
        _parse_only(params)


def test_decant_requires_total_condenser() -> None:
    """The decant lives at the condensate split: a total condenser is required."""
    params = {**_base_params(), "condenser": "partial", "condenser_water_decant": True}
    with pytest.raises(ColumnSpecError, match="needs a total condenser"):
        _parse_only(params)


def test_spec_count_mismatch_names_both_lists() -> None:
    """With strippers, the count refusal names drivers and tears explicitly."""
    st = _steam_stripper()  # product_rate present: the driver validation passes
    params = {
        **_base_params(),
        "specs": {"reflux_ratio": 2.5},  # 2 drivers vs 3 tears (top, boilup, stripper:1)
        "side_strippers": [st],
    }
    with pytest.raises(ColumnSpecError, match="every tear needs exactly one driver"):
        _parse_only(params)
