"""Control valve, R1: IEC 60534-2-1 sizing and rating with choked flow and an
inherent Cv curve (spec ``specs/backend/units/control_valve.md``).

The pure functions below are the IEC 60534-2-1:2011 (= ANSI/ISA-75.01.01-2007)
sizing core, evaluated by ``fluids.control_valve`` (verified against the
standard's worked inputs to 1e-12 relative in this module's tests):

- liquid, non-choked turbulent (eq. 1): ``Kv = Q/N1*sqrt((rho1/rho0)/dP)``,
  ``N1 = 0.1`` (Q in m3/h, dP in kPa), ``rho0 = 999.10329 kg/m3``;
- liquid pressure-ratio factor (eq. 4): ``FF = 0.96 - 0.28*sqrt(Psat/Pc)``;
- liquid choked when ``dP >= FL^2*(P1 - FF*Psat)`` (eq. 2), then
  ``Kv = Q/(N1*FL)*sqrt((rho1/rho0)/(P1 - FF*Psat))`` (eq. 3);
- gas (eqs. 8/10/13, volumetric form, ``N9 = 24.6`` at 0 degC, 101.325 kPa):
  ``x = dP/P1``, ``Fgamma = gamma/1.4``,
  ``Y = 1 - x/(3*Fgamma*xT)`` (eq. 10); choked when ``x >= Fgamma*xT``,
  in which case ``x`` is replaced by ``Fgamma*xT`` and ``Y = 2/3``;
  ``Kv = Q_std/(N9*P1*Y)*sqrt(M*T1*Z1/x)``;
- standard volumetric gas flow (eq. 5): ``Q_std = n*R*273.15/101325`` m3/s.

``Q`` reaching ``fluids`` is m3/s (liquid: at inlet conditions; gas: at
273.15 K / 101325 Pa — the standard-volumetric basis of ``N9``); ``fluids``
converts to the standard's m3/h and kPa internally.

US ``Cv = Kv/0.865`` (:data:`KV_PER_CV`, IEC 60534-1 Annex — the same
constant as ``ngdesign.sizing.control_valve._KV_PER_CV``).

The inherent flow characteristic (IEC 60534-2-4 / ISA-75.11.01) maps relative
travel ``l`` to ``phi = Kv(l)/Kv_rated``: linear ``phi = l``; equal percentage
``phi = R^(l-1)``; quick opening ``phi = sqrt(l)``.

The adapter :class:`ControlValveR1` wraps these in the unit contract:
sizing mode (spec ``P_out``/``dP``, optional ``Cv_rated``) and rating mode
(``Cv_rated`` + ``opening``, solve for ``P_out`` by bracketing between the
choked capacity and ``P1``).
"""

from __future__ import annotations

import math
from typing import Any, Final, Literal

from fluids.control_valve import (
    size_control_valve_g,
    size_control_valve_l,
)

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.control_valve import ControlValveSpecError

__all__ = [
    "ControlValveRatingError",
    "ControlValveR1",
    "ChokedCapacityError",
    "KV_PER_CV",
    "VMOL_STD",
    "characteristic",
    "characteristic_inverse",
    "kv_gas",
    "kv_liquid",
]

#: 1 US Cv = 0.865 metric Kv (m3/h per bar^0.5), IEC 60534-1 Annex; the same
#: constant as ``ngdesign.sizing.control_valve._KV_PER_CV`` (R0).
KV_PER_CV: Final[float] = 0.865

#: Molar volume of an ideal gas at 273.15 K and 101325 Pa, m3/mol
#: (eq. 5: R*273.15/101325 with R = 8.31446261815324 J/(mol K)).
VMOL_STD: Final[float] = 8.31446261815324 * 273.15 / 101325.0

CharacteristicKind = Literal["linear", "equal_percentage", "quick_opening"]

_KINDS: Final[tuple[str, ...]] = ("linear", "equal_percentage", "quick_opening")


def characteristic(travel: float, kind: str, R: float = 50.0) -> float:
    """Inherent flow characteristic ``phi(l) = Kv(l)/Kv_rated`` (IEC 60534-2-4).

    linear: ``phi = l``; equal percentage: ``phi = R**(l-1)``; quick opening:
    ``phi = sqrt(l)``. Relative travel ``l`` in (0, 1]. (The first parameter is
    named ``travel``; the standard's symbol is ``l``.)
    """
    if kind not in _KINDS:
        raise ControlValveSpecError(f"characteristic {kind!r} is not one of {list(_KINDS)}")
    if not 0.0 < travel <= 1.0:
        raise ControlValveSpecError(f"opening {travel} outside (0, 1]")
    if kind == "linear":
        return travel
    if kind == "equal_percentage":
        return float(float(R) ** (travel - 1.0))
    return math.sqrt(travel)


