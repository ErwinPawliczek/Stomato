"""Shared primitives. LOCKED: agents must not edit contracts/.

Unit convention (internal, everywhere): SI.
  temperature K, pressure Pa (absolute), molar flow mol/s, mass flow kg/s,
  energy J, power W, length m (piping geometry mm, see piping.py),
  density kg/m3, viscosity Pa.s, enthalpy J/mol, entropy J/(mol.K).
Convert only at the edges (input parsing, drawings, reports).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_serializer

TAG_RE = re.compile(r"^[A-Z]{1,3}-\d{3,4}[A-Z]?$")  # V-101, K-201A, PSV-1001


class Model(BaseModel):
    """Base for all contract models: strict, immutable-ish, no stray fields."""

    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)


class DeferredModel(Model):
    """A Model some of whose fields may be computed on first read.

    Built through :meth:`deferred`, a named field holds a zero-argument callable
    instead of a value until something reads it - attribute access, equality,
    iteration, repr, pickling or serialization - and then holds the callable's
    result for good. To every reader the record is indistinguishable from one
    built eagerly with the same values: same field values, same ``model_dump``
    and JSON bytes, same ``model_fields_set``. Thermo packages use it for
    transport properties (viscosity, thermal conductivity) that most callers -
    column stage loops above all - never read.

    The callable must return a value already valid for the field's type; it is
    not re-validated.
    """

    _pending: dict[str, Callable[[], Any]] = PrivateAttr(default_factory=dict)

    @classmethod
    def deferred(cls, deferred: Mapping[str, Callable[[], Any]], /, **values: Any) -> Self:
        """Build with ``values`` now and the ``deferred`` fields on first read.

        Each deferred field must be an optional field (it is validated as None
        at construction, so ``model_fields_set`` matches an eager build).
        """
        unknown = [name for name in deferred if name not in cls.model_fields]
        if unknown:
            raise ValueError(f"{cls.__name__} has no field(s) {unknown}")
        obj = cls(**values, **dict.fromkeys(deferred))
        pending = obj._pending_map()
        for name, thunk in deferred.items():
            del obj.__dict__[name]
            pending[name] = thunk
        return obj

    def _pending_map(self) -> dict[str, Callable[[], Any]]:
        private = object.__getattribute__(self, "__pydantic_private__")
        return private["_pending"]  # type: ignore[no-any-return]

    def _store(self, name: str, value: Any) -> None:
        """Set a resolved field, keeping ``__dict__`` in declaration order (dump key order)."""
        fields = self.__dict__
        fields[name] = value
        ordered = {key: fields[key] for key in type(self).model_fields if key in fields}
        fields.clear()
        fields.update(ordered)

    def _resolve(self) -> None:
        """Compute every still-deferred field."""
        pending = self._pending_map()
        for name in list(pending):
            thunk = pending.pop(name)
            if name not in self.__dict__:
                self._store(name, thunk())

    if not TYPE_CHECKING:  # keep mypy's attribute checking on the declared fields

        def __getattr__(self, name: str) -> Any:
            try:
                private = object.__getattribute__(self, "__pydantic_private__")
            except AttributeError:
                private = None
            pending = private.get("_pending") if private else None
            if pending and name in pending:
                value = pending.pop(name)()
                self._store(name, value)
                return value
            return super().__getattr__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in type(self).model_fields:
            self._resolve()
        super().__setattr__(name, value)

    if not TYPE_CHECKING:
        # No return annotation on purpose: pydantic would take it as the
        # serialization JSON schema (an annotated ``Any`` erases the model's
        # schema from openapi.json); unannotated, the model's own schema stands.
        @model_serializer(mode="wrap")
        def _serialize_resolved(self, handler):
            self._resolve()
            return handler(self)

    def __eq__(self, other: object) -> bool:
        self._resolve()
        if isinstance(other, DeferredModel):
            other._resolve()
        return super().__eq__(other)

    def __iter__(self) -> Iterator[tuple[str, Any]]:  # type: ignore[override]
        self._resolve()
        return super().__iter__()

    def __repr_args__(self) -> Any:
        self._resolve()
        return super().__repr_args__()

    def __copy__(self) -> Self:
        new = super().__copy__()
        # BaseModel.__copy__ shares the private dict's values; the pending map
        # must not be shared, or resolving one copy would strand the other.
        object.__getattribute__(new, "__pydantic_private__")["_pending"] = dict(self._pending_map())
        return new

    def __getstate__(self) -> dict[Any, Any]:
        self._resolve()
        return super().__getstate__()


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
