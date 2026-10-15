"""MDEA regenerator unit (Kent-Eisenberg). Plugin kind "unit", name "mdea_regenerator".

Second amine unit: strips the rich solvent leaving the absorber
(``mdea_absorber``) back to lean acid-gas loadings by inverting the same
Kent-Eisenberg equilibrium the absorber uses:

    rich_amine_in -> lean_amine_out, acid_gas_out

The acid gas is stripped with the water steam the reboiler generates; in v1
the steam is an energy-based estimate, not a modelled stream -- water and MDEA
are held in the liquid (no solvent cross-transfer, the absorber v1 precedent),
so the component balances of the amine loop close exactly and the stripping
steam demand is reported through ``info``.

Spec-driven solve (absorber precedent): the lean-loading targets set the
stripping duty; the equilibrium bounds the targets from both ends.

- Boiling floor: the reboiler temperature must sit above the regenerator
  pressure's water saturation point (steam is the stripping medium). A
  pressure at or above saturation raises -- no boiling, no stripping steam.
- Lean ceiling: the equilibrium acid-gas partial pressures the LEAN solvent
  exerts at the reboiler temperature (``equilibrium_partial_pressures``) plus
  the water vapor pressure over the solvent (Raoult, x_H2O * Psat_water) must
  fit under the regenerator pressure. A lean target the liquid cannot hold at
  the operating point raises, naming the pressures -- the liquid would boil
  acid gas until its equilibrium pressure fits.

Component passthrough mirrors the absorber: a lean target at or above the
rich loading passes that component unstripped; raising occurs only when
neither component strips.

Both products leave at the reboiler temperature and the regenerator pressure
(single equilibrium-stage shortcut); overhead cooling and condenser duty are
out of scope in v1. ``duty_W`` is the enthalpy difference across the unit --
sensible heating of the rich solvent to the reboiler temperature plus the heat
of acid-gas desorption: the reboiler duty estimate. The stripping steam rate
is that duty divided by the latent heat of vaporization of water at the
reboiler temperature (thermo library water databank, ``Chemical('water')``).
"""

from __future__ import annotations

from typing import Any

from thermo import Chemical

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.units.mdea_equilibrium import (
    amine_molarity,
    equilibrium_partial_pressures,
)

__all__ = ["MdeaRegenerator"]

#: Default lean CO2 loading target, mol CO2 per mol MDEA (the absorber's
#: example lean solvent, so absorber/regenerator pairs are consistent).
DEFAULT_LEAN_CO2_LOADING = 0.005

#: Default lean H2S loading target, mol H2S per mol MDEA.
DEFAULT_LEAN_H2S_LOADING = 0.002

#: Default regenerator pressure, Pa abs (typical MDEA still, ~1.8 bara).
DEFAULT_REGENERATOR_P = 1.8e5

#: Default reboiler temperature, K (~121 C; typical MDEA reboiler 118-127 C).
DEFAULT_REBOILER_T = 394.15


def _mw(component: str) -> float:
    """Molecular weight of a databanked component, g/mol."""
    return float(components()[component]["mw"])


def _mixture_mw(z: dict[str, float]) -> float:
    """Mole-fraction-weighted molecular weight of a composition, g/mol."""
    return sum(f * _mw(c) for c, f in z.items())


def _rich_amine_basis(rich_amine: StreamState) -> tuple[float, float, dict[str, float]]:
    """MDEA molar flow (mol/s), amine molarity (mol/m3), composition of the rich solvent.

    The rich amine is a defined single-liquid solution, so the unit consumes
    the OVERALL stream composition, never phase splits -- cubic-EOS phase
    splits of electrolytic amines are classification artifacts (the absorber's
    ``_lean_amine_basis`` rationale, same basis so both loop units agree).
    The solution density is the densest flashed phase's density -- the best
    liquid density the Peng-Robinson package offers for the solution.
    """
    if not rich_amine.phases:
        raise ValueError("rich_amine_in must be a flashed stream (has phases)")
    z = rich_amine.composition
    n_mdea = rich_amine.molar_flow * z.get("MDEA", 0.0)
    if n_mdea <= 0.0:
        raise ValueError("rich_amine_in carries no MDEA; not an amine solvent")
    rho = max(p.density for p in rich_amine.phases)
    c_amine = amine_molarity(z["MDEA"], _mixture_mw(z), rho)
    return n_mdea, c_amine, z


