"""Compressor R1: performance map with Schultz polytropic head.

Spec: specs/backend/units/compressor.md (level wave, U-R2 conventions).

Method: the map gives head and efficiency versus actual inlet flow at map
speed. Fan laws (Perry's 9th ed. par. 10, compressor laws; API 617 8th ed.
par. 2.x, informative) scale to the speed ratio s = N/N_map:
Q_eq = Q/s, H = s^2 * H_map(Q_eq), eta = eta_map(Q_eq). PCHIP
interpolation with no extrapolation. Surge and stonewall limits are
compared with Q_eq, both at map speed.

Two efficiency bases:
- isentropic: H_is(P2) = (h(P2, s1) - h1)/M. The operating point solves
  H_is(P2) = H; the outlet is the R0 adapter (ngdesign.units.compressor).
- polytropic (Schultz, J. Eng. Power 84 (1962) 69-82; ASME PTC 10-1997
  par. 5, the Schultz method):
  n_s = ln(P2/P1) / ln(v1/v2s);
  f = [(h2s - h1)/M] / [(n_s/(n_s - 1)) * (P2*v2s - P1*v1)];
  actual work w = H/eta_p, so h2 = h1 + M*H/eta_p and
  state 2 = flash_ph(z, P2, h2); n = ln(P2/P1) / ln(v1/v2);
  H_p(P2) = f * (n/(n - 1)) * (P2*v2 - P1*v1).
  The operating point solves H_p(P2) = H.

P2 is found with brentq (explicit xtol = 1e-9*P1, maxiter 100, sign check
at b); every state used in a head evaluation must be single-phase, else a
typed refusal. Power is F*(h2 - h1) = mdot*H/eta in both bases.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.compressor import Compressor


class CompressorR1SpecError(ValueError):
    """A compressor R1 spec or parameter is invalid."""


class CompressorSurgeError(CompressorR1SpecError):
    """The operating point lies left of the surge line."""


class CompressorStonewallError(CompressorR1SpecError):
    """The operating point lies right of the stonewall line."""


class CompressorMapRangeError(CompressorR1SpecError):
    """The operating point or the discharge solve falls outside the map."""


class CompressorTwoPhaseError(CompressorR1SpecError):
    """A state used in a head evaluation is not single-phase."""


def _single_phase(state: StreamState, P2: float) -> None:
    """Refuse any state used in a head evaluation that is not single-phase.

    Single-phase is literal: one phase in the flash result, whatever the
    package calls it (a dense supercritical discharge is one phase). Only a
    flash that splits into two phases is refused, with P2.
    """
    if len(state.phases) != 1:
        raise CompressorTwoPhaseError(f"two-phase state at P2 = {P2:.6g} Pa during the head evaluation")


def _parse_map(params: dict[str, Any]) -> tuple[list[float], list[float], list[float]]:
    """Validate and unpack the map arrays (refusal rows: map.<key>, length, monotonicity)."""
    raw = params.get("map")
    if not isinstance(raw, dict):
        raise CompressorR1SpecError("map is required: map.flow_m3_s, map.head_J_kg and map.efficiency")
    arrays: dict[str, list[float]] = {}
    for key in ("flow_m3_s", "head_J_kg", "efficiency"):
        if key not in raw:
            raise CompressorR1SpecError(f"map.{key} is required")
        arrays[key] = [float(x) for x in raw[key]]
    flow, head, eff = arrays["flow_m3_s"], arrays["head_J_kg"], arrays["efficiency"]
    if len(flow) != len(head) or len(flow) != len(eff):
        raise CompressorR1SpecError(
            "map.flow_m3_s, map.head_J_kg and map.efficiency must have the same length"
        )
    if len(flow) < 2:
        raise CompressorR1SpecError("map.flow_m3_s must be strictly increasing with at least 2 points")
    if any(flow[i + 1] <= flow[i] for i in range(len(flow) - 1)):
        raise CompressorR1SpecError("map.flow_m3_s must be strictly increasing")
    return flow, head, eff


def _polytropic_pieces(
    z: dict[str, float],
    P1: float,
    h1: float,
    s1: float,
    M: float,
    v1: float,
    F: float,
    H: float,
    eta: float,
    P2: float,
    thermo: Thermo,
) -> tuple[float, float, float, float, StreamState]:
    """Schultz pieces at P2, per spec eq. 6.

    Returns (H_p, f, n_isentropic_path, n_polytropic, state 2). State 2s
    comes from flash_ps at the inlet entropy; state 2 from flash_ph at the
    actual work h2 = h1 + M*H/eta_p. Every state must be single-phase.
    """
    st2s = thermo.flash_ps(z, P2, s1, F)
    _single_phase(st2s, P2)
    v2s = 1.0 / st2s.phases[0].density
    n_isentropic = math.log(P2 / P1) / math.log(v1 / v2s)
    schultz_f = ((st2s.enthalpy - h1) / M) / ((n_isentropic / (n_isentropic - 1.0)) * (P2 * v2s - P1 * v1))
    st2 = thermo.flash_ph(z, P2, h1 + M * H / eta, F)
    _single_phase(st2, P2)
    v2 = 1.0 / st2.phases[0].density
    n_polytropic = math.log(P2 / P1) / math.log(v1 / v2)
    head = schultz_f * (n_polytropic / (n_polytropic - 1.0)) * (P2 * v2 - P1 * v1)
    return head, schultz_f, n_isentropic, n_polytropic, st2


class CompressorR1:
    """Centrifugal compressor on a head/efficiency performance map.

    Plugin kind "unit", name "compressor", level R1 (provisional). Reduces to
    the R0 isentropic adapter when ``efficiency_basis`` is ``isentropic``.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction < 0.999 or len(inlet.phases) != 1:
            raise CompressorR1SpecError(
                f"inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f}, phases={len(inlet.phases)})"
            )

        flow, head_map, eff_map = _parse_map(params)
        basis = str(params.get("efficiency_basis", "polytropic"))
        if basis not in ("polytropic", "isentropic"):
            raise CompressorR1SpecError(f"efficiency_basis {basis!r} must be 'polytropic' or 'isentropic'")
        speed = float(params.get("speed_ratio", 1.0))
        if speed <= 0.0:
            raise CompressorR1SpecError(f"speed_ratio {speed} must be > 0")
        max_ratio = float(params.get("max_pressure_ratio", 10.0))
        if max_ratio <= 1.0:
            raise CompressorR1SpecError(f"max_pressure_ratio {max_ratio} must be > 1")
        surge = float(params.get("surge_flow_m3_s", flow[0]))
        stonewall = float(params.get("stonewall_flow_m3_s", flow[-1]))
        if surge < flow[0] or surge > flow[-1] or surge >= stonewall:
            raise CompressorR1SpecError(
                f"surge_flow_m3_s {surge} must lie within the map"
                f" [{flow[0]}, {flow[-1]}] and below stonewall_flow_m3_s {stonewall}"
            )

        # Q = mdot/rho1 (eq. 1); fan laws (eq. 2) and surge/stonewall (eq. 4).
        rho1 = inlet.phases[0].density  # kg/m3, single phase by the check above
        mdot = inlet.mass_flow
        F = inlet.molar_flow
        M = mdot / F  # kg/mol
        Q = mdot / rho1
        Q_eq = Q / speed
        if Q_eq < surge:
            raise CompressorSurgeError(
                f"surge: Q_eq {Q_eq:.6f} m3/s is below the surge flow {surge:.6f} m3/s"
            )
        if Q_eq > stonewall:
            raise CompressorStonewallError(
                f"stonewall: Q_eq {Q_eq:.6f} m3/s exceeds the stonewall flow {stonewall:.6f} m3/s"
            )
        if Q_eq < flow[0] or Q_eq > flow[-1]:
            raise CompressorMapRangeError(
                f"Q_eq {Q_eq:.6f} m3/s is outside the map [{flow[0]}, {flow[-1]}] m3/s"
            )

        # Map interpolation (eq. 3): PCHIP, no extrapolation; fan laws (eq. 2).
        head_curve = PchipInterpolator(flow, head_map, axis=0, extrapolate=None)
        eta_curve = PchipInterpolator(flow, eff_map, axis=0, extrapolate=None)
        H = speed * speed * float(head_curve(Q_eq))
        eta = float(eta_curve(Q_eq))
        if H <= 0.0:
            raise CompressorR1SpecError(f"head {H} J/kg interpolated from the map must be > 0")
        if not 0.0 < eta <= 1.0:
            raise CompressorR1SpecError(f"efficiency {eta} interpolated from the map outside (0, 1]")

        z, P1 = inlet.composition, inlet.P
        h1, s1 = inlet.enthalpy, inlet.entropy
        v1 = 1.0 / rho1

        def head_isentropic(P2: float) -> float:
            """g(P2) = H_is(P2) - H (eq. 5 less the map head): the brentq residual."""
            st2s = thermo.flash_ps(z, P2, s1, F)
            _single_phase(st2s, P2)
            return (st2s.enthalpy - h1) / M - H

        def head_polytropic(P2: float) -> float:
            """g(P2) = H_p(P2) - H (eq. 6 less the map head): the brentq residual."""
            return _polytropic_pieces(z, P1, h1, s1, M, v1, F, H, eta, P2, thermo)[0] - H

        head_fn: Callable[[float], float] = head_isentropic if basis == "isentropic" else head_polytropic

        # Discharge-pressure solve (algorithm step 4).
        a = P1 * (1.0 + 1e-6)
        b = P1 * max_ratio
        if head_fn(b) < 0.0:
            raise CompressorMapRangeError(
                f"map head exceeds the head at max_pressure_ratio {max_ratio}: no root up to P2 = {b:.6g} Pa"
            )
        try:
            P2 = brentq(head_fn, a, b, xtol=1e-9 * P1, maxiter=100)
        except (ValueError, RuntimeError) as exc:
            raise CompressorMapRangeError(
                f"no root up to max_pressure_ratio {max_ratio}: brentq failed in"
                f" bracket [{a:.6g}, {b:.6g}] Pa ({exc})"
            ) from exc

        # Outlet construction (algorithm step 5).
        if basis == "isentropic":
            r0 = Compressor().solve(inlets, {"P_out": P2, "eta_isentropic": eta}, thermo)
            outlet = r0.outlets["outlet"]
            power_W = r0.power_W
        else:
            _, _, _, _, outlet = _polytropic_pieces(z, P1, h1, s1, M, v1, F, H, eta, P2, thermo)
            power_W = F * (outlet.enthalpy - h1)

        info: dict[str, float] = {
            "P_out_Pa": P2,
            "pressure_ratio": P2 / P1,
            "Q_actual_m3_s": Q,
            "Q_equiv_m3_s": Q_eq,
            "head_J_kg": H,
            "eta": eta,
            "speed_ratio": speed,
            "surge_margin": Q_eq / surge - 1.0,
            "stonewall_margin": 1.0 - Q_eq / stonewall,
            "T_out_K": outlet.T,
        }
        if basis == "polytropic":
            _, schultz_f, n_isentropic, n_polytropic, _ = _polytropic_pieces(
                z, P1, h1, s1, M, v1, F, H, eta, P2, thermo
            )
            info["schultz_f"] = schultz_f
            info["n_polytropic"] = n_polytropic
            info["n_isentropic_path"] = n_isentropic
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=power_W, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed (dry gas, 322.15 K, 3.447 MPa, 691.7 mol/s) on the spec map."""
        feeds, _ = Compressor.example_case()
        params: dict[str, Any] = {
            "map": {
                "flow_m3_s": [0.30, 0.40, 0.50, 0.60, 0.70],
                "head_J_kg": [72000.0, 66000.0, 60000.0, 54000.0, 48000.0],
                "efficiency": [0.69, 0.72, 0.75, 0.78, 0.81],
            },
        }
        return feeds, params
