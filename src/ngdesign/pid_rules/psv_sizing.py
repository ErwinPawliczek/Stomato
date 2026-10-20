"""S-34: Relief load and PSV sizing on the P&ID.

Plugin kind ``pid_rule``, name ``psv_sizing`` (runs after ``vessel_psv``).

Every pressure vessel's PSV is sized for up to two cases and the governing
API 526 orifice letter is recorded:

- **Blocked outlet**: load = max inlet flow to the vessel; relieving pressure
  = 1.1 x set pressure (spec S-34).
- **Fire case**: heat absorption Q = 21000 * F * A_wet^0.82 (API 521, USC
  units, F = 1, per spec S-34) with the wetted surface from the vessel
  datasheet; relieving pressure = 1.21 x set pressure. The vapor generation
  rate is Q / lambda, lambda the latent heat at relieving conditions. The
  case is evaluated only when the relief basis carries both a wetted area and
  a latent heat; the bare sample P&ID has no datasheet, so there the blocked
  outlet governs.

Required area comes from the S-09 correlation plugin ``psv_api520_gas``
(API 520 Part I eq. 9, critical flow); the orifice letter from its
``api526_orifice``. The letter is stored in the ``note`` of the
``InlineItem`` that references the PSV valve: the locked PID contract
annotates valves through the referencing line item (``Valve`` itself has no
note field). ``check()`` flags PSVs without a recorded orifice, and flags a
pressure vessel that has no PSV at all so the bare sample is not silently
clean; ``apply()`` delegates valve/line creation to ``vessel_psv`` and sizes
what a relief basis covers. Vessels outside the basis stay flagged: sizing
without a load basis would be fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass

from ngdesign import registry
from ngdesign.contracts import (
    PID,
    InlineItem,
    InlineKind,
    PhaseKind,
    PidEquipment,
    PidLine,
    RuleViolation,
    SolvedFlowsheet,
    Valve,
    ValveType,
)
from ngdesign.pid_rules._common import psv_nozzle
from ngdesign.pid_rules.vessel_psv import _PRESSURE_VESSEL_KINDS
from ngdesign.registry import register
from ngdesign.sizing.psv_gas import api526_orifice

__all__ = [
    "CaseSizing",
    "PsvSizing",
    "PsvSizingResult",
    "VesselRelief",
    "blocked_case",
    "fire_case",
    "relief_basis",
    "size_psv",
]

RULE_NAME = "psv_sizing"

#: Exact SI<->USC edge factors (unit definitions, not empirical data).
LB_PER_KG = 0.45359237  # avoirdupois pound, exact
R_PER_K = 9.0 / 5.0  # degree Rankine, exact
FT2_PER_M2 = 1.0 / 0.3048**2  # international foot, exact
BTU_IT_J = 1055.05585262  # international-table BTU, exact
PSI_PA = 4.4482216152605 / 0.0254**2  # pound-force per square inch, exact

#: Relieving pressure as a multiple of set pressure (spec S-34).
BLOCKED_OVERPRESSURE = 1.1
FIRE_OVERPRESSURE = 1.21

#: API 521 fire heat flux constant, BTU/(h.ft2^0.82), environmental factor F = 1 (spec S-34).
FIRE_HEAT_FLUX = 21000.0


@dataclass(frozen=True)
class VesselRelief:
    """Relief basis for one pressure vessel (SI inputs).

    ``blocked_load_mol_s`` is the max inlet flow (blocked outlet). ``k``, ``M_g_mol``
    and ``Z`` describe the relieving vapor. ``T_rel_K`` falls back to the vessel
    design temperature when not given. The fire case is evaluated only when both
    ``wetted_area_m2`` and ``latent_heat_J_mol`` are given. ``Kd``/``Kb``/``Kc`` are
    the API 520 discharge, back-pressure and combination correction factors.
    """

    blocked_load_mol_s: float
    k: float
    M_g_mol: float
    Z: float
    T_rel_K: float | None = None
    wetted_area_m2: float | None = None
    latent_heat_J_mol: float | None = None
    F: float = 1.0
    Kd: float = 0.975
    Kb: float = 1.0
    Kc: float = 1.0


@dataclass(frozen=True)
class CaseSizing:
    """One relief case's load, relieving pressure and required orifice area."""

    case: str  # "blocked outlet" | "fire"
    load_mol_s: float
    relieving_pressure_Pa: float
    area_in2: float


@dataclass(frozen=True)
class PsvSizingResult:
    """Governing sizing for one PSV across the evaluated relief cases."""

    cases: tuple[CaseSizing, ...]
    governing: str
    area_in2: float
    orifice: str


