"""Crude assay records (spec A-01).

``DistillationCurve`` is one measured distillation curve (TBP, ASTM D86, ASTM
D1160 or ASTM D2887) and ``Assay`` the bulk measurements a refinery has around
it: bulk gravity, light ends and optional gravity/characterization extras.
A-01 stops at the records and the conversions in :mod:`ngdesign.data.assay`;
wiring an ``Assay`` into ``Flowsheet`` is the round-1 U-H assay feeder, which
consumes the cut slate unchanged.

This module is a contract: pure records, no physics. The conversions, the
distribution fit and the cutting live in ``ngdesign.data.assay`` (the lowest
import layer), which returns data-layer pseudo definitions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from .common import Model

#: Curve types the assay layer accepts, with the conversion each needs
#: (spec A-01): TBP is used as measured; D86, D1160 and D2887 convert to TBP
#: through the cited correlations in ``ngdesign.data.assay``.
CurveKind = Literal["TBP", "D86", "D1160", "D2887"]

#: Basis of the curve (and of the light ends, declared separately): liquid
#: volume percent or weight percent, per the source's own reporting.
CurveBasis = Literal["LV%", "wt%"]


class DistillationCurve(Model):
    """One measured distillation curve: (percent, T_K) points, ascending.

    ``P_kPa`` records the operating pressure for a D1160 curve (the pressure
    the vapor temperatures were measured at); it must be absent for the other
    kinds, which are atmospheric measurements.
    """

    kind: CurveKind
    basis: CurveBasis
    points: list[tuple[float, float]]  # (volume/weight percent, T in K)
    P_kPa: float | None = None  # kPa abs, D1160 only (2 mmHg lower bound ~0.27)

    @model_validator(mode="after")
    def _monotone_points(self) -> DistillationCurve:
        if len(self.points) < 3:
            raise ValueError(f"{self.kind} curve needs at least 3 points, got {len(self.points)}")
        percents = [p for p, _ in self.points]
        temps = [t for _, t in self.points]
        for percent in percents:
            if not 0.0 <= percent <= 100.0:
                raise ValueError(f"{self.kind} curve percent {percent} outside [0, 100]")
        if any(t2 <= t1 for t1, t2 in zip(temps, temps[1:], strict=False)):
            raise ValueError(f"{self.kind} curve temperatures must be strictly increasing")
        if percents != sorted(percents):
            raise ValueError(f"{self.kind} curve percents must be ascending")
        if self.kind == "D1160":
            if self.P_kPa is None or self.P_kPa <= 0.0:
                raise ValueError("a D1160 curve needs its operating pressure P_kPa > 0")
        elif self.P_kPa is not None:
            raise ValueError(f"{self.kind} is an atmospheric curve; P_kPa must be absent")
        return self


class Assay(Model):
    """One crude assay: a distillation curve plus the bulk refinery measurements.

    Bulk gravity is ``api_gravity`` or ``sg`` (exactly one). The optional
    ``sg_curve`` overrides the constant-Watson-K gravity distribution; an
    explicit ``watson_k`` or ``meabp_k`` overrides the value derived from the
    bulk gravity and the curve's average boiling points. ``light_ends`` maps
    databank component ids to fractions on ``light_ends_basis`` (mole, mass or
    volume). ``provenance`` is required and non-empty: where the numbers were
    printed (source, table, page).
    """

    id: str
    curve: DistillationCurve
    api_gravity: float | None = None  # deg API at 15.6 C
    sg: float | None = None  # specific gravity, water = 1
    sg_curve: list[tuple[float, float]] | None = None  # (percent, sg)
    watson_k: float | None = None  # Watson characterization factor, -
    meabp_k: float | None = None  # K, measured mean average boiling point
    light_ends: dict[str, float] = {}  # databank cid -> fraction
    light_ends_basis: Literal["mole", "mass", "volume"] | None = None
    sulfur_wt_pct: float | None = None
    provenance: dict[str, str]

    @model_validator(mode="after")
    def _bulk_and_provenance(self) -> Assay:
        if (self.api_gravity is None) == (self.sg is None):
            raise ValueError(f"assay {self.id!r} needs exactly one of api_gravity and sg")
        if not self.provenance:
            raise ValueError(f"assay {self.id!r} needs a non-empty provenance")
        if bool(self.light_ends) != (self.light_ends_basis is not None):
            raise ValueError(f"assay {self.id!r}: light_ends and light_ends_basis must be given together")
        if self.api_gravity is not None and not 0.0 < self.api_gravity < 100.0:
            raise ValueError(f"assay {self.id!r}: api_gravity {self.api_gravity} outside (0, 100)")
        if self.sg is not None and not 0.5 < self.sg < 1.5:
            raise ValueError(f"assay {self.id!r}: sg {self.sg} outside (0.5, 1.5)")
        return self

    @property
    def bulk_sg(self) -> float:
        """Bulk specific gravity, water = 1 (141.5/(131.5 + API), the inverse API definition)."""
        if self.sg is not None:
            return self.sg
        assert self.api_gravity is not None  # validator guarantees one
        return 141.5 / (131.5 + self.api_gravity)
