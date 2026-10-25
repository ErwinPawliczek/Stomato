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

ORCHESTRATOR RULING (PR #284, 2026-10-25) on the enthalpy basis: Merkel's
driving force (h_s - h_a) is defined on the MOIST-AIR convention -- dry air as
ideal gas and LIQUID water at 273.15 K as the references (ASHRAE Fundamentals
Ch. 1). :func:`humid_air_enthalpy` therefore shifts the package enthalpies by
subtracting the package enthalpies of dry air (ideal gas) and of liquid water
at 273.15 K per their amounts, and the closed-form agreement test
``test_shifted_h_s_matches_the_hyland_wexler_closed_form`` (1 % over 290-320 K
at 1 atm) pins the shift. Feasibility ruling: the identity test runs at C =
1.0, the monotonicity sweep at C in {0.8, 1.0, 1.2}, and C = 1.7 is kept as a
TYPED refusal (:class:`CoolingTowerCharacteristicInfeasibleError`) carrying
the requested characteristic and the attainable Merkel number.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, cast

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

    The MOIST-AIR convention of ASHRAE Fundamentals Ch. 1 per the
    orchestrator ruling on PR #284 (2026-10-25): both h_s and h_a are per kg
    of dry air with the reference states dry air (ideal gas) and liquid water
    at 273.15 K, i.e. the package enthalpies of dry air and of liquid water
    at 273.15 K are subtracted per their amounts
    (h = 1.006 t + W (2501 + 1.86 t) on the standard-air basis). The same
    construction as R0's private ``_humid_enthalpy`` (re-implemented; the R0
    helpers are private), with the reference shift required by the ruling:
    the Merkel driving force h_s(T_i) - h_a(T_i) compares states of DIFFERENT
    humidity, so per-component reference offsets do not cancel without it
    (measured: inlet-air enthalpy 1.50 kJ/kg_da on the raw scale vs 61.5
    kJ/kg_da psychrometric). The shift is pinned by
    ``test_shifted_h_s_matches_the_hyland_wexler_closed_form`` (1 % over
    290-320 K at 1 atm, ASHRAE Fundamentals Ch. 1 eq. 6 closed form).
    """
    dry_sum = sum(dry.values())
    if dry_sum <= 0.0:
        raise ValueError("air composition is pure water vapour: no dry gas to humidify")
    z_dry = {cid: x / dry_sum for cid, x in dry.items()}
    h_dry = thermo.flash_pt(z_dry, T, P, 1.0).enthalpy
    h_dry_ref = thermo.flash_pt(z_dry, 273.15, P, 1.0).enthalpy
    h_vap = thermo.flash_pt({"H2O": 1.0}, T, 0.5 * _psat(thermo, T), 1.0).enthalpy
    h_w_ref = thermo.flash_pt({"H2O": 1.0}, 273.15, P, 1.0).enthalpy
    mw_dry = _mean_molar_mass(z_dry)
    w = y / (1.0 - y)
    return float((h_dry - h_dry_ref + w * (h_vap - h_w_ref)) / (mw_dry / 1000.0) / 1000.0)


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

    Two modes. SOLUTION mode (characteristic_C and characteristic_n given):
    the WATER OUTLET is solved from r(T_out) = KaV/L_Chebyshev(T_out) -
    C (L/G)^-n by brentq on (T_wb + 1e-6, T_in - 1e-6); the approach is then
    T_out - T_wb. RATING mode (approach_K alone): the approach is given and
    the attained Merkel number is reported at it -- the path the locked
    per-row balance test reaches through the LevelDispatch, whose inherited
    example_case is R0's (read-only for this spec). Both delegate to the R0
    adapter (:class:`ngdesign.units.heat.cooling_tower.CoolingTower`) at the
    approach, so every outlet, the energy closure and the blowdown/makeup
    split are R0's by construction (solution mode: R1 equals R0 run at the
    solved approach, bit for bit). L and G are MASS flows: water and dry
    air, kg/s. Giving the characteristic params AND approach_K is a typed
    refusal.
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
        given_approach = params.get("approach_K")
        cycles = params.get("cycles_of_concentration")
        if cycles is not None and float(cycles) < 1.0:
            raise ValueError(f"cooling tower: cycles_of_concentration {cycles} must be >= 1")
        if characteristic_C is not None and characteristic_n is not None:
            if given_approach is not None:
                raise CoolingTowerSpecError(
                    "cooling tower R1: approach_K is solved at R1; give characteristic_C "
                    "and characteristic_n, or rate at a given approach_K without them"
                )
        elif characteristic_C is None and characteristic_n is None:
            # Rating mode: the approach is GIVEN and the Merkel number is
            # reported at it. This is what the locked per-row balance test
            # reaches through the LevelDispatch: the dispatch subclasses the
            # default (R0) adapter, so example_case() is R0's -- whose params
            # carry approach_K -- and model: R1 lands here. R0's file is
            # read-only for this spec, so R1 accepts its example params
            # instead of the other way round.
            if given_approach is None:
                raise CoolingTowerSpecError(
                    "cooling tower R1: give characteristic_C and characteristic_n to solve "
                    "the water outlet, or approach_K to rate the tower at a given approach"
                )
            given_approach = float(cast(float, given_approach))
            if given_approach <= 0.0:
                raise CoolingTowerSpecError(f"cooling tower R1: approach_K {given_approach} must be > 0")
            T_wb0 = wet_bulb(thermo, air)
            return self._close(inlets, T_wb0 + given_approach, given_approach, cycles, thermo, None)
        else:
            raise CoolingTowerSpecError(
                "cooling tower R1: characteristic_C and characteristic_n are given together "
                "or not at all (rating mode takes approach_K alone)"
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

        Shared by both modes: the characteristic mode arrives with the
        brentq-solved water outlet, rating mode with T_wb + approach_K. The
        outlets, duty and blowdown/makeup split are R0's by construction.
        """
        water = inlets["water_in"]
        air = inlets["air_in"]
        dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}
        y1 = air.composition.get("H2O", 0.0)
        mw_dry = _mean_molar_mass(dry)
        L = water.molar_flow * _mean_molar_mass({"H2O": 1.0}) / 1000.0
        G = air.molar_flow * (1.0 - y1) * mw_dry / 1000.0
        h_a_in = humid_air_enthalpy(thermo, dry, air.T, air.P, y1)

        def h_s(T: float) -> float:
            return saturated_air_enthalpy(thermo, dry, T, air.P)

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
        characteristic at C = 1.0 (KaV/L = 3.61 on these feeds): the spec's
        C = 1.7 gives 6.14, above the attainable Merkel number on these feeds
        (about 5.1 on the moist-air basis), and is kept as a TYPED refusal
        instead. C = 1.0 solves at an approach of a few kelvin.
        """
        feeds, _params = CoolingTower.example_case()
        params: dict[str, Any] = {
            "characteristic_C": 1.0,
            "characteristic_n": 0.6,
            "cycles_of_concentration": 3.0,
        }
        return feeds, params
