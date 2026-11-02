"""Naphtha hydrotreater R1: model-compound kinetics in catalyst beds (``specs/backend/units/naphtha_ht.md``).

The slate and stoichiometry are R0's (Fahim, Al-Sahhaf & Elkilani, *Fundamentals of
Petroleum Refining*, 2010, E12.2):

    hds_thiophene   thiophene + 4 H2 -> nC4 + H2S
    hdn_pyridine    pyridine + 5 H2 -> nC5 + NH3
    olefin_sat      1-pentene + H2 -> nC5
    arom_sat        benzene + 3 H2 -> cyclohexane

The kinetics are the contract's own PowerLaw or LHHW, per kg of catalyst, and are
required inputs: a Satterfield-type H2S-inhibited HDS, r = k*y_T*y_H2/(1 + K*y_H2S)**2,
is an LHHW with exponent 2 (Satterfield & Roberts, AIChE J. 14 (1968) 159, form only).
A reaction left out of ``kinetics`` is inactive.  No rate constant is a default.

Each bed is the pfr integrator over V_b = W_b/rho_b, so the integral of rho_b*r' dV is
the integral of r' dW exactly, and closes exactly through ``thermal_outlet``.  Beds run
in flow order with an optional heater before each.  The sharp final split and the
overall duty are R0's definitions.  Pseudo-components are refused: the kinetics act on
real model compounds and a pseudo carrier has no formation enthalpy for the bed closure
(issue #222); R0 remains the level for a pseudo naphtha.  All SI.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import LHHW, PowerLaw, Reaction, ReactionSet
from ngdesign.data import component_record
from ngdesign.units._physics.kinetics import apply_extents
from ngdesign.units.balance import energy_basis, stream_enthalpy
from ngdesign.units.reactors._shared import thermal_outlet, z_from
from ngdesign.units.reactors.plug_flow import _CATALYST_RATE_UNITS, integrate_plug_flow
from ngdesign.units.refining.reactors_hdt import _GAS_CIDS, AW_NITROGEN, AW_SULFUR

#: The R0 reactions: id -> (stoichiometry, base component).
_SLATE: dict[str, tuple[dict[str, float], str]] = {
    "hds_thiophene": ({"thiophene": -1.0, "H2": -4.0, "nC4": 1.0, "H2S": 1.0}, "thiophene"),
    "hdn_pyridine": ({"pyridine": -1.0, "H2": -5.0, "nC5": 1.0, "NH3": 1.0}, "pyridine"),
    "olefin_sat": ({"1-pentene": -1.0, "H2": -1.0, "nC5": 1.0}, "1-pentene"),
    "arom_sat": ({"benzene": -1.0, "H2": -3.0, "cyclohexane": 1.0}, "benzene"),
}


class HdtKineticError(ValueError):
    """A refused naphtha_ht R1 specification; the message names the parameter."""


def _reaction_set(kinetics: Mapping[str, Any], slate: set[str]) -> ReactionSet:
    """The active reactions with the user's kinetics (spec equations 1-2)."""
    unknown = sorted(set(kinetics) - set(_SLATE))
    if unknown:
        raise HdtKineticError(f"kinetics names unknown reactions {unknown}; expected {sorted(_SLATE)}")
    if not kinetics:
        raise HdtKineticError("kinetics must give at least one reaction")
    reactions: list[Reaction] = []
    for rid, (stoichiometry, base) in _SLATE.items():
        if rid not in kinetics:
            continue
        body = kinetics[rid]
        try:
            model: PowerLaw | LHHW = (
                LHHW.model_validate(body)
                if isinstance(body, Mapping) and "driving_force" in body
                else PowerLaw.model_validate(body)
            )
        except ValueError as exc:
            raise HdtKineticError(f"kinetics[{rid!r}] is not a PowerLaw or LHHW: {exc}") from exc
        if model.rate_units not in _CATALYST_RATE_UNITS:
            raise HdtKineticError(f"kinetics[{rid!r}]: rate_units {model.rate_units!r} must be per kg_cat")
        reactions.append(
            Reaction(
                id=rid,
                stoichiometry=stoichiometry,
                base_component=base,
                provenance="Fahim et al. 2010 E12.2 stoichiometry; user kinetics",
                kinetics=model,
            )
        )
        slate.update(stoichiometry)
    return ReactionSet(id="naphtha_ht_r1", reactions=reactions, components=sorted(slate))


