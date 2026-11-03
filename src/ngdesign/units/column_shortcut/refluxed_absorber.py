"""Refluxed / reboiled absorber, R2 (plan U-E 5, unit ``refluxed_absorber``).

Plugin kind "unit", name "refluxed_absorber". Ports ``gas_in`` + ``solvent_in``
-> ``gas_out`` + ``rich_out``. MESH with exactly one end exchanger, on the
column row's solvers (Boston & Sullivan 1974 inside-out with the Naphtali &
Sandholm 1971 fallback, ``ngdesign.units.column``); this module only lays the
two feeds and the single exchanger onto the column API. Stages 1..N top to
bottom.

``configuration: reboiled`` (Seader, Henley & Roper 3rd ed., Table 10.1, reboiled
absorber): kettle on stage N, no condenser, solvent on stage 1 by default, gas
on ``gas_stage``. One tear, the boilup; one spec: ``boilup_ratio``,
``bottoms_rate`` or ``component_recovery``.

``configuration: refluxed`` (ibid., refluxed absorber / rectifier with
solvent): a PARTIAL condenser is stage 1, no reboiler, gas on stage N by
default, solvent on ``solvent_stage``. One tear, the vapour product; one spec:
``distillate_rate``, the ``gas_out`` flow. A total condenser is refused here:
``gas_out`` is a vapour and a light gas does not condense at stage temperature.

Unlike the zero-tear absorber this unit has real heat-transfer equipment, so
``duty_W`` is the column's boundary-closed net duty and the exchanger's duty is
in ``info`` (``condenser_duty_W`` or ``reboiler_duty_W``). The unused end's
column closure value is reported as ``mesh_energy_residual_W``: the converged
MESH residual, not a duty.

Refusals (typed :class:`RefluxedAbsorberError`, a ValueError): a missing or
zero-flow inlet; an unknown ``configuration``; a missing or non-integer
``n_stages``; a spec key outside the configuration's list; any unknown
parameter. Column convergence and spec failures propagate as the column's own
typed errors.

All SI: K, Pa abs, mol/s, J/mol, W. Pure functions; no I/O; no global state.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column

_ALLOWED_KEYS = frozenset(
    {"n_stages", "configuration", "gas_stage", "solvent_stage", "pressure_profile", "spec"}
)
_SPECS = {
    "reboiled": frozenset({"boilup_ratio", "bottoms_rate", "component_recovery"}),
    "refluxed": frozenset({"distillate_rate"}),
}


#: Refluxed configuration: largest closure residual as a share of the inlet
#: enthalpy flows (the column's own stage-H gate, _MESH_H_TOL).
_MESH_ENERGY_GATE = 1e-2


class RefluxedAbsorberError(ValueError):
    """Refusal: the refluxed-absorber spec is invalid."""


def _stage(params: dict[str, Any], key: str, default: int, lowest: int, n_stages: int) -> int:
    value = params.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or not lowest <= value <= n_stages:
        raise RefluxedAbsorberError(f"{key} must be an integer in {lowest}..{n_stages}, got {value!r}")
    return value


class RefluxedAbsorber:
    """One-end-exchanger MESH absorber over the public column API."""

    inlet_ports = ("gas_in", "solvent_in")
    outlet_ports = ("gas_out", "rich_out")

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        gas = inlets.get("gas_in")
        solvent = inlets.get("solvent_in")
        if gas is None or solvent is None:
            missing = "gas_in" if gas is None else "solvent_in"
            raise RefluxedAbsorberError(f"refluxed_absorber requires the {missing} inlet stream")
        if gas.molar_flow <= 0.0 or solvent.molar_flow <= 0.0:
            raise RefluxedAbsorberError("refluxed_absorber refuses a zero-molar-flow inlet")
        for key in params:
            if key not in _ALLOWED_KEYS:
                raise RefluxedAbsorberError(f"refluxed_absorber refuses unknown parameter {key!r}")

        configuration = params.get("configuration", "reboiled")
        if configuration not in _SPECS:
            raise RefluxedAbsorberError(
                f"configuration must be 'reboiled' or 'refluxed', got {configuration!r}"
            )
        n_stages = params.get("n_stages")
        if not isinstance(n_stages, int) or isinstance(n_stages, bool) or n_stages < 3:
            raise RefluxedAbsorberError(f"n_stages must be an integer >= 3, got {n_stages!r}")
        spec = params.get("spec")
        if not isinstance(spec, dict) or len(spec) != 1 or not set(spec) <= _SPECS[configuration]:
            raise RefluxedAbsorberError(
                f"spec must be exactly one of {sorted(_SPECS[configuration])} "
                f"for the {configuration} configuration, got {spec!r}"
            )

        if configuration == "reboiled":
            condenser, reboiler = "none", "kettle"
            gas_stage = _stage(params, "gas_stage", (n_stages + 1) // 2, 2, n_stages)
            solvent_stage = _stage(params, "solvent_stage", 1, 1, n_stages)
        else:
            condenser, reboiler = "partial", "none"
            gas_stage = _stage(params, "gas_stage", n_stages, 2, n_stages)
            solvent_stage = _stage(params, "solvent_stage", (n_stages + 1) // 2, 1, n_stages)
        if solvent_stage > gas_stage:
            raise RefluxedAbsorberError(
                f"solvent_stage {solvent_stage} below gas_stage {gas_stage} is not a contactor: "
                "the solvent falls and the gas rises"
            )

        column_params: dict[str, Any] = {
            "n_stages": n_stages,
            "condenser": condenser,
            "reboiler": reboiler,
            "pressure_profile": params.get("pressure_profile", gas.P),
            "feed_stage": gas_stage,
            "feeds": [
                {
                    "stage": solvent_stage,
                    "T": solvent.T,
                    "P": solvent.P,
                    "molar_flow": solvent.molar_flow,
                    "composition": dict(solvent.composition),
                }
            ],
            "specs": spec,
        }
        result = Column().solve({"feed": gas}, column_params, thermo)

        info = {key: value for key, value in result.info.items() if key.startswith("stage_")}
        for key in ("n_stages", "outer_iterations", "inner_iterations", "ns_used"):
            info[key] = result.info[key]
        if configuration == "reboiled":
            info["reboiler_duty_W"] = result.info["reboiler_duty_W"]
            info["boilup_ratio"] = result.info["boilup_ratio"]
            info["mesh_energy_residual_W"] = 0.0
        else:
            info["condenser_duty_W"] = result.info["condenser_duty_W"]
            residual = result.info["reboiler_duty_W"]
            # This unit has no reboiler, so the column's closure value is the
            # MESH residual. Large means the gate passed estimated K-values on
            # a state with no real vapour-liquid equilibrium, never a duty.
            throughput = abs(gas.enthalpy * gas.molar_flow) + abs(solvent.enthalpy * solvent.molar_flow)
            if abs(residual) > _MESH_ENERGY_GATE * max(throughput, 1.0):
                raise RefluxedAbsorberError(
                    f"column closed with an energy residual of {residual:.4g} W on a unit with "
                    f"no reboiler: not a converged stage solve (throughput {throughput:.4g} W)"
                )
            info["mesh_energy_residual_W"] = residual
        return UnitResult(
            outlets={"gas_out": result.outlets["distillate"], "rich_out": result.outlets["bottoms"]},
            duty_W=result.duty_W,
            power_W=0.0,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """Illustrative feeds: C2/C3 gas into lean n-butane, 2 MPa, partial condenser."""
        feeds = {
            "gas_in": {
                "T": 320.0,
                "P": 2.0e6,
                "molar_flow": 100.0,
                "composition": {"C2": 0.6, "C3": 0.4},
            },
            "solvent_in": {"T": 300.0, "P": 2.0e6, "molar_flow": 60.0, "composition": {"NC4": 1.0}},
        }
        params = {
            "configuration": "refluxed",
            "n_stages": 8,
            "solvent_stage": 3,
            "spec": {"distillate_rate": 60.0},
        }
        return feeds, params
