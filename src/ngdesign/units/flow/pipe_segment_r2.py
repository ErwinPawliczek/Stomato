"""Pipe segment, level R2 (spec specs/backend/units/pipe_segment.md).

Two-phase Beggs-Brill pipe segment with a profile along the length. Segments
whose node flashes two-phase (0.001 < vapour molar fraction < 0.999) take
their step's dP from :func:`fluids.Beggs_Brill` -- the original 1973 holdup
correlation with the Brill-Beggs regime-map interpolation, the original
acceleration term, and **no Payne correction** (the Payne et al. holdup and
friction corrections are not applied, as specified). Single-phase segments
use the R1 Darcy-Colebrook step, so a line may flash part-way along.
Integration is the same Heun predictor-corrector as R1 but at a fixed N
(``n_segments``, default 20, cap 200): regime switches make the refinement
norm non-smooth, so R2 reports the N/2 discretisation difference
(``dP_check_N_half_Pa``) instead of auto-refining.

Each node is adiabatic and isenthalpic (PH flash at the inlet enthalpy), as
at R1. Surface tension is not part of the Thermo protocol, so a two-phase
node requires ``sigma_N_m`` as a param -- it is never invented.
"""

from __future__ import annotations

import math
from typing import Any

from fluids import Beggs_Brill

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import Phase, PhaseKind
from ngdesign.sizing.line_friction import darcy_colebrook
from ngdesign.units.flow.pipe_segment import PipeSegmentSpecError
from ngdesign.units.flow.pipe_segment_r1 import (
    _validated,
    dP_fittings_Pa,
    node_terms,
)

#: Two-phase window on the molar vapour fraction (spec).
VF_MIN, VF_MAX = 0.001, 0.999

#: Segment-count cap for R2 (spec: no refinement; the N/2 check is reported).
R2_MAX_SEGMENTS = 200


class PipeSegmentR2Error(PipeSegmentSpecError):
    """Typed refusal for an R2 pipe-segment spec outside the level's validity."""


def _is_two_phase(state: StreamState) -> bool:
    return VF_MIN < state.vapor_fraction < VF_MAX


def _mass_quality(state: StreamState) -> float:
    """Vapour mass fraction (mass quality x) of a flashed state."""
    if not _is_two_phase(state):
        return 1.0 if state.vapor_fraction >= VF_MAX else 0.0
    m_total = sum(p.mole_fraction * p.molecular_weight for p in state.phases)
    m_vap = sum(
        p.mole_fraction * p.molecular_weight
        for p in state.phases
        if p.kind == PhaseKind.VAPOR
    )
    return m_vap / m_total


def _phase_of_kind(state: StreamState, kind: PhaseKind) -> Phase:
    return next(p for p in state.phases if p.kind == kind)


def _viscosity(phase: Phase, fallback: float) -> float:
    return float(phase.viscosity) if phase.viscosity is not None else fallback


def _node_gradient(
    P: float,
    state: StreamState,
    mdot: float,
    D: float,
    eps: float,
    angle_deg: float,
    h: float,
    mu_fallback: float,
    sigma: float | None,
) -> tuple[float, float, float]:
    """Pressure-drop gradient (Pa/m) at a node, positive for a drop.

    Returns ``(gradient, darcy_friction_part, darcy_gravity_part)``. For a
    two-phase node the whole Beggs-Brill segment dP is booked as friction
    (fluids returns only the total) and the gravity part is zero.
    """
    if _is_two_phase(state):
        if sigma is None:
            raise PipeSegmentR2Error(
                "sigma_N_m is required when any node is two-phase (the Thermo "
                "protocol has no surface tension)"
            )
        liq = _phase_of_kind(state, PhaseKind.HC_LIQUID)
        vap = _phase_of_kind(state, PhaseKind.VAPOR)
        try:
            dP_seg = Beggs_Brill(
                m=mdot,
                x=_mass_quality(state),
                rhol=liq.density,
                rhog=vap.density,
                mul=_viscosity(liq, mu_fallback),
                mug=_viscosity(vap, mu_fallback),
                sigma=sigma,
                P=P,
                D=D,
                angle=angle_deg,
                roughness=eps,
                L=h,
                acceleration=True,
            )
        except ValueError as exc:
            raise PipeSegmentR2Error(
                f"Beggs-Brill regime map failed at P = {P} Pa: {exc}"
            ) from exc
        return dP_seg / h, dP_seg / h, 0.0
    dominant = max(state.phases, key=lambda p: p.mole_fraction)
    rho = dominant.density
    fric, grav = node_terms(
        rho,
        _viscosity(dominant, mu_fallback),
        mdot,
        D,
        eps,
        math.sin(math.radians(angle_deg)),
    )
    return fric + grav, fric, grav


