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

Enthalpies are per kg of DRY AIR on the ASHRAE Fundamentals Ch. 1
psychrometric closed form (see the rulings below; not the thermo package).
The integration is by the 4-point Chebyshev rule of CTI ATC-105 /
ASHRAE Ch. 40 with abscissae at 0.1, 0.4, 0.6, 0.9 of the range.

ORCHESTRATOR RULINGS (PR #284, 2026-10-25) on the enthalpy basis and the
rating mode. Review item 1: the rating mode is REMOVED and ``approach_K``
is refused UNCONDITIONALLY -- R1's own example_case carries the
characteristic (the ruling), so the locked per-row balance test reaches
solution mode directly and no longer depends on the deleted mode. Review
item 2: the Merkel enthalpies h_s and h_a do NOT come from the thermo
package -- Peng-Robinson's water latent heat near 273.15 K is about 4 % high
(the +3.2 % h_s bias measured in the deleted xfail test, recorded on #249) --
but from the ASHRAE Fundamentals Ch. 1 psychrometric closed form:
Hyland-Wexler p_ws (eq. 6), W_s = 0.621945 p_ws / (P - p_ws) and
h = 1.006 t + W (2501 + 1.86 t) per kg of dry air. The R0 energy balance
stays with R0 through the thermo package, unchanged, so V0 closure is
unaffected. The closed form is pinned against printed ASHRAE Table 2 values
by ``test_saturated_air_enthalpy_matches_ashrae_table_2``.
Feasibility ruling: the identity test runs at C = 1.0, the monotonicity
sweep at C in {0.8, 1.0, 1.2}, and an unattainable characteristic is kept
as a TYPED refusal (:class:`CoolingTowerCharacteristicInfeasibleError`)
carrying the requested characteristic and the attainable Merkel number.
Measured on this basis the attainable number on the example feeds is 6.06,
so the spec's C = 1.7 (requested 6.02) is now attainable and the refusal
case moves to C = 1.8 (requested 6.37).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.heat.cooling_tower import CoolingTower, wet_bulb

#: Chebyshev abscissae as fractions of the temperature range (CTI ATC-105;
#: ASHRAE Handbook HVAC Systems and Equipment, Ch. 40).
CHEBYSHEV_FRACTIONS: tuple[float, ...] = (0.1, 0.4, 0.6, 0.9)


class CoolingTowerSpecError(ValueError):
    """A cooling-tower spec R1 refuses: a bad parameter or an infeasible state."""


class CoolingTowerConvergenceError(ValueError):
    """The Merkel residual did not bracket a root, or did not converge."""


class CoolingTowerCharacteristicInfeasibleError(CoolingTowerConvergenceError):
    """The requested characteristic exceeds the attainable Merkel number.

    For these flows the 4-point Chebyshev Merkel demand KaV/L(T_out) has a
    finite maximum over the water-outlet bracket; a characteristic
    C (L/G)^-n above it admits no water outlet. The message carries both
    numbers (requested characteristic, attainable maximum) per the
    orchestrator ruling on PR #284 (2026-10-25).
    """


def tower_characteristic(C: float, n: float, L_over_G: float) -> float:
    """CTI tower characteristic KaV/L = C (L/G)^-n (dimensionless)."""
    return C * math.pow(L_over_G, -n)


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


def max_attainable_ka_v_l(
    T_in: float,
    T_wb: float,
    L_over_G: float,
    h_s: Callable[[float], float],
    h_a_in: float,
    c_pw_of: Callable[[float], float],
    samples: int = 2001,
) -> float:
    """The largest finite Merkel demand the quadrature attains over the bracket.

    Scans T_out over (T_wb, T_in), evaluates
    :func:`merkel_number_chebyshev` at each and returns the maximum finite
    value -- the attainable Merkel number for these flows (used by the typed
    refusal of the adapter's ``solve``).
    """
    best = 0.0
    for i in range(1, samples + 1):
        T_out = T_wb + (T_in - T_wb) * i / (samples + 1)
        ka_v_l = merkel_number_chebyshev(T_in, T_out, L_over_G, c_pw_of(T_out), h_s, h_a_in)
        if math.isfinite(ka_v_l) and ka_v_l > best:
            best = ka_v_l
    return best


#: Hyland-Wexler constants, ASHRAE Fundamentals 2017 SI Ch. 1, eq. 6:
#: ln p_ws = C8/T + C9 + C10 T + C11 T^2 + C12 T^3 + C13 ln T
#: (saturation pressure over liquid water, 273.15-473.15 K; p_ws in Pa, T in K).
#: Checked against the printed ASHRAE Table 3 (4.2467 kPa at 30 C) in the tests.
_HW_C8: float = -5.8002206e3
_HW_C9: float = 1.3914993
_HW_C10: float = -4.8640239e-2
_HW_C11: float = 4.1764768e-5
_HW_C12: float = -1.4452093e-8
_HW_C13: float = 6.5459673


def hyland_wexler_psat(T: float) -> float:
    """Water saturation pressure over liquid water, Pa (ASHRAE Fund. 2017 Ch. 1, eq. 6).

    Hyland-Wexler, valid 273.15-473.15 K; constants checked against printed
    ASHRAE Table 3 in the tests (4.2467 kPa at 30 C).
    """
    return math.exp(
        _HW_C8 / T + _HW_C9 + _HW_C10 * T + _HW_C11 * T**2 + _HW_C12 * T**3 + _HW_C13 * math.log(T)
    )


def _mean_molar_mass(composition: dict[str, float]) -> float:
    """Mean molar mass of a (normalized) composition, g/mol, from the component db."""
    from ngdesign.data import components

    db = components()
    total = sum(composition.values())
    if total <= 0.0:
        raise ValueError("composition has no components")
    return sum(x / total * float(db[cid]["mw"]) for cid, x in composition.items())


def psychrometric_enthalpy(T: float, W: float) -> float:
    """Moist-air enthalpy per kg of dry air, kJ/kg_da (ASHRAE Fund. 2017 Ch. 1, eq. 32).

    h = 1.006 t + W (2501 + 1.86 t), with t = T - 273.15 in deg C and W the
    humidity ratio kg_w/kg_da; reference states: dry air and liquid water,
    both 0 at 0 deg C.
    """
    t = T - 273.15
    return 1.006 * t + W * (2501.0 + 1.86 * t)


def saturated_air_enthalpy(T: float, P: float) -> float:
    """Enthalpy of air saturated at T, kJ/kg_da, at total pressure P (Pa).

    ASHRAE basis per the orchestrator ruling on PR #284 (2026-10-25): the
    Merkel enthalpies do not come from the thermo package -- Peng-Robinson's
    water latent heat near 273.15 K is about 4 % high (recorded on #249) --
    but from the closed form: Hyland-Wexler p_ws (:func:`hyland_wexler_psat`,
    eq. 6), W_s = 0.621945 p_ws / (P - p_ws) and
    h = 1.006 t + W_s (2501 + 1.86 t). Pinned against printed ASHRAE
    Table 2 values by ``test_saturated_air_enthalpy_matches_ashrae_table_2``.
    """
    p_ws = hyland_wexler_psat(T)
    w_s = 0.621945 * p_ws / (P - p_ws)
    return psychrometric_enthalpy(T, w_s)


def inlet_air_enthalpy(T: float, y_water: float, mw_dry: float) -> float:
    """Bulk-air enthalpy of the INLET air, kJ/kg_da, on the same ASHRAE basis.

    The inlet humidity (H2O mole fraction y_water) is converted to the
    humidity ratio W = MW_w y / ((1 - y) MW_da), then
    h = 1.006 t + W (2501 + 1.86 t). The operating line is anchored here at
    the air inlet (h_a,in), so the whole Merkel driving force lives on one
    psychrometric basis independent of the property package.
    """
    mw_water = _mean_molar_mass({"H2O": 1.0})
    w = mw_water * y_water / ((1.0 - y_water) * mw_dry)
    return psychrometric_enthalpy(T, w)


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
    T_out - T_wb. ``approach_K`` is refused at R1 unconditionally (the plan's
    refusal table: it is solved here; the pre-#309 rating mode is gone
    because R1's own example_case carries the characteristic). The adapter
    delegates to the R0 adapter
    (:class:`ngdesign.units.heat.cooling_tower.CoolingTower`) at the solved
    approach, so every outlet, the energy closure and the blowdown/makeup
    split are R0's by construction (R1 equals R0 run at the solved approach,
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
        characteristic_n = params.get("characteristic_n")
        if params.get("approach_K") is not None:
            # Plan refusal table: approach_K is solved at R1 and refused
            # UNCONDITIONALLY (orchestrator review item 1, PR #284: the
            # rating mode was a pre-#309 workaround; R1's own example_case
            # carries the characteristic, so the locked balance test reaches
            # solution mode directly).
            raise CoolingTowerSpecError(
                "cooling tower R1: approach_K is solved at R1; give characteristic_C "
                "and characteristic_n to solve the water outlet"
            )
        cycles = params.get("cycles_of_concentration")
        if cycles is not None and float(cycles) < 1.0:
            raise ValueError(f"cooling tower: cycles_of_concentration {cycles} must be >= 1")
        if characteristic_C is None and characteristic_n is None:
            raise CoolingTowerSpecError(
                "cooling tower R1: give characteristic_C and characteristic_n to solve "
                "the water outlet (approach_K is solved at R1, not a parameter)"
            )
        if characteristic_C is None or characteristic_n is None:
            raise CoolingTowerSpecError(
                "cooling tower R1: characteristic_C and characteristic_n are given together or not at all"
            )
        characteristic_C = float(characteristic_C)
        if characteristic_C <= 0.0:
            raise CoolingTowerSpecError(f"cooling tower R1: characteristic_C {characteristic_C} must be > 0")
        characteristic_n = float(characteristic_n)
        if characteristic_n < 0.0:
            raise CoolingTowerSpecError(f"cooling tower R1: characteristic_n {characteristic_n} must be >= 0")

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

        h_a_in = inlet_air_enthalpy(air.T, y1, mw_dry)

        def h_s(T: float) -> float:
            return saturated_air_enthalpy(T, air.P)

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
            # The usual failure is a characteristic no real tower can meet:
            # the requested C (L/G)^-n above the attainable Merkel number.
            # Refuse TYPED with both numbers in the message (orchestrator
            # ruling on PR #284, 2026-10-25), not a bare brentq complaint.
            attainable = max_attainable_ka_v_l(
                water.T,
                T_wb,
                L_over_G,
                h_s,
                h_a_in,
                lambda T: water_specific_heat(thermo, water.T, T, water.P),
            )
            if characteristic > attainable:
                raise CoolingTowerCharacteristicInfeasibleError(
                    f"cooling tower R1: the requested characteristic KaV/L = "
                    f"{characteristic:.4f} exceeds the attainable Merkel number "
                    f"{attainable:.4f} for these flows: no water outlet exists"
                ) from exc
            raise CoolingTowerConvergenceError(
                f"cooling tower R1: the Merkel residual has no root in the bracket "
                f"({lo:.4f}, {hi:.4f}) K or did not converge: {exc}"
            ) from exc

        return self._close(inlets, T_out, T_out - T_wb, cycles, thermo, characteristic)

    def _close(
        self,
        inlets: dict[str, StreamState],
        T_out: float,
        approach: float,
        cycles: Any,
        thermo: Thermo,
        characteristic: float | None,
    ) -> UnitResult:
        """Delegate to R0 at the approach and assemble the R1 info block.

        Reached with the brentq-solved water outlet; the outlets, duty and
        blowdown/makeup split are R0's by construction.
        """
        water = inlets["water_in"]
        air = inlets["air_in"]
        dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}
        y1 = air.composition.get("H2O", 0.0)
        mw_dry = _mean_molar_mass(dry)
        L = water.molar_flow * _mean_molar_mass({"H2O": 1.0}) / 1000.0
        G = air.molar_flow * (1.0 - y1) * mw_dry / 1000.0
        h_a_in = inlet_air_enthalpy(air.T, y1, mw_dry)

        def h_s(T: float) -> float:
            return saturated_air_enthalpy(T, air.P)

        r0_params: dict[str, Any] = {"approach_K": approach}
        if cycles is not None:
            r0_params["cycles_of_concentration"] = float(cycles)
        result = CoolingTower().solve(inlets, r0_params, thermo)

        c_pw = water_specific_heat(thermo, water.T, T_out, water.P)
        merkel = merkel_number_chebyshev(water.T, T_out, L / G, c_pw, h_s, h_a_in)
        info = dict(result.info)
        info.update(
            {
                "merkel_KaV_L": merkel,
                "L_over_G": L / G,
                "range_K": water.T - T_out,
                "approach_K": approach,
            }
        )
        if characteristic is not None:
            info["characteristic_KaV_L"] = characteristic
        return UnitResult(
            outlets=result.outlets,
            duty_W=result.duty_W,
            power_W=result.power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 example feeds with a Merkel characteristic: C = 1.0, n = 0.6.

        The orchestrator ruling on PR #284 (2026-10-25) sets the example
        characteristic at C = 1.0 (KaV/L = 3.54 on these feeds): the spec's
        C = 1.7 gives 6.02, which on the ASHRAE closed-form basis is BELOW
        the attainable Merkel number on these feeds (measured 6.06), so it
        solves; the typed refusal is exercised at C = 1.8 (requested 6.37)
        instead. C = 1.0 solves at an approach of about 1.2 K (measured).
        """
        feeds, _params = CoolingTower.example_case()
        params: dict[str, Any] = {
            "characteristic_C": 1.0,
            "characteristic_n": 0.6,
            "cycles_of_concentration": 3.0,
        }
        return feeds, params
