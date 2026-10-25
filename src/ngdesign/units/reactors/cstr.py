"""Kinetic CSTR (specs U-R2, units/cstr.md).

Continuous stirred-tank reactor with kinetic rates evaluated at the outlet
(well-mixed) conditions and algebraic extents solved by a damped Newton
iteration. Level R1 demands a single phase in the vessel; level R2 (a later
PR, after R1 merges) carries VLE in the vessel and a phase-resolved rate.

The reaction-rate scale and the concentration-equivalent pressure are the
pfr spec's equations 3 and 4, copied privately (units/cstr.md review
checklist) so the two reactor threads never edit one shared file.

All SI: J, mol, K, Pa, s. Plugin kind "unit", name "cstr", level R1.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.linalg import LinAlgError

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw, Reaction, ReactionSet
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units._physics.kinetics import (
    R,
    ReactionExtentError,
    apply_extents,
    enthalpy_with_formation,
    rate,
)
from ngdesign.units.reactors._shared import reaction_set_param, thermal_outlet, z_from

__all__ = ["CstrConvergenceError", "CstrError", "CstrPhaseError", "CstrR1"]


class CstrError(ValueError):
    """Refusal base for the cstr unit: a bad spec the adapter will not run."""


class CstrConvergenceError(CstrError):
    """The Newton iteration hit its cap, formed a singular Jacobian, or found
    no decreasing step."""


class CstrPhaseError(CstrError):
    """Level R1: the vessel flashed two phases in the declared reacting phase."""


#: Nominal heat capacity of the energy residual's normalizer (units/cstr.md
#: equation 3), J/(mol K). It normalizes the residual only, never the solution.
_CP_NOMINAL = 30.0

#: Vapour-fraction window of the R1 single-phase check (units/cstr.md step 5).
_VF_TOL = 1e-9

#: Newton limits (units/cstr.md step 4): residual and step tolerances, the
#: iteration cap and the backtracking cap.
_RESIDUAL_TOL = 1e-12
_STEP_TOL = 1e-12
_MAX_ITERATIONS = 100
_MAX_HALVINGS = 30

#: Forward-difference Jacobian steps (units/cstr.md step 4), scaled per unknown.
_H_XI = 1e-7
_H_T = 1e-6


def _rate_scale(reaction: Reaction, bulk_density_kg_m3: float | None) -> float:
    """Rate-units scale ``s_j`` (units/pfr.md equation 3, copied privately).

    ``1`` for per-m3 rates, ``rho_b`` (the ``bulk_density_kg_m3`` param) for
    per-kg_cat rates, so the two reactors read identically. Any other string
    is refused.
    """
    kinetics = reaction.kinetics
    if kinetics is None:
        raise CstrError(f"reaction {reaction.id!r} has no kinetics")
    units = kinetics.rate_units
    if units in ("mol/(m3·s)", "mol/(m3*s)", "mol/m3/s"):
        return 1.0
    if units in ("mol/(kg_cat·s)", "mol/(kg_cat*s)", "mol/kg_cat/s"):
        if bulk_density_kg_m3 is None:
            raise CstrError(
                f"reaction {reaction.id!r}: rate_units {units!r} is a catalyst basis "
                "and needs the bulk_density_kg_m3 parameter"
            )
        return bulk_density_kg_m3
    raise CstrError(f"reaction {reaction.id!r}: unknown rate_units {units!r}")


def _effective_pressure(stream: StreamState, T: float, P: float) -> float:
    """Concentration-equivalent pressure of the reacting phase (units/pfr.md
    equation 4, copied privately).

    Vapour: ``P``, the contract's ideal-gas definition ``c = y·P/(R·T)``,
    used unchanged. Liquid: ``P_eff = c_tot·R·T`` with
    ``c_tot = 1000·rho/MW`` (mol/m3) from the liquid phase, so ``rate`` then
    sees ``c_i = x_i·c_tot`` exactly. Mole-fraction-basis rates do not depend
    on P_eff.
    """
    for phase in stream.phases:
        if phase.kind is not PhaseKind.VAPOR:
            return 1000.0 * phase.density / phase.molecular_weight * R * T
    return P


def _validated_scales(rset: ReactionSet, bulk_density_kg_m3: float | None) -> list[float]:
    """Refuse every reaction the adapter cannot run; return the rate scales.

    Refusals (units/cstr.md table): a reaction without kinetics; a PowerLaw
    with an equilibrium model but no explicit ``reverse`` (``kinetics.rate``
    would apply (1 - 1/K) with no reaction quotient); unknown ``rate_units``;
    a catalyst basis without ``bulk_density_kg_m3``.
    """
    scales: list[float] = []
    for reaction in rset.reactions:
        kinetics = reaction.kinetics
        if kinetics is None:
            raise CstrError(
                f"reaction {reaction.id!r} has no kinetics; a kinetic CSTR needs a rate for every reaction"
            )
        if isinstance(kinetics, PowerLaw) and kinetics.reverse is None and reaction.equilibrium is not None:
            raise CstrError(
                f"reaction {reaction.id!r}: equilibrium without an explicit reverse expression "
                "(the CSTR design equation needs a rate that is defined beyond equilibrium)"
            )
        scales.append(_rate_scale(reaction, bulk_density_kg_m3))
    return scales


def _norm_inf(values: list[float]) -> float:
    return max((abs(v) for v in values), default=0.0)


def _norm2(values: list[float]) -> float:
    return math.sqrt(math.fsum(v * v for v in values))


@dataclass(frozen=True)
class _NewtonResult:
    """The converged Newton state: extents, temperature and the iteration record."""

    extents: tuple[float, ...]
    T_newton_K: float
    iterations: int
    residual_inf: float


def _solve_cstr(
    inlet: StreamState,
    rset: ReactionSet,
    thermo: Thermo,
    *,
    volume_m3: float,
    reacting_phase: str,
    scales: list[float],
    duty_W: float | None,
    T_fixed: float | None,
    T_guess_K: float | None,
) -> _NewtonResult:
    """The private Newton solver (units/cstr.md step 4).

    Unknowns ``u = [xi_1..xi_m]`` when ``T_fixed`` is given (isothermal and
    T_out modes), ``u = [xi_1..xi_m, T]`` otherwise (adiabatic and duty
    modes). The residual vector is ``[g_j/sum(F_in)..., g_T]`` with

    - ``g_j = |nu_base,j|·xi_j - s_j·V·r_j(T, P_eff, z_out)`` (equation 1,
      evaluated at outlet conditions), and
    - ``g_T = [H_out(z_out, T, P) - H_in - Q]/(sum(F_in)·30)`` (equation 3,
      formation basis; ``Q = 0`` adiabatic, the fixed duty otherwise).

    Forward-difference Jacobian, ``numpy.linalg.solve`` steps, backtracking
    that halves ``alpha`` while the trial drives an outlet amount negative or
    fails to decrease the residual's 2-norm (at most 30 halvings), and the
    100-iteration cap. A singular Jacobian or an exhausted cap raises
    :class:`CstrConvergenceError`.

    Returns the extents, the Newton temperature, the iteration count and the
    final residual's infinity norm.
    """
    n_in = inlet.component_flows()
    total_in = math.fsum(n_in.values())
    nu_base = [abs(float(reaction.stoichiometry[reaction.base_component])) for reaction in rset.reactions]
    m = len(rset.reactions)
    h_in_W = enthalpy_with_formation(inlet)

    def evaluate(u: list[float]) -> tuple[list[float], StreamState] | None:
        """The residual vector at ``u``, or None when the trial extents drive
        an outlet amount negative (the backtracking rejects such steps)."""
        xi = u[:m]
        T = T_fixed if T_fixed is not None else u[m]
        try:
            n_out = apply_extents(n_in, rset, xi)
        except ReactionExtentError:
            return None
        z = z_from(n_out)
        total = math.fsum(n_out.values())
        stream = thermo.flash_pt(z, T, inlet.P, total)
        vf = stream.vapor_fraction
        if reacting_phase == "vapor":
            if vf < 1.0 - _VF_TOL:
                raise CstrPhaseError(
                    f"the vessel flashes two phases at T = {T} K, P = {inlet.P} Pa "
                    f"(vapour fraction {vf:.6g}): two phases in the vessel; use level R2"
                )
        else:  # "liquid"
            if vf > _VF_TOL:
                raise CstrPhaseError(
                    f"the vessel flashes two phases at T = {T} K, P = {inlet.P} Pa "
                    f"(vapour fraction {vf:.6g}): two phases in the vessel; use level R2"
                )
        p_eff = _effective_pressure(stream, T, inlet.P)
        g = [
            (nu_b * xi_j - s_j * volume_m3 * rate(reaction, T, p_eff, z)) / total_in
            for reaction, s_j, nu_b, xi_j in zip(rset.reactions, scales, nu_base, xi, strict=True)
        ]
        if duty_W is not None:
            h_out = enthalpy_with_formation(stream)
            g.append((h_out - h_in_W - duty_W) / (total_in * _CP_NOMINAL))
        return g, stream

    def jacobian(u: list[float], g0: list[float]) -> list[list[float]]:
        """Forward-difference Jacobian (units/cstr.md step 4)."""
        columns: list[list[float]] = []
        for k in range(len(u)):
            h = _H_XI * max(abs(u[k]), 1e-6 * total_in) if k < m else _H_T
            column: list[float] | None = None
            for _attempt in range(4):
                up = list(u)
                up[k] += h
                trial = evaluate(up)
                if trial is not None:
                    column = [(gp - b) / h for gp, b in zip(trial[0], g0, strict=True)]
                    break
                h *= 0.5
            if column is None:
                raise CstrConvergenceError(
                    f"cstr: the Newton Jacobian could not be formed (unknown {k} evaluates "
                    "nowhere valid; the extents hit the depletion boundary)"
                )
            columns.append(column)
        return [[row[k] for row in columns] for k in range(len(columns[0]))]

    xi0: list[float] = [0.0] * m
    u = xi0 if T_fixed is not None else [*xi0, T_guess_K if T_guess_K is not None else inlet.T]
    first = evaluate(u)
    if first is None:  # unreachable at xi = 0, guarded for typing
        raise CstrConvergenceError("cstr: the inlet amounts are already negative")
    g, _stream = first
    applied_step = 0.0
    iterations = 0
    while _norm_inf(g) > _RESIDUAL_TOL or applied_step > _STEP_TOL * total_in:
        if iterations >= _MAX_ITERATIONS:
            raise CstrConvergenceError(
                f"cstr did not converge in {_MAX_ITERATIONS} Newton iterations "
                f"(last residual norm |g|inf = {_norm_inf(g):.3e})"
            )
        iterations += 1
        J = jacobian(u, g)
        try:
            du = np.linalg.solve(np.array(J), -np.array(g)).tolist()
        except LinAlgError as exc:
            raise CstrConvergenceError("cstr: the Newton Jacobian is singular") from exc
        alpha = 1.0
        accepted: tuple[float, list[float], tuple[list[float], StreamState]] | None = None
        for _halving in range(_MAX_HALVINGS + 1):
            trial_u = [ui + alpha * dui for ui, dui in zip(u, du, strict=True)]
            trial = evaluate(trial_u)
            if trial is not None and _norm2(trial[0]) < _norm2(g):
                accepted = (alpha, trial_u, trial)
                break
            alpha *= 0.5
        if accepted is None:
            raise CstrConvergenceError(
                f"cstr did not converge: backtracking found no decreasing step in "
                f"{_MAX_HALVINGS} halvings (last residual norm |g|inf = {_norm_inf(g):.3e})"
            )
        alpha_applied, u_next, (g_next, _stream_next) = accepted
        applied_step = alpha_applied * max((abs(d) for d in du[:m]), default=0.0)
        u, g = u_next, g_next
    T_newton = T_fixed if T_fixed is not None else u[m]
    return _NewtonResult(
        extents=tuple(u[:m]), T_newton_K=T_newton, iterations=iterations, residual_inf=_norm_inf(g)
    )


def _positive(params: Mapping[str, Any], key: str) -> float:
    """A required positive number param (units/cstr.md refusal table)."""
    value = float(params[key])
    if value <= 0.0:
        raise CstrError(f"{key} {value!r} must be positive")
    return value


def _energy_mode(thermal: Any, inlet: StreamState) -> tuple[float | None, float | None]:
    """Classify the thermal mode for the Newton unknowns.

    Returns ``(duty_W, T_fixed)``: ``(None, T_in)`` isothermal, ``(0, None)``
    adiabatic, ``(q, None)`` fixed duty, ``(None, T_out)`` fixed outlet
    temperature. A bad mode raises the same ``ValueError`` text
    :func:`thermal_outlet` raises, so the refusal table's wording holds
    whichever check sees the bad mode first.
    """
    if isinstance(thermal, str):
        if thermal == "isothermal":
            return None, inlet.T
        if thermal == "adiabatic":
            return 0.0, None
        raise ValueError(
            f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic', "
            '{"duty_W": W} or {"T_out": K}'
        )
    if isinstance(thermal, Mapping):
        if set(thermal) == {"duty_W"}:
            return float(thermal["duty_W"]), None
        if set(thermal) == {"T_out"}:
            return None, float(thermal["T_out"])
        raise ValueError(
            f"thermal mapping takes exactly {{'duty_W': W}} or {{'T_out': K}}, got {sorted(thermal)}"
        )
    raise ValueError(f"thermal mode must be a string or a mapping, got {type(thermal).__name__}")


class CstrR1:
    """Kinetic CSTR, level R1: algebraic extents with the rate evaluated at
    the outlet conditions, single phase in the vessel (units/cstr.md).

    Params: ``reaction_set`` (inline ReactionSet), ``volume_m3`` (> 0),
    ``thermal`` ('isothermal' | 'adiabatic' | {duty_W: W} | {T_out: K};
    default isothermal), ``reacting_phase`` ('vapor' | 'liquid', default
    'vapor'), ``bulk_density_kg_m3`` (per-kg_cat rates) and ``T_guess_K``
    (Newton start; selects the steady-state branch). ``info`` carries each
    reaction's extent and conversion, the Newton iteration count,
    ``T_newton_K`` and ``T_closure_gap_K`` from the ``thermal_outlet``
    energy closure.
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        inlet = inlets["inlet"]
        volume_m3 = _positive(params, "volume_m3")
        reacting_phase = str(params.get("reacting_phase", "vapor"))
        if reacting_phase not in ("vapor", "liquid"):
            raise CstrError(f"reacting_phase {reacting_phase!r} is not one of 'vapor', 'liquid' (level R1)")
        rset = reaction_set_param(params["reaction_set"])
        bulk = params.get("bulk_density_kg_m3")
        bulk_density = float(bulk) if bulk is not None else None
        scales = _validated_scales(rset, bulk_density)
        duty_W, T_fixed = _energy_mode(params.get("thermal", "isothermal"), inlet)
        guess = params.get("T_guess_K")
        newton = _solve_cstr(
            inlet,
            rset,
            thermo,
            volume_m3=volume_m3,
            reacting_phase=reacting_phase,
            scales=scales,
            duty_W=duty_W,
            T_fixed=T_fixed,
            T_guess_K=float(guess) if guess is not None else None,
        )
        n_out = apply_extents(inlet.component_flows(), rset, list(newton.extents))
        outlet, duty = thermal_outlet(inlet, n_out, params.get("thermal", "isothermal"), thermo)
        info: dict[str, float] = {}
        for reaction, xi_j in zip(rset.reactions, newton.extents, strict=True):
            info[f"extent_{reaction.id}_mol_s"] = xi_j
            base_flow = float(inlet.composition.get(reaction.base_component, 0.0)) * inlet.molar_flow
            nu_base = abs(float(reaction.stoichiometry[reaction.base_component]))
            info[f"conversion_{reaction.base_component}_{reaction.id}"] = (
                nu_base * xi_j / base_flow if base_flow > 0.0 else 0.0
            )
        info["newton_iterations"] = float(newton.iterations)
        info["T_newton_K"] = newton.T_newton_K
        info["T_closure_gap_K"] = outlet.T - newton.T_newton_K
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R1-A closed-form basis: isothermal first-order gas isomerization.

        nC4 -> iC4 at 500 K, 2.0e5 Pa, 1.0 mol/s of pure nC4, V = 2.0 m3
        (units/cstr.md, tests): k(500 K) = 1.0e3·exp(-5.0e4/(R·500)) = 5.978e-3
        1/s, c = P/(R·T) = 48.11 mol/m3, Da = k·V·c/F_A0 = 0.575299226 and
        X = Da/(1 + Da) = 0.365199967.
        """
        feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
        params = {
            "reaction_set": {
                "id": "cstr_isom_case",
                "components": ["nC4", "iC4"],
                "reactions": [
                    {
                        "id": "isom",
                        "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                        "base_component": "nC4",
                        "provenance": "n-butane isomerization, first-order gas-phase lump "
                        "(Fogler, Elements of CRE, 4th ed., CSTR design equation)",
                        "kinetics": {
                            "rate_units": "mol/(m3·s)",
                            "k0": 1.0e3,
                            "Ea": 5.0e4,
                            "orders": {"nC4": 1.0},
                            "basis": "concentration",
                        },
                    }
                ],
            },
            "volume_m3": 2.0,
            "thermal": "isothermal",
        }
        return {"inlet": feed}, params
