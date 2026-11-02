"""Isobaric batch reactor, one full cycle (catalogue row ``batch_reactor``).

The catalogue is steady state, so the unit reports one batch cycle, not a
dynamic mode.  The inlet stream is the cycle-averaged charge rate F (mol/s):
one batch charges N0 = F*t_cycle, reacts for ``batch_time_s`` and is discharged
whole, and the outlet is the discharge averaged over t_cycle = batch_time_s +
``turnaround_s``.  Over a closed cycle the vessel holds nothing at either end,
so the stream balance H_in + Q = H_out is exact and V0 applies unchanged.

Batch mole balance (Levenspiel, *Chemical Reaction Engineering*, 3rd ed., ch. 3;
Fogler, *Elements of CRE*, ch. 1), per reaction on the extent per mole charged:

    d(xi_j)/dt = s_j*r_j(T, P_eff, z)*v(t)/|nu_base,j|

with r_j from :func:`ngdesign.units._physics.kinetics.rate` and s_j the pfr
rate-basis scale.  The volume v per mole charged and the concentration basis
follow the pfr spec's equation 4, so the two units read the same rate law the
same way: vapour v = N*R*T/P with P_eff = P (the contract's c_i = y_i*P/(R*T));
liquid v = N*MW/(1000*rho) with P_eff = c_tot*R*T.  Either way c_i*v = N_i, so
first-order kinetics give N_A = N_A0*exp(-k*t) exactly.

Energy, at constant pressure: dT/dt = (-Sum_j dH_j*d(xi_j)/dt + q)/(N*c_p) with
the closure-consistent dH_j of the pfr integrator.  As there, the discharge
temperature comes from the exact formation-basis closure, and the ODE's end
temperature is reported as ``T_closure_gap_K``.

Scope: an isobaric vessel (blanketed or vented) in one phase.  A constant-volume
gas batch (pressure rise, dU = Q), semi-batch feeding and a two-phase vessel are
not modelled and are refused or absent, never approximated.  All SI.
"""

from __future__ import annotations

import math
from typing import Any, Literal

import numpy as np
from scipy.integrate import solve_ivp

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import R, apply_extents, rate
from ngdesign.units.reactors._shared import reaction_set_param, thermal_outlet, z_from
from ngdesign.units.reactors.plug_flow import (
    _PHASE_KIND,
    RHS_CAP,
    _flows,
    _partial_molar_enthalpies,
    _pkg_reaction_enthalpy,
    _validate_reactions,
    audit_single_phase,
)

#: Output points of the phase audit along the batch.
_N_OUTPUT = 51


class BatchReactorError(ValueError):
    """Raised when a batch cycle is ill-posed or fails."""


