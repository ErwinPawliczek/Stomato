"""Stream state. LOCKED."""

from __future__ import annotations

from enum import StrEnum

from pydantic import field_validator, model_validator

from .common import Model

COMPONENTS: tuple[str, ...] = (
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
    "MeOH",
    "MEG",
)  # keys of data/components.yaml

COMP_TOL = 1e-6


def _check_composition(z: dict[str, float]) -> dict[str, float]:
    unknown = set(z) - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unknown components {sorted(unknown)}")
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


class Phase(Model):
    kind: PhaseKind
    mole_fraction: float  # of the total stream
    composition: dict[str, float]
    density: float  # kg/m3
    viscosity: float | None = None  # Pa.s
    z_factor: float | None = None
    molecular_weight: float  # g/mol

    @field_validator("composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)


class StreamState(Model):
    """Fully specified thermodynamic state of a stream."""

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
        """kg/s, from phase MWs if present, else requires the thermo layer."""
        if not self.phases:
            raise ValueError("mass_flow needs phases (call thermo first)")
        mw = sum(p.mole_fraction * p.molecular_weight for p in self.phases)
        return self.molar_flow * mw / 1000.0

    def component_flows(self) -> dict[str, float]:
        """mol/s of each component."""
        return {k: v * self.molar_flow for k, v in self.composition.items()}
