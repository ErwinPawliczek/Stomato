"""U-R2 line-loss and back-pressure checks around the relief valve (API 520 Pt I 11th ed. §5.6.4).

Wraps U-R1's sizing with the two API 520 Part I line-loss checks: the inlet
pressure loss must stay within 3 % of the set gauge pressure and, for
conventional and balanced-bellows valves, the total back pressure (superimposed
plus built-up) must stay within 10 % / 50 % of set gauge respectively. Inlet
and outlet line losses come from :func:`ngdesign.sizing.line_friction.darcy_colebrook`
— the repo's one owner for incompressible Colebrook friction — with a fixed
point on the outlet-line density when the relief flashing dominates the line.
Refusals follow the repo policy: impossible inputs raise the unit's typed
error with a concrete message; conservation and flash errors surface as
raised. Boundaries are closed: a loss exactly at the limit reads ok = 1.
"""

from __future__ import annotations

from typing import Any

from fluids.safety_valve import API520_B, API520_W

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.line_friction import darcy_colebrook
from ngdesign.units.flow.relief_valve import ReliefValveSpecError
from ngdesign.units.flow.relief_valve_r1 import ReliefValveR1, mixture_v


class ReliefValveR2Error(ReliefValveSpecError):
    """Typed refusal for the U-R2 line-loss check extension."""


def mcadams_viscosity(x_mass_vapor: float, mu_g: float, mu_l: float) -> float:
    """McAdams (1942) two-phase viscosity 1/mu = x/mu_g + (1-x)/mu_l, Pa s."""
    if not 0.0 <= x_mass_vapor <= 1.0:
        raise ReliefValveR2Error(f"mass vapour fraction must be in [0, 1], got {x_mass_vapor!r}")
    if mu_g <= 0 or mu_l <= 0:
        raise ReliefValveR2Error("phase viscosities must be positive")
    return 1.0 / (x_mass_vapor / mu_g + (1.0 - x_mass_vapor) / mu_l)


def _phase_viscosity(stream: StreamState, i: int, thermo: Thermo) -> float:
    """Viscosity of the stream's i-th phase, re-derived when the flash omits it."""
    phase = stream.phases[i]
    if phase.viscosity is not None:
        return phase.viscosity
    kind = phase.kind
    props = thermo.phase_props(
        dict(stream.mole_fractions), stream.T, stream.P, kind
    )
    if props.viscosity is None:
        raise ReliefValveR2Error(
            f"phase {i} ({kind.value}) carries no viscosity; the omega-method line "
            "losses cannot be evaluated"
        )
    return props.viscosity


def mixture_viscosity(stream: StreamState, thermo: Thermo) -> float:
    """Mass-weighted McAdams mixture viscosity over the stream's phases, Pa s."""
    masses = [p.mole_fraction * p.molecular_weight / 1000.0 for p in stream.phases]
    total = sum(masses)
    if total <= 0:
        raise ReliefValveR2Error("stream carries no mass")
    mu = 0.0
    for i, m in enumerate(masses):
        mu += m * 1.0 / _phase_viscosity(stream, i, thermo)
    return 1.0 / mu


def inlet_line_dP(
    W: float,
    rho: float,
    mu: float,
    D: float,
    L: float,
    eps: float,
    K: float,
) -> dict[str, float]:
    """Inlet line loss by the Darcy-Weisbach form of eq. 7, Pa.

    Delegates the Colebrook friction factor to the sizing layer's
    :func:`darcy_colebrook`; the returned dict carries velocity (m/s), Re, the
    Darcy f and dP.
    """
    if W <= 0:
        raise ReliefValveR2Error(f"mass flow must be positive, got {W!r}")
    if rho <= 0:
        raise ReliefValveR2Error(f"density must be positive, got {rho!r}")
    if mu <= 0:
        raise ReliefValveR2Error(f"viscosity must be positive, got {mu!r}")
    if D <= 0:
        raise ReliefValveR2Error(f"line diameter must be positive, got {D!r}")
    if L < 0:
        raise ReliefValveR2Error(f"line length must be non-negative, got {L!r}")
    if eps < 0:
        raise ReliefValveR2Error(f"roughness must be non-negative, got {eps!r}")
    if K < 0:
        raise ReliefValveR2Error(f"resistance coefficient must be non-negative, got {K!r}")
    return darcy_colebrook(W, rho, mu, D, L, eps, K)


