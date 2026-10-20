"""Thermo contract records (spec P1-01). Typed outputs of the ``Thermo`` protocol.

All SI: K, Pa absolute, J/mol, J/(mol K), kg/m3, Pa.s, W/(m K).
"""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from .common import Model
from .stream import PhaseKind, _check_composition


class SaturationError(ValueError):
    """Raised when no two-phase region exists at the requested state.

    The "None-equivalent" error of the saturation surface: a supercritical feed
    (above every component's critical point at the given T or P) has no bubble
    or dew point, so the solver raises this instead of returning a number.
    """


class PhaseProps(Model):
    """Properties of ONE phase at (composition, T, P), built without flashing."""

    kind: PhaseKind
    mole_fraction: float  # of the phase object itself; 1.0 for a single-phase build
    composition: dict[str, float]
    molecular_weight: float  # g/mol
    density: float  # kg/m3
    enthalpy: float  # J/mol
    entropy: float  # J/(mol K)
    cp: float  # J/(mol K)
    gibbs: float  # J/mol
    z_factor: float  # P * V_molar / (R * T)
    viscosity: float | None = None  # Pa.s
    thermal_conductivity: float | None = None  # W/(m K)
    ln_phi: dict[str, float] = {}  # ln fugacity coefficient per component

    @field_validator("composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)


class SaturationPoint(Model):
    """One bubble or dew point of the feed composition."""

    T: float  # K
    P: float  # Pa absolute
    kind: Literal["bubble", "dew"]
    incipient_composition: dict[str, float]  # composition of the appearing phase

    @field_validator("incipient_composition")
    @classmethod
    def _comp(cls, v: dict[str, float]) -> dict[str, float]:
        return _check_composition(v)


class PropertyDerivatives(Model):
    """d ln phi / d state per component, for one phase at (composition, T, P)."""

    dlnphi_dT: dict[str, float]  # 1/K
    dlnphi_dP: dict[str, float]  # 1/Pa
