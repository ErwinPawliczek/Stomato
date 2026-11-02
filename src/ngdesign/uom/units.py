"""Unit table and unit-expression parser.

Conversion factors come from ``scipy.constants`` (CODATA 2018 and the exact
definitions tabulated in NIST SP 811 Appendix B) wherever it defines them, so
none are retyped here; the few the library lacks are derived on the line that
defines them, with the definition stated. A unit converts to SI as
``si = value * factor + offset``.

Grammar of a unit expression::

    expr   := group (('*' | '/') group)*
    group  := term ((' ' | '-' | '·') term)*
    term   := '(' expr ')' power? | name power? | number
    power  := ('^' | '**') signed-number | signed-integer-suffix | superscript

so ``J/(mol K)``, ``J/mol/K``, ``kg·m/s²``, ``m3/h``, ``mol L-1 s-1`` and
``Btu/lb-degF`` all parse. Four decisions worth stating:

- **A space, hyphen or middle dot binds tighter than ``/``**, as engineers read it:
  ``Btu/lb-degF``, ``W/m2 K`` and ``J/kg·K`` keep everything after the slash in the
  denominator. ``*`` before a ``/`` is fine, but after one it is refused: it means
  opposite things in code and in print.
- **Offset scales** (``degC``, ``degF``, ``barg``, ``psig``) are points on a
  shifted scale only when they stand alone. Inside a compound they mean an
  interval, which is the only meaning a compound can have: ``Btu/lb-degF`` is a
  heat capacity and ``degC/min`` a ramp rate.
- **Ambiguous bare symbols are refused.** ``F`` (farad or Fahrenheit) and ``C``
  (coulomb or Celsius) raise and name the spellings to use.
- **Standard gas volumes are amounts.** ``Nm3``, ``Sm3`` and ``scf`` are ideal-gas
  mole counts at their stated reference state, so ``MMSCFD`` is a molar flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

import scipy.constants as sc

from .dimension import (
    AMOUNT,
    CURRENT,
    DIMENSIONLESS,
    LENGTH,
    MASS,
    TEMPERATURE,
    TIME,
    Dimension,
    UnknownUnitError,
)


@dataclass(frozen=True, slots=True)
class Unit:
    """A linear or affine map to SI: ``si = value * factor + offset``."""

    factor: float
    dimension: Dimension
    offset: float = 0.0
    symbol: str = ""

    @property
    def is_offset(self) -> bool:
        return self.offset != 0.0

    def __mul__(self, other: Unit) -> Unit:
        return Unit(self.factor * other.factor, self.dimension * other.dimension)

    def __truediv__(self, other: Unit) -> Unit:
        return Unit(self.factor / other.factor, self.dimension / other.dimension)

    def __pow__(self, power: Fraction) -> Unit:
        return Unit(self.factor ** float(power), self.dimension**power)


#: Force, pressure, energy and power expressed through base dimensions.
_FORCE = MASS * LENGTH / TIME**2
_PRESSURE = _FORCE / LENGTH**2
_ENERGY = _FORCE * LENGTH
_POWER = _ENERGY / TIME
_VOLTAGE = _POWER / CURRENT
_VISCOSITY = _PRESSURE * TIME

#: Reference conditions of the standard gas volumes (T in K, P in Pa).
#: ``Nm3``: 0 °C, 1 atm (DIN 1343). ``Sm3``: 15 °C, 1 atm (ISO 13443).
#: ``scf``: 60 °F, 14.696 psia (GPA 2172 / gas-industry convention).
NORMAL_REF = (sc.zero_Celsius, sc.atm)
STANDARD_REF = (sc.zero_Celsius + 15.0, sc.atm)
SCF_REF = ((60.0 + 459.67) * 5.0 / 9.0, 14.696 * sc.psi)


def _ideal_gas_moles(volume_m3: float, reference: tuple[float, float]) -> float:
    """n = P·V/(R·T) at the reference state: a standard volume as an amount."""
    T, P = reference
    return float(P * volume_m3 / (sc.R * T))


_CUBIC_FOOT = sc.foot**3
_SCF_MOL = _ideal_gas_moles(_CUBIC_FOOT, SCF_REF)
_ONE_G_PER_MOL_LBMOL = sc.lb * 1000.0  # mol per lbmol: pound-mole = 453.59237 mol

#: Prefixable SI-style units (symbol -> Unit); every SI prefix applies to these.
_PREFIXABLE: dict[str, Unit] = {
    "g": Unit(1e-3, MASS),
    "m": Unit(1.0, LENGTH),
    "s": Unit(1.0, TIME),
    "mol": Unit(1.0, AMOUNT),
    "K": Unit(1.0, TEMPERATURE),
    "A": Unit(1.0, CURRENT),
    "N": Unit(1.0, _FORCE),
    "Pa": Unit(1.0, _PRESSURE),
    "J": Unit(1.0, _ENERGY),
    "W": Unit(1.0, _POWER),
    "V": Unit(1.0, _VOLTAGE),
    "Hz": Unit(1.0, TIME**-1),
    "L": Unit(sc.liter, LENGTH**3),
    "l": Unit(sc.liter, LENGTH**3),
    "bar": Unit(sc.bar, _PRESSURE),
    "cal": Unit(sc.calorie, _ENERGY),
    "P": Unit(0.1, _VISCOSITY),  # poise = 1 dyn·s/cm2 = 0.1 Pa·s
    "St": Unit(1e-4, LENGTH**2 / TIME),  # stokes = 1 cm2/s
    "M": Unit(1000.0, AMOUNT / LENGTH**3),  # molar = mol/L
    "eV": Unit(sc.eV, _ENERGY),
}

_PREFIXES: dict[str, float] = {
    "Y": 1e24,
    "Z": 1e21,
    "E": 1e18,
    "P": 1e15,
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "h": 1e2,
    "da": 1e1,
    "d": 1e-1,
    "c": 1e-2,
    "m": 1e-3,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
    "f": 1e-15,
}

#: Whole units, looked up before any prefix is tried (so ``min`` is never milli-inch).
_NAMED: dict[str, Unit] = {
    # dimensionless
    "1": Unit(1.0, DIMENSIONLESS),
    "percent": Unit(0.01, DIMENSIONLESS),
    "%": Unit(0.01, DIMENSIONLESS),
    "ppm": Unit(1e-6, DIMENSIONLESS),
    "ppmv": Unit(1e-6, DIMENSIONLESS),
    "ppmw": Unit(1e-6, DIMENSIONLESS),
    "ppb": Unit(1e-9, DIMENSIONLESS),
    "rad": Unit(1.0, DIMENSIONLESS),
    "deg": Unit(sc.degree, DIMENSIONLESS),
    # mass
    "lb": Unit(sc.lb, MASS),
    "lbm": Unit(sc.lb, MASS),
    "oz": Unit(sc.oz, MASS),
    "ton": Unit(sc.short_ton, MASS),
    "short_ton": Unit(sc.short_ton, MASS),
    "long_ton": Unit(sc.long_ton, MASS),
    "tonne": Unit(1000.0, MASS),
    "t": Unit(1000.0, MASS),
    "kt": Unit(1e6, MASS),
    "Mt": Unit(1e9, MASS),
    "slug": Unit(sc.lbf / (sc.foot), MASS),  # 1 lbf·s²/ft
    # length, area, volume
    "in": Unit(sc.inch, LENGTH),
    "ft": Unit(sc.foot, LENGTH),
    "yd": Unit(sc.yard, LENGTH),
    "mi": Unit(sc.mile, LENGTH),
    "acre": Unit(sc.acre, LENGTH**2),
    "ha": Unit(sc.hectare, LENGTH**2),
    "gal": Unit(sc.gallon, LENGTH**3),
    "gal_imp": Unit(sc.gallon_imp, LENGTH**3),
    "bbl": Unit(sc.barrel, LENGTH**3),
    "cc": Unit(1e-6, LENGTH**3),
    # time
    "min": Unit(sc.minute, TIME),
    "h": Unit(sc.hour, TIME),
    "hr": Unit(sc.hour, TIME),
    "d": Unit(sc.day, TIME),
    "day": Unit(sc.day, TIME),
    "wk": Unit(sc.week, TIME),
    "yr": Unit(sc.year, TIME),
    # amount and standard gas volumes (ideal-gas amounts, see the module docstring)
    "lbmol": Unit(_ONE_G_PER_MOL_LBMOL, AMOUNT),
    "lb-mol": Unit(_ONE_G_PER_MOL_LBMOL, AMOUNT),
    "gmol": Unit(1.0, AMOUNT),
    "Nm3": Unit(_ideal_gas_moles(1.0, NORMAL_REF), AMOUNT),
    "Sm3": Unit(_ideal_gas_moles(1.0, STANDARD_REF), AMOUNT),
    "scf": Unit(_SCF_MOL, AMOUNT),
    "SCF": Unit(_SCF_MOL, AMOUNT),
    "Mscf": Unit(1e3 * _SCF_MOL, AMOUNT),
    "MMscf": Unit(1e6 * _SCF_MOL, AMOUNT),
    "MMSCF": Unit(1e6 * _SCF_MOL, AMOUNT),
    "Bscf": Unit(1e9 * _SCF_MOL, AMOUNT),
    "SCFM": Unit(_SCF_MOL / sc.minute, AMOUNT / TIME),
    "SCFH": Unit(_SCF_MOL / sc.hour, AMOUNT / TIME),
    "SCFD": Unit(_SCF_MOL / sc.day, AMOUNT / TIME),
    "MSCFD": Unit(1e3 * _SCF_MOL / sc.day, AMOUNT / TIME),
    "MMSCFD": Unit(1e6 * _SCF_MOL / sc.day, AMOUNT / TIME),
    # force, pressure
    "dyn": Unit(sc.dyn, _FORCE),
    "lbf": Unit(sc.lbf, _FORCE),
    "kgf": Unit(sc.kgf, _FORCE),
    "psi": Unit(sc.psi, _PRESSURE),
    "psia": Unit(sc.psi, _PRESSURE),
    "ksi": Unit(1e3 * sc.psi, _PRESSURE),
    "atm": Unit(sc.atm, _PRESSURE),
    "bara": Unit(sc.bar, _PRESSURE),
    "torr": Unit(sc.torr, _PRESSURE),
    "Torr": Unit(sc.torr, _PRESSURE),
    "mtorr": Unit(sc.torr / 1000.0, _PRESSURE),
    "mmHg": Unit(sc.mmHg, _PRESSURE),
    "inHg": Unit(sc.mmHg * 25.4, _PRESSURE),
    # conventional water columns: ρ = 1000 kg/m3 at standard gravity (NIST SP 811 B.8)
    "mmH2O": Unit(1000.0 * sc.g * 1e-3, _PRESSURE),
    "mH2O": Unit(1000.0 * sc.g, _PRESSURE),
    "inH2O": Unit(1000.0 * sc.g * sc.inch, _PRESSURE),
    "ftH2O": Unit(1000.0 * sc.g * sc.foot, _PRESSURE),
    # gauge pressures, referenced to one standard atmosphere
    "barg": Unit(sc.bar, _PRESSURE, sc.atm),
    "psig": Unit(sc.psi, _PRESSURE, sc.atm),
    "kPag": Unit(1e3, _PRESSURE, sc.atm),
    "MPag": Unit(1e6, _PRESSURE, sc.atm),
    # temperature: scales with an offset, and intervals without one
    "degC": Unit(1.0, TEMPERATURE, sc.zero_Celsius),
    "°C": Unit(1.0, TEMPERATURE, sc.zero_Celsius),
    "degF": Unit(5.0 / 9.0, TEMPERATURE, 459.67 * 5.0 / 9.0),
    "°F": Unit(5.0 / 9.0, TEMPERATURE, 459.67 * 5.0 / 9.0),
    "degR": Unit(5.0 / 9.0, TEMPERATURE),
    "°R": Unit(5.0 / 9.0, TEMPERATURE),
    "delta_degC": Unit(1.0, TEMPERATURE),
    "delta_degF": Unit(5.0 / 9.0, TEMPERATURE),
    # energy, power
    "Btu": Unit(sc.Btu, _ENERGY),
    "BTU": Unit(sc.Btu, _ENERGY),
    "Btu_th": Unit(sc.Btu_th, _ENERGY),
    "MMBtu": Unit(1e6 * sc.Btu, _ENERGY),
    "therm": Unit(1e5 * sc.Btu, _ENERGY),
    "erg": Unit(sc.erg, _ENERGY),
    "cal_IT": Unit(sc.calorie_IT, _ENERGY),
    "kWh": Unit(1e3 * sc.hour, _ENERGY),
    "MWh": Unit(1e6 * sc.hour, _ENERGY),
    "GWh": Unit(1e9 * sc.hour, _ENERGY),
    "hp": Unit(sc.hp, _POWER),
    "TR": Unit(12000.0 * sc.Btu / sc.hour, _POWER),  # ton of refrigeration
    # viscosity is covered by the poise/stokes prefixables
    # electricity
    "ohm": Unit(1.0, _VOLTAGE / CURRENT),
    "Ω": Unit(1.0, _VOLTAGE / CURRENT),
    "coulomb": Unit(1.0, CURRENT * TIME),
    "farad": Unit(1.0, CURRENT * TIME / _VOLTAGE),
    "Ah": Unit(sc.hour, CURRENT * TIME),
}

_AMBIGUOUS = {
    "F": "use 'degF' for Fahrenheit or 'farad' for capacitance",
    "C": "use 'degC' for Celsius or 'coulomb' for charge",
    "R": "use 'degR' for Rankine",
}

_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_TOKEN = re.compile(
    r"""\s*(?:
        (?P<open>\()|(?P<close>\))|
        (?P<power>\*\*|\^)|(?P<mul>\*)|(?P<dot>[·⋅])|(?P<div>/|÷)|
        (?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)|
        (?P<num>[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z]))|
        (?P<name>[%A-Za-z°µμΩ_][A-Za-z0-9°µμΩ_%]*(?:-mol)?)|
        (?P<dash>-)
    )""",
    re.VERBOSE,
)


def _lookup(name: str) -> Unit | None:
    """A name from the tables, with an SI prefix when that is what resolves it."""
    if name in _NAMED:
        return _NAMED[name]
    if name in _PREFIXABLE:
        return _PREFIXABLE[name]
    for prefix, scale in _PREFIXES.items():
        if name.startswith(prefix):
            base = _PREFIXABLE.get(name[len(prefix) :])
            if base is not None:
                return Unit(scale * base.factor, base.dimension, base.offset)
    return None


def _atom(name: str) -> tuple[Unit, Fraction]:
    """Resolve a bare name, peeling a trailing exponent (``m3``, ``s-1``) if needed."""
    if name in _AMBIGUOUS:
        raise UnknownUnitError(f"unit {name!r} is ambiguous: {_AMBIGUOUS[name]}")
    unit = _lookup(name)
    if unit is not None:
        return unit, Fraction(1)
    match = re.fullmatch(r"(.*?[A-Za-z%°µμΩ])(\d+)", name)
    if match is not None:
        unit = _lookup(match.group(1))
        if unit is not None:
            return unit, Fraction(int(match.group(2)))
    raise UnknownUnitError(f"unknown unit {name!r}")


class _Parser:
    """Recursive-descent parser over the token stream of one unit expression."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens: list[tuple[str, str]] = []
        position = 0
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None or match.end() == position:
                if text[position:].strip() == "":
                    break
                raise UnknownUnitError(f"cannot parse unit expression {text!r} at {text[position:]!r}")
            kind = match.lastgroup
            assert kind is not None
            self.tokens.append((kind, match.group(kind)))
            position = match.end()
        self.position = 0

    def _peek(self) -> str | None:
        return self.tokens[self.position][0] if self.position < len(self.tokens) else None

    def _take(self) -> tuple[str, str]:
        token = self.tokens[self.position]
        self.position += 1
        return token

    def parse(self) -> tuple[Unit, int]:
        unit, terms = self._expression()
        if self.position != len(self.tokens):
            raise UnknownUnitError(f"cannot parse unit expression {self.text!r}: unbalanced ')'")
        return unit, terms

    def _expression(self) -> tuple[Unit, int]:
        unit = self._group()
        terms = 1
        divided = False
        while True:
            kind = self._peek()
            if kind == "div":
                self._take()
                unit = unit / self._group()
                divided = True
            elif kind == "mul":
                if divided:
                    raise UnknownUnitError(
                        f"{self.text!r} is ambiguous: '*' after '/' means a/b*c in code and a/(b c) in "
                        "print; use parentheses"
                    )
                self._take()
                unit = unit * self._group()
            else:
                return unit, terms
            terms += 1

    def _group(self) -> Unit:
        """Terms joined by a space or hyphen, binding tighter than ``/``."""
        unit = self._term()
        while True:
            kind = self._peek()
            if kind in ("dash", "dot"):
                self._take()
                unit = unit * self._term()
            elif kind in ("name", "open"):
                unit = unit * self._term()
            elif kind == "num":
                raise UnknownUnitError(f"a bare number inside unit expression {self.text!r}")
            else:
                return unit

    def _term(self) -> Unit:
        if self._peek() is None:
            raise UnknownUnitError(f"unit expression {self.text!r} ends where a unit is expected")
        kind, value = self._take()
        if kind == "open":
            inner, _ = self._expression()
            if self._peek() != "close":
                raise UnknownUnitError(f"unbalanced parentheses in unit expression {self.text!r}")
            self._take()
            return self._power(inner, after_group=True)
        if kind == "num":
            return Unit(float(value), DIMENSIONLESS)
        if kind == "name":
            unit, exponent = _atom(value)
            if exponent != 1:
                unit = unit**exponent
            return self._power(unit)
        raise UnknownUnitError(f"unexpected {value!r} in unit expression {self.text!r}")

    def _power(self, unit: Unit, *, after_group: bool = False) -> Unit:
        kind = self._peek()
        if kind == "power":
            self._take()
            sign, value = 1, ""
            if self._peek() == "dash":
                self._take()
                sign = -1
            if self._peek() != "num":
                raise UnknownUnitError(f"exponent expected in unit expression {self.text!r}")
            value = self._take()[1]
            exponent = sign * Fraction(value).limit_denominator(1000)
            if self._peek() == "div" and self._next_is_number():  # m^1/2
                self._take()
                exponent /= Fraction(self._take()[1])
            return unit**exponent
        if kind == "sup":
            return unit ** Fraction(self._take()[1].translate(_SUPERSCRIPTS))
        if kind == "num" and (self.tokens[self.position][1][0] in "+-" or after_group):
            # s-1, s-1.5 and (m/s)2: a number directly on a unit or a group is its exponent
            return unit ** Fraction(self._take()[1]).limit_denominator(1000)
        return unit

    def _next_is_number(self) -> bool:
        return self.position + 1 < len(self.tokens) and self.tokens[self.position + 1][0] == "num"


def _enclosing(text: str) -> bool:
    """True when the first parenthesis closes on the last character."""
    depth = 0
    for i, char in enumerate(text):
        depth += (char == "(") - (char == ")")
        if depth == 0:
            return i == len(text) - 1
    return False


@lru_cache(maxsize=2048)
def parse_unit(expression: str) -> Unit:
    """Parse a unit expression into a :class:`Unit`.

    A lone offset unit keeps its offset; inside a compound the offset is dropped
    (an interval, see the module docstring). Raises
    :class:`~ngdesign.uom.dimension.UnknownUnitError`.
    """
    text = expression.strip()
    while text.startswith("(") and text.endswith(")") and _enclosing(text):
        text = text[1:-1].strip()
    if not text:
        return Unit(1.0, DIMENSIONLESS, symbol="1")
    named = _lookup(text)
    if named is not None:
        return Unit(named.factor, named.dimension, named.offset, text)
    unit, _terms = _Parser(text).parse()
    return Unit(unit.factor, unit.dimension, 0.0, text)