def characteristic_inverse(phi: float, kind: str, R: float = 50.0) -> float:
    """Inverse characteristic: relative travel ``l`` from ``phi`` in (0, 1].

    linear: ``l = phi``; equal percentage: ``l = 1 + ln(phi)/ln(R)``; quick
    opening: ``l = phi**2``.
    """
    if kind not in _KINDS:
        raise ControlValveSpecError(f"characteristic {kind!r} is not one of {list(_KINDS)}")
    if not 0.0 < phi <= 1.0:
        raise ControlValveSpecError(f"phi {phi} outside (0, 1]")
    if kind == "linear":
        return phi
    if kind == "equal_percentage":
        return 1.0 + math.log(phi) / math.log(R)
    return phi * phi


def kv_liquid(
    Q_m3_s: float,
    rho: float,
    mu: float,
    Psat: float,
    Pc: float,
    P1: float,
    P2: float,
    FL: float,
    Fd: float,
    D1_m: float | None = None,
    D2_m: float | None = None,
    d_m: float | None = None,
) -> dict[str, float]:
    """IEC 60534-2-1 liquid Kv (m3/h per bar^0.5) for one operating point.

    ``Q_m3_s`` is the liquid volumetric flow at inlet conditions; pressures in
    Pa. Calls ``fluids.control_valve.size_control_valve_l`` (eqs. 1-4) with
    ``allow_laminar=True`` and ``full_output=True``; fittings (``FP``, ``FLP``)
    are applied by fluids when all three diameters are passed. Returns
    ``{Kv, choked, FR, FP}`` (``FR``/``FP`` 1.0 when no fittings apply).
    """
    out: Any = size_control_valve_l(
        rho=rho,
        Psat=Psat,
        Pc=Pc,
        mu=mu,
        P1=P1,
        P2=P2,
        Q=Q_m3_s,
        D1=D1_m,
        D2=D2_m,
        d=d_m,
        FL=FL,
        Fd=Fd,
        allow_choked=True,
        allow_laminar=True,
        full_output=True,
    )
    return {
        "Kv": float(out["Kv"]),
        "choked": 1.0 if out["choked"] else 0.0,
        "FR": 1.0 if out["FR"] is None else float(out["FR"]),
        "FP": 1.0 if out["FP"] is None else float(out["FP"]),
    }


def kv_gas(
    n_mol_s: float,
    MW: float,
    mu: float,
    gamma: float,
    Z: float,
    T: float,
    P1: float,
    P2: float,
    xT: float,
    FL: float,
    Fd: float,
    D1_m: float | None = None,
    D2_m: float | None = None,
    d_m: float | None = None,
) -> dict[str, float]:
    """IEC 60534-2-1 gas Kv (m3/h per bar^0.5) for one operating point.

    ``n_mol_s`` is the molar flow; the flow passed to fluids is the standard
    volumetric flow ``Q_std = n*VMOL_STD`` (eq. 5), the basis of ``N9 = 24.6``
    — not the actual inlet volumetric flow. Pressures in Pa. Calls
    ``fluids.control_valve.size_control_valve_g`` (eqs. 8/10/13) with
    ``allow_laminar=True`` and ``full_output=True``. Returns
    ``{Kv, choked, FR, FP, Y}``.
    """
    out: Any = size_control_valve_g(
        T=T,
        MW=MW,
        mu=mu,
        gamma=gamma,
        Z=Z,
        P1=P1,
        P2=P2,
        Q=n_mol_s * VMOL_STD,
        D1=D1_m,
        D2=D2_m,
        d=d_m,
        FL=FL,
        Fd=Fd,
        xT=xT,
        allow_choked=True,
        allow_laminar=True,
        full_output=True,
    )
    return {
        "Kv": float(out["Kv"]),
        "choked": 1.0 if out["choked"] else 0.0,
        "FR": 1.0 if out["FR"] is None else float(out["FR"]),
        "FP": 1.0 if out["FP"] is None else float(out["FP"]),
        "Y": float(out["Y"]),
    }


class ChokedCapacityError(ControlValveSpecError):
    """Rating demand exceeds the valve's choked capacity at the given opening."""


