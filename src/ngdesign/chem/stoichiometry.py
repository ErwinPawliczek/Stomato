"""Stoichiometry: equations, exact balancing, reaction spaces and yield accounting.

Balancing is exact linear algebra over the rationals. For the composition matrix
A (one row per element, plus one for charge) a balanced reaction is a vector ν
with A·ν = 0, so the reaction space is the null space of A; its dimension is the
number of independent reactions among the species (Aris & Mah 1963; Smith &
Missen, *Chemical Reaction Equilibrium Analysis*, 1982, ch. 2). Dimension 1 is a
unique balance, 0 means no balance exists, and more means the species list does
not determine one reaction, which is refused rather than guessed.

Species tokens are formulas (``C3H8``, ``H2O(l)``, ``SO4^2-``) or database names
(``n-butane``, ``methanol``), resolved through :mod:`ngdesign.data.chemdb`.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from functools import reduce

from ngdesign.chem.formula import Formula, FormulaError, parse_formula
from ngdesign.contracts.reactions import Reaction
from ngdesign.data import chemdb


class StoichiometryError(ValueError):
    """Base class of stoichiometry refusals."""


class EquationSyntaxError(StoichiometryError):
    """An equation string cannot be parsed."""


class NoBalanceError(StoichiometryError):
    """No set of nonzero coefficients conserves every element and the charge."""


class IndeterminateBalanceError(StoichiometryError):
    """The species admit several independent reactions, so one balance is not defined."""


_PHASE_CODES = {"gas": "g", "liquid": "l", "solid": "s", "aqueous": "aq"}


@dataclass(frozen=True, slots=True)
class Term:
    """One species in an equation."""

    label: str  # the token as written, without coefficient or phase suffix
    formula: Formula
    species_query: str | None = None  # what to look up in the database, when known
    phase: str | None = None

    @property
    def key(self) -> str:
        """Identity of the term: a species in another phase is another term."""
        return f"{self.label}({_PHASE_CODES[self.phase]})" if self.phase else self.label


@dataclass(frozen=True)
class Equation:
    """A chemical equation: terms with signed stoichiometric coefficients ν."""

    terms: tuple[Term, ...]
    coefficients: tuple[Fraction, ...]  # ν < 0 reactants, ν > 0 products
    reversible: bool = False

    @property
    def reactants(self) -> dict[str, Fraction]:
        return {t.key: -c for t, c in zip(self.terms, self.coefficients, strict=True) if c < 0}

    @property
    def products(self) -> dict[str, Fraction]:
        return {t.key: c for t, c in zip(self.terms, self.coefficients, strict=True) if c > 0}

    @property
    def nu(self) -> dict[str, float]:
        """Net ν by term key, as floats (the contract and solver currency).

        A catalytic species written on both sides nets out here, and stays
        visible in ``terms`` for the rate law.
        """
        net: dict[str, float] = {}
        for term, coefficient in zip(self.terms, self.coefficients, strict=True):
            net[term.key] = net.get(term.key, 0.0) + float(coefficient)
        return net

    def imbalance(self) -> dict[str, Fraction]:
        """Net element and charge residual; empty when balanced."""
        net: dict[str, Fraction] = {}
        for term, nu in zip(self.terms, self.coefficients, strict=True):
            for element, count in term.formula.atoms:
                net[element] = net.get(element, Fraction(0)) + nu * count
            if term.formula.charge:
                net["charge"] = net.get("charge", Fraction(0)) + nu * term.formula.charge
        return {key: value for key, value in net.items() if value != 0}

    @property
    def is_balanced(self) -> bool:
        return not self.imbalance()

    def __str__(self) -> str:
        def side(pairs: list[tuple[Term, Fraction]]) -> str:
            return " + ".join(f"{_coefficient(abs(nu))}{term.key}" for term, nu in pairs)

        pairs = list(zip(self.terms, self.coefficients, strict=True))
        left = side([p for p in pairs if p[1] < 0])
        right = side([p for p in pairs if p[1] > 0])
        return f"{left} {'<=>' if self.reversible else '->'} {right}"


def _coefficient(value: Fraction) -> str:
    return "" if value == 1 else f"{value} "


_ARROW = re.compile(r"\s*(<=>|<->|⇌|↔|->|→|=>|=)\s*")
_LEADING = re.compile(r"^(\d+(?:/\d+)?(?:\.\d+)?)\s*\*?\s*(?=[A-Za-z(\[e])")
_PHASE_TAIL = re.compile(r"\s*\((g|l|s|cr|c|aq)\)\s*$")


def resolve_term(token: str) -> Term:
    """A species token to a :class:`Term`: a formula if it parses, else a database name."""
    text = token.strip()
    tail = _PHASE_TAIL.search(text)
    phase_free = text[: tail.start()] if tail else text
    try:
        formula = parse_formula(text)
    except FormulaError:
        try:
            species = chemdb.find(phase_free)
        except chemdb.ChemDbError as exc:
            raise EquationSyntaxError(f"{token!r} is neither a formula nor a known species: {exc}") from exc
        formula = parse_formula(species.formula)
        return Term(phase_free, formula, species.cas, _phase_of(tail))
    return Term(formula.text, formula, formula.text if not formula.charge else None, formula.phase)


def _phase_of(tail: re.Match[str] | None) -> str | None:
    if tail is None:
        return None
    return parse_formula(f"H2{tail.group(0).strip()}").phase


def _side(text: str) -> list[tuple[Fraction | None, Term]]:
    terms: list[tuple[Fraction | None, Term]] = []
    # A spaced '+' separates terms; so does a tight one between two formulas ("H2+O2").
    # A charge's '+' never does: it ends its token ("Na+ + Cl-") or leads a digit ("Fe+3").
    for piece in re.split(r"\s+\+\s+|(?<=[0-9a-z)\]])\+(?=[A-Z(])", text):
        token = piece.strip()
        if not token:
            raise EquationSyntaxError(f"empty term in {text!r}")
        coefficient: Fraction | None = None
        match = _LEADING.match(token)
        if match is not None:
            coefficient = Fraction(match.group(1))
            token = token[match.end() :]
        terms.append((coefficient, resolve_term(token)))
    return terms


def parse_equation(text: str) -> Equation:
    """Parse ``"2 H2 + O2 -> 2 H2O"``; missing coefficients are 1 until balanced."""
    parts = _ARROW.split(text.strip())
    if len(parts) != 3:
        raise EquationSyntaxError(f"equation {text!r} needs exactly one arrow")
    left, arrow, right = parts
    if not left or not right:
        raise EquationSyntaxError(f"equation {text!r} needs both sides")
    terms: list[Term] = []
    coefficients: list[Fraction] = []
    for sign, side in ((-1, left), (1, right)):
        seen: set[str] = set()
        for coefficient, term in _side(side):
            if term.key in seen:
                raise EquationSyntaxError(
                    f"{term.key!r} appears twice on one side of {text!r}; use a coefficient"
                )
            seen.add(term.key)
            terms.append(term)
            coefficients.append(sign * (coefficient if coefficient is not None else Fraction(1)))
    return Equation(tuple(terms), tuple(coefficients), arrow in ("<=>", "<->", "⇌", "↔"))


def composition_matrix(formulas: Sequence[Formula]) -> tuple[list[str], list[list[Fraction]]]:
    """(row labels, A): element rows plus a ``charge`` row when any species is charged."""
    elements = sorted({element for f in formulas for element, _ in f.atoms})
    rows = [[Fraction(f.composition.get(element, 0)) for f in formulas] for element in elements]
    if any(f.charge for f in formulas):
        elements.append("charge")
        rows.append([Fraction(f.charge) for f in formulas])
    return elements, rows


def _rref(matrix: list[list[Fraction]], n_columns: int) -> tuple[list[list[Fraction]], list[int]]:
    """Reduced row echelon form over Q, with the pivot columns."""
    rows = [list(row) for row in matrix]
    pivots: list[int] = []
    row_index = 0
    for column in range(n_columns):
        pivot = next((r for r in range(row_index, len(rows)) if rows[r][column] != 0), None)
        if pivot is None:
            continue
        rows[row_index], rows[pivot] = rows[pivot], rows[row_index]
        head = rows[row_index][column]
        rows[row_index] = [value / head for value in rows[row_index]]
        for r in range(len(rows)):
            if r != row_index and rows[r][column] != 0:
                factor = rows[r][column]
                rows[r] = [a - factor * b for a, b in zip(rows[r], rows[row_index], strict=True)]
        pivots.append(column)
        row_index += 1
        if row_index == len(rows):
            break
    return rows, pivots


def null_space(matrix: list[list[Fraction]], n_columns: int) -> list[list[Fraction]]:
    """Exact basis of {ν : A·ν = 0}: one vector per free column, integer-scaled."""
    reduced, pivots = _rref(matrix, n_columns)
    free = [c for c in range(n_columns) if c not in pivots]
    basis: list[list[Fraction]] = []
    for column in free:
        vector = [Fraction(0)] * n_columns
        vector[column] = Fraction(1)
        for row, pivot in zip(reduced, pivots, strict=False):
            vector[pivot] = -row[column]
        basis.append(_integer_scaled(vector))
    return basis


def _integer_scaled(vector: Sequence[Fraction]) -> list[Fraction]:
    """Smallest integer multiple of ``vector``."""
    denominator = reduce(math.lcm, (v.denominator for v in vector), 1)
    numerators = [int(v * denominator) for v in vector]
    divisor = reduce(math.gcd, (abs(n) for n in numerators), 0) or 1
    return [Fraction(n, divisor) for n in numerators]


def balance(equation: str | Equation) -> Equation:
    """Balance an equation, keeping each term on the side it was written on.

    Refuses with :class:`NoBalanceError` when no balance exists (including a
    balance that needs a term on the other side, which the message names) and
    with :class:`IndeterminateBalanceError` when the species do not fix one.
    """
    parsed = parse_equation(equation) if isinstance(equation, str) else equation
    labels = [term.key for term in parsed.terms]
    n = len(parsed.terms)
    _, matrix = composition_matrix([term.formula for term in parsed.terms])
    basis = null_space(matrix, n)
    if not basis:
        raise NoBalanceError(f"no balance exists for {parsed}: the species conserve nothing in common")
    if len(basis) > 1:
        raise IndeterminateBalanceError(
            f"{parsed} has {len(basis)} independent balances; the species alone do not fix one reaction. "
            "Add a stated ratio or split it into separate reactions."
        )
    vector = basis[0]
    if any(v == 0 for v in vector):
        zero = [label for label, v in zip(labels, vector, strict=True) if v == 0]
        raise NoBalanceError(f"{parsed}: terms {zero} cannot take part in any balance of the rest")
    # orient so that the reference term keeps its written side
    sides = [1 if c > 0 else -1 for c in parsed.coefficients]
    if vector[0] * sides[0] < 0:
        vector = [-v for v in vector]
    wrong = [label for label, v, side in zip(labels, vector, sides, strict=True) if (v > 0) != (side > 0)]
    if wrong:
        raise NoBalanceError(f"{parsed}: a balance exists only with {wrong} on the other side")
    return Equation(parsed.terms, tuple(vector), parsed.reversible)


def as_written(equation: str | Equation) -> Equation:
    """A balanced equation on the basis the caller wrote it, balancing only if needed.

    ``CO + 1/2 O2 -> CO2`` stays per mole of CO. :func:`balance` would reduce it to
    smallest integers, doubling every per-reaction quantity downstream.
    """
    parsed = parse_equation(equation) if isinstance(equation, str) else equation
    return parsed if parsed.is_balanced else balance(parsed)


@dataclass(frozen=True)
class ReactionSpace:
    """The independent reactions of a species set."""

    species: tuple[str, ...]
    elements: tuple[str, ...]
    rank: int  # rank of the composition matrix: independent element constraints
    reactions: tuple[Equation, ...]

    @property
    def n_independent(self) -> int:
        return len(self.reactions)


def reaction_space(species: Sequence[str]) -> ReactionSpace:
    """Rank and a basis of independent reactions among ``species`` (C − rank of them)."""
    terms = [resolve_term(token) for token in species]
    labels, matrix = composition_matrix([term.formula for term in terms])
    _, pivots = _rref(matrix, len(terms))
    equations = []
    for vector in null_space(matrix, len(terms)):
        pairs = [(t, v) for t, v in zip(terms, vector, strict=True) if v != 0]
        leading = next(v for _, v in pairs)
        oriented = [(t, -v if leading > 0 else v) for t, v in pairs]
        equations.append(Equation(tuple(t for t, _ in oriented), tuple(v for _, v in oriented)))
    return ReactionSpace(tuple(t.key for t in terms), tuple(labels), len(pivots), tuple(equations))


# ---------------------------------------------------------------- yield accounting


@dataclass(frozen=True)
class ExtentResult:
    """Outcome of running one reaction to completion on a feed."""

    limiting: str
    extent: float  # mol of reaction
    final: dict[str, float] = field(default_factory=dict)  # mol


def limiting_reagent(equation: str | Equation, feed: Mapping[str, float]) -> ExtentResult:
    """The reactant that runs out first, ξ_max = min_i n_i/|ν_i|, and the final amounts.

    ``feed`` is in mol, keyed by term key; a reactant absent from it is refused
    (it is not in excess by omission; say so with a number).
    """
    balanced = as_written(equation)
    consumed = {key: -nu for key, nu in balanced.nu.items() if nu < 0.0}  # net: a catalyst is not consumed
    missing = [key for key in consumed if key not in feed]
    if missing:
        raise StoichiometryError(f"feed gives no amount for reactants {missing}")
    negative = sorted(key for key, n in feed.items() if n < 0.0)
    if negative:
        raise StoichiometryError(f"negative feed amounts for {negative}")
    extents = {key: float(feed[key]) / nu for key, nu in consumed.items()}
    limiting = min(extents, key=lambda key: (extents[key], key))
    extent = extents[limiting]
    final = {key: float(n) for key, n in feed.items()}
    for key, nu in balanced.nu.items():
        final[key] = final.get(key, 0.0) + nu * extent
    final[limiting] = 0.0
    return ExtentResult(limiting, extent, final)


def theoretical_yield(equation: str | Equation, feed: Mapping[str, float], product: str) -> float:
    """mol of ``product`` formed when the limiting reagent is consumed."""
    balanced = as_written(equation)
    if product not in balanced.products:
        raise StoichiometryError(f"{product!r} is not a product of {balanced}")
    return limiting_reagent(balanced, feed).extent * float(balanced.products[product])


def percent_yield(actual: float, theoretical: float) -> float:
    """100·actual/theoretical."""
    if theoretical <= 0.0:
        raise StoichiometryError("theoretical yield must be positive")
    return 100.0 * actual / theoretical


def atom_economy(equation: str | Equation, product: str) -> float:
    """Trost atom economy: 100·ν_p·M_p / Σ_reactants ν_i·M_i (Science 254, 1471, 1991)."""
    balanced = as_written(equation)
    if product not in balanced.products:
        raise StoichiometryError(f"{product!r} is not a product of {balanced}")
    masses = {t.key: t.formula.molar_mass for t in balanced.terms}
    feed_mass = sum(float(nu) * masses[key] for key, nu in balanced.reactants.items())
    return 100.0 * float(balanced.products[product]) * masses[product] / feed_mass


@dataclass(frozen=True)
class Performance:
    """Conversion of the key reactant, with selectivity and yield of the desired product."""

    conversion: float
    selectivity: float
    yield_: float


def reactor_performance(
    n_in: Mapping[str, float],
    n_out: Mapping[str, float],
    key: str,
    desired: str,
    nu_key: float = 1.0,
    nu_desired: float = 1.0,
) -> Performance:
    """X = (n_k0 − n_k)/n_k0; S = (ν_k/ν_p)·Δn_p/(n_k0 − n_k); Y = X·S (fractions)."""
    feed = float(n_in[key])
    if feed <= 0.0:
        raise StoichiometryError(f"key reactant {key!r} has no feed")
    reacted = feed - float(n_out.get(key, 0.0))
    made = float(n_out.get(desired, 0.0)) - float(n_in.get(desired, 0.0))
    conversion = reacted / feed
    if reacted == 0.0:
        return Performance(0.0, 0.0, 0.0)
    selectivity = (nu_key / nu_desired) * made / reacted
    return Performance(conversion, selectivity, conversion * selectivity)


def to_reaction(
    equation: str | Equation,
    *,
    reaction_id: str,
    provenance: str,
    base_component: str | None = None,
    ids: Mapping[str, str] | None = None,
) -> Reaction:
    """The flowsheet :class:`~ngdesign.contracts.reactions.Reaction` of a balanced equation.

    Terms map to component ids through ``ids`` (term key -> slate id) or, failing
    that, the species CAS, which ``component_record`` resolves for any database
    species. ``base_component`` (default: the first reactant) names a term key.
    Charged terms cannot enter a molecular slate and are refused by that lookup.
    """
    balanced = as_written(equation)
    mapping = dict(ids or {})

    def identity(term: Term) -> str:
        if term.key in mapping:
            return mapping[term.key]
        if term.species_query is None:
            raise StoichiometryError(f"{term.key!r} has no component identity")
        try:
            return chemdb.find(term.species_query).cas
        except chemdb.ChemDbError as exc:
            raise StoichiometryError(f"{term.key!r}: {exc}; pass ids= to name it") from exc

    stoichiometry = {
        identity(term): float(nu) for term, nu in zip(balanced.terms, balanced.coefficients, strict=True)
    }
    base_key = base_component or next(iter(balanced.reactants))
    base_term = next((t for t in balanced.terms if t.key == base_key), None)
    if base_term is None:
        raise StoichiometryError(f"base component {base_key!r} is not a term of {balanced}")
    return Reaction(
        id=reaction_id,
        stoichiometry=stoichiometry,
        base_component=identity(base_term),
        provenance=provenance,
    )