#: Relief basis for the hand-built sample P&ID, used when the rule is created
#: without an explicit basis (the pid_rule protocol passes no context). Values
#: are the slice basis for V-101: the 50 MMSCFD feed of flowsheets/slice.py as
#: blocked-outlet load; vapor M and Z from the S-01 PR flash of stream S-001;
#: ideal-gas k at the 338.15 K design temperature. The bare sample P&ID has no
#: vessel datasheet, so the fire case is not evaluated on it.
_DEFAULT_BASIS: dict[str, VesselRelief] = {
    "V-101": VesselRelief(
        blocked_load_mol_s=691.7061964498163,
        k=1.2437791845027308,
        M_g_mol=19.705974858874683,
        Z=0.8863507971362715,
    )
}


def _area_in2(basis: VesselRelief, load_mol_s: float, relieving_pressure_Pa: float, T_rel_K: float) -> float:
    """Required orifice area [in2] via the S-09 correlation (API 520 critical flow)."""
    w_lb_h = load_mol_s * basis.M_g_mol * 3600.0 / (1000.0 * LB_PER_KG)
    got = registry.create("correlation", "psv_api520_gas")(
        W_lb_h=w_lb_h,
        T_R=T_rel_K * R_PER_K,
        Z=basis.Z,
        M=basis.M_g_mol,
        k=basis.k,
        P1_psia=relieving_pressure_Pa / PSI_PA,
        Kd=basis.Kd,
        Kb=basis.Kb,
        Kc=basis.Kc,
    )
    return float(got["area_in2"])


def blocked_case(basis: VesselRelief, set_pressure_Pa: float, design_temperature_K: float) -> CaseSizing:
    """Blocked-outlet case: max inlet load at 1.1 x set pressure."""
    t_rel = basis.T_rel_K if basis.T_rel_K is not None else design_temperature_K
    p1 = BLOCKED_OVERPRESSURE * set_pressure_Pa
    return CaseSizing(
        case="blocked outlet",
        load_mol_s=basis.blocked_load_mol_s,
        relieving_pressure_Pa=p1,
        area_in2=_area_in2(basis, basis.blocked_load_mol_s, p1, t_rel),
    )


def fire_case(basis: VesselRelief, set_pressure_Pa: float, design_temperature_K: float) -> CaseSizing | None:
    """Fire case at 1.21 x set pressure; None when the basis carries no datasheet inputs."""
    if basis.wetted_area_m2 is None or basis.latent_heat_J_mol is None:
        return None
    a_ft2 = basis.wetted_area_m2 * FT2_PER_M2
    q_btu_h = FIRE_HEAT_FLUX * basis.F * a_ft2**0.82
    q_w = q_btu_h * BTU_IT_J / 3600.0
    load_mol_s = q_w / basis.latent_heat_J_mol
    t_rel = basis.T_rel_K if basis.T_rel_K is not None else design_temperature_K
    p1 = FIRE_OVERPRESSURE * set_pressure_Pa
    return CaseSizing(
        case="fire",
        load_mol_s=load_mol_s,
        relieving_pressure_Pa=p1,
        area_in2=_area_in2(basis, load_mol_s, p1, t_rel),
    )


def size_psv(basis: VesselRelief, set_pressure_Pa: float, design_temperature_K: float) -> PsvSizingResult:
    """Size one PSV across the blocked-outlet and (when evaluable) fire cases."""
    blocked = blocked_case(basis, set_pressure_Pa, design_temperature_K)
    fire = fire_case(basis, set_pressure_Pa, design_temperature_K)
    cases = (blocked,) + ((fire,) if fire is not None else ())
    governing = max(cases, key=lambda c: c.area_in2)
    return PsvSizingResult(
        cases=cases,
        governing=governing.case,
        area_in2=governing.area_in2,
        orifice=api526_orifice(governing.area_in2),
    )


