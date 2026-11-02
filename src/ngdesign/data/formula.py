"""Chemical formula parsing: atoms, charge, phase and hydrate handling.

Lives in the data layer because the database resolves ions through it.

Element counting is delegated to ``chemicals.elements.nested_formula_parser`` and
charge reading to ``charge_from_formula``. This module adds what they do not take:
the phase suffix ``(g)``/``(l)``/``(s)``/``(aq)``, hydrate dots ``CuSO4·5H2O``,
caret charges ``SO4^2-``, and the electron ``e-`` that half-reactions need.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from chemicals.elements import (
    atoms_to_Hill,
    charge_from_formula,
    molecular_weight,
    nested_formula_parser,
    periodic_table,
)

_PHASES = {
    "g": "gas",
    "l": "liquid",
    "s": "solid",
    "cr": "solid",
    "c": "solid",
    "aq": "aqueous",
}
_PHASE_SUFFIX = re.compile(r"\s*\((g|l|s|cr|c|aq)\)\s*$")
_CARET_CHARGE = re.compile(r"\^?\{?(\d*)([+-])\}?$")
_SIGNED_CHARGE = re.compile(r"(?:[+-]\d*|\+\+|--)$")
_DIGIT_THEN_SIGN = re.compile(r"^(.*?[A-Za-z\])])(\d+)([+-])$")
_LONE_ELEMENT = re.compile(r"[A-Z][a-z]?")
_MOLECULAR_ELEMENTS = {"H", "N", "O", "F", "Cl", "Br", "I"}
_ELEMENT_SHAPE = re.compile(r"^[\[(]?[A-Z][A-Za-z0-9()\[\]·.*]*")


#: Element symbols of the periodic table, plus the hydrogen isotopes as symbols.
_ELEMENTS = {element.symbol for element in periodic_table} | {"D", "T"}


class FormulaError(ValueError):
    """A string is not a parsable chemical formula."""


@dataclass(frozen=True, slots=True)
class Formula:
    """One parsed species token."""

    text: str  # the token without its phase suffix, as written
    atoms: tuple[tuple[str, int], ...]  # sorted (element, count)
    charge: int
    phase: str | None  # "gas" | "liquid" | "solid" | "aqueous" | None

    @property
    def composition(self) -> dict[str, int]:
        return dict(self.atoms)

    @property
    def hill(self) -> str:
        """The neutral Hill-order formula."""
        if not self.atoms:
            return ""
        return str(atoms_to_Hill(self.composition))

    @property
    def molar_mass(self) -> float:
        """g/mol from the standard atomic weights in ``chemicals.periodic_table``."""
        if not self.atoms:
            return 0.0
        return float(molecular_weight(self.composition))


def _split_charge(body: str) -> tuple[str, int]:
    """Strip a trailing charge from a formula body: ``(body-without-charge, charge)``.

    ``NH4+`` and ``Fe3+`` have the same shape and opposite meanings, so a digit before
    a final sign is read by what precedes it. After ``]`` it is the charge
    (``[Fe(CN)6]3-``); after ``)`` a subscript (``Al(OH)4-``). After a lone metal it is
    the charge (``Fe3+``). After a lone H, N, O or halogen it could be either (``O2-``),
    so it is refused, as is a two-digit run on a polyatomic (``SO42-``). Otherwise it is
    a subscript (``NO3-``, ``NH4+``).
    The caret and sign-first spellings (``SO4^2-``, ``Fe+3``) are never ambiguous.
    """
    if "^" in body or body.endswith("}"):
        head, _, tail = (
            body.rpartition("^") if "^" in body else (body[: body.rfind("{")], "", body[body.rfind("{") :])
        )
        match = _CARET_CHARGE.fullmatch(tail.strip())
        if match is None:
            raise FormulaError(f"cannot read the charge in {body!r}")
        magnitude = int(match.group(1) or 1)
        return head, magnitude if match.group(2) == "+" else -magnitude
    trailing = _DIGIT_THEN_SIGN.search(body)
    if trailing is not None:
        head, digits, sign = trailing.groups()
        magnitude = int(digits[-1]) * (1 if sign == "+" else -1)
        if head.endswith("]") and len(digits) == 1:
            return head, magnitude
        lone = _LONE_ELEMENT.fullmatch(head)
        if lone is not None and len(digits) == 1:
            if head in _MOLECULAR_ELEMENTS:
                raise FormulaError(
                    f"{body!r} is ambiguous: write {head}{digits}^{sign} or {head}^{digits}{sign}"
                )
            return head, magnitude
        if len(digits) > 1:
            raise FormulaError(f"{body!r} is ambiguous: write the charge with a caret, as in SO4^2-")
    if _SIGNED_CHARGE.search(body):
        return re.sub(_SIGNED_CHARGE, "", body), int(charge_from_formula(body))
    return body, 0


def _hydrate_parts(body: str) -> list[tuple[int, str]]:
    """Split ``CuSO4·5H2O`` into [(1, "CuSO4"), (5, "H2O")]."""
    if re.search(r"[·⋅*.]\s*\d+\.\d", body):
        raise FormulaError(f"{body!r}: a fractional hydrate has no integer atom counts")
    if re.search(r"\d\.\d+[A-Z]", body) and re.search(r"(?<!\d)0\.\d", body):
        raise FormulaError(f"{body!r} has a fractional subscript")
    parts: list[tuple[int, str]] = []
    for piece in re.split(r"[·⋅*]|(?<=[A-Za-z0-9)\]])\.(?=\d*[A-Z(])", body):
        match = re.fullmatch(r"(\d+)?(.+)", piece.strip())
        if match is None:
            raise FormulaError(f"empty hydrate part in {body!r}")
        parts.append((int(match.group(1) or 1), match.group(2)))
    return parts


@lru_cache(maxsize=4096)
def parse_formula(token: str) -> Formula:
    """Parse a species token such as ``H2O(l)``, ``Fe2(SO4)3``, ``SO4^2-`` or ``e-``."""
    raw = token.strip()
    phase: str | None = None
    match = _PHASE_SUFFIX.search(raw)
    if match is not None:
        phase = _PHASES[match.group(1)]
        raw = raw[: match.start()]
    if raw in ("e-", "e", "e^-"):
        return Formula("e-", (), -1, phase)
    if not raw or _ELEMENT_SHAPE.match(raw) is None:
        raise FormulaError(f"{token!r} is not a chemical formula")
    body, charge = _split_charge(raw)
    atoms: dict[str, int] = {}
    try:
        for multiple, part in _hydrate_parts(body):
            for element, count in nested_formula_parser(part).items():
                if float(count) != int(count):
                    raise FormulaError(f"{token!r} is non-stoichiometric ({element}{count})")
                atoms[element] = atoms.get(element, 0) + multiple * int(count)
    except FormulaError:
        raise
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise FormulaError(f"{token!r} is not a chemical formula: {exc}") from exc
    if not atoms:
        raise FormulaError(f"{token!r} has no atoms")
    unknown = sorted(set(atoms) - _ELEMENTS)
    if unknown:
        raise FormulaError(f"{token!r} names unknown elements {unknown}")
    return Formula(raw, tuple(sorted(atoms.items())), charge, phase)
