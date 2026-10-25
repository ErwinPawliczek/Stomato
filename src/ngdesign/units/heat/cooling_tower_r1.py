"""Cooling tower R1: Merkel number (Chebyshev 4-point) against a tower characteristic.

Spec ``specs/backend/units/cooling_tower.md`` (U-R2 level wave). The R1 level
solves the WATER OUTLET temperature from the Merkel equation

    KaV/L = integral from T_out to T_in of c_pw dT / (h_s(T) - h_a(T))

(Merkel 1925; ASHRAE Handbook HVAC Systems and Equipment, Ch. 40; CTI
ATC-105) matched to the tower characteristic KaV/L = C (L/G)^-n, then
delegates to the R0 adapter
(:class:`ngdesign.units.heat.cooling_tower.CoolingTower`) at the solved
approach, so every outlet, the energy closure and the blowdown/makeup split
are R0's by construction. Merkel's assumptions: evaporation loss neglected
in L, and a Lewis factor of 1.

Enthalpies are per kg of DRY AIR on the same ideal-saturated construction as
R0's private ``_humid_enthalpy`` (re-implemented here): h(T, y) = [(1 - y)
h_dry(T) + y h_vap(T)] / [(1 - y) MW_dry / 1000], with the saturation
humidity y_s(T) = p_sat(T) / P from ``thermo.pure_psat("H2O", T)``. The
integration is by the 4-point Chebyshev rule of CTI ATC-105 /
ASHRAE Ch. 40 with abscissae at 0.1, 0.4, 0.6, 0.9 of the range.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ngdesign.contracts.plugins import Thermo

#: Chebyshev abscissae as fractions of the temperature range (CTI ATC-105;
#: ASHRAE Handbook HVAC Systems and Equipment, Ch. 40).
CHEBYSHEV_FRACTIONS: tuple[float, ...] = (0.1, 0.4, 0.6, 0.9)


class CoolingTowerSpecError(ValueError):
    """A cooling-tower spec R1 refuses: a bad parameter or an infeasible state."""


class CoolingTowerConvergenceError(ValueError):
    """The Merkel residual did not bracket a root, or did not converge."""


def tower_characteristic(C: float, n: float, L_over_G: float) -> float:
    """CTI tower characteristic KaV/L = C (L/G)^-n (dimensionless)."""
    return C * L_over_G ** (-n)


def operating_line(
    h_a_in: float,
    L_over_G: float,
    c_pw: float,
    T_out: float,
) -> Callable[[float], float]:
    """Bulk-air enthalpy on the operating line, kJ/kg_da.

    h_a(T) = h_a,in + (L/G) c_pw (T - T_out), anchored at the cold end
    (T_out) where the air enters the pack.
    """

    def h_a(T: float) -> float:
        return h_a_in + L_over_G * c_pw * (T - T_out)

    return h_a


def merkel_number_chebyshev(
    T_in: float,
    T_out: float,
    L_over_G: float,
    c_pw: float,
    h_s: Callable[[float], float],
    h_a_in: float,
) -> float:
    """Merkel number by 4-point Chebyshev integration (dimensionless).

    KaV/L ~ c_pw (T_in - T_out) / 4 * sum_i 1/dh_i, with dh_i = h_s(T_i) -
    h_a(T_i) at T_i = T_out + f_i (T_in - T_out) over
    :data:`CHEBYSHEV_FRACTIONS` (CTI ATC-105; ASHRAE HVAC S&E Ch. 40).

    ``h_s`` is injected (kJ/kg_da callable of T, K), so this integrator is
    independent of any property package. Units: ``c_pw`` kJ/(kg K), ``T`` in
    K. Returns ``math.inf`` when any dh_i <= 0 - the operating line touches
    the saturation curve, i.e. an infinite tower.
    """
    span = T_in - T_out
    h_a = operating_line(h_a_in, L_over_G, c_pw, T_out)
    total = 0.0
    for f in CHEBYSHEV_FRACTIONS:
        dh = h_s(T_out + f * span) - h_a(T_out + f * span)
        if dh <= 0.0:
            return math.inf
        total += 1.0 / dh
    return c_pw * span / 4.0 * total


def _psat(thermo: Thermo, T: float) -> float:
    """Water saturation pressure (Pa); the protocol types it Optional."""
    psat = thermo.pure_psat("H2O", T)
    if psat is None:
        raise ValueError(f"no water saturation pressure available at {T:.2f} K")
    return psat


def _mean_molar_mass(composition: dict[str, float]) -> float:
    """Mean molar mass of a (normalized) composition, g/mol, from the component db."""
    from ngdesign.data import components

    db = components()
    total = sum(composition.values())
    if total <= 0.0:
        raise ValueError("composition has no components")
    return sum(x / total * float(db[cid]["mw"]) for cid, x in composition.items())


def humid_air_enthalpy(
    thermo: Thermo,
    dry: dict[str, float],
    T: float,
    P: float,
    y: float,
) -> float:
    """Ideal humid-air enthalpy per kg of dry air, kJ/kg_da, at humidity y.

    The same construction as R0's private ``_humid_enthalpy`` (re-implemented;
    the R0 helpers are private): each component flashed in its vapour region
    (the water at half its saturation pressure, where the flash is safely all
    gas), the mixture enthalpy ``(1 - y) h_dry(T) + y h_vap(T)`` per mol
    divided by the dry-air mass ``(1 - y) MW_dry / 1000``.
    """
    dry_sum = sum(dry.values())
    if dry_sum <= 0.0:
        raise ValueError("air composition is pure water vapour: no dry gas to humidify")
    z_dry = {cid: x / dry_sum for cid, x in dry.items()}
    h_dry = thermo.flash_pt(z_dry, T, P, 1.0).enthalpy
    h_vap = thermo.flash_pt({"H2O": 1.0}, T, 0.5 * _psat(thermo, T), 1.0).enthalpy
    mw_dry = _mean_molar_mass(z_dry)
    return ((1.0 - y) * h_dry + y * h_vap) / ((1.0 - y) * mw_dry / 1000.0) / 1000.0


def saturated_air_enthalpy(thermo: Thermo, dry: dict[str, float], T: float, P: float) -> float:
    """Enthalpy of air saturated at T, kJ/kg_da, with y_s = p_sat(T) / P."""
    return humid_air_enthalpy(thermo, dry, T, P, _psat(thermo, T) / P)


def water_specific_heat(thermo: Thermo, T_in: float, T_out: float, P_water: float) -> float:
    """Mean liquid-water cp between the water inlet and outlet, kJ/(kg K).

    c_pw = [h_w(T_in) - h_w(T_out)] / [(T_in - T_out) MW_w / 1000], with h_w
    from ``flash_pt({"H2O": 1}, T, P_water, 1)`` (liquid). Only enthalpy
    differences enter, so the reference state cancels.
    """
    h_in = thermo.flash_pt({"H2O": 1.0}, T_in, P_water, 1.0).enthalpy
    h_out = thermo.flash_pt({"H2O": 1.0}, T_out, P_water, 1.0).enthalpy
    mw_w = _mean_molar_mass({"H2O": 1.0})
    return (h_in - h_out) / ((T_in - T_out) * mw_w / 1000.0) / 1000.0
