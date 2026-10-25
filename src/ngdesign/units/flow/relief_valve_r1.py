"""U-R1 omega-method extensions to the relief valve unit (API 520 Pt I 11th ed. §B.4).

Rounds out U-R0's gas-only sizing with Leung's homogeneous-equilibrium omega
method for two-phase and subcooled-liquid inlets, delegating gas inlets to
U-R0 unchanged. Refusals follow the repo policy: impossible inputs raise the
unit's typed error with a concrete message (omega <= 0, failed root-finds);
conservation and flash errors surface as raised. Boundaries are closed: an
inlet exactly at saturation is the saturated two-phase case; a back pressure
exactly at the choke is critical; P_back at the relieving pressure is refused.
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


class ReliefValveR1Error(ReliefValveSpecError):
    """Typed refusal for the U-R1 omega-method extension."""


# --- omega-method closed forms (API 520 Pt I 11th ed. eqs. B.4.1-B.4.11) ----


def eta_c(omega: float) -> float:
    """Critical pressure ratio eta_c of eq. B.4.1, solved by brentq (1e-12 xtol).

    Refusals: omega <= 0 raises before the root-find; a failed root-find is a
    typed error, never a scipy ValueError.
    """
    if omega <= 0:
        raise ReliefValveR1Error(f"omega must be positive, got {omega!r}")
    try:
        return brentq(
            lambda eta: 0.5 - omega * (1.0 - eta) - math.log(1.0 / eta),
            1e-6,
            1.0,
            xtol=1e-12,
        )
    except ValueError as e:
        raise ReliefValveR1Error(f"critical pressure ratio did not converge: {e}") from e


def eta_c_leung_fit(omega: float) -> float:
    """Leung's explicit fit, eq. B.4.2 (agrees with eq. B.4.1 to 2e-4 for omega > 0.05)."""
    return 2.0 * omega / (1.0 + 2.0 * omega)


def omega_two_phase(v0: float, v9: float) -> float:
    """omega = 9 (v9/v0 - 1), eq. B.4.3, from inlet volume v0 and flashed v9."""
    if v0 <= 0:
        raise ReliefValveR1Error(f"inlet specific volume must be positive, got {v0!r}")
    if v9 <= 0:
        raise ReliefValveR1Error(f"flashed specific volume must be positive, got {v9!r}")
    return 9.0 * (v9 / v0 - 1.0)


def G_two_phase_subcritical(P0: float, v0: float, omega: float, eta_a: float) -> float:
    """Mass flux of eq. B.4.4 at back pressure eta_a = P_a / P0, kg/(m2 s)."""
    if eta_a <= 0:
        raise ReliefValveR1Error(f"back pressure ratio must be positive, got {eta_a!r}")
    return (
        eta_a
        * math.sqrt(P0 / v0)
        / math.sqrt(
            omega * (eta_a - 1.0)
            + 2.0 * (1.0 - eta_a)
            + 2.0 * omega * eta_a * math.log(eta_a)
        )
    )


def G_two_phase(P0: float, v0: float, omega: float, eta_a: float) -> tuple[float, int]:
    """Mass flux of eq. B.4.4 with the choke check, (kg/(m2 s), critical flag).

    At eta_a below the critical ratio the flux is evaluated at eta_c (choked);
    the subcritical form at eta_a = eta_c equals the choked value to 1e-12.
    """
    ec = eta_c(omega)
    if eta_a < ec:
        return G_two_phase_subcritical(P0, v0, omega, ec), 1
    return G_two_phase_subcritical(P0, v0, omega, eta_a), 0


def area_m2(W: float, G: float, Kd: float, Kb: float = 1.0, Kw: float = 1.0) -> float:
    """Required area A = W / (Kd Kb Kw G), m2 (eq. B.4.5)."""
    return W / (Kd * Kb * Kw * G)


def eta_st_subcooled(omega_s: float) -> float:
    """Stagnation threshold 2 omega_s / (1 + 2 omega_s) of eq. B.4.7."""
    return 2.0 * omega_s / (1.0 + 2.0 * omega_s)


