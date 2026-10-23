"""Crude assay conversion, completion and pseudo-component cutting (spec A-01).

Converts measured refinery distillation data (ASTM D86, D2887, D1160) to a
full-range TBP curve and cuts it into pseudo-components. Every numeric constant
is quoted from a printed public source, recorded at its definition. Method
notes fixed by the spec and the source research behind them:

- **D86 to TBP** uses the Riazi-Daubert two-parameter form
  ``T_TBP = a * T_D86(K) ** b`` (API TDB procedure 3A1.1), constants per vol%
  point; Riazi, M.R., *Characterization and Properties of Petroleum Fractions*,
  ASTM MNL50 (2005), section 3.2.2.1 p. 102. The printed table stops at 95 %;
  the 100 % endpoint is not produced by the pointwise conversion.
- **TBP to D86** is the analytic inverse of the same correlation (no separate
  printed inverse table is publicly verifiable; an inverse of a published
  correlation introduces no new constants).
- **D2887 to TBP** uses Daubert's (1994) increment form (API TDB 3A3.1):
  ``TBP(50 %) = SD(50 %)``, ``dT_TBP(F) = C * dT_SD(F) ** D`` per printed
  interval, accumulated outward from 50 %; API TDB chapter 3 procedure 3A3.1
  table (2025 ballot draft, "Conversion of Simulated Distillation Assays to
  True Boiling Point Distillations"), cross-checked against the Riazi (2005)
  MNL50 section 3.2.2.2 p. 103 K/C form of the same constants and against the
  worked example transcribed in Kopisto (LUT thesis, 2017) Tables V/VII,
  reproduced in tests/data/test_assay.py.
- **D1160 to AET** uses Maxwell & Bonnell (1957) as printed in ASTM D1160
  annex A7.1 transcriptions and API TDB 5A1.19, with the pressure in kPa. Two
  printed constant sets circulate, one labelled mmHg; only the kPa reading is
  self-consistent: it reproduces the defining limit AET(P = 101.325 kPa) = T
  within 0.2 K, and both constant branches agree at the 0.2667 kPa switch
  within 0.05 % (checked numerically in the A-01 tests).
- **D1160 AET to TBP** uses API TDB procedure 3A2.1, constants from the
  secondary printed reproduction (Riazi 2005 section 3.2.2.3 p. 106 area); no
  independently printable worked example exists.
- **Curve completion to 0 % / 100 %** fits the Riazi (2005, MNL50 section
  4.5.4) generalized distribution model ``T(x) = alpha + A * (-ln(1-x)) ** B``
  (the versatile correlation, Riazi 1989, I&EC Res. 28, 1731-1735, with a
  fitted location shift) to the measured points by nonlinear least squares.
  The model is unbounded as x -> 1, so the reported 0 % / 100 % endpoints are
  the 0.05 vol% / 99.95 vol% quantiles of the fitted model; interpolation on
  the completed curve is piecewise linear.
- **Gravity distribution** defaults to a constant Watson K from the bulk
  gravity and the curve's mean average boiling point,
  ``sg(Tb) = (1.8 * Tb_K) ** (1/3) / K_w``. The printed MeABP - VABP
  correction (Riazi 2005 eq. 3.6, section 3.2.1 p. 100) has no verifiable
  public transcription - the circulating constants give an impossible ~57 K
  correction for a light naphtha - so VABP is used as the MeABP estimate
  unless the caller supplies ``meabp_k_override`` or ``watson_k_override``
  explicitly. For narrow cuts VABP approximates MeABP to well under 1 K; the
  whole-crude effect on the cut slate is measured and reported in the A-01
  tests.
- **Basis conversion** of cut fractions is volume-additive mixing: volume <->
  mass through specific gravity, mass <-> mole through molecular weight
  (pseudo-components: Riazi & Daubert 1980 MW; light ends: databank records).

This module sits at the bottom of the import layering: it accepts assay-shaped
inputs structurally (no import of ``ngdesign.contracts``) and returns data-layer
:class:`ngdesign.data.PseudoDefinition` records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from scipy.optimize import least_squares

from ngdesign.data import PseudoDefinition, _riazi_daubert_mw, component_record

# --------------------------------------------------------------------------- curve plumbing

#: Standard vol% grid the pointwise correlations are defined on (API TDB 3A1.1 /
#: 3A2.1 / 3A3.1). 100 % is handled separately (extrapolation / accumulation).
STD_GRID = (0.0, 10.0, 30.0, 50.0, 70.0, 90.0, 95.0)


class CurveLike(Protocol):
    """Structural view of a measured distillation curve (see contracts.assay)."""

    # Read-only members, so the frozen contract model (Literal-typed fields)
    # satisfies the protocol structurally.
    @property
    def kind(self) -> str: ...  # "TBP" | "D86" | "D1160" | "D2887"
    @property
    def basis(self) -> str: ...  # "LV%" | "wt%"
    @property
    def points(self) -> list[tuple[float, float]]: ...  # (percent, T_K)
    @property
    def P_kPa(self) -> float | None: ...


def _interp(points: list[tuple[float, float]], percent: float) -> float:
    """Piecewise-linear interpolation of temperature at ``percent`` (K)."""
    if percent < points[0][0] or percent > points[-1][0]:
        raise ValueError(f"percent {percent} outside curve [{points[0][0]}, {points[-1][0]}]")
    for (p1, t1), (p2, t2) in zip(points, points[1:], strict=False):
        if p1 <= percent <= p2:
            if p2 == p1:
                return t1
            return t1 + (t2 - t1) * (percent - p1) / (p2 - p1)
    raise AssertionError("unreachable: percent inside curve range")


def _to_std_grid(points: list[tuple[float, float]]) -> dict[float, float]:
    """Temperatures (K) at the standard grid points covered by ``points``."""
    return {p: _interp(points, p) for p in STD_GRID if points[0][0] <= p <= points[-1][0]}


# --------------------------------------------------------------------------- D86 <-> TBP (API 3A1.1)

#: API TDB 3A1.1 / Riazi-Daubert (T in K): TBP = a * T_D86 ** b, per vol% point.
#: Riazi (2005) MNL50 section 3.2.2.1 p. 102; the printed worked example next to
#: the table (D86 36.5/54.1/76.9/101.5/131.0/171.0 C at 0/10/30/50/70/90 vol% ->
#: TBP 14.1/33.4/68.9/101.6/135.1/180.5 C) is reproduced in tests/data/test_assay.py.
D86_TO_TBP_AB: dict[float, tuple[float, float]] = {
    0.0: (0.9177, 1.0019),
    10.0: (0.5564, 1.0900),
    30.0: (0.7617, 1.0425),
    50.0: (0.9013, 1.0176),
    70.0: (0.8821, 1.0226),
    90.0: (0.9552, 1.0110),
    95.0: (0.8177, 1.0355),
}


def d86_to_tbp_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Measured D86 points (percent, K) -> TBP points (percent, K), API 3A1.1.

    Pointwise on the standard grid covered by the measurement. The 100 %
    endpoint is not produced here (the printed table stops at 95 %); use
    :func:`complete_curve` for endpoint extrapolation.
    """
    return [(p, a * t**b) for p, t in sorted(_to_std_grid(points).items()) for a, b in (D86_TO_TBP_AB[p],)]


