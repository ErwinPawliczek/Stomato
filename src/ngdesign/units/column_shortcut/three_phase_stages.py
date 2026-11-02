"""Three-phase (VLLE) stages, R2 (plan U-E 7, unit ``three_phase_stages``).

Plugin kind "unit", name "three_phase_stages". Ports ``feed`` -> ``distillate``
+ ``bottoms``. MESH with two liquids per stage on the column row's solvers:
the cascade carries one overall liquid xbar_j, and the split into two liquids
is the stage's own VLLE flash, so K_ij = y_ij / xbar_ij reads the vapour against
the pooled liquid, as does the stage liquid enthalpy (Block & Hegner, AIChE J.
22 (1976) 582; Cairns & Furzer, I&EC Res. 29 (1990) 1349). The pooling lives in
``_ThermoBox._liquid`` and is switched by the column's ``pool_liquids``; a stage
holding one liquid reads exactly as the plain column does. No decanter: both
liquids flow down together, and a stage's own liquids are never drawn apart.

After the solve each stage's contents L x + V y are flashed once at (T_j, P_j).
That flash supplies the reported split (``stage_<j>_n_liquids``,
``stage_<j>_liquid2_fraction``, ``stage_<j>_x1_<cid>``, ``stage_<j>_x2_<cid>``)
and an equilibrium gate: a stage whose flash vapour misses the solved y by more
than ``_STAGE_EQ_GATE`` is refused as unconverged, because the mesh gate falls
back on estimated K-values on single-phase states and can pass a profile that
holds no vapour at all.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import Column, ColumnConvergenceError

_ALLOWED_KEYS = frozenset({"n_stages", "condenser", "reboiler", "feed_stage", "pressure_profile", "specs"})
#: Largest |y_flash - y_solved| accepted on any stage: the plain two-tear
#: column's own floor (measured 0.0148 on its 16-stage example; the M/H gate
#: does not read the summation row). One-tear solves sit far below it.
_STAGE_EQ_GATE = 0.02
#: The same gate on a stage whose contents flash all-liquid: |T - T_bubble|, K.
_STAGE_T_GATE_K = 1.0
#: A stage holding less than this share of a phase has nothing to compare.
_PHASE_FLOOR = 1e-9


class ThreePhaseStagesError(ValueError):
    """Refusal: the three-phase column spec is invalid."""


def split_report(info: dict[str, float], comps: list[str], thermo: Thermo) -> dict[str, float]:
    """Flash every stage's contents: the liquid split report and the equilibrium gate."""
    report: dict[str, float] = {}
    two_liquid = 0
    for j in range(int(info["n_stages"])):
        liquid, vapour = info[f"stage_{j}_L_mol_s"], info[f"stage_{j}_V_mol_s"]
        total = liquid + vapour
        x = {c: info.get(f"stage_{j}_x_{c}", 0.0) for c in comps}
        y = {c: info.get(f"stage_{j}_y_{c}", 0.0) for c in comps}
        z = {c: (liquid * x[c] + vapour * y[c]) / total for c in comps}
        state = thermo.flash_pt(
            {c: v for c, v in z.items() if v > 0.0}, info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"], total
        )
        vap = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        liquids = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
        if vapour > _PHASE_FLOOR * total and liquid > _PHASE_FLOOR * total:
            if vap is None:
                # Solved T a hair under the bubble point (the summation row is
                # not gated): the contents flash all-liquid. Judge T instead.
                t_bubble = thermo.bubble_point(
                    {c: v for c, v in x.items() if v > 0.0}, P=info[f"stage_{j}_P_Pa"]
                ).T
                miss = abs(t_bubble - info[f"stage_{j}_T_K"]) / _STAGE_T_GATE_K * _STAGE_EQ_GATE
            else:
                miss = max(abs(vap.composition.get(c, 0.0) - y[c]) for c in comps)
            if miss > _STAGE_EQ_GATE:
                raise ColumnConvergenceError(
                    f"stage {j + 1} is not at phase equilibrium: its re-flash misses the solved "
                    f"vapour by {miss:.3g} (gate {_STAGE_EQ_GATE})"
                )
        report[f"stage_{j}_n_liquids"] = float(len(liquids))
        share = sum(p.mole_fraction for p in liquids)
        second = liquids[1].mole_fraction / share if len(liquids) > 1 else 0.0
        report[f"stage_{j}_liquid2_fraction"] = second
        for k, phase in enumerate(liquids[:2], start=1):
            for c in comps:
                report[f"stage_{j}_x{k}_{c}"] = phase.composition.get(c, 0.0)
        two_liquid += len(liquids) > 1
    report["two_liquid_stages"] = float(two_liquid)
    return report


class ThreePhaseStages:
    """MESH with a pooled two-liquid stage, over the public column API."""

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ThreePhaseStagesError("three_phase_stages requires the feed inlet stream")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise ThreePhaseStagesError(f"three_phase_stages refuses unknown parameter {key!r}")
        result = Column().solve({"feed": feed}, {**params, "pool_liquids": True}, thermo)
        info = {**result.info, **split_report(result.info, sorted(feed.composition), thermo)}
        return UnitResult(
            outlets={"distillate": result.outlets["distillate"], "bottoms": result.outlets["bottoms"]},
            duty_W=result.duty_W,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Illustrative: wet n-hexane/n-heptane boiled in a top-fed kettle column, 2 bar."""
        feed = {
            "T": 330.0,
            "P": 2.0e5,
            "molar_flow": 100.0,
            "composition": {"H2O": 0.05, "nC6": 0.5, "nC7": 0.45},
        }
        params = {
            "n_stages": 6,
            "condenser": "none",
            "reboiler": "kettle",
            "feed_stage": 1,
            "pressure_profile": 2.0e5,
            "specs": {"boilup_rate": 30.0},
        }
        return {"feed": feed}, params
