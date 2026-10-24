"""Control valve, R0 (spec U-B, plan §2 U-B 6).

Method (spec): isenthalpic PH flash to ``outlet_P`` (or ``dP``). When the
inlet is all liquid, info carries ``Cv`` from
:func:`ngdesign.sizing.control_valve.cv_liquid_isa` (the repo's one owner for
ISA/IEC 60534 liquid sizing), divided by the user-supplied piping geometry
factor ``Fp`` (default 1.0). The ``choked`` flag comes from the ISA liquid
criterion as implemented by ``fluids.control_valve.is_choked_turbulent_l``
with ``FF = 0.96 - 0.28*sqrt(Psat/Pc)`` (IEC 60534-2-1) and the valve's
liquid pressure-recovery factor ``FL`` (default 0.9). Vapour or two-phase Cv
is reported as not-applicable at R0 — never invented. ISA sizing needs a
positive viscosity; when the thermo package reports none, an optional
``mu_liquid`` param supplies it, otherwise ``Cv`` is not reported. ``Cv``
is also not reported at zero pressure drop (nothing to size).
"""

from __future__ import annotations

from typing import Any

from fluids.control_valve import FF_critical_pressure_ratio_l, is_choked_turbulent_l

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.sizing.control_valve import cv_liquid_isa


class ControlValveSpecError(ValueError):
    """Typed refusal naming the parameter of a bad control-valve spec."""


def _outlet_pressure(inlet_P: float, params: dict[str, Any]) -> float:
    has_P_out = "P_out" in params
    has_dP = "dP" in params
    if has_P_out == has_dP:
        raise ControlValveSpecError("exactly one of P_out / dP must be given")
    if has_P_out:
        P_out = float(params["P_out"])
        if P_out <= 0:
            raise ControlValveSpecError(f"P_out {P_out} Pa must be > 0")
        if P_out > inlet_P:
            raise ControlValveSpecError(
                f"P_out {P_out} Pa is above the inlet pressure {inlet_P} Pa; a valve cannot raise pressure"
            )
        return P_out
    dP = float(params["dP"])
    if dP < 0:
        raise ControlValveSpecError(f"dP {dP} Pa must be >= 0 (a valve drops pressure)")
    return inlet_P - dP


def _liquid_phase(state: StreamState) -> Any:
    """Dominant liquid phase, or None for a vapour/two-phase inlet (Cv not applicable)."""
    if state.vapor_fraction > 0.001:
        return None
    liquids = [p for p in state.phases if p.kind is not PhaseKind.VAPOR]
    return max(liquids, key=lambda p: p.mole_fraction) if liquids else None


class ControlValve:
    """Isenthalpic throttling valve with an ISA liquid Cv report (R0)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        P_out = _outlet_pressure(inlet.P, params)

        info: dict[str, float] = {}
        liquid = _liquid_phase(inlet)
        mu = liquid.viscosity if liquid is not None else None
        if mu is None and params.get("mu_liquid") is not None:
            mu = float(params["mu_liquid"])
        if liquid is not None and mu is not None and P_out < inlet.P:
            info.update(self._cv_info(inlet, params, thermo, liquid.density, mu))
        else:
            # Vapour/two-phase Cv is not applicable at R0, and a zero-dP inlet
            # has nothing to size: cv_liquid_isa needs a positive drop.
            info["cv_reported"] = 0.0

        outlet = thermo.flash_ph(inlet.composition, P_out, inlet.enthalpy, inlet.molar_flow)
        info["dT_K"] = outlet.T - inlet.T
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=0.0, info=info)

    @staticmethod
    def _cv_info(
        inlet: StreamState, params: dict[str, Any], thermo: Thermo, rho: float, mu: float
    ) -> dict[str, float]:
        """Cv (divided by Fp) and the ISA choked flag for an all-liquid inlet."""
        Fp = float(params.get("Fp", 1.0))
        FL = float(params.get("FL", 0.9))
        if not 0.0 < Fp <= 1.0:
            raise ControlValveSpecError(f"Fp {Fp} outside (0, 1]")
        if not 0.0 < FL <= 1.0:
            raise ControlValveSpecError(f"FL {FL} outside (0, 1]")
        if mu <= 0:
            raise ControlValveSpecError(f"liquid viscosity {mu} Pa.s must be > 0")

        Psat_Pa = 0.0
        Pc_Pa = 0.0
        db = components()
        for cid, x in inlet.composition.items():
            psat = thermo.pure_psat(cid, inlet.T)
            if psat is not None:
                Psat_Pa += x * psat
            Pc_Pa += x * float(db[cid]["pc_Pa"])

        Q = inlet.mass_flow / rho  # m3/s at inlet conditions
        cv = (
            cv_liquid_isa(
                Q_m3_s=Q,
                rho=rho,
                Psat_Pa=Psat_Pa,
                Pc_Pa=Pc_Pa,
                mu=mu,
                P1_Pa=inlet.P,
                P2_Pa=_valve_outlet_P(inlet, params),
            )
            / Fp
        )

        ff = FF_critical_pressure_ratio_l(Psat=Psat_Pa, Pc=Pc_Pa)
        choked = is_choked_turbulent_l(
            dP=inlet.P - _valve_outlet_P(inlet, params),
            P1=inlet.P,
            Psat=Psat_Pa,
            FF=ff,
            FL=FL,
        )
        return {"Cv": cv, "choked": 1.0 if choked else 0.0, "Fp": Fp, "cv_reported": 1.0}

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Propane letdown basis (Emerson CVH liquid example state): 294.26 K, ~2.17 MPa."""
        feed = {
            "T": 294.261,
            "P": 2.16978e6,
            "molar_flow": 574.66,
            "composition": {"C3": 1.0},
        }
        return {"inlet": feed}, {"P_out": 1.997411e6, "Fp": 1.0}


def _valve_outlet_P(inlet: StreamState, params: dict[str, Any]) -> float:
    """The valve outlet pressure already validated by solve(); mirrors _outlet_pressure."""
    return float(params["P_out"]) if "P_out" in params else inlet.P - float(params["dP"])
