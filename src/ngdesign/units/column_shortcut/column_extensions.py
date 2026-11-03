"""Column with its MESH extensions on the flowsheet graph, R2 (plan U-E 6).

Plugin kind "unit", name "column_extensions". Ports ``feed`` (and the optional
``feed_2``) -> ``distillate`` + ``bottoms`` + the optional ``side_draw``.

Method: the column row's MESH solvers (Boston & Sullivan 1974; Naphtali &
Sandholm 1971; ``ngdesign.units.column``), with all four extensions in the same
stage equations:

- a second feed, on any stage, through a real port (the column row takes further
  feeds in params only, invisible to the graph);
- one side draw, liquid or vapour, leaving through a real port;
- pumparounds: the core's fixed loops (S0-1), ``pa_<name>_*`` in info;
- inter-stage heaters and coolers: Q_j in the stage's H balance (Seader, Henley &
  Roper 3rd ed., eq. 10-4), ``heater_<stage>_duty_W`` in info.

``duty_W`` is the net boundary duty over all exchangers. More than one draw is
refused: this unit has one draw port, and material must leave through a port.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column

_PASSED_KEYS = frozenset(
    {
        "n_stages",
        "condenser",
        "reboiler",
        "feed_stage",
        "pressure_profile",
        "specs",
        "pumparounds",
        "stage_heaters",
    }
)
_ALLOWED_KEYS = _PASSED_KEYS | {"feed_2_stage", "side_draw"}


class ColumnExtensionsError(ValueError):
    """Refusal: the extended-column spec is invalid."""


class ColumnExtensions:
    """The column with a second feed port, a draw port, pumparounds and heaters."""

    inlet_ports = ("feed", "feed_2")
    outlet_ports = ("distillate", "bottoms", "side_draw")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ColumnExtensionsError("column_extensions requires the feed inlet stream")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise ColumnExtensionsError(f"column_extensions refuses unknown parameter {key!r}")
        column_params = {key: params[key] for key in _PASSED_KEYS if key in params}

        second = inlets.get("feed_2")
        if second is not None and second.molar_flow > 0.0:
            if "feed_2_stage" not in params:
                raise ColumnExtensionsError("feed_2 is connected: feed_2_stage is required")
            column_params["feeds"] = [
                {
                    "stage": params["feed_2_stage"],
                    "T": second.T,
                    "P": second.P,
                    "molar_flow": second.molar_flow,
                    "composition": dict(second.composition),
                }
            ]
        elif "feed_2_stage" in params:
            raise ColumnExtensionsError("feed_2_stage is set but no feed_2 stream is connected")

        draw = params.get("side_draw")
        if draw is not None:
            if not isinstance(draw, dict):
                raise ColumnExtensionsError(
                    "side_draw must be one {stage, phase, flow_mol_s} dict: this unit has one draw port"
                )
            column_params["draws"] = [dict(draw)]

        result = Column().solve({"feed": feed}, column_params, thermo)
        return result

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Illustrative: the column row's C3/iC4 split with all four extensions on it."""
        feeds = {
            "feed": {"T": 330.0, "P": 1.5e6, "molar_flow": 100.0, "composition": {"C3": 0.5, "iC4": 0.5}},
            "feed_2": {"T": 325.0, "P": 1.5e6, "molar_flow": 20.0, "composition": {"C3": 0.8, "iC4": 0.2}},
        }
        params = {
            "n_stages": 16,
            "condenser": "total",
            "reboiler": "kettle",
            "feed_stage": 9,
            "feed_2_stage": 5,
            "pressure_profile": 1.5e6,
            "specs": {"reflux_ratio": 2.5, "distillate_rate": 50.0},
            "side_draw": {"stage": 3, "phase": "liquid", "flow_mol_s": 8.0},
            "pumparounds": [
                {"name": "mid", "draw_stage": 12, "return_stage": 8, "flow_mol_s": 30.0, "duty_W": -5.0e3}
            ],
            "stage_heaters": [{"stage": 14, "duty_W": 2.0e4}],
        }
        return feeds, params
