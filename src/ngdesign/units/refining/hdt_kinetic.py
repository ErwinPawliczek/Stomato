"""Naphtha hydrotreater R1: kinetic model-compound HDS/HDN/saturation (spec U-R2).

``NaphthaHydrotreaterR1`` keeps the R0 slate (Fahim, Al-Sahhaf & Elkilani,
*Fundamentals of Petroleum Refining*, Elsevier 2010, worked Example E12.2
(p. 309) and the pyridine HDN reaction of the ch. 7 hydroconversion scheme
(7.1) (p. 156)) but replaces the declared removal fractions with kinetics in
catalyst beds on the shared pfr integrator
:func:`ngdesign.units.reactors.plug_flow.integrate_plug_flow`:

    hds_thiophene:  thiophene + 4 H2 -> nC4 + H2S   (E12.2.1, HDS)
    hdn_pyridine:   pyridine  + 5 H2 -> nC5 + NH3   (scheme (7.1), p. 156, HDN)
    olefin_sat:     1-pentene + H2   -> nC5         (E12.2.2, olefin saturation)
    arom_sat:       benzene   + 3 H2 -> cyclohexane (E12.2.3, aromatic saturation)

Each bed integrates the extents over ``V_b = W_b/rho_b`` (rates per kg_cat
scaled by the bulk density, pfr spec equation 3), then closes the bed energy
exactly through ``_shared.thermal_outlet`` on the formation-enthalpy basis.
Feed mixing is flash_ph at the minimum inlet pressure (spec equation 4);
each bed may carry a heater to its ``inlet_T_K`` (spec equation 5).  The
final effluent is split as in R0: ``gas_out`` takes the ``_GAS_CIDS`` species
(the single owner of the gas/treated split, imported read-only), `treated_out`
the rest.  Pseudo components are refused in either inlet (the kinetics act on
real model compounds and a pseudo carries no formation enthalpy for the bed
closure — issue #222); R0 remains the level for pseudo naphtha.

All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import LHHW, PowerLaw, Reaction, ReactionSet
from ngdesign.contracts.stream import StreamState
from ngdesign.data import component_record
from ngdesign.units._physics.kinetics import apply_extents
from ngdesign.units.balance import energy_basis, species_without_formation, stream_enthalpy
from ngdesign.units.reactors._shared import thermal_outlet, z_from
from ngdesign.units.reactors.plug_flow import integrate_plug_flow
from ngdesign.units.refining.reactors_hdt import _GAS_CIDS, AW_NITROGEN, AW_SULFUR

#: Rate-unit spellings accepted for per-kg_cat kinetics (pfr equation 3).
_KG_CAT_UNITS = ("mol/(kg_cat·s)", "mol/(kg_cat*s)", "mol/kg_cat/s")


class HdtKineticError(ValueError):
    """Raised when the naphtha_ht R1 params or feeds are ill-posed."""


#: The fixed slate (spec equation 1): id -> (stoichiometry, base component,
#: provenance), in the order the reactions are registered in the set.
_SLATE: tuple[tuple[str, dict[str, float], str, str], ...] = (
    (
        "hds_thiophene",
        {"thiophene": -1.0, "H2": -4.0, "nC4": 1.0, "H2S": 1.0},
        "thiophene",
        "Fahim, Al-Sahhaf & Elkilani 2010, worked Example E12.2.1 (p. 309)",
    ),
    (
        "hdn_pyridine",
        {"pyridine": -1.0, "H2": -5.0, "nC5": 1.0, "NH3": 1.0},
        "pyridine",
        "Fahim, Al-Sahhaf & Elkilani 2010, scheme (7.1) (p. 156)",
    ),
    (
        "olefin_sat",
        {"1-pentene": -1.0, "H2": -1.0, "nC5": 1.0},
        "1-pentene",
        "Fahim, Al-Sahhaf & Elkilani 2010, worked Example E12.2.2 (p. 309)",
    ),
    (
        "arom_sat",
        {"benzene": -1.0, "H2": -3.0, "cyclohexane": 1.0},
        "benzene",
        "Fahim, Al-Sahhaf & Elkilani 2010, worked Example E12.2.3 (p. 309)",
    ),
)

_KINETICS_ADAPTER: TypeAdapter[PowerLaw | LHHW] = TypeAdapter(PowerLaw | LHHW)


@dataclass(frozen=True)
class _Bed:
    """One validated catalyst bed."""

    catalyst_mass_kg: float
    inlet_T_K: float | None
    thermal: str


def _positive(params: Mapping[str, Any], key: str) -> float:
    value = params.get(key)
    if value is None:
        raise HdtKineticError(f"naphtha_ht: {key} is required")
    v = float(value)
    if not v > 0.0:
        raise HdtKineticError(f"naphtha_ht: {key} {v} must be > 0")
    return v


def _beds_param(params: Mapping[str, Any]) -> list[_Bed]:
    beds_raw = params.get("beds")
    if not isinstance(beds_raw, (list, tuple)) or not beds_raw:
        raise HdtKineticError("naphtha_ht: beds must be a non-empty array of bed specs")
    beds: list[_Bed] = []
    for i, raw in enumerate(beds_raw, 1):
        if not isinstance(raw, Mapping):
            raise HdtKineticError(f"naphtha_ht: beds[{i}] must be a mapping of bed fields")
        w = raw.get("catalyst_mass_kg")
        if w is None:
            raise HdtKineticError(f"naphtha_ht: beds[{i}].catalyst_mass_kg is required")
        w_f = float(w)
        if not w_f > 0.0:
            raise HdtKineticError(f"naphtha_ht: beds[{i}].catalyst_mass_kg {w_f} must be > 0")
        thermal = raw.get("thermal")
        if thermal not in ("adiabatic", "isothermal"):
            raise HdtKineticError(
                f"naphtha_ht: beds[{i}].thermal {thermal!r} is not one of 'adiabatic', 'isothermal'"
            )
        t_in = raw.get("inlet_T_K")
        t_in_f: float | None = None
        if t_in is not None:
            t_in_f = float(t_in)
            if not t_in_f > 0.0:
                raise HdtKineticError(f"naphtha_ht: beds[{i}].inlet_T_K {t_in_f} must be > 0")
        beds.append(_Bed(catalyst_mass_kg=w_f, inlet_T_K=t_in_f, thermal=str(thermal)))
    return beds


def _kinetics_param(params: Mapping[str, Any]) -> dict[str, PowerLaw | LHHW]:
    kin = params.get("kinetics")
    if not isinstance(kin, Mapping) or not kin:
        raise HdtKineticError(
            "naphtha_ht: kinetics must name at least one of the four reaction ids "
            f"{[rid for rid, *_ in _SLATE]} — an omitted reaction is inactive"
        )
    out: dict[str, PowerLaw | LHHW] = {}
    for rid, body in kin.items():
        rid_s = str(rid)
        if rid_s not in {rid for rid, *_ in _SLATE}:
            raise HdtKineticError(
                f"naphtha_ht: kinetics key {rid_s!r} is not one of {[rid for rid, *_ in _SLATE]}"
            )
        try:
            parsed = _KINETICS_ADAPTER.validate_python(body)
        except ValidationError as exc:
            raise HdtKineticError(
                f"naphtha_ht: kinetics[{rid_s!r}] is not a contract PowerLaw or LHHW: {exc}"
            ) from exc
        if parsed.rate_units not in _KG_CAT_UNITS:
            raise HdtKineticError(
                f"naphtha_ht: kinetics[{rid_s!r}] rate_units {parsed.rate_units!r} is not "
                f"per kg catalyst (one of {_KG_CAT_UNITS})"
            )
        out[rid_s] = parsed
    return out


def _build_rset(
    kinetics: Mapping[str, PowerLaw | LHHW],
    inlet_cids: set[str],
) -> tuple[ReactionSet, list[str]]:
    """The ``naphtha_ht_r1`` set: the fixed slate with the user's kinetics.

    Reactions omitted from ``kinetics`` are not integrated (they are inactive,
    rate 0) and are returned as the second element, for the ``info`` report.
    """
    reactions = [
        Reaction(
            id=rid,
            stoichiometry=dict(stoich),
            base_component=base,
            provenance=prov,
            kinetics=kinetics[rid],
        )
        for rid, stoich, base, prov in _SLATE
        if rid in kinetics
    ]
    slate = set(inlet_cids) | {cid for _, stoich, _, _ in _SLATE for cid in stoich}
    rset = ReactionSet(id="naphtha_ht_r1", components=sorted(slate), reactions=reactions)
    inactive = [rid for rid, *_ in _SLATE if rid not in kinetics]
    return rset, inactive


def _mix(inlets: Mapping[str, StreamState], thermo: Thermo) -> StreamState:
    """Feed mixing without reaction (spec equation 4)."""
    n: dict[str, float] = {}
    h_total = 0.0
    for port in ("naphtha_in", "h2_in"):
        s = inlets[port]
        for cid, y in s.composition.items():
            n[cid] = n.get(cid, 0.0) + y * s.molar_flow
        h_total += s.molar_flow * s.enthalpy
    n_tot = math.fsum(n.values())
    p_mix = min(inlets["naphtha_in"].P, inlets["h2_in"].P)
    return thermo.flash_ph(z_from(n), p_mix, h_total / n_tot, n_tot)


def _heat_to(state: StreamState, t_target: float, thermo: Thermo) -> tuple[StreamState, float]:
    """Heater before a bed (spec equation 5): re-flash at ``t_target``, same P."""
    heated = thermo.flash_pt(z_from(state.component_flows()), t_target, state.P, state.molar_flow)
    duty = state.molar_flow * (heated.enthalpy - state.enthalpy)
    return heated, duty


def _split_outlets(
    n_final: Mapping[str, float], state: StreamState, thermo: Thermo
) -> dict[str, StreamState]:
    """The R0-identical gas/treated split (spec algorithm step 5)."""
    gas_cids = sorted(cid for cid in _GAS_CIDS if n_final.get(cid, 0.0) > 0.0)
    if not gas_cids:
        raise HdtKineticError(
            "naphtha_ht: gas_out would carry no species (no H2 excess, no H2S/NH3 formed) — "
            "give hydrogen excess or S/N removal"
        )
    treated_cids = sorted(cid for cid, n in n_final.items() if n > 0.0 and cid not in _GAS_CIDS)
    outlets: dict[str, StreamState] = {}
    for port, cids in (("treated_out", treated_cids), ("gas_out", gas_cids)):
        total = math.fsum(n_final[c] for c in cids)
        z = {c: n_final[c] / total for c in cids}
        outlets[port] = thermo.flash_pt(z, state.T, state.P, total)
    return outlets


class NaphthaHydrotreaterR1:
    """Naphtha hydrotreater, rigour level R1: kinetic beds on the pfr integrator."""

    inlet_ports: tuple[str, ...] = ("naphtha_in", "h2_in")
    outlet_ports: tuple[str, ...] = ("treated_out", "gas_out")

    def solve(
        self,
        inlets: Mapping[str, StreamState],
        params: Mapping[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        for port in self.inlet_ports:
            if port not in inlets:
                raise HdtKineticError(f"naphtha_ht: inlet port {port!r} is required")
        naphtha = inlets["naphtha_in"]
        h2 = inlets["h2_in"]

        # Algorithm step 1: validate the params, then refuse pseudo feeds.
        beds = _beds_param(params)
        rho = _positive(params, "bulk_density_kg_m3")
        kinetics = _kinetics_param(params)

        n_mix: dict[str, float] = {}
        for s in (naphtha, h2):
            for cid, y in s.composition.items():
                n_mix[cid] = n_mix.get(cid, 0.0) + y * s.molar_flow

        pseudos = species_without_formation([naphtha, h2])
        if pseudos:
            raise HdtKineticError(
                f"naphtha_ht: inlet species {pseudos} are pseudo components without formation "
                "enthalpy — the R1 kinetics act on real model compounds, which the bed energy "
                "closure needs (issue #222, pseudo elemental characterization); R0 remains "
                "the level for pseudo naphtha"
            )

        # Algorithm step 2: the reaction set, step 3: the mixer.
        rset, inactive = _build_rset(kinetics, set(n_mix))
        state = _mix(inlets, thermo)

        info: dict[str, float] = {}
        xi_last: dict[str, float] = {}

        # Algorithm step 4: the beds in flow order.
        for k, bed in enumerate(beds, 1):
            if bed.inlet_T_K is not None:
                state, q_heat = _heat_to(state, bed.inlet_T_K, thermo)
                info[f"heater_duty_b{k}_W"] = q_heat
            n_bed_in = state.component_flows()
            profile = integrate_plug_flow(
                state,
                rset,
                thermo,
                volume_m3=bed.catalyst_mass_kg / rho,
                energy=bed.thermal,  # type: ignore[arg-type]
                bulk_density_kg_m3=rho,
                reacting_phase="vapor",
            )
            n_out = apply_extents(n_bed_in, rset, profile.extents[-1])
            state, q_bed = thermal_outlet(state, n_out, bed.thermal, thermo)
            info[f"bed_duty_b{k}_W"] = q_bed
            info[f"bed_T_out_b{k}_K"] = float(state.T)
            info[f"T_closure_gap_b{k}_K"] = float(state.T) - float(profile.T_K[-1])
            xi_last = dict(zip([r.id for r in rset.reactions], profile.extents[-1], strict=True))

        # Algorithm step 5: the R0-identical gas/treated split.
        n_final = state.component_flows()
        gas_cids = sorted(cid for cid in _GAS_CIDS if n_final.get(cid, 0.0) > 0.0)
        if not gas_cids:
            raise HdtKineticError(
                "naphtha_ht: gas_out would carry no species (no H2 excess, no H2S/NH3 formed) — "
                "give hydrogen excess or S/N removal"
            )
        treated_cids = sorted(cid for cid, n in n_final.items() if n > 0.0 and cid not in _GAS_CIDS)
        outlets: dict[str, StreamState] = {}
        for port, cids in (("treated_out", treated_cids), ("gas_out", gas_cids)):
            total = math.fsum(n_final[c] for c in cids)
            z = {c: n_final[c] / total for c in cids}
            outlets[port] = thermo.flash_pt(z, state.T, state.P, total)

        # Algorithm step 6: duty on the formation basis + the R0 info keys.
        xi_hds = xi_last.get("hds_thiophene", 0.0)
        xi_hdn = xi_last.get("hdn_pyridine", 0.0)
        xi_olefin = xi_last.get("olefin_sat", 0.0)
        xi_arom = xi_last.get("arom_sat", 0.0)
        feed_mass = math.fsum(
            y * s.molar_flow * float(component_record(cid)["mw"])
            for s in (naphtha, h2)
            for cid, y in s.composition.items()
        )
        n_thio = n_mix.get("thiophene", 0.0)
        n_py = n_mix.get("pyridine", 0.0)
        sulfur_w = 100.0 * n_thio * AW_SULFUR / feed_mass
        nitrogen_w = 100.0 * n_py * AW_NITROGEN / feed_mass
        info.update(
            {
                "h2_consumed_mol_s": n_mix.get("H2", 0.0) - n_final.get("H2", 0.0),
                "h2s_mol_s": xi_hds,
                "nh3_mol_s": xi_hdn,
                "nbutane_mol_s": xi_hds,
                "npentane_mol_s": xi_hdn + xi_olefin,
                "cyclohexane_mol_s": xi_arom,
                "feed_sulfur_wt_pct": sulfur_w,
                "feed_nitrogen_wt_pct": nitrogen_w,
                "h2_makeup_maples_scf_bbl": 191.0 * sulfur_w - 30.7,
            }
        )
        for rid in inactive:
            info[f"inactive_{rid}"] = 1.0

        basis = energy_basis("mass_elements", (naphtha, h2), outlets.values(), info)
        duty_w = stream_enthalpy(outlets.values(), basis) - stream_enthalpy((naphtha, h2), basis)
        info["split_enthalpy_W"] = duty_w - math.fsum(
            q for key, q in info.items() if key.startswith(("heater_duty_", "bed_duty_"))
        )
        return UnitResult(outlets=outlets, duty_W=duty_w, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Two adiabatic beds over the four-reaction slate, nC7 carrier.

        Illustrative test kinetics (not transcribed parameters): first-order
        HDS/HDN/saturation power laws, per kg_cat.  A heater between the beds
        re-rates bed 2's inlet to 620 K.  hydrogen 1.3x the stoichiometric
        demand of the full slate.
        """
        n_c7, n_thio, n_py, n_pent, n_bz = 97.0, 1.0, 0.5, 1.0, 0.5  # mol/s
        h2_demand = 4.0 * n_thio + 5.0 * n_py + n_pent + 3.0 * n_bz
        h2_feed = 1.3 * h2_demand
        total = n_c7 + n_thio + n_py + n_pent + n_bz
        feeds: dict[str, dict[str, Any]] = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3.0e6,
                "molar_flow": total,
                "composition": {
                    "nC7": n_c7 / total,
                    "thiophene": n_thio / total,
                    "pyridine": n_py / total,
                    "1-pentene": n_pent / total,
                    "benzene": n_bz / total,
                },
            },
            "h2_in": {
                "T": 600.0,
                "P": 3.0e6,
                "molar_flow": h2_feed,
                "composition": {"H2": 1.0},
            },
        }
        params: dict[str, Any] = {
            "beds": [
                {"catalyst_mass_kg": 500.0, "thermal": "adiabatic"},
                {"catalyst_mass_kg": 500.0, "inlet_T_K": 620.0, "thermal": "adiabatic"},
            ],
            "bulk_density_kg_m3": 800.0,
            "kinetics": {
                "hds_thiophene": {
                    "rate_units": "mol/(kg_cat·s)",
                    "k0": 0.5,
                    "Ea": 0.0,
                    "orders": {"thiophene": 1.0, "H2": 1.0},
                    "basis": "mole_fraction",
                },
                "hdn_pyridine": {
                    "rate_units": "mol/(kg_cat·s)",
                    "k0": 0.5,
                    "Ea": 0.0,
                    "orders": {"pyridine": 1.0, "H2": 1.0},
                    "basis": "mole_fraction",
                },
                "olefin_sat": {
                    "rate_units": "mol/(kg_cat·s)",
                    "k0": 0.5,
                    "Ea": 0.0,
                    "orders": {"1-pentene": 1.0, "H2": 1.0},
                    "basis": "mole_fraction",
                },
                "arom_sat": {
                    "rate_units": "mol/(kg_cat·s)",
                    "k0": 0.2,
                    "Ea": 0.0,
                    "orders": {"benzene": 1.0, "H2": 1.0},
                    "basis": "mole_fraction",
                },
            },
        }
        return feeds, params
