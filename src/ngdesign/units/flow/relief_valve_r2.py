"""U-R2 line-loss and back-pressure checks around the relief valve (API 520 Pt I 10th ed. 2020).

Wraps U-R1's sizing with the API 520 checks: rated capacity (A proportional to
W at a fixed relieving state), the inlet line loss against the 3 % rule
(API 520 Part II 2015 §7.3.6, API 521), and the built-up back pressure with
the conventional / balanced-bellows / pilot limits of API 520 Part I §5.3.3.
Line losses come from :func:`ngdesign.sizing.line_friction.darcy_colebrook`
(the repo's one owner for incompressible Colebrook friction) plus the caller's
Sigma-K form term; the discharge-line density is iterated at the line's mean
pressure, where a failed flash is a typed refusal naming the pressure.
Refusals follow the repo policy: impossible inputs raise the unit's typed
error with a concrete message. Boundaries are closed: a loss exactly at the
limit reads ok = 1.
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

    def __init__(self, message: str) -> None:
        super().__init__(message)


def mcadams_viscosity(x_mass_vapor: float, mu_g: float, mu_l: float) -> float:
    """McAdams, Woods & Heroman (1942) two-phase viscosity 1/mu = x/mu_g + (1-x)/mu_l, Pa s."""
    if not 0.0 <= x_mass_vapor <= 1.0:
        raise ReliefValveR2Error(f"vapour mass fraction must be in [0, 1], got {x_mass_vapor!r}")
    if mu_g <= 0 or mu_l <= 0:
        raise ReliefValveR2Error("phase viscosities must be positive")
    return 1.0 / (x_mass_vapor / mu_g + (1.0 - x_mass_vapor) / mu_l)


def _phase_viscosity(stream: StreamState, i: int, thermo: Thermo) -> float:
    """Viscosity of the stream's i-th phase, re-derived when the flash omits it."""
    phase = stream.phases[i]
    if phase.viscosity is not None:
        return phase.viscosity
    props = thermo.phase_props(dict(stream.composition), stream.T, stream.P, phase.kind)
    if props.viscosity is None:
        raise ReliefValveR2Error(
            f"phase {i} ({phase.kind.value}) carries no viscosity; the line loss cannot be evaluated"
        )
    return props.viscosity


def mixture_viscosity(stream: StreamState, thermo: Thermo) -> float:
    """Inlet viscosity for the line loss: the single phase's, else the McAdams form."""
    if len(stream.phases) == 1:
        return _phase_viscosity(stream, 0, thermo)
    masses = [p.mole_fraction * p.molecular_weight / 1000.0 for p in stream.phases]
    total = sum(masses)
    if total <= 0:
        raise ReliefValveR2Error("stream carries no mass")
    x_vapor = 0.0
    for m, phase in zip(masses, stream.phases, strict=True):
        if phase.kind is PhaseKind.VAPOR:
            x_vapor += m / total
    mu_vapor: float | None = None
    mu_liq: float | None = None
    for i, phase in enumerate(stream.phases):
        mu = _phase_viscosity(stream, i, thermo)
        if phase.kind is PhaseKind.VAPOR and mu_vapor is None:
            mu_vapor = mu
        elif mu_liq is None:
            mu_liq = mu
    if mu_vapor is None or mu_liq is None:
        raise ReliefValveR2Error("the McAdams two-phase viscosity needs one vapour and one liquid phase")
    return mcadams_viscosity(x_vapor, mu_vapor, mu_liq)


def _form_dP(K: float, rho: float, v: float) -> float:
    """The Sigma-K form term K rho v^2 / 2."""
    return K * rho * v**2 / 2.0


