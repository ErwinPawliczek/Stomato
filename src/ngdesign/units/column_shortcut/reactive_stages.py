"""Reactive stages, R2 (plan U-E 8, unit ``reactive_stages``).

Plugin kind "unit", name "reactive_stages". Ports ``feed`` -> ``distillate`` +
``bottoms``. MESH on the column row's solvers with a ReactionSet on the stage
liquid holdup: kinetic stages, with no chemical-equilibrium shortcut. The stage
equations carry

    S_ij = sum_r nu_ir H_j r_r(T_j, P_j, x_j)                 [mol/s]
    Q_rx,j = -sum_i S_ij dHf°298,i                            [W]

in the component and enthalpy balances (Taylor & Krishna, Chem. Eng. Sci. 55
(2000) 5183), where the rates are the shared ``units/_physics/kinetics`` rate
expressions, so this module holds no reaction physics of its own. It lays the
params onto the core (``_refresh_reactions`` in ``units/column/inside_out.py``)
and drops the zero-flow draw port. Chemical equilibrium is reached as the large
holdup limit of a reversible rate, tested against K_C(T).

A liquid stage bounds the rate forms: the mole-fraction basis only, and an
explicit reverse rate rather than ``Reaction.equilibrium``, whose quotient is
ideal-gas (typed ``ColumnSpecError`` from the column parser). Holdups sit on
ordinary trays: never on a condenser or kettle stage. Stage terms are reported
as ``stage_<j>_generation_<cid>``, the total as ``reaction_heat_W``.

The row declares ``balance: mass_elements``. ``duty_W`` is the net exchanger
duty and closes on the element-reference (formation) basis.

Example: the liquid-phase n-butane isomerization of Fogler, Elements of Chemical
Reaction Engineering, Example 11-3: k_f(360 K) = 31.1 1/h, E = 65.7 kJ/mol,
K_C(333 K) = 3.03, dH_rx = -6900 J/mol, C_A0 = 9.3 kmol/m3 at 90 mol% n-butane.
On the mole-fraction basis r = C_t (k_f x_A - k_r x_B), C_t = C_A0/0.9, and
k_r = k_f/K_C is an Arrhenius term with E_r = E - dH_rx. The tray holdup and the
column are illustrative, and the book's reactor is liquid-full: boiling on the
stage is this example's extrapolation of that rate law.

All SI: K, Pa abs, mol/s, J/mol, W, m3. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.column import Column

_ALLOWED_KEYS = frozenset(
    {
        "n_stages",
        "condenser",
        "reboiler",
        "feed_stage",
        "pressure_profile",
        "specs",
        "reaction_set",
        "reactive_holdup_m3",
    }
)

#: Fogler, Example 11-3 (see the module docstring).
_K_F_360 = 31.1 / 3600.0  # 1/s
_E_F = 65700.0  # J/mol
_K_C_333 = 3.03
_DH_RX = -6900.0  # J/mol
_C_TOTAL = 9300.0 / 0.9  # mol/m3


class ReactiveStagesError(ValueError):
    """Refusal: the reactive-stage spec is invalid."""


def fogler_isomerization_set() -> dict[str, Any]:
    """The Example 11-3 reversible rate as a ReactionSet document (mole-fraction basis)."""
    e_r = _E_F - _DH_RX
    k_f_333 = _K_F_360 * math.exp(-_E_F / R * (1.0 / 333.0 - 1.0 / 360.0))
    k0_forward = _C_TOTAL * _K_F_360 * math.exp(_E_F / (R * 360.0))
    k0_reverse = _C_TOTAL * k_f_333 / _K_C_333 * math.exp(e_r / (R * 333.0))
    return {
        "id": "fogler_ex_11_3",
        "components": ["nC4", "iC4"],
        "reactions": [
            {
                "id": "butane_isomerization",
                "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                "base_component": "nC4",
                "provenance": "Fogler, Elements of Chemical Reaction Engineering, Example 11-3",
                "kinetics": {
                    "rate_units": "mol/(m3·s)",
                    "k0": k0_forward,
                    "Ea": _E_F,
                    "orders": {"nC4": 1.0},
                    "basis": "mole_fraction",
                    "reverse": {
                        "rate_units": "mol/(m3·s)",
                        "k0": k0_reverse,
                        "Ea": e_r,
                        "orders": {"iC4": 1.0},
                        "basis": "mole_fraction",
                    },
                },
            }
        ],
    }


class ReactiveStages:
    """Kinetic reactive column over the public column API."""

    inlet_ports = ("feed",)
    outlet_ports = ("distillate", "bottoms")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        feed = inlets.get("feed")
        if feed is None:
            raise ReactiveStagesError("reactive_stages requires the feed inlet stream")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise ReactiveStagesError(f"reactive_stages refuses unknown parameter {key!r}")
        if "reaction_set" not in params or "reactive_holdup_m3" not in params:
            raise ReactiveStagesError("reactive_stages requires reaction_set and reactive_holdup_m3")
        result = Column().solve({"feed": feed}, params, thermo)
        return UnitResult(
            outlets={"distillate": result.outlets["distillate"], "bottoms": result.outlets["bottoms"]},
            duty_W=result.duty_W,
            power_W=0.0,
            info=result.info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Top-fed kettle column on the Fogler isomerization; holdups illustrative."""
        feed = {"T": 330.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"nC4": 0.9, "iC4": 0.1}}
        params = {
            "n_stages": 8,
            "condenser": "none",
            "reboiler": "kettle",
            "feed_stage": 1,
            "pressure_profile": 1.0e6,
            "specs": {"boilup_ratio": 1.0},
            "reaction_set": fogler_isomerization_set(),
            "reactive_holdup_m3": {str(stage): 0.05 for stage in range(1, 8)},
        }
        return {"feed": feed}, params
