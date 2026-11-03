"""Control valve R1: IEC 60534-2-1 sizing and rating (``specs/backend/units/control_valve.md``).

Sizing and choked-flow equations are the ``fluids`` implementation of IEC 60534-2-1:2011
(= ANSI/ISA-75.01.01-2007), called and never re-derived:

- liquid, non-choked (eq. 1) Kv = Q/N1*sqrt((rho1/rho0)/dP); choked when dP >=
  FL**2*(P1 - FF*Psat) (eq. 2) with FF = 0.96 - 0.28*sqrt(Psat/Pc) (eq. 4), then eq. 3;
- gas (eqs. 8, 10, 13) x = dP/P1, Fgamma = gamma/1.4, Y = 1 - x/(3*Fgamma*xT), choked
  when x >= Fgamma*xT.  fluids takes the volumetric flow at 273.15 K and 101325 Pa.
- Kv = 0.865*Cv (IEC 60534-1 Annex), the constant of ``sizing.control_valve``.

The inherent characteristic phi(l) = Kv(l)/Kv,rated is IEC 60534-2-4 / ISA-75.11.01:
linear phi = l, equal percentage phi = R**(l - 1), quick opening phi = sqrt(l).

Sizing mode takes P_out or dP; rating mode takes neither, and solves the P2 at which
the valve's available Kv passes the flow.  Both flash isenthalpically to P2, as R0.
"""

from __future__ import annotations

import math
from typing import Any

from fluids.control_valve import (
    control_valve_choke_P_g,
    control_valve_choke_P_l,
    size_control_valve_g,
    size_control_valve_l,
)
from scipy.optimize import brentq

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.units._physics.kinetics import R
from ngdesign.units.flow.control_valve import ControlValve, ControlValveSpecError, _outlet_pressure

#: Kv per US Cv (IEC 60534-1 Annex), as ``sizing.control_valve``.
_KV_PER_CV = 0.865

#: Molar volume of an ideal gas at 273.15 K and 101325 Pa, m3/mol: the basis of N9.
VM_STD = R * 273.15 / 101325.0

_CHARACTERISTICS = ("linear", "equal_percentage", "quick_opening")


class ChokedCapacityError(ControlValveSpecError):
    """The flow exceeds the choked capacity of the valve at this opening."""


