"""P&ID model: full connectivity, valves, instruments. No geometry. LOCKED."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import field_validator, model_validator

from .common import Model, Nozzle

# 6"-PG-1001-B1  -> size, fluid code, sequence, pipe class
LINE_NO_RE = re.compile(r'^(\d+(\.\d+)?|\d+/\d+)"-[A-Z]{1,3}-\d{4}-[A-Z]\d$')
# ISA S5.1: first letters + loop number, e.g. PT-1001, LSHH-1002, PSV-1003
INSTR_TAG_RE = re.compile(r"^[A-Z]{2,5}-\d{4}[A-Z]?$")


class ValveType(StrEnum):
    GATE = "gate"
    GLOBE = "globe"
    BALL = "ball"
    PLUG = "plug"
    BUTTERFLY = "butterfly"
    CHECK_SWING = "check_swing"
    CHECK_PISTON = "check_piston"
    CHECK_DUAL_PLATE = "check_dual_plate"
    CONTROL = "control"
    PSV = "psv"
    RUPTURE_DISC = "rupture_disc"
    ESD = "esd"  # SDV / XV
    BLOWDOWN = "blowdown"  # BDV
    NEEDLE = "needle"


class FailPosition(StrEnum):
    FO = "fail_open"
    FC = "fail_closed"
    FL = "fail_last"
    NA = "n/a"


class InlineKind(StrEnum):
    """Items that sit in a line, in flow order."""

    VALVE = "valve"
    REDUCER_CONC = "reducer_concentric"
    REDUCER_ECC = "reducer_eccentric"
    STRAINER = "strainer"
    SPEC_BREAK = "spec_break"
    ORIFICE = "orifice"
    BLIND = "spectacle_blind"
    INSTRUMENT_TAP = "instrument_tap"
    DRAIN = "drain"
    VENT = "vent"


class InlineItem(Model):
    kind: InlineKind
    ref: str | None = None  # valve tag or instrument tag this item refers to
    nps_in: float | None = None  # for reducers: downstream size
    note: str = ""


class Valve(Model):
    tag: str  # e.g. HV-1001, PV-1002, PSV-1003, XV-1004
    type: ValveType
    nps_in: float
    flange_class: int
    fail_position: FailPosition = FailPosition.NA
    set_pressure_Pa: float | None = None  # PSV only
    cv: float | None = None  # control valves


class Instrument(Model):
    tag: str
    function: str  # "PT", "LSHH", "PIC" ...
    loop: int
    connected_to: str  # equipment tag or line number
    controls: str | None = None  # valve tag for controllers

    @field_validator("tag")
    @classmethod
    def _tag(cls, v: str) -> str:
        if not INSTR_TAG_RE.match(v):
            raise ValueError(f"bad instrument tag {v!r}")
        return v


class PidEquipment(Model):
    tag: str
    kind: str
    nozzles: list[Nozzle]
    design_pressure_Pa: float
    design_temperature_K: float


class LineEnd(Model):
    equipment: str | None = None  # equipment tag
    nozzle: str | None = None  # nozzle id
    line: str | None = None  # or tie-in to another line number
    boundary: str | None = None  # or battery limit label


class PidLine(Model):
    number: str  # LINE_NO_RE
    stream_id: str | None = None  # sim stream this line carries
    nps_in: float
    fluid_code: str  # PG, PL, W, FG, FL ...
    pipe_class: str  # key in data/pipe_classes.yaml
    design_pressure_Pa: float
    design_temperature_K: float
    start: LineEnd
    end: LineEnd
    items: list[InlineItem] = []  # in flow order

    @field_validator("number")
    @classmethod
    def _num(cls, v: str) -> str:
        if not LINE_NO_RE.match(v):
            raise ValueError(f'bad line number {v!r}; expected like 6"-PG-1001-B1')
        return v


class PID(Model):
    equipment: list[PidEquipment]
    lines: list[PidLine]
    valves: list[Valve]
    instruments: list[Instrument]

    @model_validator(mode="after")
    def _unique(self) -> PID:
        for name, items in (
            ("line number", [ln.number for ln in self.lines]),
            ("valve tag", [v.tag for v in self.valves]),
            ("instrument tag", [i.tag for i in self.instruments]),
            ("equipment tag", [e.tag for e in self.equipment]),
        ):
            if len(items) != len(set(items)):
                raise ValueError(f"duplicate {name}")
        valve_tags = {v.tag for v in self.valves}
        for ln in self.lines:
            for it in ln.items:
                if it.kind == InlineKind.VALVE and it.ref not in valve_tags:
                    raise ValueError(f"line {ln.number} references unknown valve {it.ref}")
        return self


class RuleViolation(Model):
    rule: str
    target: str  # tag or line number
    message: str
