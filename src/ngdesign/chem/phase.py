"""Phase behaviour: pure-species saturation, the phase rule, VLE and SLE.

Pure species read their vapour-pressure fits and fixed points from the cited
database. Mixtures come in two strengths: **ideal** Raoult's-law calculations that
work for every species with a fit, and **rigorous** diagrams that take any
registered :class:`~ngdesign.contracts.plugins.Thermo` package, so the activity and
EOS models of ``ngdesign.thermo`` supply the physics and this module the sweep.

Vapour-pressure forms: Wagner 2.5-5 and 1.5-3-6 via ``chemicals.vapor_pressure``;
Antoine log10(P/bar) = A − B/(T + C). A temperature outside every fit is refused.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from chemicals.rachford_rice import flash_inner_loop
from chemicals.vapor_pressure import Wagner, Wagner_original
from scipy.optimize import brentq, minimize_scalar

from ngdesign.chem.thermochem import R
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import SaturationError
from ngdesign.data import chemdb
from ngdesign.data.chemdb import MissingPropertyError
from ngdesign.uom.quantity import si_arguments

#: How far y may sit from x at a bubble-curve extremum and still be an azeotrope.
_AZEOTROPE_Y_TOLERANCE = 0.01


class PhaseError(ValueError):
    """A phase calculation is ill-posed or outside its data."""


@dataclass(frozen=True)
class VapourPressure:
    """A saturation pressure with the fit that produced it."""

    P: float  # Pa
    form: str
    source: str
    window: tuple[float, float]  # K


def _fits(query: str) -> list[tuple[str, str, tuple[float, float], dict[str, float]]]:
    """Vapour-pressure fits of a species, most trusted first."""
    species = chemdb.find(query)
    fits: list[tuple[str, str, tuple[float, float], dict[str, float]]] = []
    for row in sorted(chemdb.wagner(species.cas), key=lambda r: r["form"] != "2.5-5"):
        fits.append((f"wagner {row['form']}", row["source"], (row["Tmin"], row["Tmax"]), row))
    for row in sorted(chemdb.antoine(species.cas), key=lambda r: r["source"] != "poling"):
        if row["Tmin"] is not None and row["Tmax"] is not None:
            fits.append(("antoine", row["source"], (row["Tmin"], row["Tmax"]), row))
    return fits


def _evaluate(form: str, row: Mapping[str, float], T: float) -> float:
    if form == "wagner 2.5-5":
        return float(Wagner(T, row["Tc"], row["Pc"], row["A"], row["B"], row["C"], row["D"]))
    if form == "wagner 1.5-3-6":
        return float(Wagner_original(T, row["Tc"], row["Pc"], row["A"], row["B"], row["C"], row["D"]))
    return float(1e5 * 10.0 ** (row["A"] - row["B"] / (T + row["C"])))


@si_arguments(T="temperature")
def psat(query: str, T: float) -> VapourPressure:
    """Saturation pressure at T from the most trusted fit whose window holds T."""
    fits = _fits(query)
    if not fits:
        raise MissingPropertyError(f"no vapour-pressure fit for {query!r}")
    for form, source, window, row in fits:
        if window[0] <= T <= window[1]:
            return VapourPressure(_evaluate(form, row, T), form, source, window)
    low = min(f[2][0] for f in fits)
    high = max(f[2][1] for f in fits)
    raise PhaseError(f"{query}: no vapour-pressure fit holds {T} K (data span {low}-{high} K)")


def _saturation_residual(T: float, form: str, row: Mapping[str, float], P: float) -> float:
    return _evaluate(form, row, T) - P


@si_arguments(P="pressure")
def tsat(query: str, P: float) -> float:
    """Saturation temperature at P, K, inverted on the fits."""
    fits = _fits(query)
    if not fits:
        raise MissingPropertyError(f"no vapour-pressure fit for {query!r}")
    for form, _source, window, row in fits:
        low = _evaluate(form, row, window[0])
        high = _evaluate(form, row, window[1])
        if low <= P <= high:
            return float(brentq(_saturation_residual, *window, args=(form, row, P), xtol=1e-9))
    raise PhaseError(f"{query}: no vapour-pressure fit reaches {P} Pa")


@si_arguments(T="temperature")
def hvap_clausius_clapeyron(query: str, T: float) -> float:
    """ΔHvap ≈ −R·d ln Psat/d(1/T), J/mol: ideal vapour, negligible liquid volume.

    Good well below Tc; the error grows toward the critical point, where the assumed
    ΔZ = 1 fails.
    """
    fit = psat(query, T)
    low, high = fit.window
    h = min(0.5, (T - low) / 2 or 0.5, (high - T) / 2 or 0.5)
    up = psat(query, T + h).P
    down = psat(query, T - h).P
    slope = (math.log(up) - math.log(down)) / (1.0 / (T + h) - 1.0 / (T - h))
    return float(-R * slope)


def degrees_of_freedom(components: int, phases: int, reactions: int = 0, constraints: int = 0) -> int:
    """Gibbs phase rule with reactions: F = (C − r − s) − π + 2 (Denbigh; Smith & Missen)."""
    if components < 1 or phases < 1:
        raise PhaseError("need at least one component and one phase")
    freedom = components - reactions - constraints - phases + 2
    if freedom < 0:
        raise PhaseError(
            f"F = {freedom}: {phases} phases cannot coexist with {components} components, "
            f"{reactions} reactions and {constraints} constraints"
        )
    return freedom


@dataclass(frozen=True)
class FixedPoints:
    """Fixed points of a pure species from the database (SI; None when unstated)."""

    name: str
    Tm: float | None
    Tb: float | None
    Tt: float | None
    Pt: float | None
    Tc: float | None
    Pc: float | None
    Vc: float | None


def fixed_points(query: str) -> FixedPoints:
    species = chemdb.find(query)
    props = {prop: chemdb.maybe(species.cas, prop) for prop in ("Tm", "Tb", "Tt", "Pt", "Tc", "Pc", "Vc")}
    return FixedPoints(species.name, **props)


@si_arguments(T="temperature", P="pressure")
def pure_phase(query: str, T: float, P: float) -> str:
    """The phase of a pure species at (T, P): supercritical, gas, liquid or solid.

    Uses the critical point, the saturation curve between triple and critical point,
    and the melting point below it. Pressure dependence of melting is neglected.
    """
    points = fixed_points(query)
    if points.Tc is not None and T >= points.Tc:
        return "supercritical" if points.Pc is not None and P >= points.Pc else "gas"
    if points.Tm is not None and T < points.Tm:
        return "solid"
    return "liquid" if P >= psat(query, T).P else "gas"


@dataclass(frozen=True)
class RaoultFlash:
    """Ideal two-phase split: vapour fraction and phase compositions by species."""

    vapour_fraction: float
    x: dict[str, float]
    y: dict[str, float]
    K: dict[str, float]


def _normalised(z: Mapping[str, float]) -> tuple[list[str], np.ndarray]:
    keys = list(z)
    values = np.array([float(z[k]) for k in keys])
    if (values < 0.0).any() or values.sum() <= 0.0:
        raise PhaseError("composition must be non-negative with a positive sum")
    return keys, values / values.sum()


@si_arguments(T="temperature")
def raoult_bubble_pressure(z: Mapping[str, float], T: float) -> float:
    """P_bubble = Σ x_i Psat_i(T), Pa."""
    keys, x = _normalised(z)
    return float(sum(xi * psat(k, T).P for k, xi in zip(keys, x, strict=True)))


@si_arguments(T="temperature")
def raoult_dew_pressure(z: Mapping[str, float], T: float) -> float:
    """P_dew = 1 / Σ (y_i / Psat_i(T)), Pa."""
    keys, y = _normalised(z)
    return float(1.0 / sum(yi / psat(k, T).P for k, yi in zip(keys, y, strict=True)))


@si_arguments(P="pressure")
def raoult_bubble_temperature(z: Mapping[str, float], P: float) -> float:
    """Bubble T at P under Raoult's law, K, bracketed by the pure saturation temperatures."""
    keys, _ = _normalised(z)
    sats = [tsat(k, P) for k in keys]
    return float(brentq(lambda T: raoult_bubble_pressure(z, T) - P, min(sats), max(sats), xtol=1e-8))


