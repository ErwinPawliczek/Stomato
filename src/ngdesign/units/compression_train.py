"""Multistage compression train with interstage cooling (wave-2 expansion).

Plugin kind "unit", name "compression_train".

One node instead of the repeated compressor + cooler pattern: the total
pressure ratio splits geometrically over the fewest stages so no stage exceeds
``max_ratio_per_stage`` -- the same convention as ``sizing/machines.py``
(``n = ceil(ln(ratio) / ln(max_per_stage) - 1e-9)``, minimum 1; the 1e-9 guard
keeps the exact n-stage case ``ln(max**n) / ln(max)`` from rounding up by one
ulp). Stage count and the per-stage ratio are computed once per solve.

Per stage, the existing single-stage compressor physics: isentropic reference
``flash_ps`` to the stage discharge pressure at the stage-inlet entropy, the
real discharge enthalpy recovers only ``eta_isentropic`` of the isentropic
rise, ``flash_ph`` for the real discharge state. Every stage except the last
is followed by an intercooler to ``T_interstage_out`` at constant pressure
(``flash_pt``); the final stage discharges directly. Plain iteration inside
``solve()`` -- the flowsheet stays one-pass per unit, zero solver changes.

``duty_W`` is the summed intercooler duty (negative: heat removed) and
``power_W`` the summed shaft power; ``info`` carries per-stage discharge
pressures, per-stage intercooler duties, and the totals.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import register
from ngdesign.units._examples import INLET_COMPOSITION, MMSCFD_TO_MOL_S

#: Max pressure ratio per stage, per the sizing/machines.py convention.
DEFAULT_MAX_RATIO_PER_STAGE = 3.5
#: Intercooler outlet temperature basis, K (the slice convention: 322.15 K
#: feed/dehydration-temperature level). Override via params.
DEFAULT_T_INTERSTAGE_OUT = 322.15
DEFAULT_ETA_ISENTROPIC = 0.75


def stage_plan(
    P_in: float,
    P_discharge: float,
    max_ratio_per_stage: float,
) -> tuple[int, float]:
    """Stage count and per-stage pressure ratio (geometric split).

    Fewest stages so no stage exceeds ``max_ratio_per_stage``, each stage
    seeing the same ratio ``r = (P_discharge / P_in) ** (1 / n)``.
    """
    if P_in <= 0 or P_discharge <= 0:
        raise ValueError(f"pressures must be positive, got P_in {P_in} Pa, P_discharge {P_discharge} Pa")
    if max_ratio_per_stage <= 1.0:
        raise ValueError(f"max_ratio_per_stage must be > 1, got {max_ratio_per_stage}")
    ratio = P_discharge / P_in
    if ratio <= 1.0:
        raise ValueError(f"P_discharge {P_discharge} Pa must exceed P_in {P_in} Pa")
    if ratio <= max_ratio_per_stage:
        return 1, ratio
    # 1e-9 guard: exactly n stages at ratio max**n must not round up to n+1
    # (see sizing/machines.compressor_stages for the same rule).
    n = math.ceil(math.log(ratio) / math.log(max_ratio_per_stage) - 1e-9)
    return n, ratio ** (1.0 / n)


def _compress_stage(
    thermo: Thermo,
    z: dict[str, float],
    flow: float,
    inlet: StreamState,
    P_out: float,
    eta: float,
) -> StreamState:
    """One isentropic-efficiency compression step (compressor.py physics)."""
    isentropic = thermo.flash_ps(z, P_out, inlet.entropy, flow)
    h_out = inlet.enthalpy + (isentropic.enthalpy - inlet.enthalpy) / eta
    return thermo.flash_ph(z, P_out, h_out, flow)


@register("unit", "compression_train")
class CompressionTrain:
    """Multistage gas compressor with interstage cooling to a set discharge pressure."""

    inlet_ports = ("gas_in",)
    outlet_ports = ("gas_out",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["gas_in"]
        if inlet.vapor_fraction < 0.999:
            raise ValueError(
                f"compression_train inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f})"
            )
        P_discharge = float(params["P_discharge"])
        max_ratio = float(params.get("max_ratio_per_stage", DEFAULT_MAX_RATIO_PER_STAGE))
        eta = float(params.get("eta_isentropic", DEFAULT_ETA_ISENTROPIC))
        T_interstage = float(params.get("T_interstage_out", DEFAULT_T_INTERSTAGE_OUT))
        if not 0.0 < eta <= 1.0:
            raise ValueError(f"eta_isentropic {eta} outside (0, 1]")
        if T_interstage <= 0:
            raise ValueError(f"T_interstage_out {T_interstage} K must be positive")

        n_stages, stage_ratio = stage_plan(inlet.P, P_discharge, max_ratio)

        z, flow = inlet.composition, inlet.molar_flow
        current = inlet
        power_W = 0.0
        duty_W = 0.0
        info: dict[str, float] = {"stages": float(n_stages), "stage_pressure_ratio": stage_ratio}
        for stage in range(1, n_stages + 1):
            P_stage = inlet.P * stage_ratio**stage
            discharge = _compress_stage(thermo, z, flow, current, P_stage, eta)
            power_W += flow * (discharge.enthalpy - current.enthalpy)
            info[f"stage_{stage}_P_discharge"] = discharge.P
            if stage < n_stages:
                cooled = thermo.flash_pt(z, T_interstage, P_stage, flow)
                stage_duty = flow * (cooled.enthalpy - discharge.enthalpy)
                duty_W += stage_duty
                info[f"stage_{stage}_intercooler_duty_W"] = stage_duty
                current = cooled
            else:
                current = discharge

        info["total_power_W"] = power_W
        info["total_intercooler_duty_W"] = duty_W
        return UnitResult(
            outlets={"gas_out": current},
            duty_W=duty_W,
            power_W=power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Dry separator gas (the compressor example basis) at 3.447 MPa, two-stage to 15 MPa.

        50 MMSCFD, 322.15 K so the feed is single-phase vapor; the total ratio
        4.35 exceeds the 3.5 per-stage cap, so the default params exercise two
        stages with one intercooler.
        """
        dry = {cid: x for cid, x in INLET_COMPOSITION.items() if cid != "H2O"}
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 3.447e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        return {"gas_in": feed}, {
            "P_discharge": 15.0e6,
            "eta_isentropic": 0.75,
            "T_interstage_out": 322.15,
        }
