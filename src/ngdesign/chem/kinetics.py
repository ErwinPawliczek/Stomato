"""Chemical kinetics: rate constants, mechanisms and reactor integration.

Rate-law bookkeeping uses the unit layer: a rate constant's units follow from its
reaction order, and :func:`rate_constant` converts and dimension-checks the units a
paper quotes, so a mis-stated order fails instead of integrating quietly.

A :class:`Mechanism` is a list of elementary steps with mass-action rates on
concentrations (mol/m3). A reversible step takes its reverse constant from detailed
balance, k_r = k_f / K_c(T), with K_c from :mod:`ngdesign.chem.thermochem`, so a
mechanism cannot drive past thermodynamic equilibrium. Third-body and Lindemann
fall-off steps follow Lindemann (1922); the broadening factors of Troe are not
implemented.

Reactor models integrate with stiff implicit methods (``scipy.integrate.solve_ivp``
BDF/Radau with an analytic mass-action Jacobian): isothermal or adiabatic batch at
constant volume, ideal PFR by residence time, and a steady CSTR by Newton with a
pseudo-transient fallback.

Flowsheet reaction sets stay on their own rate laws: :func:`integrate_reaction_set`
drives ``units._physics.kinetics.rate``, the evaluator the reactor units use, so a
batch run here and a PFR unit share one rate expression.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import least_squares

from ngdesign.chem.stoichiometry import Equation, as_written
from ngdesign.chem.thermochem import R, kp_to_kc, reaction_thermo, species_thermo
from ngdesign.contracts.reactions import Reaction, ReactionSet
from ngdesign.units._physics.kinetics import rate as contract_rate
from ngdesign.uom.dimension import AMOUNT, LENGTH, TIME, Dimension, DimensionError, kind_dimension
from ngdesign.uom.units import parse_unit


class KineticsError(ValueError):
    """A kinetics problem is ill-posed or an integration failed."""


def rate_constant_dimension(order: float) -> Dimension:
    """Dimension of k for overall order n on concentration: (mol/m3)^(1−n) / s."""
    concentration = AMOUNT / LENGTH**3
    return concentration ** (1 - Fraction(order).limit_denominator(1000)) / TIME


def rate_constant(value: float, unit: str, order: float) -> float:
    """A quoted rate constant in SI (mol, m3, s), checked against its reaction order."""
    parsed = parse_unit(unit)
    expected = rate_constant_dimension(order)
    if parsed.dimension != expected:
        raise DimensionError(
            f"{value} {unit} cannot be a rate constant of order {order}: "
            f"dimension {parsed.dimension}, expected {expected}"
        )
    return float(value * parsed.factor)


@dataclass(frozen=True, slots=True)
class ArrheniusLaw:
    """Modified Arrhenius k(T) = A·(T/T0)^n·exp(−Ea/(R·T)), in SI (mol, m3, s, J)."""

    A: float
    Ea: float = 0.0
    n: float = 0.0
    T0: float = 1.0

    def __call__(self, T: float) -> float:
        return float(self.A * (T / self.T0) ** self.n * math.exp(-self.Ea / (R * T)))

    def d_ln_k_dT(self, T: float) -> float:
        """d ln k/dT = n/T + Ea/(R·T²)."""
        return float(self.n / T + self.Ea / (R * T * T))


@dataclass(frozen=True)
class ArrheniusFit:
    """Regression of ln k on 1/T."""

    A: float
    Ea: float  # J/mol
    r_squared: float
    Ea_standard_error: float  # J/mol

    def law(self) -> ArrheniusLaw:
        return ArrheniusLaw(self.A, self.Ea)


def fit_arrhenius(T: Sequence[float], k: Sequence[float]) -> ArrheniusFit:
    """Least-squares ln k = ln A − Ea/(R·T), with the slope's standard error."""
    t = np.asarray(T, dtype=float)
    values = np.asarray(k, dtype=float)
    if t.size < 2 or t.size != values.size:
        raise KineticsError("need at least two (T, k) pairs of equal length")
    if (values <= 0.0).any() or (t <= 0.0).any():
        raise KineticsError("T and k must be positive")
    x = 1.0 / t
    y = np.log(values)
    design = np.vstack([np.ones_like(x), -x / R]).T
    coefficients, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ coefficients
    total = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - float((residual**2).sum()) / total if total > 0.0 else 1.0
    if t.size > 2:
        variance = float((residual**2).sum()) / (t.size - 2)
        covariance = variance * np.linalg.inv(design.T @ design)
        error = math.sqrt(float(covariance[1, 1]))
    else:
        error = 0.0
    return ArrheniusFit(math.exp(float(coefficients[0])), float(coefficients[1]), r_squared, error)