@si_arguments(T="temperature", P="pressure")
def raoult_flash(z: Mapping[str, float], T: float, P: float) -> RaoultFlash:
    """Isothermal ideal flash at (T, P), by Rachford-Rice (``chemicals``).

    Outside the two-phase region the mixture is single phase: at or above the bubble
    pressure the vapour fraction is 0 and ``y`` is the incipient vapour; at or below the
    dew pressure it is 1 and ``x`` the incipient liquid.
    """
    keys, zs = _normalised(z)
    ks = [psat(k, T).P / P for k in keys]
    bubble = float(sum(zi * ki for zi, ki in zip(zs, ks, strict=True)))  # P_bubble / P
    dew = float(sum(zi / ki for zi, ki in zip(zs, ks, strict=True)))  # P / P_dew
    if bubble <= 1.0:
        vf, xs, ys = 0.0, list(zs), [zi * ki / bubble for zi, ki in zip(zs, ks, strict=True)]
    elif dew <= 1.0:
        vf, xs, ys = 1.0, [zi / ki / dew for zi, ki in zip(zs, ks, strict=True)], list(zs)
    else:
        vf, xs, ys = flash_inner_loop(list(zs), ks)
    return RaoultFlash(
        float(vf),
        dict(zip(keys, map(float, xs), strict=True)),
        dict(zip(keys, map(float, ys), strict=True)),
        dict(zip(keys, map(float, ks), strict=True)),
    )