class ControlValveRatingError(ControlValveSpecError):
    """The rating-mode outlet-pressure solve did not converge."""


class ControlValveR1:
    """IEC 60534-2-1 control valve with choked flow and a Cv curve (R1).

    Sizing mode (exactly one of ``P_out``/``dP``, optional ``Cv_rated``):
    computes the required Kv at the spec pressure drop and, when ``Cv_rated``
    is given, the relative travel that delivers it. Rating mode (``Cv_rated``
    + ``opening``, neither ``P_out`` nor ``dP``): solves the outlet pressure
    whose Kv equals the available capacity between the choked capacity and
    ``P1`` (step 3 of the spec).

    Isenthalpic (``flash_ph`` to ``P2``), so ``duty_W = power_W = 0`` and the
    V0 balances close exactly, as at R0.
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
        rating = not ("P_out" in params or "dP" in params)

        FL = float(params.get("FL", 0.9))
        Fd = float(params.get("Fd", 1.0))
        xT = float(params.get("xT", 0.7))
        for name, v in (("FL", FL), ("Fd", Fd), ("xT", xT)):
            if not 0.0 < v <= 1.0:
                raise ControlValveSpecError(f"{name} {v} outside (0, 1]")
        kind = str(params.get("characteristic", "linear"))
        rangeability = float(params.get("rangeability", 50.0))
        if rangeability <= 1.0:
            raise ControlValveSpecError(f"rangeability {rangeability} must be > 1")

        D1_m, D2_m, d_m = _pipe_diameters(params)
        if rating:
            if "Cv_rated" not in params or "opening" not in params:
                raise ControlValveSpecError("rating mode needs Cv_rated and opening")
            if D1_m is not None:
                raise ControlValveSpecError("piping geometry factors are supported in sizing mode only")
            opening = float(params["opening"])
            if not 0.0 < opening <= 1.0:
                raise ControlValveSpecError(f"opening {opening} outside (0, 1]")
        else:
            P2 = _outlet_pressure(inlet.P, params)
            if P2 >= inlet.P:
                raise ControlValveSpecError(
                    "zero pressure drop: Kv is unbounded (the valve does nothing)"
                )

        phase_code = _phase_code(inlet)
        P1 = inlet.P
        if phase_code == 0:
            liquid = _liquid_phase(inlet)
            rho = liquid.density
            mu = liquid.viscosity
            if mu is None and params.get("mu_liquid") is not None:
                mu = float(params["mu_liquid"])
            if mu is None:
                raise ControlValveSpecError("liquid viscosity unavailable; pass mu_liquid")
            Psat = _psat(inlet, thermo)
            Pc = _average_Pc(inlet)
            Q_m3_s = inlet.mass_flow / rho
            kv = kv_liquid(
                Q_m3_s=Q_m3_s, rho=rho, mu=mu, Psat=Psat, Pc=Pc,
                P1=P1, P2=P2, FL=FL, Fd=Fd, D1_m=D1_m, D2_m=D2_m, d_m=d_m,
            )
            P2_choke = float(control_valve_choke_P_l(Psat=Psat, Pc=Pc, FL=FL, P1=P1))
        else:
            vapor = next((p for p in inlet.phases if p.kind is PhaseKind.VAPOR), None)
            if vapor is None:
                raise ControlValveSpecError("inlet has no vapour phase to size")
            MW = vapor.molecular_weight
            Z = vapor.z_factor
            if Z is None:
                raise ControlValveSpecError("vapour z_factor unavailable; cannot size gas")
            mu = vapor.viscosity
            if mu is None and params.get("mu_gas") is not None:
                mu = float(params["mu_gas"])
            if mu is None:
                raise ControlValveSpecError("gas viscosity unavailable; pass mu_gas")
            props = thermo.phase_props(vapor.composition, inlet.T, inlet.P, PhaseKind.VAPOR)
            gamma = props.cp / (props.cp - R_UNIVERSAL)
            if not math.isfinite(gamma) or gamma <= 1.0:
                raise ControlValveSpecError(f"gamma {gamma} must be > 1 (from cp {props.cp})")
            kv = kv_gas(
                n_mol_s=inlet.molar_flow, MW=MW, mu=mu, gamma=gamma, Z=Z, T=inlet.T,
                P1=P1, P2=P2, xT=xT, FL=FL, Fd=Fd, D1_m=D1_m, D2_m=D2_m, d_m=d_m,
            )
            P2_choke = float(control_valve_choke_P_g(xT=xT, gamma=gamma, P1=P1))

        outlet = thermo.flash_ph(inlet.composition, P2, inlet.enthalpy, inlet.molar_flow)
        info: dict[str, float] = {
            "Kv_m3h_bar05": kv["Kv"],
            "Cv": kv["Kv"] / KV_PER_CV,
            "choked": kv["choked"],
            "dP_choke_Pa": P1 - P2_choke,
            "FR": kv["FR"],
            "FP": kv["FP"],
            "P_out_Pa": P2,
            "phase_code": float(phase_code),
            "dT_K": outlet.T - inlet.T,
        }
        if phase_code == 1:
            info["x"] = (P1 - P2) / P1
            info["Y"] = kv["Y"]
        if not rating and "Cv_rated" in params:
            Cv_rated = float(params["Cv_rated"])
            if Cv_rated <= 0:
                raise ControlValveSpecError(f"Cv_rated {Cv_rated} must be > 0")
            required_Cv = kv["Kv"] / KV_PER_CV
            phi = kv["Kv"] / (KV_PER_CV * Cv_rated)
            if phi > 1.0:
                raise ControlValveSpecError(
                    f"required Cv {required_Cv} exceeds Cv_rated {Cv_rated}"
                )
            info["travel"] = characteristic_inverse(phi, kind, rangeability)
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=0.0, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Propane letdown basis (the R0 example) plus a rated capacity."""
        feed = {
            "T": 294.261,
            "P": 2.16978e6,
            "molar_flow": 574.66,
            "composition": {"C3": 1.0},
        }
        return {"inlet": feed}, {"P_out": 1.997411e6, "Cv_rated": 125.0, "mu_liquid": 1.0371e-4}


