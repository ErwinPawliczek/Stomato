"""ASME B31.3 pipe wall thickness and schedule selection (spec S-02).

Pressure design thickness per ASME B31.3 para. 304.1.2:

    t = P * D / (2 * (S * E * W + P * Y))

with P (design pressure) and S (allowable stress) in MPa and D = pipe OD in mm
from `ngdesign.data`. The required nominal thickness adds corrosion allowance
and compensates the mill tolerance:

    t_nominal = (t + CA) / (1 - mill_tolerance)

The thinnest schedule, in ASME B36.10M preference order, whose wall thickness
is at least t_nominal is selected (ties go to the earlier entry).
"""

from __future__ import annotations

from typing import Any

from ngdesign.data import pipe, pipe_classes, pipe_schedules
from ngdesign.registry import register

#: ASME B36.10M schedule preference order (thinnest first; ties -> earlier entry).
SCHEDULE_PREFERENCE: tuple[str, ...] = (
    "10",
    "20",
    "30",
    "40",
    "STD",
    "60",
    "XS",
    "80",
    "100",
    "120",
    "140",
    "160",
    "XXS",
)

#: Standard B31.3 mill tolerance for seamless pipe (12.5%); overridable in select_schedule.
DEFAULT_MILL_TOLERANCE = 0.125

MPa_PER_PA = 1.0e-6


def _pipe_od_mm(nps_in: float) -> float:
    """OD (mm) for an NPS from the first B36.10M/B36.19M row on file."""
    for row in pipe_schedules():
        if row["nps_in"] == nps_in:
            return float(row["od_mm"])
    raise ValueError(f"unknown NPS {nps_in!r} in pipe schedule data")


def select_schedule_for_nominal(nps_in: float, t_nominal_mm: float) -> tuple[str, float]:
    """Thinnest schedule for NPS with wall >= t_nominal (mm).

    "Thinnest" = minimum wall among the preferred schedules available for the
    NPS; ties (equal wall, e.g. SCH 40 vs STD) go to the earlier entry in
    SCHEDULE_PREFERENCE. Returns (schedule, wall_mm). Raises ValueError when no
    listed schedule suffices for the NPS.
    """
    candidates = []
    for schedule in SCHEDULE_PREFERENCE:
        row = _try_pipe(nps_in, schedule)
        if row is not None and float(row["wall_mm"]) >= t_nominal_mm:
            # Tuple order (wall, preference index) makes min() pick the thinnest
            # wall, breaking ties toward the earlier preferred schedule.
            candidates.append((float(row["wall_mm"]), SCHEDULE_PREFERENCE.index(schedule), schedule))
    if not candidates:
        raise ValueError(
            f"no schedule for NPS {nps_in} with wall >= {t_nominal_mm:.4f} mm among {SCHEDULE_PREFERENCE}"
        )
    wall_mm, _, schedule = min(candidates)
    return schedule, wall_mm


def _try_pipe(nps_in: float, schedule: str) -> dict[str, Any] | None:
    """pipe() row or None when the schedule is not offered for that NPS."""
    try:
        return pipe(nps_in, schedule)
    except KeyError:
        return None


