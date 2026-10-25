"""Reciprocating compressor, R1: cylinder capacity vs clearance and rod load.

Spec: ``specs/backend/units/reciprocating_compressor.md`` (level R1, over the
R0 staged-isentropic adapter, which is imported read-only).

Geometry, per stage ``i`` (GPSA Engineering Data Book, 13th ed., Section 13,
piston displacement and the VE equation; API 618 5th ed. definitions and
§6.6 "combined rod load"; Bloch & Hoefner, *Reciprocating Compressors* (1996),
ch. 2):

- Piston and rod areas ``A_p = pi*D_b^2/4``, ``A_r = pi*d_r^2/4``.
- Piston displacement per cylinder, with crank speed ``N`` (rpm) and stroke
  ``S``: double-acting ``PD = (2*A_p - A_r)*S*N/60``; single-acting head end
  ``PD = A_p*S*N/60``.
- Volumetric efficiency with the compressibility correction::

      E_v,i = 1 - L - C_i * ((Z_s/Z_d) * r^(1/k_i) - 1)

  ``k_i = Cp/(Cp - R)`` at the stage suction (R0's ``_k_ideal``), ``Z_s`` and
  ``Z_d`` the suction/discharge vapour ``z_factor``. With
  ``z_ratio_correction: false`` the ratio is 1, which is exactly R0's formula.
- Stage capacity ``Cap_i = n_cyl,i * PD_i * E_v,i`` (m3/s at suction
  conditions), against the required suction flow ``Q_s,i = m/rho(S_i)``.
- Clearance pocket to match the flow (capacity control by added clearance);
  because ``E_v`` is linear in the clearance, the requirement is closed form::

      C_req,i = (1 - L - Q_s,i/(n_cyl,i * PD_i)) / ((Z_s/Z_d) * r^(1/k_i) - 1)
- Gas rod load (gas load only; **inertia loads are out of scope at R1**),
  with ``F(P_HE, P_CE) = P_HE*A_p - P_CE*(A_p - A_r) - P_cc*A_r``:
  double-acting compression load ``F_c = F(P_d, P_s)`` and tension load
  ``F_t = -F(P_s, P_d)``; single-acting head end ``F_c = F(P_d, P_cc)`` and
  ``F_t = -F(P_s, P_cc)``.

Outlets, ``power_W`` and ``duty_W`` are R0's exactly: the module runs the R0
adapter, re-traverses the identical stage sequence to expose the per-stage
suction/discharge states, and asserts the re-run's final state equals R0's
outlet (a mismatch is a bug, raised as ``RuntimeError``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.efficiency import isentropic_step
from ngdesign.units.flow.reciprocating_compressor import ReciprocatingCompressor, _k_ideal

#: Legal acting types for a cylinder (double, or single-acting head end).
_ACTIONS = ("double", "single_head_end")
#: Legal capacity-control modes (none, or report the required clearance pocket).
_CAPACITY_CONTROLS = ("none", "clearance_pocket")


class RecipR1SpecError(ValueError):
    """Typed refusal naming the parameter of a bad R1 compressor spec."""


class RecipCapacityError(RecipR1SpecError):
    """The cylinder geometry cannot deliver the required suction flow."""


class RecipRodLoadError(RecipR1SpecError):
    """The gas rod load exceeds a stated allowable."""


@dataclass(frozen=True)
class _Cylinder:
    """One validated stage's cylinder geometry."""

    n_cylinders: int
    bore_m: float
    stroke_m: float
    rod_diameter_m: float
    action: str
    clearance: float


def _vapor_phase(state: StreamState, what: str) -> Any:
    """The vapour phase of a state; raises if absent."""
    for phase in state.phases:
        if phase.kind == "vapor":
            return phase
    raise RecipR1SpecError(f"{what} has no vapor phase")


