"""Project = the single source of truth. Every view is derived from it. LOCKED."""

from __future__ import annotations

from .common import Model, Vec3
from .flowsheet import Flowsheet


class XY(Model):
    x: float
    y: float


class Layout(Model):
    """User placements per view, keyed by tag. A missing tag means: auto-layout decides."""

    pfd: dict[str, XY] = {}
    pid: dict[str, XY] = {}
    plot: dict[str, Vec3] = {}  # plot plan, mm; drives 3D routing and isometrics


class Project(Model):
    name: str
    flowsheet: Flowsheet
    layout: Layout = Layout()
