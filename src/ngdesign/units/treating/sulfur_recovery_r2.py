"""Claus sulfur recovery R2: Gibbs equilibrium per catalytic converter (``specs/backend/units/sulfur_recovery.md``).

Each converter is at chemical equilibrium at T_eq = T + approach_K, by Gibbs minimisation
over the converter species set on the ideal-gas JANAF basis (``_physics.gibbs``): minimise
G/RT = Sum n_i*(mu0_i/RT + ln(y_i*P/P0)) subject to A*n = b.  Sulfur forms S6 and S8, and
optionally COS, CS2, CO and H2 join every converter's set.

Scope, each measured when the spec was written and held here on purpose:

- No Gibbs furnace: S2, the dominant sulfur species above about 1000 K, has no formation
  enthalpy or critical constants in the databank.  The thermal stage is R0's rule, reached
  by calling R0 with no catalytic stages, so nothing is copied.
- Isothermal converters at the stage temperature, as in R0; the heat release shows in the
  unit duty.  Adiabatic beds are not modelled.
- Complete condensation of S6 and S8 at T_condenser, as R0 for S8: the package's sulfur
  saturation pressure is about 5.2 times too high at the normal boiling point.

Every feed species, inerts included, goes in ``species`` with ``inerts = []``:
``gibbs_minimum`` counts inert atoms but refuses an element no species carries.  With the
species restricted to R0's set the problem has one degree of freedom, the Claus extent, and
R2 equals R0's approach mode.  All SI.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data.formation import MissingFormationData, atomic_composition, formation_enthalpy_298
from ngdesign.units._physics.gibbs import GibbsError, gibbs_minimum
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.treating.sulfur_recovery import SulfurRecovery, SulfurRecoveryError

_EXTRA_ALLOWED = ("COS", "CS2", "CO", "H2")
_SULFUR = ("S6", "S8")


def _converter_equilibrium(
    gas: Mapping[str, float], T: float, P: float, species: Sequence[str]
) -> dict[str, float]:
    """The Gibbs minimum of ``gas`` over ``species``, with no fixed inerts."""
    for cid in species:
        try:
            formation_enthalpy_298(cid)
        except MissingFormationData as exc:
            raise SulfurRecoveryError(f"species {cid!r} has no formation data: {exc}") from exc
    return gibbs_minimum(list(species), [], dict(gas), T, P)


class SulfurRecoveryR2:
    """Claus unit with R0's furnace and a Gibbs equilibrium per converter."""

    inlet_ports: tuple[str, ...] = SulfurRecovery.inlet_ports
    outlet_ports: tuple[str, ...] = SulfurRecovery.outlet_ports

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        stages = params.get("catalytic_stages")
        if not isinstance(stages, list):
            raise SulfurRecoveryError("param 'catalytic_stages' must be a list of stage specs")
        for i, stage in enumerate(stages):
            if not isinstance(stage, dict) or "T" not in stage:
                raise SulfurRecoveryError(f"catalytic_stages[{i}] must be a dict with a 'T' key")
            if "conversion" in stage:
                raise SulfurRecoveryError(
                    f"catalytic_stages[{i}]: a conversion is an R0 spec; R2 converters are at equilibrium"
                )
            if float(stage["T"]) <= 0.0 or float(stage.get("approach_K", 0.0)) < 0.0:
                raise SulfurRecoveryError(f"catalytic_stages[{i}]: T must be > 0 and approach_K >= 0")
        extra = list(params.get("extra_species", ()))
        outside = sorted(set(extra) - set(_EXTRA_ALLOWED))
        if outside:
            raise SulfurRecoveryError(f"extra_species {outside} are outside {list(_EXTRA_ALLOWED)}")

        r0 = SulfurRecovery().solve(inlets, {**params, "catalytic_stages": []}, thermo)
        gas = dict(r0.outlets["tail_gas_out"].component_flows())
        pressure = float(params["P"])
        t_cond = float(params["T_condenser"])
        sulfur = {"S6": 0.0, "S8": float(r0.outlets["sulfur_out"].molar_flow)}
        info: dict[str, float] = dict(r0.info)
        n_species = 0
        for i, stage in enumerate(stages):
            t_eq = float(stage["T"]) + float(stage.get("approach_K", 0.0))
            present = {cid for cid, n in gas.items() if n > 0.0}
            species = sorted(present | set(_SULFUR) | set(extra))
            n_species = max(n_species, len(species))
            h2s_in = gas.get("H2S", 0.0)
            try:
                out = _converter_equilibrium({cid: gas[cid] for cid in present}, t_eq, pressure, species)
            except GibbsError as exc:
                raise SulfurRecoveryError(f"catalytic stage {i}: {exc}") from exc
            info[f"stage_{i}_H2S_conversion"] = 1.0 - out.get("H2S", 0.0) / h2s_in if h2s_in > 0.0 else 0.0
            info[f"stage_{i}_S6_mol_s"] = out.get("S6", 0.0)
            info[f"stage_{i}_S8_mol_s"] = out.get("S8", 0.0)
            info[f"stage_{i}_T_eq_K"] = t_eq
            for cid in _SULFUR:
                sulfur[cid] += out.pop(cid, 0.0)
            gas = {cid: n for cid, n in out.items() if n > 0.0}

        total_tail = math.fsum(gas.values())
        tail = thermo.flash_pt({cid: n / total_tail for cid, n in gas.items()}, t_cond, pressure, total_tail)
        total_sulfur = sulfur["S6"] + sulfur["S8"]
        z_sulfur = {cid: n / total_sulfur for cid, n in sulfur.items() if n > 0.0} if total_sulfur else {"S8": 1.0}
        sulfur_out = thermo.flash_pt(z_sulfur, t_cond, pressure, total_sulfur)

        duty = enthalpy_with_formation(tail) + enthalpy_with_formation(sulfur_out)
        duty -= math.fsum(enthalpy_with_formation(s) for s in inlets.values())
        s_in = math.fsum(
            n * atomic_composition(cid).get("S", 0)
            for s in inlets.values()
            for cid, n in s.component_flows().items()
        )
        info.update(
            sulfur_out_mol_s=total_sulfur,
            tail_gas_mol_s=total_tail,
            sulfur_recovery_fraction=(6.0 * sulfur["S6"] + 8.0 * sulfur["S8"]) / s_in,
            species_set_size=float(n_species),
            n_catalytic_stages=float(len(stages)),
        )
        return UnitResult(outlets={"tail_gas_out": tail, "sulfur_out": sulfur_out}, duty_W=duty, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's feed and params with the first converter at equilibrium at 573 K."""
        feeds, params = SulfurRecovery.example_case()
        return feeds, {**params, "catalytic_stages": [{"T": 573.0}, {"T": 473.15, "approach_K": 30.0}]}
