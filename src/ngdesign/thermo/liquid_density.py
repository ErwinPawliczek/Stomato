"""Liquid-density correlations selected as a cubic-adapter option (spec T-02 vocabulary).

The density of a liquid root stops being the cubic EOS's own volume and comes from
a corresponding-states correlation. VLE, enthalpy and entropy stay the EOS's: the
option changes the reported volume only, which is exactly what simulators mean by
"PR with COSTALD liquid density" (the EOS volume is the worst thing a cubic
reports, the fugacities are unaffected). The price is that the reported volume is
no longer the pressure derivative of the EOS Gibbs energy.

- ``rackett``: Spencer & Danner (1972) mixture form of the Rackett (1970) equation
  (``chemicals.volume.Rackett_mixture``) with the Yamada & Gunn (1973) generalised
  ``Z_RA = 0.29056 - 0.08775 omega``. Saturated-liquid volume: no pressure term.
- ``costald``: Hankinson & Thomson (1979) saturated volume with the
  Thomson, Brobst & Hankinson (1982) Tait compression, the API Technical Data Book
  procedures 6A3.2/6A3.4 (``chemicals.volume.COSTALD_mixture_compressed``). The
  databank critical volume stands in for the fitted characteristic volume V*.

Both correlations are subcritical in the mixture's own pseudo-critical temperature.
At or above it, and on a root that is not a liquid root, the EOS volume stands: no
correlation is extrapolated past its definition.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from chemicals.volume import COSTALD_mixture_compressed, Rackett_mixture
from thermo.phases import CEOSGas

from ngdesign.thermo.options import LiquidDensity

#: Yamada & Gunn (1973), J. Chem. Eng. Data 18, 234: generalised Rackett parameter.
_ZRA_INTERCEPT = 0.29056
_ZRA_SLOPE = 0.08775


def rackett_zra(omega: float) -> float:
    """Rackett parameter ``Z_RA = 0.29056 - 0.08775 omega`` (Yamada & Gunn 1973)."""
    return _ZRA_INTERCEPT - _ZRA_SLOPE * omega


def _real_volume(correlation: Callable[..., Any], *args: Any) -> float | None:
    """The correlation's volume, or None once T passes its mixture Tcm.

    Above Tcm both correlations raise (1 - Tr) to a fractional power, which leaves the
    reals: Python hands back a complex, or raises from the arithmetic built on it.
    """
    try:
        volume = correlation(*args)
    except (ValueError, ZeroDivisionError, OverflowError, TypeError):
        return None
    if not isinstance(volume, float) or not math.isfinite(volume) or volume <= 0.0:
        return None
    return volume


def rackett_volume(
    T: float,
    xs: Sequence[float],
    tcs: Sequence[float],
    pcs: Sequence[float],
    omegas: Sequence[float],
    mws: Sequence[float],
) -> float | None:
    """Saturated-liquid molar volume (m3/mol), Spencer-Danner mixture Rackett; None above Tcm.

    V_m = R (sum x_i Tc_i/Pc_i) Z_RA,m^(1 + (1 - Tr)^(2/7)), Spencer & Danner, J. Chem.
    Eng. Data 17 (1972) 236.
    """
    zrs = [rackett_zra(om) for om in omegas]
    return _real_volume(Rackett_mixture, T, list(xs), list(mws), list(tcs), list(pcs), zrs)


def costald_volume(
    T: float,
    P: float,
    xs: Sequence[float],
    tcs: Sequence[float],
    vcs: Sequence[float],
    omegas: Sequence[float],
) -> float | None:
    """COSTALD-Tait compressed-liquid molar volume (m3/mol); None past the correlation's range.

    V = V_s [1 - C ln((B + P)/(B + P_sat))], Thomson, Brobst & Hankinson, AIChE J. 28
    (1982) 671, over the Hankinson & Thomson, AIChE J. 25 (1979) 653 saturated volume.
    """
    return _real_volume(COSTALD_mixture_compressed, list(xs), T, list(tcs), list(vcs), list(omegas), P)


class CorrelatedDensityPhase:
    """Mixin for CEOS phase classes: liquid roots take their volume from a correlation.

    Class attributes hold the per-slate constants: `thermo` clones phases through a
    whitelist, so instance attributes would not survive a state change.
    """

    density_model: ClassVar[LiquidDensity]
    density_vcs: ClassVar[tuple[float, ...]] = ()
    density_mws: ClassVar[tuple[float, ...]] = ()

    # Provided by the CEOS phase this mixes into.
    eos_mix: Any
    zs: list[float]
    T: float
    P: float

    def _holds_liquid_root(self) -> bool:
        """True when this phase reports a liquid root (see _state._holds_gas_root)."""
        if isinstance(self, CEOSGas):
            return bool(self.eos_mix.phase == "l")
        return hasattr(self.eos_mix, "V_l")

    def V(self) -> float:
        eos_volume = float(super().V())  # type: ignore[misc]
        if not self._holds_liquid_root():
            return eos_volume
        eos = self.eos_mix
        if self.density_model == LiquidDensity.RACKETT:
            volume = rackett_volume(self.T, self.zs, eos.Tcs, eos.Pcs, eos.omegas, self.density_mws)
        else:
            volume = costald_volume(self.T, self.P, self.zs, eos.Tcs, self.density_vcs, eos.omegas)
        return eos_volume if volume is None else volume