@dataclass(frozen=True)
class BinaryDiagram:
    """A binary VLE sweep: light-key liquid x, vapour y, and the swept variable."""

    a: str
    b: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    values: tuple[float, ...]  # T in K for Txy, P in Pa for Pxy
    kind: str  # "Txy" or "Pxy"


def _bubble(
    thermo: Thermo, a: str, b: str, xa: float, *, T: float | None, P: float | None
) -> tuple[float, float, float]:
    point = thermo.bubble_point({a: xa, b: 1.0 - xa}, T=T, P=P)
    return point.T, point.P, float(point.incipient_composition.get(a, 0.0))


def _grid(points: int) -> np.ndarray:
    if points < 3:
        raise PhaseError("a diagram needs at least three points")
    return np.linspace(0.0, 1.0, points + 2)[1:-1]


@si_arguments(P="pressure")
def txy(thermo: Thermo, a: str, b: str, P: float, points: int = 21) -> BinaryDiagram:
    """Bubble line at fixed P: T(x) and y(x), with x_a on a uniform interior grid."""
    xs, ys, ts = [], [], []
    for xa in _grid(points):
        T, _, ya = _bubble(thermo, a, b, float(xa), T=None, P=P)
        xs.append(float(xa))
        ys.append(ya)
        ts.append(T)
    return BinaryDiagram(a, b, tuple(xs), tuple(ys), tuple(ts), "Txy")


@si_arguments(T="temperature")
def pxy(thermo: Thermo, a: str, b: str, T: float, points: int = 21) -> BinaryDiagram:
    """Bubble line at fixed T: P(x) and y(x)."""
    xs, ys, ps = [], [], []
    for xa in _grid(points):
        _, P, ya = _bubble(thermo, a, b, float(xa), T=T, P=None)
        xs.append(float(xa))
        ys.append(ya)
        ps.append(P)
    return BinaryDiagram(a, b, tuple(xs), tuple(ys), tuple(ps), "Pxy")


@dataclass(frozen=True)
class Azeotrope:
    """A binary azeotrope at fixed pressure."""

    x: float  # mole fraction of the first species
    T: float  # K
    P: float  # Pa


@si_arguments(P="pressure")
def find_azeotrope(thermo: Thermo, a: str, b: str, P: float, points: int = 41) -> Azeotrope | None:
    """The azeotrope at P, or None: an interior extremum of the bubble curve T(x).

    By the Gibbs-Konowalov theorem dT/dx = 0 at fixed P exactly where y = x, so the
    search reads T alone. That matters because saturation solvers can report y = x
    across a finite plateau around an azeotrope (where the phases are nearly
    identical), which defeats a sign-change search on y − x. The found point is then
    required to satisfy y ≈ x, so a package artefact in T(x) is not reported.
    """
    grid = _grid(points)
    temperatures = np.array([_bubble(thermo, a, b, float(x), T=None, P=P)[0] for x in grid])
    interior = range(1, len(grid) - 1)
    minima = [
        i
        for i in interior
        if temperatures[i] < temperatures[i - 1] and temperatures[i] <= temperatures[i + 1]
    ]
    maxima = [
        i
        for i in interior
        if temperatures[i] > temperatures[i - 1] and temperatures[i] >= temperatures[i + 1]
    ]
    if not minima and not maxima:
        return None
    index, sign = (minima[0], 1.0) if minima else (maxima[0], -1.0)
    solved = minimize_scalar(
        lambda x: sign * _bubble(thermo, a, b, float(x), T=None, P=P)[0],
        bounds=(float(grid[index - 1]), float(grid[index + 1])),
        method="bounded",
        options={"xatol": 1e-5},
    )
    x = float(solved.x)
    T, _, y = _bubble(thermo, a, b, x, T=None, P=P)
    if abs(y - x) > _AZEOTROPE_Y_TOLERANCE:
        return None
    return Azeotrope(x, T, P)


