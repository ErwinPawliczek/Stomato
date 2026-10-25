"""Expander, R1: performance map — isentropic efficiency vs velocity ratio.

Spec: ``specs/backend/units/expander.md`` (unit ``expander``, level R1).

Method (spec): the R0 isentropic expansion is driven by a performance map.
The isentropic enthalpy drop per unit mass gives the spouting (isentropic
jet) velocity ``c0 = sqrt(2*dh_s)``; the rotor tip speed is ``u = pi*D*N/60``;
the velocity ratio ``nu = u/c0`` reads an isentropic efficiency off a PCHIP
performance map with no extrapolation (an explicit range refusal instead).
Radial-inflow turbines peak near nu ~ 0.7 (Whitfield & Baines 1990, ch. 7;
Balje 1981, ch. 3; Perry's 9th ed. section 10, expanders). The outlet
arithmetic is R0's: R1 delegates to :class:`ngdesign.units.expander.Expander`
with the mapped efficiency, so the outlet state, power and balance are
exactly R0's and the level reduces to R0 for a flat map.

Optional flow-capacity range: the actual inlet volumetric flow
``Q = mdot/rho1`` must lie in ``[flow_min_m3_s, flow_max_m3_s]`` when given —
below the minimum the nozzle setting cannot pass it, above the maximum the
machine chokes.
"""

from __future__ import annotations

import math
from typing import Any

from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.expander import Expander

__all__ = [
    "ExpanderFlowRangeError",
    "ExpanderMapRangeError",
    "ExpanderR1SpecError",
    "ExpanderR1",
]


class ExpanderR1SpecError(ValueError):
    """Typed refusal naming the parameter of a bad expander R1 spec."""


class ExpanderMapRangeError(ExpanderR1SpecError):
    """The operating velocity ratio falls outside the supplied map."""


class ExpanderFlowRangeError(ExpanderR1SpecError):
    """The actual inlet flow falls outside the supplied flow-capacity range."""


def _molar_mass(inlet: StreamState) -> float:
    """kg/mol: the spec's M = mdot/F."""
    return inlet.mass_flow / inlet.molar_flow


def _inlet_density(inlet: StreamState) -> float:
    """kg/m3 of the flashed inlet: total mass over total phase volume."""
    volume = 0.0
    for phase in inlet.phases:
        phase_mass = inlet.molar_flow * phase.mole_fraction * phase.molecular_weight / 1000.0
        volume += phase_mass / phase.density
    return inlet.mass_flow / volume


