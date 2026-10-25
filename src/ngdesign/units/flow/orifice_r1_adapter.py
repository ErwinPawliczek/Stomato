"""Orifice R1 adapter: rating and sizing on the single inlet port.

Adapter conventions per U-R1, mechanics per U-R2: the pure function
:func:`ngdesign.units.flow.orifice_r1.orifice_dp` owns every number; this
class maps the inlet state and catalogue params onto it.

Params (all optional keys read with ``params.get``; refusals name the
parameter):

- ``D_m``: pipe internal diameter, m (required, > 0).
- ``bore_m`` **or** ``dP_design_Pa`` — exactly one: rating mode solves the
  tap differential for the given bore; sizing mode finds the bore whose
  differential equals the design target (scipy ``brentq`` on
  ``dP(d) - dP_design_Pa`` over the ISO 5167-2 feasible range
  ``[max(0.1*D, 12.5 mm), 0.75*D]``, ``xtol=1e-12``,
  ``rtol=4*DBL_EPSILON``, maxiter 100).
- ``taps``: ``"corner" | "flange" | "D-D/2"``, default ``"flange"``.
- ``C_specified``: pins C instead of the Reader-Harris/Gallagher
  coefficient (R0 equivalence).
- ``mu_Pa_s``: viscosity override. The phase viscosity is preferred; if the
  package reports none and no ``mu_Pa_s`` is given, the spec is refused.

Phase class as R0: gas when ``vapor_fraction > 0.999`` and a vapour phase
exists (its properties supply ``kappa = cp/(cp - R)``), otherwise the
dominant dense phase. A two-phase inlet (``0.001 < vapor_fraction < 0.999``)
is refused: ISO 5167 requires single-phase flow.

The outlet flashes at ``P1 - permanent_loss`` at the inlet enthalpy —
unchanged from R0, since the flowsheet port is downstream of the plate, not
at the taps.
"""

from __future__ import annotations

import math
import sys
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.orifice import R_IDEAL
from ngdesign.units.flow.orifice_r1 import OrificeR1Error, orifice_dp


class OrificeR1:
    """ISO 5167-2 orifice plate with the Reader-Harris/Gallagher coefficient."""

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
