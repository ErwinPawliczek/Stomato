"""Orifice, R0 (spec U-B, plan §2 U-B 8).

Method (spec): ISO 5167 incompressible form solved for the pressure drop,

    dP = (mdot / (Cd * E * A * Y))^2 / (2 * rho),

with ``E = 1/sqrt(1 - beta^4)`` and ``A = pi/4 * bore_m^2``, evaluated with
the inlet's dominant-phase density. ``Y = 1`` for liquids; for a gas the
ISO 5167-2 §5.3.2.2 expansibility factor

    Y = 1 - (0.351 + 0.256*beta^4 + 0.93*beta^8) * (1 - (P2/P1)^(1/kappa))

applies, iterated to consistency with the implied P2 (fixed point, 1e-10
relative), and refused outside the standard's validity ``P2/P1 >= 0.75``.
``kappa`` uses the ideal-gas relation ``cp/(cp - R)`` from the inlet vapour.
The tap differential ``dP`` is the metering result; the flowsheet outlet sits
at ``P1 - delta_varpi`` instead, the ISO 5167-2 §5.4 permanent pressure loss
(a plate recovers part of the differential downstream):

    delta_varpi = (sqrt(1 - beta^4 (1 - C^2)) - C beta^2)
                  / (sqrt(1 - beta^4 (1 - C^2)) + C beta^2) * dP

Both ``dP_Pa`` and ``permanent_loss_Pa`` are reported in info.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

#: ISO 5167-2 §5.3.2.2 minimum validity ratio of downstream to upstream pressure.
MIN_PRESSURE_RATIO = 0.75


def permanent_loss_ratio(beta: float, C: float) -> float:
    """ISO 5167-2 §5.4 permanent pressure loss ratio, ``delta_varpi / dP``."""
    root = math.sqrt(1.0 - beta**4 * (1.0 - C**2))
    return (root - C * beta**2) / (root + C * beta**2)


#: CODATA 2018 molar gas constant, J/(mol.K) (same reference as thermo.pr).
R_IDEAL = 8.31446261815324


class OrificeSpecError(ValueError):
    """Typed refusal naming the parameter of a bad orifice spec."""


def _expansibility(beta: float, P2: float, P1: float, kappa: float) -> float:
    """ISO 5167-2 §5.3.2.2 expansibility factor Y."""
    kappa_f = float(kappa)
    exponent = 1.0 / kappa_f
    ratio = P2 / P1
    correction = 0.351 + 0.256 * beta**4 + 0.93 * beta**8
    return float(1.0 - correction * (1.0 - ratio**exponent))


class Orifice:
    """ISO 5167 orifice plate: given geometry, solve the pressure drop (R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        bore_m = float(params["bore_m"])
        beta = float(params["beta"])
        Cd = float(params["Cd"])
        if bore_m <= 0:
            raise OrificeSpecError(f"bore_m {bore_m} must be > 0")
        if not 0.0 < beta <= 1.0:
            raise OrificeSpecError(f"beta {beta} outside (0, 1]")
        if not 0.0 < Cd <= 1.0:
            raise OrificeSpecError(f"Cd {Cd} outside (0, 1]")

        vapor = next((p for p in inlet.phases if p.kind == PhaseKind.VAPOR), None)
        is_gas = inlet.vapor_fraction > 0.999 and vapor is not None
        if is_gas and vapor is not None:
            dominant = vapor
        else:
            dense = [p for p in inlet.phases if p.kind is not PhaseKind.VAPOR]
            if not dense:
                raise OrificeSpecError("inlet has no dense phase to meter")
            dominant = max(dense, key=lambda p: p.mole_fraction)
        rho = dominant.density
        E = 1.0 / math.sqrt(1.0 - beta**4)
        A = math.pi / 4.0 * bore_m**2
        mdot = inlet.mass_flow

        Y = 1.0
        dP = (mdot / (Cd * E * A * Y)) ** 2 / (2.0 * rho)
        if is_gas:
            props = thermo.phase_props(dominant.composition, inlet.T, inlet.P, PhaseKind.VAPOR)
            kappa = props.cp / (props.cp - R_IDEAL)
            for _ in range(50):
                P2 = inlet.P - dP
                if P2 / inlet.P < MIN_PRESSURE_RATIO:
                    raise OrificeSpecError(
                        f"P2/P1 = {P2 / inlet.P:.3f} below the ISO 5167-2 validity limit "
                        f"{MIN_PRESSURE_RATIO} at this flow and bore"
                    )
                Y = _expansibility(beta, P2, inlet.P, kappa)
                dP_new = (mdot / (Cd * E * A * Y)) ** 2 / (2.0 * rho)
                if abs(dP_new - dP) < 1e-10 * dP:
                    dP = dP_new
                    break
                dP = dP_new
            else:
                raise OrificeSpecError("expansibility fixed point did not converge")
        elif dP >= inlet.P:
            raise OrificeSpecError(f"implied dP {dP} Pa reaches or exceeds the inlet pressure")

        permanent_loss = permanent_loss_ratio(beta, Cd) * dP
        outlet = thermo.flash_ph(
            inlet.composition, inlet.P - permanent_loss, inlet.enthalpy, inlet.molar_flow
        )
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={
                "dP_Pa": dP,
                "permanent_loss_Pa": permanent_loss,
                "velocity_approach": E,
                "expansibility": Y,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Condensate meter run basis: 50 mm bore, beta = 0.5, Cd = 0.61."""
        feed = {
            "T": 293.15,
            "P": 1.0e6,
            "molar_flow": 50.0,
            "composition": {"iC4": 0.392, "nC4": 0.248, "iC5": 0.157, "nC5": 0.203},
        }
        return {"inlet": feed}, {"bore_m": 0.05, "beta": 0.5, "Cd": 0.61}
