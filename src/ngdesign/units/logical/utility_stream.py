"""Utility stream unit plugin (spec U-A).

Metering pass-through: one inlet, one outlet. Params declare the utility
``kind`` (steam levels, cooling water, fuel gas, refrigerant) and ``price``
in currency per kg of the stream. The unit reports ``utility_cost_rate`` in
``info`` — ``price x mass_flow`` in currency/s. Cost accounting is not
physics: no duty, no power, no state change.

``electricity`` is refused at R0: it has no stream basis. Its per-J form
needs a declared power param and comes in a later round.

The catalogue row marks the inlet optional (a pure source/sink form); this R0
adapter implements the metering pass-through and refuses the inlet-less form.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

#: Utility kinds (spec U-A). Data lives in later rounds; R0 meters only.
UTILITY_KINDS = (
    "steam_lp",
    "steam_mp",
    "steam_hp",
    "cooling_water",
    "fuel_gas",
    "electricity",
    "refrigerant",
)


class UtilityStream:
    """Meters a stream as a utility consumer (spec U-A)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        del thermo
        if "inlet" not in inlets:
            raise ValueError(
                "utility_stream at R0 is a metering pass-through and needs an inlet; "
                "the inlet-less source/sink form is out of scope"
            )
        kind = params.get("kind")
        if kind not in UTILITY_KINDS:
            raise ValueError(f"kind must be one of {UTILITY_KINDS}, got {kind!r}")
        if kind == "electricity":
            raise ValueError(
                "electricity has no stream basis at R0; its per-J form on a "
                "declared power param is a later round"
            )
        price = params.get("price", 0.0)
        if float(price) < 0.0:
            raise ValueError(f"price must be >= 0, got {price}")

        inlet = inlets["inlet"]
        rate = float(price) * inlet.mass_flow  # currency/kg x kg/s = currency/s
        return UnitResult(
            outlets={"outlet": inlet},
            duty_W=0.0,
            power_W=0.0,
            info={"utility_cost_rate": rate},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Meter the dry-gas example as an LP-steam consumer."""
        from ngdesign.units.jt_valve import dry_gas_feed

        return (
            {"inlet": dry_gas_feed(322.15, 7.0e6)},
            {"kind": "steam_lp", "price": 12.5},
        )
