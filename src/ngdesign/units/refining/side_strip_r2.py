"""Side stripper section, R2 (plan U-H 4, unit ``side_strip``).

Plugin kind "unit", name "side_strip", level R2. Ports ``draw_in`` + ``steam_in``
-> ``overhead_out`` + ``bottoms_out``, as R0. Where R0 takes one K at one
temperature through Kremser, this level solves every stage: zero-tear MESH on the
column row's solvers (Boston & Sullivan 1974; Naphtali & Sandholm 1971), the draw
on stage 1, the steam on stage N, no condenser, no reboiler. Temperature falls
down the section as the light ends flash off and the steam heats nothing: that
profile, which R0 cannot see, sets the K-values.

**This is the section alone.** The draw and the steam are inlets. It couples to a
main column only through the flowsheet's recycle on ``overhead_out``; the
simultaneous stripper solve of spec S0-1c is a different thing and the column
still refuses it. A stage holding free water is refused
(:class:`SideStripR2Error`): the stage liquid here is one hydrocarbon liquid, and
reporting free water as dissolved is what S0-1c forbids. ``three_phase_stages``
models that case.

``duty_W`` is the boundary residual of a section with no exchanger, and is
reported as ``mesh_energy_residual_W`` too; an adiabatic section has no real duty.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.column_shortcut.three_phase_stages import split_report

_ALLOWED_KEYS = frozenset({"n_stages", "pressure_profile"})


class SideStripR2Error(ValueError):
    """Refusal: the stripper section spec is invalid or leaves its model."""


class SideStripR2:
    """Steam-stripped MESH section over the public column API."""

    inlet_ports = ("draw_in", "steam_in")
    outlet_ports = ("overhead_out", "bottoms_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        draw = inlets.get("draw_in")
        steam = inlets.get("steam_in")
        if draw is None or steam is None:
            raise SideStripR2Error("side_strip R2 requires the draw_in and steam_in streams")
        if draw.molar_flow <= 0.0 or steam.molar_flow <= 0.0:
            raise SideStripR2Error("side_strip R2 refuses a zero-flow inlet: nothing strips without steam")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise SideStripR2Error(f"side_strip R2 refuses unknown parameter {key!r}")
        n_stages = params.get("n_stages")
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 2:
            raise SideStripR2Error(f"n_stages must be an integer >= 2, got {n_stages!r}")

        result = Column().solve(
            {"feed": steam},
            {
                "n_stages": n_stages,
                "condenser": "none",
                "reboiler": "none",
                "feed_stage": n_stages,
                "pressure_profile": params.get("pressure_profile", draw.P),
                "feeds": [
                    {
                        "stage": 1,
                        "T": draw.T,
                        "P": draw.P,
                        "molar_flow": draw.molar_flow,
                        "composition": dict(draw.composition),
                    }
                ],
            },
            thermo,
        )
        comps = sorted(set(draw.composition) | set(steam.composition))
        report = split_report(result.info, comps, thermo)
        if report["two_liquid_stages"]:
            wet = [j + 1 for j in range(n_stages) if report[f"stage_{j}_n_liquids"] > 1.0]
            raise SideStripR2Error(
                f"free water on stages {wet}: this section carries one liquid (see three_phase_stages)"
            )

        overhead, bottoms = result.outlets["distillate"], result.outlets["bottoms"]
        h_in = draw.molar_flow * draw.enthalpy + steam.molar_flow * steam.enthalpy
        h_out = overhead.molar_flow * overhead.enthalpy + bottoms.molar_flow * bottoms.enthalpy
        hydrocarbon = sum(n for c, n in bottoms.component_flows().items() if c not in steam.composition)
        feed_hc = sum(n for c, n in draw.component_flows().items() if c not in steam.composition)
        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            mesh_energy_residual_W=h_out - h_in,
            stripped_frac=1.0 - hydrocarbon / feed_hc,
            steam_mol_s=steam.molar_flow,
            vapour_return_mol_s=overhead.molar_flow,
            bottoms_mol_s=bottoms.molar_flow,
        )
        return UnitResult(
            outlets={"overhead_out": overhead, "bottoms_out": bottoms},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Illustrative nC8/nC10/nC12 draw near its 469.2 K bubble point at 2 bar, 2 mol/s steam."""
        feeds = {
            "draw_in": {
                "T": 469.0,
                "P": 2.0e5,
                "molar_flow": 50.0,
                "composition": {"nC8": 0.2, "nC10": 0.5, "nC12": 0.3},
            },
            "steam_in": {"T": 520.0, "P": 2.2e5, "molar_flow": 2.0, "composition": {"H2O": 1.0}},
        }
        return feeds, {"n_stages": 4}
