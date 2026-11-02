"""Chemical equilibrium: multiphase Gibbs minimisation and reaction extents.

:func:`gibbs_equilibrium` minimises the total Gibbs energy of an ideal-gas mixture
plus any number of pure condensed species over the element balances, with the
reduced Newton iteration of the NASA CEA code (Gordon & McBride, NASA RP-1311,
1994, eqs. 2.24-2.26): unknowns are the element potentials π_j, the condensed
amounts and Δln N, from which each Δln n_i follows. The condensed species present
are found by an active set: after each converged gas-phase solve, the candidate
with the most negative driving force μ_c/RT − Σ_j a_cj π_j joins (CEA §3.5), and a
species whose amount goes negative leaves.

Real-gas behaviour enters through ``thermo=``, any registered package: ln φ_i of
the vapour is evaluated at the current composition and the ideal solve is repeated
until the composition stops moving (successive substitution on the fugacity term).

The ideal-gas path has its own older implementation in
``ngdesign.units._physics.gibbs.gibbs_minimum``, which the Gibbs reactor unit uses;
the two are cross-checked in ``tests/chem/test_equilibrium.py``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import brentq, linprog

from ngdesign.chem.formula import parse_formula
from ngdesign.chem.stoichiometry import Equation, _rref, balance
from ngdesign.chem.thermochem import (
    P_STANDARD,
    PHASES,
    T_REF,
    R,
    ReactionThermo,
    SpeciesThermo,
    reaction_thermo,
    species_thermo,
)
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import chemdb
from ngdesign.uom.quantity import si_arguments

#: Trace-species floor as a fraction of the total: below it a mole number stops
#: steering Newton (CEA's SIZE parameter plays this role).
_TRACE = 1e-28
_MAX_ITERATIONS = 500
_MAX_PHASE_CHANGES = 40


class EquilibriumError(ValueError):
    """An equilibrium problem is ill-posed or did not converge."""


@dataclass(frozen=True)
class Candidate:
    """One species-in-a-phase the solver may use."""

    key: str
    thermo: SpeciesThermo
    atoms: dict[str, int]

    @property
    def condensed(self) -> bool:
        return self.thermo.phase != "gas"


@dataclass(frozen=True)
class EquilibriumResult:
    """Equilibrium amounts in mol (per the feed basis) and what the solver did."""

    T: float
    P: float
    gas: dict[str, float]  # mol, gas species
    condensed: dict[str, float]  # mol, pure condensed species present
    gibbs: float  # J, total G of the mixture
    enthalpy: float  # J, total H on the element reference
    element_potentials: dict[str, float]  # π_j = λ_j/RT
    iterations: int
    fugacity_iterations: int = 0
    ln_phi: dict[str, float] = field(default_factory=dict)
    excluded: tuple[str, ...] = ()  # condensed candidates with no model at this T

    @property
    def gas_total(self) -> float:
        return math.fsum(self.gas.values())

    @property
    def mole_fractions(self) -> dict[str, float]:
        """Gas-phase mole fractions."""
        total = self.gas_total
        return {key: n / total for key, n in self.gas.items()} if total > 0.0 else {}


def _candidate(token: str) -> Candidate:
    """``"H2O(l)"``/``"CO2"`` to a candidate; a bare token is the gas."""
    text = token.strip()
    phase = "gas"
    for suffix, name in (("(g)", "gas"), ("(l)", "liquid"), ("(s)", "solid"), ("(cr)", "solid")):
        if text.endswith(suffix):
            text, phase = text[: -len(suffix)].strip(), name
            break
    species = chemdb.find(text)
    atoms = parse_formula(species.formula).composition
    return Candidate(token.strip(), species_thermo(species.cas, phase), dict(atoms))


def _element_table(
    candidates: Sequence[Candidate], feed: Mapping[str, float]
) -> tuple[list[str], NDArray[np.float64]]:
    """(elements, b): atoms in the feed, refusing any no candidate can hold."""
    budget: dict[str, float] = {}
    for token, amount in feed.items():
        if amount < 0.0:
            raise EquilibriumError(f"negative feed amount for {token!r}")
        atoms = parse_formula(chemdb.find(_strip_phase(token)).formula).composition
        for element, count in atoms.items():
            budget[element] = budget.get(element, 0.0) + count * float(amount)
    held = {element for c in candidates for element in c.atoms}
    orphan = sorted(set(budget) - held)
    if orphan:
        raise EquilibriumError(f"no candidate species holds element(s) {orphan}")
    elements = sorted(element for element, amount in budget.items() if amount > 0.0)
    if not elements:
        raise EquilibriumError("the feed is empty")
    return elements, np.array([budget[element] for element in elements])


def _strip_phase(token: str) -> str:
    for suffix in ("(g)", "(l)", "(s)", "(cr)"):
        if token.strip().endswith(suffix):
            return token.strip()[: -len(suffix)].strip()
    return token.strip()


@dataclass(frozen=True)
class _Basis:
    """Element rows recombined so the major species sit on unit columns.

    Near a stoichiometric feed the plain element rows are dependent to within the
    trace amounts: pure H2O at 300 K has n(O2)/n ~ 1e-27, which a sum over 1.0 in
    double precision cannot hold, so the rows cannot pin it. Recombining them exactly,
    with pivots on the most abundant species, cancels the majors out of the other rows
    (the (H - 2·O) row of that feed holds only H2 and O2, and its budget is exactly
    0). This is the component-species idea of the VCS method (Smith & Missen 1982), used
    here only to condition the CEA iteration. The transform is exact, over the rationals.
    """

    key: tuple[int, ...]
    T: NDArray[np.float64]  # new rows = T @ old rows
    A: NDArray[np.float64]  # gas columns
    C: NDArray[np.float64]  # condensed rows, on the same recombined element basis
    b: NDArray[np.float64]


def _make_basis(
    key: tuple[int, ...],
    A_int: Sequence[Sequence[int]],
    C_int: Sequence[Sequence[int]],
    b: Sequence[Fraction],
) -> _Basis:
    """RREF of [columns ordered by abundance | I] gives the exact row transform."""
    n_e = len(A_int)
    n_gas = len(A_int[0]) if n_e else 0
    columns = [[Fraction(A_int[e][i]) for i in range(n_gas)] for e in range(n_e)]
    for c_row in C_int:
        for e in range(n_e):
            columns[e].append(Fraction(c_row[e]))
    ordered = [[columns[e][j] for j in key] + [Fraction(int(e == k)) for k in range(n_e)] for e in range(n_e)]
    reduced, pivots = _rref(ordered, len(key))
    # rows past the rank are 0 = 0: elements every candidate carries in one fixed ratio
    T = [row[len(key) :] for row in reduced[: len(pivots)]]
    A_new = [[sum(t * A_int[e][i] for e, t in enumerate(row)) for i in range(n_gas)] for row in T]
    C_new = [[sum(t * c_row[e] for e, t in enumerate(row)) for row in T] for c_row in C_int]
    # (each entry above is the recombined element count of one condensed species)
    b_new = [sum(t * b[e] for e, t in enumerate(row)) for row in T]
    return _Basis(
        key,
        np.array(T, dtype=float).reshape(len(T), n_e),
        np.array(A_new, dtype=float).reshape(len(T), n_gas),
        np.array(C_new, dtype=float).reshape(len(C_int), len(T)),
        np.array(b_new, dtype=float),
    )


def _solve_scaled(J: NDArray[np.float64], rhs: NDArray[np.float64]) -> NDArray[np.float64]:
    """Solve the symmetric Newton system after diagonal equilibration."""
    diagonal = np.abs(np.diag(J))
    scale = np.where(diagonal > 0.0, 1.0 / np.sqrt(np.where(diagonal > 0.0, diagonal, 1.0)), 1.0)
    scaled = (J * scale).T * scale
    try:
        y = np.linalg.solve(scaled, rhs * scale)
        error = float(np.abs(scaled @ y - rhs * scale).max())
        if not np.isfinite(y).all() or error > 1e-8 * max(float(np.abs(rhs * scale).max()), 1e-300):
            raise np.linalg.LinAlgError("inaccurate step")
    except np.linalg.LinAlgError:
        y = np.linalg.lstsq(scaled, rhs * scale, rcond=1e-15)[0]
    return np.asarray(y * scale, dtype=float)


def _solve_active(
    gas: Sequence[Candidate],
    condensed: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0_gas: NDArray[np.float64],
    g0_cond: NDArray[np.float64],
    ln_p: float,
    start: tuple[NDArray[np.float64], NDArray[np.float64]],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], int]:
    """Newton on the reduced Gibbs equations for a fixed active set.

    Returns gas amounts, condensed amounts, element potentials, iterations.
    """
    A_int = [[c.atoms.get(e, 0) for c in gas] for e in elements]
    C_int = [[c.atoms.get(e, 0) for e in elements] for c in condensed]
    b_exact = [Fraction(float(value)) for value in b]
    n, m = start[0].copy(), start[1].copy()
    n_total = float(n.sum()) if n.size else 0.0
    n_elements, n_c = len(elements), len(condensed)
    has_gas = n.size > 0
    pi = np.zeros(n_elements)
    scale = float(np.abs(b).sum())
    basis: _Basis | None = None
    for iteration in range(1, _MAX_ITERATIONS + 1):
        order = tuple(int(j) for j in np.argsort(-np.concatenate([n, m]), kind="stable"))
        if basis is None or basis.key[: n_elements + 1] != order[: n_elements + 1]:
            basis = _make_basis(order, A_int, C_int, b_exact)
        A, C, b_t = basis.A, basis.C, basis.b
        n_e = A.shape[0]
        if has_gas:
            mu = g0_gas + np.log(np.maximum(n, 1e-300)) - math.log(n_total) + ln_p
            weighted = A * n
            G = weighted @ A.T
            row_totals = weighted.sum(axis=1)
            element_residual = b_t - A @ n - (C.T @ m if n_c else 0.0) + weighted @ mu
        else:
            mu = np.zeros(0)
            G = np.zeros((n_e, n_e))
            row_totals = np.zeros(n_e)
            element_residual = b_t - (C.T @ m if n_c else np.zeros(n_e))
        size = n_e + n_c + (1 if has_gas else 0)
        J = np.zeros((size, size))
        rhs = np.zeros(size)
        J[:n_e, :n_e] = G
        rhs[:n_e] = element_residual
        if n_c:
            J[:n_e, n_e : n_e + n_c] = C.T
            J[n_e : n_e + n_c, :n_e] = C
            rhs[n_e : n_e + n_c] = g0_cond
        if has_gas:
            J[:n_e, -1] = row_totals
            J[-1, :n_e] = row_totals
            J[-1, -1] = float(n.sum()) - n_total
            rhs[-1] = n_total - float(n.sum()) + float(n @ mu)
        step = _solve_scaled(J, rhs)
        pi_basis = step[:n_e]
        pi = basis.T.T @ pi_basis
        dm = step[n_e : n_e + n_c]
        dln_total = float(step[-1]) if has_gas else 0.0
        dln = dln_total + A.T @ pi_basis - mu if has_gas else np.zeros(0)
        # CEA damping: bound the largest log step of the major species and the total.
        lam = 1.0
        if has_gas:
            major = n / n_total > 1e-10
            largest = max(5.0 * abs(dln_total), float(np.abs(dln[major]).max(initial=0.0)))
            if largest > 2.0:
                lam = 2.0 / largest
            minor_up = (~major) & (dln > 0.0)
            if minor_up.any():
                headroom = (-np.log(n[minor_up] / n_total) - 9.2) / (dln[minor_up] - dln_total + 1e-300)
                bounded = headroom[headroom > 0.0]
                if bounded.size:
                    lam = min(lam, float(np.abs(bounded).min()))
        if n_c:
            shrink = m + lam * dm
            if (shrink < 0.0).any():
                ratios = -m[dm < 0.0] / dm[dm < 0.0]
                lam = min(lam, float(ratios.min()) * 0.999 if ratios.size else lam)
        if has_gas:
            n = n * np.exp(np.clip(lam * dln, -700.0, 700.0))
            n = np.maximum(n, 1e-300)
            n_total = n_total * math.exp(lam * dln_total)
        m = m + lam * dm
        if n_c and (m <= 1e-13 * scale).any():
            return n, m, pi, iteration  # a condensed species ran out: the active set must change
        # each recombined row is judged on its own scale, so trace-only rows really close
        residual = b_t - (A @ n if has_gas else 0.0) - (C.T @ m if n_c else 0.0)
        row_scale = np.abs(b_t) + (np.abs(A) @ n if has_gas else 0.0) + (np.abs(C).T @ m if n_c else 0.0)
        balanced = bool((np.abs(residual) <= 1e-10 * row_scale + 1e-14 * _TRACE * scale).all())
        alive = n > 1e-290 if has_gas else np.zeros(0, dtype=bool)
        moved = float(np.abs(dln[alive]).max(initial=0.0)) if has_gas else 0.0
        moved = max(moved, float(np.abs(dm).max(initial=0.0)) / max(scale, 1e-300))
        if lam == 1.0 and moved < 1e-9 and balanced:
            return n, m, pi, iteration
        if has_gas and lam == 1.0 and bool((np.abs(residual) <= 1e-8 * scale).all()):
            # A species the active set can only drive to zero (H2 from CH4 before C(s)
            # joins) makes Newton in ln n step by exactly -1 for ever. Everything else
            # has converged, so stop: π already points at whichever phase resolves it.
            unsettled = alive & (np.abs(dln) > 1e-9)
            dying = (n / n_total < 1e-9) & (np.abs(dln + 1.0) < 0.05)
            if unsettled.any() and bool(np.all(dying[unsettled])):
                return n, m, pi, iteration
    raise EquilibriumError(f"equilibrium Newton did not converge in {_MAX_ITERATIONS} iterations")


@si_arguments(T="temperature", P="pressure")
def gibbs_equilibrium(
    feed: Mapping[str, float],
    species: Sequence[str],
    T: float,
    P: float = 101325.0,
    *,
    thermo: Thermo | None = None,
) -> EquilibriumResult:
    """Equilibrium composition at fixed T and P.

    ``feed`` is mol by species token; ``species`` lists the candidates, gas by default
    and ``"C(s)"``/``"H2O(l)"`` for pure condensed phases. Only candidates can appear:
    the answer is the minimum over that list, so an omitted product stays absent.
    ``thermo`` adds vapour fugacity coefficients from a registered package. A condensed
    candidate whose table does not reach T (a solid above its melting point) cannot
    exist there: it is set aside and named in ``excluded``. A gas out of range raises.
    """
    candidates = [_candidate(token) for token in species]
    keys = [c.key for c in candidates]
    if len(keys) != len(set(keys)):
        raise EquilibriumError("duplicate candidates")
    gas = [c for c in candidates if not c.condensed]
    pool = [c for c in candidates if c.condensed]
    elements, b = _element_table(candidates, feed)
    gas = [c for c in gas if set(c.atoms) <= set(elements)]
    pool = [c for c in pool if set(c.atoms) <= set(elements)]
    unavailable = tuple(c.key for c in pool if not c.thermo.t_range[0] <= T <= c.thermo.t_range[1])
    pool = [c for c in pool if c.key not in unavailable]
    if not gas and not pool:
        raise EquilibriumError("no candidate is made of the feed's elements")

    g0 = np.array([c.thermo.g(T) / (R * T) for c in gas])
    ln_p = math.log(P / P_STANDARD)
    ln_phi = np.zeros(len(gas))
    fugacity_iterations = 0
    for fugacity_iterations in range(1, 101 if thermo is not None else 2):  # noqa: B007
        result = _phase_search(gas, pool, elements, b, g0 + ln_phi, T, ln_p)
        if thermo is None:
            fugacity_iterations = 0
            break
        updated = _vapour_ln_phi(thermo, gas, result[0], T, P)
        change = float(np.abs(updated - ln_phi).max(initial=0.0))
        ln_phi = 0.5 * ln_phi + 0.5 * updated
        if change < 1e-7:
            break
    else:
        raise EquilibriumError("fugacity iteration did not converge in 100 steps")
    n, active, m, pi, iterations = result
    total = float(n.sum())
    gas_amounts = {c.key: float(ni) for c, ni in zip(gas, n, strict=True)}
    condensed = {c.key: float(mi) for c, mi in zip(active, m, strict=True)}
    gibbs = 0.0
    enthalpy = 0.0
    for i, c in enumerate(gas):
        if n[i] > 0.0:
            gibbs += float(n[i]) * R * T * (g0[i] + ln_phi[i] + math.log(n[i] / total) + ln_p)
        enthalpy += float(n[i]) * c.thermo.h(T)
    for c, mi in zip(active, m, strict=True):
        gibbs += float(mi) * c.thermo.g(T)
        enthalpy += float(mi) * c.thermo.h(T)
    return EquilibriumResult(
        T,
        P,
        gas_amounts,
        condensed,
        gibbs,
        enthalpy,
        dict(zip(elements, (float(p) for p in pi), strict=True)),
        iterations,
        fugacity_iterations,
        {c.key: float(v) for c, v in zip(gas, ln_phi, strict=True)} if thermo is not None else {},
        unavailable,
    )


def _vapour_ln_phi(
    thermo: Thermo, gas: Sequence[Candidate], n: NDArray[np.float64], T: float, P: float
) -> NDArray[np.float64]:
    """ln φ of each gas candidate at the current composition, from the package.

    Species at a trace level are kept in the composition (the package needs a
    well-formed mixture) with a floor that does not affect the major species.
    """
    y = np.maximum(n / n.sum(), 1e-12)
    y = y / y.sum()
    cas = {c.key: c.thermo.cas for c in gas}
    composition = {cas[c.key]: float(yi) for c, yi in zip(gas, y, strict=True)}
    props = thermo.phase_props(composition, T, P, PhaseKind.VAPOR)
    return np.array([float(props.ln_phi.get(cas[c.key], 0.0)) for c in gas])


def _condensed_only(
    gas: Sequence[Candidate],
    pool: Sequence[Candidate],
    active: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0: NDArray[np.float64],
    gcond: Mapping[str, float],
    ln_p: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64], str | None] | None:
    """The answer when the active condensed species hold the whole feed and no gas forms.

    The gas iteration cannot reach this state: its total N goes to zero and ln N with
    it. A gas phase forms only if Σ_i exp(Σ_j a_ij π_j − g°_i/RT − ln(P/P°)) > 1, the
    sum of the partial pressures that would sit over the condensed species. Returns
    (amounts, π, a better condensed candidate or None), or None when this is not
    that state and the gas iteration should run.
    """
    if not active:
        return None
    C = np.array([[float(c.atoms.get(e, 0)) for e in elements] for c in active])
    amounts = np.linalg.lstsq(C.T, b, rcond=None)[0]
    if (amounts <= 0.0).any() or float(np.abs(C.T @ amounts - b).max()) > 1e-9 * float(b.sum()):
        return None
    # When the active species lock elements in a fixed ratio (Ca, C and O in CaCO3), π is
    # only known up to a gauge. Stability asks whether *some* π admits it: an LP that
    # maximises the smallest slack t over Cπ = g, a_i·π + t ≤ g_i.
    g_active = np.array([gcond[c.key] for c in active])
    others = [c for c in pool if c not in active]
    bound_rows = [[float(c.atoms.get(e, 0)) for e in elements] for c in [*others, *gas]]
    bounds_rhs = [gcond[c.key] for c in others] + [float(g) + ln_p for g in g0]
    n_e = len(elements)
    if bound_rows:
        A_ub = np.hstack([np.array(bound_rows), np.ones((len(bound_rows), 1))])
        b_ub = np.array(bounds_rhs)
    else:
        A_ub, b_ub = None, None
    cost = np.zeros(n_e + 1)
    cost[-1] = -1.0
    solved = linprog(
        cost,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=np.hstack([C, np.zeros((len(active), 1))]),
        b_eq=g_active,
        bounds=[(None, None)] * n_e + [(None, 1.0)],
    )
    if not solved.success:
        return None  # more condensed species than the elements allow
    pi = np.asarray(solved.x[:n_e], dtype=float)
    if gas:
        A = np.array([[float(c.atoms.get(e, 0)) for e in elements] for c in gas])
        if float(np.exp(np.clip(A @ pi - g0 - ln_p, -700.0, 700.0)).sum()) > 1.0:
            return None
    best, entering = -1e-9, None
    for candidate in others:
        driving = gcond[candidate.key] - sum(
            p * candidate.atoms.get(e, 0) for p, e in zip(pi, elements, strict=True)
        )
        if driving < best:
            best, entering = float(driving), candidate.key
    return amounts, pi, entering


def _phase_search(
    gas: Sequence[Candidate],
    pool: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0: NDArray[np.float64],
    T: float,
    ln_p: float,
) -> tuple[NDArray[np.float64], list[Candidate], NDArray[np.float64], NDArray[np.float64], int]:
    """Active-set loop over the condensed species."""
    active: list[Candidate] = []
    n = np.full(len(gas), max(float(b.sum()), 1e-12) / max(len(gas), 1))
    total_iterations = 0
    gcond = {c.key: c.thermo.g(T) / (R * T) for c in pool}
    tried: set[tuple[str, ...]] = set()
    m = np.zeros(0)
    rejected: set[str] = set()

    def house_elements() -> None:
        """An element no gas holds (the Fe of an oxide, the Ca of a carbonate) needs a
        condensed home before Newton can balance it: seed the cheapest holder per atom."""
        nonlocal m
        for index, element in enumerate(elements):
            if any(element in c.atoms for c in [*gas, *active]):
                continue
            holders = [c for c in pool if element in c.atoms and c.key not in rejected]
            if not holders:
                raise EquilibriumError(f"no candidate holds element {element} at {T} K")
            chosen = min(holders, key=lambda c: gcond[c.key] / c.atoms[element])
            active.append(chosen)
            m = np.append(m, float(b[index]) / chosen.atoms[element])

    house_elements()
    for _ in range(_MAX_PHASE_CHANGES):
        settled = _condensed_only(gas, pool, active, elements, b, g0, gcond, ln_p)
        if settled is not None:
            amounts, potentials, entering_key = settled
            if entering_key is None:
                return np.zeros(len(gas)), active, amounts, potentials, total_iterations
            active.append(next(c for c in pool if c.key == entering_key))
            m = np.append(amounts, 0.01 * float(b.min()))
            continue
        tried.add(tuple(sorted(c.key for c in active)))
        g_active = np.array([gcond[c.key] for c in active])
        try:
            n, m, pi, iterations = _solve_active(gas, active, elements, b, g0, g_active, ln_p, (n, m))
        except EquilibriumError:
            if not active:
                raise
            # A seeded phase can leave no room to balance (CaCO3 with a CO2 atmosphere it
            # should have decomposed into): try the element's next holder.
            rejected.add(active.pop().key)
            m = m[: len(active)]
            n = np.full(len(gas), max(float(b.sum()), 1e-12) / max(len(gas), 1))
            house_elements()
            continue
        total_iterations += iterations
        if active and (m <= 1e-13 * float(b.sum())).any():
            drop = int(np.argmin(m))
            active.pop(drop)
            m = np.delete(m, drop)
            n = np.maximum(n, 1e-20 * max(float(n.sum()), 1e-12))
            house_elements()
            continue
        driving = []
        for candidate in pool:
            if candidate in active:
                continue
            stoich = sum(pi[j] * candidate.atoms.get(e, 0) for j, e in enumerate(elements))
            driving.append((gcond[candidate.key] - stoich, candidate))
        driving = [d for d in driving if d[0] < -1e-9]
        if not driving:
            return n, active, m, pi, total_iterations
        _, entering = min(driving, key=lambda d: d[0])
        trial = sorted([c.key for c in active] + [entering.key])
        if tuple(trial) in tried:
            return n, active, m, pi, total_iterations
        active.append(entering)
        m = np.append(m, 0.01 * float(b.min()) / max(sum(entering.atoms.values()), 1))
    raise EquilibriumError("condensed-phase search did not settle")


@si_arguments(P="pressure", T_in="temperature")
def adiabatic_equilibrium(
    feed: Mapping[str, float],
    species: Sequence[str],
    P: float = 101325.0,
    *,
    T_in: float = T_REF,
    feed_enthalpy: float | None = None,
    bounds: tuple[float, float] = (300.0, 5500.0),
) -> EquilibriumResult:
    """Constant-enthalpy, constant-pressure equilibrium: the flame with dissociation.

    Finds the T where the equilibrium mixture carries the feed enthalpy, by default
    Σ n_i H°_i(T_in) over the feed as gases. Pass ``feed_enthalpy`` (J) for a preheated
    or part-condensed feed.
    """
    if feed_enthalpy is None:
        enthalpy = math.fsum(float(n) * species_thermo(token).h(T_in) for token, n in feed.items())
    else:
        enthalpy = float(feed_enthalpy)

    def residual(T: float) -> float:
        return gibbs_equilibrium(feed, species, T, P).enthalpy - enthalpy

    low, high = bounds
    if residual(low) * residual(high) > 0.0:
        raise EquilibriumError(f"no adiabatic temperature on [{low}, {high}] K")
    return gibbs_equilibrium(feed, species, float(brentq(residual, low, high, xtol=1e-5)), P)


@dataclass(frozen=True)
class ExtentEquilibrium:
    """Equilibrium of a stated reaction list: only these reactions may happen."""

    T: float
    P: float
    extents: dict[str, float]  # mol of reaction, by equation string
    amounts: dict[str, float]  # mol
    constants: dict[str, ReactionThermo]


@si_arguments(T="temperature", P="pressure")
def reaction_equilibrium(
    reactions: Sequence[str | Equation],
    feed: Mapping[str, float],
    T: float,
    P: float = 101325.0,
) -> ExtentEquilibrium:
    """Equilibrium extents of given gas-phase reactions, keeping everything else frozen.

    Unlike :func:`gibbs_equilibrium`, which lets every listed species form, this
    respects kinetic reality: a species reachable only through a reaction not on the
    list stays at its feed amount. Solves Σ_i ν_ij ln a_i = ln K_j(T) for each j by
    damped Newton in the extents, starting from an interior point.
    Species in ``feed`` that no reaction touches count as inerts.
    """
    equations = [balance(r) if isinstance(r, str) else r for r in reactions]
    if not equations:
        raise EquilibriumError("no reactions given")
    phases: dict[str, str] = {}
    keys: list[str] = list(feed)
    for eq in equations:
        for term in eq.terms:
            if term.key not in keys:
                keys.append(term.key)
            phases[term.key] = term.phase or "gas"
    condensed = sorted(k for k, phase in phases.items() if phase not in ("gas", None))
    if condensed:
        raise EquilibriumError(f"reaction_equilibrium is gas-phase; use gibbs_equilibrium for {condensed}")
    thermo = [reaction_thermo(eq, T, phases={t.key: "gas" for t in eq.terms}) for eq in equations]
    ln_k = np.array([t.lnK for t in thermo])
    nu = np.array([[eq.nu.get(key, 0.0) for key in keys] for eq in equations])
    n0 = np.array([float(feed.get(key, 0.0)) for key in keys])
    if (n0 < 0.0).any():
        raise EquilibriumError("negative feed amount")
    ln_p = math.log(P / P_STANDARD)
    # products absent from the feed sit on a singular log, so start from an interior point
    xi = _interior_start(nu, n0)

    def residual(extent: NDArray[np.float64]) -> NDArray[np.float64]:
        n = n0 + nu.T @ extent
        y = n / n.sum()
        return np.asarray(nu @ (np.log(y) + ln_p) - ln_k, dtype=float)

    for _ in range(_MAX_ITERATIONS):
        f = residual(xi)
        if float(np.abs(f).max()) < 1e-10:
            break
        n = n0 + nu.T @ xi
        total = float(n.sum())
        jac = nu @ np.diag(1.0 / n) @ nu.T - np.outer(nu.sum(axis=1), nu.sum(axis=1)) / total
        step = np.linalg.solve(jac, -f)
        lam = 1.0
        for _ in range(60):
            trial = n0 + nu.T @ (xi + lam * step)
            if (trial > 0.0).all() and np.abs(residual(xi + lam * step)).max() < np.abs(f).max() * (
                1 - 1e-4 * lam
            ):
                break
            lam *= 0.5
        xi = xi + lam * step
    else:
        raise EquilibriumError("reaction equilibrium Newton did not converge")
    amounts = n0 + nu.T @ xi
    return ExtentEquilibrium(
        T,
        P,
        {str(eq): float(x) for eq, x in zip(equations, xi, strict=True)},
        {key: float(n) for key, n in zip(keys, amounts, strict=True)},
        {str(eq): t for eq, t in zip(equations, thermo, strict=True)},
    )


def _interior_start(nu: NDArray[np.float64], n0: NDArray[np.float64]) -> NDArray[np.float64]:
    """Extents that leave every species present, by the LP max t: n0 + νᵀξ ≥ t."""
    n_reactions, n_species = nu.shape
    cost = np.zeros(n_reactions + 1)
    cost[-1] = -1.0
    constraint = np.hstack([-nu.T, np.ones((n_species, 1))])
    solved = linprog(
        cost, A_ub=constraint, b_ub=n0, bounds=[(None, None)] * n_reactions + [(None, float(n0.sum()))]
    )
    if not solved.success or float(solved.x[-1]) <= 0.0:
        raise EquilibriumError(
            "no composition has every species present: the feed lacks what the reactions consume"
        )
    return np.asarray(solved.x[:-1], dtype=float)


__all__ = [
    "PHASES",
    "EquilibriumError",
    "EquilibriumResult",
    "ExtentEquilibrium",
    "adiabatic_equilibrium",
    "gibbs_equilibrium",
    "reaction_equilibrium",
]
