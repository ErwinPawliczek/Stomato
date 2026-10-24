"""Flash drum with duty (plan §2 U-D 3, spec U-D).

Plugin kind "unit", name "flash_drum" — registered from the catalogue YAML
(``data/unit_models/separation.yaml``); no decorator (round-1 conventions).

One inlet, flashed at the outlet pressure under one of three specs:

- ``duty_W`` given: PH flash with ``H_out = H_in + duty_W``;
- ``vapor_fraction`` given: PVF flash at the outlet pressure;
- neither given: PT flash at ``(T_in, P_out)`` and the balancing duty reported.

Giving both ``duty_W`` and ``vapor_fraction`` is a typed refusal. Outlets:
``gas_out`` (vapour), ``liquid_out`` (the non-aqueous liquid, the combined
liquid when the package returns one liquid) and ``aqueous_out`` (the aqueous
liquid; zero flow when the package returns a single liquid).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import combined_liquid, phase_outlet


class FlashDrumSpecError(ValueError):
    """The flash-drum spec is inconsistent; the message names the parameter."""


class FlashDrum:
    """Flash drum: one of PT, PH (with duty) or PVF, then phase outlets."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("gas_out", "liquid_out", "aqueous_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        duty_W = params.get("duty_W")
        vapor_fraction = params.get("vapor_fraction")
        if duty_W is not None and vapor_fraction is not None:
            raise FlashDrumSpecError(
                "give exactly one of duty_W and vapor_fraction, not both"
            )
        P_out = float(params.get("outlet_P", inlet.P))
        if P_out <= 0:
            raise FlashDrumSpecError(f"outlet_P {P_out} must be positive")
        if vapor_fraction is not None and not 0.0 <= float(vapor_fraction) <= 1.0:
            raise FlashDrumSpecError(
                f"vapor_fraction {vapor_fraction} outside [0, 1]"
            )

        if inlet.molar_flow <= 0.0:  # nothing to flash; zero-flow outlets
            outlets = {
                "gas_out": phase_outlet(thermo, inlet, inlet.T, P_out, None),
                "liquid_out": phase_outlet(thermo, inlet, inlet.T, P_out, None),
                "aqueous_out": phase_outlet(thermo, inlet, inlet.T, P_out, None),
            }
            return UnitResult(outlets=outlets, duty_W=0.0, power_W=0.0, info={})

        if duty_W is not None:
            h_mix = (inlet.enthalpy * inlet.molar_flow + float(duty_W)) / inlet.molar_flow
            flashed = thermo.flash_ph(inlet.composition, P_out, h_mix, inlet.molar_flow)
        elif vapor_fraction is not None:
            flashed = thermo.flash_pvf(
                inlet.composition, P_out, float(vapor_fraction), inlet.molar_flow
            )
        else:
            flashed = thermo.flash_pt(inlet.composition, inlet.T, P_out, inlet.molar_flow)

        vapor = next((p for p in flashed.phases if p.kind is PhaseKind.VAPOR), None)
        aqueous = next((p for p in flashed.phases if p.kind is PhaseKind.AQUEOUS), None)
        other_liquids = [
            p for p in flashed.phases if p.kind not in (PhaseKind.VAPOR, PhaseKind.AQUEOUS)
        ]
        # With two liquids the aqueous phase leaves on its own port; with one
        # liquid it is "the liquid" whatever its classification.
        if aqueous is not None:
            liquid_phase = combined_liquid(other_liquids)
        else:
            liquid_phase = combined_liquid(list(flashed.phases))

        outlets = {
            "gas_out": phase_outlet(thermo, inlet, flashed.T, P_out, vapor),
            "liquid_out": phase_outlet(thermo, inlet, flashed.T, P_out, liquid_phase),
            "aqueous_out": phase_outlet(thermo, inlet, flashed.T, P_out, aqueous),
        }
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info={"T_out_K": flashed.T},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The slice rich wet gas let down to 3.0 MPa with 500 kW of duty.

        The feed carries 0.3 % water, so the example exercises all three
        outlets (the aqueous outlet may be zero-flow at some states).
        """
        from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

        feed = {
            "T": 322.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": dict(INLET_COMPOSITION),
        }
        return {"inlet": feed}, {"outlet_P": 3.0e6, "duty_W": 5.0e5}
