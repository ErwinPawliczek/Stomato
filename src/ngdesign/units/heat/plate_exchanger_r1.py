"""Gasketed chevron-plate exchanger, R1 rating level (spec ``plate_exchanger R1``).

Counter-current single-phase rating on the shared
:mod:`ngdesign.units.heat.rating` core: Martin 1996 (Chem. Eng. Process. 35:301)
/ VDI Heat Atlas 2nd ed. (2010), N6 chevron-plate film coefficients and Darcy
friction, an overall U on the plate area with the wall and fouling resistances,
a pressure drop per side from INLET-state properties with the 1.4-velocity-head
port loss (Shah & Focke 1988; Kakaç, Liu & Pramuanjaroenkij, Heat Exchangers,
3rd ed., ch. 10), and the duty from the brentq solve of the counterflow
epsilon-NTU residual on enthalpies.

The VDI N6 forms are implemented explicitly (friction 1/sqrt(f) with the
Konakov turbulent branch ``(1.8 log10 Re - 1.5)**-2`` and
``Nu = 0.122 Pr^(1/3) (mu/mu_w)^(1/6) [f Re^2 sin(2 phi_c)]^0.374`` with
``mu/mu_w = 1`` at R1): the closed-form anchors of the spec pin this explicit
form, which ``ht.Nu_plate_Martin(..., variant='VDI')`` reproduces only to
~5e-6 relative (its internal evaluation differs in the last digits). The
``'1999'`` variant is never used - its friction formula is documented on a
Fanning basis while its 0.122 Nusselt coefficient assumes Darcy. The
``correlation: kumar`` switch routes both friction and Nusselt through
``fluids.friction_plate_Kumar`` / ``ht.Nu_plate_Kumar`` so a V1 case can run
the book's own correlation.

The geometry comes from the R1 params (spec Params table) through
``fluids.geometry.PlateExchanger`` (read-only): ``b = 2*amplitude``,
``D_h`` from the geometry object, per-channel flow area ``b*width``,
``channels_per_fluid = (plates - 1)/2``, heat-transfer area ``A_heat_transfer``;
single-pass counter-current arrangement. ``duty_W`` follows the R0 convention
(the round-off enthalpy residual of an internal exchanger); the transferred
heat is reported in ``info["duty_W"]``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import fluids
import ht

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units.heat.rating import (
    FilmProps,
    PropertyUnavailable,
    RatingError,
    SinglePhaseRequired,
    film_props,
    inlet_kind,
    rate_two_stream,
)

#: Martin's data cover 200 <= Re <= 1e4 (VDI Heat Atlas N6); outside the range
#: the rating refuses unless ``allow_extrapolation`` is set.
RE_MIN = 200.0
RE_MAX = 1.0e4

#: Port pressure loss in velocity heads (Shah & Focke 1988; Kakaç, Liu &
#: Pramuanjaroenkij, Heat Exchangers, 3rd ed., ch. 10).
PORT_VELOCITY_HEADS = 1.4

#: Chevron angle bounds, degrees from the flow direction (spec Params table).
CHEVRON_MIN_DEG = 0.0
CHEVRON_MAX_DEG = 80.0


class PlateGeometryError(ValueError):
    """R1 geometry params are missing, out of range or mis-typed; the param is named."""


class PlateCorrelationRangeError(RatingError):
    """The channel Re sits outside Martin's 200-1e4 data range; the side is named."""


def friction_martin_vdi(Re: float, chevron_angle_deg: float) -> float:
    """Darcy friction factor of a chevron channel (Martin 1996; VDI N6, eq. 2).

    ``1/sqrt(f) = cos(phi)/sqrt(0.18 tan(phi) + 0.36 sin(phi) + f0/cos(phi))
    + (1 - cos(phi))/sqrt(3.8 f1)`` with ``f0 = 64/Re`` and
    ``f1 = 597/Re + 3.85`` for Re < 2000; otherwise ``f0 = (1.8 log10 Re
    - 1.5)**-2`` (Konakov, the form VDI N6 prints - ``fluids``' docstring
    misprints it as ``(1.56 ln Re - 3)**-2``) and ``f1 = 39 Re**-0.289``.
    """
    phi = math.radians(chevron_angle_deg)
    if Re < 2000.0:
        f0 = 64.0 / Re
        f1 = 597.0 / Re + 3.85
    else:
        f0 = (1.8 * math.log10(Re) - 1.5) ** -2
        f1 = 39.0 * Re**-0.289
    inv_sqrt_f = math.cos(phi) / math.sqrt(
        0.18 * math.tan(phi) + 0.36 * math.sin(phi) + f0 / math.cos(phi)
    ) + (1.0 - math.cos(phi)) / math.sqrt(3.8 * f1)
    return inv_sqrt_f**-2