def inlet_line_dP(
    W_rated: float,
    rho: float,
    mu: float,
    D_m: float,
    L_m: float,
    roughness_m: float,
    K: float,
) -> dict[str, float]:
    """Line loss, homogeneous incompressible (eq. 7): (f L/D + Sigma K) rho v^2/2.

    Delegates the Colebrook friction to the sizing layer's darcy_colebrook
    (which takes the volumetric flow) and adds the Sigma-K term here. The
    returned dict carries velocity (m/s), Re, the Darcy f and dP (Pa).
    """
    if W_rated <= 0:
        raise ReliefValveR2Error(f"mass flow must be positive, got {W_rated!r}")
    if rho <= 0:
        raise ReliefValveR2Error(f"density must be positive, got {rho!r}")
    if mu <= 0:
        raise ReliefValveR2Error(f"viscosity must be positive, got {mu!r}")
    if D_m <= 0:
        raise ReliefValveR2Error(f"line diameter must be positive, got {D_m!r}")
    if L_m <= 0:
        raise ReliefValveR2Error(f"line length must be positive, got {L_m!r}")
    if roughness_m < 0:
        raise ReliefValveR2Error(f"roughness must be non-negative, got {roughness_m!r}")
    if K < 0:
        raise ReliefValveR2Error(f"resistance coefficient must be non-negative, got {K!r}")
    res = darcy_colebrook(W_rated / rho, D_m, rho, mu, roughness_m, L_m)
    res["dP_Pa"] += _form_dP(K, rho, res["velocity_m_s"])
    return res


def _fixed_point_cap() -> int:
    """Maximum fixed-point iterations on the discharge-line loss (50)."""
    return 50


