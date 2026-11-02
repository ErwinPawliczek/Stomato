"""Chemical equilibrium: multiphase Gibbs minimisation and reaction extents.

:func:`gibbs_equilibrium` minimises the total Gibbs energy of the mixture phases plus
any number of pure condensed species over the element balances, with the reduced Newton
iteration of the NASA CEA code (Gordon & McBride, NASA RP-1311, 1994, eqs. 2.24-2.26),
extended here to several mixture phases: unknowns are the element potentials π_j, the
condensed amounts and one Δln N per mixture phase, from which each Δln n_i follows. The
mixture phases are the gas, one liquid solution on the pure-liquid standard state, and
water with its solutes on the 1 molal standard state. The condensed species present
are found by an active set: after each converged gas-phase solve, the candidate
with the most negative driving force μ_c/RT − Σ_j a_cj π_j joins (CEA §3.5), and a
species whose amount goes negative leaves.

Non-ideality enters by successive substitution: with its terms frozen the solve is
ideal, then the terms are re-evaluated at the composition found, until they settle.
Those terms are ln φ_i of the vapour from ``thermo=``, ln γ_i of the solution from
``activity=`` (ln φ_i(x) − ln φ_i(pure) of any registered package), and for solutes the
mole-fraction-to-molality shift plus Davies (1962) activity coefficients.

This is the one Gibbs solver: the reactor units reach it through
:mod:`ngdesign.units._physics.gibbs`, and ``ngdesign.chem.equilibrium`` re-exports it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import scipy.constants as sc
from chemicals.iapws import iapws95_rho
from chemicals.permittivity import permittivity_IAPWS
from numpy.typing import NDArray
from scipy.optimize import brentq, linprog

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.data import chemdb
from ngdesign.data.rational import rref
from ngdesign.data.species_models import T_REF, SpeciesThermo, species_thermo
from ngdesign.uom.quantity import si_arguments

#: CODATA 2018 molar gas constant, J/(mol K).
R = sc.R
#: Standard-state pressure of the species models, Pa.
P_STANDARD = 1.0e5

#: Trace-species floor as a fraction of the total: below it a mole number stops
#: steering Newton (CEA's SIZE parameter plays this role).
_TRACE = 1e-28
_MAX_ITERATIONS = 500
_MAX_PHASE_CHANGES = 40
_MAX_NONIDEAL_PASSES = 200
#: A mixture phase below this share of the atoms is dropped; the entry test can restore it.
_PHASE_FLOOR = 1e-6
#: How often one phase may leave and return in one search.
_MAX_PHASE_FLIPS = 4
#: Fraction of the mixture moved into a mixture phase when it first appears.
_PHASE_SEED = 0.3

#: Mixture phases. Each has its own total, so a species' mole fraction is within it.
GAS = "gas"
SOLUTION = "solution"
AQUEOUS = "aqueous"
#: The pseudo-element that carries charge through the balance rows.
CHARGE = "q"
_WATER_CAS = "7732-18-5"
#: kg/mol, from the IAPWS-95 molar mass used by the water reference equation.
_WATER_KG_PER_MOL = 0.018015268
#: Davies (1962) holds to roughly this ionic strength, mol/kg.
_DAVIES_LIMIT = 0.5


class EquilibriumError(ValueError):
    """An equilibrium problem is ill-posed or did not converge."""


@dataclass(frozen=True)
class Candidate:
    """One species-in-a-phase the solver may use."""

    key: str
    thermo: SpeciesThermo | None  # None for a fixed-amount inert: it has no potential to minimise
    atoms: dict[str, int]
    group: str | None = GAS  # the mixture phase it belongs to; None for a pure condensed species
    solvent: bool = False
    charge: int = 0


def _in_range(candidate: Candidate, T: float) -> bool:
    thermo = candidate.thermo
    return thermo is None or thermo.t_range[0] <= T <= thermo.t_range[1]


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
    solution: dict[str, float] = field(default_factory=dict)  # mol, liquid-solution species
    aqueous: dict[str, float] = field(default_factory=dict)  # mol, water and its solutes
    ionic_strength: float = 0.0  # mol/kg

    @property
    def gas_total(self) -> float:
        return math.fsum(self.gas.values())

    @property
    def mole_fractions(self) -> dict[str, float]:
        """Gas-phase mole fractions."""
        total = self.gas_total
        return {key: n / total for key, n in self.gas.items()} if total > 0.0 else {}

    @property
    def solution_fractions(self) -> dict[str, float]:
        """Liquid-solution mole fractions."""
        total = math.fsum(self.solution.values())
        return {key: n / total for key, n in self.solution.items()} if total > 0.0 else {}

    def molality(self, key: str) -> float:
        """mol/kg water of one aqueous species."""
        return self.aqueous[key] / (self.aqueous["H2O(aq)"] * _WATER_KG_PER_MOL)

    @property
    def pH(self) -> float:  # noqa: N802 -- the name of the quantity
        """−log10 a(H+), with the Davies activity coefficient of the converged ionic strength."""
        ln_gamma = davies_ln_gamma(1, self.ionic_strength, debye_huckel_a(self.T))
        return float(-(math.log(self.molality("H+(aq)")) + ln_gamma) / math.log(10.0))


_SUFFIXES = (
    ("(l)", "liquid", None),
    ("(s)", "solid", None),
    ("(cr)", "solid", None),
    ("(sln)", "liquid", SOLUTION),
    ("(aq)", AQUEOUS, AQUEOUS),
    ("(g)", "gas", GAS),
)


def phase_of(token: str) -> str:
    """The phase a candidate token names: gas unless suffixed."""
    text = token.strip()
    return next((phase for suffix, phase, _ in _SUFFIXES if text.endswith(suffix)), "gas")


def species_of(token: str) -> str:
    """A candidate token without its phase suffix."""
    return _strip_phase(token)


def _candidate(token: str) -> Candidate:
    """A token to a candidate; a bare token is the gas."""
    text = token.strip()
    species = _strip_phase(text)
    phase: str = "gas"
    group: str | None = GAS
    for suffix, name, mixture in _SUFFIXES:
        if text.endswith(suffix):
            phase, group = name, mixture
            break
    record = chemdb.find(species)
    atoms = dict(chemdb.composition(record.cas))
    if group == AQUEOUS and record.cas == _WATER_CAS:
        return Candidate(text, species_thermo(record.cas, "liquid"), atoms, AQUEOUS, solvent=True)
    if record.charge:
        atoms[CHARGE] = record.charge
    return Candidate(text, species_thermo(record.cas, phase), atoms, group, charge=record.charge)


def _element_table(
    candidates: Sequence[Candidate], feed: Mapping[str, float]
) -> tuple[list[str], NDArray[np.float64]]:
    """(elements, b): atoms in the feed, refusing any no candidate can hold.

    Charge is a conserved row like an element, so a solution stays electroneutral
    whatever it speciates into.
    """
    budget: dict[str, float] = {}
    for token, amount in feed.items():
        if amount < 0.0:
            raise EquilibriumError(f"negative feed amount for {token!r}")
        record = chemdb.find(_strip_phase(token))
        for element, count in chemdb.composition(record.cas).items():
            budget[element] = budget.get(element, 0.0) + count * float(amount)
        if record.charge:
            budget[CHARGE] = budget.get(CHARGE, 0.0) + record.charge * float(amount)
    held = {element for c in candidates for element in c.atoms}
    orphan = sorted(set(budget) - held)
    if orphan:
        raise EquilibriumError(f"no candidate holds element(s) {orphan}")
    elements = sorted(element for element, amount in budget.items() if amount > 0.0 and element != CHARGE)
    if not elements:
        raise EquilibriumError("the feed is empty")
    if CHARGE in held:
        elements.append(CHARGE)
    return elements, np.array([budget.get(element, 0.0) for element in elements])


def _strip_phase(token: str) -> str:
    text = token.strip()
    for suffix, _, _ in _SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


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
    reduced, pivots = rref(ordered, len(key))
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
    mix: Sequence[Candidate],
    groups: NDArray[np.int64],
    condensed: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0_mix: NDArray[np.float64],
    g0_cond: NDArray[np.float64],
    start: tuple[NDArray[np.float64], NDArray[np.float64]],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], int]:
    """Newton on the reduced Gibbs equations for a fixed active set.

    CEA's iteration, extended from one mixture phase to several: ``groups[i]`` is the
    mixture phase of species i, and each phase carries its own total N_p and its own
    row, so μ_i/RT = g°_i + ln(n_i/N_p) with ``g0_mix`` already holding the pressure,
    fugacity, activity and molality terms. Returns mixture amounts, condensed amounts,
    element potentials and iterations; it returns early when a phase or a condensed
    species runs out, so the caller can change the active set.
    """
    A_int = [[c.atoms.get(e, 0) for c in mix] for e in elements]
    C_int = [[c.atoms.get(e, 0) for e in elements] for c in condensed]
    b_exact = [Fraction(float(value)) for value in b]
    n, m = start[0].copy(), start[1].copy()
    labels = sorted(set(int(g) for g in groups))
    member = [groups == label for label in labels]
    totals = np.array([float(n[mask].sum()) for mask in member])
    n_elements, n_c, n_p = len(elements), len(condensed), len(labels)
    has_mix = n.size > 0
    pi = np.zeros(n_elements)
    scale = float(np.abs(b).sum())
    basis: _Basis | None = None
    for iteration in range(1, _MAX_ITERATIONS + 1):
        order = tuple(int(j) for j in np.argsort(-np.concatenate([n, m]), kind="stable"))
        if basis is None or basis.key[: n_elements + 1] != order[: n_elements + 1]:
            basis = _make_basis(order, A_int, C_int, b_exact)
        A, C, b_t = basis.A, basis.C, basis.b
        n_e = A.shape[0]
        phase_total = totals[np.searchsorted(labels, groups)] if has_mix else np.zeros(0)
        mu = g0_mix + np.log(np.maximum(n, 1e-300)) - np.log(phase_total) if has_mix else np.zeros(0)
        weighted = A * n
        size = n_e + n_c + n_p
        J = np.zeros((size, size))
        rhs = np.zeros(size)
        J[:n_e, :n_e] = weighted @ A.T
        rhs[:n_e] = b_t - A @ n - (C.T @ m if n_c else 0.0) + weighted @ mu
        if n_c:
            J[:n_e, n_e : n_e + n_c] = C.T
            J[n_e : n_e + n_c, :n_e] = C
            rhs[n_e : n_e + n_c] = g0_cond
        for p, mask in enumerate(member):
            row = n_e + n_c + p
            column = weighted[:, mask].sum(axis=1)
            J[:n_e, row] = column
            J[row, :n_e] = column
            amount = float(n[mask].sum())
            J[row, row] = amount - totals[p]
            rhs[row] = totals[p] - amount + float(n[mask] @ mu[mask])
        step = _solve_scaled(J, rhs)
        pi_basis = step[:n_e]
        pi = basis.T.T @ pi_basis
        dm = step[n_e : n_e + n_c]
        dln_totals = step[n_e + n_c :]
        dln = dln_totals[np.searchsorted(labels, groups)] + A.T @ pi_basis - mu if has_mix else np.zeros(0)
        # CEA damping: bound the largest log step of the major species and each total.
        lam = 1.0
        if has_mix:
            fraction = n / phase_total
            major = fraction > 1e-10
            largest = max(
                5.0 * float(np.abs(dln_totals).max(initial=0.0)), float(np.abs(dln[major]).max(initial=0.0))
            )
            if largest > 2.0:
                lam = 2.0 / largest
            minor_up = (~major) & (dln > 0.0)
            if minor_up.any():
                shift = dln_totals[np.searchsorted(labels, groups)]
                headroom = (-np.log(fraction[minor_up]) - 9.2) / (dln[minor_up] - shift[minor_up] + 1e-300)
                bounded = headroom[headroom > 0.0]
                if bounded.size:
                    lam = min(lam, float(np.abs(bounded).min()))
        if n_c:
            shrink = m + lam * dm
            if (shrink < 0.0).any():
                ratios = -m[dm < 0.0] / dm[dm < 0.0]
                lam = min(lam, float(ratios.min()) * 0.999 if ratios.size else lam)
        if has_mix:
            n = np.maximum(n * np.exp(np.clip(lam * dln, -700.0, 700.0)), 1e-300)
            totals = totals * np.exp(lam * dln_totals)
        m = m + lam * dm
        if n_c and (m <= 1e-13 * scale).any():
            return n, m, pi, iteration  # a condensed species ran out: the active set must change
        if n_p > 1 and (totals < _PHASE_FLOOR * scale).any():
            # A vanishing phase takes its row of J to zero and Newton goes wild before
            # the phase reaches zero, so the active set has to change before that.
            return n, m, pi, iteration
        # each recombined row is judged on its own scale, so trace-only rows really close
        residual = b_t - (A @ n if has_mix else 0.0) - (C.T @ m if n_c else 0.0)
        row_scale = np.abs(b_t) + (np.abs(A) @ n if has_mix else 0.0) + (np.abs(C).T @ m if n_c else 0.0)
        balanced = bool((np.abs(residual) <= 1e-10 * row_scale + 1e-14 * _TRACE * scale).all())
        alive = n > 1e-290 if has_mix else np.zeros(0, dtype=bool)
        moved = float(np.abs(dln[alive]).max(initial=0.0)) if has_mix else 0.0
        moved = max(moved, float(np.abs(dm).max(initial=0.0)) / max(scale, 1e-300))
        if lam == 1.0 and moved < 1e-9 and balanced:
            return n, m, pi, iteration
        if has_mix and lam == 1.0 and bool((np.abs(residual) <= 1e-8 * scale).all()):
            # A species the active set can only drive to zero (H2 from CH4 before C(s)
            # joins) makes Newton in ln n step by exactly -1 for ever. Everything else
            # has converged, so stop: π already points at whichever phase resolves it.
            unsettled = alive & (np.abs(dln) > 1e-9)
            dying = (n / n.sum() < 1e-9) & (np.abs(dln + 1.0) < 0.05)
            if unsettled.any() and bool(np.all(dying[unsettled])):
                return n, m, pi, iteration
    raise EquilibriumError(f"equilibrium Newton did not converge in {_MAX_ITERATIONS} iterations")


def _vapour_ln_phi(
    thermo: Thermo, gas: Sequence[Candidate], n: NDArray[np.float64], T: float, P: float
) -> NDArray[np.float64]:
    """ln φ of each gas candidate at the current composition, from the package.

    Species at a trace level are kept in the composition (the package needs a
    well-formed mixture) with a floor that does not affect the major species.
    """
    y = np.maximum(n / n.sum(), 1e-12)
    y = y / y.sum()
    cas = {c.key: c.thermo.cas for c in gas if c.thermo is not None}
    composition = {cas[c.key]: float(yi) for c, yi in zip(gas, y, strict=True)}
    props = thermo.phase_props(composition, T, P, PhaseKind.VAPOR)
    return np.array([float(props.ln_phi.get(cas[c.key], 0.0)) for c in gas])


def _liquid_ln_gamma(
    activity: Thermo, solution: Sequence[Candidate], x: NDArray[np.float64], T: float, P: float
) -> NDArray[np.float64]:
    """ln γ_i = ln φ_i(x) − ln φ_i(pure) from a package's liquid fugacities.

    On the pure-liquid standard state, so γ → 1 as x_i → 1, for any registered package.
    """
    fractions = np.maximum(x / x.sum(), 1e-12)
    fractions = fractions / fractions.sum()
    cas = [c.thermo.cas for c in solution if c.thermo is not None]
    mixed = activity.phase_props(
        dict(zip(cas, map(float, fractions), strict=True)), T, P, PhaseKind.HC_LIQUID
    )
    gamma = np.zeros(len(cas))
    for i, identity in enumerate(cas):
        pure = activity.phase_props({identity: 1.0}, T, P, PhaseKind.HC_LIQUID)
        gamma[i] = float(mixed.ln_phi[identity]) - float(pure.ln_phi[identity])
    return gamma


def debye_huckel_a(T: float) -> float:
    """Debye-Hückel A, kg^0.5/mol^0.5: 1.82483e6·ρ^0.5·(εT)^-1.5, with ρ in kg/L.

    Water density from IAPWS-95 and relative permittivity from the IAPWS formulation,
    both through ``chemicals``, so A follows T rather than sitting at its 25 °C value.
    """
    rho = float(iapws95_rho(T, 101325.0))  # type: ignore[no-untyped-call]
    return float(1.82483e6 * math.sqrt(rho / 1000.0) * (float(permittivity_IAPWS(T, rho)) * T) ** -1.5)


def davies_ln_gamma(charge: int, ionic_strength: float, A: float) -> float:
    """Davies (1962): log10 γ = −A z² (√I/(1 + √I) − 0.3 I); a neutral solute keeps γ = 1."""
    root = math.sqrt(ionic_strength)
    return float(-A * charge * charge * (root / (1.0 + root) - 0.3 * ionic_strength) * math.log(10.0))


def _condensed_only(
    mix: Sequence[Candidate],
    pool: Sequence[Candidate],
    active: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0: NDArray[np.float64],
    gcond: Mapping[str, float],
) -> tuple[NDArray[np.float64], NDArray[np.float64], str | None] | None:
    """The answer when the active condensed species hold the whole feed and no mixture forms.

    The mixture iteration cannot reach this state: its total N goes to zero and ln N
    with it. A mixture phase forms only if Σ_i exp(Σ_j a_ij π_j − g_i) > 1 over its
    species, the sum of the fractions it would have over the condensed species. Returns
    (amounts, π, a better condensed candidate or None), or None when this is not that
    state and the mixture iteration should run.
    """
    if not active or any(c.group == AQUEOUS for c in mix):
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
    bound_rows = [[float(c.atoms.get(e, 0)) for e in elements] for c in [*others, *mix]]
    bounds_rhs = [gcond[c.key] for c in others] + [float(g) for g in g0]
    n_e = len(elements)
    A_ub, b_ub = None, None
    if bound_rows:
        A_ub = np.hstack([np.array(bound_rows), np.ones((len(bound_rows), 1))])
        b_ub = np.array(bounds_rhs)
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
    if mix:
        A = np.array([[float(c.atoms.get(e, 0)) for e in elements] for c in mix])
        exponent = np.clip(A @ pi - g0, -700.0, 700.0)
        for group in {c.group for c in mix}:
            mask = np.array([c.group == group for c in mix])
            if float(np.exp(exponent[mask]).sum()) > 1.0:
                return None
    best, entering = -1e-9, None
    for candidate in others:
        driving = gcond[candidate.key] - sum(
            p * candidate.atoms.get(e, 0) for p, e in zip(pi, elements, strict=True)
        )
        if driving < best:
            best, entering = float(driving), candidate.key
    return amounts, pi, entering


@dataclass
class _Search:
    """What a phase search keeps between fugacity and activity passes."""

    on: set[str]
    amounts: dict[str, float]


def _phase_search(
    mix: Sequence[Candidate],
    pool: Sequence[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    g0: Mapping[str, float],
    T: float,
    state: _Search,
    ln_gamma_trial: Callable[[NDArray[np.float64]], NDArray[np.float64]] | None,
) -> tuple[dict[str, float], list[Candidate], NDArray[np.float64], NDArray[np.float64], int]:
    """Active-set loop over the condensed species and the mixture phases that are on."""
    active: list[Candidate] = []
    total_iterations = 0
    gcond = {c.key: c.thermo.g(T) / (R * T) for c in pool if c.thermo is not None}
    tried: set[tuple[str, ...]] = set()
    m = np.zeros(0)
    rejected: set[str] = set()
    flips: dict[str, int] = {}
    pi = np.zeros(len(elements))
    index: dict[str | None, int] = {GAS: 0, SOLUTION: 1, AQUEOUS: 2}

    def house_elements() -> None:
        """An element no mixture holds (the Fe of an oxide, the Ca of a carbonate) needs a
        condensed home before Newton can balance it: seed the cheapest holder per atom."""
        nonlocal m
        for position, element in enumerate(elements):
            if any(element in c.atoms for c in [*mix, *active]):
                continue
            holders = [c for c in pool if element in c.atoms and c.key not in rejected]
            if not holders:
                raise EquilibriumError(f"no candidate holds element {element} at {T} K")
            chosen = min(holders, key=lambda c: gcond[c.key] / c.atoms[element])
            active.append(chosen)
            m = np.append(m, float(b[position]) / chosen.atoms[element])

    house_elements()
    for _ in range(_MAX_PHASE_CHANGES):
        g_all = np.array([g0[c.key] for c in mix])
        settled = _condensed_only(mix, pool, active, elements, b, g_all, gcond)
        if settled is not None:
            amounts, potentials, entering_key = settled
            if entering_key is None:
                state.on.clear()
                return {}, active, amounts, potentials, total_iterations
            active.append(next(c for c in pool if c.key == entering_key))
            m = np.append(amounts, 0.01 * float(b.min()))
            continue
        tried.add(tuple(sorted(c.key for c in active)))
        on = [c for c in mix if c.group in state.on]
        n = np.array([state.amounts[c.key] for c in on])
        groups = np.array([index[c.group] for c in on], dtype=np.int64)
        g_on = np.array([g0[c.key] for c in on])
        g_active = np.array([gcond[c.key] for c in active])
        try:
            n, m, pi, iterations = _solve_active(on, groups, active, elements, b, g_on, g_active, (n, m))
        except EquilibriumError:
            if not active:
                raise
            # A seeded phase can leave no room to balance (CaCO3 with a CO2 atmosphere it
            # should have decomposed into): try the element's next holder.
            rejected.add(active.pop().key)
            m = m[: len(active)]
            house_elements()
            continue
        total_iterations += iterations
        state.amounts.update({c.key: float(v) for c, v in zip(on, n, strict=True)})
        if active and (m <= 1e-13 * float(b.sum())).any():
            drop = int(np.argmin(m))
            active.pop(drop)
            m = np.delete(m, drop)
            house_elements()
            continue
        vanished = [
            group
            for group in sorted(state.on)
            if len(state.on) > 1
            and math.fsum(state.amounts[c.key] for c in on if c.group == group)
            < _PHASE_FLOOR * float(b.sum())
        ]
        if vanished:
            state.on.discard(vanished[0])
            flips[vanished[0]] = flips.get(vanished[0], 0) + 1
            continue
        if any(
            flips.get(group, 0) < _MAX_PHASE_FLIPS
            and _phase_enters(group, mix, elements, pi, g0, state, b, ln_gamma_trial)
            for group in (GAS, SOLUTION)
        ):
            continue
        driving = []
        for candidate in pool:
            if candidate in active:
                continue
            stoich = sum(pi[j] * candidate.atoms.get(e, 0) for j, e in enumerate(elements))
            driving.append((gcond[candidate.key] - stoich, candidate))
        driving = [d for d in driving if d[0] < -1e-9]
        if not driving:
            return dict(state.amounts), active, m, pi, total_iterations
        _, entering = min(driving, key=lambda d: d[0])
        trial = sorted([c.key for c in active] + [entering.key])
        if tuple(trial) in tried:
            return dict(state.amounts), active, m, pi, total_iterations
        active.append(entering)
        m = np.append(m, 0.01 * float(b.min()) / max(sum(entering.atoms.values()), 1))
    raise EquilibriumError("condensed-phase search did not settle")


def _phase_enters(
    group: str,
    mix: Sequence[Candidate],
    elements: Sequence[str],
    pi: NDArray[np.float64],
    g0: Mapping[str, float],
    state: _Search,
    b: NDArray[np.float64],
    ln_gamma_trial: Callable[[NDArray[np.float64]], NDArray[np.float64]] | None,
) -> bool:
    """Turn a mixture phase on when Σ_i exp(a_i·π − g_i − ln γ_i) > 1.

    The sum is the Michelsen tangent-plane test: at the current potentials the trial
    composition x_i ∝ exp(a_i·π − g_i − ln γ_i(x)) would have lower Gibbs energy than the
    system when it exceeds 1. Species start from that composition.
    """
    members = [c for c in mix if c.group == group]
    if not members or group in state.on:
        return False
    A = np.array([[float(c.atoms.get(e, 0)) for e in elements] for c in members])
    base = A @ pi - np.array([g0[c.key] for c in members])
    trial = np.exp(np.clip(base, -700.0, 700.0))
    total = float(trial.sum())
    for _ in range(8):
        if group != SOLUTION or ln_gamma_trial is None or total <= 0.0:
            break
        trial = np.exp(np.clip(base - ln_gamma_trial(trial / total), -700.0, 700.0))
        total = float(trial.sum())
    if total <= 1.0 + 1e-9:
        return False
    # start from a real split of what is there: a trace seed leaves Newton so far out
    # that its damping stalls
    held = math.fsum(state.amounts[c.key] for c in mix if c.group in state.on)
    moved = _PHASE_SEED * held if held > 0.0 else float(b.sum())
    for candidate in mix:
        if candidate.group in state.on:
            state.amounts[candidate.key] *= 1.0 - _PHASE_SEED
    state.on.add(group)
    for candidate, value in zip(members, trial / total, strict=True):
        state.amounts[candidate.key] = max(float(value) * moved, 1e-30)
    return True


@si_arguments(T="temperature", P="pressure")
def gibbs_equilibrium(
    feed: Mapping[str, float],
    species: Sequence[str],
    T: float,
    P: float = 101325.0,
    *,
    thermo: Thermo | None = None,
    activity: Thermo | None = None,
    inerts: Mapping[str, float] | None = None,
) -> EquilibriumResult:
    """Equilibrium composition at fixed T and P.

    ``feed`` is mol by species token. ``species`` lists the candidates: a bare token is a
    gas; ``"C(s)"``/``"H2O(l)"`` are pure condensed phases; ``"EtOH(sln)"`` is a member
    of the one liquid solution; ``"Na+(aq)"`` is a solute in water, with ``"H2O(aq)"`` as
    the solvent. Only candidates can appear: the answer is the minimum over that list,
    so an omitted product stays absent.

    ``thermo`` adds vapour fugacity coefficients from a registered package and
    ``activity`` liquid-solution activity coefficients; the solution is ideal without
    one. Solutes use Davies activity coefficients up to I = 0.5 mol/kg, above which the
    result refuses. A condensed candidate whose table does not reach T (a solid above its
    melting point) cannot exist there: it is set aside and named in ``excluded``. A
    gas out of range raises. ``inerts`` (mol by id) are gas spectators: they dilute but
    do not react, and they need no data, because each holds a private element of its
    own. They appear in ``gas``, carry no enthalpy here, and exclude ``thermo``.
    """
    if inerts and thermo is not None:
        raise EquilibriumError("inerts have no identity for a fugacity model; list them as species")
    candidates = [_candidate(token) for token in species]
    keys = [c.key for c in candidates]
    spectators = dict(inerts or {})
    if len(keys) != len(set(keys)):
        raise EquilibriumError("duplicate candidates")
    mix = [c for c in candidates if c.group is not None]
    pool = [c for c in candidates if c.group is None]
    elements, b = _element_table(candidates, feed)
    mix = [c for c in mix if set(c.atoms) <= set(elements)]
    pool = [c for c in pool if set(c.atoms) <= set(elements)]
    for key, amount in spectators.items():
        private = f"@{key}"
        mix.append(Candidate(key, None, {private: 1}, GAS))
        elements = [*elements, private]
        b = np.append(b, float(amount))
    unavailable = tuple(c.key for c in pool if not _in_range(c, T))
    pool = [c for c in pool if c.key not in unavailable]
    if not mix and not pool:
        raise EquilibriumError("no candidate is made of the feed's elements")
    return _iterate_nonideal(mix, pool, elements, b, T, P, thermo, activity, unavailable)


def _start_amounts(mix: Sequence[Candidate], b: NDArray[np.float64]) -> dict[str, float]:
    """Starting amounts: an even gas and solution, solutes well below their solvent."""
    total = max(float(np.abs(b).sum()), 1e-12)
    start: dict[str, float] = {}
    for c in mix:
        if c.group == AQUEOUS:
            start[c.key] = total / 3.0 if c.solvent else total * 1e-6
        else:
            start[c.key] = total / max(len(mix), 1)
    return start


def _iterate_nonideal(
    mix: list[Candidate],
    pool: list[Candidate],
    elements: Sequence[str],
    b: NDArray[np.float64],
    T: float,
    P: float,
    thermo: Thermo | None,
    activity: Thermo | None,
    unavailable: tuple[str, ...],
) -> EquilibriumResult:
    """Solve with the non-ideal terms frozen, update them, repeat until they settle."""
    ln_p = math.log(P / P_STANDARD)
    gas = [c for c in mix if c.group == GAS]
    solution = [c for c in mix if c.group == SOLUTION]
    aqueous = [c for c in mix if c.group == AQUEOUS]
    solvent = next((c for c in aqueous if c.solvent), None)
    if aqueous and solvent is None:
        raise EquilibriumError("aqueous candidates need the solvent H2O(aq) in the list")
    base = {c.key: (c.thermo.g(T) / (R * T) if c.thermo is not None else 0.0) for c in mix}
    offset = {c.key: 0.0 for c in mix}
    offset.update({c.key: ln_p for c in gas})
    A_dh = debye_huckel_a(T) if aqueous else 0.0
    ionic = 0.0
    state = _Search({c.group for c in mix if c.group not in (None, SOLUTION)}, _start_amounts(mix, b))
    if solution and not (gas or aqueous):
        state.on.add(SOLUTION)

    def ln_gamma_trial(x: NDArray[np.float64]) -> NDArray[np.float64]:
        assert activity is not None
        return _liquid_ln_gamma(activity, solution, x, T, P)

    trial = ln_gamma_trial if activity is not None else None
    needs_updates = thermo is not None or activity is not None or bool(aqueous)
    passes = 0
    for passes in range(1, _MAX_NONIDEAL_PASSES + 1):  # noqa: B007
        g0 = {key: base[key] + offset[key] for key in base}
        amounts, active, m, pi, iterations = _phase_search(mix, pool, elements, b, g0, T, state, trial)
        if not needs_updates:
            break
        updated = dict(offset)
        if thermo is not None and GAS in state.on and gas:
            n_gas = np.array([amounts[c.key] for c in gas])
            for c, value in zip(gas, _vapour_ln_phi(thermo, gas, n_gas, T, P), strict=True):
                updated[c.key] = ln_p + float(value)
        if activity is not None and SOLUTION in state.on:
            x = np.array([amounts[c.key] for c in solution])
            for c, value in zip(solution, _liquid_ln_gamma(activity, solution, x, T, P), strict=True):
                updated[c.key] = float(value)
        if aqueous and AQUEOUS in state.on and solvent is not None:
            n_total = math.fsum(amounts[c.key] for c in aqueous)
            kg_water = amounts[solvent.key] * _WATER_KG_PER_MOL
            ionic = 0.5 * math.fsum(amounts[c.key] / kg_water * c.charge**2 for c in aqueous)
            x_water = amounts[solvent.key] / n_total
            for c in aqueous:
                if not c.solvent:
                    updated[c.key] = -math.log(x_water * _WATER_KG_PER_MOL) + davies_ln_gamma(
                        c.charge, ionic, A_dh
                    )
        change = max((abs(updated[key] - offset[key]) for key in offset), default=0.0)
        offset = {key: 0.5 * offset[key] + 0.5 * updated[key] for key in offset}
        if change < 1e-7:
            break
    else:
        raise EquilibriumError(f"non-ideal terms did not settle in {_MAX_NONIDEAL_PASSES} passes")
    if ionic > _DAVIES_LIMIT:
        raise EquilibriumError(
            f"ionic strength {ionic:.3g} mol/kg is past the Davies range ({_DAVIES_LIMIT})"
        )
    return _result(
        mix,
        active,
        m,
        pi,
        elements,
        amounts,
        state.on,
        base,
        offset,
        T,
        P,
        iterations,
        passes,
        unavailable,
        ionic,
    )


def _result(
    mix: Sequence[Candidate],
    active: Sequence[Candidate],
    m: NDArray[np.float64],
    pi: NDArray[np.float64],
    elements: Sequence[str],
    amounts: Mapping[str, float],
    on: set[str],
    base: Mapping[str, float],
    offset: Mapping[str, float],
    T: float,
    P: float,
    iterations: int,
    passes: int,
    unavailable: tuple[str, ...],
    ionic: float,
) -> EquilibriumResult:
    """Totals and bookkeeping of a converged composition."""
    by_group: dict[str, dict[str, float]] = {GAS: {}, SOLUTION: {}, AQUEOUS: {}}
    gibbs = enthalpy = 0.0
    for group, members in ((g, [c for c in mix if c.group == g]) for g in by_group):
        total = math.fsum(amounts.get(c.key, 0.0) for c in members) if group in on else 0.0
        for c in members:
            n = amounts.get(c.key, 0.0) if group in on else 0.0
            by_group[group][c.key] = n
            if n > 0.0:
                gibbs += n * R * T * (base[c.key] + offset[c.key] + math.log(n / total))
                enthalpy += n * (c.thermo.h(T) if c.thermo is not None else 0.0)
    for c, mi in zip(active, m, strict=True):
        assert c.thermo is not None
        gibbs += float(mi) * c.thermo.g(T)
        enthalpy += float(mi) * c.thermo.h(T)
    ln_p = math.log(P / P_STANDARD)
    nonideal = {c.key: offset[c.key] - ln_p for c in mix if c.group == GAS}
    return EquilibriumResult(
        T,
        P,
        by_group[GAS],
        {c.key: float(mi) for c, mi in zip(active, m, strict=True)},
        gibbs,
        enthalpy,
        {e: float(p) for e, p in zip(elements, pi, strict=True) if e[0] != "@"},
        iterations,
        passes,
        nonideal if any(abs(v) > 0.0 for v in nonideal.values()) else {},
        unavailable,
        by_group[SOLUTION],
        by_group[AQUEOUS],
        ionic,
    )


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