def _minus_acid_gas(state: StreamState, co2_delta: float, h2s_delta: float) -> tuple[dict[str, float], float]:
    """Composition and molar flow with ``co2_delta``/``h2s_delta`` removed (mol/s).

    All other component flows are held fixed, so the component balances of the
    unit close exactly.
    """
    flows = {c: f * state.molar_flow for c, f in state.composition.items()}
    flows["CO2"] = flows.get("CO2", 0.0) - co2_delta
    flows["H2S"] = flows.get("H2S", 0.0) - h2s_delta
    total = sum(flows.values())
    if total <= 0.0:
        raise ValueError("stream collapsed to zero molar flow")
    return {c: n / total for c, n in flows.items()}, total


@register("unit", "mdea_regenerator")
class MdeaRegenerator:
    """Regenerator stripping the rich MDEA back to lean-loading specifications."""

    inlet_ports: tuple[str, ...] = ("rich_amine_in",)
    outlet_ports: tuple[str, ...] = ("lean_amine_out", "acid_gas_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        rich_in = inlets["rich_amine_in"]

        lean_co2_target = float(params.get("lean_co2_loading", DEFAULT_LEAN_CO2_LOADING))
        lean_h2s_target = float(params.get("lean_h2s_loading", DEFAULT_LEAN_H2S_LOADING))
        P_reg = float(params.get("regenerator_P", DEFAULT_REGENERATOR_P))
        T_reb = float(params.get("reboiler_T", DEFAULT_REBOILER_T))
        if not P_reg > 0.0:
            raise ValueError(f"regenerator_P must be positive, got {P_reg}")
        if not T_reb > 0.0:
            raise ValueError(f"reboiler_T must be positive, got {T_reb}")

        n_mdea, c_amine, z_rich = _rich_amine_basis(rich_in)
        rich_co2_loading = z_rich.get("CO2", 0.0) / z_rich["MDEA"]
        rich_h2s_loading = z_rich.get("H2S", 0.0) / z_rich["MDEA"]

        # Boiling floor: steam is the stripping medium; no boiling, no steam.
        water = Chemical("water", T=T_reb, P=P_reg)
        p_sat_water = float(water.Psat)
        if P_reg >= p_sat_water:
            raise ValueError(
                f"infeasible regeneration: regenerator pressure {P_reg:.4g} Pa is at or above "
                f"the water saturation pressure {p_sat_water:.4g} Pa at the reboiler temperature "
                f"{T_reb:.4g} K -- no boiling, no stripping steam; lower the pressure or raise "
                "the reboiler temperature"
            )

        # Lean ceiling: the equilibrium pressures the lean solvent exerts at the
        # reboiler temperature must fit under the regenerator pressure alongside
        # the water vapor pressure (Raoult over the water-rich solvent).
        p_co2_eq, p_h2s_eq = equilibrium_partial_pressures(T_reb, c_amine, lean_co2_target, lean_h2s_target)
        p_h2o = z_rich.get("H2O", 0.0) * p_sat_water
        p_acid_eq = p_co2_eq + p_h2s_eq
        if p_acid_eq + p_h2o > P_reg:
            raise ValueError(
                f"infeasible regeneration: the lean-loading targets (CO2 {lean_co2_target:.4g}, "
                f"H2S {lean_h2s_target:.4g} mol/mol) exert equilibrium acid-gas partial pressures "
                f"of {p_acid_eq:.4g} Pa at the reboiler temperature which, with the water vapor "
                f"pressure {p_h2o:.4g} Pa, exceed the regenerator pressure {P_reg:.4g} Pa -- "
                "the solvent would boil acid gas beyond these targets; strip to a leaner "
                "solvent (lower the lean-loading targets), raise the reboiler temperature, "
                "or lower the regenerator pressure"
            )

        # Stripping duty: rich loading down to the lean targets, mol/s.
        stripped_co2 = max(rich_co2_loading - lean_co2_target, 0.0) * n_mdea
        stripped_h2s = max(rich_h2s_loading - lean_h2s_target, 0.0) * n_mdea
        stripped_total = stripped_co2 + stripped_h2s
        if stripped_total <= 0.0:
            raise ValueError(
                f"infeasible regeneration: no acid gas to strip (rich CO2 loading "
                f"{rich_co2_loading:.4g} vs lean target {lean_co2_target:.4g}; rich H2S loading "
                f"{rich_h2s_loading:.4g} vs lean target {lean_h2s_target:.4g} mol/mol)"
            )

        lean_comp, lean_flow = _minus_acid_gas(rich_in, stripped_co2, stripped_h2s)
        lean_amine_out = thermo.flash_pt(lean_comp, T_reb, P_reg, lean_flow)

        acid_comp = {
            c: n / stripped_total for c, n in (("CO2", stripped_co2), ("H2S", stripped_h2s)) if n > 0.0
        }
        acid_gas_out = thermo.flash_pt(acid_comp, T_reb, P_reg, stripped_total)

        duty_W = (
            lean_amine_out.enthalpy * lean_amine_out.molar_flow
            + acid_gas_out.enthalpy * acid_gas_out.molar_flow
            - rich_in.enthalpy * rich_in.molar_flow
        )

        # Stripping steam estimate: reboiler duty over the latent heat of
        # vaporization of water at the reboiler temperature (thermo water data).
        h_vap_water = float(water.Hvapm)
        steam_mol_s = duty_W / h_vap_water
        steam_kg_s = steam_mol_s * _mw("H2O") / 1000.0

        info: dict[str, float] = {
            "co2_stripped_mol_s": stripped_co2,
            "h2s_stripped_mol_s": stripped_h2s,
            "rich_co2_loading": rich_co2_loading,
            "rich_h2s_loading": rich_h2s_loading,
            "lean_co2_loading": lean_co2_target,
            "lean_h2s_loading": lean_h2s_target,
            "equilibrium_p_co2_lean_Pa": p_co2_eq,
            "equilibrium_p_h2s_lean_Pa": p_h2s_eq,
            "water_vapor_pressure_Pa": p_h2o,
            "water_saturation_pressure_Pa": p_sat_water,
            "rich_amine_molarity_mol_per_l": c_amine / 1000.0,
            "reboiler_duty_W": duty_W,
            "stripping_steam_mol_s": steam_mol_s,
            "stripping_steam_kg_per_h": steam_kg_s * 3600.0,
            "steam_kg_per_kg_acid_gas": (
                steam_kg_s * 1000.0 / stripped_total if stripped_total > 0.0 else 0.0
            )
            / _mixture_mw({"CO2": stripped_co2 / stripped_total, "H2S": stripped_h2s / stripped_total}),
        }

        return UnitResult(
            outlets={"lean_amine_out": lean_amine_out, "acid_gas_out": acid_gas_out},
            duty_W=duty_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Rich solvent carrying CO2 0.40 / H2S 0.15 mol per mol MDEA at 30 C / 6.5 MPa.

        The rich end of the absorber's example solvent (same 50 wt% MDEA basis,
        loadings raised to the rich side of the loop), built on a molar basis
        so the loadings are exact by construction.
        """
        n_mdea = 1.0
        n_h2o = _mw("MDEA") / _mw("H2O") * 1.0  # 50 wt% of the MDEA + water pair
        n_co2 = 0.40 * n_mdea
        n_h2s = 0.15 * n_mdea
        total = n_mdea + n_h2o + n_co2 + n_h2s
        rich_composition = {
            "MDEA": n_mdea / total,
            "H2O": n_h2o / total,
            "CO2": n_co2 / total,
            "H2S": n_h2s / total,
        }
        feeds: dict[str, dict[str, Any]] = {
            "rich_amine_in": {
                "T": 303.15,
                "P": 6.5e6,
                "molar_flow": 100.0,
                "composition": rich_composition,
            },
        }
        params: dict[str, Any] = {}
        return feeds, params
