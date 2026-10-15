"""MDEA absorber unit (Kent-Eisenberg). Plugin kind "unit", name "mdea_absorber".

First amine-treatment unit: sweetens a sour natural-gas stream to CO2 and H2S
outlet specifications with lean aqueous MDEA in a countercurrent absorber:

    gas_in, lean_amine_in -> gas_out, rich_amine_out

The absorbed CO2/H2S joins the lean amine to form the rich amine; MDEA and
water are held in the liquid (no amine or water cross-transfer modelled in v1,
the TEG-contact precedent). Chemistry lives in the unit -- the TEG-precedent
shape (``teg_activity.py``): the joint CO2/H2S/MDEA/H2O electrolyte equilibrium
is ``ngdesign.units.mdea_equilibrium`` (Kent-Eisenberg; Edwards et al. 1978
constants, NeqSim apparent MDEA constant, Jou-Mather-Otto 1982 fitted H2S
constant), shared with the future regenerator.

Spec-driven solve (TEG-contact precedent): the outlet specs set the removed
acid gas; the Kent-Eisenberg equilibrium then bounds the specs from both ends.

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

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.units.mdea_equilibrium import (
    amine_molarity,
    equilibrium_loadings,
    equilibrium_partial_pressures,
)

__all__ = ["MdeaAbsorber"]

#: Default outlet CO2 spec, mol% in the treated gas (sales-gas inert limit).
DEFAULT_CO2_OUT_MOLPCT = 2.0

#: Default outlet H2S spec, ppmv in the treated gas (0.25 grain/100 scf).
DEFAULT_H2S_OUT_PPMV = 4.0

#: Example lean-solvent basis: MDEA mass fraction of the MDEA + water pair.
EXAMPLE_MDEA_MASS_FRACTION = 0.50

#: Example lean loadings, mol acid gas per mol MDEA.
EXAMPLE_LEAN_CO2_LOADING = 0.005
EXAMPLE_LEAN_H2S_LOADING = 0.002


def _mw(component: str) -> float:
    """Molecular weight of a databanked component, g/mol."""
    return float(components()[component]["mw"])


def _mixture_mw(z: dict[str, float]) -> float:
    """Mole-fraction-weighted molecular weight of a composition, g/mol."""
    return sum(f * _mw(c) for c, f in z.items())


def _lean_amine_composition() -> dict[str, float]:
    """Mole fractions of 50 wt% aqueous MDEA carrying the example lean loadings.

    Built on a molar basis (1 mol MDEA, water to 50 wt% of the MDEA+water pair,
    then the dissolved acid gas), so the loadings are exact by construction.
    """
    n_mdea = 1.0
    n_h2o = _mw("MDEA") / _mw("H2O") * (EXAMPLE_MDEA_MASS_FRACTION / (1.0 - EXAMPLE_MDEA_MASS_FRACTION))
    n_co2 = EXAMPLE_LEAN_CO2_LOADING * n_mdea
    n_h2s = EXAMPLE_LEAN_H2S_LOADING * n_mdea
    total = n_mdea + n_h2o + n_co2 + n_h2s
    return {
        "MDEA": n_mdea / total,
        "H2O": n_h2o / total,
        "CO2": n_co2 / total,
        "H2S": n_h2s / total,
    }


def _lean_amine_basis(lean_amine: StreamState) -> tuple[float, float]:
    """MDEA molar flow (mol/s) and amine molarity (mol/m3) of the lean solvent.

    The lean amine is a defined single-liquid solution, so the unit consumes
    the OVERALL stream composition, never phase splits: cubic-EOS phase
    splits of electrolytic amines are classification artifacts (an MDEA-rich
    liquid can come back labelled "vapor" while the "aqueous" phase is
    nearly pure water), and phase-local mole fractions are not trustworthy.
    The solution density is the densest flashed phase's density -- the best
    liquid density the Peng-Robinson package offers for the solution.
    """
    if not lean_amine.phases:
        raise ValueError("lean_amine_in must be a flashed stream (has phases)")
    z = lean_amine.composition
    n_mdea = lean_amine.molar_flow * z.get("MDEA", 0.0)
    if n_mdea <= 0.0:
        raise ValueError("lean_amine_in carries no MDEA; not an amine solvent")
    rho = max(p.density for p in lean_amine.phases)
    c_amine = amine_molarity(z["MDEA"], _mixture_mw(z), rho)
    return n_mdea, c_amine


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
    """Countercurrent MDEA absorber sweetening gas to CO2/H2S specs."""

    inlet_ports: tuple[str, ...] = ("gas_in", "lean_amine_in")
    outlet_ports: tuple[str, ...] = ("gas_out", "rich_amine_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        gas_in = inlets["gas_in"]
        lean_amine_in = inlets["lean_amine_in"]

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

        n_mdea, c_amine = _lean_amine_basis(lean_amine_in)
        z_lean = lean_amine_in.composition
        lean_co2_loading = z_lean.get("CO2", 0.0) / z_lean["MDEA"]
        lean_h2s_loading = z_lean.get("H2S", 0.0) / z_lean["MDEA"]

        T = gas_in.T
        P = gas_in.P

        # Top (lean) floor: lowest outlet content the lean amine can impose.
        p_co2_floor, p_h2s_floor = equilibrium_partial_pressures(
            T, c_amine, lean_co2_loading, lean_h2s_loading
        )
        floor_co2 = p_co2_floor / P
        floor_h2s = p_h2s_floor / P
        if y_co2_out < floor_co2:
            raise ValueError(
                f"infeasible spec: requested outlet CO2 {co2_out_molpct} mol% is below the "
                f"lean-amine equilibrium floor {floor_co2 * 100:.4g} mol% (Kent-Eisenberg)"
            )
        if y_h2s_out < floor_h2s:
            raise ValueError(
                f"infeasible spec: requested outlet H2S {h2s_out_ppmv} ppmv is below the "
                f"lean-amine equilibrium floor {floor_h2s * 1e6:.4g} ppmv (Kent-Eisenberg)"
            )

        removed_co2, removed_h2s = _acid_gas_removals(
            gas_in.molar_flow, y_co2_in, y_h2s_in, y_co2_out, y_h2s_out
        )

        # Bottom (rich) ceiling: loadings the inlet gas partial pressures support.
        max_co2_loading, max_h2s_loading = equilibrium_loadings(T, c_amine, y_co2_in * P, y_h2s_in * P)
        rich_co2_loading = lean_co2_loading + removed_co2 / n_mdea
        rich_h2s_loading = lean_h2s_loading + removed_h2s / n_mdea
        if rich_co2_loading > max_co2_loading:
            raise ValueError(
                f"infeasible circulation: rich CO2 loading {rich_co2_loading:.3f} exceeds the "
                f"bottom-stage equilibrium ceiling {max_co2_loading:.3f} mol/mol at the inlet gas "
                f"partial pressure -- increase the amine rate (mdea_per_acid_gas_removed)"
            )
        if rich_h2s_loading > max_h2s_loading:
            raise ValueError(
                f"infeasible circulation: rich H2S loading {rich_h2s_loading:.3f} exceeds the "
                f"bottom-stage equilibrium ceiling {max_h2s_loading:.3f} mol/mol at the inlet gas "
                f"partial pressure -- increase the amine rate (mdea_per_acid_gas_removed)"
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
            "mdea_per_acid_gas_removed_mol_mol": (
                n_mdea / (removed_co2 + removed_h2s) if (removed_co2 + removed_h2s) > 0.0 else 0.0
            ),
            "inlet_co2_molpct": y_co2_in * 100.0,
            "outlet_co2_molpct": float(co2_out_molpct),
            "inlet_h2s_ppmv": y_h2s_in * 1e6,
            "outlet_h2s_ppmv": float(h2s_out_ppmv),
        }

        return UnitResult(
            outlets={"gas_out": gas_out, "rich_amine_out": rich_amine_out},
            duty_W=duty_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Sour gas (6% CO2, 1.5% H2S) at 30 C / 6.5 MPa over 50 wt% lean MDEA."""
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
                "composition": _lean_amine_composition(),
            },
        }
        params: dict[str, Any] = {}
        return feeds, params
