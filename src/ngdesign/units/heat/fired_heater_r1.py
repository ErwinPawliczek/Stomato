"""Fired heater R1: Lobo-Evans radiant section plus a rated convection section.

Spec ``specs/backend/units/fired_heater.md`` (level R1). The radiant section
uses the Lobo-Evans method (Lobo & Evans 1939, Trans. AIChE 35:743; Kern 1950,
Ch. 19): ``Q_R = sigma*(alpha*A_cp)*F*(T_g^4 - T_t^4) + h_c*A_t*(T_g - T_t)``
on a well-stirred firebox whose gas temperature is the bridgewall (exit)
temperature. Computing the gas emissivity from the flue composition is OUT of
R1 scope: ``alpha_Acp_m2`` and ``exchange_factor`` are GIVEN params, read by
the user from the Lobo-Evans/Hottel charts. The convection section is a rated
counter-current exchanger (``Q_C = UA*LMTD``) between the flue gas
(bridgewall -> stack) and the process (inlet -> crossover). Combustion and the
firebox balance run on the same 298.15 K formation basis with water as vapour
as the R0 LHV (``ngdesign.units.heat.fired_heater.fuel_lhv``), imported
read-only.
"""

from __future__ import annotations

from typing import Any

from ngdesign.data.formation import atomic_composition

#: CODATA 2018 Stefan-Boltzmann constant, W/(m2 K4).
SIGMA_W_M2_K4 = 5.670374419e-8

#: Lobo-Evans radiant-section convection coefficient: 2 Btu/(h ft2 degF) in SI.
H_CONV_RADIANT_DEFAULT = 11.3565267

#: Default combustion air, mole fractions (spec params table).
DEFAULT_AIR_COMPOSITION: dict[str, float] = {"N2": 0.79, "O2": 0.21}

#: Minimum firing efficiency the outer fuel bracket supports (spec algorithm 3).
MIN_EFFICIENCY_LHV = 0.20

_BTU_IT_J = 1055.05585262  # exact, international-table Btu
_FT_M = 0.3048  # exact


def btu_h_ft2_f_to_w_m2_k(value: float) -> float:
    """Convert Btu/(h ft2 degF) to W/(m2 K)."""
    return value * _BTU_IT_J / (3600.0 * _FT_M**2 * (5.0 / 9.0))


class FiredHeaterSpecError(ValueError):
    """Refused fired-heater spec: a bad or missing parameter, named in the text."""


class FiredHeaterConvergenceError(ValueError):
    """A brentq bracket or the tube-wall fixed point failed; the stage is named."""


def validate_params(params: dict[str, Any]) -> None:
    """Refuse a spec the R1 method cannot run (spec 'Refusals' table).

    ``fuel_composition`` is required at R1, as are the four geometry /
    heat-transfer params (missing or <= 0 refused by name); ``exchange_factor``
    must sit in (0, 1], ``excess_air_frac`` >= 0 and ``radiant_loss_frac`` in
    [0, 0.5).
    """
    fuel = params.get("fuel_composition")
    if not fuel:
        raise FiredHeaterSpecError("fired_heater R1: fuel_composition is required at level R1")
    for name in (
        "alpha_Acp_m2",
        "exchange_factor",
        "tube_area_radiant_m2",
        "UA_convection_W_K",
    ):
        value = params.get(name)
        if value is None:
            raise FiredHeaterSpecError(f"fired_heater R1: {name} is required")
        value_f = float(value)
        if value_f <= 0.0:
            raise FiredHeaterSpecError(f"fired_heater R1: {name} {value_f} must be > 0")
    exchange_factor = float(params["exchange_factor"])
    if exchange_factor > 1.0:
        raise FiredHeaterSpecError(f"fired_heater R1: exchange_factor {exchange_factor} must be in (0, 1]")
    excess_air = params.get("excess_air_frac")
    if excess_air is None:
        raise FiredHeaterSpecError("fired_heater R1: excess_air_frac is required")
    if float(excess_air) < 0.0:
        raise FiredHeaterSpecError(f"fired_heater R1: excess_air_frac {excess_air} must be >= 0")
    tube_wall = params.get("tube_wall_excess_K")
    if tube_wall is None:
        raise FiredHeaterSpecError("fired_heater R1: tube_wall_excess_K is required")
    if float(tube_wall) < 0.0:
        raise FiredHeaterSpecError(f"fired_heater R1: tube_wall_excess_K {tube_wall} must be >= 0")
    loss_frac = float(params.get("radiant_loss_frac", 0.0))
    if not 0.0 <= loss_frac < 0.5:
        raise FiredHeaterSpecError(f"fired_heater R1: radiant_loss_frac {loss_frac} must be in [0, 0.5)")


def combustion_stoichiometry(
    fuel_composition: dict[str, float],
    air_composition: dict[str, float] | None = None,
    excess_air_frac: float = 0.0,
) -> dict[str, Any]:
    """Spec Eq. 1: combustion stoichiometry per mol of fuel mixture.

    Sums ``y_j * atoms_j`` (``atomic_composition``) over the fuel to C, H, O, S
    and fuel N2; theoretical O2 is ``C + H/4 + S - O/2``; the air supplied is
    ``(1 + e) * O2_th / y_O2,air``. Complete combustion: the flue gas carries
    CO2 = C, H2O = H/2, SO2 = S, the excess O2 = e * O2_th, the fuel N2 plus
    the air's non-O2 species (air argon passes through).

    Returns ``{"O2_th", "nu_air", "nu_fg", "flue"}`` where ``nu_air`` and
    ``nu_fg`` are mol per mol of fuel mixture and ``flue`` maps component id to
    mol per mol of fuel mixture. Raises ValueError for fuel elements outside
    the combustion set (same text as the R0 ``fuel_lhv``) and for a fuel with
    no heating value.
    """
    air = dict(DEFAULT_AIR_COMPOSITION if air_composition is None else air_composition)
    total_air = sum(air.values())
    if abs(total_air - 1.0) > 1e-9:
        raise FiredHeaterSpecError(f"fired_heater R1: air_composition sums to {total_air}, not 1")
    c = h = s = o = n_atoms = 0.0
    for cid, y in sorted(fuel_composition.items()):
        if y == 0.0:
            continue
        atoms = atomic_composition(cid)
        unsupported = sorted(set(atoms) - {"C", "H", "O", "S", "N"})
        if unsupported or (atoms.get("N", 0) and set(atoms) != {"N"}):
            raise ValueError(
                f"fired_heater: fuel component {cid!r} contains elements the "
                f"combustion set (C, H, O, S, inert N2) does not cover: "
                f"{', '.join(unsupported or ['bound nitrogen'])}"
            )
        c += y * atoms.get("C", 0)
        h += y * atoms.get("H", 0)
        s += y * atoms.get("S", 0)
        o += y * atoms.get("O", 0)
        n_atoms += y * atoms.get("N", 0)
    n2_fuel = n_atoms / 2.0
    o2_th = c + h / 4.0 + s - o / 2.0
    if o2_th <= 0.0:
        raise ValueError("fired_heater R1: the fuel mixture has no heating value (O2_th <= 0)")
    y_o2_air = air.get("O2", 0.0)
    if y_o2_air <= 0.0:
        raise FiredHeaterSpecError("fired_heater R1: air_composition has no O2")
    nu_air = (1.0 + excess_air_frac) * o2_th / y_o2_air
    flue: dict[str, float] = {}
    for species, y_species in air.items():
        if species == "O2":
            continue
        flue[species] = flue.get(species, 0.0) + y_species * nu_air
    flue["N2"] = flue.get("N2", 0.0) + n2_fuel
    flue["CO2"] = flue.get("CO2", 0.0) + c
    flue["H2O"] = flue.get("H2O", 0.0) + h / 2.0
    if s > 0.0:
        flue["SO2"] = flue.get("SO2", 0.0) + s
    flue["O2"] = flue.get("O2", 0.0) + excess_air_frac * o2_th
    nu_fg = sum(flue.values())
    return {"O2_th": o2_th, "nu_air": nu_air, "nu_fg": nu_fg, "flue": flue}


def radiant_transfer_W(
    alpha_Acp_m2: float,
    exchange_factor: float,
    T_g: float,
    T_t: float,
    tube_area_m2: float,
    h_conv: float = H_CONV_RADIANT_DEFAULT,
) -> tuple[float, float]:
    """Spec Eq. 3: Lobo-Evans radiant-section transfer, W.

    Returns ``(Q_radiation, Q_convection)``; the radiant duty is their sum.
    ``Q_radiation = sigma * alpha_Acp_m2 * F * (T_g^4 - T_t^4)`` with sigma the
    CODATA 2018 value, and ``Q_convection = h_conv * A_t * (T_g - T_t)`` with
    ``h_conv`` defaulting to the Lobo-Evans 2 Btu/(h ft2 degF). ``alpha_Acp_m2``
    and ``exchange_factor`` are given chart-read params (see module docstring).
    """
    q_radiation = SIGMA_W_M2_K4 * alpha_Acp_m2 * exchange_factor * (T_g**4 - T_t**4)
    q_convection = h_conv * tube_area_m2 * (T_g - T_t)
    return q_radiation, q_convection
