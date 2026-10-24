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

    inlet_ports: tuple[str, ...] = ("inlet", "inlet_2")
    outlet_ports: tuple[str, ...] = ("gas_out", "liquid_out", "aqueous_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        duty_W = params.get("duty_W")
        vapor_fraction = params.get("vapor_fraction")
        if duty_W is not None and vapor_fraction is not None:
            raise FlashDrumSpecError("give exactly one of duty_W and vapor_fraction, not both")
        if vapor_fraction is not None and not 0.0 <= float(vapor_fraction) <= 1.0:
            raise FlashDrumSpecError(f"vapor_fraction {vapor_fraction} outside [0, 1]")

        # Adiabatic mix of the positive-flow inlets at the lowest inlet
        # pressure; a single inlet reproduces the original one-port flash
        # exactly (same composition, enthalpy, T and flows).
        active = [s for s in inlets.values() if s.molar_flow > 0.0]
        if not active:  # nothing to flash; zero-flow outlets
            reference = next(iter(inlets.values()))
            P_out = float(params.get("outlet_P", reference.P))
            if P_out <= 0:
                raise FlashDrumSpecError(f"outlet_P {P_out} must be positive")
            outlets = {
                "gas_out": phase_outlet(thermo, reference, reference.T, P_out, None),
                "liquid_out": phase_outlet(thermo, reference, reference.T, P_out, None),
                "aqueous_out": phase_outlet(thermo, reference, reference.T, P_out, None),
            }
            return UnitResult(outlets=outlets, duty_W=0.0, power_W=0.0, info={})
        feed = active[0]
        n_in = sum(s.molar_flow for s in active)
        P_mix = min(s.P for s in active)
        P_out = float(params.get("outlet_P", P_mix))
        if P_out <= 0:
            raise FlashDrumSpecError(f"outlet_P {P_out} must be positive")
        h_in_W = sum(s.enthalpy * s.molar_flow for s in active)
        z_mix: dict[str, float]
        if len(active) == 1:
            reference = feed
            z_mix = dict(feed.composition)
            h_mix0 = feed.enthalpy
            T_mix = feed.T
        else:
            z_mix = {}
            for s in active:
                for cid, x in s.composition.items():
                    z_mix[cid] = z_mix.get(cid, 0.0) + x * s.molar_flow
            z_mix = {cid: x / n_in for cid, x in z_mix.items()}
            h_mix0 = h_in_W / n_in
            T_mix = thermo.flash_ph(z_mix, P_mix, h_mix0, n_in).T
            # The outlet template must carry the MIXED flow: phase_outlet
            # scales each phase by reference.molar_flow.
            reference = feed.model_copy(update={"molar_flow": n_in, "composition": z_mix})

        if duty_W is not None:
            flashed = thermo.flash_ph(z_mix, P_out, h_mix0 + float(duty_W) / n_in, n_in)
        elif vapor_fraction is not None:
            flashed = thermo.flash_pvf(z_mix, P_out, float(vapor_fraction), n_in)
        else:
            flashed = thermo.flash_pt(z_mix, T_mix, P_out, n_in)

        vapor = next((p for p in flashed.phases if p.kind is PhaseKind.VAPOR), None)
        aqueous = next((p for p in flashed.phases if p.kind is PhaseKind.AQUEOUS), None)
        other_liquids = [p for p in flashed.phases if p.kind not in (PhaseKind.VAPOR, PhaseKind.AQUEOUS)]
        # With two liquids the aqueous phase leaves on its own port; with one
        # liquid it is "the liquid" whatever its classification.
        if aqueous is not None:
            liquid_phase = combined_liquid(other_liquids)
        else:
            liquid_phase = combined_liquid(list(flashed.phases))

        outlets = {
            "gas_out": phase_outlet(thermo, reference, flashed.T, P_out, vapor),
            "liquid_out": phase_outlet(thermo, reference, flashed.T, P_out, liquid_phase),
            "aqueous_out": phase_outlet(thermo, reference, flashed.T, P_out, aqueous),
        }
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
        # A second, smaller stream of the same gas at a lower pressure
        # exercises the multi-inlet mix (every inlet port must be fed).
        feed_2 = {**feed, "P": 5.0e6, "molar_flow": 10 * MMSCFD_TO_MOL_S}
        return {"inlet": feed, "inlet_2": feed_2}, {"outlet_P": 3.0e6, "duty_W": 5.0e5}
