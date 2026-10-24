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

        # Exit air saturated at the MEAN water temperature: the counter-current
        # mean of the warm inlet and the solved outlet. Pinning the exit at the
        # inlet's wet bulb instead would spend the air's entire adiabatic
        # enthalpy drop on its own humidification (the AS identity), leaving no
        # sink for the water duty - the model could never cool.
        y1 = air.composition.get("H2O", 0.0)
        dry = {cid: x for cid, x in air.composition.items() if cid != "H2O"}

        def exit_for(T_w2: float) -> tuple[float, float, float]:
            """Exit-air state (y_H2O, enthalpy, evaporation) for a water outlet T_w2."""
            T_m = 0.5 * (water.T + T_w2)
            y2 = _psat(thermo, T_m) / air.P
            h_a2 = _humid_enthalpy(thermo, dry, T_m, air.P, y2)
            E = air.molar_flow * (y2 - y1) / (1.0 - y2)
            return y2, h_a2, E

        y2, h_air_out, E = exit_for(water.T)
        if E <= 0.0:
            raise ValueError(
                "cooling tower: the inlet air has no evaporative capacity against "
                f"its saturated exit state (E = {E:.4f} mol/s <= 0); dry or cool "
                "the air to cool the water"
            )
        if E >= water.molar_flow:
            raise ValueError(
                "cooling tower: the material closure evaporates more water than "
                "the water stream carries; reduce the air flow"
            )

        # Water outlet from the OVERALL energy closure. The exit state moves
        # with the solution (saturated at the mean water temperature), and the
        # residual falls monotonically with the water outlet temperature: a
        # colder outlet releases more water duty AND evaporates more air-side
        # water, both raising H_in - H_out.
        def residual(T_w2: float) -> float:
            _y2, h_a2, e = exit_for(T_w2)
            h_w2 = thermo.flash_pt({"H2O": 1.0}, T_w2, water.P, 1.0).enthalpy
            return (
                water.molar_flow * water.enthalpy
                + air.molar_flow * air.enthalpy
                - (water.molar_flow - e) * h_w2
                - (air.molar_flow + e) * h_a2
            )

        t_lo, t_hi = 275.0, water.T  # liquid water range
        if residual(t_hi) >= 0.0:
            raise ValueError(
                "cooling tower: the given air cannot cool the water below its "
                f"inlet temperature {water.T:.2f} K; increase the air flow"
            )
        if residual(t_lo) <= 0.0:
            raise ValueError(
                "cooling tower: the energy closure does not bracket a water outlet "
                "above 275 K; the duty is outside the R0 range"
            )
        for _ in range(_BISECT_STEPS):
            mid = 0.5 * (t_lo + t_hi)
            if residual(mid) > 0.0:
                t_lo = mid  # outlet enthalpy still below the inlet total: move up
            else:
                t_hi = mid
            if t_hi - t_lo <= 1e-9:
                break
        T_w2 = 0.5 * (t_lo + t_hi)

        y2, h_air_out, E = exit_for(T_w2)
        z_air_out = _z_with_water(dry, y2)
        water_out = thermo.flash_pt({"H2O": 1.0}, T_w2, water.P, water.molar_flow - E)
        T_air_out = 0.5 * (water.T + T_w2)
        air_out = thermo.flash_pt(z_air_out, T_air_out, air.P, air.molar_flow + E)
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
                "approach_K": T_w2 - T_wb,
                "evaporation_mol_s": E,
                "blowdown_mol_s": blowdown,
                "makeup_mol_s": makeup,
                "exit_air_T_K": T_air_out,
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
