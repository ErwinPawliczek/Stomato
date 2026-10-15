"""Regression tests for the Kent-Eisenberg MDEA equilibrium module.

Anchors are independent published values, not outputs of this module:

- CO2: NeqSim's MDEA-model regression points -- 313.15 K, 50 wt% MDEA
  (4.3638 kmol/m3 via NeqSim's density convention): p_CO2 ~ 0.0093 bara at
  loading 0.10 and ~ 0.229 bara at loading 0.40 (NeqSim
  ``MDEA-amine-thermo`` documentation; the constants behind them are Edwards,
  Maurer, Newman & Prausnitz 1978, Versteeg & van Swaaij 1988, and the
  NeqSim apparent MDEA constant fitted to Jou, Mather & Otto 1982).

- H2S: Jou, Mather & Otto 1982 (I&EC Process Des. Dev. 21, 539) 40 degC
  isotherm at 4.28 kmol/m3 MDEA, as tabulated in the GASWORKS
  h2s-mdea-absorber precedent (tests/test_equilibrium.py::test_jou_mather_anchors):
  0.0108 kPa at loading 0.01, 3.31 kPa at 0.165, 36.9 kPa at 0.453.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units.mdea_equilibrium import (
    _brent_root,
    amine_molarity,
    equilibrium_loadings,
    equilibrium_partial_pressures,
)

T_40C = 313.15
C_50WT_PCT_NEQSIM = 4363.8  # mol/m3, NeqSim amineMolarity(0.50, 119.16) convention
C_JOU = 4280.0  # mol/m3, Jou-Mather-Otto 4.28 kmol/m3


def test_co2_anchors_neqsim() -> None:
    for loading, target_bara in ((0.10, 0.0093), (0.40, 0.229)):
        p_co2, p_h2s = equilibrium_partial_pressures(T_40C, C_50WT_PCT_NEQSIM, loading, 0.0)
        assert p_h2s == 0.0
        assert p_co2 / 1e5 == pytest.approx(target_bara, rel=0.05), f"loading={loading}"


def test_h2s_anchors_jou_mather_otto() -> None:
    for loading, target_kpa in ((0.01, 0.0108), (0.165, 3.31), (0.453, 36.9)):
        p_co2, p_h2s = equilibrium_partial_pressures(T_40C, C_JOU, 0.0, loading)
        assert p_co2 == 0.0
        assert p_h2s / 1000.0 == pytest.approx(target_kpa, rel=0.03), f"loading={loading}"


@pytest.mark.parametrize("co2,h2s", [(0.05, 0.01), (0.4, 0.1), (0.8, 0.2)])
def test_round_trip_loadings_to_pressures_and_back(co2: float, h2s: float) -> None:
    p_co2, p_h2s = equilibrium_partial_pressures(T_40C, C_JOU, co2, h2s)
    back_co2, back_h2s = equilibrium_loadings(T_40C, C_JOU, p_co2, p_h2s)
    assert back_co2 == pytest.approx(co2, rel=1e-6)
    assert back_h2s == pytest.approx(h2s, rel=1e-6)


def test_acid_gases_compete_for_the_amine() -> None:
    # CO2 loading consumes proton capacity, raising the H2S partial pressure
    # at fixed H2S loading (shared MDEAH+ pool).
    _, p_h2s_alone = equilibrium_partial_pressures(T_40C, C_JOU, 0.0, 0.1)
    _, p_h2s_with_co2 = equilibrium_partial_pressures(T_40C, C_JOU, 0.6, 0.1)
    assert p_h2s_with_co2 > 10.0 * p_h2s_alone


def test_pressure_rises_with_loading_and_temperature() -> None:
    p_cold, _ = equilibrium_partial_pressures(313.15, C_JOU, 0.4, 0.0)
    p_hot, _ = equilibrium_partial_pressures(383.15, C_JOU, 0.4, 0.0)
    assert p_hot > 20.0 * p_cold  # the absorber/stripper duality
    p_lean, _ = equilibrium_partial_pressures(T_40C, C_JOU, 0.3, 0.0)
    p_rich, _ = equilibrium_partial_pressures(T_40C, C_JOU, 0.45, 0.0)
    assert p_rich > p_lean


def test_amine_molarity_from_flashed_phase() -> None:
    # 50 wt% aqueous MDEA: x_MDEA = 0.1313, phase MW ~ 31.3 g/mol, rho ~ 1035 kg/m3.
    molarity = amine_molarity(0.1313, 31.3, 1035.0)
    assert molarity / 1000.0 == pytest.approx(4.34, rel=0.03)


def test_zero_and_negative_inputs_raise() -> None:
    with pytest.raises(ValueError, match="temperature"):
        equilibrium_partial_pressures(0.0, C_JOU, 0.1, 0.0)
    with pytest.raises(ValueError, match="molarity"):
        equilibrium_partial_pressures(T_40C, 0.0, 0.1, 0.0)
    with pytest.raises(ValueError, match="co2_loading"):
        equilibrium_partial_pressures(T_40C, C_JOU, -0.1, 0.0)
    with pytest.raises(ValueError, match="h2s_loading"):
        equilibrium_partial_pressures(T_40C, C_JOU, 0.1, 2.0)
    with pytest.raises(ValueError, match="non-negative"):
        equilibrium_loadings(T_40C, C_JOU, -1.0, 0.0)


def test_no_mdea_raises() -> None:
    with pytest.raises(ValueError, match="no MDEA"):
        amine_molarity(0.0, 18.0, 1000.0)


def test_brent_root_finds_known_roots() -> None:
    root = _brent_root(lambda u: u * u - 4.0, 0.0, 3.0)
    assert root == pytest.approx(2.0, abs=1e-9)
    # High dynamic range: root of x*1e6 - 1e-3 lies far from the bracket ends.
    root = _brent_root(lambda u: u * 1e6 - 1e-3, 0.0, 1.0)
    assert root == pytest.approx(1e-9, rel=1e-6)
    with pytest.raises(ValueError, match="not bracketed"):
        _brent_root(lambda u: u * u + 1.0, 0.0, 3.0)


def test_zero_partial_pressures_give_zero_loadings() -> None:
    co2, h2s = equilibrium_loadings(T_40C, C_JOU, 0.0, 0.0)
    assert co2 == 0.0
    assert h2s == 0.0


def test_lean_amine_floor_is_well_below_treating_specs() -> None:
    # A freshly loaded lean amine imposes only a tiny acid-gas floor on the gas.
    p_co2_floor, p_h2s_floor = equilibrium_partial_pressures(303.15, 4280.0, 0.005, 0.002)
    assert p_co2_floor / 6.5e6 * 100.0 < 0.1  # mol%
    assert p_h2s_floor / 6.5e6 * 1e6 < 1.0  # ppmv


def test_bottom_ceiling_covers_treating_service() -> None:
    # At the example bottom partial pressures (6% CO2, 1.5% H2S at 6.5 MPa)
    # the CO2 loading dominates and suppresses the H2S loading through the
    # shared proton capacity: CO2 alone would extrapolate past loading 0.6 on
    # the NeqSim isotherm (alpha=0.40 at 23.3 kPa), while H2S -- despite the
    # higher solubility of the weaker acid (JMO: alpha=0.453 at 36.9 kPa) --
    # is held near 0.17 by the competition. Both stay above the example rich
    # loadings (0.35 CO2 / 0.126 H2S) with working margin.
    max_co2, max_h2s = equilibrium_loadings(303.15, 4280.0, 0.06 * 6.5e6, 0.015 * 6.5e6)
    assert 0.6 < max_co2 < 1.1
    assert 0.1 < max_h2s < 0.3
    assert math.isfinite(max_co2)
