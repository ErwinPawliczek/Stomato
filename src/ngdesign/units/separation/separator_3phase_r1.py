"""Three-phase separator R1: rating at a given vessel geometry.

Spec ``specs/backend/units/separator_3phase.md``; conventions in
``specs/backend/U-R2-level-wave-conventions.md`` (U-R1 still binds). No
``@register``: dispatch comes from the catalogue YAML row.

The R0 adapter (:class:`ngdesign.units.separator.Separator3Phase`) owns the
VLLE phase split. R1 rates a given vessel (diameter, effective length,
orientation, normal liquid level NLL and normal interface level NIL) on that
split:

- **T1** layer areas. Horizontal: circular segment ``A(h) = R^2 acos((R-h)/R)
  - (R-h) sqrt(2Rh - h^2)`` via ``fluids.geometry.A_partial_circle``;
  ``A_w = A(h_i)``, ``A_o = A(h_l) - A(h_i)``, ``A_g = pi D^2/4 - A(h_l)``.
  Vertical: every layer has the full section ``pi D^2/4``.
- **T2** residence times ``t = A L_eff / Q`` (horizontal), ``t = A H / Q``
  (vertical), with ``Q = mdot / rho`` per R0 outlet.
- **T3** Souders-Brown gas capacity (GPSA Engineering Data Book Sect. 7;
  Svrcek & Monnery, Chem. Eng. Prog. 89(10):53-60, 1993) through
  :func:`ngdesign.units.separation.scrubber_r1.size_gas_section` (owner
  :func:`ngdesign.sizing.souders_brown.souders_brown`); ``v_G = Q_G / A_g``.
  Default K is the York fit, range-checked by ``york_K_m_s``; horizontal
  vessels take ``K_separator_demister_York(P, horizontal=True)``.
- **T4** gas-section cut diameter (report only): the drop whose terminal
  velocity is ``v_s`` (vertical ``v_s = v_G``; horizontal ``v_s = v_G H_g /
  L_eff``), from the scrubber's Morrison-drag ``cut_diameter_m``.
- **T5** Stokes' law (Stokes 1851) through ``decanter_r1.stokes_velocity``.
- **T6** liquid-liquid cut diameter: ``u_t(d_cut) t = H``, so ``d_cut =
  sqrt((H/t) / u_t(1 m))`` (Stokes is proportional to d^2).
- **T7** capture fraction of a droplet (Hazen 1904 ideal settler on the
  layer's cross-section), ``s = u_t t``: horizontal water-in-oil
  ``[A(min(h_i+s, h_l)) - A(h_i)] / A_o``, oil-in-water ``[A(h_i) -
  A(max(h_i-s, 0))] / A_w``; vertical ``1`` if ``s >= H`` else ``0``.
- **T8** carry-over ``f_w = E_w (1 - eta_wo)`` of the water outlet into the
  oil outlet, ``f_o = E_o (1 - eta_ow)`` of the oil outlet into the water.

Gas-side carry-over is report-only (T3/T4). An outlet that only donates is
R0's scaled with ``model_copy`` (never re-flashed, S-24b); an outlet that
receives liquid is PT-flashed as the two-liquid mix. With no geometry, no
droplet params, zero entrainment or full capture the outlets are R0's.
"""

from __future__ import annotations

import math
from typing import Any

from fluids.geometry import A_partial_circle
from fluids.separator import K_separator_demister_York

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.decanter_r1 import stokes_velocity
from ngdesign.units.separation.scrubber_r1 import (
    cut_diameter_m,
    liquid_density_kg_m3,
    size_gas_section,
    york_K_m_s,
)
from ngdesign.units.separator import Separator3Phase

__all__ = [
    "Separator3PhaseR1",
    "Separator3PhaseR1SpecError",
    "capture_fraction",
    "layer_areas",
    "stokes_cut_diameter_m",
]

_GEOMETRY_KEYS = ("diameter_m", "length_m", "liquid_level_m", "interface_level_m")
_OVERRIDE_KEYS = ("K_m_s", "gas_viscosity_Pa_s", "oil_viscosity_Pa_s", "water_viscosity_Pa_s")
_ORIENTATIONS = ("horizontal", "vertical")


class Separator3PhaseR1SpecError(ValueError):
    """A refused three-phase separator R1 specification; the message names the parameter."""


