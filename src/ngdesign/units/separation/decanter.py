"""Decanter (plan §2 U-D 4, spec U-D).

Plugin kind "unit", name "decanter" — registered from the catalogue YAML; no
decorator (round-1 conventions).

LLE split: PT flash at ``(T_in, P_in - dP)``, the light liquid phase to
``light_out`` and the heavy one to ``heavy_out`` (light/heavy by phase
density). A flash that does not return exactly two liquid phases is refused
with a typed error naming T and P: a single liquid makes the split undefined,
and a vapour phase has no outlet on this unit (separate the gas upstream).
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import phase_outlet

#: Mole fraction above which a phase counts as present (flash numerics can
#: leave slivers; the separator's ``mole_fraction <= 0`` test is the shape).
_PHASE_PRESENT = 1e-12


class DecanterSpecError(ValueError):
    """The feed does not split into two liquid phases at the decanter state."""


class Decanter:
    """LLE split of a feed into light and heavy liquid outlets."""

    inlet_ports: tuple[str, ...] = ("inlet",)
    outlet_ports: tuple[str, ...] = ("light_out", "heavy_out")

    def solve(
        self,
        inlets: dict[str, StreamState],
        params: dict[str, Any],
        thermo: Thermo,
    ) -> UnitResult:
        inlet = inlets["inlet"]
        dP = float(params.get("dP", 0.0))
        if dP < 0:
            raise DecanterSpecError(f"dP {dP} must be >= 0")
        T, P = inlet.T, inlet.P - dP
        if P <= 0:
            raise DecanterSpecError(f"dP {dP} leaves a non-positive decanter pressure")

        flashed = thermo.flash_pt(inlet.composition, T, P, inlet.molar_flow)

        liquids = [
            p
            for p in flashed.phases
            if p.kind is not PhaseKind.VAPOR and p.mole_fraction > _PHASE_PRESENT
        ]
        vapor = next(
            (p for p in flashed.phases if p.kind is PhaseKind.VAPOR and p.mole_fraction > _PHASE_PRESENT),
            None,
        )
        if len(liquids) < 2:
            kinds = ", ".join(sorted(p.kind for p in flashed.phases)) or "none"
            raise DecanterSpecError(
                f"the flash at T={T:.2f} K, P={P:.1f} Pa returned {len(liquids)} "
                f"liquid phase(s) ({kinds}); a decanter needs two immiscible "
                "liquids — a single liquid makes the light/heavy split undefined"
            )
        if vapor is not None:
            raise DecanterSpecError(
                f"the flash at T={T:.2f} K, P={P:.1f} Pa returned a vapour phase "
                f"(mole fraction {vapor.mole_fraction:.4g}); the decanter's two "
                "outlets accept liquids only — separate the gas upstream"
            )

        light, heavy = (
            (liquids[0], liquids[1])
            if liquids[0].density <= liquids[1].density
            else (liquids[1], liquids[0])
        )
        outlets = {
            "light_out": phase_outlet(thermo, inlet, T, P, light),
            "heavy_out": phase_outlet(thermo, inlet, T, P, heavy),
        }
        h_in_W = inlet.enthalpy * inlet.molar_flow
        h_out_W = sum(s.enthalpy * s.molar_flow for s in outlets.values())
        return UnitResult(
            outlets=outlets,
            duty_W=h_out_W - h_in_W,
            power_W=0.0,
            info={},
        )

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """A subcooled water / n-pentane feed: two liquid phases, no vapour.

        0.6/0.4 H2O/nC5 at 5 °C, 1 bar flashes to an hc liquid (0.404) and an
        aqueous phase (0.596) on ``pr`` — verified against the flasher.
        """
        feed = {
            "T": 278.15,
            "P": 1.0e5,
            "molar_flow": 100.0,
            "composition": {"H2O": 0.6, "nC5": 0.4},
        }
        return {"inlet": feed}, {}
