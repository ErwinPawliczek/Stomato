"""Multi-stream R0 exchanger (spec U-C 6).

Plugin kind "unit", name "multi_stream", registered from the
catalogue row. Four optional stream pairs - hot_in_1/2, cold_in_1/2 in,
positional hot_out_1/2, cold_out_1/2 out (outlet ports are NOT mirrored
inlet names). Every active side carries a ``T_out_<port>`` spec except
exactly one balance stream, which absorbs the residual duty so the unit
closes at zero net duty (spec U-C: 2 hot + 2 cold ports, zero-flow ports
allowed). Per-port duties keep the stream-direction signs: hot ports
release (positive), cold ports absorb (positive), keyed by inlet port name
- ``duty_hot_in_1_W``, ``duty_cold_in_1_W``, ... - plus ``min_approach_K``,
``pinch_T_hot_K`` and ``pinch_T_cold_K`` (the real temperatures of the
pinch zone ends, from the zoned composite check). A crossing arrangement is
refused with :class:`~ngdesign.units._physics.heat_balance.TemperatureCross`.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import MultiStreamSide, multi_stream


class MultiStreamExchanger:
    """Two hot + two cold stream pairs with one balance stream (spec U-C 6)."""

    inlet_ports = ("hot_in_1", "hot_in_2", "cold_in_1", "cold_in_2")
    outlet_ports = ("hot_out_1", "hot_out_2", "cold_out_1", "cold_out_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        hot_sides = tuple(
            MultiStreamSide(inlets[port], T_out=params.get(f"T_out_{port}"))
            for port in ("hot_in_1", "hot_in_2")
        )
        cold_sides = tuple(
            MultiStreamSide(inlets[port], T_out=params.get(f"T_out_{port}"))
            for port in ("cold_in_1", "cold_in_2")
        )
        result = multi_stream(hot_sides, cold_sides, thermo)

        info: dict[str, Any] = {
            "min_approach_K": result.min_approach_K,
            "pinch_T_hot_K": result.pinch_T_hot_K,
            "pinch_T_cold_K": result.pinch_T_cold_K,
        }
        for i, port in enumerate(("hot_in_1", "hot_in_2")):
            if inlets[port].molar_flow > 0.0:
                info[f"duty_{port}_W"] = result.hot_duties_W[i]  # released: positive
        for i, port in enumerate(("cold_in_1", "cold_in_2")):
            if inlets[port].molar_flow > 0.0:
                info[f"duty_{port}_W"] = result.cold_duties_W[i]  # absorbed: positive

        h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out = sum(s.enthalpy * s.molar_flow for s in (*result.hot_outs, *result.cold_outs))
        return UnitResult(
            outlets={
                "hot_out_1": result.hot_outs[0],
                "hot_out_2": result.hot_outs[1],
                "cold_out_1": result.cold_outs[0],
                "cold_out_2": result.cold_outs[1],
            },
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Smith Table 16.2 streams 1 and 3 basis: hot 250 -> 40 C (CP 0.15 MW/K)
        vs cold 20 -> ~180 C balance stream; the second pair is zero-flow."""
        hot_1 = {"T": 523.15, "P": 1.0e6, "molar_flow": 5050.0, "composition": {"N2": 1.0}}
        cold_1 = {"T": 293.15, "P": 1.0e6, "molar_flow": 6734.0, "composition": {"N2": 1.0}}
        hot_2 = {"T": 300.0, "P": 1.0e6, "molar_flow": 0.0, "composition": {"N2": 1.0}}
        cold_2 = {"T": 300.0, "P": 1.0e6, "molar_flow": 0.0, "composition": {"N2": 1.0}}
        feeds = {"hot_in_1": hot_1, "hot_in_2": hot_2, "cold_in_1": cold_1, "cold_in_2": cold_2}
        return feeds, {"T_out_hot_in_1": 313.15}