def nusselt_martin_vdi(Re: float, Pr: float, chevron_angle_deg: float, f: float) -> float:
    """Nusselt number of a chevron channel (Martin 1996; VDI N6, eq. 3).

    ``Nu = 0.122 Pr^(1/3) (mu/mu_w)^(1/6) [f Re^2 sin(2 phi_c)]^0.374`` with
    the Darcy ``f`` of :func:`friction_martin_vdi` and ``mu/mu_w = 1`` at R1.
    """
    phi = math.radians(chevron_angle_deg)
    return float(0.122 * Pr ** (1.0 / 3.0) * (f * Re * Re * math.sin(2.0 * phi)) ** 0.374)


def friction_kumar(Re: float, chevron_angle_deg: float) -> float:
    """Darcy friction factor, Kumar's correlation (``fluids.friction_plate_Kumar``)."""
    return float(fluids.friction_plate_Kumar(Re, chevron_angle_deg))


def nusselt_kumar(Re: float, Pr: float, chevron_angle_deg: float) -> float:
    """Nusselt number, Kumar's correlation (``ht.Nu_plate_Kumar``)."""
    return float(ht.Nu_plate_Kumar(Re, Pr, chevron_angle_deg))


@dataclass(frozen=True)
class PlateGeometry:
    """Validated R1 geometry params and the derived channel quantities."""

    amplitude_m: float
    wavelength_m: float
    chevron_angle_deg: float
    plate_width_m: float
    plate_length_m: float
    port_diameter_m: float
    n_plates: int
    plate_thickness_m: float
    k_plate_W_mK: float
    R_f_hot_m2K_W: float
    R_f_cold_m2K_W: float
    correlation: str
    allow_extrapolation: bool
    b_m: float
    D_h_m: float
    A_channel_m2: float
    channels_per_fluid: float
    A_heat_m2: float
    enlargement_factor: float


def _require_positive(name: str, value: Any) -> float:
    """A required positive geometry param, refusing missing or non-positive."""
    if value is None:
        raise PlateGeometryError(f"plate_exchanger R1 requires geometry param {name!r}")
    v = float(value)
    if not v > 0.0:
        raise PlateGeometryError(f"plate_exchanger R1: {name} must be > 0, got {value}")
    return v


