"""HEN block R0 (spec U-C 9).

Plugin kind "unit", name "hen_block", registered from the catalogue row.
Two hot + two cold optional ports with positional positional outlets
(hot_out_1/2, cold_out_1/2): a network STAGE whose every active stream
reaches its ``T_out_<port>`` target. The Linnhoff problem table
(:func:`ngdesign.units._physics.heat_balance.problem_table`, pure arithmetic
on CP*delta-T intervals from the flashed supply/target states) gives the
utility targets ``QH_min_W`` / ``QC_min_W`` and the pinch; the adapter does
NOT add utilities - the block balances at zero net duty (the R0 problem
rows are configured so targets match). ``dT_min`` defaults to 10 K.
Zero-flow ports pass through as inlet copies and stay out of the table.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import ProblemStream, problem_table


class HenBlock:
    """One heat-exchanger-network stage with utility targets (spec U-C 9)."""

    inlet_ports = ("hot_in_1", "hot_in_2", "cold_in_1", "cold_in_2")
    outlet_ports = ("hot_out_1", "hot_out_2", "cold_out_1", "cold_out_2")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        dT_min = float(params.get("dT_min", 10.0))
        if dT_min <= 0:
            raise ValueError(f"hen_block: dT_min {dT_min} K must be > 0")

        outlets: dict[str, StreamState] = {}
        streams: list[ProblemStream] = []
        for port in self.inlet_ports:
            inlet = inlets[port]
            if inlet.molar_flow <= 0.0:
                outlets[port.replace("_in", "_out")] = inlet.model_copy()
                continue
            target = params.get(f"T_out_{port}")
            if target is None:
                raise ValueError(f"hen_block: stream {port} has no T_out_{port} target")
            target = float(target)
            is_hot = port.startswith("hot")
            if is_hot and target >= inlet.T:
                raise ValueError(
                    f"hen_block: hot stream {port} target {target:.2f} K must be below "
                    f"the supply {inlet.T:.2f} K"
                )
            if not is_hot and target <= inlet.T:
                raise ValueError(
                    f"hen_block: cold stream {port} target {target:.2f} K must be above "
                    f"the supply {inlet.T:.2f} K"
                )
            out = thermo.flash_pt(inlet.composition, target, inlet.P, inlet.molar_flow)
            outlets[port.replace("_in", "_out")] = out
            cp = inlet.molar_flow * abs(out.enthalpy - inlet.enthalpy) / abs(target - inlet.T)
            streams.append(ProblemStream(T_supply=inlet.T, T_target=target, cp_W_per_K=cp, is_hot=is_hot))

        if not streams:
            raise ValueError("hen_block needs at least one stream with positive flow")
        targets = problem_table(tuple(streams), dT_min)

        h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
        h_out = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out - h_in,
            power_W=0.0,
            info={
                "QH_min_W": targets.qh_min_W,
                "QC_min_W": targets.qc_min_W,
                "pinch_T_hot_K": targets.pinch_T_hot_K,
                "pinch_T_cold_K": targets.pinch_T_cold_K,
                "dT_min_K": dT_min,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Kemp four-stream basis: 170->60 C (3 kW/K) + 150->30 C (1.5) against
        20->135 C (2) + 80->140 C (4), dT_min 10 K, QHmin 20 kW / QCmin 60 kW."""
        hot_1 = {"T": 443.15, "P": 1.0e5, "molar_flow": 101.01, "composition": {"N2": 1.0}}
        hot_2 = {"T": 423.15, "P": 1.0e5, "molar_flow": 50.505, "composition": {"N2": 1.0}}
        cold_1 = {"T": 293.15, "P": 1.0e5, "molar_flow": 67.34, "composition": {"N2": 1.0}}
        cold_2 = {"T": 353.15, "P": 1.0e5, "molar_flow": 134.68, "composition": {"N2": 1.0}}
        feeds = {"hot_in_1": hot_1, "hot_in_2": hot_2, "cold_in_1": cold_1, "cold_in_2": cold_2}
        params = {
            "T_out_hot_in_1": 333.15,
            "T_out_hot_in_2": 303.15,
            "T_out_cold_in_1": 408.15,
            "T_out_cold_in_2": 413.15,
            "dT_min": 10.0,
        }
        return feeds, params
