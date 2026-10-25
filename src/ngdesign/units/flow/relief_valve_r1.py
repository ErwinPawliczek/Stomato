"""U-R1 omega-method extensions to the relief valve unit (API 520 Pt I 10th ed. 2020 Annex C).

Rounds out U-R0's gas-only sizing with Leung's homogeneous-equilibrium omega
method for two-phase and subcooled-liquid inlets, delegating gas inlets to
U-R0 unchanged. Equations per API 520 Part I (10th ed., 2020) Annex C, which
adopts Leung, AIChE J. 32(10):1743-1746 (1986) for two-phase flow and Leung,
Chem. Eng. Prog. 92(12):28-50 (1996) for subcooled liquid.

Refusals follow the repo policy: impossible inputs raise the unit's typed
error with a concrete message (omega <= 0, failed root-finds); conservation
and flash errors surface as raised. Boundaries are closed: an inlet whose
bubble point reaches the relieving pressure is the saturated two-phase case;
a back pressure exactly at the critical ratio is critical; `P_back` outside
(0, P0) is refused.
"""

from __future__ import annotations

import math
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.relief_valve import (
    IN2_PER_M2,
    ReliefValve,
    ReliefValveSpecError,
    _next_orifice,
)

MM2_PER_M2 = 1.0e6


class ReliefValveR1Error(ReliefValveSpecError):
    """Typed refusal for the U-R1 omega-method extension."""


# --- omega-method closed forms (Annex C eqs. 1-4) ----------------------------


def omega_two_phase(v0: float, v9: float) -> float:
    """omega = 9 (v9/v0 - 1), Annex C eq. 1, from inlet volume v0 and flashed v9."""
    if v0 <= 0:
        raise ReliefValveR1Error(f"inlet specific volume must be positive, got {v0!r}")
    if v9 <= 0:
        raise ReliefValveR1Error(f"flashed specific volume must be positive, got {v9!r}")
    omega = 9.0 * (v9 / v0 - 1.0)
    if omega <= 0:
        raise ReliefValveR1Error(f"omega must be positive, got {omega!r}")
    return omega


def _eta_c_residual(omega: float, eta: float) -> float:
    """Annex C eq. 2 left-hand side: eta^2 + (w^2-2w)(1-eta)^2 + 2w^2 ln(eta) + 2w^2(1-eta)."""
    return (
        eta**2
        + (omega**2 - 2.0 * omega) * (1.0 - eta) ** 2
        + 2.0 * omega**2 * math.log(eta)
        + 2.0 * omega**2 * (1.0 - eta)
    )


def eta_c(omega: float) -> float:
    """Critical pressure ratio of Annex C eq. 2, brentq on (1e-9, 1-1e-12), xtol 1e-14.

    Refusals: omega <= 0 raises before the root-find; a failed root-find is a
    typed error, never a scipy ValueError.
    """
    if omega <= 0:
        raise ReliefValveR1Error(f"omega must be positive, got {omega!r}")
    try:
        return brentq(
            lambda eta: _eta_c_residual(omega, eta),
            1e-9,
            1.0 - 1e-12,
            xtol=1e-14,
            maxiter=200,
        )
    except ValueError as e:
        raise ReliefValveR1Error(f"critical pressure ratio did not converge: {e}") from e


def eta_c_leung_fit(omega: float) -> float:
    """Leung's explicit fit for eta_c (test cross-check only, ~1e-3 accurate)."""
    if omega <= 0:
        raise ReliefValveR1Error(f"omega must be positive, got {omega!r}")
    return (1.0 + (1.0446 - 0.0093431 * math.sqrt(omega)) * omega ** (-0.56261)) ** (
        -0.70356 + 0.014685 * math.log(omega)
    )


def G_two_phase(P0: float, v0: float, omega: float, eta_a: float) -> tuple[float, int]:
    """Mass flux of Annex C eq. 3 with the choke check, (kg/(m2 s), critical flag).

    Critical (Pa/P0 <= eta_c): G = eta_c sqrt(P0/(v0 omega)); subcritical:
    G = sqrt(-2[omega ln(eta_a) + (omega-1)(1-eta_a)]) sqrt(P0/v0)
      / (omega(1/eta_a - 1) + 1).
    """
    ec = eta_c(omega)
    if eta_a <= ec:
        return ec * math.sqrt(P0 / (v0 * omega)), 1
    G = (
        math.sqrt(-2.0 * (omega * math.log(eta_a) + (omega - 1.0) * (1.0 - eta_a)))
        * math.sqrt(P0 / v0)
        / (omega * (1.0 / eta_a - 1.0) + 1.0)
    )
    return G, 0