def layer_areas(
    orientation: str,
    diameter_m: float,
    liquid_level_m: float,
    interface_level_m: float,
) -> dict[str, float]:
    """T1 flow areas of the gas, oil and water layers [m2].

    Horizontal: ``A_w = A(h_i)``, ``A_o = A(h_l) - A(h_i)``, ``A_g = pi D^2/4 -
    A(h_l)`` with ``A(h)`` the circular segment below h
    (``fluids.geometry.A_partial_circle``). Vertical: each layer ``pi D^2/4``.
    """
    full = math.pi * diameter_m**2 / 4.0
    if orientation == "vertical":
        return {"A_gas_m2": full, "A_oil_m2": full, "A_water_m2": full}
    a_i = A_partial_circle(diameter_m, interface_level_m)
    a_l = A_partial_circle(diameter_m, liquid_level_m)
    return {"A_gas_m2": full - a_l, "A_oil_m2": a_l - a_i, "A_water_m2": a_i}


def stokes_cut_diameter_m(
    required_velocity_m_s: float,
    rho_water: float,
    rho_oil: float,
    mu_continuous_Pa_s: float,
) -> float:
    """T6 droplet whose Stokes velocity equals ``required_velocity_m_s`` [m].

    Stokes ``u_t = g d^2 |rho_w - rho_o| / (18 mu_c)`` is proportional to d^2,
    so ``d = sqrt(v_req / u_t(1 m))`` inverts the owner
    (:func:`ngdesign.units.separation.decanter_r1.stokes_velocity`) exactly.
    """
    return math.sqrt(required_velocity_m_s / stokes_velocity(1.0, rho_water, rho_oil, mu_continuous_Pa_s))


def capture_fraction(
    orientation: str,
    diameter_m: float,
    liquid_level_m: float,
    interface_level_m: float,
    settled_distance_m: float,
    layer: str,
) -> float:
    """T7 fraction of a droplet size captured at the interface (Hazen 1904 ideal settler).

    ``settled_distance_m`` is ``s = u_t t``. ``layer`` is ``"oil"`` (water drops
    falling through the oil pad) or ``"water"`` (oil drops rising through the
    water layer). Horizontal (plug flow over the segment cross-section, drops
    entering uniformly over the flow area)::

        eta_wo = [A(min(h_i + s, h_l)) - A(h_i)] / A_o
        eta_ow = [A(h_i) - A(max(h_i - s, 0))] / A_w

    Vertical (uniform section, counter-current plug flow): ``1`` if ``s`` covers
    the layer height, else ``0``.
    """
    h_i, h_l, s = interface_level_m, liquid_level_m, settled_distance_m
    height = h_l - h_i if layer == "oil" else h_i
    if orientation == "vertical":
        return 1.0 if s >= height else 0.0
    a_i = A_partial_circle(diameter_m, h_i)
    if layer == "oil":
        a_o = A_partial_circle(diameter_m, h_l) - a_i
        return (A_partial_circle(diameter_m, min(h_i + s, h_l)) - a_i) / a_o
    return (a_i - A_partial_circle(diameter_m, max(h_i - s, 0.0))) / a_i


def _number(params: dict[str, Any], name: str, *, positive: bool = True) -> float | None:
    """An optional numeric param; refuses a non-number or a non-positive value."""
    value = params.get(name)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise Separator3PhaseR1SpecError(f"{name} must be a number, got {value!r}")
    if positive and value <= 0:
        raise Separator3PhaseR1SpecError(f"{name} must be positive, got {value}")
    return float(value)


def _fraction(params: dict[str, Any], name: str) -> float | None:
    value = _number(params, name, positive=False)
    if value is not None and not 0.0 <= value <= 1.0:
        raise Separator3PhaseR1SpecError(f"{name} must be within [0, 1], got {value}")
    return value


def _phase_of(stream: StreamState, vapour: bool) -> Any:
    """The R0 outlet's own phase (each R0 outlet carries one phase kind)."""
    for p in stream.phases:
        if (p.kind is PhaseKind.VAPOR) is vapour:
            return p
    raise Separator3PhaseR1SpecError("an R0 outlet carries no phase of its kind")


def _viscosity(stream: StreamState, vapour: bool, override: float | None, name: str) -> float:
    mu = _phase_of(stream, vapour).viscosity
    if mu is not None:
        return float(mu)
    if override is None:
        raise Separator3PhaseR1SpecError(f"the package gives no viscosity for this phase; pass {name}")
    return override


def _droplet_pair(params: dict[str, Any], fraction_key: str, diameter_key: str) -> tuple[float, float] | None:
    E = _fraction(params, fraction_key)
    d = _number(params, diameter_key)
    if (E is None) != (d is None):
        missing = diameter_key if d is None else fraction_key
        raise Separator3PhaseR1SpecError(f"{missing} is required with {fraction_key}/{diameter_key}")
    return None if E is None or d is None else (E, d)


def _mix(kept: StreamState, kept_frac: float, received: StreamState, recv_frac: float) -> tuple[dict[str, float], float]:
    n_k = kept_frac * kept.molar_flow
    n_r = recv_frac * received.molar_flow
    n = n_k + n_r
    cids = {*kept.composition, *received.composition}
    z = {c: (n_k * kept.composition.get(c, 0.0) + n_r * received.composition.get(c, 0.0)) / n for c in cids}
    return z, n


