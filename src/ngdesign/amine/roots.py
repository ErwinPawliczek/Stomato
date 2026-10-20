"""1-D bracketed root finding shared by the amine property models.

``brent_root`` moved here verbatim from the units' ``mdea_equilibrium`` module
(same algorithm, same tolerances, made public): the root finder is chemistry
infrastructure and lives with the property packages -- unit operations consume
it, never the other way round.
"""

from __future__ import annotations

import math
from collections.abc import Callable

__all__ = ["brent_root"]


def brent_root(
    fn: Callable[[float], float], lo: float, hi: float, xtol: float = 1e-12, max_iter: int = 100
) -> float:
    """Hand-rolled Brent root finder on [lo, hi] (requires fn(lo)*fn(hi) <= 0).

    Classic bisection/secant/inverse-quadratic hybrid (Brent 1973; the scipy
    ``brentq`` algorithm).  A failing bracket raises -- errors are never
    swallowed.
    """
    a, b = lo, hi
    fa, fb = fn(a), fn(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError(f"root not bracketed: fn({lo})={fa}, fn({hi})={fb}")
    c, fc = a, fa
    d = e = hi - lo
    for _ in range(max_iter):
        if fb * fc > 0.0:
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, fa = b, fb
            b, fb = c, fc
            c, fc = a, fa
        tol1 = 2.0 * xtol * abs(b) + 0.5 * xtol
        xm = 0.5 * (c - b)
        if abs(xm) <= tol1 or fb == 0.0:
            return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2.0 * xm * s
                q = 1.0 - s
            else:
                q = fa / fc
                r = fb / fc
                p = s * (2.0 * xm * q * (q - r) - (b - a) * (r - 1.0))
                q = (q - 1.0) * (r - 1.0) * (s - 1.0)
            if p > 0.0:
                q = -q
            p = abs(p)
            if 2.0 * p < min(3.0 * xm * q - abs(tol1 * q), abs(e * q)):
                e, d = d, p / q
            else:
                d = e = xm
        else:
            d = e = xm
        a, fa = b, fb
        step = d if abs(d) > tol1 else math.copysign(tol1, xm)
        b, fb = b + step, fn(b + step)
    raise ValueError(f"Brent solver did not converge in {max_iter} iterations")