def tbp_to_d86_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """TBP points (percent, K) -> D86 points (percent, K), analytic inverse of 3A1.1.

    T_D86 = (T_TBP / a) ** (1/b) at each standard grid point.
    """
    return [
        (p, (t / a) ** (1.0 / b))
        for p, t in sorted(_to_std_grid(points).items())
        for a, b in (D86_TO_TBP_AB[p],)
    ]


# --------------------------------------------------------------------------- D2887 -> TBP (API 3A3.1)

#: Daubert (1994) / API TDB 3A3.1 increment constants, per simulated-distillation
#: interval: dT_TBP(F) = C * dT_SD(F) ** D, where dT_SD is the SD temperature
#: difference across the printed vol% interval. Verified line by line against
#: the printed API TDB chapter 3 procedure 3A3.1 table (2025 ballot draft);
#: the same constants appear as a K/C form in Riazi (2005) MNL50 section
#: 3.2.2.2 p. 103 (C_K = C_F * 1.8**(1 - D)) and reproduce the worked example
#: transcribed in Kopisto (LUT thesis, 2017) Tables V/VII. Key: (lo, hi) of the
#: interval in vol%.
#:
#: The last row is printed "10 % - 5 %" in the ballot table while equation
#: (3A3.1-3) applies it from the 10 % point to reach TBP(5 %) and Riazi (2005)
#: Table 3.7 labels the interval "10-0"; implemented as the 10-0 % width.
#: The "approx. max. allowable dT_SD" column of the printed table (40/75 F by
#: interval) is advisory ("approx.") and is not enforced - the printed worked
#: example itself exceeds one of them.
D2887_TO_TBP_CD: dict[tuple[float, float], tuple[float, float]] = {
    (95.0, 100.0): (0.02172, 1.9733),
    (90.0, 95.0): (0.97476, 0.8723),
    (70.0, 90.0): (0.31531, 1.2938),
    (50.0, 70.0): (0.19861, 1.3975),
    (30.0, 50.0): (0.05342, 1.6988),
    (10.0, 30.0): (0.011903, 2.0253),
    (0.0, 10.0): (0.15779, 1.4296),
}


