"""Standard-state species models over the cited database.

Every species gets a model on the element reference used by NIST-JANAF: H°(298.15 K)
= ΔfH°298, elements in their reference state at zero, S° absolute, standard pressure
1 bar, ideal gas or pure condensed phase.

Models, best first, chosen per species and phase:

1. **NIST-JANAF table**. H°(T) − H°(298) and S°(T) are cubic Hermite interpolants
   with Cp and Cp/T as nodal slopes, so they reproduce the table at every node and
   stay consistent with dH = Cp dT between nodes.
2. **NIST Shomate** pieces (Chase 1998 form): with t = T/1000,
   Cp = A + Bt + Ct² + Dt³ + E/t²;
   H − H298 = At + Bt²/2 + Ct³/3 + Dt⁴/4 − E/t + F − H (kJ/mol);
   S = A ln t + Bt + Ct²/2 + Dt³/3 − E/(2t²) + G.
3. **Gas Cp fits**: TRC eight-term or Poling polynomial (evaluated with their
   ``chemicals`` integrals) on the selected S°298.
4. **Liquid Cp fits**: Zabransky splines or DIPPR 100 polynomials, after a saturation
   model μ°(l) = μ°(g) + RT ln(Psat/P°) wherever a vapour-pressure fit reaches 298.15 K.
5. **Constant Cp** at the tabulated 298 K value, within a narrow range for a gas. The
   result names itself ``constant_cp`` so the coarser model stays visible.

A temperature outside a model's range is refused, never extrapolated.

This sits in the data layer so the flowsheet's reaction physics (below
``ngdesign.chem`` in the import contract) can read the same potentials.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
import scipy.constants as sc
from chemicals.dippr import EQ100
from chemicals.heat_capacity import (
    Poling,
    Poling_integral,
    Poling_integral_over_T,
    Shomate,
    Shomate_integral,
    Shomate_integral_over_T,
    TRCCp,
    TRCCp_integral,
    TRCCp_integral_over_T,
    Zabransky_cubic,
    Zabransky_cubic_integral,
    Zabransky_cubic_integral_over_T,
)

from ngdesign.data import chemdb, vapour_pressure
from ngdesign.data.chemdb import MissingPropertyError

T_REF = 298.15
_R = sc.R
_P_STANDARD = 1.0e5
PHASES = ("gas", "liquid", "solid")
AQUEOUS = "aqueous"  # 1 molal standard state, H+(aq) = 0; temperature range below
#: Window the aqueous fallback is used in: 298.15 K data, liquid water around it.
_AQUEOUS_RANGE = (273.15, 373.15)
REFERENCE = "reference"  # an element's reference state, whatever phase it is in at T


class ThermochemError(ValueError):
    """Base class of thermochemistry refusals."""


class TemperatureRangeError(ThermochemError):
    """A temperature lies outside the validity range of the species model."""


class _Curve:
    """H°(T) − H°298 and S°(T) evaluation of one model."""

    tmin: float
    tmax: float
    name: str

    def cp(self, T: float) -> float:
        raise NotImplementedError

    def dh(self, T: float) -> float:
        raise NotImplementedError

    def s(self, T: float) -> float:
        raise NotImplementedError


class _JanafCurve(_Curve):
    """Cubic Hermite through a JANAF table; transitions are jumps between nodes."""

    def __init__(self, rows: Sequence[Mapping[str, Any]], table: str) -> None:
        self.t = np.array([float(r["T"]) for r in rows])
        self.cp_nodes = np.array([float(r["Cp"]) for r in rows])
        self.h_nodes = np.array([float(r["H_H298"]) for r in rows])
        self.s_nodes = np.array([float(r["S"]) for r in rows])
        self.tmin = float(self.t[0])
        self.tmax = float(self.t[-1])
        self.name = f"janaf:{table}"

    def _interval(self, T: float) -> tuple[int, float, float]:
        i = int(np.searchsorted(self.t, T, side="right")) - 1
        i = max(0, min(i, len(self.t) - 2))
        width = float(self.t[i + 1] - self.t[i])
        if width == 0.0:  # a transition sits on this node: step into the next interval
            i += 1
            width = float(self.t[i + 1] - self.t[i])
        return i, width, (T - float(self.t[i])) / width

    def cp(self, T: float) -> float:
        i, _, u = self._interval(T)
        return float(self.cp_nodes[i] + u * (self.cp_nodes[i + 1] - self.cp_nodes[i]))

    @staticmethod
    def _hermite(y0: float, y1: float, m0: float, m1: float, h: float, u: float) -> float:
        h00 = 2 * u**3 - 3 * u**2 + 1
        h10 = u**3 - 2 * u**2 + u
        h01 = -2 * u**3 + 3 * u**2
        h11 = u**3 - u**2
        return h00 * y0 + h10 * h * m0 + h01 * y1 + h11 * h * m1

    def dh(self, T: float) -> float:
        i, h, u = self._interval(T)
        return self._hermite(
            float(self.h_nodes[i]),
            float(self.h_nodes[i + 1]),
            float(self.cp_nodes[i]),
            float(self.cp_nodes[i + 1]),
            h,
            u,
        )

    def s(self, T: float) -> float:
        i, h, u = self._interval(T)
        return self._hermite(
            float(self.s_nodes[i]),
            float(self.s_nodes[i + 1]),
            float(self.cp_nodes[i] / self.t[i]),
            float(self.cp_nodes[i + 1] / self.t[i + 1]),
            h,
            u,
        )


class _ShomateCurve(_Curve):
    """Piecewise NIST Shomate fit. Table windows open at 298, treated as 298.15."""

    def __init__(self, pieces: Sequence[Mapping[str, Any]]) -> None:
        self.pieces = sorted(pieces, key=lambda p: float(p["Tmin"]))
        self.tmin = float(self.pieces[0]["Tmin"])
        self.tmax = float(self.pieces[-1]["Tmax"])
        self.name = "shomate"

    def _piece(self, T: float) -> Mapping[str, Any]:
        for piece in self.pieces:
            if T <= float(piece["Tmax"]):
                return piece
        return self.pieces[-1]

    def cp(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        return float(c["A"] + c["B"] * t + c["C"] * t**2 + c["D"] * t**3 + c["E"] / t**2)

    def dh(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        kj = (
            c["A"] * t
            + c["B"] * t**2 / 2
            + c["C"] * t**3 / 3
            + c["D"] * t**4 / 4
            - c["E"] / t
            + c["F"]
            - c["H"]
        )
        return float(kj) * 1000.0

    def s(self, T: float) -> float:
        c = self._piece(T)
        t = T / 1000.0
        return float(
            c["A"] * math.log(t)
            + c["B"] * t
            + c["C"] * t**2 / 2
            + c["D"] * t**3 / 3
            - c["E"] / (2 * t**2)
            + c["G"]
        )


class _PolyCurve(_Curve):
    """Gas Cp fit in the TRC or Poling form, anchored on S°298."""

    def __init__(self, fit: Mapping[str, Any], s298: float) -> None:
        self.form = str(fit["form"])
        self.tmin = float(fit["Tmin"])
        self.tmax = float(fit["Tmax"])
        self.name = f"cp_fit:{self.form}"
        count = 8 if self.form == "trc" else 5
        self.a = tuple(float(fit[f"a{i}"]) for i in range(count))
        self.s298 = s298

    def cp(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp(T, *self.a))
        return float(Poling(T, *self.a))  # type: ignore[no-untyped-call]

    def _h(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp_integral(T, *self.a))
        return float(Poling_integral(T, *self.a))  # type: ignore[no-untyped-call]

    def _s(self, T: float) -> float:
        if self.form == "trc":
            return float(TRCCp_integral_over_T(T, *self.a))
        return float(Poling_integral_over_T(T, *self.a))  # type: ignore[no-untyped-call]

    def dh(self, T: float) -> float:
        return self._h(T) - self._h(T_REF)

    def s(self, T: float) -> float:
        return self.s298 + self._s(T) - self._s(T_REF)


class _SaturationCurve(_Curve):
    """Liquid from its vapour: μ°(l, T) = μ°(g, T) + R·T·ln(Psat(T)/P°).

    The ideal-vapour, negligible-Poynting limit of equal fugacities at saturation.
    It holds the liquid to the cited vapour-pressure fit, so VLE built on these
    potentials reproduces that fit where a constant Cp would drift (benzene at 365 K:
    116 kPa against 144 kPa). G comes from that identity on the absolute scale; H is
    the Gibbs-Helmholtz derivative, stated relative to 298.15 K, so the stated ΔfH°(l)
    still anchors heats of reaction at 298.15 K. The two scales disagree by
    the gap between the stated ΔfH°(l) and ΔfH°(g) − ΔHvap, which ``s`` absorbs.
    """

    name = "saturation"
    _STEP = 0.05

    def __init__(self, gas: SpeciesThermo, query: str, hf: float) -> None:
        self.gas = gas
        self.query = query
        self.hf = hf
        windows = [fit.window for fit in vapour_pressure.fits(query)]
        self.tmin = max(min(w[0] for w in windows), gas.t_range[0])
        self.tmax = min(max(w[1] for w in windows), gas.t_range[1])

    def _g(self, T: float) -> float:
        fit = vapour_pressure.fit_at(self.query, T)
        if fit is None:
            raise TemperatureRangeError(f"{self.query}: no vapour-pressure fit holds {T} K")
        return float(self.gas.g(T) + _R * T * math.log(fit.pressure(T) / _P_STANDARD))

    def _h(self, T: float) -> float:
        """H = G − T·dG/dT, with the slope taken inside the fit window."""
        low = max(T - self._STEP, self.tmin)
        high = min(T + self._STEP, self.tmax)
        return self._g(T) - T * (self._g(high) - self._g(low)) / (high - low)

    def dh(self, T: float) -> float:
        return self._h(T) - self._h(T_REF)

    def cp(self, T: float) -> float:
        low = max(T - 1.0, self.tmin)
        high = min(T + 1.0, self.tmax)
        return float((self._h(high) - self._h(low)) / (high - low))

    def s(self, T: float) -> float:
        return float((self.hf + self.dh(T) - self._g(T)) / T)


class _CpFitCurve(_Curve):
    """Tabulated Cp(T) anchored on S°298: Zabransky splines, DIPPR 100, or Shomate Cp pieces.

    H and S integrate Cp from 298.15 K across piece boundaries; for Shomate pieces
    without their F, G, H constants (the WebBook snapshot) this is how the curve is
    anchored at all.
    """

    def __init__(self, pieces: Sequence[Mapping[str, Any]], s298: float) -> None:
        self.pieces = sorted(pieces, key=lambda p: float(p["Tmin"]))
        self.tmin = float(self.pieces[0]["Tmin"])
        self.tmax = float(self.pieces[-1]["Tmax"])
        self.s298 = s298
        self.name = f"cp_fit:{self.pieces[0]['source']}"

    @staticmethod
    def _antiderivatives(piece: Mapping[str, Any], T: float) -> tuple[float, float, float]:
        """(Cp, ∫Cp dT, ∫Cp/T dT) of one piece, up to its constants."""
        if piece["form"] == "shomate_cp":
            # the snapshot stores the Shomate form in kelvin, Cp = A + BT + CT² + DT³ + E/T²
            A, B, C, D, E = (float(piece[k]) for k in "ABCDE")
            return (
                float(Shomate(T, A, B, C, D, E)),  # type: ignore[no-untyped-call]
                float(Shomate_integral(T, A, B, C, D, E)),  # type: ignore[no-untyped-call]
                float(Shomate_integral_over_T(T, A, B, C, D, E)),  # type: ignore[no-untyped-call]
            )
        if piece["form"] == "dippr100":
            A, B, C, D, E = (float(piece[f"a{i}"]) / 1000.0 for i in range(5))  # per kmol to per mol
            return (
                float(EQ100(T, A, B, C, D, E)),
                float(EQ100(T, A, B, C, D, E, order=-1)),
                float(EQ100(T, A, B, C, D, E, order=-1j)),
            )
        a = [float(piece[f"a{i}"]) for i in range(4)]
        return (
            float(Zabransky_cubic(T, *a)),
            float(Zabransky_cubic_integral(T, *a)),
            float(Zabransky_cubic_integral_over_T(T, *a)),
        )

    def _piece(self, T: float) -> Mapping[str, Any]:
        for piece in self.pieces:
            if T <= float(piece["Tmax"]):
                return piece
        return self.pieces[-1]

    def _integrate(self, T: float, column: int) -> float:
        """∫ from 298.15 K to T, across piece boundaries."""
        sign, low, high = (1.0, T_REF, T) if T >= T_REF else (-1.0, T, T_REF)
        total = 0.0
        for piece in self.pieces:
            left = max(low, float(piece["Tmin"]))
            right = min(high, float(piece["Tmax"]))
            if right > left:
                total += (
                    self._antiderivatives(piece, right)[column] - self._antiderivatives(piece, left)[column]
                )
        return sign * total

    def cp(self, T: float) -> float:
        return self._antiderivatives(self._piece(T), T)[0]

    def dh(self, T: float) -> float:
        return self._integrate(T, 1)

    def s(self, T: float) -> float:
        return self.s298 + self._integrate(T, 2)


class _ConstantCpCurve(_Curve):
    """Constant Cp between stated limits: the coarse condensed-phase fallback."""

    def __init__(self, cp: float, s298: float, tmin: float, tmax: float) -> None:
        self._cp = cp
        self.s298 = s298
        self.tmin = tmin
        self.tmax = tmax
        self.name = "constant_cp"

    def cp(self, T: float) -> float:
        return self._cp

    def dh(self, T: float) -> float:
        return self._cp * (T - T_REF)

    def s(self, T: float) -> float:
        return self.s298 + self._cp * math.log(T / T_REF)


@dataclass(frozen=True)
class SpeciesThermo:
    """Standard-state thermochemistry of one species in one phase. SI: J, mol, K."""

    cas: str
    name: str
    phase: str
    hf298: float
    curve: _Curve
    provenance: dict[str, str] = field(default_factory=dict)

    @property
    def model(self) -> str:
        return self.curve.name

    @property
    def t_range(self) -> tuple[float, float]:
        return self.curve.tmin, self.curve.tmax

    def _check(self, T: float) -> float:
        if T < self.curve.tmin - 0.16 or T > self.curve.tmax:
            raise TemperatureRangeError(
                f"{self.name} ({self.phase}): {T} K is outside the {self.curve.name} range "
                f"[{self.curve.tmin}, {self.curve.tmax}] K"
            )
        return max(T, self.curve.tmin)

    def cp(self, T: float) -> float:
        """Cp°(T), J/(mol K)."""
        return self.curve.cp(self._check(T))

    def h(self, T: float) -> float:
        """H°(T) = ΔfH°298 + [H°(T) − H°298], J/mol."""
        return self.hf298 + self.curve.dh(self._check(T))

    def s(self, T: float) -> float:
        """S°(T), J/(mol K)."""
        return self.curve.s(self._check(T))

    def g(self, T: float) -> float:
        """G°(T) = H°(T) − T·S°(T), J/mol (the Gibbs energy function on the element reference)."""
        return self.h(T) - T * self.s(T)


def _janaf_rows(cas: str, phase: str) -> tuple[list[dict[str, Any]], str] | None:
    """The best single-phase JANAF rows of a species: a table that holds 298.15 K.

    A composite table is cut where it leaves the requested phase, so a solid never
    silently melts. Solid-solid transitions stay inside the solid.
    """
    tables = chemdb.janaf(cas)
    candidates: list[tuple[float, int, int, str, list[dict[str, Any]]]] = []
    for table, rows in tables.items():
        if phase == "reference":
            return (list(rows), table) if rows[0]["phase"] == "ref" else None
        label = str(rows[0]["phase"])
        phase_298 = str(rows[0]["phase_298"])
        rank: int | None = None
        if phase == "gas" and (label == "g" or (label == "ref" and phase_298 == "gas")):
            rank = 1 if label == "ref" else 0
        elif phase == "liquid" and (label == "l" or (label == "ref" and phase_298 == "liquid")):
            rank = 0
        elif phase == "solid" and (label in ("cr", "cr,l") or (label == "ref" and phase_298 == "solid")):
            rank = {"ref": 0, "cr": 1, "cr,l": 2}[label]
        if rank is None:
            continue
        window = _phase_window(rows, phase)
        at_298 = next((r for r in window if float(r["T"]) == T_REF), None)
        if at_298 is not None and at_298["Hf"] is not None:
            # the stable polymorph has the lowest G°298, however long its table runs
            gibbs = float(at_298["Hf"]) - T_REF * float(at_298["S"])
            candidates.append((round(gibbs, 3), rank, -len(window), table, window))
    if not candidates:
        return None
    _, _, _, table, window = min(candidates, key=lambda c: c[:4])
    return window, table


def _phase_window(rows: Sequence[dict[str, Any]], phase: str) -> list[dict[str, Any]]:
    """Rows of a table up to the transition that leaves ``phase``."""
    out: list[dict[str, Any]] = []
    stop = "<--> IDEAL GAS" if phase == "liquid" else "<--> LIQUID"
    for row in rows:
        out.append(row)
        note = str(row.get("note") or "").upper()
        if phase == "gas":
            continue
        if stop in note or (phase == "solid" and "<--> IDEAL GAS" in note):
            break
    return out


def _standard_entropy(cas: str, phase: str, hf: float) -> tuple[float, str]:
    """S°298: stated, else (ΔfH° − ΔfG°)/298.15 + Σ S°(elements), which ΔfS° defines."""
    stated = chemdb.values(cas, f"S0_{phase}")
    if stated:
        row = next(r for r in stated if r.selected)
        return row.value, row.source
    gibbs = chemdb.maybe(cas, f"Gf_{phase}")
    if gibbs is None:
        raise MissingPropertyError(f"no source states S° or ΔfG° for {cas} ({phase})")
    elements = 0.0
    for element, count in chemdb.composition(cas).items():
        reference = _element_reference(element)
        atoms = reference.atoms_per_molecule
        elements += count / atoms * reference.thermo.s(T_REF)
    return (hf - gibbs) / T_REF + elements, "derived from ΔfG° and element S°"


@dataclass(frozen=True)
class _ElementReference:
    thermo: SpeciesThermo
    atoms_per_molecule: int


@lru_cache(maxsize=128)
def _element_reference(symbol: str) -> _ElementReference:
    """The JANAF reference-state species of an element (N -> N2, C -> graphite, ...)."""
    for formula, atoms in ((symbol, 1), (f"{symbol}2", 2)):
        for species in chemdb.by_formula(formula):
            for table in chemdb.janaf(species.cas).values():
                if table[0]["phase"] == "ref":
                    phase = str(table[0]["phase_298"])
                    return _ElementReference(species_thermo(species.cas, phase), atoms)
    raise MissingPropertyError(f"no reference-state table for element {symbol}")


@lru_cache(maxsize=4096)
def species_thermo(query: str, phase: str = "gas", hf_source: str | None = None) -> SpeciesThermo:
    """The standard-state model of a species in ``phase``; see the module docstring.

    ``hf_source`` pins ΔfH°298 to one source (e.g. ``"janaf"``, to reproduce that
    table exactly) instead of the selected value.
    """
    if phase == REFERENCE:
        return _reference_state(query)
    if phase == AQUEOUS:
        return _aqueous_model(query)
    if phase not in PHASES:
        raise ThermochemError(f"phase must be one of {PHASES}, got {phase!r}")
    species = chemdb.find(query)
    rows = chemdb.values(species.cas, f"Hf_{phase}")
    if hf_source is not None:
        rows = [r for r in rows if r.source == hf_source]
    chosen = next((r for r in rows if r.selected), rows[0] if rows else None)
    if chosen is None:
        raise MissingPropertyError(
            f"no ΔfH° for {species.name} ({phase})" + (f" from {hf_source}" if hf_source else "")
        )
    hf = chosen.value
    provenance = {"hf298": f"{chosen.source} [{chosen.grade}] {chosen.reference}".strip()}
    curve: _Curve | None = None
    janaf = _janaf_rows(species.cas, phase)
    if janaf is not None:
        curve = _JanafCurve(janaf[0], janaf[1])
        if chosen.source == "janaf":
            # enthalpy and shape from one table: polymorphs differ in both
            hf = next(float(r["Hf"]) for r in janaf[0] if float(r["T"]) == T_REF)
            provenance["hf298"] = f"janaf [{chosen.grade}] JANAF table {janaf[1]}"
    else:
        pieces = [row for row in chemdb.shomate(species.cas, phase) if row["F"] is not None]
        if pieces:
            curve = _ShomateCurve(pieces)
    if curve is None:
        if phase == "liquid":
            curve = _saturation_curve(species.cas, hf)
    if curve is None:
        s298, s_source = _standard_entropy(species.cas, phase, hf)
        provenance["s298"] = s_source
        if phase == "gas":
            fits = chemdb.cp_gas(species.cas)
            fit = next((f for f in fits if f["form"] == "trc"), fits[0] if fits else None)
            if fit is not None:
                curve = _PolyCurve(fit, s298)
        if curve is None:
            if phase == "liquid":
                pieces = _liquid_fit_pieces(species.cas)
                if pieces:
                    curve = _CpFitCurve(pieces, s298)
            if curve is None:
                pieces = _shomate_cp_pieces(species.cas, phase)
                if pieces:
                    curve = _CpFitCurve(pieces, s298)
        if curve is None:
            cp = chemdb.maybe(species.cas, f"Cp_{phase}")
            if cp is None:
                raise MissingPropertyError(f"no Cp(T) data for {species.name} ({phase})")
            if phase == "gas":
                tmin, tmax = T_REF, T_REF + 100.0
            elif phase == "liquid":
                tmin = chemdb.maybe(species.cas, "Tm") or 200.0
                # a liquid under pressure outlives its normal boiling point, not its critical point
                critical = chemdb.maybe(species.cas, "Tc")
                tmax = 0.9 * critical if critical else chemdb.maybe(species.cas, "Tb") or T_REF + 100.0
            else:
                tmin = 100.0
                tmax = chemdb.maybe(species.cas, "Tm") or T_REF + 100.0
            curve = _ConstantCpCurve(cp, s298, min(tmin, T_REF), max(tmax, T_REF))
    provenance["shape"] = curve.name
    return SpeciesThermo(species.cas, species.name, phase, hf, curve, provenance)


def _aqueous_model(query: str) -> SpeciesThermo:
    """A solute at 1 molal: 298.15 K values with Cp held constant over liquid water.

    The stated Cp°(aq) when a source gives one, else zero (ΔH independent of T, the
    van 't Hoff form), which the model name says. S° comes from ΔfH° and ΔfG° when
    only those are stated, with the charge term of the H+ convention.
    """
    species = chemdb.find(query)
    rows = chemdb.values(species.cas, "Hf_aq")
    if not rows:
        raise MissingPropertyError(f"no aqueous ΔfH° for {species.name}")
    chosen = next(r for r in rows if r.selected)
    stated = chemdb.maybe(species.cas, "S0_aq")
    s298 = stated if stated is not None else _aqueous_entropy(species, chosen.value)
    cp = chemdb.maybe(species.cas, "Cp_aq")
    curve = _ConstantCpCurve(cp or 0.0, s298, *_AQUEOUS_RANGE)
    curve.name = "constant_cp" if cp is not None else "vant_hoff"
    provenance = {
        "hf298": f"{chosen.source} [{chosen.grade}] {chosen.reference}".strip(),
        "shape": curve.name,
    }
    return SpeciesThermo(species.cas, species.name, AQUEOUS, chosen.value, curve, provenance)


def _aqueous_entropy(species: chemdb.Species, hf: float) -> float:
    """S°(aq) = ΔfS° + Σ S°(elements) − (z/2)·S°(H2), from X + z H+ = ion + (z/2) H2."""
    gibbs = chemdb.maybe(species.cas, "Gf_aq")
    if gibbs is None:
        raise MissingPropertyError(f"no source states S° or ΔfG° of {species.name} in water")
    total = (hf - gibbs) / T_REF
    for element, count in chemdb.composition(species.cas).items():
        reference = _element_reference(element)
        total += count / reference.atoms_per_molecule * reference.thermo.s(T_REF)
    hydrogen = _element_reference("H")
    return total - species.charge / 2.0 * hydrogen.thermo.s(T_REF)


def _reference_state(query: str) -> SpeciesThermo:
    """An element's whole JANAF reference table, phase changes included, H°298 = 0.

    Above boiling this is the *reference* vapour, which for sulfur and phosphorus is
    not the atomic gas their CAS names: JANAF's reference continues as S2, so
    ``species_thermo("S", "gas")`` (monatomic) would be the wrong substance.
    """
    species = chemdb.find(query)
    janaf = _janaf_rows(species.cas, REFERENCE)
    if janaf is None:
        raise MissingPropertyError(f"{species.name} has no JANAF reference-state table")
    curve = _JanafCurve(janaf[0], janaf[1])
    return SpeciesThermo(
        species.cas, species.name, REFERENCE, 0.0, curve, {"hf298": "element", "shape": curve.name}
    )


def _has_reference_table(cas: str) -> bool:
    return any(rows[0]["phase"] == "ref" for rows in chemdb.janaf(cas).values())


def _shomate_cp_pieces(cas: str, phase: str) -> list[dict[str, Any]]:
    """Snapshot Shomate pieces that reach 298.15 K, as Cp-only pieces."""
    pieces = sorted(
        ({**row, "form": "shomate_cp"} for row in chemdb.shomate(cas, phase) if row["F"] is None),
        key=lambda r: float(r["Tmin"]),
    )
    if pieces and float(pieces[0]["Tmin"]) <= T_REF + 0.5:
        pieces[0] = {**pieces[0], "Tmin": min(float(pieces[0]["Tmin"]), T_REF)}
        return pieces
    return []


def _liquid_fit_pieces(cas: str) -> list[dict[str, Any]]:
    """Contiguous Cp pieces around 298.15 K of the best family: a reviewed spline first."""
    rows = chemdb.cp_liquid(cas)
    for form in ("zabransky_sat", "zabransky_p", "dippr100"):
        pieces = sorted((r for r in rows if r["form"] == form), key=lambda r: float(r["Tmin"]))
        if pieces and float(pieces[0]["Tmin"]) <= T_REF <= float(pieces[-1]["Tmax"]):
            joined = [pieces[0]]
            for piece in pieces[1:]:
                if float(piece["Tmin"]) > float(joined[-1]["Tmax"]) + 0.5:
                    break
                joined.append(piece)
            if float(joined[-1]["Tmax"]) >= T_REF:
                return joined
    return []


def _saturation_curve(cas: str, hf: float) -> _Curve | None:
    """The saturation model, when there is a gas model and a fit reaching 298.15 K."""
    if vapour_pressure.fit_at(cas, T_REF) is None:
        return None
    try:
        return _SaturationCurve(species_thermo(cas, "gas"), cas, hf)
    except MissingPropertyError:
        return None


def stable_phase(query: str, T: float) -> str:
    """The stable phase at (T, 1 bar), from the reference table or Tm and Tb.

    A species with no melting or boiling data, or no ΔfH° in that phase, falls to
    the nearest phase that has one, gas first.
    """
    species = chemdb.find(query)
    for table in chemdb.janaf(species.cas).values():
        if table[0]["phase"] == "ref":
            transitions = [row for row in table if "<-->" in str(row.get("note") or "")]
            for row in transitions:
                if float(row["T"]) >= T:
                    left = str(row["note"]).split("<-->")[0].strip().upper()
                    if left.startswith("LIQUID"):
                        return "liquid"
                    return "gas" if left.startswith("IDEAL GAS") else "solid"
            return "gas" if transitions else str(table[0]["phase_298"])
    tb = chemdb.maybe(species.cas, "Tb")
    tm = chemdb.maybe(species.cas, "Tm")
    if tb is not None and T >= tb:
        preferred = ["gas", "liquid", "solid"]
    elif tm is not None and T >= tm:
        preferred = ["liquid", "solid", "gas"]
    elif tm is not None:
        preferred = ["solid", "liquid", "gas"]
    elif tb is not None:
        preferred = ["liquid", "gas", "solid"]
    else:
        preferred = ["gas", "liquid", "solid"]
    for phase in preferred:
        if chemdb.maybe(species.cas, f"Hf_{phase}") is not None:
            return phase
    raise MissingPropertyError(f"no ΔfH° in any phase for {species.name}")