class ReliefValveR2(ReliefValveR1):
    """U-R2: API 520 rated capacity, inlet-loss and back-pressure checks around U-R1."""

    @classmethod
    def example_case(cls) -> tuple[dict[str, Any], dict[str, Any]]:
        """R1's two-phase example with P_set at 90 % of the relieving pressure
        and one short line on each side."""
        feeds, params = ReliefValveR1.example_case()
        return feeds, {
            **params,
            "P_set": 0.9 * feeds["inlet"]["P"],
            "L_in_m": 1.0,
            "D_in_m": 0.12,
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
        """R1's result plus the rated capacity and the two line-loss checks."""
        P_atm = params.get("P_atm", 101325.0)
        if not isinstance(P_atm, (int, float)) or P_atm <= 0:
            raise ReliefValveR2Error(f"P_atm must be positive, got {P_atm!r}")
        P_atm = float(P_atm)

        P_set = params.get("P_set")
        if P_set is None:
            raise ReliefValveR2Error("params must include P_set (Pa)")
        if not isinstance(P_set, (int, float)):
            raise ReliefValveR2Error(f"P_set must be numeric, got {type(P_set)}")
        P_set = float(P_set)
        inlet = self._inlet(inlets)
        P0 = inlet.P
        if not P_atm < P_set <= P0:
            raise ReliefValveR2Error(f"P_set must be in (P_atm, P0] = ({P_atm!r}, {P0!r}], got {P_set!r}")

        overpressure = params.get("overpressure", 0.10)
        if overpressure not in (0.10, 0.16, 0.21):
            raise ReliefValveR2Error(f"overpressure must be one of 0.10, 0.16 or 0.21, got {overpressure!r}")

        valve_type = params.get("valve_type", "conventional")
        if valve_type not in ("conventional", "balanced_bellows", "pilot"):
            raise ReliefValveR2Error(
                f"valve_type must be 'conventional', 'balanced_bellows' or 'pilot', got {valve_type!r}"
            )

        L_in = params.get("L_in_m", 0.0)
        L_out = params.get("L_out_m", 0.0)
        K_in = params.get("K_in", 0.0)
        K_out = params.get("K_out", 0.0)
        rough_in = params.get("roughness_in_m", 4.57e-5)
        rough_out = params.get("roughness_out_m", 4.57e-5)
        D_in = params.get("D_in_m", 0.0)
        D_out = params.get("D_out_m", 0.0)
        for name, val in (("L_in_m", L_in), ("L_out_m", L_out)):
            if not isinstance(val, (int, float)) or val < 0:
                raise ReliefValveR2Error(f"{name} must be non-negative, got {val!r}")
        for name, length, val in (("D_in_m", L_in, D_in), ("D_out_m", L_out, D_out)):
            if length > 0 and (not isinstance(val, (int, float)) or val <= 0):
                raise ReliefValveR2Error(
                    f"{name} must be positive when the line length is positive, got {val!r}"
                )
        for name, val in (("K_in", K_in), ("K_out", K_out)):
            if not isinstance(val, (int, float)) or val < 0:
                raise ReliefValveR2Error(f"{name} must be non-negative, got {val!r}")
        for name, val in (("roughness_in_m", rough_in), ("roughness_out_m", rough_out)):
            if not isinstance(val, (int, float)) or val < 0:
                raise ReliefValveR2Error(f"{name} must be non-negative, got {val!r}")

        base = ReliefValveR1.solve(self, inlets, params, thermo)
        info: dict[str, Any] = dict(base.info)

        # eq. 6: rated capacity — A is proportional to W at a fixed relieving state
        W = inlet.mass_flow
        W_rated = W * info["selected_orifice_area_in2"] / info["required_area_in2"]
        info["W_rated_kg_s"] = W_rated

        # eq. 7: inlet line loss at the rated capacity, inlet mixture density
        v0 = mixture_v(inlet)
        rho_m = 1.0 / v0
        dP_in = 0.0
        if L_in > 0:
            mu_in = mixture_viscosity(inlet, thermo)
            dP_in = inlet_line_dP(
                W_rated,
                rho_m,
                mu_in,
                float(D_in),
                float(L_in),
                float(rough_in),
                float(K_in),
            )["dP_Pa"]
        set_gauge = P_set - P_atm
        inlet_loss_frac = dP_in / set_gauge
        info["dP_inlet_Pa"] = dP_in
        info["inlet_loss_frac"] = inlet_loss_frac
        info["inlet_loss_ok"] = int(inlet_loss_frac <= 0.03)

        # eq. 8: built-up back pressure, fixed point on the mean-pressure density
        P_back = float(params["P_back"])
        dP_out = 0.0
        if L_out > 0:
            dP_out = self._builtup_dP(
                inlet,
                thermo,
                P_back,
                W_rated,
                float(D_out),
                float(L_out),
                float(rough_out),
                float(K_out),
            )
        P_back_total = P_back + dP_out
        info["dP_builtup_Pa"] = dP_out
        info["P_back_total_Pa"] = P_back_total
        info["backpressure_frac"] = (P_back_total - P_atm) / set_gauge

        # eq. 9: the valve-type limits (API 520 Part I §5.3.3)
        if valve_type == "pilot":
            info["backpressure_ok"] = 1
        elif valve_type == "conventional":
            info["backpressure_ok"] = int(dP_out <= overpressure * set_gauge)
        else:  # balanced_bellows
            if info["backpressure_frac"] >= 0.50:
                raise ReliefValveR2Error(
                    "total back pressure is at or above 50 % of set gauge; "
                    "API 520 Part I Fig. 30 cannot be applied"
                )
            info["backpressure_ok"] = 1
            is_liquid = info["regime_code"] >= 2
            if is_liquid:
                factor = float(API520_W(P_set, P_back_total))
                info["Kw_fig31"] = factor
            else:
                factor = float(API520_B(P_set, P_back_total, overpressure))
                info["Kb_fig30"] = factor
            info["area_with_backpressure_in2"] = info["required_area_in2"] / factor

        return UnitResult(outlets=base.outlets, info=info)

    def _builtup_dP(
        self,
        inlet: StreamState,
        thermo: Thermo,
        P_back: float,
        W_rated: float,
        D_out: float,
        L_out: float,
        rough_out: float,
        K_out: float,
    ) -> float:
        """Fixed point on the discharge-line loss at the mean line pressure.

        The outlet state is flashed at ``P_back + dP/2`` from the inlet
        enthalpy; the loss is evaluated at that state's density and viscosity.
        Converged when |delta| <= 1e-8 max(dP, 1 Pa); refused at 50 passes.
        """
        z = dict(inlet.composition)
        dP = 0.0
        for _ in range(_fixed_point_cap()):
            P_mean = P_back + dP / 2.0
            try:
                state = thermo.flash_ph(z, P_mean, inlet.enthalpy, inlet.molar_flow)
            except Exception as e:
                raise ReliefValveR2Error(
                    f"the discharge-line flash at the mean line pressure {P_mean} Pa "
                    "failed; the outlet line drives the built-up check out of range"
                ) from e
            rho = 1.0 / mixture_v(state)
            mu = mixture_viscosity(state, thermo)
            new = inlet_line_dP(W_rated, rho, mu, D_out, L_out, rough_out, K_out)["dP_Pa"]
            if abs(new - dP) <= 1e-8 * max(new, 1.0):
                return new
            dP = new
        raise ReliefValveR2Error(
            "the discharge-line back-pressure iteration did not converge within 50 passes"
        )
