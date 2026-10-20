"""Shared example basis for unit `example_case()` feeds and tests.

These are EXAMPLE values for the vertical-slice sample model and the property
tests — not engineering defaults. They live here (in `ngdesign.units`) because
sample flowsheet modules are built *from* units: the unit-operation layer must
not depend on a sample flowsheet module. Pure data, no behavior.
"""

from __future__ import annotations

# Example inlet composition (mole fractions) for the 50 MMSCFD rich wet sweet gas
# feed of the vertical-slice flowsheet.
INLET_COMPOSITION = {
    "N2": 0.005,
    "CO2": 0.015,
    "C1": 0.848,
    "C2": 0.062,
    "C3": 0.032,
    "iC4": 0.007,
    "nC4": 0.010,
    "iC5": 0.004,
    "nC5": 0.004,
    "C6+": 0.010,
    "H2O": 0.003,
}

# lbmol at 60 F, 14.696 psia -> mol/s
MMSCFD_TO_MOL_S = 1e6 / 379.49 * 453.59237 / 86400
