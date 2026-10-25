"""Kinetic plug-flow reactor integrator (spec U-R2 wave, unit ``pfr``).

The shared plug-flow integrator of the reactor chain: ``naphtha_ht``,
``reformer_cat`` and ``fixed_bed_tubular`` import
:func:`integrate_plug_flow` read-only and never edit this module.

Method (spec ``specs/backend/units/pfr.md``): the steady-state PFR mole
balances are integrated over reactor volume V (m3) as an extents ODE,
d(xi_j)/dV = s_j * a * eta_j * r_j / |nu_base,j| (Fogler, *Elements of CRE*,
mole-balance design equation dF_A/dV = r_A written per reaction), together
with the energy balance dT/dV = [-Sum_j dH_j(T) dxi_j/dV + q_V] / (Sum_i F_i
cp,mix), the accumulated heat dQ/dV = q_V and (from R2) the Ergun bed
pressure drop per unit volume.  ``r_j`` is
:func:`ngdesign.units._physics.kinetics.rate` on its base-component extent
basis; dividing by |nu_base,j| converts it to an extent rate.

Flash budget (P0-06): the RHS never flashes.  Single-phase properties come
from ``thermo.phase_props`` — a build without a phase split; two-phase and
phase-absence are refused by an audit that flashes once per output point, so
the flash count is O(n_output), independent of the reactor volume V.

The outlet temperature is **not** taken from the ODE: adapters close the
energy balance exactly on the formation-enthalpy basis through
``_shared.thermal_outlet`` / ``_shared._solve_outlet_T``.  The ODE end
temperature is reported next to the closure temperature as
``T_closure_gap_K`` (the ideal-gas dH of the energy ODE against the
package's residual enthalpy); it is reported, never forced to zero.

All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.integrate import solve_ivp

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw, Reaction, ReactionSet
from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.units._physics.kinetics import (
    R,
    heat_of_reaction,
    rate,
)
from ngdesign.units.reactors._shared import z_from

#: RHS evaluations before the integration is refused (spec: 20,000).
RHS_CAP = 20_000

#: Rate-unit strings accepted per unit reactor volume (spec equation 3).
_VOLUME_RATE_UNITS = ("mol/(m3·s)", "mol/(m3*s)", "mol/m3/s")

#: Rate-unit strings accepted per unit catalyst mass (spec equation 3).
_CATALYST_RATE_UNITS = ("mol/(kg_cat·s)", "mol/(kg_cat*s)", "mol/kg_cat/s")

#: Reacting-phase name -> contract PhaseKind for flash-free phase_props calls.
_PHASE_KIND: dict[str, PhaseKind] = {
    "vapor": PhaseKind.VAPOR,
    "liquid": PhaseKind.HC_LIQUID,
}


class PlugFlowError(ValueError):
    """Raised when a plug-flow integration is ill-posed or fails."""


@dataclass(frozen=True)
class HeatModel:
    """R2: pluggable wall heat transfer (spec algorithm step 2, equation 7).

    ``q_V(V, T, extra)`` returns the heat added to the process per unit
    volume (W/m3); ``d_extra(V, T, extra)`` the derivative of the extra ODE
    states (e.g. a coolant temperature that itself evolves).  Fixed coolant
    temperature needs no extra states.
    """

    n_extra: int
    y0_extra: tuple[float, ...]
    q_V: Callable[[float, float, Sequence[float]], float]
    d_extra: Callable[[float, float, Sequence[float]], Sequence[float]]


@dataclass(frozen=True)
class PlugFlowProfile:
    """The integrated plug-flow solution, per output point."""

    V_m3: tuple[float, ...]
    T_K: tuple[float, ...]
    P_Pa: tuple[float, ...]
    #: Extent of each reaction (mol/s), per output point, per reaction.
    extents: tuple[tuple[float, ...], ...]
    #: The heat model's extra ODE states, per output point.
    extra: tuple[tuple[float, ...], ...]
    Q_W: float
    n_rhs: int


def _scale_j(reaction: Reaction, bulk_density_kg_m3: float | None) -> float:
    """The rate-basis scale s_j (spec equation 3)."""
    units = reaction.kinetics.rate_units  # type: ignore[union-attr]
    if units in _VOLUME_RATE_UNITS:
        return 1.0
    if units in _CATALYST_RATE_UNITS:
        if bulk_density_kg_m3 is None:
            raise PlugFlowError(
                f"reaction '{reaction.id}': rate_units {units!r} is per catalyst mass "
                "and requires the param bulk_density_kg_m3"
            )
        return bulk_density_kg_m3
    raise PlugFlowError(
        f"reaction '{reaction.id}': rate_units {units!r} is not one of "
        f"{_VOLUME_RATE_UNITS + _CATALYST_RATE_UNITS}"
    )


def _validate_reactions(rset: ReactionSet, bulk_density_kg_m3: float | None) -> list[float]:
    """Refuse ill-posed kinetics up front; return the per-reaction scales s_j."""
    scales: list[float] = []
    for reaction in rset.reactions:
        if reaction.kinetics is None:
            raise PlugFlowError(f"reaction '{reaction.id}' has no kinetics")
        if isinstance(reaction.kinetics, PowerLaw) and reaction.equilibrium is not None:
            raise PlugFlowError(
                f"reaction '{reaction.id}': a PowerLaw with an equilibrium model but no "
                "explicit reverse is refused: kinetics.rate would multiply by (1 - 1/K) "
                "without the reaction quotient; give an explicit reverse"
            )
        scales.append(_scale_j(reaction, bulk_density_kg_m3))
    return scales


def _flows(rset: ReactionSet, f0: Mapping[str, float], xi: Sequence[float]) -> dict[str, float]:
    """Species molar flows from extents (spec equation 1)."""
    f = {cid: float(n) for cid, n in f0.items()}
    for reaction, xi_j in zip(rset.reactions, xi, strict=True):
        for cid, nu in reaction.stoichiometry.items():
            f[cid] = f.get(cid, 0.0) + float(nu) * xi_j
    return f


def _phase_of(state: StreamState, reacting_phase: Literal["vapor", "liquid"]) -> Phase | None:
    """The single reacting phase of a flashed state."""
    if reacting_phase == "vapor":
        for phase in state.phases:
            if phase.kind == PhaseKind.VAPOR:
                return phase
    else:
        for phase in state.phases:
            if phase.kind != PhaseKind.VAPOR:
                return phase
    return None


def integrate_plug_flow(
    inlet: StreamState,
    rset: ReactionSet,
    thermo: Thermo,
    *,
    volume_m3: float,
    energy: Literal["isothermal", "adiabatic", "uniform_duty", "heat_model"],
    duty_W: float = 0.0,
    heat: HeatModel | None = None,
    reacting_phase: Literal["vapor", "liquid"] = "vapor",
    bulk_density_kg_m3: float | None = None,
    ergun: object | None = None,  # R2: ErgunBed, owned by the R2 step
    rate_multiplier: Callable[[int, float, float, Mapping[str, float]], float] | None = None,
    n_output: int = 51,
) -> PlugFlowProfile:
    """Integrate the kinetic plug-flow equations over ``volume_m3``.

    See the module docstring for the method; the spec
    (``specs/backend/units/pfr.md``) owns the equations and the refusal
    table.  ``rate_multiplier(j, T, P, z)`` returns a*eta_j for reaction j
    (R3); ``None`` means 1.0.  ``ergun`` is the R2 packed bed; ``None`` means
    no pressure drop.
    """
    if volume_m3 <= 0.0:
        raise PlugFlowError("volume_m3 must be > 0")
    if energy == "heat_model" and heat is None:
        raise PlugFlowError("energy='heat_model' requires a heat model")
    if n_output < 2:
        raise PlugFlowError("n_output must be >= 2")

    scales = _validate_reactions(rset, bulk_density_kg_m3)
    reactions = rset.reactions
    m = len(reactions)
    f0 = inlet.component_flows()
    f_tot0 = math.fsum(f0.values())
    t_in = float(inlet.T)
    p_in = float(inlet.P)

    # Concentration-equivalent pressure (spec equation 4): the vapour phase
    # uses the contract's ideal-gas definition unchanged.
    p_eff_scale = 1.0 if reacting_phase == "vapor" else None

    q_v: Callable[[float, float, Sequence[float]], float]
    if energy == "isothermal":
        q_v = lambda _v, _t, _extra: 0.0  # noqa: E731 - closure owns the duty
    elif energy == "adiabatic":
        q_v = lambda _v, _t, _extra: 0.0  # noqa: E731
    elif energy == "uniform_duty":
        q_per_v = duty_W / volume_m3
        q_v = lambda _v, _t, _extra: q_per_v  # noqa: E731
    else:
        assert heat is not None
        q_v = heat.q_V

    n_rhs = 0
    n_extra = heat.n_extra if heat is not None else 0

    def rhs(v: float, y: np.ndarray) -> np.ndarray:
        nonlocal n_rhs
        n_rhs += 1
        if n_rhs > RHS_CAP:
            raise PlugFlowError("RHS evaluation cap")
        xi = y[:m]
        t = float(y[m])
        p = float(y[m + 1])
        extra = tuple(float(e) for e in y[m + 3 :])

        f = _flows(rset, f0, xi.tolist())
        negative = sorted(cid for cid, n in f.items() if n < 0.0)
        if negative:
            raise PlugFlowError(
                f"reaction set {rset.id!r} depletes component {negative[0]!r} at V = {v:g} m3"
            )
        f_tot = math.fsum(f.values())
        z = z_from(f)
        # Flash-free RHS (the O(1)-in-V flash budget): single-phase
        # properties come from phase_props, which never runs a phase split.
        # Two-phase and phase-absence are refused by the audit after the
        # solve, so the flash count is independent of V.
        props = thermo.phase_props(z, t, p, _PHASE_KIND[reacting_phase])
        cp_molar = float(props.cp)

        # Concentration-equivalent pressure for a liquid reacting phase
        # (spec equation 4): c_tot = 1000 rho / MW, P_eff = c_tot R T.
        if p_eff_scale is None:
            p_eff = 1000.0 * float(props.density) / float(props.molecular_weight) * R * t
        else:
            p_eff = p

        dxi = np.zeros(m)
        d_h = 0.0
        for j, reaction in enumerate(reactions):
            assert reaction.kinetics is not None
            r_j = rate(reaction, t, p_eff, z)
            multiplier = 1.0 if rate_multiplier is None else rate_multiplier(j, t, p_eff, z)
            nu_base = float(reaction.stoichiometry[reaction.base_component])
            dxi[j] = scales[j] * multiplier * r_j / abs(nu_base)
            if energy != "isothermal":
                d_h += float(heat_of_reaction(reaction, t)) * dxi[j]

        q = q_v(v, t, extra)
        if energy == "isothermal":
            dt = 0.0
        else:
            dt = (-d_h + q) / (f_tot * cp_molar)
        dq = q if energy != "isothermal" else 0.0
        dp = 0.0  # R1 carries no pressure drop; the R2 step adds Ergun here.

        out = np.zeros(m + 3 + n_extra)
        out[:m] = dxi
        out[m] = dt
        out[m + 1] = dp
        out[m + 2] = dq
        if heat is not None and n_extra:
            out[m + 3 :] = heat.d_extra(v, t, extra)
        return out

    y0 = np.zeros(m + 3 + n_extra)
    y0[m] = t_in
    y0[m + 1] = p_in
    y0[m + 2] = 0.0
    if heat is not None and n_extra:
        y0[m + 3 :] = heat.y0_extra

    atol = np.zeros(m + 3 + n_extra)
    atol[:m] = 1.0e-12 * f_tot0
    atol[m] = 1.0e-8
    atol[m + 1] = 1.0e-6
    atol[m + 2] = 1.0e-8 * max(1.0, abs(duty_W))
    if n_extra:
        atol[m + 3 :] = 1.0e-8

    # Reactant depletion event: the smallest flow among the components that
    # start positive and are consumed by some reaction (nu < 0).  Products
    # start at zero and only grow, so the literal minimum over all species
    # would never see a depleting reactant cross the threshold.
    reactants = sorted(
        {
            cid
            for reaction in reactions
            for cid, nu in reaction.stoichiometry.items()
            if nu < 0.0 and f0.get(cid, 0.0) > 0.0
        }
    )

    def depletion(_v: float, y: np.ndarray) -> float:
        xi = y[:m]
        f = _flows(rset, f0, xi.tolist())
        if not reactants:
            return 1.0
        return min(f[cid] for cid in reactants) - 1.0e-14 * f_tot0

    depletion.terminal = True  # type: ignore[attr-defined]
    depletion.direction = -1.0  # type: ignore[attr-defined]

    def pressure_floor(_v: float, y: np.ndarray) -> float:
        return float(y[m + 1]) - 0.1 * p_in

    pressure_floor.terminal = True  # type: ignore[attr-defined]
    pressure_floor.direction = -1.0  # type: ignore[attr-defined]

    t_eval = np.linspace(0.0, volume_m3, n_output)
    try:
        sol = solve_ivp(
            rhs,
            (0.0, volume_m3),
            y0,
            method="BDF",
            rtol=1.0e-8,
            atol=atol,
            t_eval=t_eval,
            events=(depletion, pressure_floor),
            dense_output=False,
        )
    except PlugFlowError:
        raise
    except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
        raise PlugFlowError(f"integration failed: {exc}") from exc
    if not bool(sol.success):
        raise PlugFlowError(f"integration failed: {sol.message}")

    # Terminal-event refusals: the event stops the integration at the
    # crossing; name the component (depletion) or the pressure drop.
    if sol.t_events is not None:
        if len(sol.t_events) > 0 and sol.t_events[0].size > 0:
            v_hit = float(sol.t_events[0][0])
            f_hit = _flows(rset, f0, sol.y[:m, -1].tolist())
            cid = min(reactants, key=lambda c: f_hit[c])
            raise PlugFlowError(f"reaction set {rset.id!r} depletes component {cid!r} at V = {v_hit:g} m3")
        if len(sol.t_events) > 1 and sol.t_events[1].size > 0:
            raise PlugFlowError(
                f"pressure drop exceeds 90 % of inlet pressure at V = {float(sol.t_events[1][0]):g} m3"
            )

    # Phase audit at the output points: one flash per point, so the flash
    # count is O(n_output) and independent of the reactor volume V (spec:
    # the flash budget must not scale with V). Refuses a two-phase state or
    # a missing reacting phase anywhere along the profile.
    for i, v_i in enumerate(t_eval):
        f_i = _flows(rset, f0, sol.y[:m, i].tolist())
        t_i = float(sol.y[m, i])
        p_i = float(sol.y[m + 1, i])
        state_i = thermo.flash_pt(z_from(f_i), t_i, p_i, math.fsum(f_i.values()))
        vf_i = float(state_i.vapor_fraction)
        if 1.0e-9 < vf_i < 1.0 - 1.0e-9:
            raise PlugFlowError(
                f"the PFR is single-phase but the state at V = {v_i:g} m3 is two-phase "
                f"(vapour fraction {vf_i:.6f})"
            )
        if _phase_of(state_i, reacting_phase) is None:
            raise PlugFlowError(
                f"reacting phase {reacting_phase!r} is absent from the single-phase state at V = {v_i:g} m3"
            )

    y_end = sol.y[:, -1]
    # Per output point, per reaction (mol/s): transpose the sol.y rows.
    extents_rows = tuple(
        tuple(float(xi) for xi in point) for point in zip(*(sol.y[j] for j in range(m)), strict=True)
    )
    extra_rows: tuple[tuple[float, ...], ...] = (
        tuple(
            tuple(float(e) for e in point)
            for point in zip(*(sol.y[m + 3 + k] for k in range(n_extra)), strict=True)
        )
        if n_extra
        else ()
    )
    return PlugFlowProfile(
        V_m3=tuple(float(v) for v in t_eval),
        T_K=tuple(float(t) for t in sol.y[m]),
        P_Pa=tuple(float(p) for p in sol.y[m + 1]),
        extents=extents_rows,
        extra=extra_rows,
        Q_W=float(y_end[m + 2]),
        n_rhs=n_rhs,
    )
