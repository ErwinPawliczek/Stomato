"""Orifice, R1: ISO 5167-2 rating and sizing (spec specs/backend/units/orifice.md).

Method (spec, clause numbers against ISO 5167-1:2003 / ISO 5167-2:2003):

1. **Mass flow** (ISO 5167-1:2003 eq. (1), stated as ISO 5167-2 eq. (1) in the
   spec): ``qm = C/sqrt(1 - beta^4) * eps * (pi/4) * d^2 * sqrt(2*dp*rho1)``,
   solved for the tap differential,

       dp = (qm / (C * E * A * eps))^2 / (2 * rho1),

   with ``beta = d/D``, ``E = 1/sqrt(1 - beta^4)`` and ``A = pi/4 * d^2``.

2. **Discharge coefficient** (ISO 5167-2:2003 eq. (4), Reader-Harris/Gallagher).
   C is taken from
   ``fluids.flow_meter.C_Reader_Harris_Gallagher(D, d, rho, mu, qm, taps)``.
   fluids' implementation carries two Reader-Harris (2015) terms that are not
   in the 2003 standard -- a ``max(log10(3700/Re_D), 0)`` factor and a
   ``max(22.7 - 0.0047*Re_D, (1e6/Re_D)^0.3)`` term. Both vanish for
   ``Re_D > 4830``, which the ISO validity limit ``Re_D >= 5000`` guarantees,
   so inside validity this call **is** ISO 5167-2:2003 eq. (4); the closed-form
   tests re-implement eq. (4) independently and confirm the equality.

3. **Expansibility** (ISO 5167-2:2003 eq. (5)):
   ``eps = 1 - (0.351 + 0.256*beta^4 + 0.93*beta^8) * (1 - (p2/p1)^(1/kappa))``,
   via ``fluids.flow_meter.orifice_expansibility``, valid for ``p2/p1 >= 0.75``
   (refused below, as R0). For a liquid ``eps = 1``. ``kappa = cp/(cp - R)``
   from the inlet vapour (same ideal-gas relation as R0, evaluated by the
   adapter); the pure function takes it as a parameter.

4. **Permanent pressure loss** (ISO 5167-2:2003 §5.4): the R0 module's
   ``permanent_loss_ratio(beta, C)`` is reused, never re-derived.

5. **Validity** (ISO 5167-2:2003 §5.3.1): ``d >= 12.5 mm``; ``50 mm <= D <=
   1000 mm``; ``0.1 <= beta <= 0.75``; corner and D-D/2 taps ``Re_D >= 5000``
   for ``beta <= 0.56`` and ``Re_D >= 16000*beta^2`` for ``beta > 0.56``;
   flange taps ``Re_D >= 5000`` and ``Re_D >= 170*beta^2*D`` (D in mm).
   ``Re_D`` uses the **pipe** diameter, ``Re_D = 4*qm/(pi*D*mu)``.

The gas expansibility enters the implicit equation for ``dp``; it is solved as
a fixed point ``eps -> dp -> eps`` to ``|ddp| < 1e-12*dp`` (100-iteration cap),
refusing ``P2/P1 < 0.75`` before every ``eps`` evaluation. C does not depend
on ``dp``, so no iteration is needed for it.

**Adapter** (:class:`OrificeR1`, below): rating mode (``bore_m``) and sizing
mode (``dP_design_Pa``, scipy ``brentq`` over the ISO-feasible bore range),
phase class as R0 with an explicit two-phase refusal, viscosity from the phase
property else ``mu_Pa_s``, outlet flashed at ``P1 - permanent_loss``.
"""

from __future__ import annotations

import math
import sys
from typing import Any

from fluids.flow_meter import C_Reader_Harris_Gallagher, orifice_expansibility
from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.orifice import (
    MIN_PRESSURE_RATIO,
    R_IDEAL,
    OrificeSpecError,
    permanent_loss_ratio,
)

#: Accepted tap arrangements (catalogue param ``taps``).
TAPS = ("corner", "flange", "D-D/2")

#: Mapping to the ``fluids.flow_meter.C_Reader_Harris_Gallagher`` taps names.
#: 'D' and 'D/2' both mean D and D/2 taps there; 'D-D/2' is the catalogue form.
_FLUIDS_TAPS = {"corner": "corner", "flange": "flange", "D-D/2": "D"}

