"""Isometric drawing output. Rendered from a RoutedLine. LOCKED."""

from __future__ import annotations

from .common import Model


class BomItem(Model):
    item: int
    qty: float  # count, or metres for pipe
    unit: str  # "ea" or "m"
    nps_in: float
    description: str
    material: str


class CutPiece(Model):
    piece: int
    spool: str
    nps_in: float
    length_mm: float


class TitleBlock(Model):
    line_number: str
    pipe_class: str
    design_pressure_kPag: float
    design_temperature_C: float
    test_pressure_kPag: float
    insulation: str = "none"
    sheet: str = "1 of 1"


class IsoSheet(Model):
    title: TitleBlock
    svg: str  # complete <svg> document
    bom: list[BomItem]
    cut_list: list[CutPiece]
    weld_count: int
    total_pipe_length_mm: float  # must equal the sum of PIPE components in the RoutedLine


class Isometric(Model):
    sheets: list[IsoSheet]
