"""Quantities: a magnitude held in SI, with its dimension and a display unit.

Holding SI means arithmetic never touches conversion factors, so the classic
offset-unit traps (doubling 20 °C) resolve themselves: a temperature read in
degC *is* its kelvin value. What still needs a rule is scale logic, so a value
entered on an offset scale is marked a **point**: two points cannot be added,
their difference is an interval, and a point plus an interval is a point.

Molar and mass bases differ by a molar mass, and a volume and a mass by a
density. Neither is a unit conversion, so neither happens silently: pass ``mw=``
or ``rho=`` to :func:`convert` / :meth:`Quantity.to` and the conversion is
carried out and dimension-checked.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from fractions import Fraction
from functools import wraps
from typing import Any, TypeVar, cast

import numpy as np
from numpy.typing import NDArray

from .dimension import (
    AMOUNT,
    DIMENSIONLESS,
    LENGTH,
    MASS,
    Dimension,
    DimensionError,
    OffsetUnitError,
    UomError,
    kind_dimension,
)
from .units import Unit, parse_unit

Magnitude = float | NDArray[np.float64]

_LEADING_NUMBER = re.compile(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$", re.DOTALL)
_MOLAR_MASS = MASS / AMOUNT
_DENSITY = MASS / LENGTH**3


def _as_magnitude(value: Any) -> Magnitude:
    if isinstance(value, np.ndarray | list | tuple):
        return np.asarray(value, dtype=float)
    return float(value)


class Quantity:
    """An immutable magnitude + dimension, displayed in ``unit``.

    ``Quantity(25, "degC")``, ``Quantity("500 psia")``, ``Quantity([1, 2], "m/s")``.
    """

    __slots__ = ("si", "dimension", "unit", "is_point", "is_interval")
    __array_ufunc__ = None  # ndarray * Quantity defers to __rmul__

    si: Magnitude
    dimension: Dimension
    unit: str
    is_point: bool
    is_interval: bool  # a known difference: it has no reading on an offset scale

    def __init__(self, value: Any, unit: str | None = None) -> None:
        if isinstance(value, str):
            if unit is not None:
                raise UomError("give the unit inside the string or as an argument, not both")
            match = _LEADING_NUMBER.match(value)
            if match is None:
                raise UomError(f"cannot read a quantity from {value!r}")
            value, unit = float(match.group(1)), match.group(2).strip()
        parsed = parse_unit(unit or "")
        magnitude = _as_magnitude(value)
        object.__setattr__(self, "si", magnitude * parsed.factor + parsed.offset)
        object.__setattr__(self, "dimension", parsed.dimension)
        object.__setattr__(self, "unit", parsed.symbol)
        object.__setattr__(self, "is_point", parsed.is_offset)
        object.__setattr__(self, "is_interval", parsed.symbol.startswith("delta_"))

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Quantity is immutable")

    @classmethod
    def _make(
        cls, si: Magnitude, dimension: Dimension, unit: str = "", point: bool = False, interval: bool = False
    ) -> Quantity:
        out = cls.__new__(cls)
        object.__setattr__(out, "si", si)
        object.__setattr__(out, "dimension", dimension)
        object.__setattr__(out, "unit", unit)
        object.__setattr__(out, "is_point", point)
        object.__setattr__(out, "is_interval", interval)
        return out

    @classmethod
    def from_si(cls, si: Any, kind_or_unit: str | Dimension) -> Quantity:
        """Wrap an SI magnitude (an engine output) with a kind name or a dimension."""
        dimension = kind_or_unit if isinstance(kind_or_unit, Dimension) else kind_dimension(kind_or_unit)
        return cls._make(_as_magnitude(si), dimension)

    # --------------------------------------------------------------- conversion
    def magnitude(self, unit: str | None = None) -> Magnitude:
        """The value in ``unit`` (default: the display unit, or SI when there is none)."""
        target = unit if unit is not None else self.unit
        if not target:
            return self.si
        parsed = parse_unit(target)
        self._check(parsed.dimension, f"cannot express {self.si!r} (SI) in {target!r}")
        self._refuse_interval_on_scale(parsed, target)
        return (self.si - parsed.offset) / parsed.factor

    def to(self, unit: str, *, mw: Any = None, rho: Any = None) -> Quantity:
        """The same physical value displayed in ``unit`` (see :func:`convert` for mw/rho)."""
        parsed = parse_unit(unit)
        self._refuse_interval_on_scale(parsed, unit)
        si = _rebased(self.si, self.dimension, parsed.dimension, mw, rho)
        return Quantity._make(si, parsed.dimension, parsed.symbol, parsed.is_offset, self.is_interval)

    def _refuse_interval_on_scale(self, target: Unit, name: str) -> None:
        if self.is_interval and target.is_offset:
            raise OffsetUnitError(f"a difference has no reading on the {name!r} scale; use delta_ units or K")

    def require(self, kind: str) -> Quantity:
        """Self, or :class:`DimensionError` when the dimension is not that of ``kind``."""
        self._check(kind_dimension(kind), f"{self} is not a {kind}")
        return self

    def _check(self, dimension: Dimension, message: str) -> None:
        if self.dimension != dimension:
            raise DimensionError(f"{message} (dimension {self.dimension}, expected {dimension})")

    # --------------------------------------------------------------- arithmetic
    def _same(self, other: Any, op: str) -> Quantity:
        rhs = _coerce_operand(other)
        if rhs.dimension != self.dimension:
            raise DimensionError(f"cannot {op} {self} and {rhs}: dimensions differ")
        return rhs

    def __add__(self, other: Any) -> Quantity:
        rhs = self._same(other, "add")
        if self.is_point and rhs.is_point:
            raise OffsetUnitError(f"cannot add two points on an offset scale: {self} + {rhs}")
        return Quantity._make(
            self.si + rhs.si, self.dimension, self.unit or rhs.unit, self.is_point or rhs.is_point
        )

    __radd__ = __add__

    def __sub__(self, other: Any) -> Quantity:
        rhs = self._same(other, "subtract")
        if rhs.is_point and not self.is_point:
            raise OffsetUnitError(f"cannot subtract a point from an interval: {self} - {rhs}")
        point = self.is_point and not rhs.is_point
        return Quantity._make(self.si - rhs.si, self.dimension, "", point, self.is_point and rhs.is_point)

    def __rsub__(self, other: Any) -> Quantity:
        return _coerce_operand(other) - self

    def __mul__(self, other: Any) -> Quantity:
        rhs = _coerce_operand(other)
        return Quantity._make(self.si * rhs.si, self.dimension * rhs.dimension)

    __rmul__ = __mul__

    def __truediv__(self, other: Any) -> Quantity:
        rhs = _coerce_operand(other)
        return Quantity._make(self.si / rhs.si, self.dimension / rhs.dimension)

    def __rtruediv__(self, other: Any) -> Quantity:
        return _coerce_operand(other) / self

    def __pow__(self, power: int | float | Fraction) -> Quantity:
        return Quantity._make(self.si ** float(power), self.dimension**power)

    def __neg__(self) -> Quantity:
        return Quantity._make(-self.si, self.dimension, self.unit)

    def __abs__(self) -> Quantity:
        return Quantity._make(np.abs(self.si), self.dimension, self.unit)

    def __float__(self) -> float:
        if self.dimension != DIMENSIONLESS:
            raise DimensionError(f"{self} is not dimensionless; use .magnitude(unit)")
        return float(cast(float, self.si))

    def sqrt(self) -> Quantity:
        return self ** Fraction(1, 2)

    # --------------------------------------------------------------- comparison
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        return self.dimension == other.dimension and bool(np.all(self.si == other.si))

    def __hash__(self) -> int:
        return hash((self.dimension, float(np.sum(self.si))))

    def __lt__(self, other: Any) -> bool:
        return bool(np.all(self.si < self._same(other, "compare").si))

    def __le__(self, other: Any) -> bool:
        return bool(np.all(self.si <= self._same(other, "compare").si))

    def __gt__(self, other: Any) -> bool:
        return bool(np.all(self.si > self._same(other, "compare").si))

    def __ge__(self, other: Any) -> bool:
        return bool(np.all(self.si >= self._same(other, "compare").si))

    def isclose(self, other: Any, rel_tol: float = 1e-9) -> bool:
        """True when both are the same dimension and within ``rel_tol`` of each other."""
        rhs = self._same(other, "compare")
        return math.isclose(float(cast(float, self.si)), float(cast(float, rhs.si)), rel_tol=rel_tol)

    def __repr__(self) -> str:
        return f"<Quantity {self}>"

    def __str__(self) -> str:
        if self.unit:
            return f"{self.magnitude()} {self.unit}"
        return f"{self.si} [{self.dimension}] (SI)"

    def __format__(self, spec: str) -> str:
        if not spec:
            return str(self)
        value = self.magnitude()
        return f"{format(value, spec)} {self.unit}".rstrip()


def _coerce_operand(value: Any) -> Quantity:
    if isinstance(value, Quantity):
        return value
    if isinstance(value, int | float | np.ndarray | np.floating | list | tuple):
        return Quantity._make(_as_magnitude(value), DIMENSIONLESS)
    raise TypeError(f"cannot combine a Quantity with {type(value).__name__}")


def Q(value: Any, unit: str | None = None) -> Quantity:  # noqa: N802 -- the conventional short name
    """Shorthand constructor: ``Q(25, "degC")`` or ``Q("500 psia")``."""
    return Quantity(value, unit)


def _molar_mass_si(mw: Any) -> float:
    """Molar mass as kg/mol: a Quantity, or a bare number in g/mol (``Component.mw``)."""
    if isinstance(mw, Quantity):
        return float(cast(float, mw.require("molar_mass").si))
    return float(mw) * 1e-3


def _density_si(rho: Any) -> float:
    """Density as kg/m3: a Quantity, or a bare number already in kg/m3."""
    if isinstance(rho, Quantity):
        return float(cast(float, rho.require("density").si))
    return float(rho)


def _rebased(si: Magnitude, source: Dimension, target: Dimension, mw: Any, rho: Any) -> Magnitude:
    """``si`` carried across a mass/mole or mass/volume basis change to ``target``."""
    if source == target:
        return si
    ratio = target / source
    for carrier, supplied, label, keyword in (
        (_MOLAR_MASS, mw, "molar mass", "mw"),
        (_DENSITY, rho, "density", "rho"),
    ):
        for power in (Fraction(1), Fraction(-1)):
            if ratio == carrier**power:
                if supplied is None:
                    raise DimensionError(f"converting {source} to {target} needs a {label}: pass {keyword}=")
                value = _molar_mass_si(supplied) if keyword == "mw" else _density_si(supplied)
                return cast(Magnitude, si * value ** float(power))
    if mw is not None and rho is not None:
        # amount <-> volume bases need both: multiply by (M/ρ)^±1
        volume_per_mol = _molar_mass_si(mw) / _density_si(rho)
        carrier = LENGTH**3 / AMOUNT
        for power in (Fraction(1), Fraction(-1)):
            if ratio == carrier**power:
                return cast(Magnitude, si * volume_per_mol ** float(power))
    raise DimensionError(f"cannot convert dimension {source} to {target}")


def convert(value: Any, source: str, target: str, *, mw: Any = None, rho: Any = None) -> Any:
    """``value`` in unit ``source`` expressed in unit ``target``.

    ``mw`` (g/mol, or a Quantity) unlocks mass<->mole bases and ``rho`` (kg/m3, or
    a Quantity) mass<->volume bases; both together unlock mole<->volume.
    ``DimensionError`` for anything else.
    """
    start = Quantity(value, source)
    return start.to(target, mw=mw, rho=rho).magnitude()


def coerce(value: Any, kind: str) -> float:
    """An edge value as an SI float, dimension-checked against ``kind``.

    Accepts a :class:`Quantity`, a string (``"25 degC"``) or a bare number, which
    the engine's convention already defines as SI.
    """
    if isinstance(value, Quantity | str):
        quantity = value if isinstance(value, Quantity) else Quantity(value)
        if kind == "temperature_difference" and quantity.is_point:
            raise OffsetUnitError(f"{quantity} is a point on a scale, not a difference; use K or delta_degC")
        return float(cast(float, quantity.require(kind).si))
    kind_dimension(kind)
    return float(value)


_R = TypeVar("_R")


def si_arguments(**kinds: str) -> Callable[[Callable[..., _R]], Callable[..., _R]]:
    """Decorator: coerce the named keyword/positional arguments to SI floats.

    ``@si_arguments(T="temperature", P="pressure")`` lets a pure SI function take
    ``"25 degC"`` or ``Q(1, "atm")`` at the edge and rejects a wrong dimension
    there, while the body stays plain SI. The wrapped signature is deliberately
    ``Callable[..., R]``: the checks those arguments get are dimensional, at run
    time, which a static ``float`` annotation could not describe.
    """

    def decorate(function: Callable[..., _R]) -> Callable[..., _R]:
        names = function.__code__.co_varnames[: function.__code__.co_argcount]

        @wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> _R:
            bound = list(args)
            for index, name in enumerate(names[: len(bound)]):
                if name in kinds and bound[index] is not None:
                    bound[index] = coerce(bound[index], kinds[name])
            for name, value in kwargs.items():
                if name in kinds and value is not None:
                    kwargs[name] = coerce(value, kinds[name])
            return function(*bound, **kwargs)

        return wrapper

    return decorate


__all__ = ["Q", "Quantity", "Unit", "coerce", "convert", "si_arguments"]
