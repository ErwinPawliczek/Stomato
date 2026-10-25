"""Adsorption bed, R1: extended-Langmuir loading and LUB breakthrough.

Plugin kind "unit", name "adsorption_bed", level R1 — registered from the
catalogue YAML; no decorator (round-1 conventions). Spec:
``specs/backend/units/adsorption_bed.md``.

R1 keeps R0's outlets and duty unchanged (R1 changes no stream, only the
cycle physics) and replaces R0's ``capacity_kg_per_kg`` cycle-time report
with an equilibrium-loading calculation:

1. **A1 Extended Langmuir** (Langmuir 1918; Markham & Benton 1931 for the
   extended form), for each adsorbate ``i`` in ``langmuir`` with saturation
   capacity ``q_m,i`` (mol/kg) and affinity ``b_i`` (1/Pa)::

       q_i* = q_m,i * b_i * p_i / (1 + sum_j b_j * p_j),   p_i = y_i * P_feed

   with ``y_i`` from the **feed** composition (review checklist). For a
   single adsorbate this reduces to ``q* = q_m b p / (1 + b p)``.

2. **A2 Temperature dependence** (optional; van 't Hoff form, Ruthven 1984
   Ch. 2)::

       b_i(T) = b_i,ref * exp((-dH_ads,i / R) * (1/T - 1/T_ref)),  R = 8.314462618

   with ``dH_ads < 0`` (exothermic). Applied only when both ``dH_ads_J_mol``
   and ``T_ref_K`` are given; otherwise ``b`` is taken as given.

3. **A3 Bed mass**: the ``bed_mass_kg`` param, or the packed-geometry form
   ``rho_b * (pi/4) * D^2 * L``. Exactly one form.

4. **A4 Stoichiometric time** for adsorbate ``i``::

       t_s,i = q_i* * m_bed / N_dot_i

   with ``N_dot_i`` the adsorbed molar rate (the ``removal_fraction`` times
   the feed molar flow of ``i``), as in R0.

5. **A5 LUB breakthrough** (Collins 1967, as in McCabe-Smith-Harriott 7th
   ed. Ch. 25 and Geankoplis 4th ed. §12.3)::

       t_b,i = t_s,i * (1 - LUB / L)

   Without a bed length ``L`` (bed given by mass) ``LUB`` must be 0 or
   absent, so ``t_b = t_s``.

6. **A6 Cycle time** = ``min_i t_b,i`` over the adsorbates with a positive
   adsorbed rate: the first breakthrough limits the cycle.

7. **A7** loadings are reported in mass units as well: ``q_i* * MW_i / 1000``
   in kg/kg.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import stream_molar_mass
from ngdesign.units.separation.adsorption_bed import AdsorptionBed

#: CODATA gas constant, J/(mol K) (spec A2).
R_GAS = 8.314462618

#: Params keys that are R1-only: stripped from the params handed to R0.
_R1_KEYS = (
    "langmuir",
    "bed_density_kg_m3",
    "bed_diameter_m",
    "bed_length_m",
    "lub_m",
    "dH_ads_J_mol",
    "T_ref_K",
)


class AdsorptionBedR1SpecError(ValueError):
    """The adsorption-bed R1 spec is bad; the message names the parameter."""


def affinity_at_temperature(
    b_ref: float,
    dH_ads_J_mol: float,
    T_K: float,
    T_ref_K: float,
) -> float:
    """A2: the Langmuir affinity at T, ``b(T) = b_ref*exp((-dH/R)(1/T - 1/T_ref))``.

    ``dH_ads_J_mol`` is negative (exothermic adsorption), so the affinity
    falls with rising temperature. Spec A2 (Ruthven 1984, Ch. 2).
    """
    if T_K <= 0.0 or T_ref_K <= 0.0:
        raise AdsorptionBedR1SpecError(
            f"T_ref_K {T_ref_K} and the feed temperature {T_K} must be positive absolute temperatures"
        )
    return b_ref * math.exp((-dH_ads_J_mol / R_GAS) * (1.0 / T_K - 1.0 / T_ref_K))


def equilibrium_loadings(
    q_max_mol_kg: dict[str, float],
    b_1_Pa: dict[str, float],
    partial_pressures_Pa: dict[str, float],
) -> dict[str, float]:
    """A1: extended-Langmuir equilibrium loadings, mol/kg.

    ``q_i* = q_m,i * b_i * p_i / (1 + sum_j b_j * p_j)`` over the adsorbates
    ``j`` (Langmuir 1918; Markham & Benton 1931 for the extended form). With
    one adsorbate this is the plain Langmuir isotherm. Keys of the three
    maps must agree.
    """
    if set(q_max_mol_kg) != set(b_1_Pa) or set(q_max_mol_kg) != set(partial_pressures_Pa):
        raise AdsorptionBedR1SpecError(
            "langmuir keys and feed partial pressures must cover the same adsorbate ids"
        )
    denom = 1.0 + sum(b_1_Pa[cid] * partial_pressures_Pa[cid] for cid in q_max_mol_kg)
    return {cid: q_max_mol_kg[cid] * b_1_Pa[cid] * partial_pressures_Pa[cid] / denom for cid in q_max_mol_kg}


def packed_bed_mass(
    bed_density_kg_m3: float,
    bed_diameter_m: float,
    bed_length_m: float,
) -> float:
    """A3 geometry form: ``rho_b*(pi/4)*D^2*L``, kg."""
    return bed_density_kg_m3 * math.pi / 4.0 * bed_diameter_m**2 * bed_length_m


def stoichiometric_time(
    q_star_mol_kg: float,
    bed_mass_kg: float,
    n_dot_adsorbed_mol_s: float,
) -> float:
    """A4: ``t_s = q* * m_bed / N_dot`` with N_dot the adsorbed molar rate, s."""
    return q_star_mol_kg * bed_mass_kg / n_dot_adsorbed_mol_s


def breakthrough_time(
    t_stoich_s: float,
    lub_m: float,
    bed_length_m: float | None,
) -> float:
    """A5: ``t_b = t_s*(1 - LUB/L)``; without L (or LUB = 0) ``t_b = t_s``, s."""
    if bed_length_m is None or lub_m == 0.0:
        return t_stoich_s
    return t_stoich_s * (1.0 - lub_m / bed_length_m)


class AdsorptionBedR1:
    """Fixed bed rated by extended-Langmuir loading and LUB breakthrough (R1).

    R0's outlets and duty, unchanged; R1 replaces the cycle-time report.
    """

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("product_out", "regen_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        feed = inlets["feed_in"]

        # --- R1 validation (before the R0 solve, so every refusal is typed) ---
        if params.get("capacity_kg_per_kg") is not None:
            raise AdsorptionBedR1SpecError(
                "capacity_kg_per_kg is not a valid R1 parameter: R1 computes the "
                "loading from langmuir; drop it"
            )
        langmuir = params.get("langmuir")
        if not isinstance(langmuir, dict) or not langmuir:
            raise AdsorptionBedR1SpecError(
                "langmuir is required: a non-empty map of adsorbate id to {q_max_mol_kg, b_1_Pa}"
            )
        removal = params.get("removal_fraction")
        if not isinstance(removal, dict) or not removal:
            raise AdsorptionBedR1SpecError(
                "removal_fraction is required: a non-empty map of component id to removed fraction"
            )
        stray = [cid for cid in langmuir if cid not in removal]
        if stray:
            raise AdsorptionBedR1SpecError(f"langmuir names component(s) {stray} not in removal_fraction")
        unadsorbed = [cid for cid, x in removal.items() if float(x) > 0.0 and cid not in langmuir]
        if unadsorbed:
            raise AdsorptionBedR1SpecError(
                f"langmuir is missing component(s) {unadsorbed} with positive removal_fraction"
            )
        q_max: dict[str, float] = {}
        b_ref: dict[str, float] = {}
        for cid, entry in langmuir.items():
            if not isinstance(entry, dict) or "q_max_mol_kg" not in entry or "b_1_Pa" not in entry:
                raise AdsorptionBedR1SpecError(f"langmuir[{cid!r}] needs q_max_mol_kg and b_1_Pa")
            q_m = float(entry["q_max_mol_kg"])
            b = float(entry["b_1_Pa"])
            if q_m <= 0.0:
                raise AdsorptionBedR1SpecError(f"langmuir[{cid!r}] q_max_mol_kg {q_m} must be > 0")
            if b <= 0.0:
                raise AdsorptionBedR1SpecError(f"langmuir[{cid!r}] b_1_Pa {b} must be > 0")
            q_max[cid] = q_m
            b_ref[cid] = b

        bed_mass = params.get("bed_mass_kg")
        geom: dict[str, float] = {}
        for key in ("bed_density_kg_m3", "bed_diameter_m", "bed_length_m"):
            value = params.get(key)
            if value is not None:
                geom[key] = float(value)
        if bed_mass is not None and geom:
            raise AdsorptionBedR1SpecError(
                "bed_mass_kg and the geometry form (bed_density_kg_m3, bed_diameter_m, "
                "bed_length_m) are mutually exclusive: give exactly one"
            )
        bed_length_m: float | None = None
        if bed_mass is None:
            if len(geom) != 3:
                missing = [
                    key for key in ("bed_density_kg_m3", "bed_diameter_m", "bed_length_m") if key not in geom
                ]
                raise AdsorptionBedR1SpecError(
                    "bed_mass_kg is required: give bed_mass_kg, or all of "
                    f"bed_density_kg_m3, bed_diameter_m, bed_length_m (missing: {missing})"
                )
            rho_b = geom["bed_density_kg_m3"]
            D = geom["bed_diameter_m"]
            L = geom["bed_length_m"]
            if min(rho_b, D, L) <= 0.0:
                raise AdsorptionBedR1SpecError(
                    f"bed_density_kg_m3 {rho_b}, bed_diameter_m {D} and bed_length_m {L} must be > 0"
                )
            bed_mass = packed_bed_mass(rho_b, D, L)
            bed_length_m = L
        elif float(bed_mass) <= 0.0:
            raise AdsorptionBedR1SpecError(f"bed_mass_kg {bed_mass} must be > 0")

        lub_m = float(params.get("lub_m", 0.0))
        if lub_m < 0.0:
            raise AdsorptionBedR1SpecError(f"lub_m {lub_m} must be >= 0")
        if lub_m > 0.0:
            if bed_length_m is None:
                raise AdsorptionBedR1SpecError(
                    "lub_m > 0 needs bed_length_m (a LUB is meaningless without a bed length)"
                )
            if lub_m >= bed_length_m:
                raise AdsorptionBedR1SpecError(f"lub_m {lub_m} must be < bed_length_m {bed_length_m}")

        dH_ads = params.get("dH_ads_J_mol")
        T_ref = params.get("T_ref_K")
        if (dH_ads is None) != (T_ref is None):
            raise AdsorptionBedR1SpecError(
                "dH_ads_J_mol and T_ref_K must be given together (the b values' reference temperature)"
            )
        if T_ref is not None and float(T_ref) <= 0.0:
            raise AdsorptionBedR1SpecError(f"T_ref_K {T_ref} must be > 0")

        # --- R0 solve: the outlets and duty are R0's, unchanged ---
        r0_params = {key: value for key, value in params.items() if key not in _R1_KEYS}
        r0 = AdsorptionBed().solve(inlets, r0_params, thermo)

        # --- A1-A6 at the feed T and P ---
        b_eff = dict(b_ref)
        if dH_ads is not None and T_ref is not None:
            dH_map = dH_ads if isinstance(dH_ads, dict) else {}
            missing_dH = [cid for cid in b_ref if cid not in dH_map]
            if missing_dH:
                raise AdsorptionBedR1SpecError(
                    f"dH_ads_J_mol is missing adsorbate(s) {missing_dH} present in langmuir"
                )
            b_eff = {
                cid: affinity_at_temperature(b_ref[cid], float(dH_map[cid]), feed.T, float(T_ref))
                for cid in b_ref
            }

        partial_P = {cid: feed.composition[cid] * feed.P for cid in b_ref}
        q_star = equilibrium_loadings(q_max, b_eff, partial_P)

        sorted_cids = sorted(b_ref)
        t_stoich: dict[str, float] = {}
        t_break: dict[str, float] = {}
        for cid in sorted_cids:
            n_dot = float(removal[cid]) * feed.composition[cid] * feed.molar_flow
            if n_dot <= 0.0:
                continue
            t_s = stoichiometric_time(q_star[cid], float(bed_mass), n_dot)
            t_stoich[cid] = t_s
            t_break[cid] = breakthrough_time(t_s, lub_m, bed_length_m)

        cycle_time = min(t_break.values()) if t_break else 0.0
        limiting: str | None = min(t_break, key=lambda cid: t_break[cid]) if t_break else None
        limiting_index = sorted_cids.index(limiting) if limiting is not None else -1

        info = dict(r0.info)
        info["cycle_time_s"] = cycle_time
        info["bed_mass_kg"] = float(bed_mass)
        info["limiting_component_index"] = float(limiting_index)
        for cid in sorted_cids:
            mw_cid = stream_molar_mass({cid: 1.0})  # g/mol, component database
            info[f"q_eq_mol_kg_{cid}"] = q_star[cid]
            info[f"q_eq_kg_kg_{cid}"] = q_star[cid] * mw_cid / 1000.0
            if cid in t_stoich:
                info[f"t_stoich_s_{cid}"] = t_stoich[cid]
                info[f"t_break_s_{cid}"] = t_break[cid]

        return UnitResult(
            outlets=r0.outlets,
            duty_W=r0.duty_W,
            power_W=r0.power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Molecular-sieve dehydration of the slice wet gas, R0's split spec.

        R0's example feed (95 % H2O removal) with Langmuir parameters for the
        13X mol-sieve water isotherm order of magnitude: q_max 12 mol/kg,
        b 5e-3 1/Pa at the feed T; 500 kg bed. Illustrative values, not data.
        """
        from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

        feed = {
            "T": 322.15,
            "P": 7.0e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": dict(INLET_COMPOSITION),
        }
        return {"feed_in": feed}, {
            "removal_fraction": {"H2O": 0.95},
            "langmuir": {"H2O": {"q_max_mol_kg": 12.0, "b_1_Pa": 5e-3}},
            "bed_mass_kg": 500.0,
        }
