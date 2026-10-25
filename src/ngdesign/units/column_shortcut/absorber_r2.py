"""Zero-tear MESH absorber, R2 (spec U-R2, unit ``absorber``).

Plugin kind "unit", name "absorber", level R2 (adapter registered through the
catalogue YAML row ``absorber``/``levels.R2``). Ports ``gas_in`` +
``solvent_in`` -> ``gas_out`` + ``rich_out``, as R0.

Method (spec): the absorber is the column row's MESH equilibrium-stage solver
(Material, Equilibrium, Summation and entHalpy balances per stage; Boston &
Sullivan 1974 inside-out with the Naphtali & Sandholm 1971 fallback, as
implemented in ``ngdesign.units.column``) in its zero-tear configuration —
no condenser, no reboiler, both feeds given, so the column's tears are zero
and its specs loop is empty (P1-09). No new equations and no iteration of its
own: this adapter builds the column params and wraps the public column API.
Lean solvent enters stage 1 as a liquid feed; feed gas enters stage N
(``feed_stage = N``). Stage numbering is 1..N top to bottom. ``gas_out`` is
the vapour leaving stage 1 (the column's ``distillate`` with
``condenser="none"``); ``rich_out`` is the liquid leaving stage N (the
column's ``bottoms``). The column's ``side_draw`` is a zero-flow placeholder
and is dropped.

**Energy, reported honestly.** The column feeds the solvent by re-flashing it
at (T, P), and a zero-hardware column closes its enthalpy only to its
stage-H gate (``_MESH_H_TOL = 1e-2`` relative; measured P1-09: 4.8e-3 of
throughput at N=2, 3.8e-7 at N=20). This adapter therefore computes its own
boundary residual from the ACTUAL inlet states,

    Q_res = sum(n*h)_out - sum(n*h)_in,

and returns ``duty_W = Q_res``: that closes V0 exactly. An adiabatic absorber
has no real duty — ``duty_W`` is the solver's residual, never a modelled
exchanger. The residual is also reported as ``info["mesh_energy_residual_W"]``
and ``info["mesh_energy_residual_rel"] = |Q_res| / max(|H_in|, |H_out|, 1)``.

Refusals (typed :class:`AbsorberR2Error`, a ValueError): a missing/non-int/
too-small ``n_stages``; a ``pressure_profile`` list whose length differs from
``n_stages`` or that carries a non-positive value; a zero-molar-flow inlet; a
``solvent_in`` vapour fraction above 0.5 (the zero-tear seed assumes a mainly
liquid top feed); any parameter other than ``n_stages``, ``pressure_profile``
and the level-dispatch selector ``model``. The ``model`` key is the
catalogue's own level selector (``ngdesign.units.levels``) and passes through
``LevelDispatch.solve`` unchanged, so it is not an absorber parameter. A
column convergence failure propagates as the column's own
``ColumnConvergenceError`` — never caught or converted here.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.column_shortcut.absorber import Absorber

#: The level-dispatch selector key (``ngdesign.units.levels.MODEL_KEY``).
#: It rides along on catalogue-driven calls and is not an absorber parameter.
_MODEL_KEY = "model"

#: Every params key :meth:`AbsorberR2.solve` accepts.
_ALLOWED_KEYS = frozenset({"n_stages", "pressure_profile", _MODEL_KEY})


class AbsorberR2Error(ValueError):
    """Refusal: the absorber R2 spec is invalid (typed ValueError per U-R2)."""


def _is_real_number(value: Any) -> bool:
    """True for int/float that is not a bool (bools are ints in Python)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class AbsorberR2:
    """MESH absorber (feed-determined, zero-tear) over the public column API."""

    inlet_ports = ("gas_in", "solvent_in")
    outlet_ports = ("gas_out", "rich_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        gas = inlets.get("gas_in")
        solvent = inlets.get("solvent_in")
        if gas is None or solvent is None:
            missing = "gas_in" if gas is None else "solvent_in"
            raise AbsorberR2Error(f"absorber R2 requires the {missing} inlet stream")
        if gas.molar_flow <= 0.0:
            raise AbsorberR2Error(f"absorber R2 refuses a zero-molar-flow gas_in (got {gas.molar_flow})")
        if solvent.molar_flow <= 0.0:
            raise AbsorberR2Error(
                f"absorber R2 refuses a zero-molar-flow solvent_in (got {solvent.molar_flow})"
            )
        if solvent.vapor_fraction > 0.5:
            raise AbsorberR2Error(
                f"absorber R2 refuses solvent_in with vapour fraction "
                f"{solvent.vapor_fraction:.3f} > 0.5: the zero-tear seed assumes "
                "a mainly-liquid top feed"
            )

        n_stages = params.get("n_stages")
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 2:
            raise AbsorberR2Error(f"absorber R2 requires an integer n_stages >= 2, got {n_stages!r}")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise AbsorberR2Error(f"absorber R2 refuses unknown parameter {key!r}")

        profile = params.get("pressure_profile", gas.P)
        pressure_profile: float | list[float]
        if isinstance(profile, list):
            if len(profile) != n_stages:
                raise AbsorberR2Error(
                    f"absorber R2 pressure_profile must carry n_stages={n_stages} entries, got {len(profile)}"
                )
            if not all(_is_real_number(v) and float(v) > 0.0 for v in profile):
                raise AbsorberR2Error("absorber R2 pressure_profile entries must all be positive")
            pressure_profile = [float(v) for v in profile]
        elif _is_real_number(profile):
            if float(profile) <= 0.0:
                raise AbsorberR2Error(f"absorber R2 pressure_profile must be positive, got {profile}")
            pressure_profile = float(profile)
        else:
            raise AbsorberR2Error(
                f"absorber R2 pressure_profile must be a positive number or a list "
                f"of n_stages positive numbers, got {profile!r}"
            )

        column_params: dict[str, Any] = {
            "n_stages": n_stages,
            "condenser": "none",
            "reboiler": "none",
            "pressure_profile": pressure_profile,
            "feed_stage": n_stages,
            "feeds": [
                {
                    "stage": 1,
                    "T": solvent.T,
                    "P": solvent.P,
                    "molar_flow": solvent.molar_flow,
                    "composition": dict(solvent.composition),
                }
            ],
        }
        result = Column().solve({"feed": gas}, column_params, thermo)

        # gas_out = stage-1 vapour (the column's distillate, condenser="none");
        # rich_out = stage-N liquid (the column's bottoms). The column's
        # side_draw is a zero-flow placeholder and is dropped.
        gas_out = result.outlets["distillate"]
        rich_out = result.outlets["bottoms"]

        # Boundary energy residual from the ACTUAL inlet states: the zero-
        # hardware column closes enthalpy only to its stage-H gate, so the
        # adapter closes V0 exactly on its own residual (see module docstring).
        h_in = gas.molar_flow * gas.enthalpy + solvent.molar_flow * solvent.enthalpy
        h_out = gas_out.molar_flow * gas_out.enthalpy + rich_out.molar_flow * rich_out.enthalpy
        q_res = h_out - h_in
        scale = max(abs(h_in), abs(h_out), 1.0)

        info: dict[str, float] = {
            key: value for key, value in result.info.items() if key.startswith("stage_")
        }
        info["n_stages"] = float(n_stages)
        info["outer_iterations"] = result.info["outer_iterations"]
        info["inner_iterations"] = result.info["inner_iterations"]
        info["ns_used"] = result.info["ns_used"]
        info["mesh_energy_residual_W"] = q_res
        info["mesh_energy_residual_rel"] = abs(q_res) / scale

        return UnitResult(
            outlets={"gas_out": gas_out, "rich_out": rich_out},
            duty_W=q_res,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """R0's Seader-Henley-Roper Example 5.3 feeds (pp. 186-188), at
        ``n_stages = 4`` on the column's own package K-values."""
        feeds, _ = Absorber.example_case()
        return feeds, {"n_stages": 4}
