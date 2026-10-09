"""Shared primitives. LOCKED: agents must not edit contracts/.

Unit convention (internal, everywhere): SI.
  temperature K, pressure Pa (absolute), molar flow mol/s, mass flow kg/s,
  energy J, power W, length m (piping geometry mm, see piping.py),
  density kg/m3, viscosity Pa.s, enthalpy J/mol, entropy J/(mol.K).
Convert only at the edges (input parsing, drawings, reports).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

TAG_RE = re.compile(r"^[A-Z]{1,3}-\d{3,4}[A-Z]?$")  # V-101, K-201A, PSV-1001


class Model(BaseModel):
    """Base for all contract models: strict, immutable-ish, no stray fields."""

    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)


class Tag(str):
    """Equipment / item tag, e.g. V-101."""


def check_tag(v: str) -> str:
    if not TAG_RE.match(v):
        raise ValueError(f"bad tag {v!r}; expected like V-101, K-201A")
    return v


class Vec3(Model):
    """3D vector / point. Piping geometry uses millimetres."""

    x: float
    y: float  # north
    z: float  # up (elevation)


class Direction(StrEnum):
    E = "E"
    W = "W"
    N = "N"
    S = "S"
    UP = "UP"
    DOWN = "DOWN"


class Nozzle(Model):
    """A connection point on equipment. Position is relative to the equipment origin (mm)."""

    id: str  # N1, N2 ... unique per equipment
    service: str  # "inlet", "gas_out", "liquid_out", "psv", "drain", ...
    port: str | None = None  # simulation port this nozzle serves, if any
    nps_in: float
    flange_class: int
    position_mm: Vec3
    facing: Direction

    @field_validator("flange_class")
    @classmethod
    def _cls(cls, v: int) -> int:
        if v not in (150, 300, 600, 900, 1500, 2500):
            raise ValueError(f"flange class {v} not in B16.5 set")
        return v
