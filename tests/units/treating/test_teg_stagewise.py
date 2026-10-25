"""Closed-form tests for the shared counter-current stage march (spec teg_contactor R2, step 1).

Kremser identity: with an injected linear equilibrium ``Y* = m * X`` in ratio
space, ``countercurrent_march`` must reproduce the Kremser absorption solution

    (Y_in - Y_1) / (Y_in - m * X_0) = (A^{N+1} - A) / (A^{N+1} - 1),
    A = S / (m * G)

to 1e-12 relative (spec allows the stated round-off; the bisection floor is far
below the 4e-16 asserted here).

Test basis (spec, R0 example flows): G = 99.95 mol/s dry gas, S = 0.197 mol/s
TEG, X_0 = 0.015/0.985, Y_in = 0.0005/0.9995 (the exact ratio conversion of the
R0 example y_H2O = 0.0005; the spec text's 5.0025e-4 is this value rounded),
m = 0.001, so A = 1.97099.
Reference march results printed in the spec: Y_1 = 1.78481225796e-4 (N=1),
4.86491069546e-5 (N=3), 1.9339588953e-5 (N=6).
"""

from __future__ import annotations

import pytest

from ngdesign.units.treating.teg_stagewise import TEGStageError, countercurrent_march

M = 0.001
G = 99.95
S = 0.197
X_LEAN = 0.015 / 0.985
Y_IN = 0.0005 / 0.9995
A = S / (M * G)  # 1.97099...


def _linear_x_of_y(y_ratio: float) -> float:
    """Linear equilibrium ``Y* = m * X`` directly in mole-ratio space.

    The classical Kremser line (Trebal, eq. with ``A = S / (m G)``) is linear
    in solute-free ratios, so the injected inverse is simply ``X = Y / m``.
    """
    return y_ratio / M


def _kremser_y1(n_stages: int) -> float:
    """Closed-form Kremser top-gas ratio for the linear line."""
    factor = (A ** (n_stages + 1) - A) / (A ** (n_stages + 1) - 1.0)
    return Y_IN - (Y_IN - M * X_LEAN) * factor


@pytest.mark.parametrize("n_stages", [1, 3, 6])
def test_march_matches_closed_form_kremser(n_stages: int) -> None:
    y, x = countercurrent_march(G, S, X_LEAN, Y_IN, n_stages, _linear_x_of_y)
    assert len(y) == n_stages + 1
    assert len(x) == n_stages
    assert y[0] == pytest.approx(_kremser_y1(n_stages), rel=4e-16)
    # Stage balances: G (Y_{j+1} - Y_j) = S (X_j - X_{j-1}) on every stage.
    for j in range(n_stages):
        x_prev = X_LEAN if j == 0 else x[j - 1]
        assert G * (y[j + 1] - y[j]) == pytest.approx(S * (x[j] - x_prev), rel=1e-12)
    assert y[-1] == pytest.approx(Y_IN, rel=1e-12)  # bottom closure


@pytest.mark.parametrize(
    ("n_stages", "printed"),
    [(1, 1.78481225796e-4), (3, 4.86491069546e-5), (6, 1.9339588953e-5)],
)
def test_march_matches_spec_printed_values(n_stages: int, printed: float) -> None:
    """The march output equals the values printed in the unit spec."""
    y, _ = countercurrent_march(G, S, X_LEAN, Y_IN, n_stages, _linear_x_of_y)
    assert y[0] == pytest.approx(printed, rel=1e-9)


def test_march_profiles_are_monotone_on_the_linear_line() -> None:
    y, x = countercurrent_march(G, S, X_LEAN, Y_IN, 6, _linear_x_of_y)
    assert all(y[i] < y[i + 1] for i in range(len(y) - 1))
    assert all(x[i] < x[i + 1] for i in range(len(x) - 1))
    assert x[-1] > X_LEAN  # the solvent picks up water


def test_march_requires_positive_flows_and_stages() -> None:
    with pytest.raises(ValueError, match="n_stages"):
        countercurrent_march(G, S, X_LEAN, Y_IN, 0, _linear_x_of_y)
    with pytest.raises(ValueError, match="G"):
        countercurrent_march(0.0, S, X_LEAN, Y_IN, 1, _linear_x_of_y)
    with pytest.raises(ValueError, match="S"):
        countercurrent_march(G, 0.0, X_LEAN, Y_IN, 1, _linear_x_of_y)


def test_march_solves_a_decreasing_residual() -> None:
    """A residual falling in Y_1 (the stripping-side orientation) converges.

    G = S = 1, X_0 = 0, Y_in = 0.5, N = 1 with the injected inverse
    ``x_of_y(y) = 2 - 4y``: the march residual ``r = Y_1 + x_of_y(Y_1) - Y_in
    = 1.5 - 3 Y_1`` is decreasing, so the bracket arrives with
    ``residual(lo) > 0`` and the bisection swaps its ends. Root Y_1 = 0.5.
    The signed stop test used to fire on the first swapped iteration and
    return the raw scan midpoint (~6 % off); the march must land at its own
    |delta ln Y_1| < 1e-14 tolerance instead.
    """
    y, _ = countercurrent_march(1.0, 1.0, 0.0, 0.5, 1, lambda y: 2.0 - 4.0 * y)
    assert y[0] == pytest.approx(0.5, rel=1e-13)


def test_bisect_decreasing_residual_matches_root() -> None:
    """Direct check on the reviewer's measurement: r(y) = 2e-3 - y.

    Before the abs() stop-test fix this returned the scan midpoint with a
    6.8e-3 relative error; the fixed bisection must reach its 1e-14 ln-space
    tolerance, i.e. relative error far below 1e-12.
    """
    from ngdesign.units.treating.teg_stagewise import _bisect, _bracket

    residual = lambda y: 2.0e-3 - y  # noqa: E731 -- falling in y by construction
    lo, hi = _bracket(residual)
    root = _bisect(residual, lo, hi)
    assert root == pytest.approx(2.0e-3, rel=1e-12)


def test_march_refuses_multiple_roots() -> None:
    """A constructed non-monotone equilibrium gives two sign changes.

    Piecewise ``x_of_y`` with G = S = 1, X_0 = 0, Y_in = 1 (residual
    ``r = Y_1 + x_of_y(Y_1) - 1``): rising on [0, 0.5] (root at 0.2), falling
    steeply on (0.5, 0.75] (root at 2/3), then overshooting the sentinel
    negative -- exactly two sign changes over the scan.
    """

    def non_monotone(y_ratio: float) -> float:
        if y_ratio <= 0.5:
            return 4.0 * y_ratio
        if y_ratio <= 0.75:
            return -10.0 * y_ratio + 7.0
        return -2.0 * y_ratio  # drives Y below 0: overshoot sentinel

    with pytest.raises(TEGStageError, match="multiple roots"):
        countercurrent_march(1.0, 1.0, 0.0, 1.0, 1, non_monotone)


def test_march_refuses_no_bracket() -> None:
    """A residual that never changes sign raises the no-bracket refusal."""

    def always_negative(y_ratio: float) -> float:
        return -y_ratio  # r = Y_1 - Y_1 - Y_in < 0 for every trial Y_1

    with pytest.raises(TEGStageError, match="no bracket"):
        countercurrent_march(1.0, 1.0, 0.0, 1.0, 1, always_negative)
