"""Kinetics against closed-form solutions and an independent stiff integrator."""

from __future__ import annotations

import math
from fractions import Fraction

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.integrate import solve_ivp

from ngdesign.chem import kinetics as K
from ngdesign.chem.kinetics import ArrheniusLaw, Mechanism, Step
from ngdesign.chem.stoichiometry import Equation, Term
from ngdesign.chem.thermochem import R
from ngdesign.contracts.reactions import PowerLaw, Reaction, ReactionSet
from ngdesign.data.formula import Formula
from ngdesign.uom.dimension import DimensionError


def _pseudo_step(
    reactants: dict[str, int], products: dict[str, int], law: ArrheniusLaw, **kwargs: object
) -> Step:
    """An elementary step over abstract labels, for the closed-form cases.

    Balance is a property of real species; the textbook A -> B cases have none, so
    they are written with one fictional shared atom per label unit.
    """
    terms = []
    coefficients = []
    for sign, side in ((-1, reactants), (1, products)):
        for label, nu in side.items():
            terms.append(Term(label, Formula(label, (("X", 1),), 0, None), None, None))
            coefficients.append(Fraction(sign * nu))
    return Step(Equation(tuple(terms), tuple(coefficients)), law, **kwargs)  # type: ignore[arg-type]


def test_consecutive_first_order_matches_bateman() -> None:
    k1, k2 = 2.0, 0.7
    mech = Mechanism(
        [
            _pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(k1)),
            _pseudo_step({"B": 1}, {"C": 1}, ArrheniusLaw(k2)),
        ]
    )
    times = np.linspace(0.1, 5.0, 25)
    run = K.simulate_batch(mech, {"A": 1.0}, 300.0, 5.0, t_eval=times, rtol=1e-10, atol=1e-12)
    a = np.exp(-k1 * times)
    b = k1 / (k2 - k1) * (np.exp(-k1 * times) - np.exp(-k2 * times))
    assert run.of("A") == pytest.approx(a, abs=1e-7)
    assert run.of("B") == pytest.approx(b, abs=1e-7)
    assert run.of("C") == pytest.approx(1.0 - a - b, abs=1e-7)


def test_explicit_reverse_first_order_relaxes_to_its_ratio() -> None:
    kf, kr = 3.0, 1.0
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(kf), reverse=ArrheniusLaw(kr))])
    times = np.array([0.05, 0.2, 1.0, 5.0])
    run = K.simulate_batch(mech, {"A": 1.0}, 300.0, 5.0, t_eval=times, rtol=1e-10, atol=1e-12)
    equilibrium = kr / (kf + kr)
    exact = equilibrium + (1.0 - equilibrium) * np.exp(-(kf + kr) * times)
    assert run.of("A") == pytest.approx(exact, abs=1e-7)


def test_second_order_decay_matches_integrated_law() -> None:
    k = 0.5
    mech = Mechanism([_pseudo_step({"A": 2}, {"B": 2}, ArrheniusLaw(k))])
    times = np.array([1.0, 4.0, 10.0])
    run = K.simulate_batch(mech, {"A": 2.0}, 300.0, 10.0, t_eval=times, rtol=1e-10, atol=1e-12)
    # dc/dt = -2 k c^2 -> 1/c = 1/c0 + 2 k t
    assert run.of("A") == pytest.approx(1.0 / (0.5 + 2.0 * k * times), abs=1e-7)


def _robertson() -> Mechanism:
    return Mechanism(
        [
            _pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(0.04)),
            _pseudo_step({"B": 2}, {"B": 1, "C": 1}, ArrheniusLaw(3e7)),
            _pseudo_step({"B": 1, "C": 1}, {"A": 1, "C": 1}, ArrheniusLaw(1e4)),
        ]
    )


