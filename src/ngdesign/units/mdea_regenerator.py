"""MDEA/MEA/DEA regenerator unit (Kent-Eisenberg). Plugin kind "unit", names
"mdea_regenerator", "mea_regenerator", "dea_regenerator".

Second amine unit: strips the rich solvent leaving the absorber
(``mdea_absorber``) back to lean acid-gas loadings by inverting the same
Kent-Eisenberg equilibrium the absorber uses:

    rich_amine_in -> lean_amine_out, acid_gas_out

The acid gas is stripped with the water steam the reboiler generates; in v1
the steam is an energy-based estimate, not a modelled stream -- water and the
amine are held in the liquid (no solvent cross-transfer, the absorber v1 precedent),
so the component balances of the amine loop close exactly and the stripping
steam demand is reported through ``info``. The solvent amine is selectable
(MDEA default, MEA, DEA) by registered kind or the ``amine`` param, matching
the absorber.

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

from typing import Any, cast

from thermo import Chemical

from ngdesign.amine.equilibrium import equilibrium_partial_pressures
from ngdesign.amine.package import AmineReactivePackage
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.units.mdea_equilibrium import AMINES, amine_molarity

__all__ = ["MdeaRegenerator", "MeaRegenerator", "DeaRegenerator"]

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


def _rich_amine_basis(rich_amine: StreamState, amine: str) -> tuple[float, float, dict[str, float]]:
    """Amine molar flow (mol/s), amine molarity (mol/m3), composition of the rich solvent.

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
    n_amine = rich_amine.molar_flow * z.get(amine, 0.0)
    if n_amine <= 0.0:
        raise ValueError(f"rich_amine_in carries no {amine}; not an amine solvent")
    rho = max(p.density for p in rich_amine.phases)
    c_amine = amine_molarity(z[amine], _mixture_mw(z), rho)
    return n_amine, c_amine, z


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
    """Regenerator stripping the rich solvent back to lean-loading specifications.

    The class carries the registered solvent amine (MDEA); the
    ``mea_regenerator``/``dea_regenerator`` aliases are thin subclasses
    overriding ``AMINE`` and the example solvent strength, matching the
    absorber aliases. A ``params["amine"]`` value overrides the class default.
    """

    inlet_ports: tuple[str, ...] = ("rich_amine_in",)
    outlet_ports: tuple[str, ...] = ("lean_amine_out", "acid_gas_out")

    @property
    def amine(self) -> str:
        """Amine this registered unit runs by default; params["amine"] overrides per solve."""
        return self.AMINE

    #: Registered solvent amine (a key of mdea_equilibrium.AMINES).
    AMINE = "MDEA"
    #: Example solvent amine mass fraction of the amine + water pair.
    SOLVENT_MASS_FRACTION = 0.50

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        rich_in = inlets["rich_amine_in"]

        amine = str(params.get("amine", self.AMINE))
        if amine not in AMINES:
            supported = ", ".join(sorted(AMINES))
            raise ValueError(f"unsupported amine {amine!r}; supported amines: {supported}")

        lean_co2_target = float(params.get("lean_co2_loading", DEFAULT_LEAN_CO2_LOADING))
        lean_h2s_target = float(params.get("lean_h2s_loading", DEFAULT_LEAN_H2S_LOADING))
        P_reg = float(params.get("regenerator_P", DEFAULT_REGENERATOR_P))
        T_reb = float(params.get("reboiler_T", DEFAULT_REBOILER_T))
        if not P_reg > 0.0:
            raise ValueError(f"regenerator_P must be positive, got {P_reg}")
        if not T_reb > 0.0:
            raise ValueError(f"reboiler_T must be positive, got {T_reb}")

        n_amine, c_amine, z_rich = _rich_amine_basis(rich_in, amine)
        rich_co2_loading = z_rich.get("CO2", 0.0) / z_rich[amine]
        rich_h2s_loading = z_rich.get("H2S", 0.0) / z_rich[amine]

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

        # A reactive amine property package carries its own chemistry: use it
        # for speciation and every outlet state (spec P1-04).  A plain cubic
        # keeps today's facade-based behaviour byte-identical.
        amine_pkg = (
            cast(AmineReactivePackage, thermo)
            if getattr(thermo, "is_amine_reactive_package", False)
            else None
        )

        # Lean ceiling: the equilibrium pressures the lean solvent exerts at the
        # reboiler temperature must fit under the regenerator pressure alongside
        # the water vapor pressure (Raoult over the water-rich solvent).
        if amine_pkg is not None:
            lean_eq = amine_pkg.equilibrium_pressures(z_rich, T_reb, lean_co2_target, lean_h2s_target)
            p_co2_eq, p_h2s_eq = lean_eq["CO2"], lean_eq["H2S"]
        else:
            p_co2_eq, p_h2s_eq = equilibrium_partial_pressures(
                params, T_reb, c_amine, lean_co2_target, lean_h2s_target, amine=amine
            )
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
        stripped_co2 = max(rich_co2_loading - lean_co2_target, 0.0) * n_amine
        stripped_h2s = max(rich_h2s_loading - lean_h2s_target, 0.0) * n_amine
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
        if amine_pkg is not None:
            # Heat of absorption the stripped acid gas releases on reabsorption;
            # stripping must supply it, and the reactive package's outlet
            # enthalpies already carry it.
            d_h_abs = amine_pkg.heat_of_absorption(z_rich, T_reb)
            info["heat_of_absorption_W"] = stripped_co2 * d_h_abs["CO2"] + stripped_h2s * d_h_abs["H2S"]

        return UnitResult(
            outlets={"lean_amine_out": lean_amine_out, "acid_gas_out": acid_gas_out},
            duty_W=duty_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Rich solvent carrying CO2 0.40 / H2S 0.15 mol per mol amine at 30 C / 6.5 MPa.

        The rich end of the class's example solvent (same solvent-strength
        basis as the absorber example, loadings raised to the rich side of the
        loop), built on a molar basis so the loadings are exact by construction.
        """
        n_amine = 1.0
        n_h2o = _mw(cls.AMINE) / _mw("H2O") * (cls.SOLVENT_MASS_FRACTION / (1.0 - cls.SOLVENT_MASS_FRACTION))
        n_co2 = 0.40 * n_amine
        n_h2s = 0.15 * n_amine
        total = n_amine + n_h2o + n_co2 + n_h2s
        rich_composition = {
            cls.AMINE: n_amine / total,
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


@register("unit", "mea_regenerator")
class MeaRegenerator(MdeaRegenerator):
    """MEA regenerator: the Kent-Eisenberg regenerator parameterized for aqueous MEA."""

    AMINE = "MEA"
    SOLVENT_MASS_FRACTION = 0.30


@register("unit", "dea_regenerator")
class DeaRegenerator(MdeaRegenerator):
    """DEA regenerator: the Kent-Eisenberg regenerator parameterized for aqueous DEA."""

    AMINE = "DEA"
    SOLVENT_MASS_FRACTION = 0.30