@dataclass(frozen=True)
class OrderFit:
    """Reaction order from one decay curve c(t)."""

    order: float
    k: float  # SI on mol/m3 and s
    r_squared: float


def fit_order(t: Sequence[float], c: Sequence[float]) -> OrderFit:
    """Order n and k of −dc/dt = k·cⁿ by nonlinear fit of the integrated law.

    c(t) = c0·exp(−k t) at n = 1, otherwise c^(1−n) = c0^(1−n) + (n−1)·k·t.
    """
    times = np.asarray(t, dtype=float) - float(t[0])  # the law runs from the first sample
    values = np.asarray(c, dtype=float)
    if times.size < 3 or times.size != values.size:
        raise KineticsError("need at least three (t, c) pairs of equal length")
    if (values <= 0.0).any():
        raise KineticsError("concentrations must be positive")
    c0 = float(values[0])

    def model(order: float, k: float) -> NDArray[np.float64]:
        if abs(order - 1.0) < 1e-6:
            return np.asarray(c0 * np.exp(-k * times), dtype=float)
        base = c0 ** (1.0 - order) + (order - 1.0) * k * times
        return np.asarray(np.power(np.maximum(base, 1e-300), 1.0 / (1.0 - order)), dtype=float)

    def residual(p: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.asarray(model(float(p[0]), math.exp(float(p[1]))) - values, dtype=float)

    span = max(float(times[-1] - times[0]), 1e-300)
    guess_k = max(abs(math.log(max(values[-1], 1e-300) / c0)) / span, 1e-300)
    best = min(
        (
            least_squares(residual, [start, math.log(guess_k)], x_scale=[1.0, 1.0])
            for start in (0.5, 1.0, 2.0)
        ),
        key=lambda s: float(s.cost),
    )
    order, k = float(best.x[0]), math.exp(float(best.x[1]))
    total = float(((values - values.mean()) ** 2).sum())
    return OrderFit(order, k, 1.0 - 2.0 * float(best.cost) / total if total > 0.0 else 1.0)


def half_life(k: float, order: float, c0: float = 1.0) -> float:
    """t½ of −dc/dt = k·cⁿ: ln2/k for n = 1, (2^(n−1) − 1)/((n−1)·k·c0^(n−1)) otherwise."""
    if k <= 0.0:
        raise KineticsError("k must be positive")
    if abs(order - 1.0) < 1e-12:
        return math.log(2.0) / k
    return float((2.0 ** (order - 1.0) - 1.0) / ((order - 1.0) * k * c0 ** (order - 1.0)))


@dataclass(frozen=True)
class Step:
    """One elementary step, mass action on concentrations.

    Reverse rate: give ``reverse`` explicitly, or ``reversible=True`` to take it from
    detailed balance, k_r = k_f/K_c(T); the equation then needs species thermo data.
    ``third_body`` adds [M] = Σ ε_i c_i (default efficiency 1 unless named); with
    ``falloff`` the rate constant is the Lindemann blend k = k∞·Pr/(1 + Pr), where
    Pr = k0[M]/k∞, ``forward`` is k∞ and ``falloff`` is k0.
    """

    equation: str | Equation
    forward: ArrheniusLaw
    reverse: ArrheniusLaw | None = None
    reversible: bool = False
    third_body: Mapping[str, float] | None = None
    falloff: ArrheniusLaw | None = None


@dataclass(frozen=True)
class _CompiledStep:
    forward: ArrheniusLaw
    reverse: ArrheniusLaw | None
    equation: Equation
    detailed_balance: bool
    delta_nu: float
    third_body: NDArray[np.float64] | None
    falloff: ArrheniusLaw | None
    orders_f: NDArray[np.float64]
    orders_r: NDArray[np.float64]


class Mechanism:
    """A compiled set of elementary steps over an ordered species list."""

    def __init__(self, steps: Sequence[Step]) -> None:
        if not steps:
            raise KineticsError("a mechanism needs at least one step")
        equations = [as_written(s.equation) for s in steps]
        species: list[str] = []
        for equation in equations:
            for term in equation.terms:
                if term.key not in species:
                    species.append(term.key)
        self.species: tuple[str, ...] = tuple(species)
        self.index = {key: i for i, key in enumerate(species)}
        n_s = len(species)
        self.nu = np.zeros((len(steps), n_s))
        compiled: list[_CompiledStep] = []
        for j, (step, equation) in enumerate(zip(steps, equations, strict=True)):
            orders_f = np.zeros(n_s)
            orders_r = np.zeros(n_s)
            # by term, not by net ν: a catalyst on both sides still enters both rate laws
            for term, coefficient in zip(equation.terms, equation.coefficients, strict=True):
                i = self.index[term.key]
                nu = float(coefficient)
                self.nu[j, i] += nu
                if nu < 0.0:
                    orders_f[i] += -nu
                else:
                    orders_r[i] += nu
            third = None
            if step.third_body is not None or step.falloff is not None:
                third = np.ones(n_s)  # fall-off needs [M] even with no enhanced colliders
                efficiencies = step.third_body or {}
                for key, efficiency in efficiencies.items():
                    if key in self.index:
                        third[self.index[key]] = efficiency
            if step.reversible and step.reverse is not None:
                raise KineticsError(f"step {equation}: give reversible=True or a reverse law, not both")
            compiled.append(
                _CompiledStep(
                    step.forward,
                    step.reverse,
                    equation,
                    step.reversible,
                    float(self.nu[j].sum()),
                    third,
                    step.falloff,
                    orders_f,
                    orders_r,
                )
            )
        self.steps = compiled

    def _constants(self, c: NDArray[np.float64], T: float) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
        """Forward and reverse rate constants at (c, T), third-body factors included."""
        kf = np.zeros(len(self.steps))
        kr = np.zeros(len(self.steps))
        for j, step in enumerate(self.steps):
            m = float(step.third_body @ c) if step.third_body is not None else 1.0
            factor = m
            if step.falloff is not None:
                reduced = step.falloff(T) * m / step.forward(T)
                factor = reduced / (1.0 + reduced)
            # one factor on both directions, so kf/kr stays the equilibrium ratio at any [M]
            kf[j] = step.forward(T) * factor
            if step.reverse is not None:
                kr[j] = step.reverse(T) * factor
            elif step.detailed_balance:
                thermo = reaction_thermo(step.equation, T, phases={t.key: "gas" for t in step.equation.terms})
                kr[j] = kf[j] / kp_to_kc(thermo.K, step.delta_nu, T)
        return kf, kr

    def rates(self, c: NDArray[np.float64], T: float) -> NDArray[np.float64]:
        """Net rate of each step, mol/(m3 s)."""
        positive = np.maximum(c, 0.0)
        kf, kr = self._constants(positive, T)
        out = np.zeros(len(self.steps))
        for j, step in enumerate(self.steps):
            out[j] = kf[j] * float(np.prod(positive**step.orders_f)) - kr[j] * float(
                np.prod(positive**step.orders_r)
            )
        return out

    def dcdt(self, c: NDArray[np.float64], T: float) -> NDArray[np.float64]:
        """Species net production, mol/(m3 s)."""
        return np.asarray(self.nu.T @ self.rates(c, T), dtype=float)

    def jacobian(self, c: NDArray[np.float64], T: float) -> NDArray[np.float64]:
        """∂(dc/dt)/∂c at fixed T: analytic mass action, third-body terms by chain rule."""
        positive = np.maximum(c, 1e-300)
        kf, kr = self._constants(positive, T)
        n = len(self.species)
        J = np.zeros((n, n))
        for j, step in enumerate(self.steps):
            forward = kf[j] * float(np.prod(positive**step.orders_f))
            reverse = kr[j] * float(np.prod(positive**step.orders_r))
            partial = (forward * step.orders_f - reverse * step.orders_r) / positive
            if step.third_body is not None:
                m = max(float(step.third_body @ positive), 1e-300)
                sensitivity = 1.0 / m  # d ln k/d[M]: 1/[M], or 1/([M](1 + Pr)) in fall-off
                if step.falloff is not None:
                    sensitivity /= 1.0 + step.falloff(T) * m / step.forward(T)
                partial = partial + (forward - reverse) * step.third_body * sensitivity
            J += np.outer(self.nu[j], partial)
        return J

    def concentrations(self, amounts: Mapping[str, float]) -> NDArray[np.float64]:
        """Vector form of a {species: c} map; a species outside the mechanism is refused."""
        outside = sorted(set(amounts) - set(self.species))
        if outside:
            raise KineticsError(f"species {outside} are not in the mechanism {list(self.species)}")
        return np.array([float(amounts.get(key, 0.0)) for key in self.species])


@dataclass(frozen=True)
class Trajectory:
    """A reactor integration: concentrations (mol/m3) and T through time."""

    species: tuple[str, ...]
    t: NDArray[np.float64]
    c: NDArray[np.float64]  # shape (n_species, n_times)
    T: NDArray[np.float64]
    n_steps: int = 0

    def of(self, key: str) -> NDArray[np.float64]:
        return np.asarray(self.c[self.species.index(key)], dtype=float)

    def final(self) -> dict[str, float]:
        return {key: float(self.c[i, -1]) for i, key in enumerate(self.species)}


def _integrate(
    fun: Callable[[float, NDArray[np.float64]], NDArray[np.float64]],
    jac: Callable[[float, NDArray[np.float64]], NDArray[np.float64]] | None,
    y0: NDArray[np.float64],
    t_end: float,
    t_eval: Sequence[float] | NDArray[np.float64] | None,
    rtol: float,
    atol: float,
    method: str,
) -> tuple[NDArray[np.float64], NDArray[np.float64], int]:
    if t_end <= 0.0:
        raise KineticsError("t_end must be positive")
    solution = solve_ivp(
        fun,
        (0.0, t_end),
        y0,
        method=method,
        jac=jac,
        rtol=rtol,
        atol=atol,
        t_eval=None if t_eval is None else np.asarray(t_eval, dtype=float),
    )
    if not solution.success:
        raise KineticsError(f"integration failed: {solution.message}")
    return solution.t, solution.y, int(solution.nfev)


def simulate_batch(
    mechanism: Mechanism,
    c0: Mapping[str, float],
    T: float,
    t_end: float,
    *,
    adiabatic: bool = False,
    t_eval: Sequence[float] | NDArray[np.float64] | None = None,
    rtol: float = 1e-8,
    atol: float = 1e-10,
    method: str = "BDF",
) -> Trajectory:
    """Constant-volume batch reactor.

    Isothermal: dc/dt = Σ_j ν_ij r_j. Adiabatic: adds the energy balance
    dT/dt = −Σ_i U_i(T) ċ_i / Σ_i c_i Cv_i(T), for ideal gases with U_i = H_i − R·T and
    Cv_i = Cp_i − R (all species must have gas thermo data).
    """
    y0 = mechanism.concentrations(c0)
    if (y0 < 0.0).any():
        raise KineticsError("negative initial concentration")
    if not adiabatic:
        t, y, evaluations = _integrate(
            lambda _t, c: mechanism.dcdt(c, T),
            lambda _t, c: mechanism.jacobian(c, T),
            y0,
            t_end,
            t_eval,
            rtol,
            atol,
            method,
        )
        return Trajectory(mechanism.species, t, y, np.full_like(t, T), evaluations)
    thermo = [species_thermo(key) for key in mechanism.species]

    def energy(_t: float, state: NDArray[np.float64]) -> NDArray[np.float64]:
        c, temperature = state[:-1], float(state[-1])
        ddt = mechanism.dcdt(c, temperature)
        u = np.array([s.h(temperature) - R * temperature for s in thermo])
        cv = np.array([s.cp(temperature) - R for s in thermo])
        return np.asarray(np.append(ddt, -float(u @ ddt) / float(np.maximum(c, 0.0) @ cv)), dtype=float)

    t, y, evaluations = _integrate(energy, None, np.append(y0, T), t_end, t_eval, rtol, atol, method)
    return Trajectory(mechanism.species, t, y[:-1], y[-1], evaluations)


def simulate_pfr(
    mechanism: Mechanism,
    c0: Mapping[str, float],
    T: float,
    residence_time: float,
    **options: float,
) -> Trajectory:
    """Ideal isothermal constant-density PFR: the batch equations in τ = z/u."""
    return simulate_batch(mechanism, c0, T, residence_time, **options)  # type: ignore[arg-type]


@dataclass(frozen=True)
class CstrResult:
    """Steady CSTR outlet."""

    species: tuple[str, ...]
    c: dict[str, float]
    residence_time: float
    T: float
    residual: float
    iterations: int


def solve_cstr(
    mechanism: Mechanism,
    c_in: Mapping[str, float],
    T: float,
    residence_time: float,
    *,
    c_start: Mapping[str, float] | None = None,
    tol: float = 1e-10,
) -> CstrResult:
    """Steady isothermal CSTR: (c_in − c)/τ + ν·r(c) = 0.

    Newton with a backtracking line search; if it stalls, integrates the transient
    CSTR for 100 τ and resumes from there. Multiple steady states exist for some
    kinetics: ``c_start`` selects the branch.
    """
    if residence_time <= 0.0:
        raise KineticsError("residence time must be positive")
    feed = mechanism.concentrations(c_in)
    tau = residence_time

    def residual(c: NDArray[np.float64]) -> NDArray[np.float64]:
        return (feed - c) / tau + mechanism.dcdt(c, T)

    def newton(start: NDArray[np.float64]) -> tuple[NDArray[np.float64], int, bool]:
        c = start.copy()
        scale = max(float(feed.max()), 1e-300) / tau
        for iteration in range(1, 200):
            f = residual(c)
            if float(np.abs(f).max()) < tol * scale:
                return c, iteration, True
            matrix = mechanism.jacobian(c, T) - np.eye(c.size) / tau
            try:
                step = np.linalg.solve(matrix, -f)
            except np.linalg.LinAlgError:
                return c, iteration, False
            lam = 1.0
            while lam > 1e-10:
                trial = np.maximum(c + lam * step, 0.0)
                if float(np.abs(residual(trial)).max()) < float(np.abs(f).max()):
                    break
                lam *= 0.5
            else:
                return c, iteration, False
            c = trial
        return c, 200, False

    start = mechanism.concentrations(c_start) if c_start is not None else feed.copy()
    c, iterations, converged = newton(start)
    if not converged:
        transient = solve_ivp(
            lambda _t, y: residual(y),
            (0.0, 100.0 * tau),
            c,
            method="BDF",
            jac=lambda _t, y: mechanism.jacobian(y, T) - np.eye(y.size) / tau,
            rtol=1e-8,
            atol=1e-12,
        )
        if not transient.success:
            raise KineticsError(f"CSTR transient failed: {transient.message}")
        c, more, converged = newton(transient.y[:, -1])
        iterations += more
        if not converged:
            raise KineticsError("CSTR Newton did not converge")
    return CstrResult(
        mechanism.species,
        dict(zip(mechanism.species, (float(v) for v in c), strict=True)),
        tau,
        T,
        float(np.abs(residual(c)).max()),
        iterations,
    )


@dataclass(frozen=True)
class ContractBatch:
    """Moles through time for a flowsheet reaction set at fixed T and P."""

    components: tuple[str, ...]
    t: NDArray[np.float64]
    n: NDArray[np.float64]  # mol, shape (n_components, n_times)
    extents: dict[str, float] = field(default_factory=dict)  # final, mol

    def final(self) -> dict[str, float]:
        return {cid: float(self.n[i, -1]) for i, cid in enumerate(self.components)}


def _volumetric_rate_factor(reaction: Reaction) -> float:
    """SI factor of a reaction's declared ``rate_units``, checked to be per volume."""
    kinetics = reaction.kinetics
    if kinetics is None:
        return 1.0
    unit = parse_unit(kinetics.rate_units)
    if unit.dimension != kind_dimension("reaction_rate"):
        raise DimensionError(
            f"reaction {reaction.id!r}: rate_units {kinetics.rate_units!r} is not a volumetric rate"
        )
    return unit.factor


def integrate_reaction_set(
    rset: ReactionSet,
    n0: Mapping[str, float],
    T: float,
    P: float,
    t_end: float,
    *,
    volume: float | None = None,
    rtol: float = 1e-8,
) -> ContractBatch:
    """Isothermal, isobaric batch run of a flowsheet :class:`ReactionSet`.

    Rates come from ``units._physics.kinetics.rate``, the reactor units' evaluator, on
    the base-component extent. Each reaction's ``rate_units`` string is read by the unit
    layer and must be a volumetric rate; a catalyst-mass basis is refused here because a
    batch run has no catalyst loading. The reacting volume is the gas volume n·R·T/P,
    or a fixed ``volume`` (m3) for a liquid-filled vessel.
    """
    slate = list(rset.components)
    extra = sorted(set(n0) - set(slate))
    if extra:
        raise KineticsError(f"feed components {extra} are outside reaction set {rset.id!r}")
    y0 = np.array([float(n0.get(cid, 0.0)) for cid in slate])
    extents = len(rset.reactions)
    nu = np.array(
        [
            [
                float(r.stoichiometry.get(cid, 0.0)) / abs(float(r.stoichiometry[r.base_component]))
                for cid in slate
            ]
            for r in rset.reactions
        ]
    ).reshape(extents, len(slate))

    scale = np.array([_volumetric_rate_factor(r) for r in rset.reactions])

    def rhs(_t: float, state: NDArray[np.float64]) -> NDArray[np.float64]:
        n = np.maximum(state[: len(slate)], 0.0)
        total = float(n.sum())
        z = {cid: float(v) / total for cid, v in zip(slate, n, strict=True)}
        size = volume if volume is not None else total * R * T / P
        rates = np.array([contract_rate(r, T, P, z) for r in rset.reactions]) * scale * size
        return np.concatenate([nu.T @ rates, rates])

    start = np.concatenate([y0, np.zeros(extents)])
    t, y, _ = _integrate(rhs, None, start, t_end, None, rtol, 1e-12, "LSODA")
    final = {r.id: float(y[len(slate) + j, -1]) for j, r in enumerate(rset.reactions)}
    return ContractBatch(tuple(slate), t, y[: len(slate)], final)


__all__ = [
    "ArrheniusFit",
    "ArrheniusLaw",
    "ContractBatch",
    "CstrResult",
    "KineticsError",
    "Mechanism",
    "OrderFit",
    "Step",
    "Trajectory",
    "fit_arrhenius",
    "fit_order",
    "half_life",
    "integrate_reaction_set",
    "rate_constant",
    "rate_constant_dimension",
    "simulate_batch",
    "simulate_pfr",
    "solve_cstr",
]
