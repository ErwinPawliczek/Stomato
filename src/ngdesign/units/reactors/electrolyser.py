"""Electrolyser / fuel-cell stack: Faraday's law at R0 (spec U-F).

Plugin kind "unit", name "electrolyser_stack".

Method (spec): ports inlet -> h2_out + o2_out. Params ``current_A``,
``n_cells``, ``cell_voltage_V`` and ``faradaic_efficiency`` (default 1.0). The
stack splits its feed: H2O is consumed at n(H2) = η·I·N/(2F) (1 mol water per
mol hydrogen), the hydrogen leaves pure on ``h2_out``, and everything else —
including the coproduct oxygen — leaves on ``o2_out``. power = V·I·N is electrical work; the isothermal duty carries the balance
(negative = heat removal). ``info`` reports the thermoneutral voltage computed
from the actual stream balance, (H_out − H_in)/(2F·n_H2): on a liquid-water
feed that is the HHV value (1.481 V at 298.15 K, less at warmer feeds); a
vapour feed gives the LHV value. It is a check on the formation data, not an
echo of an input.

Refusals: feeds already containing H2 or O2 (products present at R0 keeps the
split unambiguous), feeds without enough water, efficiency outside (0, 1],
negative current or voltage, and fewer than one cell.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors._shared import z_from

#: CODATA 2018 Faraday constant, C/mol.
FARADAY = 96485.33212


class ElectrolyserStack:
    """Faradaic water-electrolysis stack (spec U-F, R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("h2_out", "o2_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        current = float(params["current_A"])
        n_cells = float(params["n_cells"])
        voltage = float(params["cell_voltage_V"])
        eta = float(params.get("faradaic_efficiency", 1.0))
        if current < 0.0:
            raise ValueError(f"current {current} A is negative")
        if n_cells < 1.0:
            raise ValueError(f"n_cells {n_cells} is fewer than one cell")
        if voltage < 0.0:
            raise ValueError(f"cell_voltage_V {voltage} is negative")
        if not 0.0 < eta <= 1.0:
            raise ValueError(f"faradaic_efficiency {eta} outside (0, 1]")
        if "H2" in inlet.composition or "O2" in inlet.composition:
            raise ValueError(
                "electrolyser R0 refuses feeds already containing H2 or O2 "
                "(the product split would be ambiguous)"
            )
        n_h2 = eta * current * n_cells / (2.0 * FARADAY)
        n_in_h2o = inlet.molar_flow * inlet.composition.get("H2O", 0.0)
        if n_in_h2o < n_h2:
            raise ValueError(
                f"feed carries {n_in_h2o:.6g} mol/s H2O but the stack consumes "
                f"{n_h2:.6g} mol/s at {eta:.3f} Faradaic efficiency"
            )

        power = voltage * current * n_cells
        n_out = dict(inlet.component_flows())
        n_out["H2O"] = n_out.get("H2O", 0.0) - n_h2
        n_o2_total = n_out.get("O2", 0.0) + 0.5 * n_h2
        n_out.pop("O2", None)

        h2_out = thermo.flash_pt({"H2": 1.0}, inlet.T, inlet.P, n_h2)
        amounts = {**{cid: n for cid, n in n_out.items() if n > 0.0}, "O2": n_o2_total}
        o2_out = thermo.flash_pt(z_from(amounts), inlet.T, inlet.P, sum(amounts.values()))
        h_in = enthalpy_with_formation(inlet)
        h_out = enthalpy_with_formation(h2_out) + enthalpy_with_formation(o2_out)
        duty = h_out - h_in - power
        v_thermoneutral = (h_out - h_in) / (2.0 * FARADAY * n_h2)
        return UnitResult(
            outlets={"h2_out": h2_out, "o2_out": o2_out},
            duty_W=duty,
            power_W=power,
            info={
                "thermoneutral_voltage_V": v_thermoneutral,
                "faradaic_efficiency": eta,
                "h2_production_mol_s": n_h2,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """100-cell alkaline-style stack: 2000 A at 1.75 V, η = 0.98, steam feed.

        Closed form: n(H2) = 0.98·2000·100/(2F) ≈ 1.0157 mol/s, n(O2) ≈
        0.5078 mol/s, power 350 kW.
        """
        feed = {
            "T": 353.15,
            "P": 3.0e6,
            "molar_flow": 50.0,
            "composition": {"H2O": 1.0},
        }
        params = {
            "current_A": 2000.0,
            "n_cells": 100.0,
            "cell_voltage_V": 1.75,
            "faradaic_efficiency": 0.98,
        }
        return {"inlet": feed}, params
