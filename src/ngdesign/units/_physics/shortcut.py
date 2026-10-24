"""Shortcut-method physics for staged columns (spec U-E).

Pure functions, no package dependencies beyond :mod:`math`. Equation numbers
cite Seader, Henley & Roper, *Separation Process Principles*, 3rd ed.
(Wiley, 2011): chapter 9 for Fenske-Underwood-Gilliland-Kirkbride, chapters
5/6 for the Kremser absorption/stripping/extraction group methods.

Every constant typed here is checked against the book in
``tests/units/column/test_shortcut_physics.py``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

#: |A - 1| below this band uses the A -> 1 limit of the Kremser fraction.
_KREMSER_A_BAND = 1e-9

#: Above this exponent A**(N+1) saturates floating point; the fraction is 1.
_KREMSER_EXP_CAP = 350.0


def fenske_nmin(alpha_LK_HK: float, xD_LK: float, xD_HK: float, xB_LK: float, xB_HK: float) -> float:
    """Minimum equilibrium stages at total reflux, eq. (9-12).

    ``Nmin = log[(xD_LK/xD_HK) * (xB_HK/xB_LK)] / log(alpha_LK_HK)`` where the
    mole-fraction ratios use the *composition of each product stream* and
    ``alpha_LK_HK`` is the mean relative volatility (geometric mean of the top
    and bottom values, eq. (9-13)).

    Raises:
        ValueError: on non-physical inputs (non-positive alpha, alpha == 1,
            non-positive product mole fractions).
    """
    if alpha_LK_HK <= 0.0:
        raise ValueError(f"relative volatility alpha_LK_HK must be positive, got {alpha_LK_HK}")
    if math.isclose(alpha_LK_HK, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("relative volatility alpha_LK_HK must differ from 1")
    for name, value in (("xD_LK", xD_LK), ("xD_HK", xD_HK), ("xB_LK", xB_LK), ("xB_HK", xB_HK)):
        if value <= 0.0:
            raise ValueError(f"{name} must be positive, got {value}")
    separation = (xD_LK / xD_HK) * (xB_HK / xB_LK)
    return math.log(separation) / math.log(alpha_LK_HK)


def underwood_theta(alphas: Mapping[str, float], z: Mapping[str, float], q: float) -> float:
    """Underwood root theta of eq. (9-28): ``sum_i alpha_i z_i/(alpha_i - theta) = 1 - q``.

    ``alphas`` are relative volatilities referenced to the heavy key
    (``alpha_HK = 1``); the root returned is the one between ``alpha_HK`` and
    ``alpha_LK = max(alphas)``, per the spec's Class-2 single-root convention.
    Bisection; refuses when the root is not bracketed.

    Raises:
        ValueError: on non-positive alphas or compositions, ``q`` outside
            ``[0, 1]``, ``alpha_LK <= 1``, or an unbracketed root.
    """
    if not alphas:
        raise ValueError("alphas must not be empty")
    a_max = max(alphas.values())
    if a_max <= 1.0:
        raise ValueError(f"alpha_LK must exceed 1 (relative to the heavy key), got {a_max}")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"feed quality q must lie in [0, 1], got {q}")
    for cid, a in alphas.items():
        if a <= 0.0:
            raise ValueError(f"alpha[{cid}] must be positive, got {a}")
        if z.get(cid, 0.0) < 0.0:
            raise ValueError(f"z[{cid}] must be non-negative, got {z[cid]}")

    def residual(theta: float) -> float:
        return sum(a * z.get(cid, 0.0) / (a - theta) for cid, a in alphas.items()) - (1.0 - q)

    # f(1+) -> -inf through the alpha = 1 (heavy-key) term; f(alpha_LK-) -> +inf.
    lo, hi = 1.0 + 1e-12, a_max - 1e-12
    f_lo, f_hi = residual(lo), residual(hi)
    if not (f_lo < 0.0 < f_hi):
        raise ValueError(f"Underwood root not bracketed in ({lo}, {hi}): f = {f_lo:.6g}, {f_hi:.6g}")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if residual(mid) < 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def underwood_rmin(alphas: Mapping[str, float], xD: Mapping[str, float], theta: float) -> float:
    """Minimum reflux ratio from eq. (9-24)/(9-29): ``sum_i alpha_i xD_i/(alpha_i - theta) = 1 + Rmin``.

    ``xD`` is the distillate mole-fraction vector (undistributed components may
    carry xD = 0 and are skipped); ``alphas`` and ``theta`` come from the feed
    condition, as in the book's examples.

    Raises:
        ValueError: when a distributing component has ``alpha == theta``
            (singular term).
    """
    total = 0.0
    for cid, a in alphas.items():
        x = xD.get(cid, 0.0)
        if x <= 0.0:
            continue
        if math.isclose(a, theta, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"Underwood singularity: alpha[{cid}] equals theta {theta:.6g}")
        total += a * x / (a - theta)
    return total - 1.0


def gilliland(R: float, Rmin: float, Nmin: float) -> float:
    """Equilibrium stages at reflux ratio R, Molokanov et al. (1972) form of the
    Gilliland correlation, eq. (9-34):

    ``X = (R - Rmin)/(R + 1)``;

    ``Y = 1 - exp[((1 + 54.4 X)/(11 + 117.2 X)) * (X - 1)/sqrt(X)]``;

    ``N = (Nmin + Y)/(1 - Y)``.

    Raises:
        ValueError: on negative inputs, ``R <= Rmin`` (no separation is possible
            at or below minimum reflux), or a non-positive ``Nmin``.
    """
    if R < 0.0 or Rmin < 0.0:
        raise ValueError(f"reflux ratios must be non-negative, got R={R}, Rmin={Rmin}")
    if Nmin <= 0.0:
        raise ValueError(f"Nmin must be positive, got {Nmin}")
    if R <= Rmin:
        raise ValueError(f"R ({R}) must exceed Rmin ({Rmin}); N is unbounded below Rmin")
    x = (R - Rmin) / (R + 1.0)
    y = 1.0 - math.exp(((1.0 + 54.4 * x) / (11.0 + 117.2 * x)) * (x - 1.0) / math.sqrt(x))
    return (Nmin + y) / (1.0 - y)


def kirkbride(z_F_HK: float, z_F_LK: float, xB_LK: float, xD_HK: float, B_over_D: float) -> float:
    """Kirkbride (1944) feed-stage location ratio, eq. (9-36):

    ``N_R/N_S = [(z_F_HK/z_F_LK) * (xB_LK/xD_HK)^2 * (B/D)]**0.206``

    with feed and product mole fractions as weight fractions in the original
    correlation; mole fractions are the book's examples' choice.

    Raises:
        ValueError: on non-positive inputs.
    """
    for name, value in (
        ("z_F_HK", z_F_HK),
        ("z_F_LK", z_F_LK),
        ("xB_LK", xB_LK),
        ("xD_HK", xD_HK),
        ("B_over_D", B_over_D),
    ):
        if value <= 0.0:
            raise ValueError(f"kirkbride {name} must be positive, got {value}")
    return float(((z_F_HK / z_F_LK) * (xB_LK / xD_HK) ** 2 * B_over_D) ** 0.206)


def kremser_fraction(A: float, N: float) -> float:
    """Fraction absorbed (or stripped) across N ideal stages, eq. (5-46)/(6-13):

    ``phi = (A**(N+1) - A)/(A**(N+1) - 1)``, with the ``A -> 1`` limit ``N/(N+1)``.

    In the absorption form ``A = L/(K*V)`` this is the fraction of a
    gas-feed component absorbed by a solute-free solvent; in the stripping
    form ``S = K*V/L`` it is the fraction of a liquid-feed component stripped.
    The fraction *not* transferred is ``1 - kremser_fraction(A, N) =
    (A - 1)/(A**(N+1) - 1)``, eq. (5-48)/(5-50). This is the inverse form of
    :func:`ngdesign.sizing.kremser` (stage count from a recovery): pinned by a
    round-trip test.

    Raises:
        ValueError: on ``A <= 0`` or ``N < 0``.
    """
    if A <= 0.0:
        raise ValueError(f"absorption factor A must be positive, got {A}")
    if N < 0.0:
        raise ValueError(f"stage count N must be non-negative, got {N}")
    if abs(A - 1.0) < _KREMSER_A_BAND:
        return N / (N + 1.0)
    log_a2 = (N + 1.0) * math.log(A)
    if log_a2 > _KREMSER_EXP_CAP:
        return 1.0
    a2 = math.exp(log_a2)
    return (a2 - A) / (a2 - 1.0)


def kremser_stage_count(A: float, phi: float) -> float:
    """Stages N that make :func:`kremser_fraction` return ``phi`` at factor ``A``.

    Inverse of :func:`kremser_fraction`:
    ``N = log((A - phi)/(1 - phi))/log(A) - 1``.

    Raises:
        ValueError: on non-physical inputs or when ``phi`` is unreachable at
            this ``A`` (``phi >= 1``, or ``phi >= A`` for ``A < 1``).
    """
    if A <= 0.0:
        raise ValueError(f"absorption factor A must be positive, got {A}")
    if not 0.0 < phi < 1.0:
        raise ValueError(f"fraction phi must lie in (0, 1), got {phi}")
    if abs(A - 1.0) < _KREMSER_A_BAND:
        if abs(phi - 1.0) < _KREMSER_A_BAND:
            raise ValueError("phi -> 1 requires A -> 1 with N -> inf")
        return phi / (1.0 - phi)
    if A < 1.0 and phi >= A:
        raise ValueError(f"phi {phi} is unreachable at A = {A} (limit A as N grows)")
    ratio = (A - phi) / (1.0 - phi)
    if ratio <= 0.0:
        raise ValueError(f"phi {phi} is unreachable at A = {A}")
    return math.log(ratio) / math.log(A) - 1.0
