"""Read-only access to the reference tables in /data. LOCKED.
Plugins read reference data only through these functions, never by hard-coding values.
"""

from __future__ import annotations

import csv
from functools import cache
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@cache
def components() -> dict[str, dict[str, Any]]:
    """Component constants keyed by COMPONENTS ids (SI)."""
    raw = yaml.safe_load((DATA_DIR / "components.yaml").read_text())
    table: dict[str, dict[str, Any]] = raw["components"]
    return table


@cache
def pipe_classes() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load((DATA_DIR / "pipe_classes.yaml").read_text())
    table: dict[str, dict[str, Any]] = raw["classes"]
    return table


@cache
def pipe_schedules() -> list[dict[str, Any]]:
    """Rows: nps_in, schedule, od_mm, wall_mm, id_mm (ASME B36.10M/B36.19M)."""
    with (DATA_DIR / "pipe_schedules_b3610.csv").open() as f:
        return [
            {
                "nps_in": float(r["nps_in"]),
                "schedule": r["schedule"],
                "od_mm": float(r["od_mm"]),
                "wall_mm": float(r["wall_mm"]),
                "id_mm": float(r["id_mm"]),
            }
            for r in csv.DictReader(f)
        ]


def pipe(nps_in: float, schedule: str) -> dict[str, Any]:
    for r in pipe_schedules():
        if r["nps_in"] == nps_in and r["schedule"] == schedule:
            return r
    raise KeyError(f"no pipe NPS {nps_in} SCH {schedule}")


@cache
def flange_ratings() -> list[dict[str, Any]]:
    """Rows: material_group, class, temp_F, max_pressure_psig (ASME B16.5)."""
    with (DATA_DIR / "flanges_b165.csv").open() as f:
        return [
            {
                "material_group": r["material_group"],
                "class": int(r["class"]),
                "temp_F": float(r["temp_F"]),
                "max_pressure_psig": float(r["max_pressure_psig"]),
            }
            for r in csv.DictReader(f)
        ]


def golden(name: str) -> list[dict[str, Any]]:
    """Golden test cases from data/golden/<name>.yaml."""
    raw = yaml.safe_load((DATA_DIR / "golden" / f"{name}.yaml").read_text())
    cases: list[dict[str, Any]] = raw["cases"]
    return cases
