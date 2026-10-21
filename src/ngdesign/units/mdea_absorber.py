"""MDEA/MEA/DEA absorber unit (Kent-Eisenberg). Plugin kind "unit", names
"mdea_absorber", "mea_absorber", "dea_absorber".

First amine-treatment unit: sweetens a sour natural-gas stream to CO2 and H2S
outlet specifications with lean aqueous amine in a countercurrent absorber:

    gas_in, lean_amine_in -> gas_out, rich_amine_out

The solvent amine is selectable: MDEA (default), MEA or DEA, chosen by the
unit's registered kind (``mdea_absorber``/``mea_absorber``/``dea_absorber``)
or the ``amine`` param. The chemistry covers all three: primary/secondary
amines (MEA, DEA) add carbamate speciation to the shared Kent-Eisenberg
equilibrium (``ngdesign.units.mdea_equilibrium``).


The absorbed CO2/H2S joins the lean amine to form the rich amine; the amine and
water are held in the liquid (no amine or water cross-transfer modelled in v1,
the TEG-contact precedent). Spec-driven solve (same precedent): the outlet
specs set the removed acid gas; the Kent-Eisenberg equilibrium then bounds the
specs from both ends.

- Top (lean) floor: the lean amine imposes an equilibrium acid-gas content on
  the outlet gas (``p_eq(lean loading) / P``). A spec below the floor raises --
  the lean solvent cannot reach it.
- Bottom (rich) ceiling: the rich amine cannot carry more acid gas than the
  inlet gas partial pressures support (``alpha_eq(p_in)``). A circulation rate
  whose rich loading exceeds the ceiling raises, naming the required and
  maximum loadings.

Specs are upper bounds: a component whose spec sits at or above its inlet
content passes through unabsorbed (MDEA's selective H2S-over-CO2 service);
raising occurs only when neither component is removed.

Outlet gas T/P equal the inlet gas T/P (isothermal column, no pressure drop,
TEG precedent); rich amine leaves at gas T/P. Duty is the enthalpy difference
across the unit; the heat of absorption is reported through it, not modelled
separately. Stage counts are out of scope for v1 (the equilibrium is strongly
nonlinear; the Kremser shortcut is the TEG-contact precedent, not this unit's).
"""

from __future__ import annotations

from typing import Any, cast

from ngdesign.amine.equilibrium import (
    equilibrium_loadings,
    equilibrium_partial_pressures,
)
from ngdesign.amine.package import AmineReactivePackage
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.units.mdea_equilibrium import AMINES, amine_molarity

__all__ = ["MdeaAbsorber", "MeaAbsorber", "DeaAbsorber"]

#: Default outlet CO2 spec, mol% in the treated gas (sales-gas inert limit).
DEFAULT_CO2_OUT_MOLPCT = 2.0

#: Default outlet H2S spec, ppmv in the treated gas (0.25 grain/100 scf).
DEFAULT_H2S_OUT_PPMV = 4.0

#: Example lean-solvent basis: amine mass fraction of the amine + water pair
#: (50 wt% MDEA, 30 wt% MEA, 30 wt% DEA -- the standard solvent strengths).
EXAMPLE_MDEA_MASS_FRACTION = 0.50
EXAMPLE_MEA_MASS_FRACTION = 0.30
EXAMPLE_DEA_MASS_FRACTION = 0.30

#: Example lean loadings, mol acid gas per mol MDEA.
EXAMPLE_LEAN_CO2_LOADING = 0.005
EXAMPLE_LEAN_H2S_LOADING = 0.002


def _mw(component: str) -> float:
    """Molecular weight of a databanked component, g/mol."""
    return float(components()[component]["mw"])


def _mixture_mw(z: dict[str, float]) -> float:
    """Mole-fraction-weighted molecular weight of a composition, g/mol."""
    return sum(f * _mw(c) for c, f in z.items())


def _lean_amine_composition(amine: str, solvent_mass_fraction: float) -> dict[str, float]:
    """Mole fractions of aqueous amine carrying the example lean loadings.

    Built on a molar basis (1 mol amine, water to the solvent mass fraction of
    the amine+water pair, then the dissolved acid gas), so the loadings are
    exact by construction.
    """
    n_amine = 1.0
    n_h2o = _mw(amine) / _mw("H2O") * (solvent_mass_fraction / (1.0 - solvent_mass_fraction))
    n_co2 = EXAMPLE_LEAN_CO2_LOADING * n_amine
    n_h2s = EXAMPLE_LEAN_H2S_LOADING * n_amine
    total = n_amine + n_h2o + n_co2 + n_h2s
    return {
        amine: n_amine / total,
        "H2O": n_h2o / total,
        "CO2": n_co2 / total,
        "H2S": n_h2s / total,
    }


