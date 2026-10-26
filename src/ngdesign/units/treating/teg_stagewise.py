"""Stage-wise counter-current water-transfer march for TEG columns (spec teg_contactor R2).

The shared solver behind the R2 TEG contactor rating (``teg_contactor_r2``) and
the R2 regenerator level that imports it. It solves N ideal counter-current
equilibrium stages for a single transferring solute (water) between a gas and a
solvent, in mole-ratio space on solute-free bases:

    gas    ``Y = n_w / G``   with ``G`` the dry-gas (solute-free) flow [mol/s]
    liquid ``X = n_w / S``   with ``S`` the solute-free solvent flow [mol/s]

Stage balances and equilibrium, stages ``j = 1..N`` numbered top to bottom:

    G * (Y_{j+1} - Y_j) = S * (X_j - X_{j-1})      X_0 = X_lean, Y_{N+1} = Y_in
    y_j = m(x_j) * x_j                             y = Y/(1+Y), x = X/(1+X)

The equilibrium line is supplied by the caller as ``x_of_y(Y) -> X``, the
stage-equilibrium inverse in ratio space, so the march is agnostic to the
activity model (the TEG adapter injects the Parrish-Won-Baltatu line; tests
inject a linear line and recover the closed-form Kremser solution exactly).

The unknown ``Y_1`` (gas leaving the top stage) is found by shooting downwards:
for a trial ``Y_1`` the stages are marched to ``Y_{N+1}``, and the residual
``r(Y_1) = Y_{N+1} - Y_in`` is driven to zero by bisection. The bracket comes
from a log-spaced scan of ``Y_1`` requiring exactly one sign change -- never a
fixed bracket such as ``[Y*(X_lean), Y_in]``, which can silently lock onto a
wrong root on curved equilibrium lines.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ngdesign.units.teg_activity import activity_equilibrium_slope

__all__ = ["TEGStageError", "countercurrent_march", "teg_x_of_y"]

#: Log-spaced bracket-scan bounds and resolution for the trial top-gas ratio Y_1.
_Y1_MIN = 1.0e-14
_Y1_MAX = 1.0e6
_SCAN_POINTS = 400

#: Bisection stop: |delta ln Y_1| below this, or hard iteration cap.
_LN_TOL = 1.0e-14
_MAX_ITERATIONS = 300

#: Sentinel residual returned by the shooter when a stage overshoots to Y < 0.
#: The true residual never reaches this value: it is bounded below by -Y_in
#: whenever no stage goes negative (the overshoot condition fires first).
_OVERSHOOT_SENTINEL = -1.0

#: Pure-water mole-fraction ceiling for the TEG liquid-phase inverse.
_X_WATER_MAX = 1.0 - 1.0e-12

#: TEG stage-equilibrium inverse bisection: iteration cap and interval stop.
#: The cap is defensive only: 200 halvings of [0, 1) always undercut the
#: 1e-15 interval stop, so the cap refusal is unreachable in practice.
_X_BISECTION_ITERATIONS = 200
_X_BISECTION_TOL = 1.0e-15


class TEGStageError(ValueError):
    """A counter-current stage march that cannot be bracketed or converged."""


def countercurrent_march(
    G: float,
    S: float,
    X_top_in: float,
    Y_bottom_in: float,
    n_stages: int,
    x_of_y: Callable[[float], float],
) -> tuple[list[float], list[float]]:
    """Solve N counter-current equilibrium stages for the water transfer.

    Args:
        G: Dry-gas (solute-free) molar flow [mol/s].
        S: Solute-free solvent molar flow [mol/s].
        X_top_in: Solvent inlet solute ratio ``X_0 = X_lean`` [mol/mol].
        Y_bottom_in: Gas inlet solute ratio ``Y_in`` [mol/mol].
        n_stages: Number of ideal stages, ``>= 1``.
        x_of_y: Stage-equilibrium inverse in ratio space, ``X(Y_j) -> X_j``.
            May return ``+inf`` when the trial ratio exceeds the pure-solute
            limit; the shooter treats that as an overshoot to the positive side.

    Returns:
        ``(Y, X)`` where ``Y`` is the gas ratio profile ``Y[0..N]``
        (``Y[0] = Y_1`` leaving the top stage, ``Y[N] = Y_{N+1}`` entering the
        bottom) and ``X`` the solvent profile ``X[1..N]``.

    Raises:
        TEGStageError: if the scan finds no sign change or more than one, or
            the bisection hits its iteration cap.
    """
    if not G > 0.0:
        raise ValueError(f"dry-gas flow G must be positive, got {G}")
    if not S > 0.0:
        raise ValueError(f"solute-free solvent flow S must be positive, got {S}")
    if n_stages < 1:
        raise ValueError(f"n_stages must be >= 1, got {n_stages}")
    if X_top_in < 0.0:
        raise ValueError(f"X_top_in must be non-negative, got {X_top_in}")
    if Y_bottom_in < 0.0:
        raise ValueError(f"Y_bottom_in must be non-negative, got {Y_bottom_in}")

    def residual(y1: float) -> float:
        """r(Y_1) = Y_{N+1}(Y_1) - Y_in; sentinels on stage overshoots."""
        y_j = y1
        x_prev = X_top_in
        for _ in range(n_stages):
            x_j = x_of_y(y_j)
            y_next = y_j + (S / G) * (x_j - x_prev)
            if y_next < 0.0:
                return _OVERSHOOT_SENTINEL
            if math.isinf(y_next):
                return math.inf
            y_j = y_next
            x_prev = x_j
        return y_j - Y_bottom_in

    lo, hi = _bracket(residual)
    y1 = _bisect(residual, lo, hi)

    # Final shoot at the converged Y_1 to report the full profiles.
    y_profile = [y1]
    x_profile: list[float] = []
    x_prev = X_top_in
    y_j = y1
    for _ in range(n_stages):
        x_j = x_of_y(y_j)
        y_next = y_j + (S / G) * (x_j - x_prev)
        y_profile.append(y_next)
        x_profile.append(x_j)
        y_j = y_next
        x_prev = x_j
    return y_profile, x_profile


def _ratio_to_fraction(r: float) -> float:
    """Mole ratio [mol solute / mol carrier] -> wet mole fraction."""
    return r / (1.0 + r)


def _fraction_to_ratio(y: float) -> float:
    """Wet mole fraction -> mole ratio [mol solute / mol carrier]."""
    return y / (1.0 - y)


def teg_x_of_y(T: float, P: float) -> Callable[[float], float]:
    """Build the TEG stage-equilibrium inverse ``X(Y)`` at gas (T, P).

    The one construction of the inverse ``X(Y_j)`` on the Parrish-Won-Baltatu
    activity line (``m(T, P, x) * x = y`` with ``y = Y/(1 + Y)``), shared by
    the R2 contactor and regenerator so the bisection constants and logic
    live in exactly one place. Bisection runs on ``x`` in ``[0, 1 - 1e-12]``.

    Returns:
        The inverse. ``+inf`` beyond the pure-water limit (``y >= 1``) and for
        non-finite or negative ratios, ``0.0`` at ``Y == 0`` exactly (dry gas:
        the inverse of zero is zero), otherwise ``X = x/(1 - x)``.
    """

    def x_of_y(y_ratio: float) -> float:
        if not math.isfinite(y_ratio) or y_ratio < 0.0:
            return math.inf
        if y_ratio == 0.0:
            return 0.0
        y = _ratio_to_fraction(y_ratio)
        if y >= 1.0:
            return math.inf
        lo, hi = 0.0, _X_WATER_MAX
        for _ in range(_X_BISECTION_ITERATIONS):
            mid = 0.5 * (lo + hi)
            if activity_equilibrium_slope(T, P, mid) * mid < y:
                lo = mid
            else:
                hi = mid
        # The interval stop fires first: 200 halvings of [0, 1) always
        # undercut 1e-15, so the cap check below is defensive.
        if hi - lo >= _X_BISECTION_TOL:
            raise TEGStageError(
                f"stage equilibrium inverse did not converge to "
                f"|delta x| < {_X_BISECTION_TOL:g} in "
                f"{_X_BISECTION_ITERATIONS} iterations"
            )
        return _fraction_to_ratio(0.5 * (lo + hi))

    return x_of_y


def _bracket(residual: Callable[[float], float]) -> tuple[float, float]:
    """Log-spaced scan for exactly one sign change of the residual.

    Returns the bracketing pair ``(lo, hi)`` with ``residual(lo) <= 0 <=
    residual(hi)``; a scan point with an exactly zero residual degenerates to
    ``(root, root)``.

    Raises:
        TEGStageError: on no sign change or more than one sign change.
    """
    changes: list[tuple[float, float]] = []
    exact: list[float] = []

    previous_y = _Y1_MIN
    previous_r = residual(previous_y)
    if previous_r == 0.0:
        exact.append(previous_y)
    for i in range(1, _SCAN_POINTS):
        y = _Y1_MIN * (_Y1_MAX / _Y1_MIN) ** (i / (_SCAN_POINTS - 1))
        r = residual(y)
        if r == 0.0:
            exact.append(y)
        elif previous_r < 0.0 <= r or r < 0.0 <= previous_r:
            changes.append((previous_y, y))
        previous_y, previous_r = y, r

    if exact:
        if changes or len(exact) > 1:
            listed = ", ".join(f"{y:.6g}" for y in exact)
            raise TEGStageError(f"multiple roots: exact roots at {listed}")
        return exact[0], exact[0]
    if not changes:
        raise TEGStageError(
            "no bracket: the residual has no sign change over the "
            f"log-spaced scan of Y_1 in [{_Y1_MIN:g}, {_Y1_MAX:g}]"
        )
    if len(changes) > 1:
        listed = ", ".join(f"[{lo:.6g}, {hi:.6g}]" for lo, hi in changes)
        raise TEGStageError(f"multiple roots: sign changes in {listed}")
    return changes[0]


def _bisect(residual: Callable[[float], float], lo: float, hi: float) -> float:
    """Bisect the bracket to |delta ln Y_1| < 1e-14 (cap 300 iterations)."""
    if residual(lo) > 0.0:
        lo, hi = hi, lo
    for _ in range(_MAX_ITERATIONS):
        mid = 0.5 * (lo + hi)
        # abs(): a decreasing residual hands over a bracket whose lo > hi,
        # so the plain log difference is negative and a signed stop test
        # would fire on iteration one, returning the raw scan midpoint
        # (up to half a scan step, ~6 % on the reviewer's measurement).
        if abs(math.log(hi) - math.log(lo)) < _LN_TOL:
            return mid
        r = residual(mid)
        if r == _OVERSHOOT_SENTINEL or r < 0.0:
            lo = mid
        else:
            hi = mid
    raise TEGStageError(
        f"bisection cap: |delta ln Y_1| did not reach {_LN_TOL:g} in {_MAX_ITERATIONS} iterations"
    )  # Defensive: a scan step is ~0.116 in ln Y, so ~44 halvings reach the
    # 1e-14 stop; the 300-iteration cap is never the first failure.