def area_m2(
    W: float, G: float, Kd: float, Kb: float = 1.0, Kc: float = 1.0, Kv: float = 1.0, Kw: float = 1.0
) -> float:
    """Required area A = W/(Kd Kb Kc Kv Kw G), m2 (Annex C eq. 5)."""
    return W / (Kd * Kb * Kc * Kv * Kw * G)


def eta_st_subcooled(omega_s: float) -> float:
    """Subcooling transition 2 omega_s/(1 + 2 omega_s)."""
    return 2.0 * omega_s / (1.0 + 2.0 * omega_s)


def _eta_c_subcooled_residual(omega_s: float, eta_s: float, eta: float) -> float:
    """Annex C eq. 4 (low subcooling) left-hand side."""
    a = (omega_s + 1.0 / omega_s - 2.0) / (2.0 * eta_s)
    return (
        a * eta**2
        - 2.0 * (omega_s - 1.0) * eta
        + omega_s * eta_s * math.log(eta / eta_s)
        + 1.5 * omega_s * eta_s
        - 1.0
    )


def eta_c_subcooled_low(omega_s: float, eta_s: float) -> float:
    """Critical ratio for low subcooling (eta_s >= eta_st), brentq on (1e-9, eta_s(1-1e-12)).

    At eta_s = 1 this equation divided by 2 omega equals eq. 2 (checked
    algebraically and numerically in the spec), so the saturated boundary
    carries the same root and flux as the saturated two-phase form.
    """
    if omega_s <= 0:
        raise ReliefValveR1Error(f"omega_s must be positive, got {omega_s!r}")
    if not 0 < eta_s <= 1:
        raise ReliefValveR1Error(f"eta_s must be in (0, 1], got {eta_s!r}")
    try:
        return brentq(
            lambda eta: _eta_c_subcooled_residual(omega_s, eta_s, eta),
            1e-9,
            eta_s * (1.0 - 1e-12),
            xtol=1e-14,
            maxiter=200,
        )
    except ValueError as e:
        raise ReliefValveR1Error(
            f"critical pressure ratio did not converge: {e}"
        ) from e


def G_subcooled(
    P0: float, rho_l0: float, omega_s: float, eta_s: float, P_a: float
) -> tuple[float, int, int]:
    """Subcooled/liquid flux selection of Annex C eq. 4, (kg/(m2 s), regime, critical).

    Regimes: 2 = low subcooling (eta_s >= eta_st), choked at eta_c of eq. 4
    when Pa/P0 < eta_c, else subcritical at eta_a; 3 = high subcooling
    (eta_s < eta_st) with Pa < Ps, choked at the saturation pressure
    G = sqrt(2 rho_l0 (P0 - Ps)); 4 = high subcooling with Pa >= Ps, all-liquid
    non-flashing G = sqrt(2 rho_l0 (P0 - Pa)) — the API 520 Part I liquid
    equation in SI (its 11.78 constant is this expression with unit
    conversions).
    """
    if omega_s <= 0:
        raise ReliefValveR1Error(f"omega_s must be positive, got {omega_s!r}")
    if rho_l0 <= 0:
        raise ReliefValveR1Error(f"liquid density must be positive, got {rho_l0!r}")
    P_sat = eta_s * P0
    eta_a = P_a / P0
    if eta_s < eta_st_subcooled(omega_s):
        if P_a < P_sat:
            return math.sqrt(2.0 * rho_l0 * (P0 - P_sat)), 3, 1
        return math.sqrt(2.0 * rho_l0 * (P0 - P_a)), 4, 0
    ec = eta_c_subcooled_low(omega_s, eta_s)
    if eta_a < ec:
        eta = ec
        critical = 1
    else:
        eta = eta_a
        critical = 0
    G = (
        math.sqrt(
            2.0 * (1.0 - eta_s)
            + 2.0
            * (
                omega_s * eta_s * math.log(eta_s / eta)
                - (omega_s - 1.0) * (eta_s - eta)
            )
        )
        * math.sqrt(P0 * rho_l0)
        / (omega_s * (eta_s / eta - 1.0) + 1.0)
    )
    return G, 2, critical


