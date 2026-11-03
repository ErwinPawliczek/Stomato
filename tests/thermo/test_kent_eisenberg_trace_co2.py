"""Kent-Eisenberg carbamate balance at trace CO2 (amine package domain fix).

The 5-stage MEA absorber left the package domain at 335.4 K with a CO2
loading of 1.9e-14 beside an H2S loading of 0.44: the carbamate carbon
balance's Brent root has an absolute tolerance (~5e-13 mol/L), the root lay
below it, and the solver returned hco3 = 0, so p_CO2 = 0 and the heat of
absorption's ln p raised "speciation pressure vanished". Trace states are now
solved in ln(hco3). Independent checks: Henry's-law linearity of p_CO2 in the
dilute limit, and continuity across the switch to the linear solve.
"""

from __future__ import annotations

import pytest

from ngdesign.amine.kent_eisenberg import _TRACE_CO2_MOL_L, equilibrium_partial_pressures

T = 335.43848135932876
C_MEA = 3826.755353797313  # mol/m3, the absorber stage's amine molarity
A_H2S = 0.44274847100213743


def test_trace_co2_pressure_is_positive_where_it_vanished() -> None:
    p_co2, p_h2s = equilibrium_partial_pressures(T, C_MEA, 1.9370729677246003e-14, A_H2S, amine="MEA")
    assert p_co2 > 0.0
    assert p_h2s > 0.0


def test_trace_co2_pressure_is_linear_in_loading() -> None:
    """Infinite dilution: the free CO2 - hence p_CO2 - is proportional to the
    total CO2 at fixed solvent and H2S state (the trace species does not move
    the pH). Two loadings a decade apart give the same p/a to 1e-6."""
    a1, a2 = 1e-14, 1e-13
    p1 = equilibrium_partial_pressures(T, C_MEA, a1, A_H2S, amine="MEA")[0]
    p2 = equilibrium_partial_pressures(T, C_MEA, a2, A_H2S, amine="MEA")[0]
    assert p1 / a1 == pytest.approx(p2 / a2, rel=1e-6)


@pytest.mark.parametrize("amine", ["MEA", "DEA"])
def test_continuous_across_the_trace_switch(amine: str) -> None:
    """Just below and just above the switch the two solves agree to the
    LINEAR solve's own accuracy: its absolute Brent tolerance (~5e-13 mol/L)
    against the free bicarbonate there (most CO2 sits as carbamate) - measured
    jump in p/a 2.0e-6 for MEA, 6.5e-7 for DEA. The log solve is the
    accurate side; the linear one is kept above the switch so every
    non-trace state stays bit-identical (bench and dispatch golden)."""
    c_l = C_MEA / 1000.0
    below = _TRACE_CO2_MOL_L * (1.0 - 1e-9) / c_l
    above = _TRACE_CO2_MOL_L * (1.0 + 1e-9) / c_l
    p_below = equilibrium_partial_pressures(T, C_MEA, below, A_H2S, amine=amine)[0]
    p_above = equilibrium_partial_pressures(T, C_MEA, above, A_H2S, amine=amine)[0]
    assert p_below / below == pytest.approx(p_above / above, rel=1e-5)
