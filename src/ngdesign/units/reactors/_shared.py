"""Shared reactor-adapter helpers (spec U-F).

The mechanical core the four stoichiometric reactor adapters share: resolving
the ``reaction_set`` parameter, converting stated conversions into extents,
normalizing mole amounts into a feed composition, and closing the thermal
mode (isothermal / adiabatic / fixed duty) on the formation-enthalpy basis.

All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import ReactionSet
from ngdesign.contracts.stream import StreamState
from ngdesign.data import chemdb, component_record
from ngdesign.data.formation import MissingFormationData, enthalpy_datum, gas_model
from ngdesign.provenance.citations import cite_chemdb, cite_mw, cite_species_model
from ngdesign.provenance.recorder import Recorder, ValueRef, active
from ngdesign.units._physics.kinetics import enthalpy_with_formation

#: JANAF ideal-gas standard-state pressure for equilibrium quotients, Pa.
P_REF = 1.0e5

#: Bracket bounds for the adiabatic / duty outlet-temperature solve, K.
_T_MIN = 1.0
_T_MAX = 5000.0


# ---------------------------------------------------------------- provenance (tracing on only)


def _cas(cid: str) -> str | None:
    try:
        cas = component_record(cid).get("cas")
    except ValueError:
        return None
    return str(cas) if cas else None


def trace_hf(rec: Recorder, cid: str) -> ValueRef:
    """Cited leaf for the ΔfH°298 datum :func:`enthalpy_datum` returns for ``cid``.

    The citation is the chemdb row the value was read from (gas first, then the
    condensed phases :func:`enthalpy_datum` falls back to), matched exactly; a value
    no row reproduces is recorded uncited.
    """
    try:
        value = enthalpy_datum(cid)
    except (MissingFormationData, chemdb.ChemDbError):
        return rec.cited(f"{cid} ΔfH°298", float("nan"), "J/mol", None)
    cas = _cas(cid)
    citation = None
    if cas is not None:
        for prop in ("Hf_gas", "Hf_solid", "Hf_liquid"):
            if chemdb.maybe(cas, prop) == value:
                citation = cite_chemdb(cas, prop)
                break
    return rec.cited(f"{cid} ΔfH°298", value, "J/mol", citation)


def trace_mw(rec: Recorder, cid: str) -> ValueRef:
    """Cited leaf for a component's molar mass (``component_record(cid)["mw"]``), g/mol.

    Databank components take ``chemicals``' formula weight (Open Babel element table,
    :func:`cite_mw`); a pseudo-component's correlated or stated value is recorded with
    the provenance its record carries, estimated when correlated.
    """
    record = component_record(cid)
    value = float(record["mw"])
    origin = str((record.get("provenance") or {}).get("mw", ""))
    if origin.startswith("chemicals") and record.get("formula"):
        return rec.cited(f"{cid} M", value, "g/mol", cite_mw())
    return rec.cited(f"{cid} M", value, "g/mol", None, note=f"molar mass from {origin or 'unknown source'}")


def trace_species_shape(rec: Recorder, cid: str) -> ValueRef:
    """Cited leaf naming the ideal-gas H°(T) − H°298 and S°(T) model of ``cid``.

    The value is the model's name (``janaf:C-067``, ``shomate``, ...); the citation is
    the source of the rows it was built from (:func:`cite_species_model`).
    """
    try:
        model = gas_model(cid)
    except MissingFormationData:
        return rec.cited(f"{cid} ideal-gas H°(T), S°(T)", "no gas model", "", None)
    citation = cite_species_model(model)
    s298 = model.provenance.get("s298")
    note = f"S°298 from {s298}" if s298 else None
    if s298 is not None and citation is not None:
        # a fit anchored on a separately stated S°298 (or one derived from ΔfG°)
        anchor = cite_chemdb(model.cas, "Gf_gas" if s298.startswith("derived") else "S0_gas")
        if anchor is None:
            citation = None
        else:
            citation = citation.model_copy(
                update={"reference": f"{citation.reference or ''}; S°298: {anchor.citation}".lstrip("; ")}
            )
    return rec.cited(f"{cid} ideal-gas H°(T), S°(T)", model.model, "", citation, note=note)


def trace_formation_enthalpy(rec: Recorder, name: str, value: float, state: StreamState) -> ValueRef:
    """Record ``value = enthalpy_with_formation(state)`` with its cited ΔfH°298 leaves."""
    inputs: dict[str, Any] = {
        "F": (state, "molar_flow"),
        "h": (state, "enthalpy"),
        "z": (state, "composition"),
    }
    for cid in state.composition:
        inputs[f"ΔfH°[{cid}]"] = trace_hf(rec, cid)
    return rec.equation(name, value, "W", "formation_enthalpy_basis", inputs)


def trace_component_flows(
    rec: Recorder, state: StreamState, n: Mapping[str, float], name: str = "n_in"
) -> ValueRef:
    """Record ``n_i = F z_i`` (``StreamState.component_flows``) of one stream."""
    return rec.equation(
        name, n, "mol/s", "component_flows", {"F": (state, "molar_flow"), "z": (state, "composition")}
    )


def trace_extents_applied(
    rec: Recorder, n_out: Mapping[str, float], n_in_ref: ValueRef, extents: Mapping[str, Any]
) -> ValueRef:
    """Record ``n_out = n_in + Σ_j ν_j ξ_j`` (:func:`apply_extents`)."""
    return rec.equation("n_out", n_out, "mol/s", "reaction_stoichiometry", {"n_in": n_in_ref, **extents})


def trace_amounts(
    rec: Recorder, n_out: Mapping[str, float], z: Mapping[str, float], total: float
) -> tuple[ValueRef, ValueRef]:
    """Record the outlet composition and flow normalized from mole amounts ``n_out``."""
    z_ref = rec.equation("z_out", z, "1", "mole_fractions", {"n": n_out})
    f_ref = rec.equation("F_out", total, "mol/s", "mole_fractions", {"n": n_out})
    return z_ref, f_ref


def trace_reaction_duty(
    rec: Recorder, duty: float, outlet: StreamState, h_in_ref: ValueRef, power_W: float = 0.0
) -> ValueRef:
    """Record ``duty = H_out - H_in - W`` on the formation-enthalpy basis."""
    h_out_ref = trace_formation_enthalpy(rec, "H_out", enthalpy_with_formation(outlet), outlet)
    inputs: dict[str, Any] = {"H_out": h_out_ref, "H_in": h_in_ref}
    if power_W != 0.0:
        inputs["W"] = power_W
    return rec.equation("duty_W", duty, "W", "reaction_energy_balance", inputs)


def trace_outlet_T(
    rec: Recorder,
    T_out: float,
    h_in_ref: ValueRef,
    z: Mapping[str, float],
    total: Any,
    inlet: StreamState,
    *,
    power_W: float = 0.0,
    duty_W: float = 0.0,
    method: str = "reactor_outlet_temperature",
    extra: Mapping[str, Any] | None = None,
) -> ValueRef:
    """Record the outlet temperature closing ``H_out(T) = H_in + Q + W`` (a 1-D root solve)."""
    inputs: dict[str, Any] = {"H_in": h_in_ref, "z": z, "F": total, "P": (inlet, "P")}
    if duty_W != 0.0:
        inputs["Q"] = duty_W
    if power_W != 0.0:
        inputs["W"] = power_W
    for cid in z:
        inputs[f"ΔfH°[{cid}]"] = trace_hf(rec, cid)
    inputs.update(extra or {})
    return rec.equation("T_out", T_out, "K", method, inputs)


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


def close_thermal(
    enthalpy_at: Callable[[float], float],
    T_in: float,
    h_in_W: float,
    thermal: Any,
) -> tuple[float, float]:
    """(T_out, duty) of a reactor whose outlet composition itself depends on T.

    ``enthalpy_at(T)`` is the total outlet enthalpy, W, with the composition re-solved
    at T. Modes as :func:`thermal_outlet`: isothermal, adiabatic, ``{"duty_W": q}``,
    ``{"T_out": K}``.
    """
    if isinstance(thermal, Mapping) and set(thermal) == {"T_out"}:
        T_out = float(thermal["T_out"])
        return T_out, enthalpy_at(T_out) - h_in_W
    if isinstance(thermal, str) and thermal == "isothermal":
        return T_in, enthalpy_at(T_in) - h_in_W
    if (isinstance(thermal, str) and thermal == "adiabatic") or (
        isinstance(thermal, Mapping) and set(thermal) == {"duty_W"}
    ):
        duty = 0.0 if isinstance(thermal, str) else float(thermal["duty_W"])
        target = h_in_W + duty

        def f(T: float) -> float:
            return enthalpy_at(T) - target

        lo, hi = T_in - 400.0, T_in + 2000.0
        while f(lo) > 0.0 and lo > _T_MIN:
            lo = max(_T_MIN, lo - 500.0)
        if f(lo) > 0.0:
            raise ValueError(
                "heat balance is infeasible: even at 1 K the outlet enthalpy exceeds "
                "the inlet enthalpy (the reaction heat exceeds all available sensible heat)"
            )
        while f(hi) < 0.0:
            if hi >= _T_MAX:
                raise ValueError(f"reactor outlet temperature exceeds {_T_MAX} K closing the heat balance")
            hi = min(_T_MAX, hi + 1000.0)
        return float(brentq(f, lo, hi, xtol=1e-8, maxiter=100)), duty
    raise ValueError(
        f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
        '{"duty_W": W} or {"T_out": K}'
    )


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
    rec = active()
    h_in_ref: ValueRef | None = None
    if rec is not None:
        trace_amounts(rec, n_out, z, total)
        h_in_ref = trace_formation_enthalpy(rec, "H_in", h_in_W, inlet)
    if isinstance(thermal, str):
        if thermal == "isothermal":
            outlet = thermo.flash_pt(z, inlet.T, inlet.P, total)
            duty = enthalpy_with_formation(outlet) - h_in_W - power_W
            if rec is not None and h_in_ref is not None:
                trace_reaction_duty(rec, duty, outlet, h_in_ref, power_W)
            return outlet, duty
        if thermal == "adiabatic":
            T_out = _solve_outlet_T(thermo, z, total, inlet.P, inlet.T, h_in_W + power_W)
            if rec is not None and h_in_ref is not None:
                trace_outlet_T(rec, T_out, h_in_ref, z, total, inlet, power_W=power_W)
            return thermo.flash_pt(z, T_out, inlet.P, total), 0.0
        raise ValueError(
            f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
            '{"duty_W": W} or {"T_out": K}'
        )
    if isinstance(thermal, Mapping):
        if set(thermal) == {"duty_W"}:
            duty = float(thermal["duty_W"])
            T_out = _solve_outlet_T(thermo, z, total, inlet.P, inlet.T, h_in_W + power_W + duty)
            if rec is not None and h_in_ref is not None:
                trace_outlet_T(rec, T_out, h_in_ref, z, total, inlet, power_W=power_W, duty_W=duty)
            return thermo.flash_pt(z, T_out, inlet.P, total), duty
        if set(thermal) == {"T_out"}:
            T_out = float(thermal["T_out"])
            outlet = thermo.flash_pt(z, T_out, inlet.P, total)
            duty = enthalpy_with_formation(outlet) - h_in_W - power_W
            if rec is not None and h_in_ref is not None:
                trace_reaction_duty(rec, duty, outlet, h_in_ref, power_W)
            return outlet, duty
        raise ValueError(
            f"thermal mapping takes exactly {{'duty_W': W}} or {{'T_out': K}}, got {sorted(thermal)}"
        )
    raise ValueError(f"thermal mode must be a string or a mapping, got {type(thermal).__name__}")