def plate_geometry(params: dict[str, Any]) -> PlateGeometry:
    """Validate the params against the refusal table; every message names the param."""
    amplitude = _require_positive("amplitude_m", params.get("amplitude_m"))
    wavelength = _require_positive("wavelength_m", params.get("wavelength_m"))
    chevron_value = params.get("chevron_angle_deg")
    if chevron_value is None:
        raise PlateGeometryError("plate_exchanger R1 requires geometry param 'chevron_angle_deg'")
    chevron = float(chevron_value)
    if not CHEVRON_MIN_DEG <= chevron <= CHEVRON_MAX_DEG:
        raise PlateGeometryError(
            f"plate_exchanger R1: chevron_angle_deg must be in "
            f"[{CHEVRON_MIN_DEG}, {CHEVRON_MAX_DEG}], got {chevron_value}"
        )
    width = _require_positive("plate_width_m", params.get("plate_width_m"))
    length = _require_positive("plate_length_m", params.get("plate_length_m"))
    port = _require_positive("port_diameter_m", params.get("port_diameter_m"))
    plates_value = params.get("n_plates")
    if plates_value is None:
        raise PlateGeometryError("plate_exchanger R1 requires geometry param 'n_plates'")
    n_plates = int(plates_value)
    if n_plates != plates_value or n_plates < 3:
        raise PlateGeometryError(f"plate_exchanger R1: n_plates must be an integer >= 3, got {plates_value}")
    thickness = _require_positive("plate_thickness_m", params.get("plate_thickness_m", 6.0e-4))
    k_plate = _require_positive("k_plate_W_mK", params.get("k_plate_W_mK", 16.0))
    fouling: dict[str, float] = {}
    for name in ("R_f_hot_m2K_W", "R_f_cold_m2K_W"):
        raw = params.get(name, 0.0)
        if float(raw) < 0.0:
            raise PlateGeometryError(f"plate_exchanger R1: {name} must be >= 0, got {raw}")
        fouling[name] = float(raw)
    correlation = params.get("correlation", "martin")
    if correlation not in ("martin", "kumar"):
        raise PlateGeometryError(
            f"plate_exchanger R1: correlation must be 'martin' or 'kumar', got {correlation!r}"
        )
    allow_extrapolation = bool(params.get("allow_extrapolation", False))

    g = fluids.geometry.PlateExchanger(
        amplitude,
        wavelength,
        chevron_angle=int(chevron),
        width=width,
        length=length,
        d_port=port,
        plates=n_plates,
    )
    b = 2.0 * amplitude  # channel gap
    a_channel = b * width
    return PlateGeometry(
        amplitude_m=amplitude,
        wavelength_m=wavelength,
        chevron_angle_deg=chevron,
        plate_width_m=width,
        plate_length_m=length,
        port_diameter_m=port,
        n_plates=n_plates,
        plate_thickness_m=thickness,
        k_plate_W_mK=k_plate,
        R_f_hot_m2K_W=fouling["R_f_hot_m2K_W"],
        R_f_cold_m2K_W=fouling["R_f_cold_m2K_W"],
        correlation=str(correlation),
        allow_extrapolation=allow_extrapolation,
        b_m=b,
        D_h_m=float(g.D_hydraulic),
        A_channel_m2=a_channel,
        channels_per_fluid=float(g.channels_per_fluid),
        A_heat_m2=float(g.A_heat_transfer),
        enlargement_factor=float(g.plate_enlargement_factor),
    )


def channel_velocity(m_kg_s: float, rho: float, A_channel_m2: float, channels_per_fluid: float) -> float:
    """Mean channel velocity, ``v = m/(rho*N_ch*A_ch)`` (VDI N6)."""
    return m_kg_s / (rho * channels_per_fluid * A_channel_m2)


def channel_Re(rho: float, v: float, D_h_m: float, mu: float) -> float:
    """Channel Reynolds number, ``Re = rho*v*D_h/mu``."""
    return rho * v * D_h_m / mu


def channel_dP(f: float, L_m: float, D_h_m: float, rho: float, v: float) -> float:
    """Channel friction pressure drop, ``f*(L_p/D_h)*rho*v^2/2`` (Darcy form, VDI N6)."""
    return f * (L_m / D_h_m) * rho * v * v / 2.0


def port_velocity(m_kg_s: float, rho: float, d_port_m: float) -> float:
    """Port velocity, ``v_port = m/(rho*pi*d_port^2/4)``."""
    return m_kg_s / (rho * math.pi * d_port_m * d_port_m / 4.0)


def port_dP(rho: float, v_port: float) -> float:
    """Port pressure loss, ``1.4*rho*v_port^2/2`` (Shah & Focke 1988)."""
    return PORT_VELOCITY_HEADS * rho * v_port * v_port / 2.0


def overall_u(
    h_hot: float, h_cold: float, t_plate_m: float, k_plate: float, R_f_hot: float, R_f_cold: float
) -> float:
    """Overall U on the plate area, ``1/(1/h_h + t_p/k_p + 1/h_c + R_f,h + R_f,c)``."""
    return 1.0 / (1.0 / h_hot + t_plate_m / k_plate + 1.0 / h_cold + R_f_hot + R_f_cold)


@dataclass(frozen=True)
class SideRating:
    """One side's channel hydraulics at a film state."""

    v_m_s: float
    Re: float
    f: float
    Nu: float
    h_W_m2K: float
    dP_Pa: float
    in_range: bool