def d2887_to_tbp_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Measured D2887 (simulated distillation) points (percent, K) -> TBP points (K).

    The printed equations (API TDB 3A3.1) anchor TBP(50 %) = SD(50 %) and
    accumulate converted interval widths outward: TBP(70) = TBP(50) + W4,
    TBP(90) = TBP(70) + W3, TBP(95) = TBP(90) + W2, TBP(100) = TBP(95) + W1
    upward and TBP(30) = TBP(50) - W5, TBP(10) = TBP(30) - W6,
    TBP(5) = TBP(50) - W5 - W6 - W7 downward, with W_i = C * dT_SD ** D in F
    per the table above. Points whose interval endpoints fall outside the
    measured range are skipped; the printed equations produce no 0 % point.
    """
    pts = sorted(points)
    if 50.0 < pts[0][0] or 50.0 > pts[-1][0]:
        raise ValueError("D2887 conversion needs the 50 % point (TBP50 = SD50)")
    needed = (0.0, 10.0, 30.0, 50.0, 70.0, 90.0, 95.0, 100.0)
    sd = {p: _interp(pts, p) for p in needed if pts[0][0] <= p <= pts[-1][0]}

    def width_f(lo: float, hi: float) -> float | None:
        if lo not in sd or hi not in sd:
            return None
        return (sd[hi] - sd[lo]) * 1.8

    def step(w_f: float | None, interval: tuple[float, float]) -> float | None:
        if w_f is None:
            return None
        c, d = D2887_TO_TBP_CD[interval]
        return float(c * w_f**d) / 1.8  # K (float(): typeshed types float**float as Any)

    tbp: dict[float, float] = {}
    if 50.0 in sd:
        tbp[50.0] = sd[50.0]
    w5 = step(width_f(30.0, 50.0), (30.0, 50.0))
    w6 = step(width_f(10.0, 30.0), (10.0, 30.0))
    w7 = step(width_f(0.0, 10.0), (0.0, 10.0))
    w4 = step(width_f(50.0, 70.0), (50.0, 70.0))
    w3 = step(width_f(70.0, 90.0), (70.0, 90.0))
    w2 = step(width_f(90.0, 95.0), (90.0, 95.0))
    w1 = step(width_f(95.0, 100.0), (95.0, 100.0))
    if w4 is not None:
        tbp[70.0] = tbp[50.0] + w4
    if w3 is not None and 70.0 in tbp:
        tbp[90.0] = tbp[70.0] + w3
    if w2 is not None and 90.0 in tbp:
        tbp[95.0] = tbp[90.0] + w2
    if w1 is not None and 95.0 in tbp:
        tbp[100.0] = tbp[95.0] + w1
    if w5 is not None:
        tbp[30.0] = tbp[50.0] - w5
    if w6 is not None and 30.0 in tbp:
        tbp[10.0] = tbp[30.0] - w6
    if w5 is not None and w6 is not None and w7 is not None:
        tbp[5.0] = tbp[50.0] - w5 - w6 - w7
    return sorted(tbp.items())


# --------------------------------------------------------------------------- D1160 -> AET (Maxwell-Bonnell)

#: Maxwell-Bonnell (1957) / API TDB 5A1.19 / ASTM D1160 annex A7.1 constants.
#: AET = 748.1*A / (1/(T_C + 273.1) + 0.3861*A - 0.00051606) - 273.1 with
#: A = (5.143222 - 0.972546*log10 P)/(2579.329 - 95.76*log10 P) for P >= 0.2667
#: kPa (2 mmHg) and A = (5.897249 - 0.987672*log10 P)/(2962.909 - 43.00*log10 P)
#: below; P in kPa abs. The mmHg-labelled transcription variant is numerically
#: inconsistent with the 101.325 kPa identity and is not used.
_MB_HIGH = (5.143222, 0.972546, 2579.329, 95.76)
_MB_LOW = (5.897249, 0.987672, 2962.909, 43.00)
_MB_SWITCH_KPA = 2.0 * 0.133322  # 2 mmHg


def d1160_aet_c(t_vapor_c: float, p_kpa: float) -> float:
    """One D1160 vapor temperature (C at ``p_kpa``) -> atmospheric equivalent temperature (C)."""
    if p_kpa <= 0.0:
        raise ValueError("pressure must be positive (kPa abs)")
    num_c, num_k, den_c, den_k = _MB_HIGH if p_kpa >= _MB_SWITCH_KPA else _MB_LOW
    log_p = math.log10(p_kpa)
    a = (num_c - num_k * log_p) / (den_c - den_k * log_p)
    return 748.1 * a / (1.0 / (t_vapor_c + 273.1) + 0.3861 * a - 0.00051606) - 273.1


# --------------------------------------------------------------------------- D1160 AET -> TBP (API 3A2.1)

#: API TDB procedure 3A2.1 is graphical (Figure 3A2.1): at 10 mmHg, TBP and
#: D1160 temperatures are equal at 50 vol% and above; below 50 % each segment
#: temperature difference (F) converts through the printed curves. The
#: "10 % to 30 % and 30 % to 50 %" curve below is digitized from the printed
#: figure (API TDB chapter 3, Figure 3A2.1, created 1974, remastered 2012) by
#: calibrated image tracing at 300 dpi; the printed worked example next to the
#: figure (difference 75 F -> 82 F and 100 F -> 106 F on this curve) is
#: reproduced within 1 F. Digitized entries carry ~+-2 F figure-reading
#: uncertainty; the table is (dT_D1160_F, dT_TBP_F) at 5 F steps, piecewise
#: linear, identity beyond 155 F where the printed curve meets the diagonal.
#: The printed "0 % to 10 %" curve is NOT digitized or applied: no printed
#: numeric anchor exists for it, so no 0 % point is produced (curve completion
#: supplies the endpoint).
_D1160_SEG_10_50: tuple[tuple[float, float], ...] = (
    (0.0, 0.0),
    (5.0, 6.1),
    (10.0, 12.3),
    (15.0, 18.5),
    (20.0, 24.7),
    (25.0, 30.9),
    (30.0, 36.8),
    (35.0, 42.3),
    (40.0, 47.8),
    (45.0, 53.2),
    (50.0, 58.3),
    (55.0, 63.4),
    (60.0, 68.4),
    (65.0, 73.3),
    (70.0, 78.2),
    (75.0, 82.9),
    (80.0, 87.5),
    (85.0, 92.0),
    (90.0, 96.4),
    (95.0, 100.8),
    (100.0, 105.5),
    (105.0, 110.2),
    (110.0, 115.0),
    (115.0, 119.7),
    (120.0, 124.2),
    (125.0, 128.8),
    (130.0, 133.3),
    (135.0, 138.1),
    (140.0, 142.8),
    (145.0, 147.5),
    (150.0, 152.0),
    (155.0, 156.2),
)

#: 10 mmHg in kPa abs (module pressure convention: 1 mmHg = 0.133322 kPa).
_D1160_10MMHG_KPA = 10.0 * 0.133322


class UnverifiedConversionError(ValueError):
    """A requested conversion has no verifiable printed source; it is refused.

    Raised, not approximated: an unverified constant cannot be caught by
    consistency tests (see the module docstring).
    """


def _fig32a1_increment(d_tbp_f: float) -> float:
    """D1160 segment difference -> TBP segment difference (F), Figure 3A2.1."""
    if d_tbp_f < 0.0:
        raise ValueError("segment temperature difference must be non-negative")
    if d_tbp_f <= _D1160_SEG_10_50[-1][0]:
        for (x1, y1), (x2, y2) in zip(_D1160_SEG_10_50, _D1160_SEG_10_50[1:], strict=False):
            if x1 <= d_tbp_f <= x2:
                return y1 + (y2 - y1) * (d_tbp_f - x1) / (x2 - x1)
        raise AssertionError("unreachable: difference inside table range")
    return d_tbp_f  # beyond the printed curve extent the figure reads as the identity


def d1160_tbp10_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """D1160 points at 10 mmHg (percent, K) -> TBP points at 10 mmHg (K).

    API TDB Figure 3A2.1: TBP = D1160 at 50 % and above; below 50 % the
    10-30 and 30-50 segment differences convert through the digitized printed
    curve, accumulated downward from the 50 % anchor. No 0 % point is produced
    (see the digitization note above).
    """
    pts = sorted(points)
    if 50.0 < pts[0][0] or 50.0 > pts[-1][0]:
        raise UnverifiedConversionError(
            "D1160 -> TBP needs the 50 % point (the printed 3A2.1 procedure anchors there)"
        )
    grid = {p: _interp(pts, p) for p in (10.0, 30.0, 50.0, 70.0, 90.0, 95.0) if pts[0][0] <= p <= pts[-1][0]}
    tbp: dict[float, float] = {50.0: grid[50.0]}
    for p in (70.0, 90.0, 95.0):
        if p in grid:
            tbp[p] = grid[p]  # printed: 50 % and above are equal at 10 mmHg
    if 30.0 in grid:
        dt_f = (grid[50.0] - grid[30.0]) * 1.8
        tbp[30.0] = tbp[50.0] - _fig32a1_increment(dt_f) / 1.8
    if 10.0 in grid and 30.0 in tbp:
        dt_f = (grid[30.0] - grid[10.0]) * 1.8
        tbp[10.0] = tbp[30.0] - _fig32a1_increment(dt_f) / 1.8
    return sorted(tbp.items())


def d1160_to_tbp_points(points: list[tuple[float, float]], p_kpa: float) -> list[tuple[float, float]]:
    """Measured D1160 points (percent, K at ``p_kpa``) -> TBP points (percent, K).

    Two steps, as printed: D1160 at 10 mmHg -> TBP at 10 mmHg (Figure 3A2.1),
    then TBP at 10 mmHg -> atmospheric equivalent (Maxwell-Bonnell). Only
    10 mmHg input is verifiable; any other test pressure is refused.
    """
    if abs(p_kpa - _D1160_10MMHG_KPA) > 0.02:
        raise UnverifiedConversionError(
            "D1160 -> TBP is only implemented for data measured at 10 mmHg "
            f"(1.33322 kPa); got P = {p_kpa!r} kPa. The printed API TDB 3A2.1 "
            "procedure is defined at 10 mmHg and no printed interconversion to "
            "other D1160 test pressures is verifiable."
        )
    tbp10 = d1160_tbp10_points(points)
    return [(p, d1160_aet_c(t - 273.15, p_kpa) + 273.15) for p, t in tbp10]


# ----------------------------------------------------- completion (Riazi distribution model)


@dataclass(frozen=True)
class CompletedCurve:
    """A full-range TBP curve: measured points plus fitted 0 % / 100 % endpoints (K)."""

    points: list[tuple[float, float]]  # sorted by percent, 0 % .. 100 %
    fit_alpha: float  # K, fitted location shift (model T at x = 0)
    fit_a: float  # K
    fit_b: float  # -, versatile-correlation shape
    fit_max_residual_k: float  # K, worst absolute residual on the measured points


def fit_distribution(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Fit ``T(x) = alpha + A * (-ln(1-x))**B`` (x = percent/100) by least squares.

    Returns (alpha, A, B, max residual in K) on the measured interior points.
    Positivity of A and B is enforced by fitting their logarithms; alpha is
    bounded to [0, 0.98 * min(measured T)] so the fitted IBP stays physical.
    """
    xs = np.array([p / 100.0 for p, _ in points if 0.0 < p < 99.9])
    ts = np.array([t for p, t in points if 0.0 < p < 99.9])
    if len(xs) < 3:
        raise ValueError("distribution fit needs at least 3 interior points")

    def residual(params: np.ndarray) -> np.ndarray:
        alpha, ln_a, ln_b = params
        return np.asarray(ts - (alpha + np.exp(ln_a) * (-np.log1p(-xs)) ** np.exp(ln_b)))

    t_min = float(ts.min())
    best: tuple[np.ndarray, float] | None = None
    for alpha0 in (0.0, 0.5 * t_min, 0.9 * t_min):
        for b0 in (0.5, 1.0, 2.0):
            try:
                result = least_squares(
                    residual,
                    x0=np.array([alpha0, math.log(max(t_min - alpha0, 1.0)), math.log(b0)]),
                    bounds=(
                        np.array([0.0, math.log(1e-3), math.log(1e-2)]),
                        np.array([0.98 * t_min, math.log(1e6), math.log(1e2)]),
                    ),
                    max_nfev=20000,
                )
            except (ValueError, FloatingPointError):  # degenerate start, try the next
                continue
            cost = float(np.dot(result.fun, result.fun))
            if best is None or cost < best[1]:
                best = (result.x, cost)
    if best is None:
        raise ValueError("distribution fit failed to converge for this curve")
    alpha, ln_a, ln_b = (float(v) for v in best[0])
    a, b = math.exp(ln_a), math.exp(ln_b)
    max_residual = max(abs(t - (alpha + a * (-math.log1p(-x)) ** b)) for x, t in zip(xs, ts, strict=False))
    return alpha, a, b, max_residual