def test_robertson_stiff_problem_against_radau() -> None:
    """Robertson (1966): classic stiff kinetics, compared with an independent integrator."""

    def rober(_t: float, y: np.ndarray) -> np.ndarray:
        a, b, c = y
        return np.array([-0.04 * a + 1e4 * b * c, 0.04 * a - 1e4 * b * c - 3e7 * b * b, 3e7 * b * b])

    t_end = 400.0
    reference = solve_ivp(rober, (0.0, t_end), [1.0, 0.0, 0.0], method="Radau", rtol=1e-11, atol=1e-13)
    run = K.simulate_batch(_robertson(), {"A": 1.0}, 300.0, t_end, rtol=1e-9, atol=1e-12)
    assert run.final()["A"] == pytest.approx(reference.y[0, -1], rel=1e-5)
    assert run.final()["B"] == pytest.approx(reference.y[1, -1], rel=1e-4)
    assert run.final()["C"] == pytest.approx(reference.y[2, -1], rel=1e-5)
    assert run.c[:, -1].sum() == pytest.approx(1.0, abs=1e-8)  # mass conserved


def test_mass_action_jacobian_matches_finite_differences() -> None:
    mech = _robertson()
    c = np.array([0.7, 1e-4, 0.3])
    analytic = mech.jacobian(c, 300.0)
    numeric = np.zeros_like(analytic)
    for i in range(3):
        h = max(abs(c[i]) * 1e-6, 1e-10)
        up, down = c.copy(), c.copy()
        up[i] += h
        down[i] -= h
        numeric[:, i] = (mech.dcdt(up, 300.0) - mech.dcdt(down, 300.0)) / (2 * h)
    assert analytic == pytest.approx(numeric, rel=1e-5, abs=1e-5)


def test_third_body_scales_the_rate_with_total_concentration() -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(2.0), third_body={"B": 3.0})])
    index = mech.index
    c = np.zeros(2)
    c[index["A"]], c[index["B"]] = 1.0, 2.0
    # [M] = 1·[A] + 3·[B] = 7
    assert mech.rates(c, 300.0)[0] == pytest.approx(2.0 * 1.0 * 7.0)


def test_lindemann_falloff_limits() -> None:
    k_inf, k_0 = 10.0, 0.5
    mech = Mechanism(
        [_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(k_inf), third_body={}, falloff=ArrheniusLaw(k_0))]
    )

    def effective(m: float) -> float:
        c = np.zeros(2)
        c[mech.index["A"]], c[mech.index["B"]] = 1e-9, m
        return float(mech.rates(c, 300.0)[0] / 1e-9)

    assert effective(1e-6) == pytest.approx(k_0 * 1e-6, rel=1e-3)  # low-pressure limit
    assert effective(1e9) == pytest.approx(k_inf, rel=1e-3)  # high-pressure limit


def test_both_reverse_forms_together_are_refused() -> None:
    with pytest.raises(K.KineticsError):
        Mechanism(
            [_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(1.0), reverse=ArrheniusLaw(1.0), reversible=True)]
        )


def test_unknown_species_in_the_charge_is_refused() -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(1.0))])
    with pytest.raises(K.KineticsError, match="Q"):
        K.simulate_batch(mech, {"Q": 1.0}, 300.0, 1.0)


def test_negative_start_and_bad_horizon_are_refused() -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(1.0))])
    with pytest.raises(K.KineticsError):
        K.simulate_batch(mech, {"A": -1.0}, 300.0, 1.0)
    with pytest.raises(K.KineticsError):
        K.simulate_batch(mech, {"A": 1.0}, 300.0, 0.0)


@pytest.mark.parametrize("k_tau", [0.1, 1.0, 25.0])
def test_first_order_cstr_closed_form(k_tau: float) -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(k_tau))])
    result = K.solve_cstr(mech, {"A": 2.0}, 300.0, 1.0)
    assert result.c["A"] == pytest.approx(2.0 / (1.0 + k_tau), rel=1e-9)
    assert result.c["B"] == pytest.approx(2.0 - result.c["A"], rel=1e-9)


def test_second_order_cstr_closed_form() -> None:
    k, tau, c0 = 4.0, 2.0, 3.0
    mech = Mechanism([_pseudo_step({"A": 2}, {"B": 2}, ArrheniusLaw(k))])
    result = K.solve_cstr(mech, {"A": c0}, 300.0, tau)
    # (c0 - c)/τ = 2 k c² -> 2kτ c² + c - c0 = 0
    a = 2.0 * k * tau
    assert result.c["A"] == pytest.approx((-1.0 + math.sqrt(1.0 + 4.0 * a * c0)) / (2.0 * a), rel=1e-8)


