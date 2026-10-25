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

    Step-1 scope: the module-level pure functions above. Sizing and rating
    adapters follow in steps 2 and 3 of the spec.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        raise NotImplementedError("ControlValveR1 solve lands in spec steps 2-3")