def _r2_march(
    P_in: float,
    L: float,
    D: float,
    dz: float,
    eps: float,
    mdot: float,
    flash: Any,
    mu_fallback: float,
    sigma: float | None,
    n: int,
) -> dict[str, Any]:
    """One fixed-N Heun march; returns P_out, the node states, and the splits."""
    if n < 1:
        raise PipeSegmentSpecError(f"n_segments {n} must be >= 1")
    angle_deg = math.degrees(math.asin(dz / L))
    h = L / n
    P = P_in
    states: list[StreamState] = [flash(P)]
    dP_friction = 0.0
    dP_hydro = 0.0
    n_bb = 0
    for _ in range(n):
        grad1, f1, g1 = _node_gradient(
            P, states[-1], mdot, D, eps, angle_deg, h, mu_fallback, sigma
        )
        k1 = -grad1
        P_star = P + h * k1
        if P_star <= 0:
            raise PipeSegmentR2Error(
                f"pressure falls to zero along the segment (predictor {P_star} Pa)"
            )
        s_star = flash(P_star)
        grad2, f2, g2 = _node_gradient(
            P_star, s_star, mdot, D, eps, angle_deg, h, mu_fallback, sigma
        )
        k2 = -grad2
        P = P + h * (k1 + k2) / 2
        if P <= 0:
            raise PipeSegmentR2Error(
                f"pressure falls to zero along the segment (corrector {P} Pa)"
            )
        states.append(flash(P))
        dP_friction += h * (f1 + f2) / 2
        dP_hydro += h * (g1 + g2) / 2
        if _is_two_phase(states[-2]) or _is_two_phase(s_star):
            n_bb += 1
    return {
        "P_out": P,
        "states": states,
        "dP_friction": dP_friction,
        "dP_hydro": dP_hydro,
        "n_bb": n_bb,
        "h": h,
    }


class PipeSegmentR2:
    """Two-phase Beggs-Brill pipe segment with a profile (level R2).

    Same validation and refusals as R1, except a two-phase inlet is allowed
    and every two-phase node requires ``sigma_N_m``. Fixed N with a reported
    N/2 check; no auto-refinement.
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
        L_m, D_m, eps, K, dz, n = _validated(params, n_default=20, n_max=R2_MAX_SEGMENTS)
        if inlet.molar_flow <= 0:
            raise PipeSegmentSpecError(
                f"molar_flow {inlet.molar_flow} mol/s must be > 0 (darcy_colebrook needs Q > 0)"
            )
        dominant = max(inlet.phases, key=lambda p: p.mole_fraction)
        mu_in = dominant.viscosity if dominant.viscosity is not None else params.get("mu_Pa_s")
        if mu_in is None:
            raise PipeSegmentSpecError("mu_Pa_s is required: the thermo gives no phase viscosity")
        mu_in = float(mu_in)
        sigma = params.get("sigma_N_m")
        if sigma is not None:
            sigma = float(sigma)
            if sigma <= 0:
                raise PipeSegmentR2Error(f"sigma_N_m {sigma} N/m must be > 0")

        mdot = inlet.mass_flow
        rho_in = dominant.density
        inlet_friction = darcy_colebrook(
            Q_m3_s=mdot / rho_in,
            D_m=D_m,
            rho=rho_in,
            mu=mu_in,
            roughness_m=eps,
            L_m=1.0,
        )
        dP_K = dP_fittings_Pa(K, D_m, mdot, rho_in)

        z = dict(inlet.composition)
        h_in = inlet.enthalpy
        molar_flow = inlet.molar_flow

        def flash(P: float) -> StreamState:
            return thermo.flash_ph(z, P, h_in, molar_flow)

        result = _r2_march(
            inlet.P - dP_K, L_m, D_m, dz, eps, mdot, flash, mu_in, sigma, n
        )
        P_out = result["P_out"]
        # One extra pass at N/2 so the discretisation error is visible.
        if n >= 2:
            half = _r2_march(
                inlet.P - dP_K, L_m, D_m, dz, eps, mdot, flash, mu_in, sigma, n // 2
            )
            P_half = half["P_out"]
        else:
            P_half = inlet.P - dP_K
        outlet = flash(P_out)

        info: dict[str, float] = {
            "dP_friction_Pa": result["dP_friction"],
            "dP_fittings_Pa": dP_K,
            "hydrostatic_Pa": result["dP_hydro"],
            "dP_total_Pa": result["dP_friction"] + dP_K + result["dP_hydro"],
            "velocity_in_m_s": inlet_friction["velocity_m_s"],
            "Re_in": inlet_friction["Re"],
            "darcy_f_in": inlet_friction["darcy_f"],
            "n_segments_used": float(n),
            "n_two_phase_segments": float(result["n_bb"]),
            "dP_check_N_half_Pa": P_out - P_half,
            "dT_K": outlet.T - inlet.T,
        }
        for i, s in enumerate(result["states"]):
            pad = f"{i:03d}"
            info[f"profile_{pad}_x_m"] = i * result["h"]
            info[f"profile_{pad}_P_Pa"] = s.P
            info[f"profile_{pad}_T_K"] = s.T
            info[f"profile_{pad}_quality"] = _mass_quality(s)
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A propane/n-pentane line that flashes part-way along 300 m of 4 in. pipe."""
        feed = {
            "T": 340.0,
            "P": 2.0e6,
            "molar_flow": 100.0,
            "composition": {"C3": 0.5, "nC5": 0.5},
        }
        return {"inlet": feed}, {"L_m": 300.0, "D_m": 0.1023, "sigma_N_m": 0.01}
