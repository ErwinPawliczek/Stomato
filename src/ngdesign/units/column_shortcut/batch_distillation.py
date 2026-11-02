"""Differential (Rayleigh) batch distillation, level R3 (unit ``batch_distillation``).

Plugin kind "unit", name "batch_distillation". Ports ``charge`` ->
``distillate`` + ``residue``. Batch time is not modelled: the integration
variable is the fraction boiled off, so the result is the cumulative
distillate and the residue at the stop condition, not a time profile.

Method: one equilibrium pot, no column and no reflux. The vapour leaving is in
equilibrium with the pot liquid and is removed as it forms (Rayleigh, Phil.
Mag. 4 (1902) 521; Seader, Henley & Roper 3rd ed., Sect. 13.1). The component
balance d(n x_i) = y_i dn, with s = ln(n_0/n), is the residue-curve equation
(Doherty & Perkins, Chem. Eng. Sci. 33 (1978) 281):

    dx_i/ds = x_i - y_i(x, P)

where y_i and the pot temperature come from ``thermo.bubble_point(x, P=P)``,
the package's own saturation surface. The pot energy balance adds

    dE_V/ds = n h_V(y, T, P),   n = n_0 exp(-s)

the cumulative enthalpy of the vapour taken overhead. Then, with the charge at
its actual inlet enthalpy,

    Q_pot = n h_L(x_end) + E_V - n_0 h_charge
    Q_cond = E_V - n_D h_D

and ``duty_W = Q_pot - Q_cond`` closes the stream table exactly. The distillate
is the pooled condensate, reported as saturated liquid at P.

**Basis.** The ``charge.molar_flow`` is read as a campaign average, mol/s of
charge, so the outlets and duties are cycle averages per the same second and
the unit composes with a steady flowsheet. The level is R3 on the row's ladder
because it is the batch (dynamic) axis of the plan; it carries no holdup
hydraulics and no rectification stages.

Refusals (typed :class:`BatchDistillationError`, a ValueError): a missing or
zero-flow charge; ``fraction_distilled`` outside (0, 1); a non-positive
``P``; any parameter outside the schema.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind

_ALLOWED_KEYS = frozenset({"fraction_distilled", "P"})
#: Integrator tolerances on the mole fractions (Dormand-Prince RK45).
_RTOL = 1e-7
_ATOL = 1e-9
#: Pot compositions below this are held at this floor for the bubble-point
#: call only: the saturation surface validates x, and a depleted light key must
#: not fail the integration.
_X_FLOOR = 1e-12


class BatchDistillationError(ValueError):
    """Refusal: the batch-distillation spec is invalid."""


def _normalised(x: NDArray[np.float64], cids: list[str]) -> dict[str, float]:
    """Mole-fraction dict from an integrator state (clipped, renormalised)."""
    clipped = np.maximum(x, _X_FLOOR)
    total = float(clipped.sum())
    return {cid: float(v) / total for cid, v in zip(cids, clipped, strict=True)}


class BatchDistillation:
    """Rayleigh differential distillation: one pot, cumulative products."""

    inlet_ports = ("charge",)
    outlet_ports = ("distillate", "residue")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        charge = inlets.get("charge")
        if charge is None:
            raise BatchDistillationError("batch_distillation requires the charge inlet stream")
        if charge.molar_flow <= 0.0:
            raise BatchDistillationError(f"zero-flow charge refused (got {charge.molar_flow})")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise BatchDistillationError(f"batch_distillation refuses unknown parameter {key!r}")
        frac = params.get("fraction_distilled")
        if not isinstance(frac, (int, float)) or isinstance(frac, bool) or not 0.0 < float(frac) < 1.0:
            raise BatchDistillationError(f"fraction_distilled must be in (0, 1), got {frac!r}")
        pressure = float(params.get("P", charge.P))
        if not math.isfinite(pressure) or pressure <= 0.0:
            raise BatchDistillationError(f"P must be positive, got {pressure!r}")

        cids = sorted(charge.composition)
        n0 = charge.molar_flow
        s_end = -math.log(1.0 - float(frac))

        def rhs(s: float, state: NDArray[np.float64]) -> NDArray[np.float64]:
            comp = _normalised(state[:-1], cids)
            sat = thermo.bubble_point(comp, P=pressure)
            y = sat.incipient_composition
            h_v = thermo.phase_props(y, sat.T, pressure, PhaseKind.VAPOR).enthalpy
            dx = [comp[cid] - y.get(cid, 0.0) for cid in cids]
            return np.array([*dx, n0 * math.exp(-s) * h_v], dtype=float)

        start = np.array([*(charge.composition[cid] for cid in cids), 0.0], dtype=float)
        # The enthalpy integral is a quadrature on the same stepper; its
        # scale is the charge enthalpy flow, so it does not set the step.
        h_scale = max(abs(charge.enthalpy) * n0, n0 * 1e4)
        atol = np.array([_ATOL] * len(cids) + [_RTOL * h_scale])
        sol = solve_ivp(rhs, (0.0, s_end), start, method="RK45", rtol=_RTOL, atol=atol)
        if not sol.success:
            raise BatchDistillationError(f"Rayleigh integration failed: {sol.message}")

        x_end = _normalised(sol.y[:-1, -1], cids)
        e_vapour = float(sol.y[-1, -1])
        n_res = n0 * math.exp(-s_end)
        n_dist = n0 - n_res
        moles = {cid: n0 * charge.composition[cid] - n_res * x_end[cid] for cid in cids}
        z_dist = {cid: max(n, 0.0) / n_dist for cid, n in moles.items()}
        total = sum(z_dist.values())
        z_dist = {cid: v / total for cid, v in z_dist.items()}

        residue = thermo.flash_pvf(x_end, pressure, 0.0, n_res)
        distillate = thermo.flash_pvf(z_dist, pressure, 0.0, n_dist)

        h_in = charge.enthalpy * n0
        q_pot = residue.enthalpy * n_res + e_vapour - h_in
        q_cond = e_vapour - distillate.enthalpy * n_dist
        info: dict[str, float] = {
            "fraction_distilled": float(frac),
            "pot_T_start_K": float(thermo.bubble_point(dict(charge.composition), P=pressure).T),
            "pot_T_end_K": residue.T,
            "pot_duty_W": q_pot,
            "condenser_duty_W": q_cond,
            "ivp_steps": float(sol.t.size - 1),
        }
        for cid in cids:
            info[f"recovery_{cid}"] = moles[cid] / (n0 * charge.composition[cid])
        return UnitResult(
            outlets={"distillate": distillate, "residue": residue},
            duty_W=q_pot - q_cond,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Propane/n-butane/n-pentane charge at 1 MPa, half boiled off (illustrative feed)."""
        charge = {
            "T": 330.0,
            "P": 1.0e6,
            "molar_flow": 10.0,
            "composition": {"C3": 0.3, "nC4": 0.4, "nC5": 0.3},
        }
        return {"charge": charge}, {"fraction_distilled": 0.5}