def _phase_code(inlet: StreamState) -> int:
    """0 liquid, 1 gas; refuse a two-phase inlet (IEC 60534-2-1 is single-phase)."""
    if inlet.vapor_fraction <= 0.001:
        return 0
    if inlet.vapor_fraction >= 0.999:
        return 1
    raise ControlValveSpecError(
        f"two-phase flow is outside IEC 60534-2-1 (inlet vapor_fraction {inlet.vapor_fraction:.4f})"
    )


def _liquid_phase(state: StreamState) -> Any:
    """Dominant liquid phase of an all-liquid inlet (the R0 rule)."""
    liquids = [p for p in state.phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        raise ControlValveSpecError("inlet has no liquid phase to size")
    return max(liquids, key=lambda p: p.mole_fraction)


def _psat(inlet: StreamState, thermo: Thermo) -> float:
    """Inlet vapour pressure: pure-component Psat, or the bubble point for a mixture."""
    if len(inlet.composition) == 1:
        cid = next(iter(inlet.composition))
        psat = thermo.pure_psat(cid, inlet.T)
        if psat is None:
            raise ControlValveSpecError(f"pure_psat unavailable for {cid} at {inlet.T} K")
        return float(psat)
    return float(thermo.bubble_point(inlet.composition, T=inlet.T).P)


def _average_Pc(inlet: StreamState) -> float:
    """Molar average of the pure critical pressures (Kay's rule)."""
    db = components()
    return sum(x * float(db[cid]["pc_Pa"]) for cid, x in inlet.composition.items())


def _pipe_diameters(params: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Validated (D1_m, D2_m, d_m): all three or none, > 0, d <= min(D1, D2)."""
    given = [name for name in ("D1_m", "D2_m", "d_m") if params.get(name) is not None]
    if not given:
        return None, None, None
    if len(given) < 3:
        raise ControlValveSpecError(
            f"D1_m, D2_m, d_m must all be given or none (missing {set(('D1_m', 'D2_m', 'd_m')) - set(given)})"
        )
    D1_m, D2_m, d_m = (float(params[name]) for name in ("D1_m", "D2_m", "d_m"))
    if D1_m <= 0 or D2_m <= 0 or d_m <= 0:
        raise ControlValveSpecError(f"D1_m, D2_m, d_m must be > 0 (got {D1_m}, {D2_m}, {d_m})")
    if d_m > min(D1_m, D2_m):
        raise ControlValveSpecError(
            f"D1_m, D2_m, d_m: valve d_m {d_m} exceeds the smaller pipe {min(D1_m, D2_m)}"
        )
    return D1_m, D2_m, d_m