class ExpanderR1:
    """Gas turbo-expander rated against a velocity-ratio performance map (R1)."""

    inlet_ports = ("gas_in",)
    outlet_ports = ("gas_out",)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's example feed rated at a mid-map point of the example machine."""
        feeds, _ = Expander.example_case()
        params: dict[str, Any] = {
            "P_out": 2.0e6,
            "rotor_diameter_m": 0.30,
            "speed_rpm": 20000.0,
            "map": {
                "velocity_ratio": [0.40, 0.50, 0.60, 0.70, 0.80],
                "efficiency": [0.58, 0.65, 0.72, 0.79, 0.86],
            },
        }
        return feeds, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["gas_in"]
        if inlet.vapor_fraction < 0.999:
            raise ExpanderR1SpecError(
                f"inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f}); "
                "an R1 expander takes vapour, as in R0"
            )

        p_out = params.get("P_out")
        if p_out is None:
            raise ExpanderR1SpecError("P_out is required (discharge pressure, Pa)")
        p_out = float(p_out)
        if p_out >= inlet.P:
            raise ExpanderR1SpecError(f"P_out {p_out} Pa must be below P_in {inlet.P} Pa")
        if p_out <= 0:
            raise ExpanderR1SpecError(f"P_out {p_out} Pa must be > 0")

        rotor_diameter_m = params.get("rotor_diameter_m")
        if rotor_diameter_m is None:
            raise ExpanderR1SpecError("rotor_diameter_m is required (rotor tip diameter, m)")
        rotor_diameter_m = float(rotor_diameter_m)
        if rotor_diameter_m <= 0:
            raise ExpanderR1SpecError(f"rotor_diameter_m {rotor_diameter_m} must be > 0")

        speed_rpm = params.get("speed_rpm")
        if speed_rpm is None:
            raise ExpanderR1SpecError("speed_rpm is required (shaft speed, rpm)")
        speed_rpm = float(speed_rpm)
        if speed_rpm <= 0:
            raise ExpanderR1SpecError(f"speed_rpm {speed_rpm} must be > 0")

        velocity_ratio = self._map_points(params)

        q_min = params.get("flow_min_m3_s")
        q_max = params.get("flow_max_m3_s")
        if q_min is not None:
            q_min = float(q_min)
            if q_min <= 0 or (q_max is not None and q_min >= float(q_max)):
                raise ExpanderR1SpecError(
                    f"flow_min_m3_s {q_min} must be > 0 and below flow_max_m3_s"
                )
        if q_max is not None:
            q_max = float(q_max)
            if q_max <= 0:
                raise ExpanderR1SpecError(f"flow_max_m3_s {q_max} must be > 0")
        q_actual = inlet.mass_flow / _inlet_density(inlet)  # m3/s
        if (q_min is not None and q_actual < q_min) or (
            q_max is not None and q_actual > q_max
        ):
            raise ExpanderFlowRangeError(
                f"actual inlet flow {q_actual:.6f} m3/s outside the flow-capacity "
                f"range [{q_min}, {q_max}]"
            )

        iso = thermo.flash_ps(inlet.composition, p_out, inlet.entropy, inlet.molar_flow)
        dh_s = (inlet.enthalpy - iso.enthalpy) / _molar_mass(inlet)  # J/kg
        if dh_s <= 0:
            raise ExpanderR1SpecError(
                f"isentropic enthalpy drop {dh_s} J/kg is not positive; "
                "the inlet state admits no expansion work"
            )

        c0 = math.sqrt(2.0 * dh_s)  # spouting (isentropic jet) velocity, m/s
        u = math.pi * rotor_diameter_m * speed_rpm / 60.0  # rotor tip speed, m/s
        nu = u / c0
        if nu < velocity_ratio[0] or nu > velocity_ratio[-1]:
            raise ExpanderMapRangeError(
                f"velocity ratio {nu:.6f} outside the map range "
                f"[{velocity_ratio[0]}, {velocity_ratio[-1]}]"
            )
        eta = float(self._efficiency(params)(nu))
        if not 0.0 < eta <= 1.0:
            raise ExpanderR1SpecError(f"efficiency {eta} outside (0, 1]")

        r0 = Expander().solve(inlets, {"P_out": p_out, "eta_isentropic": eta}, thermo)
        info = dict(r0.info)
        info["eta"] = eta
        info["velocity_ratio"] = nu
        info["spouting_velocity_m_s"] = c0
        info["tip_speed_m_s"] = u
        info["dh_isentropic_J_kg"] = dh_s
        info["Q_actual_m3_s"] = q_actual
        return r0.model_copy(update={"info": info})

    @staticmethod
    def _map_points(params: dict[str, Any]) -> list[float]:
        """Validated map.velocity_ratio points (strictly increasing, >= 2)."""
        map_params = params.get("map")
        if not isinstance(map_params, dict):
            raise ExpanderR1SpecError("map.velocity_ratio is required (u/c0 points)")
        velocity_ratio = map_params.get("velocity_ratio")
        efficiency = map_params.get("efficiency")
        if velocity_ratio is None or efficiency is None:
            raise ExpanderR1SpecError("map.velocity_ratio is required (with map.efficiency)")
        velocity_ratio = [float(x) for x in velocity_ratio]
        efficiency = [float(x) for x in efficiency]
        if len(velocity_ratio) != len(efficiency) or len(velocity_ratio) < 2:
            raise ExpanderR1SpecError(
                f"map.velocity_ratio needs >= 2 points, as many as map.efficiency "
                f"(got {len(velocity_ratio)} vs {len(efficiency)})"
            )
        if any(b <= a for a, b in zip(velocity_ratio, velocity_ratio[1:])):
            raise ExpanderR1SpecError(
                f"map.velocity_ratio {velocity_ratio} must be strictly increasing"
            )
        return velocity_ratio

    @staticmethod
    def _efficiency(params: dict[str, Any]) -> PchipInterpolator:
        """The PCHIP efficiency map over the validated velocity-ratio points."""
        map_params = params["map"]
        velocity_ratio = [float(x) for x in map_params["velocity_ratio"]]
        efficiency = [float(x) for x in map_params["efficiency"]]
        if any(not 0.0 < e <= 1.0 for e in efficiency):
            raise ExpanderR1SpecError(f"efficiency {efficiency} outside (0, 1]")
        # No extrapolation: the caller has already refused nu outside the map.
        return PchipInterpolator(velocity_ratio, efficiency, extrapolate=False)