def _cylinder(raw: Any, stage: int) -> _Cylinder:
    """Validate one ``cylinders[i]`` entry (0-based index; messages are 1-based)."""
    where = f"stage {stage + 1}"
    if not isinstance(raw, dict):
        raise RecipR1SpecError(f"{where}: cylinders[{stage}] must be a mapping")
    bore = float(raw["bore_m"]) if raw.get("bore_m") is not None else 0.0
    if raw.get("bore_m") is None:
        raise RecipR1SpecError(f"{where}: bore_m is required")
    stroke = float(raw["stroke_m"]) if raw.get("stroke_m") is not None else 0.0
    if raw.get("stroke_m") is None:
        raise RecipR1SpecError(f"{where}: stroke_m is required")
    rod = float(raw["rod_diameter_m"]) if raw.get("rod_diameter_m") is not None else 0.0
    if raw.get("rod_diameter_m") is None:
        raise RecipR1SpecError(f"{where}: rod_diameter_m is required")
    n_cylinders = int(raw.get("n_cylinders", 1))
    action = str(raw.get("action", "double"))
    clearance = float(raw.get("clearance", 0.10))
    if n_cylinders < 1:
        raise RecipR1SpecError(f"{where}: n_cylinders {n_cylinders} must be >= 1")
    if bore <= 0.0:
        raise RecipR1SpecError(f"{where}: bore_m {bore} must be > 0")
    if stroke <= 0.0:
        raise RecipR1SpecError(f"{where}: stroke_m {stroke} must be > 0")
    if rod <= 0.0:
        raise RecipR1SpecError(f"{where}: rod_diameter_m {rod} must be > 0")
    if rod >= bore:
        raise RecipR1SpecError(f"{where}: rod_diameter_m {rod} must be < bore_m {bore}")
    if action not in _ACTIONS:
        raise RecipR1SpecError(f"{where}: action {action!r} must be one of {list(_ACTIONS)}")
    if not 0.0 <= clearance < 1.0:
        raise RecipR1SpecError(f"{where}: clearance {clearance} outside [0, 1)")
    return _Cylinder(n_cylinders, bore, stroke, rod, action, clearance)


