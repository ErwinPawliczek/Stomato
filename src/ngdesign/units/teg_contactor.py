"""TEG contactor unit (spec S-29). Plugin kind "unit", name "teg_contactor".

Dehydrates a natural-gas stream to a water specification with lean
triethylene glycol (TEG) in a countercurrent absorber column:

    gas_in, lean_teg_in -> gas_out, rich_teg_out

Water is removed from the gas down to the outlet spec; the removed water
joins the lean TEG to form the rich TEG. No TEG losses to the gas are
modelled in v1, and no regeneration (spec: out of scope).

Water-content convention (GPSA): standard conditions hold 379.49 scf/lbmol,
so one MMscf of dry gas carries ``1e6 / 379.49`` lbmol. Water content in
lb/MMscf converts to a per-dry-gas mole ratio

    r = W / (MW_H2O * 1e6 / 379.49)   [mol H2O / mol dry gas]

and a wet-gas mole fraction follows as ``y = r / (1 + r)``.

Equilibrium assumption (documented per spec): the stage count uses the
Kremser correlation (S-05) with a linear equilibrium line ``y* = m * x``
whose slope is the GPSA-style ideal-solution linearization

    m = Psat,H2O(T_gas) / P_gas

with water saturation pressure from the IAPWS correlation shipped in
``chemicals`` and ``x`` the water mole fraction in the TEG phase. This is
the v1 approximation pending rigorous TEG/water VLE (spec: out of scope);
it ignores the water-activity depression of real TEG solutions, so the
reported stage count is indicative, not a design basis.

Duty is the enthalpy difference across the unit; the heat of
absorption/mixing is reported through it, not modelled separately.
"""

from __future__ import annotations

from typing import Any

from chemicals.vapor_pressure import Psat_IAPWS

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.registry import register
from ngdesign.sizing.kremser import kremser

__all__ = ["TEGContactor"]

#: Standard conditions volume basis, scf/lbmol (spec S-29).
SCF_PER_LBMOL = 379.49

#: Standard cubic feet per million standard cubic feet (unit factor).
LBMOL_PER_MMSCF = 1.0e6 / SCF_PER_LBMOL

#: Default outlet water spec, lb/MMscf (spec S-29).
DEFAULT_WATER_OUT_LB_PER_MMSCF = 7.0


def _water_mw() -> float:
    """Molecular weight of H2O, kg/kmol, from the repo reference data."""
    return float(components()["H2O"]["mw"])


def _ratio_to_fraction(r: float) -> float:
    """Mole ratio [mol solute / mol dry gas] -> wet-gas mole fraction."""
    return r / (1.0 + r)


def _fraction_to_ratio(y: float) -> float:
    """Wet-gas mole fraction -> mole ratio [mol solute / mol dry gas]."""
    return y / (1.0 - y)


def _water_content_lb_per_mmscf(y: float) -> float:
    """Water content of a wet gas with H2O mole fraction ``y``, lb/MMscf."""
    return _fraction_to_ratio(y) * _water_mw() * LBMOL_PER_MMSCF


def _shift_water(state: StreamState, water_delta: float) -> tuple[dict[str, float], float]:
    """Return (composition, molar_flow) with ``water_delta`` added to the H2O flow.

    All other component flows are held fixed, so the component balances of
    the unit close exactly.
    """
    flows = {c: f * state.molar_flow for c, f in state.composition.items()}
    flows["H2O"] = flows.get("H2O", 0.0) + water_delta
    total = sum(flows.values())
    if total <= 0.0:
        raise ValueError("stream collapsed to zero molar flow")
    return {c: n / total for c, n in flows.items()}, total


