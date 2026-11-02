"""Pump R1: pump curve with affinity laws and an NPSHa check (``specs/backend/units/pump.md``).

The discharge pressure comes from a head curve instead of a spec; the thermodynamics
stay with the R0 adapter, which this level calls.

- Q = m_dot/rho_L at suction.
- Affinity laws at speed ratio s = N/N_curve (Karassik et al., *Pump Handbook*, 4th
  ed., §2.1; Perry's 9th ed. §10): Q_eq = Q/s, H = s**2*H_c(Q_eq), eta = eta_c(Q_eq)
  and NPSHr = s**2*NPSHr_c(Q_eq).  The NPSHr scaling is the usual approximation.
- Curves are monotone PCHIP interpolants with no extrapolation.
- P_out = P_in + rho_L*g*H.
- NPSHa = (P_in - P_v)/(rho_L*g) + z_s - h_f (ANSI/HI 9.6.1), with P_v the mixture
  bubble pressure at suction T, through ``sizing.pump_power.npsh_available``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.pump_power import npsh_available
from ngdesign.units.pump import G_STD, Pump, _liquid_density


class PumpR1SpecError(ValueError):
    """A refused pump R1 specification; the message names the parameter."""


class PumpCurveRangeError(PumpR1SpecError):
    """The operating point falls outside the supplied curve."""


class PumpCavitationError(PumpR1SpecError):
    """NPSHa is below NPSHr with ``npsh_check = "refuse"``."""


def _curve_array(curve: dict[str, Any], key: str, n: int) -> np.ndarray:
    values = np.asarray(curve[key], dtype=float)
    if values.size != n:
        raise PumpR1SpecError(f"curve.{key} must have the same length as curve.flow_m3_s")
    return values


class PumpR1:
    """Centrifugal pump rated on its curve."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction > 0.001:
            raise PumpR1SpecError(f"inlet has vapor (vapor_fraction={inlet.vapor_fraction:.4f})")
        curve = params.get("curve")
        if not isinstance(curve, dict) or "flow_m3_s" not in curve:
            raise PumpR1SpecError("curve.flow_m3_s is required")
        if "head_m" not in curve:
            raise PumpR1SpecError("curve.head_m is required")
        flow = np.asarray(curve["flow_m3_s"], dtype=float)
        n = flow.size
        if n < 2 or not bool(np.all(np.diff(flow) > 0.0)):
            raise PumpR1SpecError("curve.flow_m3_s must be strictly increasing with at least 2 points")
        head = _curve_array(curve, "head_m", n)
        has_eta_curve = "efficiency" in curve
        if has_eta_curve == ("eta" in params):
            raise PumpR1SpecError("give exactly one of curve.efficiency or eta")
        speed = float(params.get("speed_ratio", 1.0))
        if speed <= 0.0:
            raise PumpR1SpecError(f"speed_ratio {speed} must be > 0")
        npsh_check = params.get("npsh_check", "refuse")
        if npsh_check not in ("refuse", "report"):
            raise PumpR1SpecError(f"npsh_check {npsh_check!r} is not 'refuse' or 'report'")
        npshr_curve = _curve_array(curve, "npsh_required_m", n) if "npsh_required_m" in curve else None

        rho = _liquid_density(inlet)
        q = inlet.mass_flow / rho
        q_eq = q / speed
        if q_eq < flow[0] or q_eq > flow[-1]:
            raise PumpCurveRangeError(
                f"equivalent flow {q_eq} m3/s is outside the curve [{flow[0]}, {flow[-1]}]"
            )

        def at(values: np.ndarray) -> float:
            return float(PchipInterpolator(flow, values, extrapolate=False)(q_eq))

        h = speed**2 * at(head)
        eta = at(_curve_array(curve, "efficiency", n)) if has_eta_curve else float(params["eta"])
        if h <= 0.0:
            raise PumpR1SpecError(f"interpolated head {h} m must be > 0")
        if not 0.0 < eta <= 1.0:
            raise PumpR1SpecError(f"interpolated efficiency {eta} outside (0, 1]")

        p_out = inlet.P + rho * G_STD * h
        r0 = Pump().solve(inlets, {"P_out": p_out, "eta": eta}, thermo)

        p_v = float(thermo.bubble_point(dict(inlet.composition), T=inlet.T).P)
        npsha = npsh_available(
            inlet.P,
            p_v,
            rho,
            float(params.get("static_head_m", 0.0)),
            float(params.get("friction_head_m", 0.0)),
        )
        info: dict[str, float] = {
            **r0.info,
            "P_out_Pa": p_out,
            "eta": eta,
            "speed_ratio": speed,
            "Q_equiv_m3_s": q_eq,
            "P_vapor_Pa": p_v,
            "NPSHa_m": npsha,
            "curve_fraction": float((q_eq - flow[0]) / (flow[-1] - flow[0])),
        }
        if npshr_curve is not None:
            npshr = speed**2 * at(npshr_curve)
            margin = npsha - npshr
            info["NPSHr_m"] = npshr
            info["NPSH_margin_m"] = margin
            if margin < 0.0 and npsh_check == "refuse":
                raise PumpCavitationError(f"NPSHa {npsha} m is below NPSHr {npshr} m")
        return UnitResult(outlets=r0.outlets, duty_W=r0.duty_W, power_W=r0.power_W, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 feed on an illustrative linear test curve, not a vendor curve."""
        feeds, _ = Pump.example_case()
        params: dict[str, Any] = {
            "curve": {
                "flow_m3_s": [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4],
                "head_m": [80.0, 72.0, 64.0, 56.0, 48.0],
                "efficiency": [0.40, 0.50, 0.60, 0.70, 0.80],
                "npsh_required_m": [2.0, 2.5, 3.0, 3.5, 4.0],
            },
        }
        return feeds, params
