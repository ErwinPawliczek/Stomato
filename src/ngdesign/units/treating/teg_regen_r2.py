"""Stage-wise TEG regenerator with a stripping-gas (Stahl) section (spec teg_regen R2).

Plugin kind "unit", name "teg_regen", catalogue level R2. Ports are the R0
regenerator's (``rich_in``, ``stripping_gas_in`` -> ``lean_out``, ``water_out``);
the R0 module is not edited and is imported read-only. Registration comes from
``data/unit_models/treating.yaml`` (``units.catalogue.register_all``); the class
carries no ``@register`` decorator.

Method: R0's boiling-line reboiler followed by an N-stage stripping column
(the Stahl column) counter-current to the stripping gas, isothermal at
(T_reboiler, P). The lean leaving the reboiler sits on the boiling-line water
fraction ``x_reb`` (R0's own solve, ``_lean_water_mole_fraction`` — the one
owner) and flows down the stages; each stage sits at water-activity equilibrium
on the Parrish-Won-Baltatu line. The purity enhancement is computed, not read
from a chart.

Mole ratios on the solute-free bases: gas ``Y = n_w/G`` with the dry gas
``G`` = the non-water molar flow of ``stripping_gas_in``; liquid
``X = n_w/S`` with the TEG molar flow ``S`` of ``rich_in``. The gas enters the
bottom with its own water ratio ``Y_{N+1}`` (0 for dry gas).

- Stage balance: ``S * (X_{j-1} - X_j) = G * (Y_j - Y_{j+1})`` — the same
  equation the shared march solves, written for stripping.
- Stage equilibrium: ``y_j = m(T_reb, P, x_j) * x_j``, ``m`` taken read-only
  from the one owner, ``ngdesign.units.teg_activity``.

The stage system is solved by ``teg_stagewise.countercurrent_march`` (never
copied), with ``x_of_y`` the TEG equilibrium inverse built by
``teg_stagewise.teg_x_of_y`` at (T_reb, P) — the same construction the R2
contactor uses. ``X_lean = X_N`` is the lean leaving the bottom stage.

Reduction to R0: with no stripping gas (port absent or zero flow) or
``n_stages == 0`` the lean is at ``x_reb`` and the result is R0's, field for
field — the code delegates to ``TEGRegen().solve`` and adds the R2 info keys.
The march itself is singular as G -> 0, so the delegation path, not the march,
carries exact zero (the tests also check the G -> 0 limit of the march and
pin its measured sqrt(G) gap and bracket-scan refusal).

Overhead: the rich feed's water minus the lean water, plus all absorbed
lights, plus all the stripping gas (dry plus its own water). Everything leaves
through ``water_out`` (no condenser, as in R0). Duty is the enthalpy
difference across the unit on the actual inlet states (the R0 convention).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.treating.teg_regen import (
    DEFAULT_P,
    DEFAULT_T_REBOILER,
    TEGRegen,
    TEGRegenError,
    _lean_water_mole_fraction,
    _mw,
)
from ngdesign.units.treating.teg_stagewise import countercurrent_march, teg_x_of_y

__all__ = ["TEGRegenR2"]

#: The Parrish-Won-Baltatu activity correlation's fitted temperature range, K
#: (the owner correlation's fit range, as R0 flags it).
_PARRISH_T_MIN, _PARRISH_T_MAX = 300.0, 380.0

#: Components the liquid carries; everything else in the rich feed is a light.
_TEG = "TEG"
_WATER = "H2O"

_ALLOWED_PARAMS = frozenset({"T_reboiler", "P", "n_stages"})


def _ratio_to_fraction(r: float) -> float:
    """Mole ratio [mol solute / mol carrier] -> wet mole fraction."""
    return r / (1.0 + r)


def _fraction_to_ratio(y: float) -> float:
    """Wet mole fraction -> mole ratio [mol solute / mol carrier]."""
    return y / (1.0 - y)


def _n_stages_param(params: dict[str, Any]) -> int:
    """Validate ``n_stages``: default 2 when absent, a true integer, >= 0."""
    n_stages = params.get("n_stages", 2)
    if isinstance(n_stages, bool) or not isinstance(n_stages, int):
        raise TEGRegenError(f"n_stages must be an integer, got {n_stages!r}")
    if n_stages < 0:
        raise TEGRegenError(f"n_stages must be >= 0, got {n_stages}")
    return int(n_stages)


class TEGRegenR2:
    """R2 TEG regenerator: boiling-line reboiler plus N Stahl stripping stages."""

    inlet_ports: tuple[str, ...] = ("rich_in", "stripping_gas_in")
    outlet_ports: tuple[str, ...] = ("lean_out", "water_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        unknown = sorted(set(params) - _ALLOWED_PARAMS)
        if unknown:
            raise TEGRegenError(f"unknown parameter key(s): {', '.join(unknown)}")
        n_stages = _n_stages_param(params)

        T_reb = float(params.get("T_reboiler", DEFAULT_T_REBOILER))
        P = float(params.get("P", DEFAULT_P))
        if not T_reb > 0.0:
            raise TEGRegenError(f"T_reboiler must be positive, got {T_reb}")
        if not P > 0.0:
            raise TEGRegenError(f"P must be positive, got {P}")

        rich_in = inlets["rich_in"]
        gas_in = inlets.get("stripping_gas_in")

        # Zero-gas path (or N = 0): the lean is at x_reb and the result is
        # R0's exactly. Delegate; the march is singular as G -> 0, so the
        # delegation path carries exact zero.
        if gas_in is None or gas_in.molar_flow <= 0.0 or n_stages == 0:
            return self._delegate(rich_in, T_reb, P, n_stages, thermo)
        gas_flow = gas_in.molar_flow

        # Nonzero stripping gas: refuse a gas carrying TEG (it would dissolve
        # into the lean and falsify the water-only march).
        if gas_in.composition.get(_TEG, 0.0) > 0.0:
            raise TEGRegenError(
                "stripping_gas_in: a stripping gas carrying TEG is refused -- the gas dissolves "
                "into the lean glycol and the water-only stage march does not apply"
            )

        if not rich_in.phases:
            raise TEGRegenError("rich_in must be a flashed stream (has phases)")
        rich = {cid: frac * rich_in.molar_flow for cid, frac in rich_in.composition.items()}
        S = rich.get(_TEG, 0.0)
        if S <= 0.0:
            raise TEGRegenError("rich_in carries no TEG; not a rich glycol stream")
        n_water_rich = rich.get(_WATER, 0.0)

        # As R0: the boiling line at (T_reb, P) raises the no-boiling refusal
        # itself and hands over x_reb, the liquid entering the top stage.
        x_reb = _lean_water_mole_fraction(T_reb, P)
        X_0 = _fraction_to_ratio(x_reb)

        # Solute-free gas flow and its own water ratio Y_{N+1} (0 for dry gas).
        y_water_gas = gas_in.composition.get(_WATER, 0.0)
        G = gas_flow * (1.0 - y_water_gas)
        Y_np1 = _fraction_to_ratio(y_water_gas)

        y_profile, x_profile = countercurrent_march(G, S, X_0, Y_np1, n_stages, teg_x_of_y(T_reb, P))
        X_lean = x_profile[-1]
        if X_lean > X_0:
            # Unreachable for dry gas (the march cannot push the liquid
            # wetter than its feed against a stripping gradient), but kept as
            # the spec's cap: refuse rather than report a degenerate lean.
            raise TEGRegenError(
                f"n_stages march produced no stripping (lean ratio {X_lean:.6g} above the "
                f"boiling-line ratio {X_0:.6g}); check the stripping gas water content"
            )
        x_lean = _ratio_to_fraction(X_lean)
        n_water_lean = S * X_lean

        # Lean outlet: all the TEG plus the staged-held water, at (T_reb, P).
        n_lean = S * (1.0 + X_lean)
        lean_comp = {_TEG: S / n_lean, _WATER: n_water_lean / n_lean}
        lean_out = thermo.flash_pt(lean_comp, T_reb, P, n_lean)

        # Overhead: the rest of the rich water, every absorbed light, and all
        # the stripping gas (dry plus the water it brought in).
        overhead = {cid: n for cid, n in rich.items() if cid not in (_TEG, _WATER)}
        for cid, frac in gas_in.composition.items():
            if cid != _TEG:
                overhead[cid] = overhead.get(cid, 0.0) + frac * gas_flow
        n_water_overhead = n_water_rich - n_water_lean
        if n_water_overhead < 0.0:
            raise TEGRegenError(
                "rich_in carries less water than the boiling-line hold at the reboiler "
                f"temperature -- nothing to strip ({n_water_rich:.6g} mol/s feed water vs "
                f"{n_water_lean:.6g} mol/s at the boiling line)"
            )
        overhead[_WATER] = overhead.get(_WATER, 0.0) + n_water_overhead
        total_overhead = sum(overhead.values())
        overhead_comp = {cid: n / total_overhead for cid, n in overhead.items()}
        water_out = thermo.flash_pt(overhead_comp, T_reb, P, total_overhead)

        duty_W = (
            lean_out.enthalpy * lean_out.molar_flow
            + water_out.enthalpy * water_out.molar_flow
            - rich_in.enthalpy * rich_in.molar_flow
            - gas_in.enthalpy * gas_in.molar_flow
        )

        mw_teg, mw_water = _mw(_TEG), _mw(_WATER)
        mass_teg = S * mw_teg
        lean_mass_fraction = mass_teg / (mass_teg + n_water_lean * mw_water)
        boiling_mass_fraction = mass_teg / (mass_teg + S * X_0 * mw_water)
        rich_mass = sum(n * _mw(cid) for cid, n in rich.items())
        info: dict[str, float] = {
            "lean_teg_mass_fraction": lean_mass_fraction,
            "lean_water_mole_fraction": x_lean,
            "lean_teg_mass_fraction_boiling_line": boiling_mass_fraction,
            "purity_enhancement_wt_pct": 100.0 * (lean_mass_fraction - boiling_mass_fraction),
            "rich_teg_mass_fraction": mass_teg / rich_mass,
            "water_stripped_mol_s": n_water_overhead,
            "water_held_in_lean_mol_s": n_water_lean,
            "lean_out_mol_s": n_lean,
            "overhead_mol_s": total_overhead,
            "reboiler_T_K": T_reb,
            "regenerator_P_Pa": P,
            "n_stages": float(n_stages),
            "stripping_gas_mol_s": G,
            "activity_extrapolated": 0.0 if _PARRISH_T_MIN <= T_reb <= _PARRISH_T_MAX else 1.0,
        }
        for j in range(1, n_stages + 1):
            info[f"stage_{j}_x_H2O"] = _ratio_to_fraction(x_profile[j - 1])
            info[f"stage_{j}_y_H2O"] = _ratio_to_fraction(y_profile[j - 1])
        return UnitResult(
            outlets={"lean_out": lean_out, "water_out": water_out},
            duty_W=duty_W,
            info=info,
        )

    def _delegate(
        self,
        rich_in: StreamState,
        T_reb: float,
        P: float,
        n_stages: int,
        thermo: Thermo,
    ) -> UnitResult:
        """Zero-gas path: R0's solve verbatim, with the R2 info keys added."""
        result = TEGRegen().solve(
            {"rich_in": rich_in},
            {"T_reboiler": T_reb, "P": P},
            thermo,
        )
        result.info["n_stages"] = float(n_stages)
        result.info["stripping_gas_mol_s"] = 0.0
        result.info["lean_teg_mass_fraction_boiling_line"] = result.info["lean_teg_mass_fraction"]
        result.info["purity_enhancement_wt_pct"] = 0.0
        return result