@register("unit", "teg_contactor")
class TEGContactor:
    """Countercurrent TEG absorber dehydrating gas to a water spec."""

    inlet_ports: tuple[str, ...] = ("gas_in", "lean_teg_in")
    outlet_ports: tuple[str, ...] = ("gas_out", "rich_teg_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        gas_in = inlets["gas_in"]
        lean_teg_in = inlets["lean_teg_in"]

        water_out_spec = float(params.get("water_out_lb_per_mmscf", DEFAULT_WATER_OUT_LB_PER_MMSCF))
        if not water_out_spec > 0.0:
            raise ValueError(f"water_out_lb_per_mmscf must be positive, got {water_out_spec}")

        y_in = gas_in.composition.get("H2O", 0.0)
        water_in_content = _water_content_lb_per_mmscf(y_in)
        if water_out_spec >= water_in_content:
            raise ValueError(
                f"infeasible spec: requested outlet water content "
                f"{water_out_spec} lb/MMscf exceeds inlet water content "
                f"{water_in_content:.4g} lb/MMscf"
            )

        # Water removal on the dry-gas basis (GPSA conversion, spec S-29).
        dry_flow = gas_in.molar_flow * (1.0 - y_in)
        r_in = _fraction_to_ratio(y_in)
        r_out = water_out_spec / (_water_mw() * LBMOL_PER_MMSCF)
        water_removed = dry_flow * (r_in - r_out)
        if water_removed <= 0.0:
            raise ValueError(
                f"infeasible spec: no water to remove (inlet "
                f"{water_in_content:.4g} lb/MMscf vs spec {water_out_spec})"
            )

        T = gas_in.T
        P = gas_in.P

        gas_comp, gas_flow = _shift_water(gas_in, -water_removed)
        gas_out = thermo.flash_pt(gas_comp, T, P, gas_flow)

        rich_comp, rich_flow = _shift_water(lean_teg_in, water_removed)
        rich_teg_out = thermo.flash_pt(rich_comp, T, P, rich_flow)

        duty_W = (
            gas_out.enthalpy * gas_out.molar_flow
            + rich_teg_out.enthalpy * rich_teg_out.molar_flow
            - gas_in.enthalpy * gas_in.molar_flow
            - lean_teg_in.enthalpy * lean_teg_in.molar_flow
        )

        return UnitResult(
            outlets={"gas_out": gas_out, "rich_teg_out": rich_teg_out},
            duty_W=duty_W,
            info=self._info(gas_in, gas_out, lean_teg_in, dry_flow, water_removed, params),
        )

    def _info(
        self,
        gas_in: StreamState,
        gas_out: StreamState,
        lean_teg_in: StreamState,
        dry_flow: float,
        water_removed: float,
        params: dict[str, Any],
    ) -> dict[str, float]:
        """Reported scalars: removed water, circulation ratio, Kremser stages."""
        mw_h2o = _water_mw()
        water_removed_kg_h = water_removed * mw_h2o / 1000.0 * 3600.0

        # Lean TEG volume from the flashed liquid density of the inlet stream.
        if not lean_teg_in.phases:
            raise ValueError("lean_teg_in must be a flashed stream (has phases)")
        solvent = max(lean_teg_in.phases, key=lambda p: p.mole_fraction)
        teg_mass_flow = lean_teg_in.molar_flow * solvent.molecular_weight / 1000.0
        teg_volume_L_s = teg_mass_flow / solvent.density * 1000.0
        water_kg_s = water_removed * mw_h2o / 1000.0
        circulation = teg_volume_L_s / water_kg_s

        # Kremser stage count (S-05) on the GPSA-style linearized equilibrium
        # line documented in the module docstring.
        m = Psat_IAPWS(gas_in.T) / gas_in.P
        A = lean_teg_in.molar_flow / (m * dry_flow)
        stages = kremser(
            A=A,
            y_in=gas_in.composition["H2O"],
            y_out=gas_out.composition["H2O"],
            m=m,
            x_top=lean_teg_in.composition.get("H2O", 0.0),
        )["N_stages"]

        return {
            "water_removed_kg_h": water_removed_kg_h,
            "teg_circulation_L_per_kg_water": circulation,
            "N_stages": stages,
            "inlet_water_lb_per_mmscf": _water_content_lb_per_mmscf(gas_in.composition["H2O"]),
            "outlet_water_lb_per_mmscf": float(
                params.get("water_out_lb_per_mmscf", DEFAULT_WATER_OUT_LB_PER_MMSCF)
            ),
        }

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Sweet natural gas at 30 C / 7.1 MPa with ~24 lb/MMscf water, 99.8 wt% lean TEG."""
        feeds: dict[str, dict[str, Any]] = {
            "gas_in": {
                "T": 303.15,
                "P": 7.1e6,
                "molar_flow": 100.0,
                "composition": {
                    "C1": 0.90,
                    "C2": 0.05,
                    "C3": 0.03,
                    "CO2": 0.0095,
                    "N2": 0.0100,
                    "H2O": 0.0005,
                },
            },
            "lean_teg_in": {
                "T": 303.15,
                "P": 7.1e6,
                "molar_flow": 0.2,
                "composition": {"TEG": 0.985, "H2O": 0.015},
            },
        }
        return feeds, {}
