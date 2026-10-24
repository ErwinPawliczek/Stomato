"""``preflash`` adapter (spec U-H1).

Preflash drum at rigour R0: a two-phase separation of the heated crude feed at
``T`` and ``P``. The adapter composes the U-D separator (``units.separator``,
the two-phase scrubber variant): it only sets the drum conditions by flashing
the feed at (T, P) and hands the flashed feed to the separator's phase split,
so no flash physics of its own (the U-D ``flash_drum`` row replaces the
separator once it lands). Vapour reports to ``vapor_out``, all liquid phases
(hydrocarbon and aqueous) pool into ``liquid_out``. No cut-point splitting
happens here — that is the crude column's job; ``info`` carries the vapour
fraction and the two products' reference volumes.
"""

from __future__ import annotations

from typing import Any

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining._cuts import RefiningSpecError, optional_float, require_float
from ngdesign.units.refining.slate import reference_volume
from ngdesign.units.separator import Scrubber


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
            "feed_in": {
                "T": 505.37,
                "P": 2.5e5,
                "molar_flow": 1000.0,
                "composition": dict(mole),
            }
        }
        return feeds, {"T": 505.37, "P": 2.5e5}

    def solve(self, inlets: dict[str, StreamState], params: dict[str, Any], thermo: Thermo) -> UnitResult:
        """Set the drum (T, P) and let the separator adapter split the phases."""
        feed = inlets.get("feed_in")
        if feed is None:
            raise RefiningSpecError("feed_in: the crude inlet stream is required")
        t_out = require_float(params, "T")
        p_out = optional_float(params, "P", feed.P)
        if p_out <= 0.0:
            raise RefiningSpecError("P: must be positive")

        # Drum conditions: flash the feed at (T, P) — the phase split itself is
        # the separator adapter's (one owner of the flash physics).
        flashed_feed = thermo.flash_pt(feed.composition, t_out, p_out, feed.molar_flow)
        split = Scrubber().solve({"inlet": flashed_feed}, {"dP": 0.0}, thermo)
        vapour = split.outlets["gas_out"]
        liquid = split.outlets["liquid_out"]
        h_in = feed.enthalpy * feed.molar_flow
        h_out = vapour.enthalpy * vapour.molar_flow + liquid.enthalpy * liquid.molar_flow
        info = {
            "vapor_frac": flashed_feed.vapor_fraction,
            "light_ends_vol_m3_s": reference_volume(vapour),
            "crude_vol_m3_s": reference_volume(liquid),
        }
        return UnitResult(
            outlets={"vapor_out": vapour, "liquid_out": liquid},
            duty_W=h_out - h_in,
            power_W=0.0,
            info=info,
        )