def complete_curve(points: list[tuple[float, float]]) -> CompletedCurve:
    """Complete a TBP curve (percent, K) to 0 % and 100 % (Riazi distribution model).

    The fitted model supplies the 0.05 vol% and 99.95 vol% quantiles as the
    0 % / 100 % endpoints (the unbounded model has no finite x = 1 limit);
    interpolation on the completed curve is piecewise linear. Requires the
    measured curve to include at least the 10 % point for the 0 % completion
    and the 90 % point for the 100 % completion.
    """
    percents = [p for p, _ in points]
    if min(percents) > 10.0 or max(percents) < 90.0:
        raise ValueError("endpoint completion needs measured points at or beyond 10 % and 90 %")
    alpha, a, b, max_residual = fit_distribution(points)

    def model(x: float) -> float:
        return float(alpha + a * (-math.log1p(-x)) ** b)

    t_low = model(0.0005)
    t_high = model(0.9995)
    inner = sorted(points)
    completed = [(0.0, min(t_low, inner[0][1])), *inner, (100.0, max(t_high, inner[-1][1]))]
    return CompletedCurve(
        points=completed, fit_alpha=alpha, fit_a=a, fit_b=b, fit_max_residual_k=max_residual
    )


def to_tbp(curve: CurveLike) -> CompletedCurve:
    """Any supported curve kind -> completed full-range TBP curve (percent, K).

    D86, D1160 and D2887 convert through the correlations above; TBP passes
    through. Completion to 0 % / 100 % runs on the converted TBP points.
    """
    if curve.kind == "TBP":
        tbp_points = sorted(curve.points)
    elif curve.kind == "D86":
        tbp_points = d86_to_tbp_points(curve.points)
    elif curve.kind == "D1160":
        if curve.P_kPa is None:
            raise ValueError("D1160 curve needs P_kPa")
        tbp_points = d1160_to_tbp_points(curve.points, curve.P_kPa)
    elif curve.kind == "D2887":
        tbp_points = d2887_to_tbp_points(curve.points)
    else:
        raise ValueError(f"unsupported curve kind {curve.kind!r}")
    return complete_curve(tbp_points)