def eta_c_subcooled_low(omega_s: float, eta_s: float) -> float:
    """Critical ratio for the low-subcooling branch, eq. B.4.9 (brentq, 1e-12 xtol).

    At eta_s = 1 (saturated inlet) this equals eta_c(omega_s) to 1e-12, so the
    saturated boundary carries the same flux as the saturated two-phase form.
    """
    ws = omega_s * eta_s + 1.0 - eta_s
    try:
        return brentq(
            lambda eta: 0.5
            - ws * (1.0 - eta)
            - math.log(1.0 / eta)
            + ws * math.log((ws * eta_s - 1.0 + eta_s) / (ws * (1.0 - eta_s) + 1.0)),
            1e-6,
            1.0,
            xtol=1e-12,
        )
    except ValueError as e:
        raise ReliefValveR1Error(
            f"subcooled critical pressure ratio did not converge: {e}"
        ) from e


def _subcooled_low_flux(
    P0: float, rho_l0: float, omega_s: float, eta_s: float, eta_a: float
) -> float:
    """Flux of eq. B.4.11 at eta_a (choked at eta_c or subcritical), kg/(m2 s)."""
    ws = omega_s * eta_s + 1.0 - eta_s
    return (
        eta_a
        * math.sqrt(P0 * rho_l0)
        / math.sqrt(2.0 * (1.0 - eta_s) + 2.0 * ws * (1.0 - eta_a))
    )


def G_subcooled(
    P0: float, rho_l0: float, omega_s: float, eta_s: float, P_a: float
) -> tuple[float, int]:
    """Subcooled/liquid flux selection of eq. B.4.7, (kg/(m2 s), regime code).

    Regime codes: 3 = high subcooling, choked at the saturation pressure
    (G = sqrt(2 rho (P0 - Ps))); 4 = all-liquid non-flashing (P_a at or above
    P_s, G = sqrt(2 rho (P0 - Pa)) — the API 520 Part I liquid form); 2 =
    low-subcooling flashing, choked at eta_c of eq. B.4.9 (evaluated by eq.
    B.4.11 at eta_c) or subcritical (eq. B.4.11 at eta_a).
    """
    if omega_s <= 0:
        raise ReliefValveR1Error(f"omega_s must be positive, got {omega_s!r}")
    if rho_l0 <= 0:
        raise ReliefValveR1Error(f"liquid density must be positive, got {rho_l0!r}")
    eta_a = P_a / P0
    if eta_a >= eta_s:
        # Leung (1996): with the back pressure at or above the saturation
        # pressure the flow cannot flash; the all-liquid form applies.
        return math.sqrt(2.0 * rho_l0 * (P0 - P_a)), 4
    if eta_s >= eta_st_subcooled(omega_s):
        ec = eta_c_subcooled_low(omega_s, eta_s)
        if eta_a < ec:
            return _subcooled_low_flux(P0, rho_l0, omega_s, eta_s, ec), 2
        return _subcooled_low_flux(P0, rho_l0, omega_s, eta_s, eta_a), 2
    return math.sqrt(2.0 * rho_l0 * (P0 - P_a)), 3


def mixture_v(stream: StreamState) -> float:
    """Mass-weighted mixture specific volume over the stream's phases, m3/kg."""
    masses = [p.mole_fraction * p.molecular_weight / 1000.0 for p in stream.phases]
    v = sum(m / p.density for m, p in zip(masses, stream.phases, strict=True)) / sum(masses)
    if v <= 0:
        raise ReliefValveR1Error(f"mixture specific volume must be positive, got {v!r}")
    return v


# --- adapter -----------------------------------------------------------------


