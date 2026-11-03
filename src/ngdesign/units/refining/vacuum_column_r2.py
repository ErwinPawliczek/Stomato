"""Vacuum column, R2 (plan U-H 5, unit ``vacuum_column``).

Plugin kind "unit", name "vacuum_column", level R2. Ports ``feed_in`` ->
``overhead`` + ``vgo_out`` + ``bottoms``, as R0. Where R0 splits the residue
at sharp cut points, this level solves every stage on the column row's MESH
solvers (Boston & Sullivan 1974; Naphtali & Sandholm 1971): the flashed
residue enters the bottom stage, there is no condenser and no reboiler, and a
top pumparound - liquid drawn from the VGO stage, cooled to a fixed return
temperature and returned to stage 1 - condenses the gas oil. The VGO product
is a liquid draw on the same stage; the stage-1 vapour is ``overhead``, the
bottom stage's liquid ``bottoms``. Zero degrees of freedom: the feed, the
pumparound and the draw fix the column.

The column cold-starts by relaxation (``initialization: relaxation``): the
residue boils over hundreds of kelvin, and the standard feed-flash start
stalls (measured on the 19-pseudo example feed: M ~ 1.0 after 65 s; from the
relaxation start the column converges in ~4 s).

``duty_W`` is the column's net duty, the pumparound cooler's (negative); it is
reported as ``pa_duty_W`` too. All SI: K, Pa abs, mol/s, J/mol, W.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.refining._cuts import RefiningSpecError

_ALLOWED_KEYS = frozenset(
    {
        "n_stages",
        "vgo_stage",
        "vgo_rate_mol_s",
        "pumparound_flow_mol_s",
        "pumparound_return_T_K",
        "pressure_profile",
    }
)


def _positive(params: dict[str, Any], key: str) -> float:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0.0:
        raise RefiningSpecError(f"{key} must be a positive number, got {value!r}")
    return float(value)


class VacuumColumnR2:
    """Pumparound-condensed vacuum column over the public column API."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("overhead", "vgo_out", "bottoms")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example residue (the light crude's pseudos above 668.7 K at
        653.15 K and 40 mmHg, Gary et al. p. 77), 6 stages, a 600 mol/s top
        pumparound returned at 450 K, 300 mol/s of VGO drawn on stage 2."""
        from ngdesign.units.refining.vacuum_column import VacuumColumn

        feeds, _ = VacuumColumn.example_case()
        return feeds, {
            "n_stages": 6,
            "vgo_stage": 2,
            "vgo_rate_mol_s": 300.0,
            "pumparound_flow_mol_s": 600.0,
            "pumparound_return_T_K": 450.0,
        }

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed_in")
        if feed is None or feed.molar_flow <= 0.0:
            raise RefiningSpecError("feed_in: a residue inlet stream with positive flow is required")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise RefiningSpecError(f"vacuum_column R2 refuses unknown parameter {key!r}")
        n_stages = params.get("n_stages")
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 3:
            raise RefiningSpecError(f"n_stages must be an integer >= 3, got {n_stages!r}")
        vgo_stage = params.get("vgo_stage", 2)
        if not isinstance(vgo_stage, int) or isinstance(vgo_stage, bool) or not 2 <= vgo_stage < n_stages:
            raise RefiningSpecError(
                f"vgo_stage must be an integer in [2, n_stages - 1] (below the pumparound "
                f"return on stage 1, above the feed stage), got {vgo_stage!r}"
            )
        vgo = _positive(params, "vgo_rate_mol_s")
        if vgo >= feed.molar_flow:
            raise RefiningSpecError(f"vgo_rate_mol_s {vgo} must be below the feed flow {feed.molar_flow}")
        pa_flow = _positive(params, "pumparound_flow_mol_s")
        pa_t = _positive(params, "pumparound_return_T_K")
        result = Column().solve(
            {"feed": feed},
            {
                "n_stages": n_stages,
                "condenser": "none",
                "reboiler": "none",
                "feed_stage": n_stages,
                "pressure_profile": params.get("pressure_profile", feed.P),
                "draws": [{"stage": vgo_stage, "phase": "liquid", "flow_mol_s": vgo}],
                "pumparounds": [
                    {
                        "name": "top",
                        "draw_stage": vgo_stage,
                        "return_stage": 1,
                        "flow_mol_s": pa_flow,
                        "return_T_K": pa_t,
                    }
                ],
                "initialization": "relaxation",
            },
            thermo,
        )
        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        info.update(
            n_stages=float(n_stages),
            ns_used=result.info["ns_used"],
            pa_duty_W=result.info["pa_top_duty_W"],
            pa_draw_T_K=result.info["pa_top_draw_T_K"],
            overhead_mol_s=result.outlets["distillate"].molar_flow,
            vgo_mol_s=result.outlets["side_draw"].molar_flow,
            bottoms_mol_s=result.outlets["bottoms"].molar_flow,
        )
        return UnitResult(
            outlets={
                "overhead": result.outlets["distillate"],
                "vgo_out": result.outlets["side_draw"],
                "bottoms": result.outlets["bottoms"],
            },
            duty_W=result.duty_W,
            power_W=0.0,
            info=info,
        )
