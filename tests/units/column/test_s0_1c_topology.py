"""Stage-graph topology for side strippers (S0-1c step 1, issue #235).

The acceptance: a graph built for two strippers has the expected stage
count and interlinks; steam joins the fixed component list from the
start; and a column without the new keys builds exactly today's _Column
(empty sections - the byte-identical regression gate is the bench).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.inside_out import _build_column, _Column, _steam_feed_specs
from ngdesign.units.column.spec import STEAM_COMPONENT, _parse_params
from ngdesign.units.column.thermo_adapter import _ThermoBox


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


def _two_stripper_params() -> dict[str, Any]:
    """16 main stages + a 4-stage steam stripper + a 3-stage reboiled one."""
    return {
        **_base_params(),
        "side_strippers": [
            {
                "name": "steam",
                "draw_stage": 6,
                "return_stage": 3,
                "n_stages": 4,
                "steam": {"flow_mol_s": 2.0, "T_K": 450.0, "P_Pa": 5.0e5},
                "product_rate_mol_s": 15.0,
            },
            {
                "name": "reb",
                "draw_stage": 12,
                "return_stage": 10,
                "n_stages": 3,
                "reboiler_duty_W": 5.0e3,
                "product_rate_mol_s": 10.0,
            },
        ],
    }


def _build(params: dict[str, Any], thermo: Thermo) -> _Column:
    parsed = _parse_params(params, None)
    tb = _ThermoBox(thermo, min(parsed.pressures), max(parsed.pressures))
    return _build_column(parsed, tb)


def test_graph_for_two_strippers(thermo: Thermo) -> None:
    """Stage count and interlinks of a 2-stripper graph."""
    col = _build(_two_stripper_params(), thermo)

    assert col.n == 16  # main stages numbered as today
    assert col.n_graph == 23  # 16 + 4 + 3
    s0, s1 = col.sections
    # Section 1: stages 17-20 (top to bottom), draw at main 6, vapour
    # returns to main 3, steam/reboiler on the bottom stage 20.
    assert s0.stages == (17, 18, 19, 20)
    assert s0.draw_stage == 6
    assert s0.return_stage == 3
    assert s0.bottom_stage == 20
    assert s0.stripper.name == "steam"
    # Section 2: stages 21-23.
    assert s1.stages == (21, 22, 23)
    assert s1.draw_stage == 12
    assert s1.return_stage == 10
    assert s1.bottom_stage == 23
    assert s1.stripper.steam_flow is None
    assert s1.stripper.reboiler_duty_W == 5.0e3


def test_zero_stage_stripper_is_a_plain_draw(thermo: Thermo) -> None:
    """n_stages = 0: no section stages, no bottom stage, nothing returns."""
    params = _two_stripper_params()
    params["side_strippers"][1]["n_stages"] = 0
    col = _build(params, thermo)

    assert col.n_graph == 20  # 16 + 4 + 0
    assert col.sections[1].stages == ()
    assert col.sections[1].bottom_stage is None


def test_steam_joins_the_fixed_component_list(thermo: Thermo) -> None:
    """Water is in col.comps from the start - even at zero steam flow."""
    col = _build(_two_stripper_params(), thermo)
    assert STEAM_COMPONENT in col.comps

    # And the steam is an ordinary feed on the section's bottom stage.
    parsed = _parse_params(_two_stripper_params(), None)
    specs = _steam_feed_specs(parsed)
    assert len(specs) == 1
    assert specs[0].stage == 20
    assert specs[0].comp == {STEAM_COMPONENT: 1.0}
    assert specs[0].flow == 2.0

    # Zero steam flow: no feed, but the component list is still fixed.
    params = _two_stripper_params()
    params["side_strippers"][0]["steam"]["flow_mol_s"] = 0.0
    col0 = _build(params, thermo)
    assert STEAM_COMPONENT in col0.comps
    assert _steam_feed_specs(_parse_params(params, None)) == []


def test_plain_column_builds_todays_graph(thermo: Thermo) -> None:
    """No new keys: empty sections, n_graph == n, no steam component."""
    col = _build(_base_params(), thermo)

    assert col.sections == []
    assert col.strippers == []
    assert col.n_graph == col.n == 16
    assert STEAM_COMPONENT not in col.comps
