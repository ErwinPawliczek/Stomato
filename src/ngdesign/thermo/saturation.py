"""The one saturation solver over a vapour-fraction callable (spec P1-08).

``thermo._state._saturation`` (P1-01) and ``amine.package._boundary`` (P1-04)
implemented the same plateau-scan-then-bracket algorithm twice with different
tolerances and bracket rules; both now call the solver defined here,
parameterised by a ``vf_at(x) -> float`` callable and caller-computed brackets.

Method (P1-01 semantics; Michelsen & Mollerup, Thermodynamic Models:
Fundamentals and Computational Aspects, ch. 10 — saturation):

- Brackets come from Wilson-correlation bounds — deliberately rough but
  defined past Tc, where supercritical components still push the mixture
  bubble pressure up (the P1-01 finding); the caller computes and passes
  them, so this module stays free of component data.
- The vapour fraction is continuous inside the two-phase envelope but
  plateaus at the bubble/dew target outside it (and PR flashes can turn
  away from the plateau again), so plateau ends are matched within
  ``plateau_eps`` (1e-6) rather than by equality, and a non-plateau initial
  end is scanned geometrically (factor ``scan``) onto the plateau: first
  toward the opposite end (a spurious two-phase split above a bubble point
  can push the initial end past the plateau), then outward from it.
- The non-plateau end is then tightened away from the target so the secant
  sees a slope, and a secant iteration safeguarded by bisection inside the
  bracket drives the bracket width to ``rel_tol`` (1e-8 relative on the
  unknown) in at most ``max_iter`` (60) evaluations.

:func:`interior_vf_solve` handles interior vapour-fraction targets (the
TVF/PVF case): an orientation-agnostic bracketed secant that returns the
first iterate whose residual reaches ``target_tol``, falling back to the
bracket end with the smaller residual.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NamedTuple

from ngdesign.contracts.thermo import SaturationError

__all__ = ["interior_vf_solve", "solve_saturation"]

#: Bracket-refinement loop cap (expansions/shrinks) before declaring no plateau.
_BRACKET_REFINEMENTS = 40


class _Solution(NamedTuple):
    """Converged unknown value plus the last interior (0 < vf < 1) evaluation."""

    x: float
    interior_x: float | None


def _where(label: str | None) -> str:
    """Location suffix for solver error messages."""
    return f" at {label}" if label is not None else ""


def solve_saturation(
    vf_at: Callable[[float], float],
    *,
    kind: Literal["bubble", "dew"],
    unknown: Literal["P", "T"],
    bounds: tuple[float, float],
    rel_tol: float = 1e-8,
    max_iter: int = 60,
    plateau_eps: float = 1e-6,
    scan: float = 1.3,
    label: str | None = None,
) -> float:
    """Solve the bubble (vf -> 0) or dew (vf -> 1) point of ``vf_at``.

    ``unknown`` names the variable being solved for ("P" at fixed T, "T" at
    fixed P) — it fixes which bracket end carries the target plateau (bubble:
    high P / low T; dew: low P / high T).  ``bounds`` is the initial
    (low, high) bracket of the unknown, typically Wilson-correlation bounds.
    Returns the unknown at the converged bracket midpoint.

    ``label`` is optional location text (e.g. "T=300 K") carried into
    :class:`SaturationError` messages.
    """
    return _solve_saturation(
        vf_at,
        kind=kind,
        unknown=unknown,
        bounds=bounds,
        rel_tol=rel_tol,
        max_iter=max_iter,
        plateau_eps=plateau_eps,
        scan=scan,
        label=label,
    ).x


def _scan_to_plateau(
    vf_at: Callable[[float], float],
    start: float,
    other: float,
    target: float,
    plateau_eps: float,
    scan: float,
    label: str | None,
) -> tuple[float, float]:
    """Move one bracket end onto the first vf == target plateau.

    Scans first between ``start`` and ``other`` — a spurious PR two-phase split
    above a bubble point can push the initial end past the plateau — then
    outward from ``start``. Raises SaturationError when no plateau is in reach.
    """
    downward = start > other
    x = start
    for _ in range(_BRACKET_REFINEMENTS):
        xn = x / scan if downward else x * scan
        if (xn <= other) if downward else (xn >= other):
            break
        vn = vf_at(xn)
        if abs(vn - target) <= plateau_eps:
            return xn, vn
        x = xn
    x = start
    for _ in range(_BRACKET_REFINEMENTS):
        x = x * scan if downward else x / scan
        v = vf_at(x)
        if abs(v - target) <= plateau_eps:
            return x, v
    raise SaturationError(f"no two-phase bracket found{_where(label)}")


def _solve_saturation(
    vf_at: Callable[[float], float],
    *,
    kind: Literal["bubble", "dew"],
    unknown: Literal["P", "T"],
    bounds: tuple[float, float],
    rel_tol: float = 1e-8,
    max_iter: int = 60,
    plateau_eps: float = 1e-6,
    scan: float = 1.3,
    label: str | None = None,
) -> _Solution:
    """The plateau-scan-then-bracketed-secant solve; see :func:`solve_saturation`."""
    lo, hi = bounds
    target = 0.0 if kind == "bubble" else 1.0

    # bubble: vf == 0 plateau at high P (P unknown) / low T (T unknown);
    # dew: the opposite ends.
    if unknown == "P":
        flat: Literal["lo", "hi"] = "hi" if kind == "bubble" else "lo"
    else:
        flat = "lo" if kind == "bubble" else "hi"

    lo_vf = vf_at(lo)
    hi_vf = vf_at(hi)
    if flat == "hi" and abs(hi_vf - target) > plateau_eps:
        hi, hi_vf = _scan_to_plateau(vf_at, hi, lo, target, plateau_eps, scan, label)
    if flat == "lo" and abs(lo_vf - target) > plateau_eps:
        lo, lo_vf = _scan_to_plateau(vf_at, lo, hi, target, plateau_eps, scan, label)

    # tighten the non-plateau end away from the target so the secant sees a slope
    for _ in range(_BRACKET_REFINEMENTS):
        if flat == "hi":
            if abs(lo_vf - target) > plateau_eps:
                break
            lo, lo_vf = lo / scan, vf_at(lo / scan)
        else:
            if abs(hi_vf - target) > plateau_eps:
                break
            hi, hi_vf = hi * scan, vf_at(hi * scan)
    else:
        raise SaturationError(f"no two-phase bracket found{_where(label)}")

    g_lo = lo_vf - target
    g_hi = hi_vf - target
    if g_lo >= 0.0 and g_hi <= 0.0:
        x_pos, g_pos, x_neg, g_neg = lo, g_lo, hi, g_hi
    elif g_hi >= 0.0 and g_lo <= 0.0:
        x_pos, g_pos, x_neg, g_neg = hi, g_hi, lo, g_lo
    else:
        raise SaturationError(f"bracket does not straddle the {kind} point{_where(label)}")

    interior_x: float | None = None
    for _ in range(max_iter):
        width = abs(x_pos - x_neg)
        if width <= rel_tol * min(abs(x_pos), abs(x_neg)):
            break
        if g_pos != 0.0 and g_neg != 0.0:
            x = x_pos - g_pos * (x_neg - x_pos) / (g_neg - g_pos)
            if not min(x_pos, x_neg) < x < max(x_pos, x_neg):
                x = 0.5 * (x_pos + x_neg)
        else:
            x = 0.5 * (x_pos + x_neg)
        v = vf_at(x)
        g = v - target
        if 0.0 < v < 1.0:
            interior_x = x
        if g > 0.0:
            x_pos, g_pos = x, g
        elif g < 0.0:
            x_neg, g_neg = x, g
        elif g_pos == 0.0:
            x_pos, g_pos = x, 0.0
        elif g_neg == 0.0:
            x_neg, g_neg = x, 0.0
        elif flat == "lo":
            x_pos, g_pos = x, 0.0  # plateau sits at the g >= 0 end (lo)
        else:
            x_neg, g_neg = x, 0.0  # plateau sits at the g <= 0 end (hi)
    return _Solution(0.5 * (x_pos + x_neg), interior_x)


def interior_vf_solve(
    vf_at: Callable[[float], float],
    target: float,
    lo: float,
    hi: float,
    *,
    rel_tol: float = 1e-8,
    max_iter: int = 60,
    target_tol: float = 1e-9,
) -> float:
    """Bracketed secant for an interior vapour-fraction target between lo and hi.

    Orientation-agnostic: after normalization ``lo`` is the end with g >= 0,
    ``hi`` the end with g <= 0, so callers may pass the bracket in either
    order.  Returns the first iterate whose residual reaches ``target_tol``;
    when the iteration cap is hit first, the end with the smaller residual
    (one-sided secant convergence can park the far end at the bracket bound
    while the near end sits on the root).
    """
    lo_v = vf_at(lo)
    hi_v = vf_at(hi)
    if lo_v - target < 0.0 <= hi_v - target:
        lo, hi = hi, lo
        lo_v, hi_v = hi_v, lo_v
    for _ in range(max_iter):
        if abs(hi - lo) <= rel_tol * min(abs(lo), abs(hi)):
            break
        g_lo = lo_v - target
        g_hi = hi_v - target
        if g_lo != 0.0 and g_hi != 0.0:
            x = lo - g_lo * (hi - lo) / (g_hi - g_lo)
            if not min(lo, hi) < x < max(lo, hi):
                x = 0.5 * (lo + hi)
        else:
            x = 0.5 * (lo + hi)
        v = vf_at(x)
        g = v - target
        if abs(g) <= target_tol:
            return x
        if g > 0.0:
            lo, lo_v = x, v
        elif g < 0.0:
            hi, hi_v = x, v
        else:
            return x
    # One-sided secant convergence (vf curves are typically convex through the
    # target) can leave the far end parked at the bracket bound while the near
    # end sits on the root: return the end with the smaller residual rather
    # than a misleading midpoint.
    return lo if abs(lo_v - target) <= abs(hi_v - target) else hi