def mixture_v(stream: StreamState) -> float:
    """Mass-weighted mixture specific volume over the stream's own phases, m3/kg."""
    masses = [p.mole_fraction * p.molecular_weight / 1000.0 for p in stream.phases]
    total = sum(masses)
    if total <= 0:
        raise ReliefValveR1Error("stream carries no mass")
    v = sum(m / p.density for m, p in zip(masses, stream.phases, strict=True)) / total
    if v <= 0:
        raise ReliefValveR1Error(f"mixture specific volume must be positive, got {v!r}")
    return v


# --- adapter -----------------------------------------------------------------


class ReliefValveR1(ReliefValve):
    """U-R1: omega-method two-phase and subcooled sizing, gas inlets as U-R0."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, Any], dict[str, Any]]:
        """A two-phase propane/n-butane basis at 20 % vapour fraction."""
        feeds = {
            "inlet": {
                "composition": {"C3": 0.5, "nC4": 0.5},
                "molar_flow": 100.0,
                "vapour_fraction": 0.2,
                "P": 2.0e6,
            }
        }
        params: dict[str, Any] = {"P_back": 6.0e5}
        return feeds, params

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """Required area and the isenthalpic outlet, per the U-R1 spec.

        An all-vapour inlet gives exactly U-R0's result with regime_code 0; a
        two-phase or saturated inlet sizes by the omega method (regime 1); a
        liquid inlet sizes by the subcooled selection (regimes 2-4).
        """
        inlet = self._inlet(inlets)
        P0 = inlet.P
        z = dict(inlet.mole_fractions)

        P_back = params.get("P_back")
        if P_back is None:
            raise ReliefValveSpecError("params must include P_back (Pa)")
        if not isinstance(P_back, (int, float)):
            raise ReliefValveSpecError(f"P_back must be numeric, got {type(P_back)}")
        P_back = float(P_back)
        if not 0 < P_back < P0:
            raise ReliefValveSpecError(
                f"P_back must be in (0, P0) = (0, {P0!r}), got {P_back!r}"
            )

        phases = [p for p in inlet.phases if p.kind is not PhaseKind.AQUEOUS]
        all_vapour = len(phases) == 1 and phases[0].kind is PhaseKind.VAPOR
        if all_vapour:
            return self._solve_gas(inlets, params, thermo)

        vf = inlet.vapor_fraction
        if vf is None:
            vf = 0.0 if not any(p.kind is PhaseKind.VAPOR for p in phases) else 0.5

        if vf <= 0.001:
            rho_l0 = thermo.liquid_density(z, inlet.T, P0)
            P_sat = thermo.bubble_point(z, T=inlet.T).P
            if P_sat >= P0 * (1.0 - 1e-9):
                # saturated liquid: handled as two-phase with v0 = 1/rho_l0
                return self._solve_two_phase(
                    inlets, params, thermo, v0_override=1.0 / rho_l0,
                    extra_info={"P_sat_Pa": P_sat},
                )
            return self._solve_subcooled(
                inlets, params, thermo, rho_l0=rho_l0, P_sat=P_sat
            )
        return self._solve_two_phase(inlets, params, thermo)

    # -- helpers --------------------------------------------------------------

    def _inlet(self, inlets: dict[str, StreamState]) -> StreamState:
        if set(inlets) != {"inlet"} or not isinstance(inlets.get("inlet"), StreamState):
            raise ReliefValveSpecError("expected exactly one inlet, 'inlet'")
        return inlets["inlet"]

    def _solve_gas(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        """All-vapour inlet: delegate to R0 with R0's own params only."""
        r0_params: dict[str, Any] = {
            k: params[k] for k in ("P_back", "Kd", "Kc") if k in params
        }
        result = ReliefValve().solve(inlets, r0_params, thermo)
        result.info["regime_code"] = 0
        return result

    def _factors(self, params: dict[str, Any], kd_default: float) -> dict[str, float]:
        """Correction factors with regime-chosen Kd; every factor in (0, 1]."""
        factors: dict[str, float] = {}
        for key, default in (
            ("Kd", kd_default),
            ("Kb", 1.0),
            ("Kc", 1.0),
            ("Kv", 1.0),
            ("Kw", 1.0),
        ):
            val = params.get(key)
            if val is None:
                factors[key] = default
            else:
                if not isinstance(val, (int, float)) or not 0 < val <= 1:
                    raise ReliefValveSpecError(
                        f"{key} must be a correction factor in (0, 1], got {val!r}"
                    )
                factors[key] = float(val)
        return factors

    def _solve_two_phase(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
        v0_override: float | None = None,
        extra_info: dict[str, Any] | None = None,
    ) -> UnitResult:
        inlet = self._inlet(inlets)
        P0 = inlet.P
        z = dict(inlet.mole_fractions)
        factors = self._factors(params, kd_default=0.85)

        v0 = mixture_v(inlet) if v0_override is None else v0_override
        flashed = thermo.flash_ps(z, 0.9 * P0, inlet.entropy, inlet.molar_flow)
        omega = omega_two_phase(v0, mixture_v(flashed))
        G, critical = G_two_phase(P0, v0, omega, params["P_back"] / P0)
        return self._package(
            inlet, factors, G, regime_code=1, critical=critical, omega=omega,
            eta_c_value=eta_c(omega), v0=v0, extra_info=extra_info or {},
            thermo=thermo, params=params,
        )

    def _solve_subcooled(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
        rho_l0: float,
        P_sat: float,
    ) -> UnitResult:
        inlet = self._inlet(inlets)
        P0 = inlet.P
        z = dict(inlet.mole_fractions)
        factors = self._factors(params, kd_default=0.65)

        s_sat = thermo.flash_tvf(z, inlet.T, 0.0, inlet.molar_flow).entropy
        flashed = thermo.flash_ps(z, 0.9 * P_sat, s_sat, inlet.molar_flow)
        rho9 = 1.0 / mixture_v(flashed)
        omega_s = 9.0 * (rho_l0 / rho9 - 1.0)
        if omega_s <= 0:
            raise ReliefValveR1Error(f"omega_s must be positive, got {omega_s!r}")
        eta_s = P_sat / P0
        G, regime_code, critical = G_subcooled(P0, rho_l0, omega_s, eta_s, params["P_back"])
        ec: float | None = None
        if regime_code == 2:
            ec = eta_c_subcooled_low(omega_s, eta_s)
        return self._package(
            inlet, factors, G, regime_code=regime_code, critical=critical,
            omega=omega_s, eta_c_value=ec, v0=1.0 / rho_l0,
            extra_info={"P_sat_Pa": P_sat}, thermo=thermo, params=params,
        )

    def _package(
        self,
        inlet: StreamState,
        factors: dict[str, float],
        G: float,
        regime_code: int,
        critical: int,
        omega: float,
        eta_c_value: float | None,
        v0: float,
        extra_info: dict[str, Any],
        thermo: Thermo,
        params: dict[str, Any],
    ) -> UnitResult:
        area = area_m2(
            inlet.mass_flow, G, factors["Kd"], factors["Kb"], factors["Kc"],
            factors["Kv"], factors["Kw"],
        )
        _, area_in2 = _next_orifice(area / IN2_PER_M2)
        z = dict(inlet.mole_fractions)
        info: dict[str, Any] = {
            **extra_info,
            "regime_code": regime_code,
            "omega": omega,
            "eta_c": eta_c_value,
            "critical": critical,
            "G_kg_m2s": G,
            "required_area_m2": area,
            "required_area_mm2": area * MM2_PER_M2,
            "required_area_in2": area / IN2_PER_M2,
            "selected_orifice_area_in2": area_in2,
            "Kd_used": factors["Kd"],
            "v0_m3_kg": v0,
        }
        outlet = thermo.flash_ph(z, params["P_back"], inlet.enthalpy, inlet.molar_flow)
        return UnitResult(outlets={"outlet": outlet}, info=info)
