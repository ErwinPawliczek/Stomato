"""Stream state. LOCKED."""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, field_validator, model_validator

from ngdesign.data import components

from .common import Model

DEFAULT_SLATE: tuple[str, ...] = (
    "N2",
    "CO2",
    "H2S",
    "C1",
    "C2",
    "C3",
    "iC4",
    "nC4",
    "iC5",
    "nC5",
    "C6+",
    "H2O",
    "TEG",
    "MDEA",
    "MEA",
    "DEA",
    "MeOH",
    "MEG",
)  # keys of data/components.yaml - the sample flowsheets' default slate, not a type

COMP_TOL = 1e-6


def _check_composition(z: dict[str, float]) -> dict[str, float]:
    """Non-negativity and sum-to-1 only (spec P1-02).

    Component membership is not checked here: any id the open component registry
    resolves is legal. A flowsheet validates its feeds against its own component
    slate, and the thermo layer validates ids again at flasher build.
    """
    if any(v < 0 for v in z.values()):
        raise ValueError("negative mole fraction")
    s = sum(z.values())
    if abs(s - 1.0) > COMP_TOL:
        raise ValueError(f"mole fractions sum to {s}, not 1")
    return z


class PhaseKind(StrEnum):
    VAPOR = "vapor"
    HC_LIQUID = "hc_liquid"
    AQUEOUS = "aqueous"
    SOLID = "solid"  # T-10 contract change: solid-liquid equilibrium streams


class Phase(Model):
    #: Frozen (spec P1-01): property packages cache and share these objects.
    model_config = ConfigDict(frozen=True)

    kind: PhaseKind
    mole_fraction: float  # of the total stream
    composition: dict[str, float]
    density: float  # kg/m3
    viscosity: float | None = None  # Pa.s
    z_factor: float | None = None
    molecular_weight: float  # g/mol
    enthalpy: float = 0.0  # J/mol (spec P1-01)
    entropy: float = 0.0  # J/(mol K) (spec P1-01)
    cp: float = 0.0  # J/(mol K) (spec P1-01)
    ln_phi: dict[str, float] = {}  # ln fugacity coefficient per component (spec P1-01)

    @field_validator("composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)


class StreamState(Model):
    """Fully specified thermodynamic state of a stream."""

    #: Frozen (spec P1-01): property packages cache and share these objects.
    model_config = ConfigDict(frozen=True)

    T: float  # K
    P: float  # Pa absolute
    molar_flow: float  # mol/s
    composition: dict[str, float]  # overall mole fractions
    vapor_fraction: float  # molar, 0..1 (all non-vapor phases count as liquid)
    enthalpy: float  # J/mol
    entropy: float  # J/(mol.K)
    phases: list[Phase] = []

    @field_validator("composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)

    @model_validator(mode="after")
    def _ranges(self) -> StreamState:
        if self.T <= 0 or self.P <= 0 or self.molar_flow < 0:
            raise ValueError("T, P must be > 0 and flow >= 0")
        if not 0.0 <= self.vapor_fraction <= 1.0:
            raise ValueError("vapor_fraction outside [0, 1]")
        if self.phases:
            s = sum(p.mole_fraction for p in self.phases)
            if abs(s - 1.0) > 1e-6:
                raise ValueError(f"phase fractions sum to {s}")
        return self

    @property
    def mass_flow(self) -> float:
        """kg/s, from phase MWs if present, else from the component database (P1-01)."""
        if self.phases:
            mw = sum(p.mole_fraction * p.molecular_weight for p in self.phases)
        else:
            db = components()
            mw = sum(x * float(db[cid]["mw"]) for cid, x in self.composition.items())
        return self.molar_flow * mw / 1000.0

    def component_flows(self) -> dict[str, float]:
        """mol/s of each component."""
        return {k: v * self.molar_flow for k, v in self.composition.items()}
