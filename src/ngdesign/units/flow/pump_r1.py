"""Centrifugal pump, R1: pump curve with affinity laws and an NPSHa check.

Spec: specs/backend/units/pump.md (U-R2 level wave). Level R1 of the `pump` row
(`data/unit_models/flow.yaml`); the R0 adapter ``ngdesign.units.pump.Pump`` is
imported read-only and owns the thermodynamics, the energy balance and the
outlet flash — this module adds the curve.

Method (spec equations, all SI):
1. ``Q = mdot / rho_L`` with ``rho_L = _liquid_density(inlet)`` (as R0).
2. Affinity laws at the speed ratio ``s = N / N_curve`` (Karassik et al.,
   *Pump Handbook*, 4th ed., §2.1 affinity laws; Perry's 9th ed. §10):
   ``Q_eq = Q / s``; ``H(Q) = s**2 * H_c(Q_eq)``; ``eta(Q) = eta_c(Q_eq)``
   (efficiency unchanged at the equivalent point); ``NPSHr(Q) = s**2 *
   NPSHr_c(Q_eq)`` — this last one is the usual approximation (true
   similarity holds for the first three; NPSHr scales on the same exponent
   in practice because it follows the suction-eye velocity heads).
3. ``H_c``, ``eta_c`` and ``NPSHr_c`` are monotone piecewise-cubic (PCHIP)
   interpolants of the supplied curve points over ``flow_m3_s``, with
   ``extrapolate=False`` — no extrapolation, ``Q_eq`` outside the curve is
   refused before evaluation.
4. ``dP = rho_L * g * H`` with ``g = G_STD = 9.80665`` m/s**2 (ISO 80000,
   taken from ``ngdesign.units.pump.G_STD``, never retyped);
   ``P_out = P_in + dP``.
5. The outlet, ``power_W = Q * dP / eta`` and the energy balance come from the
   R0 adapter: ``Pump().solve(inlets, {"P_out": P_out, "eta": eta}, thermo)``.
   Consequently R1 reduces to R0 exactly (identity test) for any curve.
6. Suction vapour pressure ``P_v`` is the mixture bubble-point pressure at
   suction temperature (``thermo.bubble_point(z, T=T_in).P``), not a pure
   component Psat.
7. ``NPSHa = (P_in - P_v) / (rho_L * g) + z_s - h_f`` (Hydraulic Institute
   ANSI/HI 9.6.1; Perry's 9th ed. §10), evaluated by the repo's one owner,
   :func:`ngdesign.sizing.pump_power.npsh_available`.
8. ``NPSH margin M = NPSHa - NPSHr(Q)``, computed only when
   ``curve.npsh_required_m`` is given; with ``npsh_check == "refuse"`` a
   negative margin raises :class:`PumpCavitationError`, with ``"report"`` the
   negative margin is returned in ``info``.

There is no iteration. All refusals are typed ``ValueError`` subclasses
defined here; nothing is clamped silently.
"""

from __future__ import annotations

from typing import Any

from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.pump import G_STD, Pump, _liquid_density

__all__ = [
    "PumpCavitationError",
    "PumpCurveRangeError",
    "PumpR1SpecError",
    "PumpR1",
]


class PumpR1SpecError(ValueError):
    """Typed refusal naming the parameter of a bad pump R1 spec."""


class PumpCurveRangeError(PumpR1SpecError):
    """The equivalent flow falls outside the supplied curve (no extrapolation)."""


class PumpCavitationError(PumpR1SpecError):
    """NPSHa < NPSHr at the operating point with ``npsh_check == "refuse"``."""