@dataclass(frozen=True)
class PhaseEnvelope:
    """Bubble and dew curves of a fixed mixture in (T, P)."""

    T_bubble: tuple[float, ...]
    P_bubble: tuple[float, ...]
    T_dew: tuple[float, ...]
    P_dew: tuple[float, ...]

    @property
    def cricondenbar(self) -> float:
        """Highest two-phase pressure found on the sweep, Pa."""
        return max(self.P_bubble + self.P_dew)

    @property
    def cricondentherm(self) -> float:
        """Highest two-phase temperature found on the sweep, K."""
        return max(self.T_bubble + self.T_dew)


def phase_envelope(
    thermo: Thermo, z: Mapping[str, float], T_low: float, T_high: float, points: int = 40
) -> PhaseEnvelope:
    """Sweep bubble and dew pressures over T; points past the critical region drop out.

    A coarse scan, not a continuation method: it stops short of the true critical
    point, where the saturation solver declares no two-phase region, and it follows
    only the upper dew branch the saturation solver lands on.
    """
    composition = dict(z)
    bubble: list[tuple[float, float]] = []
    dew: list[tuple[float, float]] = []
    for T in np.linspace(T_low, T_high, points):
        for collector, solve in ((bubble, thermo.bubble_point), (dew, thermo.dew_point)):
            try:
                point = solve(composition, T=float(T))
            except SaturationError:
                continue
            collector.append((point.T, point.P))
    if not bubble and not dew:
        raise PhaseError("no two-phase region on the swept temperatures")
    return PhaseEnvelope(
        tuple(t for t, _ in bubble),
        tuple(p for _, p in bubble),
        tuple(t for t, _ in dew),
        tuple(p for _, p in dew),
    )


def _fusion(query: str) -> tuple[float, float]:
    species = chemdb.find(query)
    Tm = chemdb.maybe(species.cas, "Tm")
    Hfus = chemdb.maybe(species.cas, "Hfus")
    if Tm is None or Hfus is None:
        raise MissingPropertyError(f"{species.name}: Tm and ΔHfus are both needed for SLE")
    return Tm, Hfus


@si_arguments(T="temperature")
def ideal_solubility(query: str, T: float) -> float:
    """Schröder-van Laar ideal solubility: ln x = −(ΔHfus/R)·(1/T − 1/Tm), capped at 1."""
    Tm, Hfus = _fusion(query)
    return min(1.0, math.exp(-Hfus / R * (1.0 / T - 1.0 / Tm)))


@dataclass(frozen=True)
class Eutectic:
    """Ideal-solution simple eutectic of a binary."""

    x_a: float
    T: float


def eutectic(a: str, b: str) -> Eutectic:
    """Where the two ideal liquidus curves cross: x_a(T) + x_b(T) = 1."""
    Tm_a, _ = _fusion(a)
    Tm_b, _ = _fusion(b)

    def excess(T: float) -> float:
        return ideal_solubility(a, T) + ideal_solubility(b, T) - 1.0

    high = min(Tm_a, Tm_b)
    low = high
    for _ in range(200):
        low *= 0.97
        if excess(low) < 0.0:
            T = float(brentq(excess, low, high, xtol=1e-8))
            return Eutectic(ideal_solubility(a, T), T)
    raise PhaseError(f"no eutectic found below {high} K for {a}/{b}")


def relative_volatility(a: str, b: str, T: float) -> float:
    """Ideal α_ab = Psat_a/Psat_b at T."""
    return psat(a, T).P / psat(b, T).P


__all__ = [
    "Azeotrope",
    "BinaryDiagram",
    "Eutectic",
    "FixedPoints",
    "PhaseEnvelope",
    "PhaseError",
    "RaoultFlash",
    "VapourPressure",
    "degrees_of_freedom",
    "eutectic",
    "find_azeotrope",
    "fixed_points",
    "hvap_clausius_clapeyron",
    "ideal_solubility",
    "phase_envelope",
    "psat",
    "pure_phase",
    "pxy",
    "raoult_bubble_pressure",
    "raoult_bubble_temperature",
    "raoult_dew_pressure",
    "raoult_flash",
    "relative_volatility",
    "tsat",
    "txy",
]
