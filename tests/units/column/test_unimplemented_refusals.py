"""Unimplemented feature-4/5 surfaces refuse with typed errors (spec S0-1 part 2b).

Part 2a ships the side-stripper coupling (feature 2) and steam/free-water
(feature 3). The spec's feature 4 (the four refiner spec drivers and their
named free tears) and feature 5 (the public ``solve_column_full`` facade)
are part 2b: their input surfaces must refuse LOUDLY with a typed
``ColumnSpecError`` naming the key, never silently approximate or ignore.
"""

from __future__ import annotations

from typing import Any

import pytest

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


def _parse_only(params: dict[str, Any]) -> None:
    """Run just the param parsing (no solve) to assert typed refusals."""
    _parse_params(params, None)


@pytest.mark.parametrize(
    ("spec_key", "value"),
    [
        ("draw_rate", 12.0),
        ("stage_temperature", 340.0),
        ("pumparound_duty", -5.0e3),
        ("pumparound_return_T", 335.0),
    ],
)
def test_refiner_spec_keys_refused(spec_key: str, value: float) -> None:
    """Each feature-4 spec key refuses at parse, naming the key (part 2b)."""
    params = {**_base_params(), "specs": {**_base_params()["specs"], spec_key: value}}
    with pytest.raises(ColumnSpecError, match=spec_key):
        _parse_only(params)


def test_free_draw_flow_refused() -> None:
    """A named draw without ``flow_mol_s`` (a free draw tear) refuses (part 2b)."""
    params = {
        **_base_params(),
        "draws": [{"stage": 12, "vapor": False, "name": "side"}],
    }
    with pytest.raises(ColumnSpecError, match="not implemented"):
        _parse_only(params)


def test_free_pumparound_flow_refused() -> None:
    """A pumparound without ``flow_mol_s`` (a free flow tear) refuses (part 2b)."""
    params = {
        **_base_params(),
        "pumparounds": [{"draw_stage": 12, "return_stage": 8, "duty_W": -1.0e3}],
    }
    with pytest.raises(ColumnSpecError, match="not implemented"):
        _parse_only(params)


def test_public_solve_column_full_refused() -> None:
    """The feature-5 public facade refuses until part 2b lands (S0-3 needs it)."""
    from ngdesign.units.column import solve_column_full

    with pytest.raises(ColumnSpecError, match="not implemented"):
        solve_column_full({}, _base_params(), thermo=None)  # type: ignore[arg-type]