# --------------------------------------------- average boiling points and gravity


def vabp_k(completed: CompletedCurve) -> float:
    """Volume average boiling point: mean of TBP at 10/30/50/70/90 vol% (K)."""
    percents = [p for p, _ in completed.points]
    if min(percents) > 10.0 or max(percents) < 90.0:
        raise ValueError("VABP needs measured or completed points at 10 % and 90 %")
    return sum(_interp(completed.points, p) for p in (10.0, 30.0, 50.0, 70.0, 90.0)) / 5.0


def watson_k_from_meabp(bulk_sg: float, meabp_k: float) -> float:
    """Watson characterization factor ``K_w = (1.8 * MeABP_K)^(1/3) / sg``."""
    return float((1.8 * meabp_k) ** (1.0 / 3.0) / bulk_sg)


def effective_watson_k(
    curve: CurveLike,
    bulk_sg: float,
    *,
    watson_k_override: float | None = None,
    meabp_k_override: float | None = None,
) -> float:
    """Watson K for the gravity distribution.

    Precedence: explicit ``watson_k_override``, explicit ``meabp_k_override``,
    then bulk sg and VABP as the MeABP estimate (the printed MeABP - VABP
    correction has no verifiable public transcription - see the module
    docstring).
    """
    if watson_k_override is not None:
        return watson_k_override
    meabp = meabp_k_override
    if meabp is None:
        meabp = vabp_k(to_tbp(curve))
    return watson_k_from_meabp(bulk_sg, meabp)


