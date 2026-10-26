"""Kinetic plug-flow reactor integrator (spec U-R2 wave, unit ``pfr``).

The shared plug-flow integrator of the reactor chain: ``naphtha_ht``,
``reformer_cat`` and ``fixed_bed_tubular`` import
:func:`integrate_plug_flow` read-only and never edit this module.

Method (spec ``specs/backend/units/pfr.md``): the steady-state PFR mole
balances are integrated over reactor volume V (m3) as an extents ODE,
d(xi_j)/dV = s_j * a * eta_j * r_j / |nu_base,j| (Fogler, *Elements of CRE*,
mole-balance design equation dF_A/dV = r_A written per reaction), together
with the energy balance dT/dV = [-Sum_j dH_j(T) dxi_j/dV + q_V] / (Sum_i F_i
cp,mix), the accumulated heat dQ/dV = q_V and the Ergun packed-bed pressure
drop per unit volume (spec equation 8, R2).  ``r_j`` is
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
``T_closure_gap_K`` (the residual difference between the ODE's
package-consistent ΔrH(T) and the closure's flash-based solve); it is
reported, never forced to zero.

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
from ngdesign.contracts.reactions import LHHW, Reaction, ReactionSet
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

#: Reference temperature of the databank formation enthalpies, K.
T_REF_FORMATION = 298.15


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


@dataclass(frozen=True)
class ErgunBed:
    """R2: packed bed for the Ergun pressure drop (spec equation 8).

    ``particle_diameter_m`` is the effective particle diameter D_p (m) and
    ``voidage`` the bed voidage phi, which must lie strictly between 0 and 1.
    """

    particle_diameter_m: float
    voidage: float


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
        if isinstance(reaction.kinetics, LHHW) and reaction.equilibrium is not None:
            # LHHW is used directly as a forward rate and carries no equilibrium
            # term; silently ignoring the model would mislead the caller.
            raise PlugFlowError(
                f"reaction '{reaction.id}': an LHHW rate ignores the equilibrium "
                "model; drop the equilibrium model or use a PowerLaw with reverse"
            )
        scales.append(_scale_j(reaction, bulk_density_kg_m3))
    return scales


#: Relative step of the finite difference on component flows, as a fraction
#: of the total molar flow.
_H_BAR_REL_STEP = 1e-5


def _stream_enthalpy(thermo: Thermo, f: Mapping[str, float], t: float, p: float, kind: PhaseKind) -> float:
    """The mixture enthalpy flow F_tot·H_mix(z, T, P) in J/s (flash-free)."""
    f_tot = math.fsum(f.values())
    return f_tot * float(thermo.phase_props(z_from(f), t, p, kind).enthalpy)


def _partial_molar_enthalpies(
    thermo: Thermo, f: Mapping[str, float], t: float, p: float, kind: PhaseKind
) -> dict[str, float]:
    """Partial molar enthalpies h̄_i = ∂(F·H_mix)/∂F_i at fixed (T, P), J/mol.

    A central finite difference on the component flows of the mixture
    enthalpy flow :func:`_stream_enthalpy`; ``phase_props`` never flashes,
    so the O(1)-in-V flash budget is unchanged.  This is the derivative the
    outlet closure balances: summing pure-component enthalpies instead
    drops the mixture's enthalpy of mixing (about 0.16 J/mol on
    ``ideal-raoult`` for the nC4/iC4 case) and leaves a systematic
    ~1e-3 K offset in T_closure_gap_K (PR #311 review, blocking item B).
    A species whose flow is below the step uses a second-order forward
    stencil, so a product absent from the feed never needs a negative flow.
    """
    f_tot = math.fsum(f.values())
    step = _H_BAR_REL_STEP * f_tot
    s0 = _stream_enthalpy(thermo, f, t, p, kind)
    out: dict[str, float] = {}
    for cid, n in f.items():
        f_plus = dict(f)
        f_plus[cid] = n + step
        if n - step < 0.0:
            f_pp = dict(f)
            f_pp[cid] = n + 2.0 * step
            out[cid] = (
                -3.0 * s0
                + 4.0 * _stream_enthalpy(thermo, f_plus, t, p, kind)
                - _stream_enthalpy(thermo, f_pp, t, p, kind)
            ) / (2.0 * step)
        else:
            f_minus = dict(f)
            f_minus[cid] = n - step
            out[cid] = (
                _stream_enthalpy(thermo, f_plus, t, p, kind) - _stream_enthalpy(thermo, f_minus, t, p, kind)
            ) / (2.0 * step)
    return out


def _pkg_reaction_enthalpy(reaction: Reaction, h_bar: Mapping[str, float]) -> float:
    """Reaction enthalpy on the outlet-closure basis, J/mol extent (spec eq. 5).

    The closure (``thermal_outlet`` / ``_solve_outlet_T``) balances
    :func:`kinetics.enthalpy_with_formation` — the package mixture enthalpy
    plus the databank ΔfH°298 lift.  The energy ODE must use the same basis:
    ΔrH(T) = ΔrH°298 (databank, ``heat_of_reaction`` at 298.15 K) +
    Σν·h̄_i, each h̄_i a partial molar enthalpy of the actual mixture
    (:func:`_partial_molar_enthalpies`).  Earlier revisions used
    pure-component enthalpies (dropping the mixing term, a systematic
    ~1e-3 K gap) and the databank's own Cp integral (mixing two enthalpy
    bases, a ~4e-2 K gap); see the PR #311 reviews, blocking items 1 and B.
    """
    return float(heat_of_reaction(reaction, T_REF_FORMATION)) + math.fsum(
        float(nu) * h_bar[cid] for cid, nu in reaction.stoichiometry.items()
    )


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
    tube_diameter_m: float | None = None,  # R2 geometry, required with ergun
    length_m: float | None = None,  # R2 geometry, required with ergun
    n_tubes: int = 1,
    viscosity_Pa_s: float | None = None,  # R2 Ergun viscosity override
    ergun: ErgunBed | None = None,  # R2; None = no pressure drop
    rate_multiplier: Callable[[int, float, float, Mapping[str, float]], float] | None = None,
    n_output: int = 51,
) -> PlugFlowProfile:
    """Integrate the kinetic plug-flow equations over ``volume_m3``.

    See the module docstring for the method; the spec
    (``specs/backend/units/pfr.md``) owns the equations and the refusal
    table.  ``rate_multiplier(j, T, P, z)`` returns a*eta_j for reaction j
    (R3); ``None`` means 1.0.  ``ergun`` is the R2 packed bed (spec
    equation 8): the pressure ODE dP/dV integrates the Ergun gradient with
    the cross-section and superficial mass flux per tube, with rho and mu
    from the flash at (z, T, P) — ``viscosity_Pa_s`` overrides mu where the
    package has no correlation.  Without ``ergun`` (and at R1) the tube
    carries no pressure drop: P stays at P_in.
    """
    if volume_m3 <= 0.0:
        raise PlugFlowError("volume_m3 must be > 0")
    if energy == "heat_model" and heat is None:
        raise PlugFlowError("energy='heat_model' requires a heat model")
    if n_output < 2:
        raise PlugFlowError("n_output must be >= 2")
    if reacting_phase not in _PHASE_KIND:
        raise PlugFlowError(f"reacting_phase {reacting_phase!r} is not one of 'vapor' or 'liquid'")
    if ergun is not None:
        if not 0.0 < ergun.voidage < 1.0:
            raise PlugFlowError(f"bed voidage {ergun.voidage!r} is not in (0, 1)")
        if ergun.particle_diameter_m <= 0.0:
            raise PlugFlowError("particle_diameter_m must be > 0")
        if tube_diameter_m is None or tube_diameter_m <= 0.0:
            raise PlugFlowError("tube_diameter_m must be > 0 when an Ergun bed is given")
        if length_m is None or length_m <= 0.0:
            raise PlugFlowError("length_m must be > 0 when an Ergun bed is given")
        if n_tubes < 1:
            raise PlugFlowError("n_tubes must be >= 1")

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

    # R2 Ergun constants (spec equation 8): the cross-section and the
    # superficial mass flux are per tube and constant along it.
    if ergun is not None:
        assert tube_diameter_m is not None
        a_cross = math.pi * tube_diameter_m**2 / 4.0
    else:
        a_cross = 0.0

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
        h_bar = (
            _partial_molar_enthalpies(thermo, f, t, p, _PHASE_KIND[reacting_phase])
            if energy != "isothermal"
            else {}
        )
        for j, reaction in enumerate(reactions):
            assert reaction.kinetics is not None
            r_j = rate(reaction, t, p_eff, z)
            multiplier = 1.0 if rate_multiplier is None else rate_multiplier(j, t, p_eff, z)
            nu_base = float(reaction.stoichiometry[reaction.base_component])
            dxi[j] = scales[j] * multiplier * r_j / abs(nu_base)
            if energy != "isothermal":
                d_h += _pkg_reaction_enthalpy(reaction, h_bar) * dxi[j]

        q = q_v(v, t, extra)
        if energy == "isothermal":
            dt = 0.0
        else:
            dt = (-d_h + q) / (f_tot * cp_molar)
        dq = q if energy != "isothermal" else 0.0
        # R2 Ergun pressure drop per unit volume (spec equation 8): Fogler
        # eq. 4-22 in SI, divided by the tube cross-section.  rho and mu come
        # from the flash-free phase_props; viscosity_Pa_s overrides mu where
        # the package has no correlation.
        if ergun is None:
            dp = 0.0
        else:
            mu = viscosity_Pa_s if viscosity_Pa_s is not None else props.viscosity
            if mu is None:
                raise PlugFlowError(
                    "the Ergun bed needs a viscosity but the package gives none at this state; "
                    "give the param viscosity_Pa_s"
                )
            rho = float(props.density)
            g_flux = (f_tot * float(props.molecular_weight) / 1000.0) / (n_tubes * a_cross)
            phi_b = ergun.voidage
            d_p = ergun.particle_diameter_m
            dp = (
                -(1.0 / a_cross)
                * g_flux
                * (1.0 - phi_b)
                / (rho * d_p * phi_b**3)
                * (150.0 * (1.0 - phi_b) * mu / d_p + 1.75 * g_flux)
            )

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
    # Per output point, per reaction (mol/s); m = 0 gives per-point empty rows.
    extents_rows = tuple(tuple(float(sol.y[j, i]) for j in range(m)) for i in range(len(t_eval)))
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