def wall_thickness_b313(
    nps_in: float,
    design_pressure_gauge_Pa: float,
    pipe_class: str,
    allowable_stress_MPa: float,
    E: float,
    W: float,
    Y: float,
    corrosion_allowance_mm: float,
    mill_tolerance: float,
) -> dict[str, float | str]:
    """B31.3 304.1.2 wall thickness and schedule selection for one pipe.

    Args:
        nps_in: nominal pipe size (inch).
        design_pressure_gauge_Pa: design pressure, gauge (Pa).
        pipe_class: pipe class id from `ngdesign.data.pipe_classes()` (validated).
        allowable_stress_MPa: basic allowable stress S (MPa).
        E: weld joint quality factor (B31.3 Table A-1B).
        W: weld joint strength reduction factor (B31.3 302.3.5).
        Y: B31.3 Table 304.1.1 coefficient.
        corrosion_allowance_mm: corrosion/erosion allowance CA (mm).
        mill_tolerance: fractional mill tolerance (0 <= mt < 1).

    Returns od_mm, t_pressure_mm, t_required_nominal_mm, selected_wall_mm,
    selected_schedule. Raises ValueError on invalid input or when no schedule
    suffices.
    """
    if nps_in <= 0:
        raise ValueError(f"nps_in must be positive, got {nps_in}")
    if design_pressure_gauge_Pa <= 0:
        raise ValueError(f"design_pressure_gauge_Pa must be positive, got {design_pressure_gauge_Pa}")
    if allowable_stress_MPa <= 0:
        raise ValueError(f"allowable_stress_MPa must be positive, got {allowable_stress_MPa}")
    if E <= 0:
        raise ValueError(f"joint quality factor E must be positive, got {E}")
    if W <= 0:
        raise ValueError(f"weld strength reduction factor W must be positive, got {W}")
    if Y < 0:
        raise ValueError(f"Y coefficient must be non-negative, got {Y}")
    if corrosion_allowance_mm < 0:
        raise ValueError(f"corrosion_allowance_mm must be non-negative, got {corrosion_allowance_mm}")
    if not 0 <= mill_tolerance < 1:
        raise ValueError(f"mill_tolerance must be in [0, 1), got {mill_tolerance}")
    if pipe_class not in pipe_classes():
        raise ValueError(f"unknown pipe class {pipe_class!r}")

    od_mm = _pipe_od_mm(nps_in)
    p_mpa = design_pressure_gauge_Pa * MPa_PER_PA

    # B31.3 304.1.2 eq. (3a): t = P*D / (2*(S*E*W + P*Y)), P and S in MPa.
    t_pressure_mm = p_mpa * od_mm / (2.0 * (allowable_stress_MPa * E * W + p_mpa * Y))
    t_required_nominal_mm = (t_pressure_mm + corrosion_allowance_mm) / (1.0 - mill_tolerance)

    schedule, wall_mm = select_schedule_for_nominal(nps_in, t_required_nominal_mm)

    # Report at 0.0001 mm (0.1 um) precision, matching the golden data precision;
    # schedule selection above uses the unrounded nominal.
    return {
        "od_mm": od_mm,
        "t_pressure_mm": round(t_pressure_mm, 4),
        "t_required_nominal_mm": round(t_required_nominal_mm, 4),
        "selected_wall_mm": wall_mm,
        "selected_schedule": schedule,
    }


def select_schedule(
    nps_in: float,
    design_pressure_gauge_Pa: float,
    pipe_class: str,
    mill_tolerance: float = DEFAULT_MILL_TOLERANCE,
) -> dict[str, float | str]:
    """B31.3 wall thickness + schedule using class data from `ngdesign.data`.

    Reads S, E, W, Y and CA from `ngdesign.data.pipe_classes()[pipe_class]`;
    mill tolerance defaults to the standard 12.5% for seamless pipe.
    """
    cls = pipe_classes().get(pipe_class)
    if cls is None:
        raise ValueError(f"unknown pipe class {pipe_class!r}")
    return wall_thickness_b313(
        nps_in=nps_in,
        design_pressure_gauge_Pa=design_pressure_gauge_Pa,
        pipe_class=pipe_class,
        allowable_stress_MPa=float(cls["allowable_stress_MPa"]),
        E=float(cls["weld_joint_E"]),
        W=float(cls["weld_strength_W"]),
        Y=float(cls["Y"]),
        corrosion_allowance_mm=float(cls["corrosion_allowance_mm"]),
        mill_tolerance=mill_tolerance,
    )


@register("correlation", "wall_thickness_b313")
class WallThicknessB313:
    """Correlation plugin; contract is data/golden/wall_thickness_b313.yaml."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        return wall_thickness_b313(**inputs)