def sg_distribution(temps_k: list[float], k_w: float) -> list[float]:
    """Specific gravities at ``temps_k`` from the constant-Watson-K model.

    ``sg(Tb) = (1.8 * Tb)^(1/3) / K_w`` - the K_w definition rearranged, so the
    Watson-K identity holds exactly per cut.
    """
    return [(1.8 * t) ** (1.0 / 3.0) / k_w for t in temps_k]


# --------------------------------------------------------------------------- cutting


@dataclass(frozen=True)
class CutScheme:
    """How the TBP curve is sliced.

    Default (``CutScheme.default()``): 15 K intervals up to 700 K, 25 K up to
    811 K, 50 K above - the refinery-modelling convention attributed to Kaes,
    G.L., *Refinery Process Modeling* (2000); no open scan of the printed page
    is available, so the scheme is spec-stated with that attribution. Cut edges
    are temperature-space; each cut's percent width on the converted curve is
    its fraction on the curve's own basis.
    """

    widths: tuple[tuple[float, float], ...] = ((15.0, 700.0), (25.0, 811.0), (50.0, math.inf))
    by_count: int | None = None  # equal-percent slices instead of intervals

    @classmethod
    def default(cls) -> CutScheme:
        return cls()

    @classmethod
    def equal_count(cls, n: int) -> CutScheme:
        if n < 2:
            raise ValueError("need at least 2 cuts")
        return cls(by_count=n)


@dataclass(frozen=True)
class CutSlate:
    """One assay cut into discrete components (pseudo- and light ends).

    ``mole`` / ``mass`` / ``volume`` each sum to 1 (within 1e-12) and carry the
    same ids: pseudo-component ids from ``pseudos`` plus the light-end ids.
    """

    pseudos: tuple[PseudoDefinition, ...]
    light_end_ids: tuple[str, ...]
    mole: dict[str, float]
    mass: dict[str, float]
    volume: dict[str, float]


def _cut_edges(t_start: float, t_end: float, scheme: CutScheme) -> list[float]:
    """Temperature-space cut edges from ``t_start`` to ``t_end`` (K)."""
    if scheme.by_count is not None:
        return [float(v) for v in np.linspace(t_start, t_end, scheme.by_count + 1)]
    edges = [t_start]
    t = t_start
    for step, limit in scheme.widths:
        while t < min(limit, t_end) - 1e-9:
            t = min(t + step, min(limit, t_end))
            edges.append(t)
        if t >= t_end - 1e-9:
            break
    if edges[-1] < t_end - 1e-9:  # t_end below the first interval limit
        edges.append(t_end)
    return edges


def _percent_of(points: list[tuple[float, float]], temperature: float) -> float:
    """Inverse of a completed curve: percent at a temperature (piecewise linear)."""
    if temperature <= points[0][1]:
        return points[0][0]
    if temperature >= points[-1][1]:
        return points[-1][0]
    for (p1, t1), (p2, t2) in zip(points, points[1:], strict=False):
        if t1 <= temperature <= t2:
            return p1 + (p2 - p1) * (temperature - t1) / (t2 - t1)
    raise AssertionError("unreachable")


def _sg_at(sg_by_temp: list[tuple[float, float]], temperature: float) -> float:
    """Specific gravity at ``temperature`` (K) from (T, sg) pairs, piecewise linear."""
    temps = [t for t, _ in sg_by_temp]
    sgs = [s for _, s in sg_by_temp]
    if temperature <= temps[0]:
        return sgs[0]
    if temperature >= temps[-1]:
        return sgs[-1]
    for t1, t2, s1, s2 in zip(temps, temps[1:], sgs, sgs[1:], strict=False):
        if t1 <= temperature <= t2:
            return s1 + (s2 - s1) * (temperature - t1) / (t2 - t1)
    raise AssertionError("unreachable")