class BatchReactor:
    """One isothermal, adiabatic or fixed-duty isobaric batch cycle."""

    inlet_ports = ("charge_in",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["charge_in"]
        rset = reaction_set_param(params["reaction_set"])
        if "batch_time_s" not in params:
            raise BatchReactorError("batch_time_s is required")
        t_batch = float(params["batch_time_s"])
        if t_batch <= 0.0:
            raise BatchReactorError("batch_time_s must be > 0")
        turnaround = float(params.get("turnaround_s", 0.0))
        if turnaround < 0.0:
            raise BatchReactorError("turnaround_s must be >= 0")
        phase: Literal["vapor", "liquid"] = params.get("reacting_phase", "vapor")
        if phase not in _PHASE_KIND:
            raise BatchReactorError(f"reacting_phase {phase!r} is not one of 'vapor' or 'liquid'")
        thermal = params.get("thermal", "isothermal")
        duty_batch_w = 0.0
        if isinstance(thermal, dict) and set(thermal) == {"duty_W"}:
            duty_batch_w = float(thermal["duty_W"])
            energy = "duty"
        elif thermal in ("isothermal", "adiabatic"):
            energy = thermal
        else:
            raise BatchReactorError(
                f"thermal mode {thermal!r} is not one of 'isothermal', 'adiabatic' or {{\"duty_W\": W}}"
            )
        bulk = params.get("bulk_density_kg_m3")
        scales = _validate_reactions(rset, None if bulk is None else float(bulk))
        reactions = rset.reactions
        m = len(reactions)

        t_cycle = t_batch + turnaround
        n_charge = float(inlet.molar_flow) * t_cycle
        if n_charge <= 0.0:
            raise BatchReactorError("the charge has no moles")
        pressure = float(inlet.P)
        kind = _PHASE_KIND[phase]
        # Everything per mole charged: the trajectory is independent of batch size.
        f0 = {cid: float(y) for cid, y in inlet.composition.items()}
        q_per_mol = duty_batch_w / n_charge
        n_rhs = 0

        def rhs(_t: float, y: np.ndarray) -> np.ndarray:
            nonlocal n_rhs
            n_rhs += 1
            if n_rhs > RHS_CAP:
                raise BatchReactorError("RHS evaluation cap")
            temperature = float(y[m])
            f = _flows(rset, f0, y[:m].tolist())
            negative = sorted(cid for cid, n in f.items() if n < 0.0)
            if negative:
                raise BatchReactorError(f"reaction set {rset.id!r} depletes component {negative[0]!r}")
            total = math.fsum(f.values())
            z = z_from(f)
            z_rate = {cid: n / total for cid, n in f.items()}
            props = thermo.phase_props(z, temperature, pressure, kind)
            if phase == "vapor":
                p_eff = pressure
                v_per_mol = R * temperature / pressure
            else:
                c_tot = 1000.0 * float(props.density) / float(props.molecular_weight)
                p_eff = c_tot * R * temperature
                v_per_mol = 1.0 / c_tot
            volume = total * v_per_mol
            dxi = np.array(
                [
                    scales[j]
                    * rate(reaction, temperature, p_eff, z_rate)
                    * volume
                    / abs(float(reaction.stoichiometry[reaction.base_component]))
                    for j, reaction in enumerate(reactions)
                ]
            ).reshape(m)
            out = np.zeros(m + 1)
            out[:m] = dxi
            if energy != "isothermal":
                h_bar = _partial_molar_enthalpies(thermo, f, temperature, pressure, kind)
                d_h = math.fsum(
                    _pkg_reaction_enthalpy(reaction, h_bar) * dxi[j] for j, reaction in enumerate(reactions)
                )
                out[m] = (-d_h + q_per_mol) / (total * float(props.cp))
            return out

        y0 = np.zeros(m + 1)
        y0[m] = float(inlet.T)
        atol = np.full(m + 1, 1.0e-12)
        atol[m] = 1.0e-8
        t_eval = np.linspace(0.0, t_batch, _N_OUTPUT)
        try:
            sol = solve_ivp(rhs, (0.0, t_batch), y0, method="BDF", rtol=1.0e-8, atol=atol, t_eval=t_eval)
        except BatchReactorError:
            raise
        except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
            raise BatchReactorError(f"integration failed: {exc}") from exc
        if not bool(sol.success):
            raise BatchReactorError(f"integration failed: {sol.message}")

        for i, time in enumerate(t_eval):
            audit_single_phase(
                thermo,
                _flows(rset, f0, sol.y[:m, i].tolist()),
                float(sol.y[m, i]),
                pressure,
                phase,
                f"the batch at t = {time:g} s",
            )

        # Cycle-averaged extents (mol/s): the discharge over the cycle.
        xi_per_mol = [float(x) for x in sol.y[:m, -1]]
        xi_avg = [x * float(inlet.molar_flow) for x in xi_per_mol]
        n_out = apply_extents(inlet.component_flows(), rset, xi_avg)
        closure: Any = thermal
        if energy == "duty":
            closure = {"duty_W": duty_batch_w * t_batch / t_cycle}
        outlet, duty_avg = thermal_outlet(inlet, n_out, closure, thermo)

        t_profile = [float(t) for t in sol.y[m]]
        info: dict[str, float] = {}
        for reaction, xi in zip(reactions, xi_per_mol, strict=True):
            info[f"extent_{reaction.id}_mol"] = xi * n_charge
            base = reaction.base_component
            base0 = f0.get(base, 0.0)
            if base0 > 0.0:
                nu = abs(float(reaction.stoichiometry[base]))
                info[f"conversion_{base}_{reaction.id}"] = xi * nu / base0
        info["charge_mol"] = n_charge
        info["cycle_time_s"] = t_cycle
        info["batch_duty_J"] = duty_avg * t_cycle
        info["T_profile_out_K"] = t_profile[-1]
        info["T_closure_gap_K"] = float(outlet.T) - t_profile[-1]
        info["T_max_K"] = max(t_profile)
        info["n_rhs"] = float(n_rhs)
        return UnitResult(outlets={"outlet": outlet}, duty_W=duty_avg, info=info)

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Isothermal first-order nC4 -> iC4 for 96 s after a 24 s turnaround.

        k(500 K) = 1e3*exp(-5e4/(R*500)) = 5.979e-3 1/s, so X = 1 - exp(-k*96) =
        0.4369 by hand.  Illustrative test kinetics, the pfr R1 example's, not
        package defaults.
        """
        feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
        params = {
            "reaction_set": {
                "id": "nc4_isom",
                "components": ["nC4", "iC4"],
                "reactions": [
                    {
                        "id": "isom",
                        "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                        "base_component": "nC4",
                        "provenance": "illustrative first-order test kinetics (pfr R1 example)",
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
            "batch_time_s": 96.0,
            "turnaround_s": 24.0,
            "thermal": "isothermal",
        }
        return {"charge_in": feed}, params
