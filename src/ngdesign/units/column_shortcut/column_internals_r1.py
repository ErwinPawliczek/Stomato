"""Column internals hydraulics, R1: tray and packed-section rating (U-E 11).

Plugin kind ``unit``, name ``column_internals``, level R1 (spec
``specs/backend/units/column_internals.md``). The unit rates ONE column
section from that section's vapour and liquid traffic:

- **Inlet:** a two-phase :class:`StreamState` at the section's (T, P) whose
  vapour and liquid phases carry the traffic. ``V = molar_flow * vapor_fraction``
  and ``L = molar_flow * (1 - vapor_fraction)``; densities, viscosities and
  molecular weights come from the stream's ``phases`` (one VAPOR phase; one or
  more liquid phases pooled: moles add, density by mole-weighted molar
  volume, viscosity mole-weighted).
- **Outlet:** the inlet state itself, passed through unchanged, so V0 closes
  exactly with ``duty_W = power_W = 0``. All results go in ``info``.

**Tray method** (``internals="sieve_tray"``) — Seader, Henley & Roper,
*Separation Process Principles*, 3rd ed., §6.6. The Fair (1961) capacity
parameter uses the Lygeros & Magoulas (1986, Hydrocarbon Processing 65(12),
43) fit,

    C_SB = 0.0105 + 8.127e-4 * TS_mm**0.755 * exp(-1.463 * F_LV**0.842),

with ``C_SB`` in m/s and the tray spacing ``TS`` in mm. The printed form was
verified before coding: Perry, *Chemical Engineers' Handbook*, 8th ed.,
eq. 14-90 prints the same coefficients with TS in mm and C_SB in m/s (a
worked example at TS = 609 mm gives C_SB ≈ 0.10-0.11 m/s), and Souza et al.,
I&EC Res. 64(4), 2256 (2025), tabulates the same 0.0105 / 8.127e-4 / 0.755 /
1.463 / 0.842 constants for the Lygeros-Magoulas correlation.

**Packing method** (``internals="packing"``) — Stichlmair, Bravo & Fair
(1989, Gas Sep. Purif. 3, 19-28) through ``fluids.packed_tower``
(``Stichlmair_dry``, ``Stichlmair_wet``, ``Stichlmair_flood``), plus the
optional Robbins (1991, Chem. Eng. Prog. 87(5), 87) pressure drop when
``Fpd_per_ft`` is given (Fpd in 1/ft, the library's unit). HETP is not
computed; a user-supplied ``hetp_m``/``n_stages`` pair is only multiplied.

**Flooding report** (orchestrator ruling on PR #288): a rating unit reports a
flooded column rather than crashing, so every result carries
``info['flooded'] = 1.0`` when ``flood_fraction > 1`` and ``0.0`` otherwise.
(The contract's ``info`` is ``dict[str, float]``, which coerces a bool, so the
ruling's ``True``/``False`` is carried as the floats 1.0/0.0 — flagged on the
PR.) Above the flood point the irrigated (wet) Stichlmair correlation is
undefined and ``dP_wet_Pa`` is omitted, while ``dP_dry_Pa``, ``Vg_flood_m_s``
and ``flood_fraction`` (> 1) are still reported.

Every refusal is a :class:`ColumnInternalsError` (a ``ValueError`` subclass)
naming the offending parameter (U-R1 refusals rule).
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple

from fluids.packed_tower import Robbins, Stichlmair_dry, Stichlmair_flood, Stichlmair_wet

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

#: CODATA standard gravity, m/s2.
STANDARD_GRAVITY = 9.80665

#: Liquid volumetric weir-flow coefficient of the Francis weir formula
#: Q_L = 1.84 * L_w * h_ow**1.5 (SI: m3/s, m).
_FRANCIS_SI = 1.84

#: Surface-tension reference of the Fair correlation, N/m (Seader-Henley 3rd
#: ed.: F_ST = (sigma / 20 dyn/cm)**0.2).
_SIGMA_REF = 0.020


class ColumnInternalsError(ValueError):
    """Refusal for a bad column-internals specification (params or inlet phases)."""


class _Traffic(NamedTuple):
    """Mass traffic and pooled phase properties of one column section."""

    G: float  # vapour mass flow, kg/s
    L: float  # liquid mass flow, kg/s
    rho_v: float  # kg/m3
    rho_l: float  # kg/m3
    mu_v: float | None  # Pa s (packing branch only)
    mu_l: float | None  # Pa s (Robbins only)


def _number(params: dict[str, Any], key: str) -> float:
    """A required numeric param."""
    if key not in params or params[key] is None:
        raise ColumnInternalsError(f"column_internals: missing required param {key!r}")
    v = params[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ColumnInternalsError(f"column_internals: param {key!r} must be a number, got {v!r}")
    return float(v)


def _positive(params: dict[str, Any], key: str) -> float:
    """A required strictly positive numeric param."""
    v = _number(params, key)
    if v <= 0.0:
        raise ColumnInternalsError(f"column_internals: param {key!r} must be > 0, got {v}")
    return v


def _traffic(inlet: StreamState) -> _Traffic:
    """Split the inlet into mass flows and pooled phase properties."""
    vapor = [p for p in inlet.phases if p.kind is PhaseKind.VAPOR]
    liquid = [p for p in inlet.phases if p.kind is not PhaseKind.VAPOR]
    if len(vapor) != 1 or not liquid:
        raise ColumnInternalsError(
            "column_internals: inlet must be a two-phase stream (exactly one vapor phase and"
            f" at least one liquid phase), got {len(vapor)} vapor and {len(liquid)} liquid"
        )
    v_mol = inlet.molar_flow * inlet.vapor_fraction
    l_mol = inlet.molar_flow * (1.0 - inlet.vapor_fraction)
    vp = vapor[0]
    # Pool the liquid phases: moles add; density by mole-weighted molar volume;
    # viscosity mole-weighted (and only consumed by the packing branch).
    w_tot = sum(p.mole_fraction for p in liquid)
    mw_l = sum(p.mole_fraction * p.molecular_weight for p in liquid) / w_tot
    molar_volume = sum(p.mole_fraction * p.molecular_weight / p.density for p in liquid) / w_tot
    rho_l = mw_l / molar_volume
    mu_l: float | None = None
    mus: list[float] = []
    for p in liquid:
        if p.viscosity is None:
            mus = []
            break
        mus.append(p.mole_fraction * p.viscosity)
    if mus:
        mu_l = sum(mus) / w_tot
    return _Traffic(
        G=v_mol * vp.molecular_weight / 1000.0,
        L=l_mol * mw_l / 1000.0,
        rho_v=vp.density,
        rho_l=rho_l,
        mu_v=vp.viscosity,
        mu_l=mu_l,
    )


def _solve_tray(traffic: _Traffic, params: dict[str, Any]) -> dict[str, float]:
    """Sieve-tray flooding and pressure drop (Seader-Henley-Roper 3rd ed. §6.6)."""
    sigma = _positive(params, "surface_tension_N_m")
    tray_spacing = _positive(params, "tray_spacing_m")
    ad_at = _number(params, "downcomer_area_frac")
    if not 0.0 < ad_at < 0.5:
        raise ColumnInternalsError(f"column_internals: downcomer_area_frac must be in (0, 0.5), got {ad_at}")
    ah_aa = _number(params, "hole_area_frac")
    if ah_aa < 0.06 or ah_aa > 0.20:
        raise ColumnInternalsError(f"column_internals: hole_area_frac must be in [0.06, 0.20], got {ah_aa}")
    weir_height = _positive(params, "weir_height_m")
    weir_length = _positive(params, "weir_length_m")
    c_o = _positive(params, "orifice_coefficient")
    beta = _number(params, "aeration_factor")
    if not 0.0 < beta <= 1.0:
        raise ColumnInternalsError(f"column_internals: aeration_factor must be in (0, 1], got {beta}")
    foaming = 1.0
    if params.get("foaming_factor") is not None:
        foaming = _positive(params, "foaming_factor")

    give_diameter = params.get("diameter_m") is not None
    give_fraction = params.get("design_flood_fraction") is not None
    if give_diameter == give_fraction:
        raise ColumnInternalsError(
            "column_internals: give exactly one of diameter_m (rating) or"
            f" design_flood_fraction (design), got {'both' if give_diameter else 'neither'}"
        )

    rho_v, rho_l, big_g, liquid = traffic.rho_v, traffic.rho_l, traffic.G, traffic.L

    # 1-2. Fair capacity parameter via the Lygeros-Magoulas fit (TS in mm).
    f_lv = (liquid / big_g) * math.sqrt(rho_v / rho_l)
    c_sb = 0.0105 + 8.127e-4 * (tray_spacing * 1000.0) ** 0.755 * math.exp(-1.463 * f_lv**0.842)
    # 3. Corrections.
    f_st = (sigma / _SIGMA_REF) ** 0.2
    c = f_st * foaming * c_sb
    # 4. Flooding velocity on the net area.
    u_flood = c * math.sqrt((rho_l - rho_v) / rho_v)

    # 5-6. Rating at a given diameter, or design to a flood fraction.
    if give_diameter:
        diameter = _positive(params, "diameter_m")
    else:
        fraction = _number(params, "design_flood_fraction")
        if not 0.0 < fraction < 1.0:
            raise ColumnInternalsError(
                f"column_internals: design_flood_fraction must be in (0, 1), got {fraction}"
            )
        diameter = math.sqrt(4.0 * big_g / (fraction * u_flood * math.pi * (1.0 - ad_at) * rho_v))

    a_total = math.pi * diameter**2 / 4.0
    a_net = a_total * (1.0 - ad_at)
    a_active = a_total * (1.0 - 2.0 * ad_at)
    a_hole = ah_aa * a_active
    u_net = (big_g / rho_v) / a_net
    flood_fraction = u_net / u_flood
    u_hole = (big_g / rho_v) / a_hole
    # 7. Dry-tray head, orifice equation (SI form: no stray 0.186).
    h_dry = (rho_v / rho_l) * u_hole**2 / (2.0 * STANDARD_GRAVITY * c_o**2)
    # 8. Francis weir crest.
    q_l = liquid / rho_l
    h_ow = (q_l / (_FRANCIS_SI * weir_length)) ** (2.0 / 3.0)
    # 9. Aerated liquid head.
    h_liquid = beta * (weir_height + h_ow)
    # 10. Tray pressure drop.
    d_p_tray = rho_l * STANDARD_GRAVITY * (h_dry + h_liquid)
    return {
        "F_LV": f_lv,
        "C_SB_m_s": c_sb,
        "C_m_s": c,
        "U_flood_m_s": u_flood,
        "U_net_m_s": u_net,
        "flood_fraction": flood_fraction,
        "flooded": float(flood_fraction > 1.0),
        "diameter_m": diameter,
        "A_total_m2": a_total,
        "A_net_m2": a_net,
        "A_active_m2": a_active,
        "A_hole_m2": a_hole,
        "u_hole_m_s": u_hole,
        "h_dry_m": h_dry,
        "h_ow_m": h_ow,
        "h_liquid_m": h_liquid,
        "dP_tray_Pa": d_p_tray,
    }


def _solve_packing(traffic: _Traffic, params: dict[str, Any]) -> dict[str, float]:
    """Packed-section Stichlmair dry/wet/flood rating, plus optional Robbins."""
    diameter = _positive(params, "column_diameter_m")
    height = _positive(params, "packed_height_m")
    voidage = _number(params, "voidage")
    if not 0.0 < voidage < 1.0:
        raise ColumnInternalsError(f"column_internals: voidage must be in (0, 1), got {voidage}")
    specific_area = _positive(params, "specific_area_m2_m3")
    c1 = _positive(params, "stichlmair_C1")
    c2 = _positive(params, "stichlmair_C2")
    c3 = _positive(params, "stichlmair_C3")

    fpd: float | None = None
    if params.get("Fpd_per_ft") is not None:
        fpd = _positive(params, "Fpd_per_ft")

    has_hetp = params.get("hetp_m") is not None
    has_stages = params.get("n_stages") is not None
    if has_hetp != has_stages:
        raise ColumnInternalsError("column_internals: give both of hetp_m and n_stages, or neither")

    if traffic.mu_v is None:
        raise ColumnInternalsError(
            "column_internals: packing rating needs the vapour viscosity; the inlet vapour"
            " phase carries viscosity=None"
        )
    if fpd is not None and traffic.mu_l is None:
        raise ColumnInternalsError(
            "column_internals: Robbins dP needs the liquid viscosity; the inlet liquid"
            " phase carries viscosity=None"
        )

    rho_v, rho_l, big_g, liquid = traffic.rho_v, traffic.rho_l, traffic.G, traffic.L
    a_total = math.pi * diameter**2 / 4.0
    vg = (big_g / rho_v) / a_total
    vl = (liquid / rho_l) / a_total

    try:
        vg_flood = Stichlmair_flood(
            vl, rho_v, rho_l, float(traffic.mu_v), voidage, specific_area, c1, c2, c3, height
        )
    except Exception as exc:  # noqa: BLE001 - any library failure is a refusal (spec step 3)
        raise ColumnInternalsError(
            f"column_internals: the Stichlmair flood solve failed for Vl={vl} m/s,"
            f" rhoV={rho_v} kg/m3, rhoL={rho_l} kg/m3, muV={traffic.mu_v} Pa s,"
            f" voidage={voidage}, specific_area={specific_area} m2/m3,"
            f" C1={c1}, C2={c2}, C3={c3}, H={height} m: {exc}"
        ) from exc
    try:
        d_p_dry = Stichlmair_dry(vg, rho_v, float(traffic.mu_v), voidage, specific_area, c1, c2, c3, height)
    except Exception as exc:  # noqa: BLE001
        raise ColumnInternalsError(
            f"column_internals: the Stichlmair dry dP solve failed for Vg={vg} m/s,"
            f" rhoV={rho_v} kg/m3, muV={traffic.mu_v} Pa s, voidage={voidage},"
            f" specific_area={specific_area} m2/m3, C1={c1}, C2={c2}, C3={c3},"
            f" H={height} m: {exc}"
        ) from exc
    # Above the flood point the irrigated correlation is undefined and the
    # library's wet solve does not converge; the dry dP, the flood velocity and
    # the flood fraction (which flags the condition, > 1) are still reported,
    # and the flooded state is reported explicitly as info['flooded'] (the
    # orchestrator's ruling on PR #288) instead of an absent key.
    d_p_wet: float | None = None
    if vg <= vg_flood:
        try:
            d_p_wet = Stichlmair_wet(
                vg,
                vl,
                rho_v,
                rho_l,
                float(traffic.mu_v),
                voidage,
                specific_area,
                c1,
                c2,
                c3,
                height,
            )
        except Exception as exc:  # noqa: BLE001
            raise ColumnInternalsError(
                f"column_internals: the Stichlmair wet dP solve failed for Vg={vg} m/s,"
                f" Vl={vl} m/s, rhoV={rho_v} kg/m3, rhoL={rho_l} kg/m3, muV={traffic.mu_v} Pa s,"
                f" voidage={voidage}, specific_area={specific_area} m2/m3,"
                f" C1={c1}, C2={c2}, C3={c3}, H={height} m: {exc}"
            ) from exc

    info = {
        "Vg_m_s": vg,
        "Vl_m_s": vl,
        "Vg_flood_m_s": vg_flood,
        "flood_fraction": vg / vg_flood,
        "flooded": float(vg / vg_flood > 1.0),
        "dP_dry_Pa": d_p_dry,
    }
    if d_p_wet is not None:
        info["dP_wet_Pa"] = d_p_wet
    if fpd is not None:
        assert traffic.mu_l is not None  # refused above when None
        # Robbins L, G are mass fluxes, kg/s/m2; Fpd is in 1/ft (the library's unit).
        info["dP_robbins_Pa"] = Robbins(
            liquid / a_total, big_g / a_total, rho_l, rho_v, traffic.mu_l, height, fpd
        )
    if has_hetp:
        hetp = _positive(params, "hetp_m")
        stages = _number(params, "n_stages")
        if stages <= 0.0 or stages != int(stages):
            raise ColumnInternalsError(f"column_internals: n_stages must be a positive integer, got {stages}")
        info["packed_height_from_hetp_m"] = stages * hetp
    return info


class ColumnInternalsR1:
    """Column internals hydraulics, R1: tray or packing rating, pass-through outlet."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets.get("inlet")
        if inlet is None:
            raise ColumnInternalsError("column_internals: missing the 'inlet' stream")
        internals = params.get("internals")
        if internals not in ("sieve_tray", "packing"):
            raise ColumnInternalsError(
                f"column_internals: internals must be 'sieve_tray' or 'packing', got {internals!r}"
            )
        traffic = _traffic(inlet)
        if internals == "sieve_tray":
            info = _solve_tray(traffic, params)
        else:
            info = _solve_packing(traffic, params)
        # Pass-through: the same state object leaves, so V0 closes exactly.
        return UnitResult(outlets={"outlet": inlet}, duty_W=0.0, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Sieve-tray rating of one section at the closed-form test's traffic.

        Feed: 110 mol/s of a C1/nC4 mixture flashed two-phase at 250 K,
        1.0 MPa (the closest `pr`-flashable stand-in for the hand-built
        two-phase StreamState of ``test_column_internals_r1.py``; the unit is
        a pass-through, so V0 closes on any two-phase inlet). Tray params are
        the closed-form case's: 1.5 m diameter, 0.6096 m spacing.
        """
        feeds: dict[str, dict[str, Any]] = {
            "inlet": {
                "T": 250.0,
                "P": 1.0e6,
                "molar_flow": 110.0,
                "composition": {"C1": 0.5, "nC4": 0.5},
            }
        }
        params: dict[str, Any] = {
            "internals": "sieve_tray",
            "surface_tension_N_m": 0.015,
            "tray_spacing_m": 0.6096,
            "diameter_m": 1.5,
            "downcomer_area_frac": 0.12,
            "hole_area_frac": 0.10,
            "weir_height_m": 0.05,
            "weir_length_m": 1.1,
            "orifice_coefficient": 0.73,
            "aeration_factor": 0.6,
        }
        return feeds, params
