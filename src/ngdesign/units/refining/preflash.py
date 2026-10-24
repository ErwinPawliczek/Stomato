"""``preflash`` adapter (spec U-H1).

Preflash drum at rigour R0: a two-phase separation of the heated crude feed at
``T`` and ``P`` (the desalter feed temperature and drum pressure in the
flowsheet). The flash's vapour phases report to ``vapor_out``, all liquid
phases (hydrocarbon and aqueous) pool into ``liquid_out``. No cut-point
splitting happens here — that is the crude column's job; ``info`` carries the
vapour fraction and the two products' reference volumes.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import Phase, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.registry import register
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float, require_float
from ngdesign.units.refining.slate import reference_volume


@register("unit", "preflash")
class Preflash:
    """Flash the crude feed into vapour and liquid ahead of the crude column."""

    inlet_ports: tuple[str, ...] = ("feed_in",)
    outlet_ports: tuple[str, ...] = ("vapor_out", "liquid_out")

    @classmethod
    def example_case(cls) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
        """The light crude at 232 degC drum temperature and 2.5 bar (Gary et al. p. 66)."""
        from ngdesign.units.refining.assay_feeder import _EXAMPLE_ASSAY
        from ngdesign.units.refining.slate import assay_slate, register_slate

        register_slate(_EXAMPLE_ASSAY)
        _, mole = assay_slate(_EXAMPLE_ASSAY)
        feeds = {
            "crude_in": {
                "T": 505.37,
                "P": 2.5e5,
                "molar_flow": 1000.0,
                "composition": dict(mole),
            }
        }
        return feeds, {"T": 505.37, "P": 2.5e5}

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Flash the feed at (T, P) and route the vapour and liquid phases out."""
        feed = inlets.get("crude_in")
        if feed is None:
            raise RefiningSpecError("crude_in: the crude inlet stream is required")
        t_out = require_float(params, "T")
        p_out = optional_float(params, "P", feed.P)
        if p_out <= 0.0:
            raise RefiningSpecError("P: must be positive")

        flashed = thermo.flash_pt(feed.composition, t_out, p_out, feed.molar_flow)
        vapour_phase = next((p for p in flashed.phases if p.kind is PhaseKind.VAPOR), None)
        liquid_phase = _combined_liquid(flashed.phases)
        vapour = _reflashed_or_zero(thermo, feed, t_out, p_out, vapour_phase)
        liquid = _reflashed_or_zero(thermo, feed, t_out, p_out, liquid_phase)
        h_in = feed.enthalpy * feed.molar_flow
        h_out = vapour.enthalpy * vapour.molar_flow + liquid.enthalpy * liquid.molar_flow
        info = {
            "vapor_frac": flashed.vapor_fraction,
            "light_ends_vol_m3_s": reference_volume(vapour),
            "crude_vol_m3_s": reference_volume(liquid),
        }
        return UnitResult(
            outlets={"vapor_out": vapour, "liquid_out": liquid},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )


def _combined_liquid(phases: list[Phase]) -> Phase | None:
    """Flow-weighted combined liquid (hc_liquid + aqueous), as in the scrubber."""
    liquids = [p for p in phases if p.kind is not PhaseKind.VAPOR]
    if not liquids:
        return None
    total = sum(p.mole_fraction for p in liquids)
    composition = {
        cid: sum(p.mole_fraction * p.composition[cid] for p in liquids) / total
        for cid in liquids[0].composition
    }
    return liquids[0].model_copy(update={"mole_fraction": total, "composition": composition})


def _reflashed_or_zero(
    thermo: Thermo,
    feed: StreamState,
    t_out: float,
    p_out: float,
    phase: Phase | None,
) -> StreamState:
    """Re-flash one phase at (T, P); an absent phase gives a zero-flow outlet."""
    if phase is None or phase.mole_fraction <= 0.0:
        return feed.model_copy(update={"T": t_out, "P": p_out, "molar_flow": 0.0})
    return thermo.flash_pt(phase.composition, t_out, p_out, phase.mole_fraction * feed.molar_flow)