def cut_slate(
    curve: CurveLike,
    bulk_sg: float,
    *,
    light_ends: dict[str, float] | None = None,
    light_ends_basis: str | None = None,
    sg_curve: list[tuple[float, float]] | None = None,
    watson_k_override: float | None = None,
    meabp_k_override: float | None = None,
    assay_id: str = "assay",
    scheme: CutScheme | None = None,
) -> CutSlate:
    """Cut a distillation curve into a flash-ready slate of discrete components.

    Light ends (when given, fractions on ``light_ends_basis``) occupy the front
    of the curve as databank components; pseudo-components tile the rest, one
    :class:`PseudoDefinition` per cut with Tb at the cut's mid-percent TBP and
    sg from the gravity distribution (constant Watson K, or the supplied
    ``sg_curve`` of (percent, sg)). Fractions convert across mole/mass/volume
    through specific gravities and molecular weights (volume-additive mixing).
    An LV% curve pairs with volume-basis light ends; a wt% curve with mass
    basis - other combinations are the caller's conversion, not this module's.
    """
    scheme = scheme or CutScheme.default()
    le = dict(light_ends or {})
    if le and light_ends_basis is None:
        raise ValueError("light_ends need light_ends_basis")
    if light_ends_basis not in (None, "mole", "mass", "volume"):
        raise ValueError(f"unsupported light_ends_basis {light_ends_basis!r}")
    le_percent = sum(le.values()) * 100.0
    if curve.basis == "LV%" and le and light_ends_basis != "volume":
        raise ValueError("light_ends_basis must be 'volume' for an LV% curve (convert externally)")
    if curve.basis == "wt%" and le and light_ends_basis != "mass":
        raise ValueError("light_ends_basis must be 'mass' for a wt% curve (convert externally)")

    completed = to_tbp(curve)
    k_w = effective_watson_k(
        curve, bulk_sg, watson_k_override=watson_k_override, meabp_k_override=meabp_k_override
    )

    edges = _cut_edges(_interp(completed.points, le_percent), completed.points[-1][1], scheme)
    pseudo_percent: list[float] = []
    mid_t: list[float] = []
    for t1, t2 in zip(edges, edges[1:], strict=False):
        p1 = _percent_of(completed.points, t1)
        p2 = _percent_of(completed.points, t2)
        pseudo_percent.append(p2 - p1)
        mid_t.append(_interp(completed.points, (p1 + p2) / 2.0))
    if not pseudo_percent:
        raise ValueError("cut scheme produced no pseudo-component cuts")
    if le and _percent_of(completed.points, edges[0]) < le_percent - 0.5:
        raise ValueError(f"light ends ({le_percent:.2f} %) reach past the first cut edge")

    if sg_curve is not None:
        sg_by_temp = [(p, sg) for p, sg in sg_curve]
    else:
        sg_by_temp = list(zip(mid_t, sg_distribution(mid_t, k_w), strict=False))
    pseudo_sg = [_sg_at(sg_by_temp, t) for t in mid_t]
    if sg_curve is None and watson_k_override is None:
        # The bulk sg IS the volume-average sg of the whole slate under
        # volume-additive mixing, so the distribution is anchored there, not at
        # the VABP point: anchoring at VABP leaves a systematic ~0.6 API
        # recombination offset (Jensen's inequality on the concave sg(T)). One
        # scale factor keeps the per-cut Watson K uniform while making the
        # recombination exact. An explicit sg_curve or K override is the
        # caller's distribution and is never rescaled.
        pseudo_sg = _anchor_sg_volume_average(pseudo_percent, pseudo_sg, curve.basis, le, bulk_sg)

    pseudos = tuple(
        PseudoDefinition(id=f"{assay_id}_NBP{t:.0f}", name=f"{assay_id} pseudo {t:.0f} K", Tb=t, sg=sg)
        for i, (t, sg) in enumerate(zip(mid_t, pseudo_sg, strict=False))
    )

    # Primary fractions on the curve's own basis; light ends are declared on it.
    primary = [w / 100.0 for w in pseudo_percent] + [le[c] for c in le]
    ids = [d.id for d in pseudos] + list(le)
    sgs: list[float] = []
    mws: list[float] = []
    for definition in pseudos:
        sgs.append(definition.sg)
        mws.append(_riazi_daubert_mw(definition.Tb, definition.sg))
    for cid in le:
        record = component_record(cid)
        if record["sg"] is None or record["mw"] is None:
            raise ValueError(f"light end {cid!r}: databank record lacks sg/mw for basis conversion")
        sgs.append(float(record["sg"]))
        mws.append(float(record["mw"]))

    volume, mass, mole = _all_bases(primary, curve.basis, sgs, mws)
    return CutSlate(
        pseudos=pseudos,
        light_end_ids=tuple(le),
        mole=dict(zip(ids, mole, strict=False)),
        mass=dict(zip(ids, mass, strict=False)),
        volume=dict(zip(ids, volume, strict=False)),
    )