#: Expansibility fixed-point iteration cap (spec algorithm step 3).
_MAX_FIXED_POINT_ITERATIONS = 100


class OrificeR1Error(OrificeSpecError):
    """Typed refusal naming the parameter of a bad orifice R1 spec."""


def _check_validity(D: float, d: float, beta: float, Re_D: float, taps: str) -> None:
    """ISO 5167-2:2003 §5.3.1 validity limits, refusing with the violated quantity."""
    if d < 0.0125:
        raise OrificeR1Error(f"orifice bore d = {d} m outside ISO 5167-2 validity (d >= 12.5 mm)")
    if not 0.05 <= D <= 1.0:
        raise OrificeR1Error(f"pipe diameter D_m = {D} m outside ISO 5167-2 validity (50 mm <= D <= 1000 mm)")
    if not 0.1 <= beta <= 0.75:
        raise OrificeR1Error(f"beta = {beta} outside ISO 5167-2 validity (0.1 <= beta <= 0.75)")
    if taps == "flange":
        Re_min_flange = 170.0 * beta**2 * (D * 1000.0)
        if Re_D < 5000.0 or Re_D < Re_min_flange:
            raise OrificeR1Error(
                f"Re_D = {Re_D:.6g} outside ISO 5167-2 validity for flange taps "
                f"(Re_D >= 5000 and Re_D >= 170*beta^2*D = {Re_min_flange:.6g})"
            )
    else:
        Re_min_corner = 5000.0 if beta <= 0.56 else 16000.0 * beta**2
        if Re_D < Re_min_corner:
            raise OrificeR1Error(
                f"Re_D = {Re_D:.6g} outside ISO 5167-2 validity for {taps} taps "
                f"({'Re_D >= 5000' if beta <= 0.56 else 'Re_D >= 16000*beta^2'} "
                f"= {Re_min_corner:.6g} at beta = {beta})"
            )


def orifice_dp(
    qm: float,
    D: float,
    d: float,
    rho: float,
    mu: float,
    P1: float,
    kappa_or_None: float | None,
    taps: str,
    C_specified: float | None = None,
) -> dict[str, float]:
    """Tap differential, C, expansibility, Re_D and permanent loss of an orifice.

    Pure function (spec algorithm): rating mode of :class:`OrificeR1`. ``qm``
    is the mass flow in kg/s, ``D`` the pipe and ``d`` the bore internal
    diameter in m, ``rho``/``mu`` the dominant-phase density and viscosity,
    ``P1`` the upstream pressure in Pa. ``kappa_or_None`` is ``None`` for a
    liquid (``eps = 1``) or the isentropic exponent for a gas (eq. (5) fixed
    point). ``C_specified`` pins C (R0 equivalence) instead of the
    Reader-Harris/Gallagher coefficient.

    Returns ``C``, ``epsilon``, ``Re_D``, ``dP`` (tap differential, Pa) and
    ``permanent_loss`` (ISO 5167-2 §5.4, Pa).
    """
    if taps not in TAPS:
        raise OrificeR1Error(f"taps {taps!r} not in {TAPS}")
    if C_specified is not None and not 0.0 < C_specified < 1.0:
        raise OrificeR1Error(f"C_specified {C_specified} outside (0, 1)")
    if qm <= 0.0:
        raise OrificeR1Error(f"mass flow {qm} kg/s must be > 0")
    if rho <= 0.0:
        raise OrificeR1Error(f"rho {rho} kg/m3 must be > 0")
    if mu <= 0.0:
        raise OrificeR1Error(f"mu {mu} Pa.s must be > 0")

    beta = d / D
    Re_D = 4.0 * qm / (math.pi * D * mu)
    _check_validity(D, d, beta, Re_D, taps)

    C = (
        float(C_specified)
        if C_specified is not None
        else (C_Reader_Harris_Gallagher(D, d, rho, mu, qm, taps=_FLUIDS_TAPS[taps]))
    )
    E = 1.0 / math.sqrt(1.0 - beta**4)
    A = math.pi / 4.0 * d**2

    if kappa_or_None is None:
        dP = (qm / (C * E * A)) ** 2 / (2.0 * rho)
        if dP >= P1:
            raise OrificeR1Error(f"implied dP {dP} Pa exceeds the inlet pressure {P1} Pa")
        epsilon = 1.0
    else:
        dP = (qm / (C * E * A)) ** 2 / (2.0 * rho)
        epsilon = 1.0
        for _ in range(_MAX_FIXED_POINT_ITERATIONS):
            P2 = P1 - dP
            if P2 / P1 < MIN_PRESSURE_RATIO:
                raise OrificeR1Error(
                    f"P2/P1 = {P2 / P1:.6g} below the ISO 5167-2 validity limit "
                    f"{MIN_PRESSURE_RATIO} at this flow and bore"
                )
            epsilon = orifice_expansibility(D, d, P1, P2, kappa_or_None)
            dP_new = (qm / (C * E * A * epsilon)) ** 2 / (2.0 * rho)
            done = abs(dP_new - dP) < 1e-12 * dP
            dP = dP_new
            if done:
                break
        else:
            raise OrificeR1Error(
                f"expansibility fixed point did not converge within {_MAX_FIXED_POINT_ITERATIONS} iterations"
            )

    permanent_loss = permanent_loss_ratio(beta, C) * dP
    return {
        "C": C,
        "epsilon": epsilon,
        "Re_D": Re_D,
        "dP": dP,
        "permanent_loss": permanent_loss,
    }

