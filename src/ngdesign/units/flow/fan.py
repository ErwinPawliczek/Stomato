"""Fan, R0 (spec U-B, plan §2 U-B 10).

Method (spec): a single low-ratio isentropic stage. The fan raises the
pressure by ``dP`` (> 0) at ``eta`` (isentropic efficiency, default 0.7):
one :func:`~ngdesign.units._physics.efficiency.isentropic_step` in compress
mode, with the shaft power reported (positive into the process). Gas service
only — a liquid inlet is refused at R0 (fans move gas; a liquid would be a
pump, a different unit).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.efficiency import isentropic_step


class FanSpecError(ValueError):
    """Typed refusal naming the parameter of a bad fan spec."""


class Fan:
    """Low-ratio gas mover with an isentropic efficiency (R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction < 0.999:
            raise FanSpecError(
                f"inlet is not gas (vapor_fraction={inlet.vapor_fraction:.4f}); "
                "a liquid would be a pump, not a fan"
            )
        dP = float(params["dP"])
        if dP <= 0:
            raise FanSpecError(f"dP {dP} Pa must be > 0 (a fan raises pressure)")
        eta = float(params.get("eta", 0.7))
        if not 0.0 < eta <= 1.0:
            raise FanSpecError(f"eta {eta} outside (0, 1]")

        outlet, power_W = isentropic_step(inlet, inlet.P + dP, eta, thermo, "compress")
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=power_W,
            info={"pressure_ratio": (inlet.P + dP) / inlet.P},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Ventilation basis: methane at 300 K / 1 bar, 5 kPa rise at eta = 0.7."""
        feed = {"T": 300.0, "P": 1.0e5, "molar_flow": 50.0, "composition": {"C1": 1.0}}
        return {"inlet": feed}, {"dP": 5000.0, "eta": 0.7}
