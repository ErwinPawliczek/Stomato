"""Reciprocating compressor, R0 (spec U-B, plan §2 U-B 3).

Method (spec): the overall pressure ratio is split into ``n_stages`` equal
per-stage ratios ``r = (P_out/P_in)^(1/n)``; each stage is one
:func:`~ngdesign.units._physics.efficiency.isentropic_step` with
``eta_isentropic``; between stages the gas is intercooled to ``T_intercool``
at the stage discharge pressure, with the cooling duty reported (omitted
``T_intercool`` = adiabatic train). The volumetric efficiency

    E_v = 1 - L - c * (r^(1/k) - 1)

(clearance fraction ``c``, valve-loss allowance ``L``, ``k`` from Cp/Cv at
suction) and the displacement needed for the actual suction flow
(``Q_suction / E_v``) are reported in info. ``k`` uses the ideal-gas relation
``cp/(cp - R)`` — the thermo protocol exposes Cp only; noted in the row.

The existing centrifugal compressor/expander keep their own code this round
(spec: migration is a later byte-identical refactor).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._examples import MMSCFD_TO_MOL_S
from ngdesign.units._physics.efficiency import isentropic_step

#: CODATA 2018 molar gas constant, J/(mol.K) (same reference as thermo.pr).
R_IDEAL = 8.31446261815324


class ReciprocatingCompressorSpecError(ValueError):
    """Typed refusal naming the parameter of a bad compressor spec."""


def _vapor(state: StreamState, what: str) -> Any:
    """The vapor phase of a state; raises if absent."""
    for phase in state.phases:
        if phase.kind == "vapor":
            return phase
    raise ReciprocatingCompressorSpecError(f"{what} has no vapor phase")


def _k_ideal(state: StreamState, thermo: Thermo, what: str) -> float:
    """k = Cp/Cv at a state, via the ideal-gas relation Cp/(Cp - R)."""
    phase = _vapor(state, what)
    props = thermo.phase_props(phase.composition, state.T, state.P, PhaseKind.VAPOR)
    k = props.cp / (props.cp - R_IDEAL)
    if not k > 1.0:
        raise ReciprocatingCompressorSpecError(f"{what}: Cp/Cv gives k = {k}, must be > 1")
    return k


class ReciprocatingCompressor:
    """Multistage reciprocating compressor with clearance-volume losses (R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.vapor_fraction < 0.999:
            raise ReciprocatingCompressorSpecError(
                f"inlet has liquid (vapor_fraction={inlet.vapor_fraction:.4f})"
            )
        P_out = float(params["P_out"])
        if P_out <= inlet.P:
            raise ReciprocatingCompressorSpecError(f"P_out {P_out} Pa must exceed P_in {inlet.P} Pa")
        n_stages = int(params.get("n_stages", 1))
        if n_stages < 1:
            raise ReciprocatingCompressorSpecError(f"n_stages {n_stages} must be >= 1")
        eta = float(params.get("eta_isentropic", 0.75))
        T_intercool = params.get("T_intercool")
        if T_intercool is not None:
            T_intercool = float(T_intercool)
        clearance = float(params.get("clearance", 0.10))
        loss = float(params.get("loss_allowance", 0.0))
        if not 0.0 < eta <= 1.0:
            raise ReciprocatingCompressorSpecError(f"eta_isentropic {eta} outside (0, 1]")
        if not 0.0 <= clearance < 1.0:
            raise ReciprocatingCompressorSpecError(f"clearance {clearance} outside [0, 1)")
        if loss < 0.0:
            raise ReciprocatingCompressorSpecError(f"loss_allowance {loss} must be >= 0")

        ratio_per_stage = (P_out / inlet.P) ** (1.0 / n_stages)
        k_suction = _k_ideal(inlet, thermo, "suction")
        e_v = 1.0 - loss - clearance * (ratio_per_stage ** (1.0 / k_suction) - 1.0)
        if e_v <= 0.0:
            raise ReciprocatingCompressorSpecError(
                f"volumetric efficiency {e_v} <= 0: clearance {clearance} and loss {loss} "
                f"cannot carry stage ratio {ratio_per_stage:.3f} at k = {k_suction:.3f}"
            )
        rho_suction = _vapor(inlet, "suction").density
        q_suction = inlet.mass_flow / rho_suction

        z, flow = inlet.composition, inlet.molar_flow
        state = inlet
        power_W = 0.0
        duty_W = 0.0
        for stage in range(1, n_stages + 1):
            P_stage = inlet.P * ratio_per_stage**stage
            state, stage_power = isentropic_step(state, P_stage, eta, thermo, "compress")
            power_W += stage_power
            if stage < n_stages and T_intercool is not None and T_intercool < state.T:
                cooled = thermo.flash_pt(z, T_intercool, P_stage, flow)
                duty_W += flow * (cooled.enthalpy - state.enthalpy)
                state = cooled

        return UnitResult(
            outlets={"outlet": state},
            duty_W=duty_W,
            power_W=power_W,
            info={
                "pressure_ratio_per_stage": ratio_per_stage,
                "k_suction_ideal": k_suction,
                "volumetric_efficiency": e_v,
                "Q_suction_m3_s": q_suction,
                "displacement_m3_s": q_suction / e_v,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Two-stage basis: dry separator gas, 3.447 -> 8.0 MPa, intercooled to suction T.

        The suction state is the single-phase vapor basis the slice compressor
        example uses (dry gas at 322.15 K); at 1.0 MPa this composition sits in
        PR's retrograde region, which is a letdown design, not a suction basis.
        """
        dry = {
            cid: x
            for cid, x in {
                "N2": 0.005,
                "CO2": 0.015,
                "C1": 0.848,
                "C2": 0.062,
                "C3": 0.032,
                "iC4": 0.007,
                "nC4": 0.010,
                "iC5": 0.004,
                "nC5": 0.004,
                "C6+": 0.010,
            }.items()
        }
        total = sum(dry.values())
        feed = {
            "T": 322.15,
            "P": 3.447e6,
            "molar_flow": 50 * MMSCFD_TO_MOL_S,
            "composition": {cid: x / total for cid, x in dry.items()},
        }
        return {"inlet": feed}, {
            "P_out": 8.0e6,
            "n_stages": 2,
            "eta_isentropic": 0.75,
            "T_intercool": 322.15,
            "clearance": 0.10,
            "loss_allowance": 0.02,
        }