class Separator3PhaseR1:
    """Three-phase separator rated at a given geometry (gas capacity, residence, Stokes settling)."""

    inlet_ports: tuple[str, ...] = Separator3Phase.inlet_ports
    outlet_ports: tuple[str, ...] = Separator3Phase.outlet_ports

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed in a 1.5 m x 4.5 m horizontal vessel with liquid-liquid carry-over."""
        feeds, _ = Separator3Phase.example_case()
        params = {
            "orientation": "horizontal",
            "diameter_m": 1.5,
            "length_m": 4.5,
            "liquid_level_m": 0.75,
            "interface_level_m": 0.3,
            "water_in_oil_fraction": 0.1,
            "water_droplet_diameter_m": 10e-6,
            "oil_in_water_fraction": 0.05,
            "oil_droplet_diameter_m": 6e-6,
        }
        return feeds, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Rate the R0 split at the given geometry (spec algorithm, steps 1-6)."""
        orientation = params.get("orientation", "horizontal")
        if orientation not in _ORIENTATIONS:
            raise Separator3PhaseR1SpecError(f"orientation must be one of {_ORIENTATIONS}, got {orientation!r}")
        geometry = {k: _number(params, k) for k in _GEOMETRY_KEYS}
        overrides = {k: _number(params, k) for k in _OVERRIDE_KEYS}
        water_drops = _droplet_pair(params, "water_in_oil_fraction", "water_droplet_diameter_m")
        oil_drops = _droplet_pair(params, "oil_in_water_fraction", "oil_droplet_diameter_m")
        given = [k for k, v in geometry.items() if v is not None]
        if given and len(given) < len(_GEOMETRY_KEYS):
            raise Separator3PhaseR1SpecError(f"a rating requires all of {_GEOMETRY_KEYS}; got only {given}")
        if not given and (water_drops is not None or oil_drops is not None):
            raise Separator3PhaseR1SpecError("droplet carry-over needs the vessel geometry (diameter_m, ...)")

        r0 = Separator3Phase().solve(inlets, {"dP": params.get("dP", 0.0)}, thermo)
        if not given:
            return r0

        D = float(geometry["diameter_m"] or 0.0)
        L = float(geometry["length_m"] or 0.0)
        h_l = float(geometry["liquid_level_m"] or 0.0)
        h_i = float(geometry["interface_level_m"] or 0.0)
        if h_i >= h_l:
            raise Separator3PhaseR1SpecError(
                f"interface_level_m ({h_i}) must lie below liquid_level_m ({h_l})"
            )
        top = D if orientation == "horizontal" else L
        if h_l >= top:
            bound = "diameter_m" if orientation == "horizontal" else "length_m"
            raise Separator3PhaseR1SpecError(f"liquid_level_m ({h_l}) must lie below {bound} ({top})")

        gas0, hc0, w0 = r0.outlets["gas_out"], r0.outlets["hc_out"], r0.outlets["water_out"]
        if min(gas0.molar_flow, hc0.molar_flow, w0.molar_flow) <= 0.0:
            raise Separator3PhaseR1SpecError("rating needs all three R0 outlets (gas, oil, water) with flow")

        # Step 2: phase properties from the R0 outlets.
        rho_G = _phase_of(gas0, vapour=True).density
        mu_G = _viscosity(gas0, True, overrides["gas_viscosity_Pa_s"], "gas_viscosity_Pa_s")
        rho_o = liquid_density_kg_m3(hc0)
        rho_w = liquid_density_kg_m3(w0)
        if rho_w <= rho_o:
            raise Separator3PhaseR1SpecError(
                f"the water phase ({rho_w} kg/m3) must be denser than the oil ({rho_o} kg/m3)"
            )
        mu_o = _viscosity(hc0, False, overrides["oil_viscosity_Pa_s"], "oil_viscosity_Pa_s")
        mu_w = _viscosity(w0, False, overrides["water_viscosity_Pa_s"], "water_viscosity_Pa_s")
        rho_L = liquid_density_kg_m3(hc0, w0)
        Q_G = gas0.mass_flow / rho_G
        Q_o = hc0.mass_flow / rho_o
        Q_w = w0.mass_flow / rho_w

        # Step 3: T1-T6.
        areas = layer_areas(orientation, D, h_l, h_i)
        H_o, H_w = h_l - h_i, h_i
        if orientation == "horizontal":
            t_o = areas["A_oil_m2"] * L / Q_o
            t_w = areas["A_water_m2"] * L / Q_w
        else:
            t_o = areas["A_oil_m2"] * H_o / Q_o
            t_w = areas["A_water_m2"] * H_w / Q_w
        K = overrides["K_m_s"]
        if K is None:
            york_K_m_s(gas0.P)  # range check (refuses outside 1-5500 psia before fluids clamps)
            K = K_separator_demister_York(gas0.P, horizontal=orientation == "horizontal")
        v_max = size_gas_section(K, rho_L, rho_G, Q_G)["v_max_m_s"]
        v_G = Q_G / areas["A_gas_m2"]
        v_s = v_G * (D - h_l) / L if orientation == "horizontal" else v_G
        d_cut_gas = cut_diameter_m(v_s, rho_L, rho_G, mu_G)["d_cut_m"]
        d_wo = stokes_cut_diameter_m(H_o / t_o, rho_w, rho_o, mu_o)
        d_ow = stokes_cut_diameter_m(H_w / t_w, rho_w, rho_o, mu_w)
        info: dict[str, float] = {
            "K_m_s": K,
            "v_max_m_s": v_max,
            "v_gas_m_s": v_G,
            "v_ratio": v_G / v_max,
            "gas_settling_velocity_m_s": v_s,
            "d_cut_gas_m": d_cut_gas,
            **areas,
            "Q_gas_m3_s": Q_G,
            "Q_oil_m3_s": Q_o,
            "Q_water_m3_s": Q_w,
            "rho_gas_kg_m3": rho_G,
            "rho_liquid_kg_m3": rho_L,
            "rho_oil_kg_m3": rho_o,
            "rho_water_kg_m3": rho_w,
            "mu_oil_Pa_s": mu_o,
            "mu_water_Pa_s": mu_w,
            "t_res_oil_s": t_o,
            "t_res_water_s": t_w,
            "d_cut_water_in_oil_m": d_wo,
            "Re_cut_water_in_oil": rho_o * (H_o / t_o) * d_wo / mu_o,
            "d_cut_oil_in_water_m": d_ow,
            "Re_cut_oil_in_water": rho_w * (H_w / t_w) * d_ow / mu_w,
        }

        # Steps 4: T5, T7, T8 for the given droplets.
        f_w = 0.0
        f_o = 0.0
        if water_drops is not None:
            E_w, d_w = water_drops
            u_w = stokes_velocity(d_w, rho_w, rho_o, mu_o)
            self._stokes_check(rho_o * u_w * d_w / mu_o, "water_droplet_diameter_m")
            eta = capture_fraction(orientation, D, h_l, h_i, u_w * t_o, "oil")
            f_w = E_w * (1.0 - eta)
            info["eta_water_in_oil"] = eta
            info["carryover_water_to_oil_kg_s"] = f_w * w0.mass_flow
        if oil_drops is not None:
            E_o, d_o = oil_drops
            u_o = stokes_velocity(d_o, rho_w, rho_o, mu_w)
            self._stokes_check(rho_w * u_o * d_o / mu_w, "oil_droplet_diameter_m")
            eta = capture_fraction(orientation, D, h_l, h_i, u_o * t_w, "water")
            f_o = E_o * (1.0 - eta)
            info["eta_oil_in_water"] = eta
            info["carryover_oil_to_water_kg_s"] = f_o * hc0.mass_flow

        if f_w == 0.0 and f_o == 0.0:
            return UnitResult(outlets=dict(r0.outlets), duty_W=r0.duty_W, power_W=0.0, info=info)

        # Step 5: donors scaled, receivers PT-flashed as two-liquid mixes.
        T, P = hc0.T, hc0.P
        if f_w > 0.0:
            z, n = _mix(hc0, 1.0 - f_o, w0, f_w)
            hc_out = thermo.flash_pt(z, T, P, n)
        else:
            hc_out = hc0.model_copy(update={"molar_flow": (1.0 - f_o) * hc0.molar_flow})
        if f_o > 0.0:
            z, n = _mix(w0, 1.0 - f_w, hc0, f_o)
            water_out = thermo.flash_pt(z, T, P, n)
        else:
            water_out = w0.model_copy(update={"molar_flow": (1.0 - f_w) * w0.molar_flow})
        outlets = {"gas_out": gas0, "hc_out": hc_out, "water_out": water_out}

        # Step 6: the balance duty, summed exactly as R0 sums it.
        inlet = inlets["inlet"]
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - inlet.enthalpy * inlet.molar_flow,
            power_W=0.0,
            info=info,
        )

    @staticmethod
    def _stokes_check(Re: float, name: str) -> None:
        if Re >= 1.0:
            raise Separator3PhaseR1SpecError(
                f"Stokes validity exceeded: Re = {Re:.4g} >= 1 for {name}; R1 does not extrapolate Stokes' law"
            )
