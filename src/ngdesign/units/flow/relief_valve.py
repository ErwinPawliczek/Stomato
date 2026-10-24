"""Relief valve, R0 (spec U-B, plan §2 U-B 5).

Method (spec): gas service only. The required effective discharge area comes
from :func:`ngdesign.sizing.reliefs.psv_api520_gas` — the repo's one owner for
API 520 Part I §5.6.3.2 gas sizing — evaluated at the inlet relieving
pressure with the per-mass flow converted from the stream, ``k = cp/(cp - R)``
at the inlet vapour (ideal-gas relation; the thermo protocol exposes Cp
only), and the user-supplied ``Kd`` (default 0.975), ``Kb`` (default 1.0,
critical flow) and ``Kc`` (default 1.0). The next API 526 letter orifice at
or above the required area (fluids' API526 table) is selected and its
effective area reported. The outlet is an isenthalpic PH flash at
``P_back``. Liquid or two-phase relief and backpressure at or above the
relieving pressure are refused at R0 (liquid/two-phase sizing needs the
API 520 Part I §5.6 liquid method — a later round).
"""

from __future__ import annotations

from typing import Any

from fluids import API526_A, API526_letters

from ngdesign.contracts import Phase, PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.sizing.psv_gas import psv_api520_gas

#: kg/s per lb/h (1 lb = 0.45359237 kg exactly, 1 h = 3600 s).
LB_PER_H_TO_KG_S = 0.45359237 / 3600.0

#: K per rankine (1 K = 1.8 R exactly).
RANKINE_PER_K = 1.8

#: CODATA 2018 molar gas constant, J/(mol.K) (same reference as thermo.pr).
R_IDEAL = 8.31446261815324


#: in2 per m2 (1 in = 0.0254 m exactly): the fluids API 526 table is in m2.
IN2_PER_M2 = 1.0 / 0.0254**2


class ReliefValveSpecError(ValueError):
    """Typed refusal naming the parameter of a bad relief-valve spec."""


def _orifice_area_in2(letter: str) -> float:
    """Effective area of a named API 526 letter orifice, in in2, from the fluids table."""
    for available_letter, area_m2 in zip(API526_letters, API526_A, strict=True):
        if available_letter == letter:
            return area_m2 * IN2_PER_M2
    raise ReliefValveSpecError(f"API 526 letter {letter!r} not in the fluids table")


def _z_factor(vapor: Phase) -> float:
    """Compressibility of the vapour phase; the PR plugin always reports one."""
    if vapor.z_factor is None:
        raise ReliefValveSpecError("vapour phase carries no compressibility factor")
    return vapor.z_factor


class ReliefValve:
    """Gas pressure-relief valve: API 520 required area and API 526 selection (R0)."""

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
            raise ReliefValveSpecError(
                f"inlet is not all vapour (vapor_fraction={inlet.vapor_fraction:.4f}); "
                "liquid and two-phase relief sizing is refused at R0"
            )
        P_back = float(params["P_back"])
        if not 0.0 < P_back < inlet.P:
            raise ReliefValveSpecError(
                f"P_back {P_back} Pa must be > 0 and below the relieving pressure {inlet.P} Pa"
            )
        Kd = float(params.get("Kd", 0.975))
        Kb = float(params.get("Kb", 1.0))
        Kc = float(params.get("Kc", 1.0))
        for name, value in (("Kd", Kd), ("Kb", Kb), ("Kc", Kc)):
            if not 0.0 < value <= 1.0:
                raise ReliefValveSpecError(f"{name} {value} outside (0, 1]")

        vapor = next(p for p in inlet.phases if p.kind is PhaseKind.VAPOR)
        props = thermo.phase_props(vapor.composition, inlet.T, inlet.P, PhaseKind.VAPOR)
        k = props.cp / (props.cp - R_IDEAL)
        if not k > 1.0:
            raise ReliefValveSpecError(f"Cp/Cv gives k = {k}, must be > 1")

        result = psv_api520_gas(
            W_lb_h=inlet.mass_flow / LB_PER_H_TO_KG_S,
            T_R=inlet.T * RANKINE_PER_K,
            Z=_z_factor(vapor),
            M=vapor.molecular_weight,
            k=k,
            P1_psia=inlet.P / 6894.757293168361,
            Kd=Kd,
            Kb=Kb,
            Kc=Kc,
        )
        required_in2 = float(result["area_in2"])
        letter = _next_orifice(required_in2)
        info = {
            "k_ideal": k,
            "required_area_in2": required_in2,
            "selected_orifice_area_in2": _orifice_area_in2(letter),
        }

        outlet = thermo.flash_ph(inlet.composition, P_back, inlet.enthalpy, inlet.molar_flow)
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Gas relief basis at the API 520 worked example's relieving point.

        348 K / 97.2 psia set point from API 520 Part I Example 3.6.2.2; the
        composition is a stand-in (the example's own mixture is not stated
        beyond M = 65 — see the row note for the V1 adapter-level gap), and
        Kd 0.975 with Kb = Kc = 1.0 (critical flow, no rupture disk) are the
        example's printed factors.
        """
        feed = {
            "T": 348.15,
            "P": 670170.408,
            "molar_flow": 130.128,
            "composition": {"C3": 0.45, "nC4": 0.55},
        }
        return {"inlet": feed}, {"P_back": 101325.0, "Kd": 0.975, "Kc": 1.0}


def _next_orifice(required_in2: float) -> str:
    """First API 526 letter whose effective area (in2) is at or above the required area."""
    for letter, area_m2 in zip(API526_letters, API526_A, strict=True):
        if area_m2 * IN2_PER_M2 >= required_in2:
            return letter
    raise ReliefValveSpecError(f"required area {required_in2} in2 exceeds the largest API 526 orifice")
