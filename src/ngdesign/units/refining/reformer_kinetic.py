"""Catalytic reformer R1 — Smith (1959) four-reaction lumped kinetics (spec U-R2 wave).

``CatalyticReformerR1`` is the R1 adapter of row ``reformer_cat``: the naphtha
lumps are carried as representative real C7 species so every reaction is
element-balanced and the row's ``mass_elements`` V0 closes on the formation
basis with a real heat of reaction:

- P (paraffins)  = ``nC7``   (C7H16)
- N (naphthenes) = ``methylcyclohexane`` (C7H14)
- A (aromatics)  = ``toluene`` (C7H8)
- Smith's light ends C1–C5, split equally on a molar basis: ``C1``, ``C2``,
  ``C3``, ``nC4``, ``nC5``.

Four reactions (Smith, *Chem. Eng. Prog.* 55(6) (1959) 76–80, with n = 7;
spec ``specs/backend/units/reformer_cat.md`` eq. 2):

- ``dehydro``: N ⇌ A + 3 H2,        r1 = k1·(p_N − p_A·p_H³/K1)
- ``n_to_p``:  N + H2 ⇌ P,          r2 = k2·(p_N·p_H − p_P/K2)
- ``hc_n``:    N + (7/3) H2 → (7/15)(C1+C2+C3+nC4+nC5),  r3 = k3·p_N/P
- ``hc_p``:    P + (4/3) H2 → (7/15)(C1+C2+C3+nC4+nC5),  r4 = k4·p_P/P

Partial pressures p_i = y_i·P_atm with P_atm = P/101325 for the isobaric bed.
Every unit conversion from Smith's published rate constants to the contract's
``PowerLaw`` form happens in :func:`_smith_to_contract`, one commented factor
each (spec eq. 4 and the review checklist).

All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw, PowerLawRate, Reaction, ReactionSet
from ngdesign.data import component_record
from ngdesign.units._physics.kinetics import R, apply_extents, enthalpy_with_formation
from ngdesign.units.balance import stream_enthalpy
from ngdesign.units.reactors._shared import thermal_outlet, z_from
from ngdesign.units.reactors.plug_flow import PlugFlowProfile, integrate_plug_flow

#: The allowed feed slate (spec algorithm step 1). Anything else — a petroleum
#: pseudo-component in particular — is refused, naming issue #222 and R0.
SLATE = ("C1", "C2", "C3", "nC4", "nC5", "H2", "nC7", "methylcyclohexane", "toluene")

#: Light-end species, the equal-molar split of Smith's C1–C5 lump.
_LIGHT_ENDS = ("C1", "C2", "C3", "nC4", "nC5")

#: C_u = 1000/3600: lb-mol/(h·lb_cat) → mol/(kg_cat·s). lb-mol→mol is
#: ×453.59237, h→s is ÷3600, lb→kg is ÷0.45359237; the two mass factors cancel.
C_U = 1000.0 / 3600.0

#: The kinetics object's reactions and their required fields (spec params table).
_KINETIC_FIELDS: dict[str, tuple[str, ...]] = {
    "dehydro": ("k0", "Ea", "A_K", "B_K"),
    "n_to_p": ("k0", "Ea", "A_K", "B_K"),
    "hc_n": ("k0", "Ea"),
    "hc_p": ("k0", "Ea"),
}


class ReformerKineticError(ValueError):
    """Raised when the reformer_cat R1 spec is ill-posed (refusal table)."""


def validate_slate(n_in: dict[str, float]) -> None:
    """Refuse a feed species outside the real-species slate (spec refusals).

    A pseudo-component (or any other species) cannot take part in the
    element-balanced C7 chemistry: its elemental characterization is open
    (issue #222). Point the caller at R0 for the lumped-yield alternative.
    """
    outside = sorted(cid for cid, n in n_in.items() if n > 0.0 and cid not in SLATE)
    if outside:
        raise ReformerKineticError(
            f"reformer_cat R1: feed species {outside} are outside the slate {list(SLATE)}; "
            "the R1 kinetics need real species with formulas and formation data "
            "(pseudo-component elemental characterization: issue #222) — use the R0 "
            "CatalyticReformer for mass-lumped feeds"
        )


def _ea_from_b(b_deg_r: float) -> float:
    """Smith's temperature exponent, °R, to the contract's Ea, J/mol.

    Smith's rate constants use an exponent b/T_R with T in °R; T_R = 1.8·T_K,
    so b/T_R = (b/1.8)/T_K and Ea = R·b/1.8 (spec eq. 4, last bullet).
    """
    return R * b_deg_r / 1.8


def _smith_to_contract(
    k0_lb: float,
    Ea: float,
    sum_orders: float,
    p_atm: float,
) -> tuple[float, float]:
    """One Smith rate constant to the contract's mole-fraction ``PowerLaw`` body.

    ``k0_lb`` is Smith's published k0 in lb-mol/(h·lb_cat·atm^Σorders), ``Ea``
    the activation energy in J/mol (from a °R exponent through
    :func:`_ea_from_b` when transcribing the paper), ``sum_orders`` the total
    mole-fraction order of the term, ``p_atm`` the bed pressure in atm.

    Returns ``(k0_prime, Ea)`` for the ``PowerLawRate``. Factors, one each:

    - C_u = 1000/3600 converts lb-mol/(h·lb_cat) to mol/(kg_cat·s);
    - p_i = y_i·P_atm on the isobaric bed folds P_atm^Σorders into k0'
      (spec eq. 4: k0' = k0·C_u·P_atm^Σorders). For the hydrocracking rates
      r3 = k3·p_N/P and r4 = k4·p_P/P the pressure cancels (p_i/P = y_i), so
      those terms pass ``sum_orders = 0`` here and carry their mole-fraction
      order 1 directly.
    """
    k0_prime = k0_lb * C_U * p_atm**sum_orders
    return k0_prime, Ea


def kinetics_param(value: Any) -> dict[str, dict[str, float]]:
    """The ``kinetics`` parameter: the explicit constants object (spec step 2).

    ``"smith1959"`` is a preset allowed only once Smith's k_i and K_i are
    transcribed from the 1959 paper (or a reproduction that prints them) with
    page numbers in this module's docstring — not yet done, so it is refused
    with the ``preset`` fragment (spec refusal table). Anything else must be
    the explicit object ``{dehydro: {k0, Ea, A_K, B_K}, n_to_p: {...},
    hc_n: {k0, Ea}, hc_p: {k0, Ea}}``, k0 in Smith's published units
    lb-mol/(h·lb_cat·atm^Σorders), Ea in J/mol, K = exp(A_K − B_K/T[K]).
    """
    if isinstance(value, str):
        if value == "smith1959":
            raise ReformerKineticError(
                "reformer_cat R1: kinetics preset 'smith1959' is not available: Smith's k_i and "
                "K_i constants have not been transcribed from the 1959 paper with page numbers; "
                "pass the explicit kinetics object instead"
            )
        raise ReformerKineticError(
            f"reformer_cat R1: kinetics {value!r} is neither the preset 'smith1959' "
            "(not transcribed) nor an explicit object"
        )
    if not isinstance(value, dict):
        raise ReformerKineticError(
            f"reformer_cat R1: kinetics must be 'smith1959' (not transcribed) or an explicit "
            f"object, got {type(value).__name__}"
        )
    unknown = sorted(set(value) - set(_KINETIC_FIELDS))
    if unknown:
        raise ReformerKineticError(f"reformer_cat R1: kinetics has unknown reaction(s) {unknown}")
    missing = sorted(set(_KINETIC_FIELDS) - set(value))
    if missing:
        raise ReformerKineticError(f"reformer_cat R1: kinetics is missing reaction(s) {missing}")
    out: dict[str, dict[str, float]] = {}
    for rid, fields in _KINETIC_FIELDS.items():
        block = value[rid]
        if not isinstance(block, dict):
            raise ReformerKineticError(f"reformer_cat R1: kinetics.{rid} must be an object")
        block_unknown = sorted(set(block) - set(fields))
        if block_unknown:
            raise ReformerKineticError(
                f"reformer_cat R1: kinetics.{rid} has unknown field(s) {block_unknown}"
            )
        block_missing = sorted(set(fields) - set(block))
        if block_missing:
            raise ReformerKineticError(f"reformer_cat R1: kinetics.{rid} is missing field(s) {block_missing}")
        out[rid] = {f: float(block[f]) for f in fields}
    return out


def _power_law(
    rid: str,
    k0_prime: float,
    Ea: float,
    orders: dict[str, float],
    reverse: PowerLawRate | None,
) -> PowerLaw:
    """A contract ``PowerLaw`` on the mole-fraction basis, per catalyst mass."""
    return PowerLaw(
        rate_units="mol/(kg_cat·s)",
        k0=k0_prime,
        Ea=Ea,
        orders=orders,
        basis="mole_fraction",
        reverse=reverse,
    )


def build_reaction_set(kin: dict[str, dict[str, float]], p_atm: float) -> ReactionSet:
    """The ``reformer_smith_r1`` reaction set at one bed's pressure (spec eq. 2–4).

    ``kin`` is :func:`kinetics_param`'s explicit object, ``p_atm`` the isobaric
    bed pressure in atm. The bed's pressure folds into the Arrhenius k0'
    (spec eq. 4), so a set is built per bed. The contract validates every
    reaction's element balance (all species are real, ``lumped=False``).
    """
    light = {cid: 7.0 / 15.0 for cid in _LIGHT_ENDS}

    # dehydro: N ⇌ A + 3 H2; r1 = k1·(p_N − p_A·p_H³/K1).
    d = kin["dehydro"]
    # forward: p_N = y_N·P_atm → Σorders 1: k0' = k0·C_u·P_atm.
    k1_f, ea_1 = _smith_to_contract(d["k0"], d["Ea"], 1.0, p_atm)
    # reverse: k1·p_A·p_H³/K1 = (k0·C_u·e^(−A_K)·P_atm⁴)·e^(−(Ea − R·B_K)/(R·T))·y_A·y_H³
    # (spec eq. 4: k0_rev' = k0·C_u·e^(−A_K)·P_atm^4, Ea_rev = Ea − R·B_K).
    k1_r, ea_1_rev = _smith_to_contract(d["k0"] * math.exp(-d["A_K"]), d["Ea"] - R * d["B_K"], 4.0, p_atm)
    dehydro = Reaction(
        id="dehydro",
        stoichiometry={"methylcyclohexane": -1.0, "toluene": 1.0, "H2": 3.0},
        base_component="methylcyclohexane",
        provenance="Smith, Chem. Eng. Prog. 55(6) (1959) 76-80, n=7; rate form r1 = k1(p_N - p_A*p_H^3/K1) "
        "per spec specs/backend/units/reformer_cat.md eq. 2-4",
        kinetics=_power_law(
            "dehydro",
            k1_f,
            ea_1,
            {"methylcyclohexane": 1.0},
            PowerLawRate(
                rate_units="mol/(kg_cat·s)",
                k0=k1_r,
                Ea=ea_1_rev,
                basis="mole_fraction",
                orders={"toluene": 1.0, "H2": 3.0},
            ),
        ),
    )

    # n_to_p: N + H2 ⇌ P; r2 = k2·(p_N·p_H − p_P/K2).
    n = kin["n_to_p"]
    # forward: p_N·p_H → Σorders 2.
    k2_f, ea_2 = _smith_to_contract(n["k0"], n["Ea"], 2.0, p_atm)
    # reverse: p_P/K2 → Σ reverse orders 1.
    k2_r, ea_2_rev = _smith_to_contract(n["k0"] * math.exp(-n["A_K"]), n["Ea"] - R * n["B_K"], 1.0, p_atm)
    n_to_p = Reaction(
        id="n_to_p",
        stoichiometry={"methylcyclohexane": -1.0, "H2": -1.0, "nC7": 1.0},
        base_component="methylcyclohexane",
        provenance="Smith, Chem. Eng. Prog. 55(6) (1959) 76-80, n=7; rate form r2 = k2(p_N*p_H - p_P/K2) "
        "per spec specs/backend/units/reformer_cat.md eq. 2-4",
        kinetics=_power_law(
            "n_to_p",
            k2_f,
            ea_2,
            {"methylcyclohexane": 1.0, "H2": 1.0},
            PowerLawRate(
                rate_units="mol/(kg_cat·s)", k0=k2_r, Ea=ea_2_rev, basis="mole_fraction", orders={"nC7": 1.0}
            ),
        ),
    )

    # hc_n: N + (7/3) H2 → (7/15) each light end; r3 = k3·p_N/P = k3·y_N.
    # The pressure cancels, so k0' = k0·C_u (no atm power) with order 1.
    hn = kin["hc_n"]
    k3_f, ea_3 = _smith_to_contract(hn["k0"], hn["Ea"], 0.0, p_atm)
    hc_n_stoich: dict[str, float] = {"methylcyclohexane": -1.0, "H2": -7.0 / 3.0, **light}
    hc_n = Reaction(
        id="hc_n",
        stoichiometry=hc_n_stoich,
        base_component="methylcyclohexane",
        provenance="Smith, Chem. Eng. Prog. 55(6) (1959) 76-80, n=7; hydrocracking of naphthenes, "
        "r3 = k3*p_N/P, light ends equal-molar, per spec specs/backend/units/reformer_cat.md eq. 2-4",
        kinetics=_power_law("hc_n", k3_f, ea_3, {"methylcyclohexane": 1.0}, None),
    )

    # hc_p: P + (4/3) H2 → (7/15) each light end; r4 = k4·p_P/P = k4·y_P.
    hp = kin["hc_p"]
    k4_f, ea_4 = _smith_to_contract(hp["k0"], hp["Ea"], 0.0, p_atm)
    hc_p_stoich: dict[str, float] = {"nC7": -1.0, "H2": -4.0 / 3.0, **light}
    hc_p = Reaction(
        id="hc_p",
        stoichiometry=hc_p_stoich,
        base_component="nC7",
        provenance="Smith, Chem. Eng. Prog. 55(6) (1959) 76-80, n=7; hydrocracking of paraffins, "
        "r4 = k4*p_P/P, light ends equal-molar, per spec specs/backend/units/reformer_cat.md eq. 2-4",
        kinetics=_power_law("hc_p", k4_f, ea_4, {"nC7": 1.0}, None),
    )

    return ReactionSet(
        id="reformer_smith_r1",
        reactions=[dehydro, n_to_p, hc_n, hc_p],
        components=list(SLATE),
    )


# ---------------------------------------------------------------------------
# Step 2 — the adapter: bed validation, the interheater + bed loop, the
# product split, duty accounting.  Spec algorithm steps 1–6 and the refusal
# table.
# ---------------------------------------------------------------------------


def _validate_beds(beds: Any) -> list[dict[str, Any]]:
    """Validate and normalize the ``beds`` parameter (spec algorithm step 2)."""
    if not isinstance(beds, list) or not beds:
        raise ReformerKineticError(
            "reformer_cat R1: beds must be a non-empty array of bed parameter mappings"
        )
    out: list[dict[str, Any]] = []
    for i, bed in enumerate(beds):
        if not isinstance(bed, dict):
            raise ReformerKineticError(f"reformer_cat R1: bed {i} must be a mapping")
        w = bed.get("catalyst_mass_kg")
        if not isinstance(w, (int, float)) or isinstance(w, bool) or float(w) <= 0.0:
            raise ReformerKineticError(f"reformer_cat R1: bed {i} catalyst_mass_kg must be > 0")
        t_in = bed.get("inlet_T_K")
        if not isinstance(t_in, (int, float)) or isinstance(t_in, bool) or float(t_in) <= 0.0:
            raise ReformerKineticError(f"reformer_cat R1: bed {i} inlet_T_K must be > 0")
        thermal = bed.get("thermal", "isothermal")
        if thermal not in ("isothermal", "adiabatic", "uniform_duty", "heat_model"):
            raise ReformerKineticError(
                f"reformer_cat R1: bed {i} thermal must be one of "
                "'isothermal', 'adiabatic', 'uniform_duty', 'heat_model'"
            )
        out.append({"catalyst_mass_kg": float(w), "inlet_T_K": float(t_in), "thermal": thermal})
        if "duty_W" in bed:
            out[-1]["duty_W"] = float(bed["duty_W"])
    return out


#: The reformate group: everything but hydrogen leaves the reformate port
#: (spec algorithm step 5); hydrogen alone leaves the H2 port.
_REFORMATE_CIDS = frozenset(SLATE) - {"H2"}


class CatalyticReformerR1:
    """R1 adapter for the ``reformer_cat`` row (spec U-R2 wave, step 2).

    Ports: ``naphtha_in`` (StreamState), ``reformate_out`` and ``h2_out``
    (StreamState).  Adiabatic beds with interheaters between them; each
    interheater restores the next bed's ``inlet_T_K`` exactly (the heater
    duty is reported, not a parameter).  The reacting phase is vapor; the
    bed is isobaric at R1 (no Ergun pressure drop — R2).
    """

    def ports(self) -> dict[str, tuple[str, ...]]:
        return {
            "naphtha_in": ("in",),
            "reformate_out": ("out",),
            "h2_out": ("out",),
        }

    def solve(
        self,
        inputs: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        if set(inputs) != {"naphtha_in"}:
            raise ReformerKineticError(
                f"reformer_cat R1: expected exactly one input port 'naphtha_in', got {sorted(inputs)}"
            )
        inlet = inputs["naphtha_in"]

        # Algorithm step 1: the feed must be real species from the slate.
        n = {cid: float(x) * inlet.molar_flow for cid, x in inlet.composition.items() if x > 0.0}
        if not n:
            raise ReformerKineticError("reformer_cat R1: naphtha_in carries no components")
        validate_slate(n)
        # Trace seeds: the pfr integrator's z drops zero-flow species, so a
        # feed without the products (toluene, nC7, light ends) would make the
        # reverse rates' product orders raise (component outside the mixture)
        # at t = 0. Seeding every missing slate species at 1e-12 of the total
        # flow keeps the orders evaluable and sits four orders below the
        # strictest V0 tolerance (1e-8 relative).
        total_feed = math.fsum(n.values())
        for cid in SLATE:
            n.setdefault(cid, 1.0e-12 * total_feed)

        beds = _validate_beds(params.get("beds"))
        rho = params.get("bulk_density_kg_m3")
        if not isinstance(rho, (int, float)) or isinstance(rho, bool) or float(rho) <= 0.0:
            raise ReformerKineticError(
                "reformer_cat R1: bulk_density_kg_m3 must be > 0 (it converts the per-catalyst-mass rates)"
            )
        rho_f = float(rho)
        kin = kinetics_param(params.get("kinetics"))
        rset = build_reaction_set(kin, inlet.P / 101325.0)

        info: dict[str, Any] = {}
        n_state = n
        p = inlet.P
        h_prev_out: float | None = None  # formation-basis enthalpy of the previous bed's outlet
        inlet_state = inlet

        # Algorithm step 4: per bed — interheater, the pfr integration, the
        # extents, then the exact `thermal_outlet` closure (the ODE's energy
        # profile only reports the gap). The heater feeding bed k (k >= 2)
        # restores the bed's inlet_T_K from the previous bed's outlet state;
        # heater_duty_b1 is zero at R1: the feed arrives at bed 1's inlet_T_K.
        for k, bed in enumerate(beds, start=1):
            t_feed = bed["inlet_T_K"]
            heated = thermo.flash_pt(dict(z_from(n_state)), t_feed, p, math.fsum(n_state.values()))
            if h_prev_out is not None:
                info[f"heater_duty_b{k}_W"] = enthalpy_with_formation(heated) - h_prev_out
            else:
                info[f"heater_duty_b{k}_W"] = 0.0
            h_prev_out = enthalpy_with_formation(heated)
            profile: PlugFlowProfile = integrate_plug_flow(
                heated,
                rset,
                thermo,
                volume_m3=bed["catalyst_mass_kg"] / rho_f,
                energy=bed["thermal"],
                duty_W=float(bed.get("duty_W", 0.0)),
                reacting_phase="vapor",
                bulk_density_kg_m3=rho_f,
            )
            n_out = apply_extents(n_state, rset, profile.extents[-1])
            out_state, _bed_duty = thermal_outlet(heated, n_out, bed["thermal"], thermo)
            info[f"bed_dT_b{k}_K"] = out_state.T - t_feed
            info[f"bed_T_out_b{k}_K"] = out_state.T
            info[f"T_closure_gap_b{k}_K"] = out_state.T - profile.T_K[-1]
            h_prev_out = enthalpy_with_formation(out_state)
            n_state = n_out
            for j, reaction in enumerate(rset.reactions):
                info[f"extent_{reaction.id}_b{k}_mol_s"] = float(profile.extents[-1][j])

        # Algorithm step 5: the sharp product split at the last bed's outlet
        # state. The split is fictitious (both ports at the same T and P), so
        # its enthalpy of mixing is booked, not hidden: duty closes as
        # heaters + isothermal-bed duties + split_enthalpy_W.
        t_last = float(info[f"bed_T_out_b{len(beds)}_K"])
        reformate = {cid: n_state[cid] for cid in sorted(_REFORMATE_CIDS) if n_state[cid] > 0.0}
        h2_flow = n_state["H2"]
        out_reformate = thermo.flash_pt(dict(z_from(reformate)), t_last, p, math.fsum(reformate.values()))
        out_h2 = thermo.flash_pt({"H2": 1.0}, t_last, p, h2_flow)
        outlets = {"reformate_out": out_reformate, "h2_out": out_h2}
        info["split_enthalpy_W"] = math.fsum(enthalpy_with_formation(s) for s in outlets.values()) - (
            h_prev_out or 0.0
        )

        # Algorithm step 6: the duty closes on the formation-basis enthalpy
        # across the unit's own ports; power_W = 0 at R1.
        duty_W = stream_enthalpy(outlets.values(), "formation") - stream_enthalpy([inlet_state], "formation")

        # Reported yields: H2 produced per feed mass (wt %) and the C6+
        # aromatics mole fraction (toluene over the C7 lumps).
        feed_mass_kg_s = math.fsum(
            n_in * float(component_record(cid)["mw"]) for cid, n_in in n.items() if cid in n
        )
        mw_h2 = float(component_record("H2")["mw"])
        h2_produced = h2_flow - n.get("H2", 0.0)
        info["h2_yield_wt_pct"] = 100.0 * h2_produced * mw_h2 / feed_mass_kg_s
        c6plus = math.fsum(n_state[cid] for cid in ("nC7", "methylcyclohexane", "toluene"))
        info["aromatics_out_mol_frac_C6plus"] = n_state["toluene"] / c6plus if c6plus > 0.0 else 0.0

        return UnitResult(
            outlets=outlets,
            duty_W=duty_W,
            info=info,
        )