def test_pfr_outperforms_cstr_at_equal_residence_time() -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(1.0))])
    pfr = K.simulate_pfr(mech, {"A": 1.0}, 300.0, 2.0).final()["A"]
    cstr = K.solve_cstr(mech, {"A": 1.0}, 300.0, 2.0).c["A"]
    assert pfr == pytest.approx(math.exp(-2.0), abs=1e-6)
    assert pfr < cstr


def test_arrhenius_law_and_its_log_slope() -> None:
    law = ArrheniusLaw(1e10, 80e3, 0.5, 300.0)
    T, h = 500.0, 1e-3
    numeric = (math.log(law(T + h)) - math.log(law(T - h))) / (2 * h)
    assert law.d_ln_k_dT(T) == pytest.approx(numeric, rel=1e-8)


@settings(max_examples=30)
@given(st.floats(1e3, 1e14), st.floats(2e4, 2e5))
def test_arrhenius_regression_recovers_exact_data(A: float, Ea: float) -> None:
    temperatures = [300.0, 350.0, 400.0, 500.0, 650.0]
    k = [A * math.exp(-Ea / (R * T)) for T in temperatures]
    fit = K.fit_arrhenius(temperatures, k)
    assert fit.Ea == pytest.approx(Ea, rel=1e-8)
    assert fit.A == pytest.approx(A, rel=1e-6)
    assert fit.r_squared == pytest.approx(1.0)


def test_arrhenius_fit_reports_scatter() -> None:
    rng = np.random.default_rng(7)
    T = np.linspace(300.0, 600.0, 12)
    k = 1e8 * np.exp(-6e4 / (R * T)) * np.exp(rng.normal(0.0, 0.05, T.size))
    fit = K.fit_arrhenius(T.tolist(), k.tolist())
    assert abs(fit.Ea - 6e4) < 4.0 * fit.Ea_standard_error
    assert fit.r_squared < 1.0


@pytest.mark.parametrize(("order", "k"), [(0.0, 0.05), (0.5, 0.2), (1.0, 0.4), (2.0, 0.3)])
def test_order_is_recovered_from_a_decay_curve(order: float, k: float) -> None:
    t = np.linspace(0.0, 3.0, 25)
    c0 = 2.0
    if order == 1.0:
        c = c0 * np.exp(-k * t)
    else:
        c = (c0 ** (1.0 - order) + (order - 1.0) * k * t) ** (1.0 / (1.0 - order))
    fit = K.fit_order(t.tolist(), c.tolist())
    assert fit.order == pytest.approx(order, abs=1e-3)
    assert fit.k == pytest.approx(k, rel=1e-2)


def test_half_life() -> None:
    assert K.half_life(0.2, 1.0) == pytest.approx(math.log(2.0) / 0.2)
    assert K.half_life(0.5, 2.0, 2.0) == pytest.approx(1.0)  # 1/(k c0)
    assert K.half_life(0.5, 0.0, 2.0) == pytest.approx(2.0)  # c0/(2 k)


@pytest.mark.parametrize(
    ("value", "unit", "order", "expected"),
    [
        (2.0, "1/s", 1.0, 2.0),
        (2.0, "1/min", 1.0, 2.0 / 60.0),
        (1.0, "L/(mol s)", 2.0, 1e-3),
        (1.0, "mol/(L s)", 0.0, 1000.0),
        (1.0, "(L/mol)^0.5/s", 1.5, 10.0**-1.5),
    ],
)
def test_rate_constant_units_follow_the_order(value: float, unit: str, order: float, expected: float) -> None:
    assert K.rate_constant(value, unit, order) == pytest.approx(expected)


def test_a_mis_stated_order_fails_at_the_edge() -> None:
    with pytest.raises(DimensionError):
        K.rate_constant(1.0, "1/s", 2.0)


def _isomerisation(rate_units: str = "mol/(m3·s)") -> ReactionSet:
    reaction = Reaction(
        id="iso",
        stoichiometry={"nC4": -1.0, "iC4": 1.0},
        base_component="nC4",
        provenance="test: abstract first-order rate",
        kinetics=PowerLaw(rate_units=rate_units, k0=0.3, Ea=0.0, orders={"nC4": 1.0}, basis="concentration"),
    )
    return ReactionSet(id="r", reactions=[reaction], components=["nC4", "iC4"])