def _mixed_feed(inlets: Mapping[str, StreamState], thermo: Thermo) -> StreamState:
    """Adiabatic mix at the lower inlet pressure (spec equation 4)."""
    n: dict[str, float] = {}
    enthalpy = 0.0
    for port in ("naphtha_in", "h2_in"):
        stream = inlets[port]
        enthalpy += stream.enthalpy * stream.molar_flow
        for cid, flow in stream.component_flows().items():
            n[cid] = n.get(cid, 0.0) + flow
    total = math.fsum(n.values())
    return thermo.flash_ph(z_from(n), min(s.P for s in inlets.values()), enthalpy / total, total)


class NaphthaHydrotreaterR1:
    """Naphtha hydrotreater with kinetic catalyst beds, level R1."""

    inlet_ports: tuple[str, ...] = ("naphtha_in", "h2_in")
    outlet_ports: tuple[str, ...] = ("treated_out", "gas_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        for stream in inlets.values():
            for cid in stream.composition:
                if component_record(cid)["kind"] == "pseudo":
                    raise HdtKineticError(
                        f"pseudo component {cid!r}: the kinetics act on real model compounds; "
                        "pseudo elemental characterisation is issue #222, use level R0"
                    )
        beds = params.get("beds")
        if not isinstance(beds, list) or not beds:
            raise HdtKineticError("beds must be a non-empty list")
        rho_b = params.get("bulk_density_kg_m3")
        if rho_b is None or float(rho_b) <= 0.0:
            raise HdtKineticError("bulk_density_kg_m3 is required and must be > 0")
        bulk = float(rho_b)
        kinetics = params.get("kinetics")
        if not isinstance(kinetics, Mapping):
            raise HdtKineticError("kinetics must give at least one reaction")
        for i, bed in enumerate(beds):
            if float(bed.get("catalyst_mass_kg", 0.0)) <= 0.0:
                raise HdtKineticError(f"beds[{i}].catalyst_mass_kg must be > 0")
            if bed.get("thermal", "adiabatic") not in ("adiabatic", "isothermal"):
                raise HdtKineticError(f"beds[{i}].thermal must be 'adiabatic' or 'isothermal'")
            if "inlet_T_K" in bed and float(bed["inlet_T_K"]) <= 0.0:
                raise HdtKineticError(f"beds[{i}].inlet_T_K must be > 0")

        slate = {cid for s in inlets.values() for cid in s.composition}
        rset = _reaction_set(kinetics, slate)
        info: dict[str, float] = {f"inactive_{rid}": 1.0 for rid in _SLATE if rid not in kinetics}
        state = _mixed_feed(inlets, thermo)
        feed_flows = state.component_flows()
        n_now = dict(feed_flows)
        duties = 0.0
        for k, bed in enumerate(beds):
            if "inlet_T_K" in bed:
                heated = thermo.flash_pt(dict(state.composition), float(bed["inlet_T_K"]), state.P, state.molar_flow)
                heat = (heated.enthalpy - state.enthalpy) * state.molar_flow
                info[f"heater_duty_b{k}_W"] = heat
                duties += heat
                state = heated
            thermal = bed.get("thermal", "adiabatic")
            profile = integrate_plug_flow(
                state,
                rset,
                thermo,
                volume_m3=float(bed["catalyst_mass_kg"]) / bulk,
                energy=thermal,
                bulk_density_kg_m3=bulk,
                reacting_phase="vapor",
            )
            n_now = apply_extents(state.component_flows(), rset, list(profile.extents[-1]))
            state_out, duty = thermal_outlet(state, n_now, thermal, thermo)
            info[f"bed_duty_b{k}_W"] = duty
            info[f"bed_T_out_b{k}_K"] = float(state_out.T)
            info[f"T_closure_gap_b{k}_K"] = float(state_out.T) - profile.T_K[-1]
            duties += duty
            state = state_out

        gas_cids = sorted(cid for cid in _GAS_CIDS if n_now.get(cid, 0.0) > 0.0)
        treated_cids = sorted(cid for cid, n in n_now.items() if n > 0.0 and cid not in _GAS_CIDS)
        if not gas_cids:
            raise HdtKineticError("gas_out would carry no species: give hydrogen excess or S/N removal")
        outlets: dict[str, StreamState] = {}
        for port, cids in (("treated_out", treated_cids), ("gas_out", gas_cids)):
            total = math.fsum(n_now[cid] for cid in cids)
            outlets[port] = thermo.flash_pt({cid: n_now[cid] / total for cid in cids}, state.T, state.P, total)

        mass = math.fsum(n * float(component_record(cid)["mw"]) for cid, n in feed_flows.items())
        info.update(
            h2_consumed_mol_s=feed_flows.get("H2", 0.0) - n_now.get("H2", 0.0),
            h2s_mol_s=n_now.get("H2S", 0.0) - feed_flows.get("H2S", 0.0),
            nh3_mol_s=n_now.get("NH3", 0.0) - feed_flows.get("NH3", 0.0),
            feed_sulfur_wt_pct=100.0 * feed_flows.get("thiophene", 0.0) * AW_SULFUR / mass,
            feed_nitrogen_wt_pct=100.0 * feed_flows.get("pyridine", 0.0) * AW_NITROGEN / mass,
        )
        basis = energy_basis("mass_elements", inlets.values(), outlets.values(), info)
        duty_w = stream_enthalpy(outlets.values(), basis) - stream_enthalpy(inlets.values(), basis)
        info["split_enthalpy_W"] = duty_w - duties
        return UnitResult(outlets=outlets, duty_W=duty_w, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Two adiabatic beds on an nC7 carrier: test-only kinetics, illustrative, NOT published."""

        def law(k0: float, *orders: str) -> dict[str, Any]:
            return {
                "rate_units": "mol/(kg_cat·s)",
                "k0": k0,
                "Ea": 3.0e4,
                "orders": dict.fromkeys(orders, 1.0),
                "basis": "mole_fraction",
            }

        total = 1.0 + 0.01 + 0.01 + 0.02 + 0.02
        feeds = {
            "naphtha_in": {
                "T": 610.0,
                "P": 3.0e6,
                "molar_flow": total,
                "composition": {
                    "nC7": 1.0 / total,
                    "thiophene": 0.01 / total,
                    "pyridine": 0.01 / total,
                    "1-pentene": 0.02 / total,
                    "benzene": 0.02 / total,
                },
            },
            "h2_in": {"T": 610.0, "P": 3.0e6, "molar_flow": 3.0, "composition": {"H2": 1.0}},
        }
        params: dict[str, Any] = {
            "beds": [
                {"catalyst_mass_kg": 50.0, "thermal": "adiabatic"},
                {"catalyst_mass_kg": 50.0, "thermal": "adiabatic", "inlet_T_K": 620.0},
            ],
            "bulk_density_kg_m3": 800.0,
            "kinetics": {
                "hds_thiophene": {
                    "rate_units": "mol/(kg_cat·s)",
                    "basis": "mole_fraction",
                    "driving_force": [
                        {"arrhenius": {"k0": 50.0, "Ea": 3.0e4}, "orders": {"thiophene": 1.0, "H2": 1.0}}
                    ],
                    "adsorption": [
                        {"arrhenius": {"k0": 1.0, "Ea": 0.0}, "orders": {}},
                        {"arrhenius": {"k0": 20.0, "Ea": 0.0}, "orders": {"H2S": 1.0}},
                    ],
                    "adsorption_exponent": 2.0,
                },
                "hdn_pyridine": law(20.0, "pyridine"),
                "olefin_sat": law(50.0, "1-pentene"),
                "arom_sat": law(20.0, "benzene"),
            },
        }
        return feeds, params
