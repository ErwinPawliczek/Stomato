"""Fitting dimensions for 3D routing and isometrics (spec S-21).

Centre-to-end (cte) is the distance from a fitting's centre point — the
intersection of its legs — to each end face, measured along the leg axis, in
mm. Later fitting dimensions land here as their specs are implemented.
"""

from __future__ import annotations

MM_PER_IN = 25.4

# Weld-neck flange length placeholder until the H-01 flange dimensions land.
WN_FLANGE_LENGTH_MM = 100.0


def elbow_90_lr_cte_mm(nps_in: float) -> float:
    """B16.9 long-radius 90 deg elbow centre-to-end: 1.5 x NPS."""
    return 1.5 * nps_in * MM_PER_IN
