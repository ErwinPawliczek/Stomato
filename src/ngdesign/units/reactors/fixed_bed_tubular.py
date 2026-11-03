"""Fixed-bed multi-tubular reactor (spec ``specs/backend/units/fixed_bed_tubular.md``).

The tube side is the pfr R2 model over the total reacting volume
V_tot = n_t*A_c*L; identical tubes share the feed equally.  The shell-side
coolant is the one-dimensional pseudo-homogeneous coolant balance (Froment,
Bischoff & De Wilde, *Chemical Reactor Analysis and Design*, 3rd ed., ch. 11),
constant c_p and described by params: the row has no coolant ports.

    q_V = U*a_w*(T_c - T),  a_w = 4/D_t
    co-current:      dT_c/dV = -q_V/C_c,  T_c(0) = T_c,in
    counter-current: dT_c/dV = +q_V/C_c,  T_c(V_tot) = T_c,in

Counter-current is a two-point boundary-value problem, solved by shooting on
T_c(0) with brentq; each trial is one full integration.  ``duty_W`` is the heat
into the process, Q = integral of q_V over V.  All SI: J, mol, K, Pa, s.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from scipy.optimize import brentq

from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from ngdesign.units._physics.kinetics import apply_extents
from ngdesign.units.reactors._shared import reaction_set_param
from ngdesign.units.reactors.pfr import ergun_bed, outlet_at_pressure, plug_flow_info
from ngdesign.units.reactors.plug_flow import HeatModel, PlugFlowProfile, integrate_plug_flow

#: Bracket widenings of the counter-current shooting (spec algorithm step 3).
_MAX_WIDENINGS = 5


class FixedBedError(ValueError):
    """Raised when the fixed-bed parameters or the coolant shooting fail."""


def coolant_heat_model(
    u_w_m2k: float, tube_diameter_m: float, capacity_w_k: float, *, counter: bool, t_c0: float
) -> HeatModel:
    """The shell-side coolant as one extra ODE state T_c(V) (spec equations 1-2)."""
    a_w = 4.0 / tube_diameter_m
    sign = 1.0 if counter else -1.0

    def q_v(_v: float, t: float, extra: Sequence[float]) -> float:
        return u_w_m2k * a_w * (extra[0] - t)

    def d_extra(_v: float, t: float, extra: Sequence[float]) -> tuple[float, ...]:
        return (sign * q_v(_v, t, extra) / capacity_w_k,)

    return HeatModel(n_extra=1, y0_extra=(t_c0,), q_V=q_v, d_extra=d_extra)


def _positive(params: Mapping[str, Any], key: str, where: str = "") -> float:
    if key not in params:
        raise FixedBedError(f"{where}{key} is required")
    value = float(params[key])
    if value <= 0.0:
        raise FixedBedError(f"{where}{key} must be > 0")
    return value


class FixedBedTubularR2:
    """Multi-tubular packed-bed reactor with a coolant balance, rigour level R2."""

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        rset = reaction_set_param(params["reaction_set"])
        n_tubes = int(params.get("n_tubes", 0))
        if n_tubes < 1:
            raise FixedBedError("n_tubes must be >= 1")
        diameter = _positive(params, "tube_diameter_m")
        length = _positive(params, "length_m")
        u = _positive(params, "U_W_m2K")
        coolant = params.get("coolant")
        if not isinstance(coolant, Mapping):
            raise FixedBedError("coolant takes {mass_flow_kg_s, cp_J_kgK, T_in_K, flow}")
        capacity = _positive(coolant, "mass_flow_kg_s", "coolant.") * _positive(
            coolant, "cp_J_kgK", "coolant."
        )
        t_c_in = _positive(coolant, "T_in_K", "coolant.")
        flow = coolant.get("flow")
        if flow not in ("co", "counter"):
            raise FixedBedError(f"coolant.flow {flow!r} is not 'co' or 'counter'")
        counter = flow == "counter"
        volume = n_tubes * math.pi * diameter**2 / 4.0 * length
        bed = ergun_bed(params, diameter, n_tubes)
        bulk = params.get("bulk_density_kg_m3")

        def run(t_c0: float) -> PlugFlowProfile:
            return integrate_plug_flow(
                inlet,
                rset,
                thermo,
                volume_m3=volume,
                energy="heat_model",
                heat=coolant_heat_model(u, diameter, capacity, counter=counter, t_c0=t_c0),
                reacting_phase=params.get("reacting_phase", "vapor"),
                bulk_density_kg_m3=None if bulk is None else float(bulk),
                ergun=bed,
            )

        info: dict[str, float] = {}
        if counter:
            t_c0, iterations = self._shoot(run, t_c_in, float(inlet.T))
            info["shooting_iterations"] = float(iterations)
            coolant_out = t_c0
        else:
            t_c0 = t_c_in
        profile = run(t_c0)
        if not counter:
            coolant_out = profile.extra[-1][0]

        xi_end = list(profile.extents[-1])
        n_out = apply_extents(inlet.component_flows(), rset, xi_end)
        outlet = outlet_at_pressure(inlet, n_out, profile.P_Pa[-1], profile.Q_W, thermo)
        info.update(plug_flow_info(rset, xi_end, profile, outlet, float(inlet.P)))
        info["coolant_T_out_K"] = float(coolant_out)
        info["coolant_duty_W"] = -profile.Q_W
        return UnitResult(outlets={"outlet": outlet}, duty_W=profile.Q_W, info=info)

    @staticmethod
    def _shoot(run: Any, t_c_in: float, t_in: float) -> tuple[float, int]:
        """T_c(0) with T_c(V_tot) = T_c,in; returns the root and the trial count."""
        trials = 0

        def residual(s: float) -> float:
            nonlocal trials
            trials += 1
            return float(run(s).extra[-1][0]) - t_c_in

        delta = abs(t_in - t_c_in) + 50.0
        lo, hi = t_c_in - delta, t_c_in + delta
        for _ in range(_MAX_WIDENINGS + 1):
            lo, hi = max(1.0, t_c_in - delta), t_c_in + delta
            if residual(lo) * residual(hi) <= 0.0:
                break
            delta *= 2.0
        else:
            raise FixedBedError("counter-current shooting could not bracket the coolant outlet temperature")
        try:
            root = float(brentq(residual, lo, hi, xtol=1.0e-9, maxiter=100))
        except (RuntimeError, ValueError) as exc:
            raise FixedBedError(f"counter-current shooting failed: {exc}") from exc
        return root, trials

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Ethylene hydrogenation in a nitrogen carrier, counter-current coolant.

        The kinetics, geometry and coolant are illustrative test inputs, not
        published data and not package defaults: the case exists to exercise
        an exothermic hot spot under the V0 balances.
        """
        feed = {
            "T": 500.0,
            "P": 5.0e5,
            "molar_flow": 1.0,
            "composition": {"C2H4": 0.04, "H2": 0.08, "N2": 0.88},
        }
        params = {
            "reaction_set": {
                "id": "ethylene_hydrogenation_illustrative",
                "components": ["C2H4", "H2", "C2H6", "N2"],
                "reactions": [
                    {
                        "id": "hydrogenation",
                        "stoichiometry": {"C2H4": -1.0, "H2": -1.0, "C2H6": 1.0},
                        "base_component": "C2H4",
                        "provenance": "illustrative test kinetics, not a published rate",
                        "kinetics": {
                            "rate_units": "mol/(m3·s)",
                            "k0": 5.0e7,
                            "Ea": 9.0e4,
                            "orders": {"C2H4": 1.0},
                            "basis": "concentration",
                        },
                    }
                ],
            },
            "n_tubes": 200,
            "tube_diameter_m": 0.025,
            "length_m": 3.0,
            "U_W_m2K": 5.0,
            "coolant": {"mass_flow_kg_s": 2.0, "cp_J_kgK": 2000.0, "T_in_K": 490.0, "flow": "counter"},
            "bed": {"particle_diameter_m": 0.004, "voidage": 0.4},
            "viscosity_Pa_s": 2.5e-5,
        }
        return {"inlet": feed}, params