def test_contract_reaction_set_uses_the_units_rate_evaluator() -> None:
    run = K.integrate_reaction_set(_isomerisation(), {"nC4": 1.0}, 500.0, 2e5, 4.0)
    assert run.final()["nC4"] == pytest.approx(math.exp(-0.3 * 4.0), rel=1e-6)
    assert run.final()["iC4"] == pytest.approx(1.0 - math.exp(-0.3 * 4.0), rel=1e-6)
    assert run.extents["iso"] == pytest.approx(run.final()["iC4"], rel=1e-6)


def test_contract_rate_units_are_read_by_the_unit_layer() -> None:
    per_litre = K.integrate_reaction_set(_isomerisation("mol/(L·s)"), {"nC4": 1.0}, 500.0, 2e5, 4.0e-3)
    assert per_litre.final()["nC4"] == pytest.approx(math.exp(-0.3 * 1000.0 * 4.0e-3), rel=1e-6)


def test_catalyst_basis_is_refused_in_a_batch_run() -> None:
    with pytest.raises(ValueError, match="kg_cat"):
        K.integrate_reaction_set(_isomerisation("mol/(kg_cat·s)"), {"nC4": 1.0}, 500.0, 2e5, 1.0)


def test_feed_outside_the_set_is_refused() -> None:
    with pytest.raises(K.KineticsError, match="C1"):
        K.integrate_reaction_set(_isomerisation(), {"C1": 1.0}, 500.0, 2e5, 1.0)


def test_order_fit_does_not_assume_time_zero() -> None:
    """Regression: samples from t = 10 gave n = -9.4."""
    t = np.linspace(10.0, 50.0, 9)
    fit = K.fit_order(t.tolist(), (3.0 * np.exp(-0.1 * t)).tolist())
    assert fit.order == pytest.approx(1.0, abs=1e-3)
    assert fit.k == pytest.approx(0.1, rel=1e-3)


def test_falloff_needs_no_explicit_collider_list() -> None:
    """Regression: [M] stayed 1 mol/m3 without ``third_body``, freezing the fall-off."""
    k_inf, k_0 = 1000.0, 1.0
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(k_inf), falloff=ArrheniusLaw(k_0))])
    c = np.zeros(2)
    c[mech.index["A"]], c[mech.index["B"]] = 1e-6, 1000.0
    pr = k_0 * 1000.0 / k_inf
    assert mech.rates(c, 300.0)[0] / 1e-6 == pytest.approx(k_inf * pr / (1.0 + pr), rel=1e-5)


def test_explicit_reverse_in_falloff_keeps_the_equilibrium_ratio() -> None:
    """Regression: kf/kr drifted with [M], as if K depended on the collider."""
    mech = Mechanism(
        [
            _pseudo_step(
                {"A": 1}, {"B": 1}, ArrheniusLaw(10.0), reverse=ArrheniusLaw(5.0), falloff=ArrheniusLaw(0.5)
            )
        ]
    )
    for m in (0.04, 4.0, 4000.0):
        c = np.zeros(2)
        c[mech.index["A"]], c[mech.index["B"]] = m / 2.0, m / 2.0
        kf, kr = mech._constants(c, 300.0)
        assert kf[0] / kr[0] == pytest.approx(2.0)


def test_falloff_jacobian_matches_finite_differences() -> None:
    mech = Mechanism([_pseudo_step({"A": 1}, {"B": 1}, ArrheniusLaw(10.0), falloff=ArrheniusLaw(0.5))])
    c = np.array([3.0, 7.0])
    analytic = mech.jacobian(c, 300.0)
    numeric = np.zeros((2, 2))
    for i in range(2):
        h = 1e-6
        up, down = c.copy(), c.copy()
        up[i] += h
        down[i] -= h
        numeric[:, i] = (mech.dcdt(up, 300.0) - mech.dcdt(down, 300.0)) / (2 * h)
    assert analytic == pytest.approx(numeric, rel=1e-6)
