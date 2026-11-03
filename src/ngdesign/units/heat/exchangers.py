"""Two-stream R0 exchangers: plate (liquid-liquid) and double pipe (gas-gas).

Plugin kind "unit", names "plate_exchanger" and "double_pipe_exchanger",
registered from the catalogue rows (spec U-C). Both run the shared
:func:`ngdesign.units._physics.heat_balance.two_stream` balance: ports
hot_in/cold_in -> hot_out/cold_out, exactly one active spec of ``duty_W`` /
``hot_T_out`` / ``cold_T_out`` (``min_approach_K`` solves the duty by
bisection), optional ``dP_hot`` / ``dP_cold`` pressure drops. A zero-flow
side passes through as a copy of its inlet with no duty. info: ``duty_W``
(heat transferred hot -> cold), ``LMTD_K``, ``lmtd_valid``, ``min_approach_K``,
``UA_W_K``; a spec that crosses the stream temperatures is refused with
:class:`~ngdesign.units._physics.heat_balance.TemperatureCross`.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.provenance.recorder import Recorder, active
from ngdesign.units._physics.heat_balance import TwoStreamSpec, two_stream


def trace_dp_defaults(rec: Recorder, params: dict[str, Any], names: tuple[str, ...]) -> None:
    """Record the zero pressure drops a two-stream exchanger assumes when none is given."""
    for name in names:
        if name not in params:
            rec.default(name, 0.0, "Pa", f"no pressure drop unless {name} is given (spec U-C)")


def trace_internal_duty(
    rec: Recorder, duty: float, inlets: dict[str, StreamState], outlets: dict[str, StreamState]
) -> None:
    """Record the unit-level duty of an internal exchanger: the enthalpy residual
    ``sum F_out h_out - sum F_in h_in`` (zero to round-off; the transferred heat is in info)."""
    inputs: dict[str, Any] = {}
    for port, state in (*inlets.items(), *outlets.items()):
        inputs[f"F[{port}]"] = (state, "molar_flow")
        inputs[f"h[{port}]"] = (state, "enthalpy")
    rec.equation("duty_W", duty, "W", "multi_stream_energy_balance", inputs)


class _TwoStreamExchanger:
    """Shared two-stream adapter body (ports and solve, no registration)."""

    inlet_ports = ("hot_in", "cold_in")
    outlet_ports = ("hot_out", "cold_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        rec = active()
        if rec is not None:
            trace_dp_defaults(rec, params, ("dP_hot", "dP_cold"))
        spec = TwoStreamSpec(
            duty_W=params.get("duty_W"),
            hot_T_out=params.get("hot_T_out"),
            cold_T_out=params.get("cold_T_out"),
            min_approach_K=params.get("min_approach_K"),
        )
        result = two_stream(
            inlets["hot_in"],
            inlets["cold_in"],
            spec,
            thermo,
            dP_hot=float(params.get("dP_hot", 0.0)),
            dP_cold=float(params.get("dP_cold", 0.0)),
        )
        # Both streams are internal: the unit-level duty is the (rounding-level)
        # enthalpy residual, the transferred heat is reported in info.
        h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out = result.hot_out.enthalpy * result.hot_out.molar_flow
        h_out += result.cold_out.enthalpy * result.cold_out.molar_flow
        if rec is not None:
            trace_internal_duty(
                rec, h_out - h_in, inlets, {"hot_out": result.hot_out, "cold_out": result.cold_out}
            )
        return UnitResult(
            outlets={"hot_out": result.hot_out, "cold_out": result.cold_out},
            duty_W=h_out - h_in,
            power_W=0.0,
            info={
                "duty_W": result.duty_W,
                "LMTD_K": result.lmtd_K,
                "lmtd_valid": 1.0 if result.lmtd_valid else 0.0,
                "min_approach_K": result.min_approach_K,
                "UA_W_K": result.UA_W_K,
            },
        )


class PlateExchanger(_TwoStreamExchanger):
    """Plate-and-frame exchanger, liquid-liquid water service (spec U-C 4)."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Lean/rich-style water trim: hot water 160 -> 80 C against cold 30 C water."""
        hot = {"T": 433.15, "P": 1.0e6, "molar_flow": 100.0, "composition": {"H2O": 1.0}}
        cold = {"T": 303.15, "P": 1.0e6, "molar_flow": 150.0, "composition": {"H2O": 1.0}}
        return {"hot_in": hot, "cold_in": cold}, {"hot_T_out": 353.15, "dP_hot": 2.0e4, "dP_cold": 2.0e4}


class DoublePipeExchanger(_TwoStreamExchanger):
    """Double-pipe (hairpin) exchanger, gas-gas service (spec U-C 5)."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Syngas trim cooler: N2 500 -> 400 K against equal N2 flow at 320 K."""
        hot = {"T": 500.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"N2": 1.0}}
        cold = {"T": 320.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"N2": 1.0}}
        return {"hot_in": hot, "cold_in": cold}, {"hot_T_out": 400.0, "dP_hot": 1.0e4, "dP_cold": 1.0e4}
