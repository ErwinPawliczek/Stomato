"""Counter-current log-mean temperature difference (spec S-04).

Method: dT1 = Th_in - Tc_out, dT2 = Th_out - Tc_in,
LMTD = (dT1 - dT2) / ln(dT1 / dT2); if dT1 == dT2 (within 1e-9), LMTD = dT1.
A temperature cross (dT <= 0) raises ValueError.
"""

from __future__ import annotations

import math
from typing import Any

from ngdesign.registry import register

_EQUAL_DT_TOL = 1e-9


def lmtd_counter(Th_in: float, Th_out: float, Tc_in: float, Tc_out: float) -> float:
    """Counter-current LMTD in K.

    dT1 = Th_in - Tc_out and dT2 = Th_out - Tc_in are the temperature approaches at
    the two ends of the exchanger. With dT1 != dT2, LMTD = (dT1 - dT2)/ln(dT1/dT2);
    with dT1 == dT2 (within 1e-9 K) the limit is dT1. A temperature cross
    (either approach <= 0) is thermodynamically impossible here and raises.
    """
    dT1 = Th_in - Tc_out
    dT2 = Th_out - Tc_in
    if dT1 <= 0 or dT2 <= 0:
        raise ValueError(f"temperature cross: dT1={dT1!r}, dT2={dT2!r}; both approaches must be > 0")
    if abs(dT1 - dT2) <= _EQUAL_DT_TOL:
        return dT1
    return (dT1 - dT2) / math.log(dT1 / dT2)


def ua_required(Q_W: float, lmtd_K: float, F: float = 1.0) -> float:
    """Required UA conductance in W/K from Q = U*A*F*LMTD.

    F is the LMTD correction factor (F = 1.0 for pure counter-current).
    """
    if Q_W < 0:
        raise ValueError(f"Q_W must be >= 0, got {Q_W!r}")
    if lmtd_K <= 0:
        raise ValueError(f"lmtd_K must be > 0, got {lmtd_K!r}")
    if F <= 0:
        raise ValueError(f"F must be > 0, got {F!r}")
    return Q_W / (F * lmtd_K)


@register("correlation", "lmtd_counter")
class LMTDCounter:
    """Correlation plugin named `lmtd_counter` (matches data/golden/lmtd_counter.yaml)."""

    def __call__(self, **inputs: Any) -> dict[str, Any]:
        lmtd = lmtd_counter(
            Th_in=inputs["Th_in"],
            Th_out=inputs["Th_out"],
            Tc_in=inputs["Tc_in"],
            Tc_out=inputs["Tc_out"],
        )
        return {"lmtd_K": lmtd}
