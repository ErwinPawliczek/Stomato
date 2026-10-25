"""Decanter R1: Stokes settling with Richardson-Zaki hindered settling.

Plugin kind "unit", name "decanter" (level R1) — registered from the
catalogue YAML; no decorator (U-R2 conventions). Read-only over the R0
:class:`~ngdesign.units.separation.decanter.Decanter`, which supplies the
LLE split; this level adds the settling physics on top of it.

Method (spec ``specs/backend/units/decanter.md``):

- **D1** Stokes terminal velocity of a dispersed droplet in the continuous
  phase: ``u_t = g·d²·|ρ_d − ρ_c|/(18·μ_c)`` with g = 9.80665 m/s². Valid
  only for ``Re_t = ρ_c·u_t·d/μ_c < 1``; outside that range the unit refuses
  (R1 is a Stokes model — never extrapolated).
- **D2** dispersed volume fraction ``φ = Q_d/(Q_c + Q_d)`` from the R0
  outlets' volumetric flows.
- **D3** Richardson-Zaki exponent (Trans. IChemE 32:35, 1954), no wall
  correction: ``n = 4.65`` for ``Re_t < 0.2``; ``4.4·Re_t^−0.03`` for
  ``0.2 ≤ Re_t < 1``; ``4.4·Re_t^−0.1`` for ``1 ≤ Re_t < 500`` (unreachable
  under D1's validity); ``2.4`` for ``Re_t ≥ 500``.
- **D4** hindered velocity ``u_h = u_t·(1 − φ)^n``.
- **D5** Hazen (1904) ideal-settler efficiency ``η = min(1, u_h·A_i/Q_c)``,
  with ``A_i`` the interface area — for a horizontal cylinder with the
  interface at the centre line, ``A_i = D·L`` (Sinnott, *Coulson &
  Richardson's Chemical Engineering* Vol. 6, §10.6.3).
- **D6** entrainment: the fraction ``1 − η`` of the dispersed phase leaves
  with the continuous phase.

The dispersed outlet is the R0 outlet scaled to ``η·n_d`` (never re-flashed);
the continuous outlet is re-flashed as a two-liquid mix of the R0 continuous
outlet and the entrained dispersed liquid at the same T and P.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Phase, PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.decanter import Decanter

#: Standard gravity, m/s2 (D1).
G = 9.80665


class DecanterR1SpecError(ValueError):
    """The decanter R1 spec is outside the Stokes settling model."""


def stokes_velocity(d: float, rho_d: float, rho_c: float, mu_c: float) -> float:
    """Stokes terminal velocity (D1): ``u_t = g·d²·|ρ_d − ρ_c|/(18·μ_c)``.

    Units: d in m, densities in kg/m³, ``mu_c`` in Pa·s, result in m/s.
    """
    return G * d**2 * abs(rho_d - rho_c) / (18.0 * mu_c)


def rz_exponent(re_t: float) -> float:
    """Richardson-Zaki exponent (D3) as a function of the droplet Reynolds number."""
    if re_t < 0.2:
        return 4.65
    if re_t < 1.0:
        return float(4.4 * re_t**-0.03)
    if re_t < 500.0:
        return float(4.4 * re_t**-0.1)
    return 2.4


def hindered_velocity(u_t: float, phi: float, n: float) -> float:
    """Richardson-Zaki hindered settling velocity (D4): ``u_h = u_t·(1 − φ)^n``."""
    return u_t * float((1.0 - phi) ** n)


def settler_efficiency(u_h: float, area_m2: float, q_c: float) -> float:
    """Hazen ideal-settler separation efficiency (D5): ``min(1, u_h·A_i/Q_c)``."""
    return min(1.0, u_h * area_m2 / q_c)


def _liquid_phase(outlet: StreamState) -> Phase:
    """The single liquid phase an R0 outlet carries (its flash was one-phase)."""
    for phase in outlet.phases:
        if phase.kind is not PhaseKind.VAPOR and phase.mole_fraction > 0.0:
            return phase
    raise DecanterR1SpecError(
        "the R0 decanter outlet carries no liquid phase; the R1 settling model "
        "needs a density and a viscosity from each outlet's phase"
    )


def _positive(params: dict[str, Any], name: str) -> float:
    """A required, present, > 0 numeric param; typed refusal naming it."""
    value = params.get(name)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise DecanterR1SpecError(f"{name} must be a number > 0, got {value!r}")
    return float(value)


class DecanterR1:
    """Stokes/Richardson-Zaki settling on the R0 decanter's LLE split.

    The R0 :class:`Decanter` supplies the two-liquid split (its typed refusals
    propagate unchanged); this level sizes the entrainment of the droplet-sized
    dispersed phase into the continuous outlet (D1–D6 in the module docstring).

    ``mu_c`` resolution: the ``continuous_viscosity_Pa_s`` param overrides the
    continuous outlet's phase viscosity when given; with neither, the unit
    refuses (the Stokes equation needs a continuous-phase viscosity).
    """

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("light_out", "heavy_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        dispersed_phase = params.get("dispersed_phase")
        if dispersed_phase not in ("light", "heavy"):
            raise DecanterR1SpecError(
                f"dispersed_phase must be 'light' or 'heavy', got {dispersed_phase!r}"
            )
        droplet = _positive(params, "droplet_diameter_m")

        has_area = "interface_area_m2" in params
        has_dl = "diameter_m" in params and "length_m" in params
        stray_geometry = ("diameter_m" in params or "length_m" in params) and has_area
        if has_area == has_dl or stray_geometry:
            raise DecanterR1SpecError(
                "give exactly one interface-area form: interface_area_m2, or "
                "diameter_m and length_m for a horizontal vessel with the "
                "interface at the centre line"
            )
        if has_area:
            area = _positive(params, "interface_area_m2")
        else:
            area = _positive(params, "diameter_m") * _positive(params, "length_m")

        r0 = Decanter().solve(inlets, {"dP": params.get("dP", 0.0)}, thermo)
        dispersed_r0 = r0.outlets[f"{dispersed_phase}_out"]
        continuous_r0 = r0.outlets[
            "heavy_out" if dispersed_phase == "light" else "light_out"
        ]

        dispersed_liq = _liquid_phase(dispersed_r0)
        continuous_liq = _liquid_phase(continuous_r0)
        rho_d, rho_c = dispersed_liq.density, continuous_liq.density
        mu_override = params.get("continuous_viscosity_Pa_s")
        mu_c = (
            float(mu_override)
            if mu_override is not None
            else continuous_liq.viscosity
        )
        if mu_c is None or mu_c <= 0:
            raise DecanterR1SpecError(
                "continuous_viscosity_Pa_s: the continuous outlet's phase has no "
                "viscosity and no override was given; the Stokes model needs one"
            )

        # Volumetric flows from each outlet's mass flow over its phase density (D2).
        q_d = dispersed_r0.mass_flow / rho_d
        q_c = continuous_r0.mass_flow / rho_c

        u_t = stokes_velocity(droplet, rho_d, rho_c, mu_c)
        re_t = rho_c * u_t * droplet / mu_c
        if re_t >= 1.0:
            raise DecanterR1SpecError(
                f"Stokes validity exceeded: Re_t = {re_t:.4g} >= 1 at droplet "
                f"diameter {droplet} m; R1 is a Stokes model and does not extrapolate"
            )
        phi = q_d / (q_c + q_d)
        n = rz_exponent(re_t)
        u_h = hindered_velocity(u_t, phi, n)
        eta = settler_efficiency(u_h, area, q_c)

        info: dict[str, float] = {
            "u_t_m_s": u_t,
            "Re_t": re_t,
            "phi_dispersed": phi,
            "rz_exponent": n,
            "u_h_m_s": u_h,
            "interface_area_m2": area,
            "overflow_rate_m_s": q_c / area,
            "separation_efficiency": eta,
            "entrained_dispersed_fraction": 1.0 - eta,
        }

        if eta == 1.0:
            # The reduction to R0: every outlet equals R0's exactly, same duty.
            return UnitResult(outlets=dict(r0.outlets), duty_W=r0.duty_W, power_W=0.0, info=info)

        n_d = dispersed_r0.molar_flow
        n_c = continuous_r0.molar_flow
        entrained = (1.0 - eta) * n_d
        dispersed_out = dispersed_r0.model_copy(update={"molar_flow": eta * n_d})
        z_mix = {
            cid: (n_c * continuous_r0.composition[cid] + entrained * dispersed_r0.composition[cid])
            / (n_c + entrained)
            for cid in continuous_r0.composition
        }
        # Two coexisting equilibrium liquids at the same T and P, so the flash
        # returns the same tie line with the entrained liquid folded into the
        # continuous outlet.
        continuous_out = thermo.flash_pt(z_mix, continuous_r0.T, continuous_r0.P, n_c + entrained)
        outlets = {
            "light_out": dispersed_out if dispersed_phase == "light" else continuous_out,
            "heavy_out": continuous_out if dispersed_phase == "light" else dispersed_out,
        }
        inlet = inlets["inlet"]
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(outlets=outlets, duty_W=h_out_W - h_in_W, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feed at R1 params that sit at the reduction limit.

        The same subcooled water / n-pentane feed as R0, with a settling area
        large enough that eta = 1: the identity limit, so the level closes the
        same V0 balances as R0 on ``pr``.
        """
        feeds = {
            "inlet": {
                "T": 278.15,
                "P": 1.0e5,
                "molar_flow": 100.0,
                "composition": {"H2O": 0.6, "nC5": 0.4},
            }
        }
        params = {
            "dispersed_phase": "light",
            "droplet_diameter_m": 150e-6,
            "interface_area_m2": 1.0e4,
        }
        return feeds, params
