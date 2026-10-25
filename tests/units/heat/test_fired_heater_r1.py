"""Closed-form tests for fired_heater R1 (specs/backend/units/fired_heater.md).

All expected numbers are hand-computed from the spec's equations, independent
of the implementation:

Test 1 (stoichiometry, methane, 15% excess, air 0.79/0.21): methane is CH4, so
C = 1, H = 4, O2_th = 1 + 4/4 = 2 mol/mol fuel. Air = (1 + 0.15)*2/0.21 =
2.3/0.21 = 10.95238095238... mol; air N2 = 0.79*that = 8.65238095238... mol.
Flue per mol fuel: CO2 1 + H2O 2 + O2 0.15*2 = 0.3 + N2 8.65238095238 = 11.95238095238
mol total, giving y_CO2 = 1/11.95238095238 = 0.08366533865, y_H2O = 2/... =
0.16733067729, y_O2 = 0.3/... = 0.02509960159, y_N2 = 8.65238095238/... =
0.72390438247.

Test 2 (Lobo-Evans): radiation = 5.670374419e-8 * 60 * 0.6 * (1100^4 - 650^4)
= 5.670374419e-8 * 36 * 1.28559375e12 = 2624327.25 W (exact product of the
typed decimals: 36 * 1.28559375e12 = 4.6281375e13; times 5.670374419e-8 =
2624327.2499...); convection = 11.36 * 200 * (1100 - 650) = 1022400.0 W
(exact); Q_R = 3646727.25 W; mean flux = 3646727.25/200 = 18233.63625 W/m2.

Test 3 (unit conversion): 2 Btu/(h ft2 degF) = 2 * 1055.05585262 J / (3600 s *
0.3048^2 m2 * 5/9 K) = 11.35652668... W/(m2 K); the module default constant
11.3565267 is that value rounded to 8 significant figures.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.units.heat.fired_heater_r1 import (
    H_CONV_RADIANT_DEFAULT,
    FiredHeaterSpecError,
    btu_h_ft2_f_to_w_m2_k,
    combustion_stoichiometry,
    radiant_transfer_W,
    validate_params,
)


def test_stoichiometry_methane_15pct_excess() -> None:
    """Hand-computed above (docstring): closed-form test 1, rel 1e-8."""
    result = combustion_stoichiometry({"C1": 1.0}, {"N2": 0.79, "O2": 0.21}, excess_air_frac=0.15)
    assert result["O2_th"] == pytest.approx(2.0, rel=1e-12)
    assert result["nu_air"] == pytest.approx(10.95238095238095, rel=1e-8)
    assert result["nu_fg"] == pytest.approx(11.95238095238095, rel=1e-8)
    flue: dict[str, float] = result["flue"]
    total = sum(flue.values())
    assert total == pytest.approx(result["nu_fg"], rel=1e-12)
    assert flue["CO2"] == pytest.approx(1.0, rel=1e-12)
    assert flue["H2O"] == pytest.approx(2.0, rel=1e-12)
    assert flue["O2"] == pytest.approx(0.3, rel=1e-12)
    assert flue["N2"] == pytest.approx(8.65238095238095, rel=1e-8)
    for species, expected_y in (
        ("CO2", 0.08366533865),
        ("H2O", 0.16733067729),
        ("O2", 0.02509960159),
        ("N2", 0.72390438247),
    ):
        assert flue[species] / total == pytest.approx(expected_y, rel=1e-8)


def test_lobo_evans_radiant_transfer() -> None:
    """Hand-computed above (docstring): closed-form test 2, rel 1e-9."""
    q_radiation, q_convection = radiant_transfer_W(
        alpha_Acp_m2=60.0,
        exchange_factor=0.6,
        T_g=1100.0,
        T_t=650.0,
        tube_area_m2=200.0,
        h_conv=11.36,
    )
    assert q_radiation == pytest.approx(2624327.25, rel=1e-9)
    assert q_convection == pytest.approx(1022400.0, rel=1e-9)
    q_total = q_radiation + q_convection
    assert q_total == pytest.approx(3646727.25, rel=1e-9)
    assert q_total / 200.0 == pytest.approx(18233.63625, rel=1e-9)


def test_btu_conversion_is_the_h_conv_default() -> None:
    """Hand-computed above (docstring): closed-form test 3; the default h_c is
    the Lobo-Evans 2 Btu/(h ft2 degF)."""
    converted = btu_h_ft2_f_to_w_m2_k(2.0)
    assert converted == pytest.approx(11.3565267, rel=1e-7)
    assert H_CONV_RADIANT_DEFAULT == pytest.approx(converted, rel=1e-7)


def _base_params(**overrides: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "T_out": 600.0,
        "dP": 1.0e4,
        "fuel_composition": {"C1": 1.0},
        "excess_air_frac": 0.15,
        "alpha_Acp_m2": 60.0,
        "exchange_factor": 0.6,
        "tube_area_radiant_m2": 200.0,
        "tube_wall_excess_K": 100.0,
        "UA_convection_W_K": 300.0,
    }
    params.update(overrides)
    return params


def test_fuel_composition_required_at_r1() -> None:
    params = _base_params()
    del params["fuel_composition"]
    with pytest.raises(FiredHeaterSpecError, match="fuel_composition"):
        validate_params(params)


@pytest.mark.parametrize(
    "name", ["alpha_Acp_m2", "exchange_factor", "tube_area_radiant_m2", "UA_convection_W_K"]
)
def test_geometry_params_required_and_positive(name: str) -> None:
    for bad in (None, 0.0, -1.0):
        params = _base_params()
        if bad is None:
            del params[name]
        else:
            params[name] = bad
        with pytest.raises(FiredHeaterSpecError, match=name):
            validate_params(params)


def test_exchange_factor_above_one_refused() -> None:
    with pytest.raises(FiredHeaterSpecError, match="exchange_factor"):
        validate_params(_base_params(exchange_factor=1.01))


def test_negative_excess_air_refused() -> None:
    with pytest.raises(FiredHeaterSpecError, match="excess_air_frac"):
        validate_params(_base_params(excess_air_frac=-0.01))


@pytest.mark.parametrize("bad", [-0.01, 0.5])
def test_radiant_loss_frac_out_of_band_refused(bad: float) -> None:
    with pytest.raises(FiredHeaterSpecError, match="radiant_loss_frac"):
        validate_params(_base_params(radiant_loss_frac=bad))