class OrificeR1:
    """ISO 5167-2 orifice plate with the Reader-Harris/Gallagher coefficient.

    Adapter over :func:`orifice_dp` (U-R2: the pure function owns every
    number). Rating mode takes ``bore_m``; sizing mode takes
    ``dP_design_Pa`` and finds the bore whose tap differential equals the
    design target (``brentq`` over the ISO 5167-2 feasible bore range
    ``[max(0.1*D, 12.5 mm), 0.75*D]``, ``xtol=1e-12``,
    ``rtol=4*DBL_EPSILON``, maxiter 100). Params: ``D_m`` (required, m),
    ``taps`` (default ``"flange"``), ``C_specified`` (R0 equivalence) and
    ``mu_Pa_s`` (viscosity override; the phase viscosity is preferred, and
    neither present is a refusal).
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

        if "D_m" not in params:
            raise OrificeR1Error("D_m is required (pipe internal diameter, m)")
        D_m = float(params["D_m"])
        if D_m <= 0.0:
            raise OrificeR1Error(f"D_m {D_m} must be > 0")

        has_bore = "bore_m" in params and params["bore_m"] is not None
        has_target = "dP_design_Pa" in params and params["dP_design_Pa"] is not None
        if has_bore == has_target:
            raise OrificeR1Error(
                "exactly one of bore_m / dP_design_Pa must be given "
                "(rating mode takes bore_m, sizing mode takes dP_design_Pa)"
            )

        taps = params.get("taps", "flange")
        C_specified = params.get("C_specified")
        C_specified_f = float(C_specified) if C_specified is not None else None

        # Phase class as R0, plus the spec's explicit two-phase refusal.
        vapor = next((p for p in inlet.phases if p.kind == PhaseKind.VAPOR), None)
        if 0.001 < inlet.vapor_fraction < 0.999:
            raise OrificeR1Error(
                f"ISO 5167 requires single-phase flow; inlet vapor_fraction is {inlet.vapor_fraction:.4f}"
            )
        if inlet.vapor_fraction > 0.999 and vapor is not None:
            dominant = vapor
            is_gas = True
        else:
            dense = [p for p in inlet.phases if p.kind is not PhaseKind.VAPOR]
            if not dense:
                raise OrificeR1Error("inlet has no dense phase to meter")
            dominant = max(dense, key=lambda p: p.mole_fraction)
            is_gas = False

        rho = dominant.density

        kappa_or_None: float | None = None
        if is_gas:
            props = thermo.phase_props(dominant.composition, inlet.T, inlet.P, PhaseKind.VAPOR)
            kappa_or_None = props.cp / (props.cp - R_IDEAL)

        # Viscosity: phase property preferred, override second, refusal if neither.
        mu_override = params.get("mu_Pa_s")
        mu: float | None = float(mu_override) if mu_override is not None else None
        if mu is not None and mu <= 0.0:
            raise OrificeR1Error(f"mu_Pa_s {mu} must be > 0")
        if mu is None:
            props = thermo.phase_props(dominant.composition, inlet.T, inlet.P, dominant.kind)
            mu = props.viscosity
        if mu is None:
            raise OrificeR1Error(
                "mu_Pa_s is required: the property package reports no phase viscosity at the inlet state"
            )

        qm = inlet.mass_flow

        if has_bore:
            bore_m = float(params["bore_m"])
            sizing = 0.0
        else:
            dP_design = float(params["dP_design_Pa"])
            if dP_design <= 0.0:
                raise OrificeR1Error(f"dP_design_Pa {dP_design} must be > 0")
            bore_m = self._size_bore(qm, D_m, rho, mu, inlet.P, kappa_or_None, taps, C_specified_f, dP_design)
            sizing = 1.0

        r = orifice_dp(qm, D_m, bore_m, rho, mu, inlet.P, kappa_or_None, taps, C_specified_f)
        beta = bore_m / D_m
        E = 1.0 / math.sqrt(1.0 - beta**4)

        outlet = thermo.flash_ph(
            inlet.composition, inlet.P - r["permanent_loss"], inlet.enthalpy, inlet.molar_flow
        )
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={
                "C": r["C"],
                "expansibility": r["epsilon"],
                "Re_D": r["Re_D"],
                "beta": beta,
                "bore_m": bore_m,
                "dP_Pa": r["dP"],
                "permanent_loss_Pa": r["permanent_loss"],
                "velocity_approach": E,
                "sizing": sizing,
            },
        )

    @staticmethod
    def _size_bore(
        qm: float,
        D_m: float,
        rho: float,
        mu: float,
        P1: float,
        kappa_or_None: float | None,
        taps: str,
        C_specified: float | None,
        dP_design: float,
    ) -> float:
        """Bore whose tap differential equals ``dP_design`` (brentq on dP(d))."""
        d_lo = max(0.1 * D_m, 0.0125)
        d_hi = 0.75 * D_m

        def dP_at(d: float) -> float:
            return orifice_dp(qm, D_m, d, rho, mu, P1, kappa_or_None, taps, C_specified)["dP"]

        # dP falls monotonically with bore. At small bores the pure function
        # legitimately refuses (implied dP above the inlet pressure, gas
        # expansibility below the pressure-ratio limit): scan up to the first
        # valid bore; the interval [d_feas, d_hi] is valid throughout.
        d_feas = d_lo
        dP_lo: float | None = None
        for _ in range(100):
            try:
                dP_lo = dP_at(d_feas)
                break
            except OrificeR1Error:
                d_feas += (d_hi - d_lo) / 100.0
        if dP_lo is None:
            raise OrificeR1Error(
                f"no bore within the ISO 5167-2 range gives dP_design {dP_design} Pa: "
                f"every bore in ({d_lo:.6g}, {d_hi:.6g}) m is outside the pure-function "
                f"validity (differential above the inlet pressure or gas pressure "
                f"ratio below the limit)"
            )
        dP_hi = dP_at(d_hi)
        if not dP_hi <= dP_design <= dP_lo:
            raise OrificeR1Error(
                f"no bore within the ISO 5167-2 range gives dP_design "
                f"{dP_design} Pa (achievable range {dP_hi:.6g} to {dP_lo:.6g} Pa)"
            )

        def f(d: float) -> float:
            return dP_at(d) - dP_design

        try:
            return float(brentq(f, d_feas, d_hi, xtol=1e-12, rtol=4 * sys.float_info.epsilon, maxiter=100))
        except (RuntimeError, ValueError) as exc:
            raise OrificeR1Error(f"sizing did not converge: {exc}") from exc

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Condensate meter run basis: 50 mm pipe, 25 mm bore, flange taps."""
        feed = {
            "T": 293.15,
            "P": 1.0e6,
            "molar_flow": 25.0,
            "composition": {"iC4": 0.392, "nC4": 0.248, "iC5": 0.157, "nC5": 0.203},
        }
        return {"inlet": feed}, {"D_m": 0.05, "bore_m": 0.025, "taps": "flange"}
