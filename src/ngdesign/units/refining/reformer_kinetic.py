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

from ngdesign.contracts.reactions import PowerLaw, PowerLawRate, Reaction, ReactionSet
from ngdesign.units._physics.kinetics import R

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
