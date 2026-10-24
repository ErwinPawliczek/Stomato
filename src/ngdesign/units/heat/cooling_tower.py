"""Cooling tower R0 (spec U-C 8).

Plugin kind "unit", name "cooling_tower", registered from the catalogue
row. Water port (water_in -> water_out) against an air port (air_in ->
air_out, humid). The exit air is SATURATED AT THE MEAN WATER TEMPERATURE
of the solved outlet and the warm inlet (the counter-current mean): that
pin fixes the humidity rise, the material balance fixes the evaporation
rate, and the overall energy closure SOLVES the water outlet temperature
(bisection). The inlet air's wet bulb (adiabatic-saturation balance
``f(T) = H1 + (W2 - W1)*h_w(T) - H2(T)`` per mol of dry gas, bisected; a
saturated inlet returns the dry bulb immediately) is reported and sets the
approach. ``cycles_of_concentration`` scales the blowdown. info:
``wet_bulb_K``, ``approach_K``, ``evaporation_mol_s``, ``blowdown_mol_s``,
``makeup_mol_s``, ``exit_air_T_K``, ``exit_air_y_H2O``.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo

#: Wet-bulb scan step, K.
_SCAN_STEP_K = 0.5

#: Wet-bulb scan span below the dry bulb, K.
_SCAN_SPAN_K = 120.0

#: Bisection iteration cap.
_BISECT_STEPS = 60


def _psat(thermo: Thermo, T: float) -> float:
    """Water saturation pressure (Pa); the plugin protocol types it Optional."""
    psat = thermo.pure_psat("H2O", T)
    if psat is None:
        raise ValueError(f"no water saturation pressure available at {T:.2f} K")
    return psat


def _z_with_water(dry: dict[str, float], y: float) -> dict[str, float]:
    """Composition with water at mole fraction y, dry gas scaled to 1 - y."""
    if y >= 1.0:
        raise ValueError("air composition is pure water vapour: no dry gas to humidify")
    dry_sum = sum(dry.values())
    if dry_sum <= 0.0:
        raise ValueError("air feed has no dry-gas components")
    return {cid: x * (1.0 - y) / dry_sum for cid, x in dry.items()} | {"H2O": y}


def _humid_enthalpy(
    thermo: Thermo,
    dry: dict[str, float],
    T: float,
    P: float,
    y: float,
) -> float:
    """Ideal saturated-air enthalpy per mol mixture, J/mol.

    ``(1 - y) * h_dry(T) + y * h_vapour(T)`` with each component flashed in
    its vapour region (the water at half its saturation pressure, where the
    flash is safely all gas). A PT flash of an exactly saturated mixture
    returns a fog sliver instead - the real mixture holds slightly less water
    than the ideal psat humidity - which would leak liquid-water enthalpy
    (about -45 MJ/kmol for water) into the balance.
    """
    h_dry = thermo.flash_pt({cid: x / sum(dry.values()) for cid, x in dry.items()}, T, P, 1.0).enthalpy
    h_vap = thermo.flash_pt({"H2O": 1.0}, T, 0.5 * _psat(thermo, T), 1.0).enthalpy
    return (1.0 - y) * h_dry + y * h_vap


def wet_bulb(
    thermo: Thermo,
    air: StreamState,
    water_composition: dict[str, float] | None = None,
) -> float:
    """Adiabatic-saturation wet bulb of a humid air stream, K.

    Per mol of dry gas, with ``W = y/(1-y)`` and ``H = h/(1-y)`` (the
    dry-gas normalization is what keeps the balance molar-consistent):
    ``f(T) = H1 + (W2(T) - W1)*h_w(T) - H2(T)`` where ``H2(T)`` is the ideal
    saturated mixture enthalpy at T (dry gas plus water vapour, no fog
    condensate; see :func:`_humid_enthalpy`). A saturated or supersaturated
    inlet (water partial pressure at or above p_sat at the dry bulb) returns
    the dry bulb immediately. Otherwise the scan walks DOWN from the dry
    bulb - f increases as the air cools - to bracket the root, then bisects.
    Raises ValueError when no bracket is found within the scan span.
    """
    y1 = air.composition.get("H2O", 0.0)
    dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}
    water_z = water_composition or {"H2O": 1.0}

    def f(T: float) -> float:
        w1 = y1 / (1.0 - y1)
        h1 = air.enthalpy / (1.0 - y1)
        y2 = _psat(thermo, T) / air.P
        h_w = thermo.flash_pt(water_z, T, air.P, 1.0).enthalpy
        return h1 + (y2 / (1.0 - y2) - w1) * h_w - _humid_enthalpy(thermo, dry, T, air.P, y2) / (1.0 - y2)

    # Saturated or supersaturated inlet: the dry bulb IS the wet bulb. Judged
    # on the water partial pressure rather than the flashed enthalpy: the PR
    # flash of a saturated humid feed can carry a liquid sliver that corrupts
    # the enthalpy f() would compare. Checking before the scan avoids the
    # degenerate lo == hi bracket a saturated feed produces at the first step.
    if y1 * air.P >= _psat(thermo, air.T):
        return air.T

    hi = air.T  # f < 0 here
    lo: float | None = None
    T = air.T
    for _ in range(int(_SCAN_SPAN_K / _SCAN_STEP_K)):
        T -= _SCAN_STEP_K
        if T <= 0:
            break
        if f(T) > 0.0:
            lo = T
            break
        hi = T
    if lo is None:
        raise ValueError(
            f"wet bulb not bracketed within {_SCAN_SPAN_K:.0f} K below the dry bulb "
            f"{air.T:.2f} K; the air state is outside the R0 scan range"
        )

    for _ in range(_BISECT_STEPS):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0.0:
            lo = mid  # root sits between mid and hi (f turns negative above the root)
        else:
            hi = mid
        if hi - lo <= 1e-6:
            break
    return 0.5 * (lo + hi)


class CoolingTower:
    """Evaporative water cooler against humid air (spec U-C 8)."""

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
        cycles = float(params.get("cycles_of_concentration", 3.0))
        if cycles < 1.0:
            raise ValueError(f"cooling tower: cycles_of_concentration {cycles} must be >= 1")

        T_wb = wet_bulb(thermo, air)

        # Model method: the WATER OUTLET is pinned at the inlet air's wet
        # bulb plus the required approach; the exit air - saturated at a
        # temperature solved from the overall energy balance - carries the
        # heat and the evaporation the material balance fixes.
        approach = params.get("approach_K")
        if approach is None:
            raise ValueError(
                "cooling tower: approach_K is required (water outlet above the "
                "inlet-air wet bulb, K)"
            )
        approach = float(approach)
        if approach <= 0.0:
            raise ValueError(f"cooling tower: approach_K {approach} must be > 0")
        T_water_out = T_wb + approach
        if T_water_out >= water.T:
            raise ValueError(
                "cooling tower: the tower cannot cool - the specified water "
                f"outlet {T_water_out:.2f} K (wet bulb + approach) is not below "
                f"the inlet {water.T:.2f} K"
            )

        y1 = air.composition.get("H2O", 0.0)
        dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}
        n_dry = air.molar_flow * (1.0 - y1)

        def exit_air(T_exit: float) -> tuple[float, float, float, float]:
            """(y2, E, n_out, enthalpy) of saturated exit air at T_exit."""
            y2 = _psat(thermo, T_exit) / air.P
            # Evaporation is the humidity-RATIO jump over the inlet, on dry air.
            evap = (y2 / (1.0 - y2) - y1 / (1.0 - y1)) * n_dry
            n_out = n_dry / (1.0 - y2)  # exit carries dry air plus ALL its water
            h_a2 = _humid_enthalpy(thermo, dry, T_exit, air.P, y2)
            return y2, evap, n_out, h_a2

        h_water_out = thermo.flash_pt(
            {"H2O": 1.0}, T_water_out, water.P, 1.0
        ).enthalpy

        def residual(T_exit: float) -> float:
            """h_in - h_out; falls monotonically as the exit air warms."""
            _y2, evap, n_out, h_a2 = exit_air(T_exit)
            return (
                water.molar_flow * water.enthalpy
                + air.molar_flow * air.enthalpy
                - (water.molar_flow - evap) * h_water_out
                - n_out * h_a2
            )

        # The exit-air enthalpy rises with T_exit, so the residual falls; the
        # wet bulb is the lowest saturated state available. If even the
        # wet-bulb exit overshoots the duty, nothing closes. And the wet-bulb
        # evaporation is the maximum the material balance allows: if it
        # already drinks the whole water stream, no exit state keeps the
        # water positive.
        _y2_cap, evap_cap, _n_out_cap, _h_cap = exit_air(T_wb)
        if evap_cap >= water.molar_flow:
            raise ValueError(
                "cooling tower: the material closure evaporates more water than "
                "the water stream carries; reduce the air flow"
            )
        if residual(T_wb) < 0.0:
            raise ValueError(
                "cooling tower: no saturated exit air closes the energy balance "
                "at the wet bulb; the water duty exceeds the tower's capacity"
            )
        t_lo, t_hi = T_wb, water.T
        if residual(t_hi) > 0.0:
            t_hi = 500.0  # span guard; widen only if the root sits above the inlet
            if residual(t_hi) > 0.0:
                raise ValueError(
                    "cooling tower: the energy closure does not bracket an exit "
                    "air below 500 K; the duty is outside the R0 range"
                )
        for _ in range(_BISECT_STEPS):
            mid = 0.5 * (t_lo + t_hi)
            if residual(mid) > 0.0:
                t_lo = mid  # exit air can still absorb more duty: move up
            else:
                t_hi = mid
            if t_hi - t_lo <= 1e-9:
                break
        T_exit_air = t_hi  # saturated state that exactly closes the balance

        y2, E, n_air_out, h_air_out = exit_air(T_exit_air)
        if E >= water.molar_flow:
            raise ValueError(
                "cooling tower: the material closure evaporates more water than "
                "the water stream carries; reduce the air flow"
            )
        z_air_out = _z_with_water(dry, y2)
        water_out = thermo.flash_pt(
            {"H2O": 1.0}, T_water_out, water.P, water.molar_flow - E
        )
        air_out = thermo.flash_pt(z_air_out, T_exit_air, air.P, n_air_out)
        # The exit air is the ideal saturated gas: pin its enthalpy and vapour
        # fraction to the fog-free construction the balance solved with, and pin
        # the composition too - the raw PR flash of an exactly saturated humid
        # feed can report the vapour-phase composition of a two-phase split
        # instead of the overall composition this balance solved with.
        air_out = air_out.model_copy(
            update={"composition": dict(z_air_out), "enthalpy": h_air_out, "vapor_fraction": 1.0}
        )

        # Cycles of concentration: the blowdown removes evaporation/(COC - 1)
        # so the dissolved solids hold at COC x the makeup; makeup replaces
        # evaporation + blowdown.
        blowdown = E / (cycles - 1.0) if cycles > 1.0 + 1e-12 else 0.0
        makeup = E + blowdown

        h_in = water.enthalpy * water.molar_flow + air.enthalpy * air.molar_flow
        h_out = water_out.enthalpy * water_out.molar_flow + air_out.enthalpy * air_out.molar_flow
        return UnitResult(
            outlets={"water_out": water_out, "air_out": air_out},
            duty_W=h_out - h_in,
            power_W=0.0,
            info={
                "wet_bulb_K": T_wb,
                "approach_K": approach,
                "water_outlet_T_K": T_water_out,
                "evaporation_mol_s": E,
                "blowdown_mol_s": blowdown,
                "makeup_mol_s": makeup,
                "exit_air_T_K": T_exit_air,
                "exit_air_y_H2O": y2,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Warm water against warm humid air: water 40 C cools toward the wet bulb."""
        water = {"T": 313.15, "P": 1.01325e5, "molar_flow": 555.0, "composition": {"H2O": 1.0}}
        # Humid but unsaturated air at 26.67 C: y = 0.0207191 = 0.6 * y_sat(299.817 K)
        # with y_sat from the PR package (p_sat = 3498.938 Pa at 299.817 K).
        air = {
            "T": 299.817,
            "P": 1.01325e5,
            "molar_flow": 3000.0,
            "composition": {"N2": 0.9792809, "H2O": 0.0207191},
        }
        return {"water_in": water, "air_in": air}, {"cycles_of_concentration": 3.0}
