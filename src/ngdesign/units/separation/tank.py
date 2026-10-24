"""Tank / surge drum (plan §2 U-D 5, spec U-D).

Plugin kind "unit", name "tank" — registered from the catalogue YAML; no
decorator (round-1 conventions).

Steady state equals a mixer: adiabatic PH mix of the inlets at ``P = min
inlet P`` (or a given ``P``). ``volume_m3`` is an optional holdup parameter;
``info["residence_time_s"]`` is the holdup divided by the outlet liquid
volumetric flow, from the liquid phases' molecular weight and density (the
``thermo`` flash result and, where a liquid exists only off the flash,
``thermo.phase_props``).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class TankSpecError(ValueError):
    """The tank spec is bad; the message names the parameter."""


class Tank:
    """Adiabatic PH mix with an optional holdup residence-time report."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        volume_m3 = params.get("volume_m3")
        if volume_m3 is not None and float(volume_m3) < 0:
            raise TankSpecError(f"volume_m3 {volume_m3} must be >= 0")
        P_param = params.get("P")
        if P_param is not None and float(P_param) <= 0:
            raise TankSpecError(f"P {P_param} must be positive")

        active = [s for s in inlets.values() if s.molar_flow > 0.0]
        if not active:  # all ports zero-flow: no flash possible or needed
            reference = next(iter(inlets.values()))
            zero = reference.model_copy(
                update={"molar_flow": 0.0, "composition": dict(reference.composition)}
            )
            return UnitResult(outlets={"outlet": zero}, duty_W=0.0, power_W=0.0, info={})
        P_min = min(s.P for s in active)
        if P_param is not None and float(P_param) > P_min:
            raise TankSpecError(
                f"P {P_param} exceeds the lowest inlet pressure {P_min}: the tank does not raise pressure"
            )
        P_out = float(P_param) if P_param is not None else P_min

        total = sum(s.molar_flow for s in active)
        z: dict[str, float] = {}
        for s in active:
            for cid, x in s.composition.items():
                z[cid] = z.get(cid, 0.0) + x * s.molar_flow
        composition = {cid: n / total for cid, n in z.items()}
        h_mix = sum(s.enthalpy * s.molar_flow for s in active) / total

        outlet = thermo.flash_ph(composition, P_out, h_mix, total)

        liquid_vol_flow = _liquid_volumetric_flow(thermo, outlet)
        residence = volume_m3 / liquid_vol_flow if volume_m3 is not None and liquid_vol_flow > 0.0 else 0.0
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={
                "residence_time_s": residence,
                "liquid_vol_flow_m3_s": liquid_vol_flow,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The slice separator feed into a 20 m3 surge drum, no extra ΔP.

        The 293.15 K / 3.447 MPa feed flashes two-phase, so the liquid
        volumetric flow and the residence time are exercised.
        """
        from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

        feed = {
            "T": 293.15,
            "P": 3.447e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": dict(INLET_COMPOSITION),
        }
        return {"inlet": feed}, {"volume_m3": 20.0}


def _liquid_volumetric_flow(thermo: Thermo, outlet: StreamState) -> float:
    """Liquid volumetric flow of an outlet, m3/s, from its liquid phases.

    Each liquid phase carries its own molecular weight (g/mol) and density
    (kg/m3) from the flash; a single-liquid outlet without phases is built
    with ``thermo.phase_props`` at the outlet state.
    """
    liquids = [p for p in outlet.phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        return 0.0
    vol = 0.0
    for p in liquids:
        mass_flow = p.mole_fraction * outlet.molar_flow * p.molecular_weight * 1e-3  # kg/s
        vol += mass_flow / p.density  # m3/s
    return vol
