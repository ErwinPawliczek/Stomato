"""The shared saturation solver on an analytic vf (spec P1-08).

Piecewise-linear vapour fraction with plateaus: exact plateau ends, so the
converged unknowns are known in closed form and the degenerate cases (target
at a bracket end, no plateau in reach, non-straddling bracket) are reachable
by construction.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.contracts.thermo import SaturationError
from ngdesign.thermo.saturation import interior_vf_solve, solve_saturation


# P-unknown orientation: vf == 1 plateau at low x, vf == 0 plateau at high x,
# linear (slope -1) between x=1 and x=2.
def vf_p(x: float) -> float:
    if x <= 1.0:
        return 1.0
    if x >= 2.0:
        return 0.0
    return 2.0 - x


# T-unknown orientation (mirror): vf == 0 plateau at low x, vf == 1 at high x.
def vf_t(x: float) -> float:
    if x <= 1.0:
        return 0.0
    if x >= 2.0:
        return 1.0
    return x - 1.0


def test_bubble_pressure_solve() -> None:
    """Bubble plateau at the high-P end, already on it: secant converges to the knee."""
    assert math.isclose(
        solve_saturation(vf_p, kind="bubble", unknown="P", bounds=(0.5, 3.0)),
        2.0,
        rel_tol=1e-6,
    )


def test_dew_pressure_solve() -> None:
    """Dew plateau at the low-P end, already on it: converges to the other knee."""
    assert math.isclose(
        solve_saturation(vf_p, kind="dew", unknown="P", bounds=(0.5, 3.0)),
        1.0,
        rel_tol=1e-6,
    )


def test_temperature_orientation() -> None:
    """The unknown fixes the plateau end: bubble at low T, dew at high T."""
    assert math.isclose(
        solve_saturation(vf_t, kind="bubble", unknown="T", bounds=(0.5, 3.0)),
        1.0,
        rel_tol=1e-6,
    )
    assert math.isclose(
        solve_saturation(vf_t, kind="dew", unknown="T", bounds=(0.5, 3.0)),
        2.0,
        rel_tol=1e-6,
    )


def test_scan_finds_off_bracket_plateau() -> None:
    """Initial high end inside the two-phase region: the scan moves it onto the plateau."""
    assert math.isclose(
        solve_saturation(vf_p, kind="bubble", unknown="P", bounds=(0.5, 1.5)),
        2.0,
        rel_tol=1e-6,
    )


def test_interior_vf_solve_is_orientation_agnostic() -> None:
    """Interior target solved identically from either bracket order."""
    up = interior_vf_solve(vf_p, 0.5, 0.5, 3.0)
    down = interior_vf_solve(vf_p, 0.5, 3.0, 0.5)
    assert math.isclose(up, 1.5, rel_tol=1e-6)
    assert math.isclose(down, up, rel_tol=1e-12)


def test_target_at_a_bracket_end() -> None:
    """Target equal to a bracket end's vf: that end is the answer (residual 0)."""
    result = interior_vf_solve(vf_p, 1.0, 0.5, 3.0)
    assert vf_p(result) == pytest.approx(1.0)
    result = interior_vf_solve(vf_p, 0.0, 0.5, 3.0)
    assert vf_p(result) == pytest.approx(0.0)


def test_no_plateau_raises() -> None:
    """A vf that never plateaus: the scan exhausts and raises SaturationError."""
    with pytest.raises(SaturationError):
        solve_saturation(lambda _x: 0.5, kind="bubble", unknown="P", bounds=(0.5, 3.0))
    with pytest.raises(SaturationError):
        solve_saturation(lambda _x: 0.0, kind="bubble", unknown="P", bounds=(0.5, 3.0))


def test_non_straddling_bracket_raises() -> None:
    """Both ends on the same side of the target: no bracket, raise."""
    with pytest.raises(SaturationError):
        solve_saturation(lambda x: abs(x - 1.5), kind="bubble", unknown="P", bounds=(0.5, 3.0))


def test_tolerances_and_caps_pass_through() -> None:
    """max_iter caps the secant (early, loose answer); tighter rel_tol still converges."""
    loose = solve_saturation(vf_p, kind="bubble", unknown="P", bounds=(0.5, 3.0), max_iter=1)
    assert 1.75 < loose < 3.0
    tight = solve_saturation(vf_p, kind="bubble", unknown="P", bounds=(0.5, 3.0), rel_tol=1e-12)
    assert math.isclose(tight, 2.0, rel_tol=1e-9)