def _side_rating(
    geom: PlateGeometry,
    m_kg_s: float,
    props: FilmProps,
    side: str,
    allow_extrapolation: bool,
) -> SideRating:
    """Channel hydraulics of one side at a film state (Eqs. 2-4, 6).

    Raises:
        PlateCorrelationRangeError: the channel Re is outside Martin's
            200-1e4 data range and extrapolation is not allowed (the side
            and the Re are named).
    """
    v = channel_velocity(m_kg_s, props.rho_kg_m3, geom.A_channel_m2, geom.channels_per_fluid)
    Re = channel_Re(props.rho_kg_m3, v, geom.D_h_m, props.mu_Pa_s)
    in_range = RE_MIN <= Re <= RE_MAX
    if not in_range and not allow_extrapolation:
        raise PlateCorrelationRangeError(
            f"channel Re {Re:.1f} on the {side} side is outside Martin's correlation "
            f"range [{RE_MIN:g}, {RE_MAX:g}]; set allow_extrapolation to rate anyway"
        )
    if geom.correlation == "kumar":
        f = friction_kumar(Re, geom.chevron_angle_deg)
        Nu = nusselt_kumar(Re, props.Pr, geom.chevron_angle_deg)
    else:
        f = friction_martin_vdi(Re, geom.chevron_angle_deg)
        Nu = nusselt_martin_vdi(Re, props.Pr, geom.chevron_angle_deg, f)
    h = Nu * props.k_W_mK / geom.D_h_m
    v_port = port_velocity(m_kg_s, props.rho_kg_m3, geom.port_diameter_m)
    dP = channel_dP(f, geom.plate_length_m, geom.D_h_m, props.rho_kg_m3, v) + port_dP(props.rho_kg_m3, v_port)
    return SideRating(v_m_s=v, Re=Re, f=f, Nu=Nu, h_W_m2K=h, dP_Pa=dP, in_range=in_range)


