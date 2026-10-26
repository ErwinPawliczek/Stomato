"""Claus sulfur-recovery unit, R2 adapter (spec ``specs/backend/units/sulfur_recovery.md``).

Level R2 of catalogue row ``sulfur_recovery``: **Gibbs equilibrium per catalytic
converter** — each catalytic stage solves the full Gibbs minimum over its
species set (ideal gas at ``P``) instead of R0's single Claus extent, so S6 and
S8 (and optionally COS, CS2, CO, H2) compete in the equilibrium. The thermal
stage and the condensers stay exactly R0's.

Scope limits carried over from the spec (measured there, cited here):

- **No Gibbs furnace.** S2 — the dominant sulfur species above about 1000 K —
  has no formation enthalpy and no critical constants in the databank, so a
  Gibbs furnace without S2 would be physically wrong. The furnace keeps R0's
  burn-one-third + given-``thermal_conversion`` rule unchanged.
- **No adiabatic converters — a stated modelling choice, not a defect.** The
  U-01b energy-basis defect is fixed on main (#247/#252):
  ``enthalpy_with_formation`` lifts by the constant ΔfH°298 on top of a package
  enthalpy that already carries the sensible heat from 298.15 K, so reaction
  enthalpies reproduce the databank heats of reaction. Converters are
  **isothermal** at the given stage ``T`` because the plan scopes R2 to
  isothermal beds (as in R0); their heat release shows in the unit duty.
  Adiabatic beds remain a follow-up.
- **Complete sulfur condensation** (R0's shortcut): the package S8 saturation
  pressure is unusable (``pure_psat("S8", 717.8 K)`` = 5.29e5 Pa against a
  1.013e5 Pa normal boiling point), so the condenser removes all S6 and S8.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import ReactionSet
from ngdesign.data.formation import (
    MissingFormationData,
    atomic_composition,
    formation_enthalpy_298,
)
from ngdesign.units._physics.gibbs import GibbsError, gibbs_minimum
from ngdesign.units._physics.kinetics import (
    ReactionExtentError,
    apply_extents,
    enthalpy_with_formation,
)
from ngdesign.units.treating.sulfur_recovery import (
    _BURN_FRACTION,
    SulfurRecoveryError,
    _split_sulfur,
)

__all__ = ["SulfurRecoveryR2"]

#: Condensed sulfur species at R2: both databank sulfur allotropes join the
#: converter equilibria and are condensed completely at the condenser (R0
#: condenses S8 only).
_SULFUR_SPECIES_R2 = ("S6", "S8")

#: Extra species a converter's Gibbs set may carry (the spec's enum).
_EXTRA_SPECIES = frozenset({"COS", "CS2", "CO", "H2"})


def _require(params: dict[str, Any], key: str) -> Any:
    if key not in params:
        raise SulfurRecoveryError(f"missing required param {key!r}")
    return params[key]


def _positive(params: dict[str, Any], key: str) -> float:
    value = float(_require(params, key))
    if not value > 0.0:
        raise SulfurRecoveryError(f"param {key!r} must be positive, got {value}")
    return value


def _converter_species(gas: Mapping[str, float], extra_species: Sequence[str]) -> list[str]:
    """Species set of one converter's Gibbs minimum: every gas component with a
    positive flow (inerts included -- N2 and CO2 ride as ordinary species; see
    the module docstring for why ``inerts`` stays empty), plus the condensed
    sulfur allotropes S6 and S8, plus the requested extras, sorted."""
    species = {cid for cid, n in gas.items() if n > 0.0}
    species |= set(_SULFUR_SPECIES_R2)
    species |= set(extra_species)
    return sorted(species)


def _converter_equilibrium(
    gas: Mapping[str, float],
    T: float,
    P: float,
    species: Sequence[str],
) -> dict[str, float]:
    """Gibbs minimum of one catalytic converter, mol/s.

    Minimises G/RT over ``species`` at (T, P) subject to the element budgets
    of the incoming gas (``ngdesign.units._physics.gibbs.gibbs_minimum``;
    JANAF-basis ideal-gas standard state at 1 bar). Raises
    ``SulfurRecoveryError`` naming the species when formation data is missing,
    and lets ``GibbsError`` propagate for the caller to wrap with the stage
    number.
    """
    for cid in species:
        try:
            formation_enthalpy_298(cid)
        except MissingFormationData as exc:
            raise SulfurRecoveryError(
                f"converter species {cid!r} has no formation data in the databank: {exc}"
            ) from exc
    return gibbs_minimum(species, [], gas, T, P)


class SulfurRecoveryR2:
    """R2 Claus sulfur recovery: R0's furnace and condensers, Gibbs converters.

    Registered through the catalogue (``levels.R2`` of row ``sulfur_recovery``);
    no decorator -- registration comes from the YAML.
    """

    inlet_ports: tuple[str, ...] = ("acid_gas_in",)
    outlet_ports: tuple[str, ...] = ("tail_gas_out", "sulfur_out")

    def _run_converter(
        self,
        gas: Mapping[str, float],
        T_eq: float,
        P: float,
        extra_species: Sequence[str] = (),
        _species_override: Sequence[str] | None = None,
    ) -> dict[str, float]:
        """One converter stage: species assembly then the Gibbs minimum.

        ``_species_override`` restricts the Gibbs species set (the R0-reduction
        test hook; never exposed through the public params).
        """
        species = (
            list(_species_override)
            if _species_override is not None
            else _converter_species(gas, extra_species)
        )
        return _converter_equilibrium(gas, T_eq, P, species)

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
            if "conversion" in stage:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}] carries 'conversion': R2 converters are Gibbs "
                    "equilibrium stages and have no conversion path"
                )
            approach = float(stage.get("approach_K", 0.0))
            if approach < 0.0:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}]['approach_K'] must be non-negative, got {approach}"
                )
        extra_species = params.get("extra_species", [])
        if not isinstance(extra_species, list) or any(
            not isinstance(cid, str) or cid not in _EXTRA_SPECIES for cid in extra_species
        ):
            raise SulfurRecoveryError(
                f"param 'extra_species' must be a list drawn from {sorted(_EXTRA_SPECIES)}, "
                f"got {extra_species!r}"
            )

        # --- Reaction set: R0's validation, R0's messages (the thermal stage
        # is exactly R0's and still runs on this set). ---
        rset = ReactionSet.model_validate(_require(params, "reaction_set"))
        if len(rset.reactions) != 2:
            raise SulfurRecoveryError(
                f"reaction set {rset.id!r}: the Claus unit needs exactly 2 reactions "
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

        # --- Thermal stage: exactly R0's code path and messages. ---
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
        gas, s8_thermal = _split_sulfur(n)
        s6_total = 0.0
        s8_total = s8_thermal

        # --- Catalytic stages: Gibbs equilibrium each, complete S6+S8
        # condensation after each. ---
        info: dict[str, float] = {
            "burn_extent_mol_s": xi_burn,
            "thermal_extent_mol_s": xi_thermal,
            "o2_excess_mol_s": o2_available - o2_needed,
            "n_catalytic_stages": float(len(stages)),
        }
        species_set_size = 0.0
        for i, stage in enumerate(stages):
            T_eq = float(stage["T"]) + float(stage.get("approach_K", 0.0))
            h2s_in = gas.get("H2S", 0.0)
            species = _converter_species(gas, extra_species)
            try:
                n_out = self._run_converter(gas, T_eq, P, extra_species)
            except GibbsError as exc:
                raise SulfurRecoveryError(f"catalytic stage {i}: {exc}") from exc
            s6_stage = n_out.get("S6", 0.0)
            s8_stage = n_out.get("S8", 0.0)
            s6_total += s6_stage
            s8_total += s8_stage
            gas = {cid: n for cid, n in n_out.items() if cid not in _SULFUR_SPECIES_R2}
            info[f"stage_{i}_H2S_conversion"] = 1.0 - n_out.get("H2S", 0.0) / h2s_in if h2s_in > 0.0 else 0.0
            info[f"stage_{i}_S6_mol_s"] = s6_stage
            info[f"stage_{i}_S8_mol_s"] = s8_stage
            info[f"stage_{i}_T_eq_K"] = T_eq
            info[f"stage_{i}_species_set_size"] = float(len(species))
            species_set_size = float(len(species))

        if not gas:
            raise SulfurRecoveryError(
                "every component condensed or reacted: the Claus unit would produce no tail gas -- "
                "check the reaction set and feed"
            )
        n_tail = sum(gas.values())
        tail_comp = {cid: n / n_tail for cid, n in gas.items()}
        tail_gas_out = thermo.flash_pt(tail_comp, T_cond, P, n_tail)

        sulfur_total = s6_total + s8_total
        if sulfur_total > 0.0:
            sulfur_comp: dict[str, float] = {}
            if s6_total > 0.0:
                sulfur_comp["S6"] = s6_total / sulfur_total
            if s8_total > 0.0:
                sulfur_comp["S8"] = s8_total / sulfur_total
            sulfur_out = thermo.flash_pt(sulfur_comp, T_cond, P, sulfur_total)
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

        feed_sulfur = 0.0
        for cid, frac in feed.composition.items():
            feed_sulfur += atomic_composition(cid).get("S", 0) * frac * feed.molar_flow
        info["sulfur_out_mol_s"] = sulfur_total
        info["sulfur_recovery_fraction"] = (
            (6.0 * s6_total + 8.0 * s8_total) / feed_sulfur if feed_sulfur > 0.0 else 0.0
        )
        info["species_set_size"] = species_set_size
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
        """A 100 mol/s burner mixture over two catalytic Gibbs stages.

        R0's feeds and thermal params; the given-conversion first converter is
        replaced by a Gibbs equilibrium stage at 573 K (approach 0 K), and the
        second stays at R0's 473.15 K with a 30 K equilibrium approach.
        Feed: H2S 0.30, O2 0.15 (exactly the air the one-third burn needs:
        1.5 * 0.30/3), CO2 0.05, N2 0.50, at 320 K and 1.5 bara. Thermal stage
        at 1350 K (typical reaction-furnace temperature), 60 % thermal Claus
        conversion, condensers at 423 K (150 C -- liquid sulfur).
        Reactions: Kohl & Nielsen, Gas Purification, 5th ed., ch. 8.
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
                {"T": 573.0, "approach_K": 0.0},
                {"T": 473.15, "approach_K": 30.0},
            ],
            "reaction_set": reaction_set,
        }
        return feeds, params
