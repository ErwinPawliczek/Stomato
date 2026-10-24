"""Shared reactor-adapter helpers (spec U-F).

The mechanical core the four stoichiometric reactor adapters share: resolving
the ``reaction_set`` parameter, converting stated conversions into extents,
normalizing mole amounts into a feed composition, and closing the thermal
mode (isothermal / adiabatic / fixed duty) on the formation-enthalpy basis.

All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import ReactionSet
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import enthalpy_with_formation

#: JANAF ideal-gas standard-state pressure for equilibrium quotients, Pa.
P_REF = 1.0e5

#: Bracket bounds for the adiabatic / duty outlet-temperature solve, K.
_T_MIN = 1.0
_T_MAX = 5000.0


def reaction_set_param(value: Any) -> ReactionSet:
    """The ``reaction_set`` unit parameter: an inline set, passed through.

    A :class:`ReactionSet` (or its dict form) is accepted directly. A bare
    string id has nothing to resolve against at the adapter level — the solver
    replaces string ids with the flowsheet's owned set before calling solve —
    so it is refused, naming the id and the resolution path.
    """
    if isinstance(value, ReactionSet):
        return value
    if isinstance(value, str):
        raise ValueError(
            f"reaction_set {value!r} is not registered (a string id is resolved by the "
            "solver against the flowsheet's owned reaction sets)"
        )
    return ReactionSet.model_validate(value)


def extents_from_conversion(
    rset: ReactionSet,
    n_in: Mapping[str, float],
    conversion: Mapping[str, float],
    *,
    sequential: bool = False,
) -> list[float]:
    """Extent of each reaction from a stated fractional conversion.

    ``conversion[reaction_id]`` is the fraction of that reaction's
    ``base_component`` amount converted. Simultaneous (default, R0): extents
    are computed on the inlet amounts (reactions in one set share the same
    basis). ``sequential=True`` processes the reactions in declaration order,
    each conversion applied to the amounts left by the previous reactions —
    the running depletion, not the inlet basis.

    Refuses: a reaction with no conversion entry, an entry for an unknown
    reaction id, a conversion outside [0, 1], and (naming the species) an
    extent combination that drives any species negative.
    """
    ids = [r.id for r in rset.reactions]
    missing = [rid for rid in ids if rid not in conversion]
    if missing:
        raise ValueError(f"conversion entries missing for reactions {missing}")
    unknown = sorted(set(conversion) - set(ids))
    if unknown:
        raise ValueError(f"conversion entries for unknown reactions {unknown}")
    extents: list[float] = []
    if not sequential:
        for reaction in rset.reactions:
            frac = float(conversion[reaction.id])
            if not 0.0 <= frac <= 1.0:
                raise ValueError(f"reaction {reaction.id!r}: conversion {frac} outside [0, 1]")
            nu_base = float(reaction.stoichiometry[reaction.base_component])
            extents.append(frac * float(n_in.get(reaction.base_component, 0.0)) / abs(nu_base))
        return extents
    running = {cid: float(n) for cid, n in n_in.items()}
    for reaction in rset.reactions:
        frac = float(conversion[reaction.id])
        if not 0.0 <= frac <= 1.0:
            raise ValueError(f"reaction {reaction.id!r}: conversion {frac} outside [0, 1]")
        nu_base = float(reaction.stoichiometry[reaction.base_component])
        xi = frac * running.get(reaction.base_component, 0.0) / abs(nu_base)
        extents.append(xi)
        for cid, nu in reaction.stoichiometry.items():
            running[cid] = running.get(cid, 0.0) + xi * nu
    negative = sorted(cid for cid, n in running.items() if n < 0.0)
    if negative:
        raise ValueError(f"sequential conversions drive components {negative} negative")
    return extents


def z_from(n: Mapping[str, float]) -> dict[str, float]:
    """Mole amounts -> normalized composition (sorted, positive entries only)."""
    total = math.fsum(n.values())
    if total <= 0.0:
        raise ValueError(f"reactor outlet has zero total molar flow (amounts {dict(n)})")
    return {cid: amount / total for cid, amount in sorted(n.items()) if amount > 0.0}


def _outlet_enthalpy(thermo: Thermo, z: Mapping[str, float], total: float, P: float, T: float) -> float:
    """Formation-basis outlet stream enthalpy, W, at (z, P, T)."""
    return enthalpy_with_formation(thermo.flash_pt(dict(z), T, P, total))


def _solve_outlet_T(
    thermo: Thermo,
    z: Mapping[str, float],
    total: float,
    P: float,
    T_in: float,
    target_W: float,
) -> float:
    """Outlet temperature whose formation-basis enthalpy equals ``target_W``.

    H_out(T) is strictly increasing in T (every component's sensible enthalpy
    is), so the root is unique; the bracket expands from the inlet temperature
    until it signs. Refuses past the [1, 5000] K physical range.
    """

    def f(T: float) -> float:
        return _outlet_enthalpy(thermo, z, total, P, T) - target_W

    lo, hi = max(_T_MIN, T_in - 400.0), T_in + 2000.0
    while f(lo) > 0.0 and lo > _T_MIN:
        lo = max(_T_MIN, lo - 500.0)
    if f(lo) > 0.0:
        raise ValueError(
            "adiabatic heat balance is infeasible: even at 1 K the outlet enthalpy "
            "exceeds the inlet enthalpy (the reaction heat exceeds all available sensible heat)"
        )
    while f(hi) < 0.0:
        if hi >= _T_MAX:
            raise ValueError(f"reactor outlet temperature exceeds {_T_MAX} K closing the heat balance")
        hi = min(_T_MAX, hi + 1000.0)
    return float(brentq(f, lo, hi, xtol=1e-9, maxiter=200))


def thermal_outlet(
    inlet: StreamState,
    n_out: Mapping[str, float],
    thermal: Any,
    thermo: Thermo,
    *,
    power_W: float = 0.0,
) -> tuple[StreamState, float]:
    """Outlet state + heat duty closing the energy balance on the thermal mode.

    ``thermal`` is ``"isothermal"`` (outlet at the inlet temperature, duty
    carries the reaction heat), ``"adiabatic"`` (zero duty, outlet temperature
    solved from the balance), ``{"duty_W": q}`` (fixed duty, temperature
    solved) or ``{"T_out": K}`` (fixed outlet temperature, duty solved). The
    balance is on the formation-enthalpy basis:
    H_in + duty + power = H_out, with the electrical work reactors like the
    electrolyser convert.
    """
    z = z_from(n_out)
    total = math.fsum(n_out.values())
    h_in_W = enthalpy_with_formation(inlet)
    if isinstance(thermal, str):
        if thermal == "isothermal":
            outlet = thermo.flash_pt(z, inlet.T, inlet.P, total)
            return outlet, enthalpy_with_formation(outlet) - h_in_W - power_W
        if thermal == "adiabatic":
            T_out = _solve_outlet_T(thermo, z, total, inlet.P, inlet.T, h_in_W + power_W)
            return thermo.flash_pt(z, T_out, inlet.P, total), 0.0
        raise ValueError(
            f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
            '{"duty_W": W} or {"T_out": K}'
        )
    if isinstance(thermal, Mapping):
        if set(thermal) == {"duty_W"}:
            duty = float(thermal["duty_W"])
            T_out = _solve_outlet_T(thermo, z, total, inlet.P, inlet.T, h_in_W + power_W + duty)
            return thermo.flash_pt(z, T_out, inlet.P, total), duty
        if set(thermal) == {"T_out"}:
            T_out = float(thermal["T_out"])
            outlet = thermo.flash_pt(z, T_out, inlet.P, total)
            return outlet, enthalpy_with_formation(outlet) - h_in_W - power_W
        raise ValueError(
            f"thermal mapping takes exactly {{'duty_W': W}} or {{'T_out': K}}, got {sorted(thermal)}"
        )
    raise ValueError(f"thermal mode must be a string or a mapping, got {type(thermal).__name__}")