def relief_basis(solved: SolvedFlowsheet, k_gas: float) -> dict[str, VesselRelief]:
    """Relief basis per pressure vessel from a solved flowsheet.

    Blocked-outlet load = max inlet molar flow; gas M and Z from that stream's
    vapor phase; relieving temperature = the stream temperature. ``k_gas`` is
    the heat-capacity ratio of the relieving vapor: not carried by the locked
    StreamState contract, so the caller supplies it (e.g. ideal-gas Cp/Cv at
    relieving conditions).
    """
    basis: dict[str, VesselRelief] = {}
    for unit in solved.flowsheet.units:
        if unit.kind not in _PRESSURE_VESSEL_KINDS:
            continue
        inlets = solved.flowsheet.inlets(unit.tag)
        if not inlets:
            continue
        governing = max(inlets, key=lambda s: solved.streams[s.id].molar_flow)
        state = solved.streams[governing.id]
        vapor = next((p for p in state.phases if p.kind == PhaseKind.VAPOR), None)
        if vapor is None:
            raise ValueError(
                f"vessel {unit.tag} inlet {governing.id} has no vapor phase; "
                "all-liquid relief is out of scope for S-34"
            )
        if vapor.z_factor is None:
            raise ValueError(f"vessel {unit.tag} inlet {governing.id} vapor phase has no z-factor")
        basis[unit.tag] = VesselRelief(
            blocked_load_mol_s=state.molar_flow,
            k=k_gas,
            M_g_mol=vapor.molecular_weight,
            Z=vapor.z_factor,
            T_rel_K=state.T,
        )
    return basis


def _relief_valves(pid: PID, eq: PidEquipment, nozzle_id: str) -> list[tuple[PidLine, InlineItem, Valve]]:
    """The PSV valves sitting on lines leaving the vessel's psv nozzle."""
    out: list[tuple[PidLine, InlineItem, Valve]] = []
    for ln in pid.lines:
        if ln.start.equipment != eq.tag or ln.start.nozzle != nozzle_id:
            continue
        for item in ln.items:
            if item.kind != InlineKind.VALVE or item.ref is None:
                continue
            valve = next((v for v in pid.valves if v.tag == item.ref), None)
            if valve is not None and valve.type == ValveType.PSV:
                out.append((ln, item, valve))
    return out


def _sized(item: InlineItem) -> bool:
    """True when the item's note records an API 526 orifice (apply()'s own format)."""
    return item.note.startswith("API 526")


def _note(sizing: PsvSizingResult) -> str:
    governing = next(c for c in sizing.cases if c.case == sizing.governing)
    return (
        f"API 526 {sizing.orifice} orifice ({sizing.governing} case governs, "
        f"{governing.area_in2:.3f} in2 at {governing.relieving_pressure_Pa / 1e6:.2f} MPa)"
    )


@register("pid_rule", RULE_NAME)
class PsvSizing:
    """Relief load and PSV sizing on the P&ID (spec S-34). Runs after vessel_psv."""

    def __init__(self, basis: dict[str, VesselRelief] | None = None) -> None:
        self._basis = basis

    def _basis_map(self) -> dict[str, VesselRelief]:
        """Explicit basis when given; the sample default otherwise."""
        return _DEFAULT_BASIS if self._basis is None else self._basis

    def check(self, pid: PID) -> list[RuleViolation]:
        """Flag PSVs without a recorded orifice, and vessels without any PSV to size."""
        violations: list[RuleViolation] = []
        for eq in pid.equipment:
            if eq.kind not in _PRESSURE_VESSEL_KINDS:
                continue
            nozzle = psv_nozzle(eq)
            if nozzle is None:
                continue  # nozzles are owned by the sizers; vessel_psv reports the gap
            reliefs = _relief_valves(pid, eq, nozzle.id)
            if not reliefs:
                violations.append(
                    RuleViolation(
                        rule=RULE_NAME,
                        target=eq.tag,
                        message=f"pressure vessel {eq.tag} has no PSV to size",
                    )
                )
                continue
            for ln, item, valve in reliefs:
                if not _sized(item):
                    violations.append(
                        RuleViolation(
                            rule=RULE_NAME,
                            target=valve.tag,
                            message=f"PSV {valve.tag} on {ln.number} has no API 526 orifice recorded",
                        )
                    )
        return violations

    def apply(self, pid: PID) -> PID:
        """Add missing PSVs (via vessel_psv) and record the governing orifice for each PSV."""
        fixed: PID = registry.create("pid_rule", "vessel_psv").apply(pid)
        basis_map = self._basis_map()
        for eq in fixed.equipment:
            if eq.kind not in _PRESSURE_VESSEL_KINDS:
                continue
            nozzle = psv_nozzle(eq)
            if nozzle is None:
                continue
            for _ln, item, valve in _relief_valves(fixed, eq, nozzle.id):
                if _sized(item):
                    continue
                basis = basis_map.get(eq.tag)
                if basis is None or valve.set_pressure_Pa is None:
                    continue  # stays flagged by check(); sizing without inputs would be fabrication
                item.note = _note(size_psv(basis, valve.set_pressure_Pa, eq.design_temperature_K))
        return fixed
