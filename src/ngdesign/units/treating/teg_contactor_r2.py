"""Stage-wise TEG absorber, rating at N stages (spec teg_contactor R2).

Plugin kind "unit", name "teg_contactor", catalogue level R2. Ports are the
R0 contactor's (``gas_in``, ``lean_teg_in`` -> ``gas_out``, ``rich_teg_out``);
the R0 module is not edited and is imported read-only. Registration comes
from ``data/unit_models/treating.yaml`` (``units.catalogue.register_all``); the
class carries no ``@register`` decorator.

Method: counter-current equilibrium stages ``j = 1..N`` numbered top to bottom,
isothermal at ``T = gas_in.T`` and ``P = gas_in.P`` (the R0 convention: GPSA
contactor practice treats the column as at the gas temperature). Water is the
only transferring species; hydrocarbon co-absorption and TEG losses are
neglected, as in R0.

Mole ratios on the solute-free bases: gas ``Y = n_w/G`` with the dry gas
``G = (1 - y_in) * F_gas``; liquid ``X = n_w/S`` with the TEG ``S = n_TEG`` of
the lean.

- Stage balance: ``G * (Y_{j+1} - Y_j) = S * (X_j - X_{j-1})``, with
  ``X_0 = X_lean`` and ``Y_{N+1} = Y_in``.
- Stage equilibrium: ``y_j = m(T, P, x_j) * x_j`` with ``y = Y/(1 + Y)`` and
  ``x = X/(1 + X)``; ``m`` is the Parrish-Won-Baltatu activity slope
  (Parrish, Won & Baltatu, Proc. 65th GPA Convention, 1986, as parameterized in
  Filep, Todinca & Dumitrel, Chem. Biochem. Eng. Q. 36(1) 25-38, 2022, eqs.
  12-17), taken read-only from the one owner, ``ngdesign.units.teg_activity``.

The stage system is solved by ``teg_stagewise.countercurrent_march`` (owned
here; shared with the R2 regenerator level). ``y*(x) = m(x) * x`` is strictly
increasing on (0, 1) over the fitted range (asserted on a grid in the tests),
so the stage equilibrium inverse ``x_of_y`` exists and bisection on ``x``
converges.

Unlike R0 (spec-driven: outlet water given), R2 is a rating: the stage count
``n_stages`` is given and the outlet water content follows. There is no exact
reduction to R0 — R0's stage count is a lean-end-slope Kremser indication,
while R2 marches the curved activity line; the tests relate them instead.

Duty is the enthalpy difference across the unit on the actual inlet states
(the R0 convention): heat of absorption and temperature equalisation are
reported through it, not modelled separately.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.teg_activity import activity_equilibrium_slope
from ngdesign.units.teg_contactor import _water_content_lb_per_mmscf
from ngdesign.units.treating.teg_stagewise import TEGStageError, countercurrent_march

__all__ = ["TEGContactorR2", "TEGContactorR2Error"]


class TEGContactorR2Error(ValueError):
    """A contactor feed or parameter set the R2 rating refuses."""


#: The Parrish-Won-Baltatu activity correlation's fitted temperature range, K
#: (the owner correlation's fit range, as the R0 regen flags it).
_PARRISH_T_MIN, _PARRISH_T_MAX = 300.0, 380.0

#: Pure-water mole-fraction ceiling for the liquid-phase inverse.
_X_WATER_MAX = 1.0 - 1.0e-12

#: Stage-equilibrium inverse bisection: iteration cap and interval stop.
_X_BISECTION_ITERATIONS = 200
_X_BISECTION_TOL = 1.0e-15


def _ratio_to_fraction(r: float) -> float:
    """Mole ratio [mol solute / mol carrier] -> wet mole fraction."""
    return r / (1.0 + r)


def _fraction_to_ratio(y: float) -> float:
    """Wet mole fraction -> mole ratio [mol solute / mol carrier]."""
    return y / (1.0 - y)


def _shift_water(state: StreamState, water_delta: float) -> tuple[dict[str, float], float]:
    """Return (composition, molar_flow) with ``water_delta`` added to the H2O flow.

    All other component flows are held fixed, so the component balances of
    the unit close exactly.
    """
    flows = {c: f * state.molar_flow for c, f in state.composition.items()}
    flows["H2O"] = flows.get("H2O", 0.0) + water_delta
    total = sum(flows.values())
    if total <= 0.0:
        raise ValueError("stream collapsed to zero molar flow")
    return {c: n / total for c, n in flows.items()}, total


def _n_stages_param(params: dict[str, Any]) -> int:
    """Validate the ``n_stages`` parameter: present, a true integer, >= 1."""
    extra = sorted(set(params) - {"n_stages"})
    if extra:
        raise TEGContactorR2Error(f"unknown parameter key(s): {', '.join(extra)}")
    if "n_stages" not in params:
        raise TEGContactorR2Error("n_stages is required (equilibrium stages >= 1)")
    n_stages = params["n_stages"]
    if isinstance(n_stages, bool) or not isinstance(n_stages, int):
        raise TEGContactorR2Error(f"n_stages must be an integer, got {n_stages!r}")
    if n_stages < 1:
        raise TEGContactorR2Error(f"n_stages must be >= 1, got {n_stages}")
    return int(n_stages)


class TEGContactorR2:
    """Countercurrent TEG absorber rated at N isothermal equilibrium stages."""

    inlet_ports: tuple[str, ...] = ("gas_in", "lean_teg_in")
    outlet_ports: tuple[str, ...] = ("gas_out", "rich_teg_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        n_stages = _n_stages_param(params)

        gas_in = inlets["gas_in"]
        lean_in = inlets["lean_teg_in"]

        y_in = gas_in.composition.get("H2O", 0.0)
        if not y_in > 0.0:
            raise TEGContactorR2Error(f"gas_in must carry H2O > 0, got mole fraction {y_in}")
        x_water_lean = lean_in.composition.get("H2O", 0.0)
        x_teg_lean = lean_in.composition.get("TEG", 0.0)
        if not x_teg_lean > 0.0:
            raise TEGContactorR2Error(f"lean_teg_in must carry TEG > 0, got mole fraction {x_teg_lean}")
        if not x_water_lean < 1.0:
            raise TEGContactorR2Error(
                f"lean_teg_in must carry TEG > 0, got water mole fraction {x_water_lean}"
            )

        T = gas_in.T
        P = gas_in.P

        # Solute-free bases and inlet ratios.
        G = gas_in.molar_flow * (1.0 - y_in)
        S = lean_in.molar_flow * x_teg_lean
        Y_in = _fraction_to_ratio(y_in)
        X_lean = _fraction_to_ratio(x_water_lean)

        def x_of_y(y_ratio: float) -> float:
            """Stage-equilibrium inverse ``X(Y)`` on the activity line.

            Bisects ``x`` on [0, 1 - 1e-12] for ``m(T, P, x) * x = y`` with
            ``y = Y/(1 + Y)``, then converts ``x -> X``. Beyond the pure-water
            limit (``y >= 1``) returns +inf for the shooter.
            """
            if not math.isfinite(y_ratio) or y_ratio <= 0.0:
                return math.inf
            y = _ratio_to_fraction(y_ratio)
            if y >= 1.0:
                return math.inf
            lo, hi = 0.0, _X_WATER_MAX
            for _ in range(_X_BISECTION_ITERATIONS):
                mid = 0.5 * (lo + hi)
                if activity_equilibrium_slope(T, P, mid) * mid < y:
                    lo = mid
                else:
                    hi = mid
            if hi - lo >= _X_BISECTION_TOL:
                raise TEGStageError(
                    f"stage equilibrium inverse did not converge to "
                    f"|delta x| < {_X_BISECTION_TOL:g} in "
                    f"{_X_BISECTION_ITERATIONS} iterations"
                )
            return _fraction_to_ratio(0.5 * (lo + hi))

        y_profile, x_profile = countercurrent_march(G, S, X_lean, Y_in, n_stages, x_of_y)

        water_removed = G * (Y_in - y_profile[0])
        # Negative water_removed is desorption (lean wetter than the gas
        # equilibrium): physical, allowed and reported as-is.

        gas_comp, gas_flow = _shift_water(gas_in, -water_removed)
        gas_out = thermo.flash_pt(gas_comp, T, P, gas_flow)

        rich_comp, rich_flow = _shift_water(lean_in, water_removed)
        rich_teg_out = thermo.flash_pt(rich_comp, T, P, rich_flow)

        duty_W = (
            gas_out.enthalpy * gas_out.molar_flow
            + rich_teg_out.enthalpy * rich_teg_out.molar_flow
            - gas_in.enthalpy * gas_in.molar_flow
            - lean_in.enthalpy * lean_in.molar_flow
        )

        return UnitResult(
            outlets={"gas_out": gas_out, "rich_teg_out": rich_teg_out},
            duty_W=duty_W,
            info=self._info(
                n_stages=n_stages,
                T=T,
                P=P,
                y_profile=y_profile,
                x_profile=x_profile,
                water_removed=water_removed,
                x_water_lean=x_water_lean,
            ),
        )

    def _info(
        self,
        n_stages: int,
        T: float,
        P: float,
        y_profile: list[float],
        x_profile: list[float],
        water_removed: float,
        x_water_lean: float,
    ) -> dict[str, float]:
        """Reported scalars: outlet water, removal, floor, per-stage profiles."""
        y_1 = _ratio_to_fraction(y_profile[0])
        rich_x_water = _ratio_to_fraction(x_profile[-1])
        lean_floor_y = activity_equilibrium_slope(T, P, x_water_lean) * x_water_lean

        info: dict[str, float] = {
            "n_stages": float(n_stages),
            "outlet_water_lb_per_mmscf": _water_content_lb_per_mmscf(y_1),
            "water_removed_mol_s": water_removed,
            "equilibrium_floor_lb_per_mmscf": _water_content_lb_per_mmscf(lean_floor_y),
            "rich_x_water": rich_x_water,
            "activity_extrapolated": (0.0 if _PARRISH_T_MIN <= T <= _PARRISH_T_MAX else 1.0),
        }
        for j in range(1, n_stages + 1):
            info[f"stage_{j}_y_H2O"] = _ratio_to_fraction(y_profile[j - 1])
            info[f"stage_{j}_x_H2O"] = _ratio_to_fraction(x_profile[j - 1])
        return info

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's feeds (sweet gas at 30 C / 7.1 MPa, 99.8 wt% lean TEG) rated at 3 stages."""
        feeds: dict[str, dict[str, Any]] = {
            "gas_in": {
                "T": 303.15,
                "P": 7.1e6,
                "molar_flow": 100.0,
                "composition": {
                    "C1": 0.90,
                    "C2": 0.05,
                    "C3": 0.03,
                    "CO2": 0.0095,
                    "N2": 0.0100,
                    "H2O": 0.0005,
                },
            },
            "lean_teg_in": {
                "T": 303.15,
                "P": 7.1e6,
                "molar_flow": 0.2,
                "composition": {"TEG": 0.985, "H2O": 0.015},
            },
        }
        return feeds, {"n_stages": 3}