def _anchor_sg_volume_average(
    pseudo_percent: list[float],
    pseudo_sg: list[float],
    basis: str,
    le: dict[str, float],
    bulk_sg: float,
) -> list[float]:
    """Scale constant-K pseudo sgs so the slate recombines to ``bulk_sg``.

    LV%: sum(v_i * sg_i) = bulk_sg over pseudo widths and light-end volume
    fractions. wt%: sum(m_i / sg_i) = 1 / bulk_sg over pseudo and light-end
    mass fractions (volume fractions are proportional to m/sg). Raises when
    the light ends or the distribution cannot reach the bulk gravity.
    """
    le_term = 0.0
    for cid, frac in le.items():
        record = component_record(cid)
        if record["sg"] is None:
            raise ValueError(f"light end {cid!r}: databank record lacks sg for gravity anchoring")
        le_term += frac * float(record["sg"]) if basis == "LV%" else frac / float(record["sg"])
    if basis == "LV%":
        pseudo_term = sum(w / 100.0 * sg for w, sg in zip(pseudo_percent, pseudo_sg, strict=False))
        target = bulk_sg - le_term
    elif basis == "wt%":
        pseudo_term = sum((w / 100.0) / sg for w, sg in zip(pseudo_percent, pseudo_sg, strict=False))
        target = 1.0 / bulk_sg - le_term
    else:
        raise ValueError(f"unsupported curve basis {basis!r} for gravity anchoring")
    if pseudo_term <= 0.0 or target <= 0.0:
        raise ValueError("bulk sg unreachable: light ends leave no room for the pseudo cuts")
    scale = target / pseudo_term if basis == "LV%" else pseudo_term / target
    return [sg * scale for sg in pseudo_sg]


def _all_bases(
    primary: list[float], basis: str, sgs: list[float], mws: list[float]
) -> tuple[list[float], list[float], list[float]]:
    """Primary-basis fractions -> (volume, mass, mole), each normalized to 1.

    volume <-> mass through sg; mass <-> mole through MW (volume-additive
    mixing, the standard refinery recombination convention).
    """
    mass: list[float]
    volume: list[float]
    if basis == "LV%":
        volume = list(primary)
        mass = [v * sg for v, sg in zip(volume, sgs, strict=False)]
    elif basis == "wt%":
        mass = list(primary)
        volume = [m / sg for m, sg in zip(mass, sgs, strict=False)]
    else:
        raise ValueError(f"unsupported curve basis {basis!r}")
    mole = [m / mw for m, mw in zip(mass, mws, strict=False)]
    return _normalized(volume), _normalized(mass), _normalized(mole)


def _normalized(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0.0:
        raise ValueError("cut fractions sum to zero")
    return [v / total for v in values]


def cut(assay: Any, scheme: CutScheme | None = None) -> CutSlate:
    """Cut one ``ngdesign.contracts.assay.Assay`` into a slate.

    The assay model is accepted structurally (this module is below the
    contracts layer and never imports it): anything exposing ``curve``,
    ``bulk_sg``, ``light_ends``, ``light_ends_basis``, ``sg_curve``,
    ``watson_k``, ``meabp_k`` and ``id`` works. Light ends declared on a mole
    basis are converted to the curve's own basis here (through databank MW and
    sg); volume/mass declarations pass through to :func:`cut_slate`'s pairing
    rules.
    """
    curve: CurveLike = assay.curve
    le = dict(assay.light_ends)
    basis = assay.light_ends_basis
    if le and basis == "mole":
        le = _mole_to(curve.basis, le)
        basis = "volume" if curve.basis == "LV%" else "mass"
    return cut_slate(
        curve,
        assay.bulk_sg,
        light_ends=le,
        light_ends_basis=basis,
        sg_curve=assay.sg_curve,
        watson_k_override=assay.watson_k,
        meabp_k_override=assay.meabp_k,
        assay_id=assay.id,
        scheme=scheme,
    )


def _mole_to(basis: str, le: dict[str, float]) -> dict[str, float]:
    """Mole fractions of databank light ends -> mass (wt%) or volume (LV%) fractions."""
    mass: list[float] = []
    volume: list[float] = []
    for cid, x in le.items():
        record = component_record(cid)
        if record["mw"] is None:
            raise ValueError(f"light end {cid!r}: databank record lacks MW")
        m = x * float(record["mw"])
        mass.append(m)
        if record["sg"] is None:
            raise ValueError(f"light end {cid!r}: databank record lacks sg")
        volume.append(m / float(record["sg"]))
    if basis == "wt%":
        return dict(zip(le, _normalized(mass), strict=False))
    if basis == "LV%":
        return dict(zip(le, _normalized(volume), strict=False))
    raise ValueError(f"unsupported curve basis {basis!r}")