def API520_W_10th(P1: float, P_set: float, P_b: float, op_const: float) -> float:
    """Built-up back-pressure correction Kw, Fig. 31 (fluids API520_W)."""
    return API520_W(P1, P_set, P_b, op_const)


def _dP_outlet_iteration_cap() -> int:
    """Maximum fixed-point iterations on the outlet-line density (50)."""
    return 50


class ReliefValveR2(ReliefValveR1):
    """U-R2: API 520 Part I inlet-loss and back-pressure checks around U-R1."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, Any], dict[str, Any]]:
        """R1's example with P_set at 90 % of the feed relieving pressure and
        one short line on each side."""
        feeds, params = ReliefValveR1.example_case()
        P_set = 0.9 * feeds["inlet"]["P"]
        return feeds, {
            **params,
            "P_set": P_set,
            "L_in_m": 1.0,
            "D_in_m": 0.1,
            "K_in": 0.5,
            "L_out_m": 5.0,
            "D_out_m": 0.15,
            "K_out": 1.0,
        }

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """R1's result plus the two line-loss checks, per the U-R2 spec."""
        P_set = params.get("P_set")
        if P_set is None:
            raise ReliefValveR2Error("params must include P_set (Pa)")
        if not isinstance(P_set, (int, float)):
            raise ReliefValveR2Error(f"P_set must be numeric, got {type(P_set)}")
        P_set = float(P_set)
        P_atm = 101325.0
        if P_set <= P_atm:
            raise ReliefValveR2Error(
                f"P_set must be above atmospheric, got {P_set!r}"
            )

        inlet = inlets.get("inlet")
        if inlet is None:
            raise ReliefValveR2Error("expected exactly one inlet, 'inlet'")
        if set(inlets) != {"inlet"}:
            raise ReliefValveR2Error("expected exactly one inlet, 'inlet'")
        if P_set > inlet.P:
            raise ReliefValveR2Error(
                f"P_set must be at or below the relieving pressure, got {P_set!r}"
            )

        valve_type = params.get("valve_type", "conventional")
        if valve_type not in ("conventional", "balanced_bellows", "pilot"):
            raise ReliefValveR2Error(
                f"valve_type must be 'conventional', 'balanced_bellows' or 'pilot', "
                f"got {valve_type!r}"
            )

        L_in = params.get("L_in_m", 0.0)
        L_out = params.get("L_out_m", 0.0)
        for name, val in (("L_in_m", L_in), ("L_out_m", L_out)):
            if not isinstance(val, (int, float)) or val < 0:
                raise ReliefValveR2Error(f"{name} must be non-negative, got {val!r}")
        D_in = params.get("D_in_m", 0.0)
        D_out = params.get("D_out_m", 0.0)
        for name, length, val in (
            ("D_in_m", L_in, D_in),
            ("D_out_m", L_out, D_out),
        ):
            if length > 0 and (not isinstance(val, (int, float)) or val <= 0):
                raise ReliefValveR2Error(
                    f"{name} must be positive when the line length is positive, got {val!r}"
                )
        K_in = params.get("K_in", 0.0)
        K_out = params.get("K_out", 0.0)
        for name, val in (("K_in", K_in), ("K_out", K_out)):
            if not isinstance(val, (int, float)) or val < 0:
                raise ReliefValveR2Error(f"{name} must be non-negative, got {val!r}")
        eps = params.get("roughness_m", 4.57e-5)
        if not isinstance(eps, (int, float)) or eps < 0:
            raise ReliefValveR2Error(f"roughness_m must be non-negative, got {eps!r}")
        eps_out = params.get("roughness_out_m", eps)
        if not isinstance(eps_out, (int, float)) or eps_out < 0:
            raise ReliefValveR2Error(
                f"roughness_out_m must be non-negative, got {eps_out!r}"
            )

        base = ReliefValveR1.solve(self, inlets, params, thermo)
        info: dict[str, Any] = dict(base.info)
        W = inlet.mass_flow

        # inlet loss at the inlet density (subcooled liquid: no flash in the inlet line)
        dP_inlet = 0.0
        if L_in > 0:
            mu_in = mixture_viscosity(inlet, thermo)
            rho_in = 1.0 / mixture_v(inlet)
            loss = inlet_line_dP(W, rho_in, mu_in, float(D_in), float(L_in), float(eps), float(K_in))
            dP_inlet = loss["dP_Pa"]
        inlet_frac = dP_inlet / (P_set - P_atm)
        info["dP_inlet_Pa"] = dP_inlet
        info["inlet_loss_frac"] = inlet_frac
        info["inlet_loss_ok"] = int(inlet_frac <= 0.03)

        # total back pressure = superimposed (given) + built-up (line loss from
        # the flash at the total pressure); pilot valves see no limit.
        P_back_super = base.info["P_back_ref"]
        dP_out = 0.0
        if L_out > 0:
            dP_out = self._builtup_dP(z=inlet.mole_fractions, W=W, inlets=inlets, thermo=thermo,
                                      P_target=P_back_super, D_out=float(D_out), L_out=float(L_out),
                                      eps_out=float(eps_out), K_out=float(K_out))
        P_back_total = P_back_super + dP_out
        set_gauge = P_set - P_atm
        info["P_back_total_Pa"] = P_back_total
        info["dP_builtup_Pa"] = dP_out
        info["backpressure_frac"] = (P_back_total - P_atm) / set_gauge

        if valve_type == "pilot":
            info["backpressure_ok"] = 1
        elif valve_type == "conventional":
            info["backpressure_ok"] = int(info["backpressure_frac"] <= 0.10)
            if info["backpressure_frac"] > 0.50:
                raise ReliefValveR2Error(
                    "back pressure exceeds 50 % of set gauge; a conventional valve cannot be sized"
                )
        else:  # balanced_bellows: Kb from Fig. 30 between 30 % and 50 %
            if info["backpressure_frac"] > 0.50:
                raise ReliefValveR2Error(
                    "balanced-bellows back pressure is at or above 50 % of set gauge; "
                    "fluids' Fig. 30 interpolation refuses to extrapolate"
                )
            kb = float(API520_B(P_set, P_back_total, 0.10))
            info["Kb_fig30"] = kb
            area_in2 = info["required_area_in2"] / kb
            info["area_with_backpressure_in2"] = area_in2
            from ngdesign.units.flow.relief_valve import _next_orifice

            orifice, area_sel = _next_orifice(area_in2)
            info["selected_orifice"] = orifice
            info["selected_orifice_area_in2"] = area_sel
            info["backpressure_ok"] = 1

        return UnitResult(outlets=base.outlets, info=info)

    def _builtup_dP(
        self,
        z: dict[str, float],
        W: float,
        inlets: dict[str, StreamState],
        thermo: Thermo,
        P_target: float,
        D_out: float,
        L_out: float,
        eps_out: float,
        K_out: float,
    ) -> float:
        """Built-up back pressure: fixed point on the outlet-line density.

        The line loss is evaluated at the density of the state flashing at
        ``P_super + dP``; iterated to 1e-8 relative or refused at 50 passes.
        """
        inlet = inlets["inlet"]
        dP = 0.0
        for _ in range(_dP_outlet_iteration_cap()):
            state = thermo.flash_ph(z, P_target + dP, inlet.enthalpy, inlet.molar_flow)
            if any(p.kind is PhaseKind.AQUEOUS for p in state.phases):
                raise ReliefValveR2Error("aqueous phase in the outlet line is not supported")
            rho = 1.0 / mixture_v(state)
            mu = mixture_viscosity(state, thermo)
            loss = inlet_line_dP(W, rho, mu, D_out, L_out, eps_out, K_out)
            if abs(loss["dP_Pa"] - dP) <= 1e-8 * max(1.0, abs(dP)):
                return loss["dP_Pa"]
            dP = loss["dP_Pa"]
        raise ReliefValveR2Error(
            "outlet-line back-pressure iteration did not converge within 50 passes"
        )