def _lean_amine_basis(lean_amine: StreamState, amine: str) -> tuple[float, float]:
    """Amine molar flow (mol/s) and amine molarity (mol/m3) of the lean solvent.

    The lean amine is a defined single-liquid solution, so the unit consumes
    the OVERALL stream composition, never phase splits: cubic-EOS phase
    splits of electrolytic amines are classification artifacts (an amine-rich
    liquid can come back labelled "vapor" while the "aqueous" phase is
    nearly pure water), and phase-local mole fractions are not trustworthy.
    The solution density is the densest flashed phase's density -- the best
    liquid density the Peng-Robinson package offers for the solution.
    """
    if not lean_amine.phases:
        raise ValueError("lean_amine_in must be a flashed stream (has phases)")
    z = lean_amine.composition
    n_amine = lean_amine.molar_flow * z.get(amine, 0.0)
    if n_amine <= 0.0:
        raise ValueError(f"lean_amine_in carries no {amine}; not an amine solvent")
    rho = max(p.density for p in lean_amine.phases)
    c_amine = amine_molarity(z[amine], _mixture_mw(z), rho)
    return n_amine, c_amine


def _acid_gas_removals(
    gas_flow: float,
    y_co2_in: float,
    y_h2s_in: float,
    y_co2_out: float,
    y_h2s_out: float,
) -> tuple[float, float]:
    """Removed (CO2, H2S) molar flows, mol/s, for the two outlet specs.

    The outlet specs are upper bounds on the wet-gas mole fractions: a spec at
    or above the inlet content passes that component through. Solves the mole
    balance ``n_c_out = y_c_out * (n_inert + n_co2_out + n_h2s_out)`` in closed
    form; a component pinned at its inlet flow (passthrough) re-solves the
    other component on the actual outlet flow, so a met spec stays met.
    """
    n_co2_in = gas_flow * y_co2_in
    n_h2s_in = gas_flow * y_h2s_in
    n_inert = gas_flow * (1.0 - y_co2_in - y_h2s_in)
    denom = 1.0 - y_co2_out - y_h2s_out
    n_co2_out = y_co2_out * n_inert / denom
    n_h2s_out = y_h2s_out * n_inert / denom
    if n_co2_out > n_co2_in:  # CO2 spec above inlet content: CO2 passes through
        n_co2_out = n_co2_in
        n_h2s_out = y_h2s_out * (n_inert + n_co2_out) / (1.0 - y_h2s_out)
    if n_h2s_out > n_h2s_in:  # H2S spec above inlet content: H2S passes through
        n_h2s_out = n_h2s_in
        n_co2_out = min(y_co2_out * (n_inert + n_h2s_out) / (1.0 - y_co2_out), n_co2_in)
    removed_co2 = n_co2_in - n_co2_out
    removed_h2s = n_h2s_in - n_h2s_out
    if removed_co2 <= 0.0 and removed_h2s <= 0.0:
        raise ValueError(
            f"infeasible spec: no acid gas to remove (inlet CO2 {y_co2_in:.4g} mol fraction "
            f"vs spec {y_co2_out:.4g}; H2S {y_h2s_in:.4g} vs spec {y_h2s_out:.4g})"
        )
    return removed_co2, removed_h2s


def _residual_composition(state: StreamState, co2_flow: float, h2s_flow: float) -> dict[str, float]:
    """Composition with CO2/H2S pinned to absolute molar flows, others scaled to fit."""
    flows = {c: f * state.molar_flow for c, f in state.composition.items()}
    flows["CO2"] = co2_flow
    flows["H2S"] = h2s_flow
    total = sum(flows.values())
    if total <= 0.0:
        raise ValueError("stream collapsed to zero molar flow")
    return {c: n / total for c, n in flows.items()}


def _plus_acid_gas(state: StreamState, co2_delta: float, h2s_delta: float) -> tuple[dict[str, float], float]:
    """Composition and molar flow with ``co2_delta``/``h2s_delta`` added (mol/s).

    All other component flows are held fixed, so the component balances of the
    unit close exactly.
    """
    flows = {c: f * state.molar_flow for c, f in state.composition.items()}
    flows["CO2"] = flows.get("CO2", 0.0) + co2_delta
    flows["H2S"] = flows.get("H2S", 0.0) + h2s_delta
    total = sum(flows.values())
    return {c: n / total for c, n in flows.items()}, total


