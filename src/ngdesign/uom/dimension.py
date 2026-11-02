"""Physical dimensions as exact rational exponent vectors.

A :class:`Dimension` is the exponent vector over the seven SI base dimensions.
Exponents are :class:`fractions.Fraction`, so the half-order rate constants of
chemical kinetics (``(mol/m3)^-0.5 / s``) stay exact and compare exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

_BASE = ("M", "L", "T", "Θ", "N", "I", "J")


class UomError(ValueError):
    """Base class of every unit-of-measure refusal."""


class UnknownUnitError(UomError):
    """A unit expression names something the unit table does not define."""


class DimensionError(UomError):
    """Two quantities or units with incompatible dimensions were combined."""


class OffsetUnitError(UomError):
    """An operation is meaningless on an offset scale (two absolute points added)."""


@dataclass(frozen=True, slots=True)
class Dimension:
    """Exponents of (mass, length, time, temperature, amount, current, luminosity)."""

    exponents: tuple[Fraction, ...] = (Fraction(0),) * 7

    def __mul__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a + b for a, b in zip(self.exponents, other.exponents, strict=True)))

    def __truediv__(self, other: Dimension) -> Dimension:
        return Dimension(tuple(a - b for a, b in zip(self.exponents, other.exponents, strict=True)))

    def __pow__(self, power: int | float | Fraction) -> Dimension:
        exact = Fraction(power).limit_denominator(1000)
        return Dimension(tuple(a * exact for a in self.exponents))

    @property
    def dimensionless(self) -> bool:
        return all(e == 0 for e in self.exponents)

    def __str__(self) -> str:
        parts = [f"{sym}^{e}" if e != 1 else sym for sym, e in zip(_BASE, self.exponents, strict=True) if e]
        return "·".join(parts) if parts else "1"


def _dim(M: int = 0, L: int = 0, T: int = 0, Th: int = 0, N: int = 0, Cur: int = 0, J: int = 0) -> Dimension:
    return Dimension(tuple(Fraction(e) for e in (M, L, T, Th, N, Cur, J)))


DIMENSIONLESS = _dim()
MASS = _dim(M=1)
LENGTH = _dim(L=1)
TIME = _dim(T=1)
TEMPERATURE = _dim(Th=1)
AMOUNT = _dim(N=1)
CURRENT = _dim(Cur=1)
LUMINOSITY = _dim(J=1)

#: Named physical kinds -> dimension. Used by ``require``/``coerce`` and by the
#: display unit sets. Several kinds may share one dimension (energy and torque
#: do; the kind names what a value means, the dimension what it can convert to).
KINDS: dict[str, Dimension] = {
    "dimensionless": DIMENSIONLESS,
    "mass": MASS,
    "length": LENGTH,
    "time": TIME,
    "temperature": TEMPERATURE,
    "temperature_difference": TEMPERATURE,
    "amount": AMOUNT,
    "current": CURRENT,
    "luminosity": LUMINOSITY,
    "area": LENGTH**2,
    "volume": LENGTH**3,
    "velocity": LENGTH / TIME,
    "acceleration": LENGTH / TIME**2,
    "force": MASS * LENGTH / TIME**2,
    "pressure": MASS / (LENGTH * TIME**2),
    "energy": MASS * LENGTH**2 / TIME**2,
    "power": MASS * LENGTH**2 / TIME**3,
    "density": MASS / LENGTH**3,
    "molar_density": AMOUNT / LENGTH**3,
    "concentration": AMOUNT / LENGTH**3,
    "specific_volume": LENGTH**3 / MASS,
    "molar_volume": LENGTH**3 / AMOUNT,
    "molar_mass": MASS / AMOUNT,
    "mass_flow": MASS / TIME,
    "molar_flow": AMOUNT / TIME,
    "volume_flow": LENGTH**3 / TIME,
    "molar_energy": MASS * LENGTH**2 / (TIME**2 * AMOUNT),
    "specific_energy": LENGTH**2 / TIME**2,
    "molar_heat_capacity": MASS * LENGTH**2 / (TIME**2 * AMOUNT * TEMPERATURE),
    "specific_heat_capacity": LENGTH**2 / (TIME**2 * TEMPERATURE),
    "molar_entropy": MASS * LENGTH**2 / (TIME**2 * AMOUNT * TEMPERATURE),
    "dynamic_viscosity": MASS / (LENGTH * TIME),
    "kinematic_viscosity": LENGTH**2 / TIME,
    "thermal_conductivity": MASS * LENGTH / (TIME**3 * TEMPERATURE),
    "heat_transfer_coefficient": MASS / (TIME**3 * TEMPERATURE),
    "heat_flux": MASS / TIME**3,
    "surface_tension": MASS / TIME**2,
    "frequency": TIME**-1,
    "first_order_rate_constant": TIME**-1,
    "reaction_rate": AMOUNT / (LENGTH**3 * TIME),
    "voltage": MASS * LENGTH**2 / (TIME**3 * CURRENT),
    "charge": CURRENT * TIME,
}


def kind_dimension(kind: str) -> Dimension:
    """The dimension of a named kind; :class:`UomError` listing the names otherwise."""
    try:
        return KINDS[kind]
    except KeyError:
        raise UomError(f"unknown quantity kind {kind!r}; known kinds: {sorted(KINDS)}") from None