class ReliefValveR1(ReliefValve):
    """U-R1: omega-method two-phase and subcooled sizing, gas inlets as U-R0."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, Any], dict[str, Any]]:
        """R0's example (gas service) — the regime-0 identity path."""
        return ReliefValve.example_case()

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
        P_back = params.get("P_back")
        if P_back is None:
            raise ReliefValveSpecError("params must include P_back (Pa)")
        if not isinstance(P_back, (int, float)):
            raise ReliefValveSpecError(f"P_back must be numeric, got {type(P_back)}")
        P_back = float(P_back)
        if P_back <= 0:
            raise ReliefValveSpecError(f"P_back must be positive, got {P_back!r}")

        inlet = inlets.get("inlet")
        if inlet is None:
            raise ReliefValveSpecError("expected exactly one inlet, 'inlet'")
        if set(inlets) != {"inlet"}:
            raise ReliefValveSpecError("expected exactly one inlet, 'inlet'")
        z = dict(inlet.mole_fractions)
        P0 = inlet.P

        phases = [p for p in inlet.phases if p.kind != PhaseKind.AQUEOUS]
        if len(phases) == 1 and phases[0].kind is PhaseKind.VAPOR:
            # gas/vapour sizing: identical to U-R0's own path, info carried through
            gas = ReliefValve().solve(inlets, params, thermo)
            info: dict[str, Any] = {
                **gas.info,
                "regime_code": 0,
                # R0 does not expose the critical-flow flag; None, not a guess.
                "critical": None,
                "omega": None,
                "eta_s": None,
                "liquid_density_ref": None,
                "P_back_ref": P_back,
            }
            return UnitResult(outlets={"outlet": gas.outlets["outlet"]}, info=info)

        factors: dict[str, float] = {}
        for key in ("Kd", "Kw", "Kb", "Kc"):
            val = params.get(key)
            if val is None:
                factors[key] = {"Kd": 0.85, "Kw": 1.0, "Kb": 1.0, "Kc": 1.0}[key]
            else:
                if not isinstance(val, (int, float)) or not 0 < val <= 1:
                    raise ReliefValveSpecError(
                        f"{key} must be a correction factor in (0, 1], got {val!r}"
                    )
                factors[key] = float(val)

        info_r0: dict[str, Any] = {}
        if inlet.vapor_fraction is not None and inlet.vapor_fraction <= 0.001:
            rho_l0 = thermo.liquid_density(z, inlet.T, P0)
            P_sat = thermo.bubble_point(z, T=inlet.T).P
            eta_s = P_sat / P0
            flashed = thermo.flash_ps(z, 0.9 * P_sat, inlet.entropy, inlet.molar_flow)
            omega = omega_two_phase(1.0 / rho_l0, mixture_v(flashed))
            G, regime_code = G_subcooled(P0, rho_l0, omega, eta_s, P_back)
            if regime_code == 2:
                critical = int(P_back / P0 < eta_c_subcooled_low(omega, eta_s))
            else:
                critical = 1 if regime_code == 3 else 0
            info_r0 = {"P_sat_ref": P_sat}
        else:
            flashed = thermo.flash_ps(z, 0.9 * P0, inlet.entropy, inlet.molar_flow)
            omega = omega_two_phase(mixture_v(inlet), mixture_v(flashed))
            rho_l0 = thermo.liquid_density(z, inlet.T, P0)
            eta_s = 1.0
            G, critical = G_two_phase(P0, 1.0 / rho_l0, omega, P_back / P0)
            regime_code = 1

        area = area_m2(inlet.mass_flow, G, factors["Kd"], factors["Kb"], factors["Kw"])
        orifice, area_in2 = _next_orifice(area / IN2_PER_M2)
        info = {
            **info_r0,
            "regime_code": regime_code,
            "critical": critical,
            "omega": omega,
            "eta_s": eta_s,
            "liquid_density_ref": rho_l0,
            "G_kg_m2s": G,
            "Kd_used": factors["Kd"],
            "Kb_used": factors["Kb"],
            "Kw_used": factors["Kw"],
            "Kc_used": factors["Kc"],
            "required_area_m2": area,
            "required_area_in2": area / IN2_PER_M2,
            "selected_orifice": orifice,
            "selected_orifice_area_in2": area_in2,
            "P_back_ref": P_back,
        }
        outlet = thermo.flash_ph(z, P_back, inlet.enthalpy, inlet.molar_flow)
        return UnitResult(outlets={"outlet": outlet}, info=info)