@register("unit", "mdea_absorber")
class MdeaAbsorber:
    """Countercurrent amine absorber sweetening gas to CO2/H2S specs.

    The class carries the registered solvent amine (MDEA); the
    ``mea_absorber``/``dea_absorber`` aliases are thin subclasses overriding
    ``AMINE`` and the example solvent strength. A ``params["amine"]`` value
    overrides the class default for either kind.
    """

    inlet_ports: tuple[str, ...] = ("gas_in", "lean_amine_in")
    outlet_ports: tuple[str, ...] = ("gas_out", "rich_amine_out")

    @property
    def amine(self) -> str:
        """Amine this registered unit runs by default; params["amine"] overrides per solve."""
        return self.AMINE

    #: Registered solvent amine (a key of mdea_equilibrium.AMINES).
    AMINE = "MDEA"
    #: Example lean-solvent amine mass fraction of the amine + water pair.
    SOLVENT_MASS_FRACTION = EXAMPLE_MDEA_MASS_FRACTION

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        gas_in = inlets["gas_in"]
        lean_amine_in = inlets["lean_amine_in"]

        amine = str(params.get("amine", self.AMINE))
        if amine not in AMINES:
            supported = ", ".join(sorted(AMINES))
            raise ValueError(f"unsupported amine {amine!r}; supported amines: {supported}")

        co2_out_molpct = float(params.get("co2_out_molpct", DEFAULT_CO2_OUT_MOLPCT))
        h2s_out_ppmv = float(params.get("h2s_out_ppmv", DEFAULT_H2S_OUT_PPMV))
        if not co2_out_molpct > 0.0:
            raise ValueError(f"co2_out_molpct must be positive, got {co2_out_molpct}")
        if not h2s_out_ppmv > 0.0:
            raise ValueError(f"h2s_out_ppmv must be positive, got {h2s_out_ppmv}")
        y_co2_out = co2_out_molpct / 100.0
        y_h2s_out = h2s_out_ppmv * 1e-6

        y_co2_in = gas_in.composition.get("CO2", 0.0)
        y_h2s_in = gas_in.composition.get("H2S", 0.0)

        n_amine, c_amine = _lean_amine_basis(lean_amine_in, amine)
        z_lean = lean_amine_in.composition
        lean_co2_loading = z_lean.get("CO2", 0.0) / z_lean[amine]
        lean_h2s_loading = z_lean.get("H2S", 0.0) / z_lean[amine]

        T = gas_in.T
        P = gas_in.P

        # A reactive amine property package carries its own chemistry: use it
        # for speciation and every outlet state (spec P1-04).  A plain cubic
        # keeps today's facade-based behaviour byte-identical.
        amine_pkg = (
            cast(AmineReactivePackage, thermo)
            if getattr(thermo, "is_amine_reactive_package", False)
            else None
        )
        model_name = "the selected equilibrium model" if amine_pkg is not None else "Kent-Eisenberg"

        # Top (lean) floor: lowest outlet content the lean amine can impose.
        if amine_pkg is not None:
            floor_eq = amine_pkg.equilibrium_pressures(z_lean, T, lean_co2_loading, lean_h2s_loading)
            p_co2_floor, p_h2s_floor = floor_eq["CO2"], floor_eq["H2S"]
        else:
            p_co2_floor, p_h2s_floor = equilibrium_partial_pressures(
                params, T, c_amine, lean_co2_loading, lean_h2s_loading, amine=amine
            )
        floor_co2 = p_co2_floor / P
        floor_h2s = p_h2s_floor / P
        if y_co2_out < floor_co2:
            raise ValueError(
                f"infeasible spec: requested outlet CO2 {co2_out_molpct} mol% is below the "
                f"lean-amine equilibrium floor {floor_co2 * 100:.4g} mol% ({model_name})"
            )
        if y_h2s_out < floor_h2s:
            raise ValueError(
                f"infeasible spec: requested outlet H2S {h2s_out_ppmv} ppmv is below the "
                f"lean-amine equilibrium floor {floor_h2s * 1e6:.4g} ppmv ({model_name})"
            )

        removed_co2, removed_h2s = _acid_gas_removals(
            gas_in.molar_flow, y_co2_in, y_h2s_in, y_co2_out, y_h2s_out
        )

        # Bottom (rich) ceiling: loadings the inlet gas partial pressures support.
        if amine_pkg is not None:
            max_co2_loading, max_h2s_loading = amine_pkg.equilibrium_loadings(
                z_lean, T, y_co2_in * P, y_h2s_in * P
            )
        else:
            max_co2_loading, max_h2s_loading = equilibrium_loadings(
                params, T, c_amine, y_co2_in * P, y_h2s_in * P, amine=amine
            )
        rich_co2_loading = lean_co2_loading + removed_co2 / n_amine
        rich_h2s_loading = lean_h2s_loading + removed_h2s / n_amine
        if rich_co2_loading > max_co2_loading:
            raise ValueError(
                f"infeasible circulation: rich CO2 loading {rich_co2_loading:.3f} exceeds the "
                f"bottom-stage equilibrium ceiling {max_co2_loading:.3f} mol/mol at the inlet gas "
                f"partial pressure -- increase the amine rate (amine_per_acid_gas_removed)"
            )
        if rich_h2s_loading > max_h2s_loading:
            raise ValueError(
                f"infeasible circulation: rich H2S loading {rich_h2s_loading:.3f} exceeds the "
                f"bottom-stage equilibrium ceiling {max_h2s_loading:.3f} mol/mol at the inlet gas "
                f"partial pressure -- increase the amine rate (amine_per_acid_gas_removed)"
            )

        n_co2_out = gas_in.molar_flow * y_co2_in - removed_co2
        n_h2s_out = gas_in.molar_flow * y_h2s_in - removed_h2s
        gas_comp = _residual_composition(gas_in, n_co2_out, n_h2s_out)
        gas_flow = gas_in.molar_flow - removed_co2 - removed_h2s
        gas_out = thermo.flash_pt(gas_comp, T, P, gas_flow)

        rich_comp, rich_flow = _plus_acid_gas(lean_amine_in, removed_co2, removed_h2s)
        rich_amine_out = thermo.flash_pt(rich_comp, T, P, rich_flow)

        duty_W = (
            gas_out.enthalpy * gas_out.molar_flow
            + rich_amine_out.enthalpy * rich_amine_out.molar_flow
            - gas_in.enthalpy * gas_in.molar_flow
            - lean_amine_in.enthalpy * lean_amine_in.molar_flow
        )

        info: dict[str, float] = {
            "co2_removed_mol_s": removed_co2,
            "h2s_removed_mol_s": removed_h2s,
            "co2_removal_fraction": removed_co2 / (gas_in.molar_flow * y_co2_in) if y_co2_in > 0.0 else 0.0,
            "h2s_removal_fraction": removed_h2s / (gas_in.molar_flow * y_h2s_in) if y_h2s_in > 0.0 else 0.0,
            "lean_co2_loading": lean_co2_loading,
            "lean_h2s_loading": lean_h2s_loading,
            "rich_co2_loading": rich_co2_loading,
            "rich_h2s_loading": rich_h2s_loading,
            "equilibrium_max_co2_loading": max_co2_loading,
            "equilibrium_max_h2s_loading": max_h2s_loading,
            "equilibrium_floor_co2_molpct": floor_co2 * 100.0,
            "equilibrium_floor_h2s_ppmv": floor_h2s * 1e6,
            "lean_amine_molarity_mol_per_l": c_amine / 1000.0,
            "amine_per_acid_gas_removed_mol_mol": (
                n_amine / (removed_co2 + removed_h2s) if (removed_co2 + removed_h2s) > 0.0 else 0.0
            ),
            "inlet_co2_molpct": y_co2_in * 100.0,
            "outlet_co2_molpct": float(co2_out_molpct),
            "inlet_h2s_ppmv": y_h2s_in * 1e6,
            "outlet_h2s_ppmv": float(h2s_out_ppmv),
        }
        if amine_pkg is not None:
            # Heat of absorption released into the streams by the removed acid
            # gas; the reactive package's outlet enthalpies already carry it.
            d_h_abs = amine_pkg.heat_of_absorption(rich_comp, T)
            info["heat_of_absorption_W"] = removed_co2 * d_h_abs["CO2"] + removed_h2s * d_h_abs["H2S"]

        return UnitResult(
            outlets={"gas_out": gas_out, "rich_amine_out": rich_amine_out},
            duty_W=duty_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Sour gas (6% CO2, 1.5% H2S) at 30 C / 6.5 MPa over the class's lean solvent."""
        feeds: dict[str, dict[str, Any]] = {
            "gas_in": {
                "T": 303.15,
                "P": 6.5e6,
                "molar_flow": 100.0,
                "composition": {
                    "C1": 0.85,
                    "C2": 0.05,
                    "C3": 0.02,
                    "N2": 0.005,
                    "CO2": 0.06,
                    "H2S": 0.015,
                },
            },
            "lean_amine_in": {
                "T": 303.15,
                "P": 6.5e6,
                "molar_flow": 92.0,
                "composition": _lean_amine_composition(cls.AMINE, cls.SOLVENT_MASS_FRACTION),
            },
        }
        params: dict[str, Any] = {}
        return feeds, params


@register("unit", "mea_absorber")
class MeaAbsorber(MdeaAbsorber):
    """MEA absorber: the Kent-Eisenberg absorber parameterized for aqueous MEA."""

    AMINE = "MEA"
    SOLVENT_MASS_FRACTION = EXAMPLE_MEA_MASS_FRACTION


@register("unit", "dea_absorber")
class DeaAbsorber(MdeaAbsorber):
    """DEA absorber: the Kent-Eisenberg absorber parameterized for aqueous DEA."""

    AMINE = "DEA"
    SOLVENT_MASS_FRACTION = EXAMPLE_DEA_MASS_FRACTION
