"""Ejector, R0 (spec U-B, plan §2 U-B 9).

Method (spec): adiabatic mixing. The motive and suction streams are consumed
in full (``H_out = H_m + H_s``); the mixed composition is the flow-weighted
mole average and the outlet is a PH flash of the mix at ``P_out``. The
entrainment spec ``m`` (kg suction per kg motive) is converted to the
required motive-to-suction mass ratio ``1/m``, and the ratio the given
streams actually achieve is reported alongside. No ejector performance curve
is applied at R0 — the spec fixes the mixing, the curve (R1) would trim the
achievable discharge pressure.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo


class EjectorSpecError(ValueError):
    """Typed refusal naming the parameter of a bad ejector spec."""


class Ejector:
    """Adiabatic motive/suction mixer with an entrainment spec (R0)."""

    inlet_ports = ("motive", "suction")
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        motive = inlets["motive"]
        suction = inlets["suction"]
        P_out = float(params["P_out"])
        entrainment = float(params["entrainment"])
        if P_out <= 0:
            raise EjectorSpecError(f"P_out {P_out} Pa must be > 0")
        if P_out > motive.P:
            raise EjectorSpecError(f"P_out {P_out} Pa is above the motive pressure {motive.P} Pa")
        if P_out < suction.P:
            raise EjectorSpecError(f"P_out {P_out} Pa is below the suction pressure {suction.P} Pa")
        if entrainment <= 0:
            raise EjectorSpecError(f"entrainment {entrainment} kg/kg must be > 0")

        n_m, n_s = motive.molar_flow, suction.molar_flow
        z_mix = {
            cid: (n_m * motive.composition.get(cid, 0.0) + n_s * suction.composition.get(cid, 0.0))
            / (n_m + n_s)
            for cid in set(motive.composition) | set(suction.composition)
        }
        h_mix = (n_m * motive.enthalpy + n_s * suction.enthalpy) / (n_m + n_s)
        outlet = thermo.flash_ph(z_mix, P_out, h_mix, n_m + n_s)

        mass_m, mass_s = motive.mass_flow, suction.mass_flow
        achieved = mass_s / mass_m
        return UnitResult(
            outlets={"outlet": outlet},
            duty_W=0.0,
            power_W=0.0,
            info={
                "entrainment_achieved": achieved,
                "motive_to_suction_required": 1.0 / entrainment,
                "entrainment_spec_met": 1.0 if abs(achieved / entrainment - 1.0) <= 1e-5 else 0.0,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Graham-style ejector basis: 500 K motive steam pulling 300 K vapour at ~15 torr."""
        motive = {"T": 500.0, "P": 1.0e6, "molar_flow": 146.873, "composition": {"H2O": 1.0}}
        suction = {"T": 300.0, "P": 2000.0, "molar_flow": 48.958, "composition": {"H2O": 1.0}}
        return {"motive": motive, "suction": suction}, {"P_out": 5.0e4, "entrainment": 1.0 / 3.0}
