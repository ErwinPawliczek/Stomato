"""Evaluate the cited vapour-pressure fits of a species.

Forms: Wagner 2.5-5 and 1.5-3-6 via ``chemicals.vapor_pressure``; Antoine
log10(P/bar) = A − B/(T + C). Fits are tried most trusted first, and a temperature
outside every window gives no answer rather than an extrapolation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from chemicals.vapor_pressure import Wagner, Wagner_original
from scipy.optimize import brentq

from ngdesign.data import chemdb


@dataclass(frozen=True)
class Fit:
    """One vapour-pressure correlation of a species."""

    form: str
    source: str
    window: tuple[float, float]  # K
    row: Mapping[str, float]

    def pressure(self, T: float) -> float:
        """Psat(T), Pa."""
        row = self.row
        if self.form == "wagner 2.5-5":
            return float(Wagner(T, row["Tc"], row["Pc"], row["A"], row["B"], row["C"], row["D"]))
        if self.form == "wagner 1.5-3-6":
            return float(Wagner_original(T, row["Tc"], row["Pc"], row["A"], row["B"], row["C"], row["D"]))
        return float(1e5 * 10.0 ** (row["A"] - row["B"] / (T + row["C"])))


def fits(query: str) -> list[Fit]:
    """Vapour-pressure fits of a species, most trusted first."""
    species = chemdb.find(query)
    found: list[Fit] = []
    for row in sorted(chemdb.wagner(species.cas), key=lambda r: r["form"] != "2.5-5"):
        found.append(Fit(f"wagner {row['form']}", row["source"], (row["Tmin"], row["Tmax"]), row))
    for row in sorted(chemdb.antoine(species.cas), key=lambda r: r["source"] != "poling"):
        if row["Tmin"] is not None and row["Tmax"] is not None:
            found.append(Fit("antoine", row["source"], (row["Tmin"], row["Tmax"]), row))
    return found


def fit_at(query: str, T: float) -> Fit | None:
    """The most trusted fit whose window holds T."""
    return next((fit for fit in fits(query) if fit.window[0] <= T <= fit.window[1]), None)


def temperature_at(fit: Fit, P: float) -> float | None:
    """The T where ``fit`` gives P, or None when P is outside its window."""
    low, high = fit.window
    if not fit.pressure(low) <= P <= fit.pressure(high):
        return None
    return float(brentq(lambda T: fit.pressure(T) - P, low, high, xtol=1e-9))
