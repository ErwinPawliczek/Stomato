"""Multiphase Gibbs reactor: gas plus pure condensed species (spec C-02).

Plugin kind "unit", name "gibbs_multiphase". The gas-only ``gibbs_reactor`` cannot
deposit anything: this unit lets a candidate be a pure condensed phase, so carbon
forms on a reformer, sulfur drops out of a Claus stage and an oxide reduces, with
each phase's presence decided by the Gibbs minimum rather than stated.

Ports: ``inlet`` -> ``vapor_out`` (the gas, flashed by the flowsheet package at the
outlet state) and ``condensed_out`` (the pure condensed species). Params:

- ``species``: candidates. A bare id is the gas; ``"C(s)"``, ``"H2O(l)"`` are pure
  condensed phases. Only candidates can form.
- ``inerts``: fixed-amount gas spectators.
- ``thermal``: as ``gibbs_reactor``; adiabatic and duty modes re-equilibrate at every
  trial temperature, so a phase may appear on the way to the answer.

The condensed stream's enthalpy is not a package flash: a cubic EOS has no graphite.
It is built from the species models on the flowsheet datum, H = H°(T) − datum, so
``enthalpy_with_formation`` of the stream returns the true Σ n_i H°_i(T) and the
energy balance closes across the phase change.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data.formation import enthalpy_datum
from ngdesign.data.species_models import species_thermo
from ngdesign.units._physics.gibbs_phases import (
    EquilibriumError,
    EquilibriumResult,
    gibbs_equilibrium,
    phase_of,
    species_of,
)
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.reactors._shared import close_thermal, z_from


class GibbsMultiphaseError(ValueError):
    """The candidate set or the feed cannot be equilibrated."""


def _condensed_stream(amounts: Mapping[str, float], fallback: str, T: float, P: float) -> StreamState:
    """The condensed outlet, on the flowsheet enthalpy datum; a zero-flow stream when none forms."""
    total = math.fsum(amounts.values())
    if total <= 0.0:
        return StreamState(
            T=T,
            P=P,
            molar_flow=0.0,
            composition={fallback: 1.0},
            vapor_fraction=0.0,
            enthalpy=0.0,
            entropy=0.0,
        )
    enthalpy = entropy = 0.0
    composition: dict[str, float] = {}
    for token, n in amounts.items():
        cid = species_of(token)
        model = species_thermo(cid, phase_of(token))
        y = n / total
        composition[cid] = composition.get(cid, 0.0) + y
        enthalpy += y * (model.h(T) - enthalpy_datum(cid))
        entropy += y * model.s(T)
    return StreamState(
        T=T,
        P=P,
        molar_flow=total,
        composition=composition,
        vapor_fraction=0.0,
        enthalpy=enthalpy,
        entropy=entropy,
    )


class GibbsMultiphase:
    """Gibbs minimum over a gas and pure condensed phases."""

    inlet_ports = ("inlet",)
    outlet_ports = ("vapor_out", "condensed_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        inlet = inlets["inlet"]
        tokens = list(params["species"])
        inerts = list(params.get("inerts", []))
        names = {species_of(token) for token in tokens}
        overlap = sorted(names & set(inerts))
        if overlap:
            raise GibbsMultiphaseError(f"{overlap} are both species and inerts")
        unlisted = sorted(set(inlet.composition) - names - set(inerts))
        if unlisted:
            raise GibbsMultiphaseError(f"feed components {unlisted} are not listed in species or inerts")
        condensed_tokens = [token for token in tokens if phase_of(token) != "gas"]
        if not condensed_tokens:
            raise GibbsMultiphaseError("no condensed candidate: use gibbs_reactor for a gas-only set")
        n_in = inlet.component_flows()
        reactive = {cid: n for cid, n in n_in.items() if cid not in inerts}
        spectators = {cid: n_in[cid] for cid in inerts}
        gas_tokens = [token for token in tokens if phase_of(token) == "gas"]
        h_in_W = enthalpy_with_formation(inlet)

        def equilibrium(T: float) -> EquilibriumResult:
            try:
                return gibbs_equilibrium(reactive, tokens, T, inlet.P, inerts=spectators)
            except EquilibriumError as exc:
                raise GibbsMultiphaseError(str(exc)) from exc

        def outlets(T: float) -> tuple[StreamState, StreamState, EquilibriumResult]:
            result = equilibrium(T)
            gas = {cid: n for cid, n in result.gas.items() if n > 0.0}
            total = math.fsum(gas.values())
            if total > 0.0:
                vapor = thermo.flash_pt(z_from(gas), T, inlet.P, total)
            else:
                vapor = thermo.flash_pt({gas_tokens[0]: 1.0}, T, inlet.P, 0.0)
            condensed = _condensed_stream(result.condensed, species_of(condensed_tokens[0]), T, inlet.P)
            return vapor, condensed, result

        def enthalpy_at(T: float) -> float:
            vapor, condensed, _ = outlets(T)
            return enthalpy_with_formation(vapor) + enthalpy_with_formation(condensed)

        T_out, duty = close_thermal(enthalpy_at, inlet.T, h_in_W, params.get("thermal", "isothermal"))
        vapor, condensed, result = outlets(T_out)
        return UnitResult(
            outlets={"vapor_out": vapor, "condensed_out": condensed},
            duty_W=duty,
            info={
                "T_out": T_out,
                "condensed_molar_flow": condensed.molar_flow,
                **{f"n_{token}": n for token, n in result.condensed.items()},
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Methane cracking at 1200 K and 1 bar: carbon deposits, no phase is stated."""
        feed = {"T": 1200.0, "P": 1.0e5, "molar_flow": 1.0, "composition": {"CH4": 1.0}}
        return {"inlet": feed}, {"species": ["CH4", "H2", "C(s)"], "thermal": "isothermal"}
