"""Membrane R2: multicomponent solution-diffusion, counter-current module.

Plugin kind "unit", name "membrane" level R2 — registered from the catalogue
YAML; no decorator (round-1 conventions). Built on R1: this module imports the
cross-flow local-flux solver (`_local_y`) and validation (`_validate_pure`,
`MembraneR1SpecError`) from `membrane_r1` (spec `specs/backend/units/membrane.md`).

Method (M4, Pan, AIChE J. 29(4):545 (1983), counter-current hollow fibre): the
permeate side is a plug flow moving toward the feed end a = 0, where it is
collected as the permeate product.

- Feed side: ``dn_i/da = −J_i``; permeate side: ``dp_i/da = −J_i`` with
  ``p_i(A) = 0`` — permeate created downstream flows back toward a = 0.
- Local permeate-side bulk composition ``y_i = p_i/Σp``; at the residue end,
  where Σp = 0, y is the cross-flow limit (M2). The switch happens whenever
  ``Σp ≤ 1e-12 F``.
- Boundary-value problem: unknowns ``r_i = n_i(A)`` (the residue flows, N
  unknowns). Integrate from a = A to a = 0 and require ``n_i(0) = F z_i`` —
  N equations. Solved by shooting with `scipy.optimize.root` (hybr).
- With ``P_l = 0`` the permeate side has no effect and R2 equals R1 at the
  same area (spec identity R2 -> R1, relative 1e-8).

Isothermal outlets exactly as in R1: `split_by_component`, permeate at
``P_permeate``, residue at the feed pressure, both at the feed T. ``duty_W``
closes the energy balance; ``power_W = 0``.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, root

from ngdesign.units.separation.membrane_r1 import (
    MembraneR1SpecError,
    _INTEGRATION_RTOL,
    _local_y,
    _validate_pure,
    cross_flow,
)

_P_SWITCH = 1e-12  # cross-flow switch: Σp ≤ _P_SWITCH · F


def counter_current(
    F: float,
    z: Mapping[str, float],
    Pi: Mapping[str, float],
    P_h: float,
    P_l: float,
    area: float | None = None,
    stage_cut: float | None = None,
) -> tuple[dict[str, float], dict[str, float], float, float, int]:
    """Counter-current membrane (R2, M4): shooting on the residue flows.

    Returns ``(residue_flows, permeate_flows, area, stage_cut, nfev)``. In
    rating mode (``area`` given) the stage cut is computed; in design mode
    (``stage_cut`` given) the area is found by brentq on ``θ_R2(A) − θ`` over
    ``[0, A_R1(θ)]`` (bracket doubled up to 10 times when
    ``θ_R2(A_R1) < θ``, then refusal `not achievable`). Tolerances: DOP853,
    ``rtol=1e-11``, ``atol=1e-13 F``; `root` hybr, ``tol=1e-12``,
    ``maxfev=200``; brentq ``xtol=1e-12 A``, ``maxiter=100``.

    Refusal `counter-current shooting did not converge` when the shooting
    fails or ``max|residual| > 1e-9 F``.
    """
    area_f, stage_cut_f = _validate_pure(F, z, Pi, P_h, P_l, area, stage_cut)
    order = list(z)
    N = len(order)
    zv = np.array([float(z[c]) for c in order])
    piv = np.array([float(Pi[c]) for c in order])
    Fz = float(F) * zv
    F_f = float(F)
    P_hf = float(P_h)
    P_lf = float(P_l)

    def integrate_to_feed_end(A: float, r: np.ndarray) -> np.ndarray:
        """Integrate M4 from a = A (n = r, p = 0) down to a = 0; return the state."""

        def rhs(a: float, state: np.ndarray) -> np.ndarray:
            n = state[:N]
            p = state[N:]
            x = n / float(np.sum(n))
            if float(np.sum(p)) <= _P_SWITCH * F_f:
                y, _ = _local_y(x, piv, P_hf, P_lf)
            else:
                y = p / float(np.sum(p))
            flux = piv * (P_hf * x - P_lf * y)
            return np.concatenate((-flux, -flux))

        sol = solve_ivp(
            rhs,
            (A, 0.0),
            np.concatenate((r, np.zeros(N))),
            method="DOP853",
            rtol=_INTEGRATION_RTOL,
            atol=1e-13 * F_f,
        )
        if not sol.success:
            raise MembraneR1SpecError("counter-current shooting did not converge")
        return sol.y[:, -1]

    def solve_at(A: float) -> tuple[dict[str, float], dict[str, float], float, float, int]:
        """Shooting at a fixed area; returns outlets, theta and nfev."""
        if A <= 0.0:
            zero: dict[str, float] = {c: 0.0 for c in order}
            full: dict[str, float] = {c: Fz[i] for i, c in enumerate(order)}
            return full, zero, 0.0, 0.0, 0
        r1_res = cross_flow(F=F_f, z=z, Pi=Pi, P_h=P_hf, P_l=P_lf, area=A)[0]
        r0 = np.array([r1_res[c] for c in order])

        def residual(r_flat: np.ndarray) -> np.ndarray:
            end = integrate_to_feed_end(A, r_flat)
            return end[:N] - Fz

        shoot = root(residual, r0, method="hybr", tol=1e-12, options={"maxfev": 200})
        if not shoot.success or float(np.max(np.abs(shoot.fun))) > 1e-9 * F_f:
            raise MembraneR1SpecError("counter-current shooting did not converge")
        end = integrate_to_feed_end(A, shoot.x)
        n_end, p_end = end[:N], end[N:]
        residue = {c: float(v) for c, v in zip(order, n_end, strict=True)}
        permeate = {c: float(v) for c, v in zip(order, p_end, strict=True)}
        theta = float(np.sum(p_end)) / F_f
        return residue, permeate, float(A), theta, int(shoot.nfev)

    if area_f is not None:
        return solve_at(area_f)

    assert stage_cut_f is not None
    target = stage_cut_f
    # Initial bracket: [0, A_R1(θ)] — R2 recovers at least as much as R1 at
    # the same area, so θ_R2(A_R1(θ)) ≥ θ up to integration tolerance.
    hi = cross_flow(F=F_f, z=z, Pi=Pi, P_h=P_hf, P_l=P_lf, stage_cut=target)[2]

    def theta_error(A: float) -> float:
        return solve_at(A)[3] - target

    for _ in range(10):
        if theta_error(hi) >= 0.0:
            break
        hi *= 2.0
    else:
        raise MembraneR1SpecError(
            f"stage cut {target} not achievable: not reached with the bracket doubled 10 times"
        )
    A = brentq(theta_error, 0.0, hi, xtol=1e-12 * hi, maxiter=100)
    return solve_at(A)
