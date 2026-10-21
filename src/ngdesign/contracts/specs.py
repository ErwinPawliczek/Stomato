"""Flowsheet-level design specs (spec P2-01): pure contract data + address syntax.

A :class:`DesignSpec` names a design question - "set K-101 discharge pressure so
the TEG contactor outlet water content is 7 lb/MMscf": ``target`` is any readable
address (resolved against a solved flowsheet), ``manipulated`` any writable one
(assigned on the unsolved flowsheet), with bounds and a relative tolerance; the
solver's outer loop (``ngdesign.solver.design_specs``) drives the sequential-
modular solve to the target. A :class:`DesignSpecResult` records one spec's
outcome. Pure data: frozen models plus the address-syntax checks the flowsheet
validator runs; resolution and assignment semantics live in
``ngdesign.variables`` (the contracts layer cannot import it).
"""

from __future__ import annotations

from pydantic import field_validator, model_validator

from .common import Model

#: Fields readable on a stream state (``x`` needs a component id argument).
READ_STREAM_FIELDS = ("T", "P", "molar_flow", "mass_flow", "vapor_fraction", "x")

#: Fields readable on a unit result (``info`` needs a key argument).
READ_UNIT_FIELDS = ("duty_W", "power_W", "info")

#: Fields writable on a unit (only ``params``: unit results are solve outputs).
WRITE_UNIT_FIELDS = ("params",)

#: Fields writable on a boundary feed (``composition`` needs a component id).
WRITE_FEED_FIELDS = ("T", "P", "molar_flow", "composition")


class DesignSpec(Model):
    """One design specification: drive ``target`` to ``value`` via ``manipulated``.

    ``target`` and ``manipulated`` are variable addresses (grammar in
    ``ngdesign.variables``); the flowsheet validator checks they parse and that
    their heads name a stream or unit of the sheet. ``tolerance`` is relative on
    the target: converged when ``|achieved - value| <= tolerance * |value|``.
    """

    id: str  # unique within the flowsheet, e.g. "DS-001"
    target: str  # readable address, e.g. "S-005.x.H2O"
    value: float  # the target value (SI)
    manipulated: str  # writable address, e.g. "K-101.params.P_out"
    lower: float  # lower bound on the manipulated variable
    upper: float  # upper bound on the manipulated variable
    tolerance: float = 1e-4  # relative on the target
    max_iterations: int = 30  # outer iterations (one inner solve each)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("design spec id must not be empty")
        return v

    @model_validator(mode="after")
    def _bounds(self) -> DesignSpec:
        if not self.lower < self.upper:
            raise ValueError(f"design spec {self.id!r}: lower {self.lower} must be < upper {self.upper}")
        if not self.tolerance > 0.0:
            raise ValueError(f"design spec {self.id!r}: tolerance must be positive")
        if self.max_iterations < 1:
            raise ValueError(f"design spec {self.id!r}: max_iterations must be >= 1")
        return self


class DesignSpecResult(Model):
    """One design spec's outcome after the outer loop (spec P2-01).

    ``history`` holds one ``(manipulated, achieved)`` pair per outer iteration
    that produced a solvable flowsheet. On convergence ``achieved`` is the last
    iteration's value; otherwise it is the closest value any iteration reached
    (with ``manipulated_value`` the manipulated variable that produced it). A
    spec aborted by a failed inner solve has ``converged=False``; if no
    iteration ever solved, ``achieved`` and ``manipulated_value`` are NaN.
    """

    id: str  # the DesignSpec it answers
    achieved: float  # target value reached
    manipulated_value: float  # manipulated variable at that point
    iterations: int  # outer iterations recorded (len(history))
    converged: bool
    history: list[tuple[float, float]]  # (manipulated, target) per iteration


def check_read_address(addr: str, *, head_is_stream: bool) -> None:
    """Raise ValueError unless ``addr`` parses as a read address of the given head kind.

    Stream heads read ``<id>.<field>`` / ``<id>.x.<cid>``; unit heads read
    ``<tag>.<field>`` / ``<tag>.info.<key>``. Whether the head names an existing
    stream or unit is the caller's check (the flowsheet validator knows).
    """
    parts = addr.split(".")
    if len(parts) < 2:
        raise ValueError(f"bad read address {addr!r}: expected '<head>.<field>'")
    field, rest = parts[1], parts[2:]
    if head_is_stream:
        if field == "x":
            if len(rest) != 1:
                raise ValueError(f"bad read address {addr!r}: 'x' needs a component id")
            return
        if field in READ_STREAM_FIELDS and not rest:
            return
        raise ValueError(
            f"bad read address {addr!r}: stream fields are {sorted(READ_STREAM_FIELDS)} and x.<cid>"
        )
    if field == "info":
        if len(rest) != 1:
            raise ValueError(f"bad read address {addr!r}: 'info' needs a key")
        return
    if field in READ_UNIT_FIELDS and not rest:
        return
    raise ValueError(f"bad read address {addr!r}: unit fields are {sorted(READ_UNIT_FIELDS)} and info.<key>")


def check_write_address(addr: str, *, head_is_stream: bool) -> None:
    """Raise ValueError unless ``addr`` parses as a write address of the given head kind.

    Unit heads write ``<tag>.params.<key>``; stream heads write boundary feed
    fields ``<id>.feed.<T|P|molar_flow>`` and ``<id>.feed.composition.<cid>``.
    Whether the head names an existing unit or feed stream is the caller's check.
    """
    parts = addr.split(".")
    if head_is_stream:
        if len(parts) == 3 and parts[1] == "feed" and parts[2] in WRITE_FEED_FIELDS:
            return
        if len(parts) == 4 and parts[1] == "feed" and parts[2] == "composition":
            return
        raise ValueError(
            f"bad write address {addr!r}: stream writes look like "
            f"'<id>.feed.<{'|'.join(WRITE_FEED_FIELDS)}>' with composition taking a component id"
        )
    if len(parts) == 3 and parts[1] in WRITE_UNIT_FIELDS:
        return
    raise ValueError(f"bad write address {addr!r}: unit writes look like '<tag>.params.<key>'")