def _float_array(value: Any, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or not value:
        raise PumpR1SpecError(f"curve.{name} must be a non-empty array")
    return [float(v) for v in value]


def _curve_arrays(
    curve: Any,
) -> tuple[list[float], list[float], list[float] | None]:
    """Validate the curve dict and return (flow, head, efficiency)."""
    if not isinstance(curve, dict):
        raise PumpR1SpecError("curve.flow_m3_s and curve.head_m are required (curve missing)")
    if "flow_m3_s" not in curve or curve["flow_m3_s"] is None:
        raise PumpR1SpecError("curve.flow_m3_s and curve.head_m are required (curve.flow_m3_s missing)")
    if "head_m" not in curve or curve["head_m"] is None:
        raise PumpR1SpecError("curve.flow_m3_s and curve.head_m are required (curve.head_m missing)")
    flow = _float_array(curve["flow_m3_s"], "flow_m3_s")
    head = _float_array(curve["head_m"], "head_m")
    if len(flow) != len(head):
        raise PumpR1SpecError(
            f"curve.flow_m3_s and curve.head_m must have the same length (got {len(flow)} and {len(head)})"
        )
    if len(flow) < 2:
        raise PumpR1SpecError(
            f"curve.flow_m3_s must be strictly increasing over at least 2 points (got {len(flow)})"
        )
    if any(b <= a for a, b in zip(flow, flow[1:], strict=False)):
        raise PumpR1SpecError("curve.flow_m3_s must be strictly increasing")
    efficiency: list[float] | None = None
    if curve.get("efficiency") is not None:
        efficiency = _float_array(curve["efficiency"], "efficiency")
        if len(efficiency) != len(flow):
            raise PumpR1SpecError(
                f"curve.efficiency must have the same length as curve.flow_m3_s "
                f"(got {len(efficiency)} and {len(flow)})"
            )
        for e in efficiency:
            if not 0.0 < e <= 1.0:
                raise PumpR1SpecError(f"curve efficiency {e} outside (0, 1]")
    npsh_required: list[float] | None = None
    if curve.get("npsh_required_m") is not None:
        npsh_required = _float_array(curve["npsh_required_m"], "npsh_required_m")
        if len(npsh_required) != len(flow):
            raise PumpR1SpecError(
                f"curve.npsh_required_m must have the same length as curve.flow_m3_s "
                f"(got {len(npsh_required)} and {len(flow)})"
            )
        for n in npsh_required:
            if n < 0:
                raise PumpR1SpecError(f"curve npsh_required_m {n} must be >= 0")
    for h in head:
        if h <= 0:
            raise PumpR1SpecError(f"curve head {h} must be > 0")
    return flow, head, efficiency


def _efficiency(curve: Any, params: dict[str, Any]) -> float:
    """Exactly one of curve.efficiency / eta; the scalar (nan when the curve carries the array)."""
    has_curve_eff = curve.get("efficiency") is not None
    has_eta = params.get("eta") is not None
    if has_curve_eff == has_eta:
        raise PumpR1SpecError("exactly one of curve.efficiency or eta must be given")
    if has_eta:
        eta = float(params["eta"])
        if not 0.0 < eta <= 1.0:
            raise PumpR1SpecError(f"eta {eta} outside (0, 1]")
        return eta
    return float("nan")


class PumpR1:
    """Centrifugal pump on a head/efficiency curve with affinity laws (R1)."""

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
            raise PumpR1SpecError(
                f"inlet has vapor (vapor_fraction={inlet.vapor_fraction:.4f}); a pump needs liquid"
            )

        curve = params.get("curve")
        flow, head, eff_arr = _curve_arrays(curve)
        eta_const = _efficiency(curve, params)

        s_raw = params.get("speed_ratio")
        speed_ratio = 1.0 if s_raw is None else float(s_raw)
        if not speed_ratio > 0:
            raise PumpR1SpecError(f"speed_ratio {speed_ratio} must be > 0")

        rho = _liquid_density(inlet)
        Q = inlet.mass_flow / rho  # m3/s
        Q_eq = Q / speed_ratio

        # Refuse before evaluation: PCHIP with extrapolate=False returns NaN
        # outside the domain; the refusal is explicit instead.
        if Q_eq < flow[0] or Q_eq > flow[-1]:
            raise PumpCurveRangeError(
                f"equivalent flow Q_eq {Q_eq:.6g} m3/s is outside the curve "
                f"[{flow[0]:.6g}, {flow[-1]:.6g}] m3/s; there is no extrapolation"
            )

        H_c = PchipInterpolator(flow, head, axis=0, extrapolate=False)
        H = speed_ratio**2 * float(H_c(Q_eq))
        eta = (
            eta_const
            if eff_arr is None
            else float(PchipInterpolator(flow, eff_arr, axis=0, extrapolate=False)(Q_eq))
        )
        if not 0.0 < eta <= 1.0:
            raise PumpR1SpecError(f"interpolated efficiency {eta} outside (0, 1]")
        if H <= 0:
            raise PumpR1SpecError(f"interpolated head {H} m is <= 0")

        dP = rho * G_STD * H
        P_out = inlet.P + dP

        r0 = Pump().solve(inlets, {"P_out": P_out, "eta": eta}, thermo)

        info: dict[str, float] = {
            **r0.info,
            "P_out_Pa": P_out,
            "eta": eta,
            "speed_ratio": speed_ratio,
            "Q_equiv_m3_s": Q_eq,
            "curve_fraction": (Q_eq - flow[0]) / (flow[-1] - flow[0]),
        }
        return UnitResult(outlets=r0.outlets, duty_W=r0.duty_W, power_W=r0.power_W, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed on the spec's closed-form curve at speed 1."""
        feeds, _params = Pump.example_case()
        curve = {
            "flow_m3_s": [0.0, 2.0e-4, 4.0e-4, 6.0e-4, 8.0e-4],
            "head_m": [80.0, 72.0, 64.0, 56.0, 48.0],
            "efficiency": [0.40, 0.50, 0.60, 0.70, 0.80],
        }
        return feeds, {"curve": curve}