class ReciprocatingCompressorR1:
    """Multistage reciprocating compressor with per-stage cylinder geometry (R1).

    Balances and thermodynamics are R0's; R1 adds piston displacement, the
    Z-corrected volumetric efficiency, stage capacity vs the required suction
    flow, the closed-form clearance pocket, and gas rod loads (no inertia).
    """

    inlet_ports = ("inlet",)
    outlet_ports = ("outlet",)

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        if "clearance" in params:
            raise RecipR1SpecError("use cylinders[].clearance")
        n_stages = int(params.get("n_stages", 1))
        raw_cylinders = params.get("cylinders")
        if not isinstance(raw_cylinders, (list, tuple)) or len(raw_cylinders) != n_stages:
            raise RecipR1SpecError(
                f"cylinders must have one entry per stage (n_stages={n_stages})"
            )
        cylinders = [_cylinder(raw, i) for i, raw in enumerate(raw_cylinders)]
        speed_rpm = params.get("speed_rpm")
        if speed_rpm is None:
            raise RecipR1SpecError("speed_rpm is required")
        speed = float(speed_rpm)
        if speed <= 0.0:
            raise RecipR1SpecError(f"speed_rpm {speed} must be > 0")
        capacity_control = str(params.get("capacity_control", "none"))
        if capacity_control not in _CAPACITY_CONTROLS:
            raise RecipR1SpecError(
                f"capacity_control {capacity_control!r} must be one of {list(_CAPACITY_CONTROLS)}"
            )
        z_ratio_correction = bool(params.get("z_ratio_correction", True))
        loss = float(params.get("loss_allowance", 0.0))
        p_crankcase_raw = params.get("P_crankcase_Pa")
        p_crankcase = float(p_crankcase_raw) if p_crankcase_raw is not None else 101325.0
        if p_crankcase <= 0.0:
            raise RecipR1SpecError(f"P_crankcase_Pa {p_crankcase} must be > 0")
        rod_limit = params.get("rod_load_limit_N")
        limit_compression: float | None = None
        limit_tension: float | None = None
        if rod_limit is not None:
            if not isinstance(rod_limit, dict):
                raise RecipR1SpecError("rod_load_limit_N must be a mapping")
            limit_compression = (
                float(rod_limit["compression"])
                if rod_limit.get("compression") is not None
                else None
            )
            limit_tension = (
                float(rod_limit["tension"]) if rod_limit.get("tension") is not None else None
            )
            for name, value in (("compression", limit_compression), ("tension", limit_tension)):
                if value is not None and value <= 0.0:
                    raise RecipR1SpecError(f"rod_load_limit_N.{name} {value} must be > 0")

        def _rod_load(p_head_end: float, p_crank_end: float, cyl: _Cylinder) -> float:
            """Gas load on the rod (N), positive in compression (API 618 §6.6)."""
            a_p = math.pi * cyl.bore_m**2 / 4.0
            a_r = math.pi * cyl.rod_diameter_m**2 / 4.0
            return p_head_end * a_p - p_crank_end * (a_p - a_r) - p_crankcase * a_r

        # R0 owns the balances: run it on the R0 keys, with stage 1's clearance.
        r0_params: dict[str, Any] = {
            "P_out": params["P_out"],
            "n_stages": n_stages,
            "eta_isentropic": params.get("eta_isentropic", 0.75),
            "T_intercool": params.get("T_intercool"),
            "clearance": cylinders[0].clearance,
            "loss_allowance": loss,
        }
        r0 = ReciprocatingCompressor().solve(inlets, r0_params, thermo)

        # Re-traverse the identical stage sequence to expose S_i and D_i.
        # The re-run is deterministic; its final state must equal R0's outlet,
        # else this module's traversal is a bug, not a refused spec.
        P_in = inlet.P
        ratio = float(r0.info["pressure_ratio_per_stage"])
        eta = float(r0_params["eta_isentropic"])
        T_intercool = r0_params["T_intercool"]
        z, flow = inlet.composition, inlet.molar_flow
        suction = inlet
        stages: list[tuple[StreamState, StreamState]] = []
        for stage in range(1, n_stages + 1):
            P_stage = P_in * ratio**stage
            discharge, _power = isentropic_step(suction, P_stage, eta, thermo, "compress")
            stages.append((suction, discharge))
            if stage < n_stages and T_intercool is not None and T_intercool < discharge.T:
                suction = thermo.flash_pt(z, float(T_intercool), P_stage, flow)
            else:
                suction = discharge
        final_T, final_P, final_h = stages[-1][1].T, stages[-1][1].P, stages[-1][1].enthalpy
        outlet = r0.outlets["outlet"]
        if (final_T, final_P, final_h) != (outlet.T, outlet.P, outlet.enthalpy):
            raise RuntimeError(
                "R1 stage re-traversal diverged from R0's outlet: "
                f"T {final_T} vs {outlet.T}, P {final_P} vs {outlet.P}, "
                f"h {final_h} vs {outlet.enthalpy}"
            )

        info: dict[str, Any] = dict(r0.info)
        for i, (s_i, d_i) in enumerate(stages, start=1):
            cyl = cylinders[i - 1]
            where = f"stage {i}"
            rho_s = float(_vapor_phase(s_i, f"{where} suction").density)
            q_s = s_i.mass_flow / rho_s
            k = _k_ideal(s_i, thermo, f"{where} suction")
            a_p = math.pi * cyl.bore_m**2 / 4.0
            a_r = math.pi * cyl.rod_diameter_m**2 / 4.0
            if cyl.action == "double":
                pd_cyl = (2.0 * a_p - a_r) * cyl.stroke_m * speed / 60.0
            else:
                pd_cyl = a_p * cyl.stroke_m * speed / 60.0
            displacement = cyl.n_cylinders * pd_cyl
            if z_ratio_correction:
                z_s = _vapor_phase(s_i, f"{where} suction").z_factor
                z_d = _vapor_phase(d_i, f"{where} discharge").z_factor
                if z_s is None or z_d is None:
                    raise RecipR1SpecError(
                        f"{where}: z_factor missing (suction {z_s}, discharge {z_d}); "
                        "z_ratio_correction needs single-phase vapour Z"
                    )
                z_ratio = float(z_s) / float(z_d)
            else:
                z_ratio = 1.0
            e_v = 1.0 - loss - cyl.clearance * (z_ratio * ratio ** (1.0 / k) - 1.0)
            if e_v <= 0.0:
                raise RecipCapacityError(
                    f"{where}: volumetric efficiency {e_v:.6f} <= 0: clearance "
                    f"{cyl.clearance} and loss {loss} cannot carry stage ratio {ratio:.3f}"
                )
            capacity = displacement * e_v
            info[f"displacement_stage{i}_m3_s"] = displacement
            info[f"volumetric_efficiency_stage{i}"] = e_v
            info[f"capacity_stage{i}_m3_s"] = capacity
            info[f"Q_suction_stage{i}_m3_s"] = q_s
            info[f"capacity_ratio_stage{i}"] = capacity / q_s
            if capacity < q_s:
                raise RecipCapacityError(
                    f"{where}: capacity {capacity:.6f} m3/s < required suction flow "
                    f"{q_s:.6f} m3/s; add cylinders or reduce the stage clearance"
                )
            # Gas rod load (API 618 §6.6): gas load only, no inertia loads.
            p_s, p_d = float(s_i.P), float(d_i.P)
            if cyl.action == "double":
                load_compression = _rod_load(p_d, p_s, cyl)
                load_tension = -_rod_load(p_s, p_d, cyl)
            else:
                load_compression = _rod_load(p_d, p_crankcase, cyl)
                load_tension = -_rod_load(p_s, p_crankcase, cyl)
            info[f"rod_load_compression_stage{i}_N"] = load_compression
            info[f"rod_load_tension_stage{i}_N"] = load_tension
            for kind, load, limit in (
                ("compression", load_compression, limit_compression),
                ("tension", load_tension, limit_tension),
            ):
                if limit is not None and load > limit:
                    raise RecipRodLoadError(
                        f"{where}: rod {kind} load {load:.1f} N exceeds the allowable "
                        f"{limit:.1f} N (gas load only; inertia loads are out of scope at R1)"
                    )
            if capacity_control == "clearance_pocket":
                # Closed form (E_v is linear in C). c_req < C cannot occur when
                # Cap >= Q and K > 0, so that branch is a guard, not a refusal
                # of a user error of its own kind.
                kk = z_ratio * ratio ** (1.0 / k) - 1.0
                c_req = (1.0 - loss - q_s / displacement) / kk if kk > 0.0 else float("inf")
                if c_req < cyl.clearance:
                    raise RecipCapacityError(
                        f"{where}: required clearance {c_req:.6f} below the fixed "
                        f"clearance {cyl.clearance} (capacity already sufficient; guard)"
                    )
                if c_req >= 1.0:
                    raise RecipCapacityError(
                        f"{where}: required clearance {c_req:.6f} >= 1; the cylinders "
                        "cannot be trimmed to the required flow by a clearance pocket"
                    )
                info[f"clearance_required_stage{i}"] = c_req

        return UnitResult(
            outlets=r0.outlets,
            duty_W=r0.duty_W,
            power_W=r0.power_W,
            info=info,
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The R0 two-stage example basis plus the R1 cylinder geometry (spec Tests).

        Stage 1: one double-acting cylinder, bore 0.34 m, stroke 0.20 m, rod
        0.06 m, clearance 0.10; stage 2 the same at bore 0.28 m; 900 rpm.
        """
        feeds, r0_params = ReciprocatingCompressor.example_case()
        params = {key: value for key, value in r0_params.items() if key != "clearance"}
        params["cylinders"] = [
            {
                "n_cylinders": 1,
                "bore_m": 0.34,
                "stroke_m": 0.20,
                "rod_diameter_m": 0.06,
                "action": "double",
                "clearance": 0.10,
            },
            {
                "n_cylinders": 1,
                "bore_m": 0.28,
                "stroke_m": 0.20,
                "rod_diameter_m": 0.06,
                "action": "double",
                "clearance": 0.10,
            },
        ]
        params["speed_rpm"] = 900.0
        return feeds, params
