"""Claus sulfur-recovery unit, R0 adapter (spec U-G). NOT registered.

Catalogue row ``sulfur_recovery`` stays **planned**: this adapter implements the
R0 level the plan describes, but the row cannot be flipped yet because the
locked property test ``tests/property/test_unit_balances.py`` has no reactive
branch -- its per-component molar assertion and plain-enthalpy energy check both
fail for any reaction unit (measured on issue #212: H2S in 3.0000 vs 0.8000 out
at 1e-5 tolerance; energy miss -5.256e5 W at ~37 W tolerance, because the file
checks sensible enthalpy, not formation-basis enthalpy). The file is locked
(orchestrator-owned) and the spec grants no edit to it, so registering the row
would fail the suite. Flipping the row needs the orchestrator's locked-test
extension first.

Method (spec U-G, R0: balances plus a spec):

    acid_gas_in (the burner mixture) -> tail_gas_out + sulfur_out

- **Two inline reactions ride the params**, as a ``ReactionSet`` payload under
  ``reaction_set`` (the U-F pattern (a): the flowsheet owns the chemistry): the
  thermal burn ``H2S + 1.5 O2 -> SO2 + H2O`` and the Claus reaction
  ``2 H2S + SO2 -> 2 H2O + 0.375 S8``. The set is validated to be that pair
  (burn on H2S first, Claus on SO2 second).

- **No air port** (fixed by the catalogue row, U-00): the oxygen rides the
  ``acid_gas_in`` stream -- the feed is the burner mixture of acid gas and air.
  The unit burns exactly one third of the feed H2S (the textbook Claus split:
  the burn must supply exactly the SO2 the Claus reaction consumes) and refuses
  a feed whose O2 falls short of that stoichiometry; excess O2 passes through
  unreacted and is reported in info.

- **Thermal stage**: the burn extent, then the Claus extent at the given
  thermal conversion (fraction of the freshly formed SO2 consumed).

- **Catalytic stages**: each at a given conversion, or at a given equilibrium
  approach (K): the extent solves ``Q(xi) = ln K(T_stage + approach)`` on
  ideal-gas activities ``y_i P / P0`` (P0 = 1 bar, the NIST-JANAF basis the
  formation data behind ``kinetics.ln_keq`` is built on), bisected between zero
  and the stoichiometric limit; a feed already at or past equilibrium holds at
  zero extent.

- **Ports**: all condensed S8 leaves through ``sulfur_out`` as a pure flashed
  stream at the condenser conditions; the remaining gas leaves through
  ``tail_gas_out`` at the same conditions. Condensation is modelled as complete
  per stage (R0 shortcut; no dew-point check). The duty closes the
  formation-basis element balance the harness's reactive branch will check.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import ReactionSet
from ngdesign.units._physics.kinetics import (
    KineticsError,
    ReactionExtentError,
    apply_extents,
    enthalpy_with_formation,
    ln_keq,
)

__all__ = ["SulfurRecovery", "SulfurRecoveryError"]

#: Ideal-gas standard-state pressure, Pa (1 bar, the NIST-JANAF basis of the
#: formation data behind ``kinetics.ln_keq``).
_P0 = 1.0e5

#: Fraction of the feed H2S burned in the thermal stage: the classic Claus
#: split -- the burn supplies exactly the SO2 the Claus reaction consumes
#: (1/3 of the H2S, since 2 H2S + SO2 -> 2 H2O + 0.375 S8).
_BURN_FRACTION = 1.0 / 3.0

#: Condensed sulfur species (databank-verified: S6 and S8 carry formula and
#: formation data and flash through PR; S2 lacks critical constants). R0
#: condenses S8 only.
_SULFUR_SPECIES = ("S8",)

#: Bisection iteration budget for approach-based extents.
_MAX_BISECT_ITERS = 100


class SulfurRecoveryError(ValueError):
    """An acid gas, spec or reaction set the R0 Claus unit refuses."""


def _require(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise SulfurRecoveryError(f"missing required param {key!r}")
    return params[key]


def _positive(params: dict[str, Any], key: str) -> float:
    value = float(_require(params, key))
    if not value > 0.0:
        raise SulfurRecoveryError(f"param {key!r} must be positive, got {value}")
    return value


def _approach_extent(
    n: dict[str, float], claus: Any, T: float, approach_K: float, P: float
) -> tuple[float, float]:
    """Extent of the Claus reaction at an equilibrium approach, mol/s.

    An adiabatic catalyst bed falls ``approach_K`` short of equilibrium: its
    exit composition equals the equilibrium composition at ``T + approach_K``
    (warmer, hence less converted -- the standard direction for the exothermic
    Claus reaction). Solves ``Q(xi) = ln K(T + approach)`` with
    ``Q = sum(nu_i * ln(y_i P / P0))`` on ideal-gas activities, bisected between
    zero and the stoichiometric limit. Returns (extent, ln K used). Q is
    monotone increasing in xi: the reactants H2S and SO2 thin out while the
    products (water, and total moles via nu_sum = +0.625) grow.
    """
    T_eq = T + approach_K
    ln_k = ln_keq(claus, T_eq)
    nu = claus.stoichiometry

    def q_of(xi: float) -> float:
        trial = dict(n)
        for cid, coef in nu.items():
            trial[cid] = trial.get(cid, 0.0) + xi * coef
        n_total = sum(trial.values())
        q = 0.0
        for cid, coef in nu.items():
            y = max(trial[cid] / n_total, 1e-300)
            q += coef * math.log(y * P / _P0)
        return q

    xi_max = min(-n.get(cid, 0.0) / coef for cid, coef in nu.items() if coef < 0.0) * (1.0 - 1e-12)
    if q_of(0.0) >= ln_k:
        return 0.0, ln_k  # at or past equilibrium: hold
    if q_of(xi_max) <= ln_k:
        return xi_max, ln_k  # equilibrium limit lies beyond the feed
    lo, hi = 0.0, xi_max
    for _ in range(_MAX_BISECT_ITERS):
        mid = 0.5 * (lo + hi)
        if q_of(mid) < ln_k:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi), ln_k


def _split_sulfur(n: dict[str, float]) -> tuple[dict[str, float], float]:
    """Pull the condensed sulfur species out of a mole table, mol/s."""
    gas = {cid: n for cid, n in n.items() if cid not in _SULFUR_SPECIES}
    sulfur = sum(n.get(cid, 0.0) for cid in _SULFUR_SPECIES)
    return gas, sulfur


class SulfurRecovery:
    """R0 Claus sulfur recovery over a flowsheet-owned two-reaction set.

    NOT registered: the catalogue row ``sulfur_recovery`` stays planned until
    the locked property balance test grows a reactive branch (module docstring).
    """

    inlet_ports: tuple[str, ...] = ("acid_gas_in",)
    outlet_ports: tuple[str, ...] = ("tail_gas_out", "sulfur_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["acid_gas_in"]
        if not feed.phases:
            raise SulfurRecoveryError("acid_gas_in must be a flashed stream (has phases)")

        T_thermal = _positive(params, "T_thermal")
        P = _positive(params, "P")
        T_cond = _positive(params, "T_condenser")
        thermal_conversion = float(_require(params, "thermal_conversion"))
        if not 0.0 <= thermal_conversion <= 1.0:
            raise SulfurRecoveryError(
                f"param 'thermal_conversion' must be a fraction in [0, 1], got {thermal_conversion}"
            )
        stages = _require(params, "catalytic_stages")
        if not isinstance(stages, list):
            raise SulfurRecoveryError("param 'catalytic_stages' must be a list of stage specs")
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict) or "T" not in stage:
                raise SulfurRecoveryError(f"catalytic_stages[{i}] must be a dict with a 'T' key")
            stage_T = float(stage["T"])
            if not stage_T > 0.0:
                raise SulfurRecoveryError(f"catalytic_stages[{i}]['T'] must be positive, got {stage_T}")
            has_conversion = "conversion" in stage
            has_approach = "approach_K" in stage
            if has_conversion == has_approach:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}] must set exactly one of 'conversion' or 'approach_K'"
                )
            if has_conversion and not 0.0 <= float(stage["conversion"]) <= 1.0:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}]['conversion'] must be a fraction in [0, 1], "
                    f"got {stage['conversion']}"
                )
            if has_approach and float(stage["approach_K"]) < 0.0:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}]['approach_K'] must be non-negative, got {stage['approach_K']}"
                )

        rset = ReactionSet.model_validate(_require(params, "reaction_set"))
        if len(rset.reactions) != 2:
            raise SulfurRecoveryError(
                f"reaction set {rset.id!r}: the R0 Claus unit needs exactly 2 reactions "
                f"(the H2S burn and the Claus reaction), got {len(rset.reactions)}"
            )
        burn, claus = rset.reactions
        if burn.base_component != "H2S":
            raise SulfurRecoveryError(
                f"reaction set {rset.id!r}: the first reaction must burn H2S "
                f"(base_component 'H2S'), got {burn.base_component!r}"
            )
        if claus.base_component != "SO2":
            raise SulfurRecoveryError(
                f"reaction set {rset.id!r}: the second (Claus) reaction must consume SO2 "
                f"(base_component 'SO2'), got {claus.base_component!r}"
            )
        if "O2" not in burn.stoichiometry:
            raise SulfurRecoveryError(
                f"reaction set {rset.id!r}: the burn reaction carries no O2 -- the feed is the "
                "burner mixture, so the burn must consume the feed oxygen"
            )

        n = {cid: frac * feed.molar_flow for cid, frac in feed.composition.items()}
        n_h2s_feed = n.get("H2S", 0.0)
        if n_h2s_feed <= 0.0:
            raise SulfurRecoveryError("acid_gas_in carries no H2S; there is no sulfur to recover")

        # Thermal stage: burn exactly one third of the H2S, air-stoichiometric.
        xi_burn = _BURN_FRACTION * n_h2s_feed
        o2_needed = -burn.stoichiometry["O2"] * xi_burn
        o2_available = n.get("O2", 0.0)
        if o2_available < o2_needed * (1.0 - 1e-9):
            raise SulfurRecoveryError(
                f"acid_gas_in carries {o2_available:.6g} mol/s of O2 but burning "
                f"{_BURN_FRACTION:.4g} of the H2S needs {o2_needed:.6g} mol/s -- enrich the burner "
                "air or the feed cannot sustain the Claus split"
            )
        try:
            n = apply_extents(n, rset, [xi_burn, 0.0])
            xi_thermal = thermal_conversion * n.get("SO2", 0.0)
            n = apply_extents(n, rset, [0.0, xi_thermal])
        except ReactionExtentError as exc:
            raise SulfurRecoveryError(f"thermal stage refuses the feed: {exc}") from exc
        gas, sulfur = _split_sulfur(n)

        # Catalytic stages: given conversion or equilibrium approach each.
        info: dict[str, float] = {
            "burn_extent_mol_s": xi_burn,
            "thermal_extent_mol_s": xi_thermal,
            "o2_excess_mol_s": o2_available - o2_needed,
            "n_catalytic_stages": float(len(stages)),
        }
        for i, stage in enumerate(stages):
            T_stage = float(stage["T"])
            if "conversion" in stage:
                xi = float(stage["conversion"]) * gas.get("SO2", 0.0)
                # Reported for reference; on the conversion path it does not
                # set the extent. Finite on purpose: info must serialize and
                # compare equal run to run (no NaN).
                stage_ln_k = ln_keq(claus, T_stage)
            else:
                try:
                    xi, stage_ln_k = _approach_extent(gas, claus, T_stage, float(stage["approach_K"]), P)
                except KineticsError as exc:  # bad equilibrium data: same refusal class
                    raise SulfurRecoveryError(f"catalytic stage {i}: {exc}") from exc
            try:
                gas = apply_extents(gas, rset, [0.0, xi])
            except ReactionExtentError as exc:
                raise SulfurRecoveryError(f"catalytic stage {i} refuses its extent: {exc}") from exc
            gas, sulfur_stage = _split_sulfur(gas)
            sulfur += sulfur_stage
            info[f"stage_{i}_extent_mol_s"] = xi
            info[f"stage_{i}_T_K"] = T_stage
            info[f"stage_{i}_ln_keq"] = stage_ln_k

        if not gas:
            raise SulfurRecoveryError(
                "every component condensed or reacted: the Claus unit would produce no tail gas -- "
                "check the reaction set and feed"
            )
        n_tail = sum(gas.values())
        tail_comp = {cid: n / n_tail for cid, n in gas.items()}
        tail_gas_out = thermo.flash_pt(tail_comp, T_cond, P, n_tail)

        if sulfur > 0.0:
            sulfur_out = thermo.flash_pt({"S8": 1.0}, T_cond, P, sulfur)
        else:  # zero-flow outlet: assembled by hand, per the plugin convention
            sulfur_out = StreamState(
                T=T_cond,
                P=P,
                molar_flow=0.0,
                composition={"S8": 1.0},
                vapor_fraction=0.0,
                enthalpy=0.0,
                entropy=0.0,
                phases=[],
            )

        h_in = sum(enthalpy_with_formation(s) for s in inlets.values())
        h_out = enthalpy_with_formation(tail_gas_out) + enthalpy_with_formation(sulfur_out)
        duty_W = h_out - h_in

        sulfur_in = n_h2s_feed  # one S atom per H2S: the only sulfur carrier in R0
        info["sulfur_out_mol_s"] = sulfur
        info["sulfur_recovery_fraction"] = 8.0 * sulfur / sulfur_in if sulfur_in > 0.0 else 0.0
        info["tail_gas_mol_s"] = n_tail
        info["thermal_T_K"] = T_thermal
        info["process_P_Pa"] = P
        info["condenser_T_K"] = T_cond
        return UnitResult(
            outlets={"tail_gas_out": tail_gas_out, "sulfur_out": sulfur_out},
            duty_W=duty_W,
            info=info,
        )

    @staticmethod
    def example_case() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A 100 mol/s burner mixture over two catalytic stages.

        Feed (the burner mixture of a lean acid gas and stoichiometric air):
        H2S 0.30, O2 0.15 (exactly the air the one-third burn needs:
        1.5 * 0.30/3), CO2 0.05, N2 0.50, at 320 K and 1.5 bara. Thermal stage
        at 1350 K (typical reaction-furnace temperature), 60 % thermal Claus
        conversion, two catalytic stages (573 K at 70 % conversion; 473 K at a
        30 K equilibrium approach), condensers at 423 K (150 C -- liquid
        sulfur). Reactions: Kohl & Nielsen, Gas Purification, 5th ed., ch. 8.
        """
        reaction_set = {
            "id": "claus",
            "components": ["H2S", "O2", "SO2", "H2O", "S8", "N2", "CO2"],
            "reactions": [
                {
                    "id": "h2s_burn",
                    "stoichiometry": {"H2S": -1.0, "O2": -1.5, "SO2": 1.0, "H2O": 1.0},
                    "base_component": "H2S",
                    "provenance": "standard Claus thermal oxidation, Kohl & Nielsen, "
                    "Gas Purification, 5th ed., ch. 8",
                },
                {
                    "id": "claus_reaction",
                    "stoichiometry": {"H2S": -2.0, "SO2": -1.0, "H2O": 2.0, "S8": 0.375},
                    "base_component": "SO2",
                    "provenance": "standard Claus reaction, Kohl & Nielsen, Gas Purification, 5th ed., ch. 8",
                    "equilibrium": {"form": "from_gibbs"},
                },
            ],
        }
        feeds: dict[str, dict[str, Any]] = {
            "acid_gas_in": {
                "T": 320.0,
                "P": 1.5e5,
                "molar_flow": 100.0,
                "composition": {"H2S": 0.30, "O2": 0.15, "CO2": 0.05, "N2": 0.50},
            },
        }
        params: dict[str, Any] = {
            "T_thermal": 1350.0,
            "P": 1.2e5,
            "T_condenser": 423.15,
            "thermal_conversion": 0.6,
            "catalytic_stages": [
                {"T": 573.15, "conversion": 0.7},
                {"T": 473.15, "approach_K": 30.0},
            ],
            "reaction_set": reaction_set,
        }
        return feeds, params