class PlateExchangerR1:
    """Gasketed chevron-plate exchanger, R1: single-phase rating level."""

    inlet_ports = ("hot_in", "cold_in")
    outlet_ports = ("hot_out", "cold_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 water trim-cooler feeds plus the spec's geometry P1.

        Geometry P1 (0.5 mm amplitude, 3.7 mm wavelength, 45 degrees,
        0.3 x 1.2 m plates, 50 mm ports, 51 plates) keeps both sides inside
        Martin's 200-1e4 Re range on these feeds on the ``pr`` package
        (measured: hot ~2.4e3, cold ~7.8e2).
        """
        hot = {"T": 433.15, "P": 1.0e6, "molar_flow": 100.0, "composition": {"H2O": 1.0}}
        cold = {"T": 303.15, "P": 1.0e6, "molar_flow": 150.0, "composition": {"H2O": 1.0}}
        params: dict[str, Any] = {
            "amplitude_m": 5.0e-4,
            "wavelength_m": 3.7e-3,
            "chevron_angle_deg": 45.0,
            "plate_width_m": 0.3,
            "plate_length_m": 1.2,
            "port_diameter_m": 0.05,
            "n_plates": 51,
        }
        return {"hot_in": hot, "cold_in": cold}, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the exchanger at the R1 level; see the module docstring."""
        geom = plate_geometry(params)
        hot, cold = inlets["hot_in"], inlets["cold_in"]
        for side, state in (("hot", hot), ("cold", cold)):
            if state.mass_flow <= 0.0:
                raise RatingError(f"R1 rating needs both streams flowing: {side} side has zero flow")
        kind_h = _side_kind(hot, "hot")
        kind_c = _side_kind(cold, "cold")

        # Pressure drop per side from INLET-state properties (Eq. 6), before
        # the solve; no deltaP-property loop.
        film_h = _side_film(thermo, hot.composition, hot.T, hot.P, kind_h, "hot")
        film_c = _side_film(thermo, cold.composition, cold.T, cold.P, kind_c, "cold")
        rate_h = _side_rating(geom, hot.mass_flow, film_h, "hot", geom.allow_extrapolation)
        rate_c = _side_rating(geom, cold.mass_flow, film_c, "cold", geom.allow_extrapolation)
        P_h_out, P_c_out = hot.P - rate_h.dP_Pa, cold.P - rate_c.dP_Pa
        for side, p_out, drop in (("hot", P_h_out, rate_h.dP_Pa), ("cold", P_c_out, rate_c.dP_Pa)):
            if p_out <= 0.0:
                raise RatingError(
                    f"non-positive outlet pressure: {side} side drops to {p_out} Pa "
                    f"({drop} Pa across this geometry)"
                )

        # UA from the side-mean film state of each side (Eqs. 2-5),
        # re-evaluated at every g(Q) step; the last evaluation is the
        # reported rating. The correlation range flag is 1.0 only when every
        # evaluation stayed inside Martin's data range.
        last: dict[str, SideRating] = {}
        range_flags: list[bool] = [rate_h.in_range, rate_c.in_range]

        def ua_of(hot_out: StreamState, cold_out: StreamState) -> float:
            film_hm = _side_film(
                thermo, hot.composition, (hot.T + hot_out.T) / 2.0, (hot.P + P_h_out) / 2.0, kind_h, "hot"
            )
            film_cm = _side_film(
                thermo,
                cold.composition,
                (cold.T + cold_out.T) / 2.0,
                (cold.P + P_c_out) / 2.0,
                kind_c,
                "cold",
            )
            rm = _side_rating(geom, hot.mass_flow, film_hm, "hot", geom.allow_extrapolation)
            rc = _side_rating(geom, cold.mass_flow, film_cm, "cold", geom.allow_extrapolation)
            last["hot"], last["cold"] = rm, rc
            range_flags.extend((rm.in_range, rc.in_range))
            return (
                overall_u(
                    h_hot=rm.h_W_m2K,
                    h_cold=rc.h_W_m2K,
                    t_plate_m=geom.plate_thickness_m,
                    k_plate=geom.k_plate_W_mK,
                    R_f_hot=geom.R_f_hot_m2K_W,
                    R_f_cold=geom.R_f_cold_m2K_W,
                )
                * geom.A_heat_m2
            )

        rated = rate_two_stream(hot, cold, thermo, P_h_out, P_c_out, ua_of, eps_counterflow)

        h_in = hot.enthalpy * hot.molar_flow + cold.enthalpy * cold.molar_flow
        h_out = rated.hot_out.enthalpy * rated.hot_out.molar_flow
        h_out += rated.cold_out.enthalpy * rated.cold_out.molar_flow
        info: dict[str, Any] = {
            "duty_W": rated.duty_W,
            "U_W_m2K": rated.UA_W_K / geom.A_heat_m2,
            "A_m2": geom.A_heat_m2,
            "UA_W_K": rated.UA_W_K,
            "NTU": rated.NTU,
            "effectiveness": rated.effectiveness,
            "LMTD_K": lmtd_counter(hot.T, rated.hot_out.T, cold.T, rated.cold_out.T),
            "h_hot_W_m2K": last["hot"].h_W_m2K,
            "h_cold_W_m2K": last["cold"].h_W_m2K,
            "Re_hot": last["hot"].Re,
            "Re_cold": last["cold"].Re,
            "dP_hot_Pa": rate_h.dP_Pa,
            "dP_cold_Pa": rate_c.dP_Pa,
            "correlation_in_range": 1.0 if all(range_flags) else 0.0,
        }
        return UnitResult(
            outlets={"hot_out": rated.hot_out, "cold_out": rated.cold_out},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )


def eps_counterflow(NTU: float, Cr: float) -> float:
    """Counter-current effectiveness through ``ht.effectiveness_from_NTU``.

    ``[1 - exp(-NTU(1-Cr))] / [1 - Cr*exp(-NTU(1-Cr))]``, or ``NTU/(1 + NTU)``
    at Cr = 1 (``ht``'s ``counterflow`` subtype, which the R0 replay
    reproduces exactly).
    """
    return float(ht.effectiveness_from_NTU(NTU, Cr, subtype="counterflow"))  # type: ignore[no-untyped-call]


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
