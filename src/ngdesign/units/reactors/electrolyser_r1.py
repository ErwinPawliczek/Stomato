"""Electrolyser stack, level R1: polarisation curve (spec ``electrolyser_stack``).

Plugin kind "unit", name "electrolyser_stack" (level ``R1`` of the row; the
level is selected by ``params["model"] = "R1"`` through the catalogue's
level dispatch, never by editing the R0 adapter).

Method: the R0 voltage input ``cell_voltage_V`` is replaced by a polarisation
curve. The reversible voltage comes from the databank through the single
ΔG°(T) owner, ``kinetics.ln_keq`` on H2O(g) → H2 + ½O2 with
``equilibrium: {form: from_gibbs}`` (equation 1):

    U_rev,g(T) = ΔG°(T)/(2F) = −R·T·ln K(T)/(2F)                 (ideal-gas, 1 bar)

A liquid water reactant carries the ideal-vapour equilibrium correction
μ_H2O(l) = μ°_ig + R·T·ln(p_sat/P°) (equation 2; Poynting neglected,
P° = 1e5 Pa, p_sat from ``Thermo.pure_psat``):

    U_rev,l(T) = [ΔG°(T) − R·T·ln(p_sat(T)/P°)]/(2F)

An optional Nernst pressure term (``pressure_correction: true``, equation 3)
lifts both dry product gases to the stack pressure P:

    U_rev += (R·T/(2F))·ln[(P/P°)^1.5]

The cell voltage is the Ulleberg (2003) alkaline form, equation 4, with
T_C = T − 273.15 (°C) and current density i = I/A_cell (A/m²):

    U_cell = U_rev + (r1 + r2·T_C)·i + s·log10[(t1 + t2/T_C + t3/T_C²)·i + 1]

    Ulleberg, Int. J. Hydrogen Energy 28 (2003) 21–33, eq. 4.

The logarithm is base 10 as printed; the generic form above is what the
adapter implements for user-supplied coefficients. The ``ulleberg2003``
preset is refused until its Table 1 coefficients are transcribed with page
and equation numbers (spec V1 rule: printed source values only). The
Faradaic efficiency is the Ulleberg eq. 9 form (equation 5),

    η_F = f2·i²/(f1 + i²)         (f1 in A²/m⁴),

defaulting to 1 when ``faradaic`` is absent.

Delegation: the stack solve itself — the Faraday split, the power and the
isothermal energy closure — stays in the R0 adapter
``ElectrolyserStack``, called by composition with the computed
``cell_voltage_V`` and ``faradaic_efficiency``. The R1 result IS R0's
result; the outlets leave at R0's (inlet) temperature, and a ``T_K``
parameter different from the inlet T is refused rather than re-heated.

Reduction to the lower level: with r1 = r2 = s = t1 = t2 = t3 = 0,
``pressure_correction`` false and ``faradaic`` absent, U_cell = U_rev and
η_F = 1, and the R1 ``UnitResult`` equals the R0 solve at
``cell_voltage_V = U_rev`` exactly (the same code path).

Refusals (typed :class:`ElectrolyserError`, a ``ValueError`` subclass):
``area_m2`` ≤ 0, ``current_A`` ≤ 0, ``n_cells`` < 1, ``T_C`` ≤ 0 °C while
t2 or t3 is nonzero (the log argument diverges), a non-positive activation
log argument, a two-phase inlet, a liquid inlet without a saturation
pressure, a ``T_K`` different from the inlet T, and the ungated
``ulleberg2003`` preset. R0's own refusals (H2/O2 in the feed, water
short, …) propagate unchanged.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Equilibrium, Reaction
from ngdesign.units._physics.kinetics import R, ln_keq
from ngdesign.units.reactors.electrolyser import FARADAY, ElectrolyserStack

#: JANAF ideal-gas standard-state pressure, Pa.
P_REF = 1.0e5

#: H2O(g) → H2 + ½O2 on the ideal-gas standard state: the reaction whose
#: ``from_gibbs`` ln K is the single owner of ΔG°(T) for the reversible
#: voltage. The databank formation data are ideal-gas (vapour) values, so the
#: liquid-water reactant is recovered by the μ°_ig + R·T·ln(p_sat/P°)
#: correction, not by changing the reaction.
_WATER_SPLITTING = Reaction(
    id="water_splitting_vapour",
    stoichiometry={"H2O": -1.0, "H2": 1.0, "O2": 0.5},
    base_component="H2O",
    provenance=(
        "H2O(g) -> H2 + 1/2 O2, JANAF ideal-gas standard state (spec electrolyser_stack R1, equation 1)"
    ),
    equilibrium=Equilibrium(form="from_gibbs"),
)


class ElectrolyserError(ValueError):
    """A polarisation-curve electrolyser request is ill-posed."""


def reversible_voltage_gibbs(T: float) -> float:
    """U_rev,g(T) = ΔG°(T)/(2F) for H2O(g) → H2 + ½O2, V (equation 1).

    ΔG°(T) = −R·T·ln K(T) comes only from ``kinetics.ln_keq`` on the
    ``from_gibbs`` path — no re-derivation here.
    """
    return -R * T * ln_keq(_WATER_SPLITTING, T) / (2.0 * FARADAY)


def reversible_voltage(
    thermo: Thermo,
    T: float,
    P: float,
    *,
    liquid_reactant: bool,
    pressure_correction: bool = False,
) -> float:
    """Reversible voltage V at (T, P) for the feed's phase (equations 1–3).

    ``liquid_reactant`` applies the saturation correction of equation 2 with
    ``thermo.pure_psat("H2O", T)`` and P° = 1e5 Pa; ``pressure_correction``
    adds the Nernst term of equation 3, (R·T/(2F))·ln[(P/P°)^1.5], for both
    dry product gases at the stack pressure P.
    """
    u_rev = reversible_voltage_gibbs(T)
    if liquid_reactant:
        p_sat = thermo.pure_psat("H2O", T)
        if p_sat is None:
            raise ElectrolyserError(
                "liquid water feed needs the H2O saturation pressure at "
                f"{T} K and the thermo package returned none (pure_psat)"
            )
        u_rev -= R * T * math.log(p_sat / P_REF) / (2.0 * FARADAY)
    if pressure_correction:
        u_rev += (R * T / (2.0 * FARADAY)) * 1.5 * math.log(P / P_REF)
    return u_rev


def _polarisation(params_polarisation: Any) -> dict[str, float]:
    """The ``polarisation`` parameter: the six Ulleberg-form coefficients.

    Refuses the ``ulleberg2003`` preset name — its Table 1 coefficients are
    not transcribed with a citation yet (spec V1 rule), so requesting the
    preset is an error, never a hidden default.
    """
    if isinstance(params_polarisation, str):
        raise ElectrolyserError(
            f"polarisation preset {params_polarisation!r} is not available: its "
            "coefficients are not transcribed from a printed source with page "
            "and equation numbers yet (Ulleberg 2003, Table 1)"
        )
    pol = dict(params_polarisation)
    missing = sorted({"r1", "r2", "s", "t1", "t2", "t3"} - set(pol))
    if missing:
        raise ElectrolyserError(f"polarisation is missing coefficients {missing}")
    return {key: float(pol[key]) for key in ("r1", "r2", "s", "t1", "t2", "t3")}


def overpotentials(
    u_rev: float,
    i: float,
    T_C: float,
    polarisation: dict[str, float],
) -> tuple[float, float]:
    """Ohmic and activation overpotentials of equation 4, in V, given U_rev.

    Returns ``(eta_ohmic_V, eta_activation_V)`` with

        eta_ohmic = (r1 + r2·T_C)·i
        eta_act   = s·log10[(t1 + t2/T_C + t3/T_C²)·i + 1]

    Ulleberg, Int. J. Hydrogen Energy 28 (2003) 21–33, eq. 4; the logarithm
    is base 10 as printed. Refuses T_C ≤ 0 °C while t2 or t3 is nonzero
    (the reciprocal terms diverge) and a non-positive log argument.
    """
    r1 = polarisation["r1"]
    r2 = polarisation["r2"]
    s = polarisation["s"]
    t1 = polarisation["t1"]
    t2 = polarisation["t2"]
    t3 = polarisation["t3"]
    if T_C <= 0.0 and (t2 != 0.0 or t3 != 0.0):
        raise ElectrolyserError(
            f"T_C {T_C} degC is at or below 0 degC with nonzero t2/t3: the "
            "t2/T_C + t3/T_C^2 terms of the activation argument diverge"
        )
    eta_ohmic = (r1 + r2 * T_C) * i
    reciprocal = (t2 / T_C if T_C != 0.0 else 0.0) + (t3 / T_C**2 if T_C != 0.0 else 0.0)
    argument = (t1 + reciprocal) * i + 1.0
    if argument <= 0.0:
        raise ElectrolyserError(
            f"activation term {(t1 + reciprocal) * i + 1.0} at current density "
            f"{i} A/m^2 is non-positive: the log10 of equation 4 is undefined"
        )
    return eta_ohmic, s * math.log10(argument)


def faradaic_efficiency(i: float, faradaic: dict[str, float] | None) -> float:
    """η_F = f2·i²/(f1 + i²) (Ulleberg 2003, eq. 9 form; equation 5), or 1.

    ``faradaic`` is ``{"f1": A²/m⁴, "f2": —}``; absent means η_F = 1.
    """
    if faradaic is None:
        return 1.0
    f1 = float(faradaic["f1"])
    f2 = float(faradaic["f2"])
    if f1 <= 0.0:
        raise ElectrolyserError(f"f1 {f1} A^2/m^4 is not positive")
    if not 0.0 < f2 <= 1.0:
        raise ElectrolyserError(f"f2 {f2} is outside (0, 1]")
    return f2 * i * i / (f1 + i * i)


class ElectrolyserStackR1:
    """Polarisation-curve water-electrolysis stack (spec ``electrolyser_stack``, R1)."""

    inlet_ports = ("inlet",)
    outlet_ports = ("h2_out", "o2_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        current = float(params["current_A"])
        n_cells = float(params["n_cells"])
        area = float(params["area_m2"])
        if area <= 0.0:
            raise ElectrolyserError(f"area_m2 {area} m^2 is not positive")
        if current <= 0.0:
            raise ElectrolyserError(f"current_A {current} A is not positive")
        if n_cells < 1.0:
            raise ElectrolyserError(f"n_cells {n_cells} is fewer than one cell")

        t_stated = params.get("T_K", inlet.T)
        if float(t_stated) != inlet.T:
            raise ElectrolyserError(
                f"T_K {t_stated} K differs from the inlet temperature {inlet.T} K: "
                "R0 is isothermal at the inlet T and R1 refuses to re-heat "
                "(the outlets leave at R0's temperature)"
            )

        vapor_fraction = inlet.vapor_fraction
        if vapor_fraction == 0.0:
            liquid_reactant = True
        elif vapor_fraction == 1.0:
            liquid_reactant = False
        else:
            raise ElectrolyserError(
                f"inlet vapor fraction {vapor_fraction} is two-phase: the "
                "reversible voltage needs a single-phase water reactant "
                "(0 = liquid, equation 2; 1 = vapour, equation 1)"
            )

        polarisation = _polarisation(params["polarisation"])
        faradaic = params.get("faradaic")
        pressure_correction = bool(params.get("pressure_correction", False))

        T = inlet.T
        u_rev = reversible_voltage(
            thermo,
            T,
            inlet.P,
            liquid_reactant=liquid_reactant,
            pressure_correction=pressure_correction,
        )
        current_density = current / area
        T_C = T - 273.15
        eta_ohmic, eta_activation = overpotentials(u_rev, current_density, T_C, polarisation)
        u_cell = u_rev + eta_ohmic + eta_activation
        eta_f = faradaic_efficiency(current_density, faradaic)

        r0 = ElectrolyserStack().solve(
            inlets,
            {
                "current_A": current,
                "n_cells": n_cells,
                "cell_voltage_V": u_cell,
                "faradaic_efficiency": eta_f,
            },
            thermo,
        )
        thermoneutral = float(r0.info["thermoneutral_voltage_V"])
        return UnitResult(
            outlets=r0.outlets,
            duty_W=r0.duty_W,
            power_W=r0.power_W,
            info={
                **r0.info,
                "U_rev_V": u_rev,
                "eta_ohmic_V": eta_ohmic,
                "eta_activation_V": eta_activation,
                "cell_voltage_V": u_cell,
                "current_density_A_m2": current_density,
                "faradaic_efficiency": eta_f,
                "efficiency_HHV": thermoneutral / u_cell,
            },
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's water feed on the spec's test polarisation coefficients.

        100-cell stack, 2000 A on 0.25 m² active area per cell (i = 8000
        A/m²), liquid water at 298.15 K: U_rev,l = 1.22874 V, ohmic 0.59 V,
        activation 0.68512 V, so U_cell ≈ 2.50386 V, and η_F = 0.95963 from
        f1 = 2.5e4 A²/m⁴, f2 = 0.96.
        """
        feed = {
            "T": 298.15,
            "P": 3.0e6,
            "molar_flow": 50.0,
            "composition": {"H2O": 1.0},
        }
        params = {
            "current_A": 2000.0,
            "n_cells": 100.0,
            "area_m2": 0.25,
            "polarisation": {
                "r1": 8.0e-5,
                "r2": -2.5e-7,
                "s": 0.185,
                "t1": -0.1,
                "t2": 8.4,
                "t3": 247.0,
            },
            "faradaic": {"f1": 2.5e4, "f2": 0.96},
        }
        return {"inlet": feed}, params
