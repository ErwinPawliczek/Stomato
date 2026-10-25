"""Double-pipe (hairpin) exchanger, R1 rating level (spec U-R2, issue #266).

Counter-current single-phase rating on the shared
:mod:`ngdesign.units.heat.rating` core: Gnielinski film coefficients in the
inner pipe and the annulus (hydraulic diameter; the Gnielinski 2009 annulus
correction is deliberately omitted), an overall U referenced to the inner
tube's outside area, a pressure drop per side from INLET-state properties
(Darcy-Weisbach, no deltaP-property loop), and the duty from a brentq solve
of the counterflow epsilon-NTU residual on enthalpies.

The geometry comes from the R1 params (spec Params table); ``model``/``mode``
are ignored - the dispatcher resolves the level and passes params through.
Two-phase service is refused with ``SinglePhaseRequired`` naming the side.
``duty_W`` follows the R0 convention (the round-off enthalpy residual of an
internal exchanger); the transferred heat is reported in ``info["duty_W"]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units.heat.rating import (
    DuctResult,
    FilmProps,
    PropertyUnavailable,
    RatingError,
    SinglePhaseRequired,
    darcy_dP,
    duct_h,
    film_props,
    inlet_kind,
    rate_two_stream,
    u_outside_tube,
)


class DoublePipeGeometryError(ValueError):
    """R1 geometry params are missing, non-positive or mis-ordered; the param is named."""


def eps_counterflow(NTU: float, Cr: float) -> float:
    """Counter-current effectiveness (Incropera eqs. 11.29a/b).

    ``[1 - exp(-NTU(1-Cr))] / [1 - Cr*exp(-NTU(1-Cr))]``, or ``NTU/(1 + NTU)``
    at Cr = 1.
    """
    if Cr >= 1.0 - 1e-12:
        return NTU / (1.0 + NTU)
    ex = math.exp(-NTU * (1.0 - Cr))
    return (1.0 - ex) / (1.0 - Cr * ex)


@dataclass(frozen=True)
class _Geometry:
    """Validated R1 geometry params (spec Params table, defaults applied)."""

    inner_ID_m: float
    inner_OD_m: float
    outer_ID_m: float
    length_m: float
    inner_side: str
    k_wall_W_mK: float
    R_f_inner_m2K_W: float
    R_f_outer_m2K_W: float
    roughness_m: float


def _geometry(params: dict[str, Any]) -> _Geometry:
    """Validate the params against the refusal table; every message names the param."""
    values: dict[str, Any] = {
        "inner_ID_m": params.get("inner_ID_m"),
        "inner_OD_m": params.get("inner_OD_m"),
        "outer_ID_m": params.get("outer_ID_m"),
        "length_m": params.get("length_m"),
        "inner_side": params.get("inner_side"),
        "k_wall_W_mK": params.get("k_wall_W_mK", 45.0),
        "R_f_inner_m2K_W": params.get("R_f_inner_m2K_W", 0.0),
        "R_f_outer_m2K_W": params.get("R_f_outer_m2K_W", 0.0),
        "roughness_m": params.get("roughness_m", 4.5e-5),
    }
    for name in ("inner_ID_m", "inner_OD_m", "outer_ID_m", "length_m", "k_wall_W_mK"):
        value = values[name]
        if value is None:
            raise DoublePipeGeometryError(f"double_pipe R1 requires geometry param {name!r}")
        if float(value) <= 0.0:
            raise DoublePipeGeometryError(f"double_pipe R1: {name} must be > 0, got {value}")
    for name in ("R_f_inner_m2K_W", "R_f_outer_m2K_W", "roughness_m"):
        if float(values[name]) < 0.0:
            raise DoublePipeGeometryError(f"double_pipe R1: {name} must be >= 0, got {values[name]}")
    if values["inner_side"] not in ("hot", "cold"):
        raise DoublePipeGeometryError(
            f"double_pipe R1: inner_side must be 'hot' or 'cold', got {values['inner_side']!r}"
        )
    if float(values["inner_OD_m"]) <= float(values["inner_ID_m"]):
        raise DoublePipeGeometryError(
            "double_pipe R1: inner_OD_m must exceed inner_ID_m "
            f"(got inner_ID_m {values['inner_ID_m']} >= inner_OD_m {values['inner_OD_m']})"
        )
    if float(values["outer_ID_m"]) <= float(values["inner_OD_m"]):
        raise DoublePipeGeometryError(
            "double_pipe R1: outer_ID_m must exceed inner_OD_m "
            f"(got inner_OD_m {values['inner_OD_m']} >= outer_ID_m {values['outer_ID_m']})"
        )
    return _Geometry(
        inner_ID_m=float(values["inner_ID_m"]),
        inner_OD_m=float(values["inner_OD_m"]),
        outer_ID_m=float(values["outer_ID_m"]),
        length_m=float(values["length_m"]),
        inner_side=str(values["inner_side"]),
        k_wall_W_mK=float(values["k_wall_W_mK"]),
        R_f_inner_m2K_W=float(values["R_f_inner_m2K_W"]),
        R_f_outer_m2K_W=float(values["R_f_outer_m2K_W"]),
        roughness_m=float(values["roughness_m"]),
    )


def _side_kind(state: StreamState, side: str) -> PhaseKind:
    """``inlet_kind`` with the side named in the refusal."""
    try:
        return inlet_kind(state)
    except SinglePhaseRequired as exc:
        raise SinglePhaseRequired(f"{exc} ({side} inlet)") from exc


def _side_film(
    thermo: Thermo, z: dict[str, float], T: float, P: float, kind: PhaseKind, side: str
) -> FilmProps:
    """``film_props`` with the side named in a property refusal."""
    try:
        return film_props(thermo, z, T, P, kind)
    except PropertyUnavailable as exc:
        raise PropertyUnavailable(f"{exc} ({side} side)") from exc


class DoublePipeR1:
    """Double-pipe (hairpin) exchanger, R1: single-phase rating level."""

    inlet_ports = ("hot_in", "cold_in")
    outlet_ports = ("hot_out", "cold_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 syngas trim-cooler feeds plus a rating geometry.

        The spec's 1-inch / 60 m geometry (inner_ID 0.0266 m) refuses on
        these feeds: 100 mol/s of N2 gas runs ~750 m/s in a 1-inch pipe, a
        ~60 MPa drop on a 1 MPa feed - the refusal table's non-positive
        outlet pressure. The example therefore uses standard Sch 40
        hairpin pipe (4-inch inner in a 6-inch shell), hydraulically
        feasible for the same duty and documented in the test file.
        """
        hot = {"T": 500.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"N2": 1.0}}
        cold = {"T": 320.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"N2": 1.0}}
        params: dict[str, Any] = {
            "inner_ID_m": 0.10226,
            "inner_OD_m": 0.1143,
            "outer_ID_m": 0.15405,
            "length_m": 60.0,
            "inner_side": "hot",
        }
        return {"hot_in": hot, "cold_in": cold}, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the exchanger at the R1 level; see the module docstring."""
        geom = _geometry(params)
        hot, cold = inlets["hot_in"], inlets["cold_in"]
        for side, state in (("hot", hot), ("cold", cold)):
            if state.mass_flow <= 0.0:
                raise RatingError(
                    f"R1 rating needs both streams flowing: {side} side has zero flow"
                )
        kind_h = _side_kind(hot, "hot")
        kind_c = _side_kind(cold, "cold")
        inner_hot = geom.inner_side == "hot"

        # Duct geometry per side (Eq. 2): inner pipe and annulus, hydraulic
        # diameter on the annulus (no Gnielinski 2009 annulus correction).
        a_inner = math.pi * geom.inner_ID_m**2 / 4.0
        dh_inner = geom.inner_ID_m
        a_annulus = math.pi * (geom.outer_ID_m**2 - geom.inner_OD_m**2) / 4.0
        dh_annulus = geom.outer_ID_m - geom.inner_OD_m

        # Pressure drop per side from INLET-state properties (Eq. 7), before
        # the solve; no deltaP-property loop.
        film_h = _side_film(thermo, hot.composition, hot.T, hot.P, kind_h, "hot")
        film_c = _side_film(thermo, cold.composition, cold.T, cold.P, kind_c, "cold")
        if inner_hot:
            d_inner = duct_h(hot.mass_flow, a_inner, dh_inner, film_h, geom.roughness_m)
            d_ann = duct_h(cold.mass_flow, a_annulus, dh_annulus, film_c, geom.roughness_m)
            dp_inner = darcy_dP(d_inner.fd, geom.length_m, dh_inner, film_h.rho_kg_m3, d_inner.v_m_s)
            dp_annulus = darcy_dP(d_ann.fd, geom.length_m, dh_annulus, film_c.rho_kg_m3, d_ann.v_m_s)
        else:
            d_inner = duct_h(cold.mass_flow, a_inner, dh_inner, film_c, geom.roughness_m)
            d_ann = duct_h(hot.mass_flow, a_annulus, dh_annulus, film_h, geom.roughness_m)
            dp_inner = darcy_dP(d_inner.fd, geom.length_m, dh_inner, film_c.rho_kg_m3, d_inner.v_m_s)
            dp_annulus = darcy_dP(d_ann.fd, geom.length_m, dh_annulus, film_h.rho_kg_m3, d_ann.v_m_s)
        dp_h, dp_c = (dp_inner, dp_annulus) if inner_hot else (dp_annulus, dp_inner)
        P_h_out, P_c_out = hot.P - dp_h, cold.P - dp_c
        for side, p_out, drop in (("hot", P_h_out, dp_h), ("cold", P_c_out, dp_c)):
            if p_out <= 0.0:
                raise RatingError(
                    f"non-positive outlet pressure: {side} side drops to {p_out} Pa "
                    f"({drop} Pa across this geometry)"
                )

        # UA at the bulk-mean film state of each side (Eq. 1), re-evaluated at
        # every g(Q) step; the last evaluation is the reported rating.
        last: dict[str, DuctResult] = {}

        def ua_of(hot_out: StreamState, cold_out: StreamState) -> float:
            film_hm = _side_film(
                thermo, hot.composition, (hot.T + hot_out.T) / 2.0, (hot.P + P_h_out) / 2.0, kind_h, "hot"
            )
            film_cm = _side_film(
                thermo, cold.composition, (cold.T + cold_out.T) / 2.0, (cold.P + P_c_out) / 2.0, kind_c, "cold"
            )
            if inner_hot:
                d_i = duct_h(hot.mass_flow, a_inner, dh_inner, film_hm, geom.roughness_m)
                d_a = duct_h(cold.mass_flow, a_annulus, dh_annulus, film_cm, geom.roughness_m)
            else:
                d_i = duct_h(cold.mass_flow, a_inner, dh_inner, film_cm, geom.roughness_m)
                d_a = duct_h(hot.mass_flow, a_annulus, dh_annulus, film_hm, geom.roughness_m)
            last["inner"], last["annulus"] = d_i, d_a
            u_outer = u_outside_tube(
                h_i=d_i.h_W_m2K,
                h_o=d_a.h_W_m2K,
                Do=geom.inner_OD_m,
                Di=geom.inner_ID_m,
                k_wall=geom.k_wall_W_mK,
                R_fi=geom.R_f_inner_m2K_W,
                R_fo=geom.R_f_outer_m2K_W,
            )
            return u_outer * math.pi * geom.inner_OD_m * geom.length_m

        rated = rate_two_stream(hot, cold, thermo, P_h_out, P_c_out, ua_of, eps_counterflow)

        a_outer = math.pi * geom.inner_OD_m * geom.length_m
        h_in = hot.enthalpy * hot.molar_flow + cold.enthalpy * cold.molar_flow
        h_out = rated.hot_out.enthalpy * rated.hot_out.molar_flow
        h_out += rated.cold_out.enthalpy * rated.cold_out.molar_flow
        info: dict[str, Any] = {
            "duty_W": rated.duty_W,
            "U_W_m2K": rated.UA_W_K / a_outer,
            "A_m2": a_outer,
            "UA_W_K": rated.UA_W_K,
            "NTU": rated.NTU,
            "effectiveness": rated.effectiveness,
            "LMTD_K": lmtd_counter(hot.T, rated.hot_out.T, cold.T, rated.cold_out.T),
            "h_inner_W_m2K": last["inner"].h_W_m2K,
            "h_annulus_W_m2K": last["annulus"].h_W_m2K,
            "Re_inner": last["inner"].Re,
            "Re_annulus": last["annulus"].Re,
            "dP_inner_Pa": dp_inner,
            "dP_annulus_Pa": dp_annulus,
            "rating_iterations": float(rated.iterations),
        }
        return UnitResult(
            outlets={"hot_out": rated.hot_out, "cold_out": rated.cold_out},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )
