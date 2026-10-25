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

from scipy.optimize import brentq

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data.formation import atomic_composition
from ngdesign.sizing.lmtd import lmtd_counter
from ngdesign.units.heat.fired_heater import fuel_lhv

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


class FiredHeaterDewPointError(FiredHeaterConvergenceError):
    """A solved stack temperature sits below the flue dew point at box
    pressure: the flue would condense water. The condensing regime is HHV
    territory and outside R1 (the LHV basis assumes water leaves as vapour)."""


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


#: 298.15 K formation reference, matching ``fuel_lhv`` (water as vapour).
T_REF_K = 298.15

#: Brent caps (spec algorithm 3): 100 iterations, xtol 1e-12. The xtol is
#: ABSOLUTE (scipy brentq has no relative form): on the outer fuel bracket
#: (n_f of order a few mol/s) that is ~5e-13 relative, and on the temperature
#: brackets (hundreds of K) it is negligible.
_BRENT_MAXITER = 100
_BRENT_XTOL = 1e-12

#: Tube-wall fixed-point cap (spec algorithm 3a).
_FIXED_POINT_CAP = 50

#: Upper bound of the adiabatic flame temperature bracket, K.
_T_AD_MAX_K = 4000.0


def mixture_enthalpy(thermo: Thermo, composition: dict[str, float], T: float, P: float) -> float:
    """Molar enthalpy (J/mol) of a mixture as ONE vapour phase.

    Uses ``phase_props(..., PhaseKind.VAPOR)`` - a single-vapour-phase build,
    never a flash. ``fuel_lhv`` is on the 298.15 K basis with water as vapour,
    so the flue and air reference and sensible enthalpies must be vapour-phase
    too: a ``flash_pt`` at 298.15 K would condense the flue water and slip its
    latent heat (about 10 % of the LHV on a methane flue) into every
    "sensible above reference" term.
    """
    total = sum(composition.values())
    if total <= 0.0:
        raise ValueError("fired_heater R1: mixture composition sums to <= 0")
    z = {cid: y / total for cid, y in composition.items() if y != 0.0}
    return thermo.phase_props(z, T, P, PhaseKind.VAPOR).enthalpy


def solve_fuel_and_sections(
    thermo: Thermo,
    *,
    lhv_J_per_mol: float,
    flue_mol: dict[str, float],
    air_fractions: dict[str, float],
    nu_air: float,
    nu_fg: float,
    Q_W: float,
    F_mol_s: float,
    h_in_J_per_mol: float,
    T_in_K: float,
    T_out_K: float,
    P_out_Pa: float,
    composition: dict[str, float],
    air_T_K: float,
    box_P_Pa: float,
    alpha_Acp_m2: float,
    exchange_factor: float,
    tube_area_m2: float,
    h_conv_W_m2K: float,
    tube_wall_excess_K: float,
    UA_convection_W_K: float,
    radiant_loss_frac: float,
) -> dict[str, float]:
    """Spec algorithm 3: solve the fuel rate and both sections for a fixed duty.

    Outer unknown is the fuel molar flow ``n_f`` (brentq on
    ``[Q/LHV*(1+1e-9), Q/(0.20*LHV)]``). For each ``n_f``: the tube-wall
    temperature fixed point alternates the bridgewall solve (Eqs. 2 = 3,
    brentq on ``[T_t + 1e-6, T_ad]``), the stack solve (Eq. 4 flue enthalpy,
    brentq on ``[T_air, T_g]``) and the process crossover (``flash_ph``), until
    ``T_t = mean(T_cross, T_out) + tube_wall_excess_K`` moves < 1e-9 K (cap 50).
    The outer residual is ``UA_C*LMTD - Q_C``; a crossed convection section or
    an over-delivering radiant section short-circuits it to ``-Q`` / ``+Q``.
    A stack-bracket failure is read as a crossed convection section (the flue
    cannot carry ``Q_C`` down to the air temperature), i.e. fuel too low, and
    short-circuits to ``-Q``; a solved ``T_stack`` below the flue dew point at
    box pressure raises :class:`FiredHeaterDewPointError` (a condensing flue is
    HHV territory, outside the LHV basis).

    Returns ``fuel_molar_flow``, ``T_adiabatic_K``, ``T_bridgewall_K``,
    ``T_stack_K``, ``T_crossover_K``, ``T_tube_wall_K``, ``Q_radiant_W``,
    ``Q_convection_W``, ``efficiency_LHV`` and the outer ``residual_W`` at the
    solution. Raises :class:`FiredHeaterConvergenceError` naming the stage
    (outer, T_g, T_ad, T_stack, tube wall) on any bracket or fixed-point
    failure.
    """
    air_sensible = mixture_enthalpy(thermo, air_fractions, air_T_K, box_P_Pa) - (
        mixture_enthalpy(thermo, air_fractions, T_REF_K, box_P_Pa)
    )
    h_fg_ref = mixture_enthalpy(thermo, flue_mol, T_REF_K, box_P_Pa)
    h_fg_cache: dict[float, float] = {}
    flue_total = sum(flue_mol.values())
    flue_z = {cid: y / flue_total for cid, y in flue_mol.items() if y != 0.0}
    try:
        flue_dew_T: float | None = thermo.dew_point(flue_z, P=box_P_Pa).T
    except ValueError:
        # No two-phase region at box pressure (supercritical feed): the flue
        # cannot condense, so no dew-point refusal applies.
        flue_dew_T = None

    def q_flue_above_ref(T: float) -> float:
        h = h_fg_cache.get(T)
        if h is None:
            h = mixture_enthalpy(thermo, flue_mol, T, box_P_Pa)
            h_fg_cache[T] = h
        return nu_fg * (h - h_fg_ref)

    # T_ad: Eq. 2 with Q_R = 0 (the loss term stays, per the spec's equation).
    def ad_residual(T: float) -> float:
        return q_flue_above_ref(T) + radiant_loss_frac * lhv_J_per_mol - lhv_J_per_mol - nu_air * air_sensible

    try:
        T_ad = float(
            brentq(
                ad_residual,
                air_T_K,
                _T_AD_MAX_K,
                maxiter=_BRENT_MAXITER,
                xtol=_BRENT_XTOL,
            )
        )
    except ValueError as exc:
        raise FiredHeaterConvergenceError(
            f"fired_heater R1: adiabatic flame temperature bracket failed (stage T_ad): {exc}"
        ) from exc

    def balance_q_R_per_mol(T_g: float) -> float:
        """Eq. 2 rearranged: Q_R/n_f that the firebox balance demands at T_g."""
        return (1.0 - radiant_loss_frac) * lhv_J_per_mol + nu_air * air_sensible - q_flue_above_ref(T_g)

    def q_R_lobo_W(T_g: float, T_t: float) -> float:
        q_rad, q_conv = radiant_transfer_W(
            alpha_Acp_m2, exchange_factor, T_g, T_t, tube_area_m2, h_conv_W_m2K
        )
        return q_rad + q_conv

    def solve_T_g(T_t: float, n_f: float) -> float:
        def residual(T_g: float) -> float:
            return balance_q_R_per_mol(T_g) - q_R_lobo_W(T_g, T_t) / n_f

        try:
            return float(
                brentq(
                    residual,
                    T_t + 1e-6,
                    T_ad,
                    maxiter=_BRENT_MAXITER,
                    xtol=_BRENT_XTOL,
                )
            )
        except ValueError as exc:
            raise FiredHeaterConvergenceError(
                f"fired_heater R1: bridgewall temperature bracket failed (stage T_g): {exc}"
            ) from exc

    def solve_T_stack(T_g: float, q_C_per_mol_fuel: float) -> float:
        def residual(T: float) -> float:
            return q_flue_above_ref(T_g) - q_flue_above_ref(T) - q_C_per_mol_fuel

        try:
            T_stack = float(
                brentq(
                    residual,
                    air_T_K,
                    T_g,
                    maxiter=_BRENT_MAXITER,
                    xtol=_BRENT_XTOL,
                )
            )
        except ValueError as exc:
            raise FiredHeaterConvergenceError(
                f"fired_heater R1: stack temperature bracket failed (stage T_stack): {exc}"
            ) from exc
        if flue_dew_T is not None and T_stack < flue_dew_T:
            raise FiredHeaterDewPointError(
                f"fired_heater R1: solved stack temperature {T_stack:.2f} K is below the "
                f"flue dew point {flue_dew_T:.2f} K at box pressure (stage T_stack): a "
                "condensing flue is HHV territory and outside R1 (LHV basis)"
            )
        return T_stack

    def evaluate(n_f: float, final: bool = False) -> dict[str, float]:
        """Tube-wall fixed point at this fuel rate, with the outer residual.

        ``final=True`` (the accepted solution) re-raises a dew-point crossing;
        during bracket probing a crossing only means the fuel is too low.
        """
        T_t = (T_in_K + T_out_K) / 2.0 + tube_wall_excess_K
        T_g = T_stack = T_cross = 0.0
        Q_C = 0.0
        for _ in range(_FIXED_POINT_CAP):
            T_g = solve_T_g(T_t, n_f)
            Q_R = q_R_lobo_W(T_g, T_t)
            Q_C = Q_W - Q_R
            if Q_C < 0.0:
                # Radiant section alone over-delivers: the fuel is too high.
                return {"residual_W": Q_W}
            try:
                T_stack = solve_T_stack(T_g, Q_C / n_f)
            except FiredHeaterDewPointError:
                if final:
                    raise  # the accepted solution condenses the flue: refuse
                # A probe firing rate whose flue would condense cannot carry
                # the convection duty on the LHV basis: fuel too low.
                return {"residual_W": -Q_W}
            except FiredHeaterConvergenceError:
                # The flue cannot carry Q_C down to the air temperature: the
                # convection section is crossed, the fuel is too low.
                return {"residual_W": -Q_W}
            cross = thermo.flash_ph(composition, P_out_Pa, h_in_J_per_mol + Q_C / F_mol_s, F_mol_s)
            T_cross = cross.T
            T_t_new = (T_cross + T_out_K) / 2.0 + tube_wall_excess_K
            if abs(T_t_new - T_t) < 1e-9:
                T_t = T_t_new
                T_g = solve_T_g(T_t, n_f)
                break
            T_t = T_t_new
        else:
            raise FiredHeaterConvergenceError(
                "fired_heater R1: tube wall fixed point did not converge (stage tube wall)"
            )
        Q_R = q_R_lobo_W(T_g, T_t)
        Q_C = Q_W - Q_R
        if Q_C < 0.0:
            return {"residual_W": Q_W}
        try:
            lmtd = lmtd_counter(T_g, T_stack, T_in_K, T_cross)
        except ValueError:
            return {"residual_W": -Q_W}
        return {
            "residual_W": UA_convection_W_K * lmtd - Q_C,
            "T_bridgewall_K": T_g,
            "T_stack_K": T_stack,
            "T_crossover_K": T_cross,
            "T_tube_wall_K": T_t,
            "Q_radiant_W": Q_R,
            "Q_convection_W": Q_C,
        }

    n_lo = Q_W / lhv_J_per_mol * (1.0 + 1e-9)
    n_hi = Q_W / (MIN_EFFICIENCY_LHV * lhv_J_per_mol)
    if evaluate(n_hi)["residual_W"] <= 0.0 or evaluate(n_lo)["residual_W"] >= 0.0:
        raise FiredHeaterConvergenceError(
            "fired_heater R1: no firing rate reaches the spec duty with "
            f"efficiency >= {MIN_EFFICIENCY_LHV:.2f} (stage outer)"
        )

    def outer_residual(n_f: float) -> float:
        return evaluate(n_f)["residual_W"]

    try:
        n_f = float(
            brentq(
                outer_residual,
                n_lo,
                n_hi,
                maxiter=_BRENT_MAXITER,
                xtol=_BRENT_XTOL,
            )
        )
    except ValueError as exc:
        raise FiredHeaterConvergenceError(
            f"fired_heater R1: outer fuel bracket failed (stage outer): {exc}"
        ) from exc

    final = evaluate(n_f, final=True)
    return {
        "fuel_molar_flow": n_f,
        "T_adiabatic_K": T_ad,
        "efficiency_LHV": Q_W / (n_f * lhv_J_per_mol),
        **final,
    }


class FiredHeaterR1:
    """Fired heater R1 (spec U-C 7, level R1): Lobo-Evans radiant section
    plus a rated convection section, with the fuel and flue-gas balance
    solved rather than an assumed efficiency.

    The process outlet is computed exactly as R0 (``T_out`` -> ``flash_pt`` at
    ``P - dP``, or ``duty_W`` -> ``flash_ph``). ``fuel_composition`` is
    required at R1; the LHV comes from the R0 ``fuel_lhv`` (298.15 K
    formation basis, water as vapour). The firing rate, bridgewall, stack and
    crossover temperatures solve spec algorithm 3; ``alpha_Acp_m2`` and
    ``exchange_factor`` are chart-read params (Hottel/Lobo charts - computing
    the gas emissivity is out of R1 scope). Refusals follow the spec table:
    bad or missing params raise ``FiredHeaterSpecError``, infeasible firing
    raise ``FiredHeaterConvergenceError``.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if inlet.molar_flow <= 0.0:
            raise ValueError("fired_heater R1 needs a process stream with positive flow")
        validate_params(params)
        T_out = params.get("T_out")
        duty_spec = params.get("duty_W")
        if T_out is not None and duty_spec is not None:
            raise ValueError("fired_heater R1: specify exactly one of T_out (K) or duty_W (W)")
        P_out = inlet.P - float(params.get("dP", 0.0))
        if P_out <= 0:
            raise ValueError(f"fired_heater R1: dP {params.get('dP')} leaves a non-positive outlet pressure")
        if T_out is not None:
            T_out_f = float(T_out)
            if T_out_f <= 0:
                raise ValueError(f"fired_heater R1: T_out {T_out_f} K must be > 0")
            out = thermo.flash_pt(inlet.composition, T_out_f, P_out, inlet.molar_flow)
        elif duty_spec is not None:
            out = thermo.flash_ph(
                inlet.composition,
                P_out,
                inlet.enthalpy + float(duty_spec) / inlet.molar_flow,
                inlet.molar_flow,
            )
        else:
            raise ValueError("fired_heater R1: specify exactly one of T_out (K) or duty_W (W)")
        duty = inlet.molar_flow * (out.enthalpy - inlet.enthalpy)
        if duty <= 0.0:
            raise ValueError(
                "fired_heater R1 heats the process stream; the spec gives duty "
                f"{duty:.4f} W <= 0 and cannot be satisfied by firing"
            )
        fuel = {str(cid): float(y) for cid, y in params["fuel_composition"].items()}
        lhv = fuel_lhv(fuel)
        if lhv <= 0.0:
            raise ValueError("fired_heater R1: the fuel mixture has no heating value (LHV <= 0)")
        air = (
            {str(k): float(v) for k, v in params["air_composition"].items()}
            if params.get("air_composition")
            else dict(DEFAULT_AIR_COMPOSITION)
        )
        air_T = float(params.get("air_T_K", 298.15))
        if air_T <= 0.0:
            raise FiredHeaterSpecError(f"fired_heater R1: air_T_K {air_T} must be > 0")
        box_P = float(params.get("box_P_Pa", 101325.0))
        if box_P <= 0.0:
            raise FiredHeaterSpecError(f"fired_heater R1: box_P_Pa {box_P} must be > 0")
        h_conv = float(params.get("h_conv_radiant_W_m2K", H_CONV_RADIANT_DEFAULT))
        if h_conv < 0.0:
            raise FiredHeaterSpecError(f"fired_heater R1: h_conv_radiant_W_m2K {h_conv} must be >= 0")
        tube_area = float(params["tube_area_radiant_m2"])
        stoich = combustion_stoichiometry(fuel, air, float(params["excess_air_frac"]))
        solved = solve_fuel_and_sections(
            thermo,
            lhv_J_per_mol=lhv,
            flue_mol=stoich["flue"],
            air_fractions=air,
            nu_air=stoich["nu_air"],
            nu_fg=stoich["nu_fg"],
            Q_W=duty,
            F_mol_s=inlet.molar_flow,
            h_in_J_per_mol=inlet.enthalpy,
            T_in_K=inlet.T,
            T_out_K=out.T,
            P_out_Pa=P_out,
            composition=inlet.composition,
            air_T_K=air_T,
            box_P_Pa=box_P,
            alpha_Acp_m2=float(params["alpha_Acp_m2"]),
            exchange_factor=float(params["exchange_factor"]),
            tube_area_m2=tube_area,
            h_conv_W_m2K=h_conv,
            tube_wall_excess_K=float(params["tube_wall_excess_K"]),
            UA_convection_W_K=float(params["UA_convection_W_K"]),
            radiant_loss_frac=float(params.get("radiant_loss_frac", 0.0)),
        )
        n_f = solved["fuel_molar_flow"]
        info: dict[str, Any] = {
            "Q_fired_W": n_f * lhv,
            "fuel_LHV_J_per_mol": lhv,
            "fuel_molar_flow": n_f,
            "efficiency_LHV": solved["efficiency_LHV"],
            "Q_radiant_W": solved["Q_radiant_W"],
            "Q_convection_W": solved["Q_convection_W"],
            "T_bridgewall_K": solved["T_bridgewall_K"],
            "T_stack_K": solved["T_stack_K"],
            "T_crossover_K": solved["T_crossover_K"],
            "T_tube_wall_K": solved["T_tube_wall_K"],
            "T_adiabatic_K": solved["T_adiabatic_K"],
            "radiant_flux_W_m2": solved["Q_radiant_W"] / tube_area,
            "air_molar_flow": n_f * stoich["nu_air"],
            "flue_molar_flow": n_f * stoich["nu_fg"],
            "flue_y_O2": stoich["flue"].get("O2", 0.0) / stoich["nu_fg"],
        }
        h_out_total = out.enthalpy * out.molar_flow
        return UnitResult(
            outlets={"outlet": out},
            duty_W=h_out_total - inlet.enthalpy * inlet.molar_flow,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Methane fuel (15 % excess air) heating natural gas 300 -> 600 K with
        the step-2 basis geometry: measured efficiency_LHV 0.8253 (alpha_Acp
        8 m2, exchange factor 0.6, A_t 200 m2, UA_C 1200 W/K)."""
        inlet = {"T": 300.0, "P": 5.0e5, "molar_flow": 100.0, "composition": {"C1": 1.0}}
        params: dict[str, Any] = {
            "T_out": 600.0,
            "dP": 1.0e4,
            "fuel_composition": {"C1": 1.0},
            "excess_air_frac": 0.15,
            "alpha_Acp_m2": 8.0,
            "exchange_factor": 0.6,
            "tube_area_radiant_m2": 200.0,
            "tube_wall_excess_K": 100.0,
            "UA_convection_W_K": 1200.0,
        }
        return {"inlet": inlet}, params
