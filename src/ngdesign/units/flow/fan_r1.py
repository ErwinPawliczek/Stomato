"""Fan, R1 (spec ``specs/backend/units/fan.md``).

Method (spec): a performance curve — fan total pressure rise and efficiency
against actual inlet volumetric flow — interpolated with a PCHIP spline and
corrected to the operating speed and density with the fan laws (AMCA
Publication 201, *Fans and Systems*; ASHRAE Handbook — HVAC Systems and
Equipment, "Fans" chapter). At speed ratio ``s = N/N_curve`` and density
ratio ``r = rho_1/rho_curve``::

    Q_eq = Q / s
    dP(Q)  = dP_curve(Q_eq) * s^2 * r
    eta(Q) = eta_curve(Q_eq)

``Q = mdot / rho_1`` is the actual inlet volumetric flow of the single gas
phase; omitting ``curve_density_kg_m3`` takes the curve at the operating
density (``r = 1``). There is no iteration.

The curve's ``pressure_rise_Pa`` is the fan **total** pressure rise. It is
applied here as the stream static pressure change, ``P_out = P_in + dP``:
this matches R0, which carries no velocity head.

The thermodynamic step is R0's (:class:`ngdesign.units.flow.fan.Fan`) called
with the evaluated ``dP`` and ``eta``, so R1 reduces to R0 exactly: a flat
curve at ``s = 1``, ``r = 1`` reproduces ``Fan().solve`` with ``dP = dP*``,
``eta = eta*``.
"""

from __future__ import annotations

from typing import Any

from scipy.interpolate import PchipInterpolator

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.flow.fan import Fan


class FanR1SpecError(ValueError):
    """Typed refusal naming the parameter of a bad fan R1 spec."""


class FanCurveRangeError(FanR1SpecError):
    """The equivalent operating point lies outside the supplied curve."""


_CURVE_KEYS = ("flow_m3_s", "pressure_rise_Pa", "efficiency")


class FanR1:
    """Fan performance curve (PCHIP) with fan laws and density correction (R1)."""

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
            raise FanR1SpecError(
                f"inlet is not gas (vapor_fraction={inlet.vapor_fraction:.4f}); "
                "a fan curve moves gas — a liquid would be a pump"
            )
        curve = params.get("curve")
        if not isinstance(curve, dict):
            raise FanR1SpecError("curve is required (flow_m3_s, pressure_rise_Pa, efficiency)")
        series = {key: curve.get(key) for key in _CURVE_KEYS}
        for key, value in series.items():
            if value is None:
                raise FanR1SpecError(f"curve.{key} is required")
        flow = [float(x) for x in series["flow_m3_s"]]
        dP_c = [float(x) for x in series["pressure_rise_Pa"]]
        eta_c = [float(x) for x in series["efficiency"]]
        if len(flow) != len(dP_c) or len(flow) != len(eta_c):
            raise FanR1SpecError(
                "curve.flow_m3_s, curve.pressure_rise_Pa and curve.efficiency "
                f"must have equal lengths (got {len(flow)}, {len(dP_c)}, {len(eta_c)})"
            )
        if len(flow) < 2:
            raise FanR1SpecError(f"curve.flow_m3_s needs at least 2 points (got {len(flow)})")
        if any(b <= a for a, b in zip(flow, flow[1:], strict=True)):
            raise FanR1SpecError("curve.flow_m3_s must be strictly increasing")

        speed_ratio = float(params.get("speed_ratio", 1.0))
        if speed_ratio <= 0:
            raise FanR1SpecError(f"speed_ratio {speed_ratio} must be > 0")
        curve_density = params.get("curve_density_kg_m3")
        if curve_density is not None and float(curve_density) <= 0:
            raise FanR1SpecError(f"curve_density_kg_m3 {curve_density} kg/m3 must be > 0")

        vapor = next((p for p in inlet.phases if p.kind == PhaseKind.VAPOR), None)
        if vapor is None:
            raise FanR1SpecError("inlet is not gas (no vapor phase)")
        rho_1 = vapor.density
        q_actual = inlet.mass_flow / rho_1
        q_equiv = q_actual / speed_ratio
        if q_equiv < flow[0] or q_equiv > flow[-1]:
            raise FanCurveRangeError(
                f"Q_eq {q_equiv:.6g} m3/s (Q {q_actual:.6g} m3/s at speed ratio "
                f"{speed_ratio:g}) outside the curve [{flow[0]:.6g}, {flow[-1]:.6g}]"
            )

        dP_c_q = float(PchipInterpolator(flow, dP_c, extrapolate=False)(q_equiv))
        eta_c_q = float(PchipInterpolator(flow, eta_c, extrapolate=False)(q_equiv))
        density_ratio = 1.0 if curve_density is None else rho_1 / float(curve_density)
        dP = dP_c_q * speed_ratio**2 * density_ratio
        eta = eta_c_q
        if dP <= 0:
            raise FanR1SpecError(f"pressure rise {dP} Pa must be > 0 (a fan raises pressure)")
        if not 0.0 < eta <= 1.0:
            raise FanR1SpecError(f"efficiency {eta} outside (0, 1]")

        r0 = Fan().solve(inlets, {"dP": dP, "eta": eta}, thermo)
        info = dict(r0.info)
        info.update(
            {
                "dP_Pa": dP,
                "eta": eta,
                "Q_actual_m3_s": q_actual,
                "Q_equiv_m3_s": q_equiv,
                "speed_ratio": speed_ratio,
                "density_ratio": density_ratio,
            }
        )
        return UnitResult(
            outlets=r0.outlets,
            duty_W=r0.duty_W,
            power_W=r0.power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 ventilation basis on the spec's five-point linear curve."""
        feed = {"T": 300.0, "P": 1.0e5, "molar_flow": 50.0, "composition": {"C1": 1.0}}
        params = {
            "curve": {
                "flow_m3_s": [0.5, 0.75, 1.0, 1.25, 1.5],
                "pressure_rise_Pa": [6000.0, 5000.0, 4000.0, 3000.0, 2000.0],
                "efficiency": [0.60, 0.65, 0.70, 0.75, 0.80],
            }
        }
        return {"inlet": feed}, params