class ControlValveRatingError(ControlValveSpecError):
    """The rating solve failed."""


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
    """Metric Kv of a liquid (IEC 60534-2-1 eqs. 1-4) through ``fluids``."""
    out: Any = size_control_valve_l(
        rho, Psat, Pc, mu, P1, P2, Q_m3_s, D1=D1_m, D2=D2_m, d=d_m, FL=FL, Fd=Fd, full_output=True
    )
    return {
        "Kv": float(out["Kv"]),
        "choked": 1.0 if out["choked"] else 0.0,
        "FR": float(out["FR"] if out["FR"] is not None else 1.0),
        "FP": float(out["FP"] if out["FP"] is not None else 1.0),
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
    """Metric Kv of a gas (IEC 60534-2-1 eqs. 8, 10, 13) through ``fluids``."""
    out: Any = size_control_valve_g(
        T,
        MW,
        mu,
        gamma,
        Z,
        P1,
        P2,
        n_mol_s * VM_STD,
        D1=D1_m,
        D2=D2_m,
        d=d_m,
        FL=FL,
        Fd=Fd,
        xT=xT,
        full_output=True,
    )
    return {
        "Kv": float(out["Kv"]),
        "choked": 1.0 if out["choked"] else 0.0,
        "FR": float(out["FR"] if out["FR"] is not None else 1.0),
        "FP": float(out["FP"] if out["FP"] is not None else 1.0),
        "Y": float(out["Y"]),
    }


def characteristic(l: float, kind: str, R_range: float) -> float:  # noqa: E741
    """Inherent characteristic phi(l) at relative travel l."""
    if kind == "linear":
        return l
    if kind == "equal_percentage":
        return float(R_range ** (l - 1.0))
    return math.sqrt(l)


def characteristic_inverse(phi: float, kind: str, R_range: float) -> float:
    """Relative travel l at phi."""
    if kind == "linear":
        return phi
    if kind == "equal_percentage":
        return 1.0 + math.log(phi) / math.log(R_range)
    return phi**2


def _fraction(params: dict[str, Any], key: str, default: float) -> float:
    value = float(params.get(key, default))
    if not 0.0 < value <= 1.0:
        raise ControlValveSpecError(f"{key} {value} outside (0, 1]")
    return value


class ControlValveR1:
    """IEC 60534-2-1 control valve, in sizing or rating mode."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        vf = float(inlet.vapor_fraction)
        if 0.001 < vf < 0.999:
            raise ControlValveSpecError("two-phase flow is outside IEC 60534-2-1")
        is_liquid = vf <= 0.001
        fl = _fraction(params, "FL", 0.9)
        fd = _fraction(params, "Fd", 1.0)
        xt = _fraction(params, "xT", 0.7)
        kind = params.get("characteristic", "linear")
        if kind not in _CHARACTERISTICS:
            raise ControlValveSpecError(f"characteristic {kind!r} is not one of {_CHARACTERISTICS}")
        rangeability = float(params.get("rangeability", 50.0))
        if rangeability <= 1.0:
            raise ControlValveSpecError(f"rangeability {rangeability} must be > 1")
        diameters = [params.get(k) for k in ("D1_m", "D2_m", "d_m")]
        given = [d is not None for d in diameters]
        if any(given) and not all(given):
            raise ControlValveSpecError("give all or none of D1_m, D2_m, d_m")
        d1, d2, d = (None, None, None) if not all(given) else tuple(float(x) for x in diameters)  # type: ignore[arg-type]
        if d1 is not None and d2 is not None and d is not None and (min(d1, d2, d) <= 0.0 or d > min(d1, d2)):
            raise ControlValveSpecError("D1_m, D2_m, d_m must be > 0 with d_m <= min(D1_m, D2_m)")

        rating = "P_out" not in params and "dP" not in params
        cv_rated = params.get("Cv_rated")
        if rating and (cv_rated is None or params.get("opening") is None):
            raise ControlValveSpecError("rating mode needs Cv_rated and opening")
        if rating and all(given):
            raise ControlValveSpecError("piping geometry factors are supported in sizing mode only")

        info: dict[str, float] = {}
        if is_liquid:
            kv_of, p_choke = self._liquid(inlet, params, thermo, fl, fd, d1, d2, d)
            info["phase_code"] = 0.0
        else:
            kv_of, p_choke, x_of = self._gas(inlet, params, thermo, xt, fl, fd, d1, d2, d)
            info["phase_code"] = 1.0

        if rating:
            opening = float(params["opening"])
            if not 0.0 < opening <= 1.0:
                raise ControlValveSpecError(f"opening {opening} outside (0, 1]")
            kv_available = _KV_PER_CV * float(cv_rated) * characteristic(opening, kind, rangeability)  # type: ignore[arg-type]
            p2 = self._rate(float(inlet.P), kv_available, p_choke, opening, lambda p: kv_of(p)["Kv"])
            info["opening"] = opening
        else:
            p2 = _outlet_pressure(float(inlet.P), params)
            if p2 == inlet.P:
                raise ControlValveSpecError("zero pressure drop: Kv is unbounded")

        result = kv_of(p2)
        kv = result["Kv"]
        cv = kv / _KV_PER_CV
        if not rating and cv_rated is not None:
            if cv > float(cv_rated):
                raise ControlValveSpecError(f"required Cv {cv} exceeds Cv_rated {cv_rated}")
            info["travel"] = characteristic_inverse(cv / float(cv_rated), kind, rangeability)

        outlet = thermo.flash_ph(dict(inlet.composition), p2, inlet.enthalpy, inlet.molar_flow)
        info.update(
            {
                "Kv_m3h_bar05": kv,
                "Cv": cv,
                "choked": result["choked"],
                "dP_choke_Pa": float(inlet.P) - p_choke,
                "FR": result["FR"],
                "FP": result["FP"],
                "P_out_Pa": p2,
                "dT_K": outlet.T - inlet.T,
            }
        )
        if not is_liquid:
            info["x"] = x_of(p2)
            info["Y"] = result["Y"]
        return UnitResult(outlets={"outlet": outlet}, duty_W=0.0, power_W=0.0, info=info)

    @staticmethod
    def _rate(p1: float, kv_available: float, p_choke: float, opening: float, kv: Any) -> float:
        """P2 where Kv(P2) = Kv_avail; Kv rises monotonically with P2 above the choke."""
        kv_choke = kv(p_choke * (1.0 - 1.0e-12))
        if kv_available < kv_choke * (1.0 - 1.0e-9):
            raise ChokedCapacityError(
                f"flow exceeds the choked capacity of the valve at opening {opening}: "
                f"Kv available {kv_available}, Kv at choke {kv_choke}"
            )
        lo, hi = p_choke, p1 * (1.0 - 1.0e-9)
        try:
            return float(brentq(lambda p: kv(p) - kv_available, lo, hi, xtol=1.0e-9 * p1, maxiter=100))
        except (RuntimeError, ValueError) as exc:
            raise ControlValveRatingError(
                f"rating did not converge: P1 {p1}, Kv available {kv_available}, bracket [{lo}, {hi}]: {exc}"
            ) from exc

    @staticmethod
    def _liquid(
        inlet: StreamState,
        params: dict[str, Any],
        thermo: Thermo,
        fl: float,
        fd: float,
        d1: float | None,
        d2: float | None,
        d: float | None,
    ) -> tuple[Any, float]:
        liquids = [p for p in inlet.phases if p.kind is not PhaseKind.VAPOR]
        phase = max(liquids, key=lambda p: p.mole_fraction)
        mu = phase.viscosity if phase.viscosity is not None else params.get("mu_liquid")
        if mu is None:
            raise ControlValveSpecError("liquid viscosity unavailable; pass mu_liquid")
        z = dict(inlet.composition)
        if len(z) == 1:
            psat = thermo.pure_psat(next(iter(z)), inlet.T)
            if psat is None:
                raise ControlValveSpecError("the package gives no saturation pressure for this liquid")
        else:
            psat = float(thermo.bubble_point(z, T=inlet.T).P)
        db = components()
        pc = math.fsum(x * float(db[cid]["pc_Pa"]) for cid, x in z.items())
        q = inlet.mass_flow / phase.density
        p1 = float(inlet.P)

        def kv_of(p2: float) -> dict[str, float]:
            return kv_liquid(q, phase.density, float(mu), psat, pc, p1, p2, fl, fd, d1, d2, d)

        return kv_of, float(control_valve_choke_P_l(psat, pc, fl, P1=p1))

    @staticmethod
    def _gas(
        inlet: StreamState,
        params: dict[str, Any],
        thermo: Thermo,
        xt: float,
        fl: float,
        fd: float,
        d1: float | None,
        d2: float | None,
        d: float | None,
    ) -> tuple[Any, float, Any]:
        phase = next(p for p in inlet.phases if p.kind is PhaseKind.VAPOR)
        if phase.z_factor is None:
            raise ControlValveSpecError("the package reports no z_factor for this gas")
        mu = phase.viscosity if phase.viscosity is not None else params.get("mu_gas")
        if mu is None:
            raise ControlValveSpecError("gas viscosity unavailable; pass mu_gas")
        cp = float(thermo.phase_props(dict(inlet.composition), inlet.T, inlet.P, PhaseKind.VAPOR).cp)
        gamma = cp / (cp - R) if cp > R else 0.0
        if gamma <= 1.0:
            raise ControlValveSpecError(f"gamma {gamma} must be > 1")
        p1 = float(inlet.P)
        n, mw, z_factor, t = float(inlet.molar_flow), float(phase.molecular_weight), phase.z_factor, inlet.T

        def kv_of(p2: float) -> dict[str, float]:
            return kv_gas(n, mw, float(mu), gamma, z_factor, t, p1, p2, xt, fl, fd, d1, d2, d)

        return kv_of, float(control_valve_choke_P_g(xt, gamma, P1=p1)), lambda p2: (p1 - p2) / p1

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 propane letdown with an illustrative rated valve (test input)."""
        feeds, params = ControlValve.example_case()
        return feeds, {
            "P_out": params["P_out"],
            "Cv_rated": 200.0,
            "characteristic": "equal_percentage",
            "mu_liquid": 1.0e-4,
        }
