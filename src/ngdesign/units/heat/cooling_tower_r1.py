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
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.heat.cooling_tower import CoolingTower, wet_bulb
from scipy.optimize import brentq

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
    the R0 helpers are private), with ONE deviation documented as a SPEC ISSUE
    on the PR: the water-vapour term is h_vap(T) - h_w(273.15 K), i.e. the
    vapour enthalpy referenced to liquid water at 273.15 K (the psychrometric
    convention of ASHRAE Fundamentals Ch. 1, h = 1.006 t + W (2501 + 1.86 t)).
    R0's raw ``h_vap(T)`` is only reference-consistent inside R0's wet-bulb
    balance, where the ``(W2 - W1) h_w`` term compensates the package's
    per-component reference offset; the Merkel driving force h_s(T_i) -
    h_a(T_i) compares states of DIFFERENT humidity and has no compensating
    term, so the raw offset (measured: inlet-air enthalpy 1.50 kJ/kg_da on
    the raw scale vs 61.5 kJ/kg_da psychrometric) leaks into every dh_i.
    Each component's offset cancels in this form: dry gas appears once per kg
    of dry air on both sides, and vapour and liquid water share one package
    reference, so h_vap(T) - h_w(273.15 K) is offset-free.
    """
    dry_sum = sum(dry.values())
    if dry_sum <= 0.0:
        raise ValueError("air composition is pure water vapour: no dry gas to humidify")
    z_dry = {cid: x / dry_sum for cid, x in dry.items()}
    h_dry = thermo.flash_pt(z_dry, T, P, 1.0).enthalpy
    h_vap = thermo.flash_pt({"H2O": 1.0}, T, 0.5 * _psat(thermo, T), 1.0).enthalpy
    h_w_ref = thermo.flash_pt({"H2O": 1.0}, 273.15, P, 1.0).enthalpy
    mw_dry = _mean_molar_mass(z_dry)
    w = y / (1.0 - y)
    return (h_dry + w * (h_vap - h_w_ref)) / (mw_dry / 1000.0) / 1000.0


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


class CoolingTowerR1:
    """Cooling tower R1: Merkel number against the tower characteristic.

    The WATER OUTLET is solved from r(T_out) = KaV/L_Chebyshev(T_out) -
    C (L/G)^-n by brentq on (T_wb + 1e-6, T_in - 1e-6); the approach is then
    T_out - T_wb and the R0 adapter closes the balance at that approach, so
    every outlet, the energy closure and the blowdown/makeup split are R0's
    by construction (the identity: R1 equals R0 run at the solved approach,
    bit for bit). L and G are MASS flows: water and dry air, kg/s.
    """

    inlet_ports = ("water_in", "air_in")
    outlet_ports = ("water_out", "air_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        water = inlets["water_in"]
        air = inlets["air_in"]
        if water.molar_flow <= 0.0:
            raise ValueError("cooling tower needs a water stream with positive flow")
        if air.molar_flow <= 0.0:
            raise ValueError("cooling tower needs an air stream with positive flow")

        characteristic_C = params.get("characteristic_C")
        if characteristic_C is None:
            raise CoolingTowerSpecError(
                "cooling tower R1: characteristic_C is required (C in KaV/L = C (L/G)^-n)"
            )
        characteristic_C = float(characteristic_C)
        if characteristic_C <= 0.0:
            raise CoolingTowerSpecError(
                f"cooling tower R1: characteristic_C {characteristic_C} must be > 0"
            )
        characteristic_n = params.get("characteristic_n")
        if characteristic_n is None:
            raise CoolingTowerSpecError(
                "cooling tower R1: characteristic_n is required (n in KaV/L = C (L/G)^-n)"
            )
        characteristic_n = float(characteristic_n)
        if characteristic_n < 0.0:
            raise CoolingTowerSpecError(
                f"cooling tower R1: characteristic_n {characteristic_n} must be >= 0"
            )
        if "approach_K" in params:
            raise CoolingTowerSpecError(
                "cooling tower R1: approach_K is solved at R1; give characteristic_C "
                "and characteristic_n instead"
            )
        cycles = params.get("cycles_of_concentration")
        if cycles is not None and float(cycles) < 1.0:
            raise ValueError(f"cooling tower: cycles_of_concentration {cycles} must be >= 1")

        y1 = air.composition.get("H2O", 0.0)
        dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}
        if sum(dry.values()) <= 0.0:
            raise ValueError("air composition is pure water vapour: no dry gas to humidify")
        mw_dry = _mean_molar_mass(dry)
        mw_water = _mean_molar_mass({"H2O": 1.0})

        # L and G are MASS flows: water (kg/s) and dry air (kg/s).
        L = water.molar_flow * mw_water / 1000.0
        G = air.molar_flow * (1.0 - y1) * mw_dry / 1000.0
        L_over_G = L / G
        characteristic = tower_characteristic(characteristic_C, characteristic_n, L_over_G)

        T_wb = wet_bulb(thermo, air)
        if T_wb >= water.T:
            raise CoolingTowerSpecError(
                f"cooling tower R1: the water inlet {water.T:.2f} K is at or below the "
                f"inlet wet bulb {T_wb:.2f} K: no tower range exists"
            )

        h_a_in = humid_air_enthalpy(thermo, dry, air.T, air.P, y1)

        def h_s(T: float) -> float:
            return saturated_air_enthalpy(thermo, dry, T, air.P)

        def residual(T_out: float) -> float:
            """r(T_out) = KaV/L_Chebyshev(T_out) - C (L/G)^-n.

            c_pw is evaluated between T_in and the trial T_out (only enthalpy
            differences enter). +inf when the operating line touches the
            saturation curve: an infinite tower.
            """
            c_pw = water_specific_heat(thermo, water.T, T_out, water.P)
            ka_v_l = merkel_number_chebyshev(water.T, T_out, L_over_G, c_pw, h_s, h_a_in)
            if math.isinf(ka_v_l):
                return math.inf
            return ka_v_l - characteristic

        # As T_out -> T_wb the Merkel integral grows without bound (r > 0);
        # as T_out -> T_in the range shrinks to 0, KaV/L -> 0 and r < 0.
        # Where the operating line touches saturation (dh_i <= 0) r is +inf;
        # brentq treats that discontinuity as a sign change and would return
        # a FALSE root at the jump (observed: an impossible characteristic
        # "converged" to T_out = 299.09 K at the inf boundary), so the
        # bracket is first pulled in to the left edge of the finite region
        # (r -> +large there, since 1/dh -> inf). An inf at the HOT end
        # means no finite T_out exists at all.
        lo, hi = T_wb + 1e-6, water.T - 1e-6
        if math.isinf(residual(hi)):
            raise CoolingTowerConvergenceError(
                f"cooling tower R1: the Merkel driving force is exhausted over the whole "
                f"bracket ({lo:.4f}, {hi:.4f}) K: the operating line touches saturation"
            )
        if math.isinf(residual(lo)):
            a, b = lo, hi
            for _ in range(60):
                mid = 0.5 * (a + b)
                if math.isinf(residual(mid)):
                    a = mid
                else:
                    b = mid
                if b - a <= 1e-10:
                    break
            lo = b
        try:
            T_out = brentq(residual, lo, hi, xtol=1e-10, maxiter=100)
        except (ValueError, RuntimeError) as exc:
            raise CoolingTowerConvergenceError(
                f"cooling tower R1: the Merkel residual has no root in the bracket "
                f"({lo:.4f}, {hi:.4f}) K or did not converge: {exc}"
            ) from exc

        approach = T_out - T_wb
        r0_params: dict[str, Any] = {"approach_K": approach}
        if cycles is not None:
            r0_params["cycles_of_concentration"] = float(cycles)
        result = CoolingTower().solve(inlets, r0_params, thermo)

        c_pw = water_specific_heat(thermo, water.T, T_out, water.P)
        merkel = merkel_number_chebyshev(water.T, T_out, L_over_G, c_pw, h_s, h_a_in)
        info = dict(result.info)
        info.update(
            {
                "merkel_KaV_L": merkel,
                "characteristic_KaV_L": characteristic,
                "L_over_G": L_over_G,
                "range_K": water.T - T_out,
                "approach_K": approach,
            }
        )
        return UnitResult(
            outlets=result.outlets,
            duty_W=result.duty_W,
            power_W=result.power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feeds with a Merkel characteristic: C = 1.7, n = 0.6."""
        feeds, _params = CoolingTower.example_case()
        params: dict[str, Any] = {
            "characteristic_C": 1.7,
            "characteristic_n": 0.6,
            "cycles_of_concentration": 3.0,
        }
        return feeds, params
