"""Quantity arithmetic, offset-scale logic, basis changes and edge coercion."""

from __future__ import annotations

import numpy as np
import pytest

from ngdesign.uom.dimension import DimensionError, OffsetUnitError, UomError
from ngdesign.uom.quantity import Q, Quantity, coerce, convert, si_arguments
from ngdesign.uom.sets import display


def test_arithmetic_tracks_dimensions() -> None:
    power = Q(100, "kg/h") * Q(10, "kJ/kg")
    assert power.require("power").magnitude("W") == pytest.approx(100 / 3600 * 10_000)
    assert (Q(1, "m") / Q(1, "s")).require("velocity").si == 1.0
    assert (Q(4, "m2") ** 0.5).require("length").si == 2.0
    assert Q(4, "m2").sqrt().require("length").si == 2.0


def test_half_order_exponent_stays_exact() -> None:
    half = Q(1.0, "(mol/m3)^-0.5/s")
    assert (half * Q(1.0, "(mol/m3)^0.5")).require("frequency").si == 1.0


def test_adding_different_dimensions_is_refused() -> None:
    with pytest.raises(DimensionError):
        _ = Q(1, "m") + Q(1, "s")
    with pytest.raises(DimensionError):
        _ = Q(1, "kg") < Q(1, "m")


def test_dimensionless_quantity_converts_to_float_only_when_dimensionless() -> None:
    assert float(Q(50, "%")) == 0.5
    with pytest.raises(DimensionError):
        float(Q(1, "m"))


def test_two_temperature_points_cannot_be_added() -> None:
    with pytest.raises(OffsetUnitError):
        _ = Q(20, "degC") + Q(5, "degC")


def test_point_difference_is_an_interval_and_point_plus_interval_a_point() -> None:
    interval = Q(30, "degC") - Q(20, "degC")
    assert interval.si == pytest.approx(10.0)
    assert not interval.is_point
    point = Q(20, "degC") + Q(5, "delta_degC")
    assert point.is_point
    assert point.magnitude("degC") == pytest.approx(25.0)
    with pytest.raises(OffsetUnitError):
        _ = interval - Q(20, "degC")


def test_multiplying_an_absolute_temperature_uses_kelvin() -> None:
    # R·T with T read in degC must use 298.15 K, the classic offset trap.
    assert (Q(25, "degC") * Q(8.314, "J/(mol K)")).magnitude("J/mol") == pytest.approx(8.314 * 298.15)


def test_mass_mole_basis_needs_a_molar_mass() -> None:
    with pytest.raises(DimensionError, match="mw="):
        convert(100.0, "kg/h", "kmol/h")
    assert convert(100.0, "kg/h", "kmol/h", mw=20.0) == pytest.approx(5.0)
    assert convert(5.0, "kmol/h", "kg/h", mw=Q(20, "kg/kmol")) == pytest.approx(100.0)
    assert convert(1.0, "kJ/kg", "J/mol", mw=20.0) == pytest.approx(20.0)


def test_volume_bases_need_density() -> None:
    with pytest.raises(DimensionError, match="rho="):
        convert(1.0, "m3/h", "kg/h")
    assert convert(1.0, "m3/h", "kg/h", rho=800.0) == pytest.approx(800.0)
    assert convert(800.0, "kg/h", "m3/h", rho=Q(800, "kg/m3")) == pytest.approx(1.0)
    assert convert(1.0, "m3/h", "kmol/h", mw=20.0, rho=1000.0) == pytest.approx(50.0)


def test_wrong_supplied_carrier_dimension_is_refused() -> None:
    with pytest.raises(DimensionError):
        convert(100.0, "kg/h", "kmol/h", mw=Q(20, "kg/m3"))


def test_arrays_work_elementwise() -> None:
    temperatures = Q([0.0, 100.0], "degC")
    assert np.allclose(temperatures.magnitude("K"), [273.15, 373.15])
    assert np.allclose((np.array([2.0, 3.0]) * Q(1.0, "m")).si, [2.0, 3.0])


def test_quantity_is_immutable() -> None:
    with pytest.raises(AttributeError):
        Q(1, "m").si = 2.0


def test_format_and_string_constructor() -> None:
    assert f"{Q(1.5, 'bar'):.2f}" == "1.50 bar"
    assert Q("  1e3 kPa ").magnitude("MPa") == pytest.approx(1.0)
    assert Q("25.5").dimension == Q(1).dimension
    with pytest.raises(UomError):
        Q("no number here")
    with pytest.raises(UomError):
        Q("1 m", "m")


def test_coerce_at_the_edge() -> None:
    assert coerce("25 degC", "temperature") == pytest.approx(298.15)
    assert coerce(Q(1, "atm"), "pressure") == 101325.0
    assert coerce(350.0, "temperature") == 350.0
    with pytest.raises(DimensionError):
        coerce("1 bar", "temperature")
    with pytest.raises(UomError):
        coerce(1.0, "not_a_kind")


def test_si_arguments_decorator_coerces_and_checks() -> None:
    @si_arguments(T="temperature", P="pressure")
    def ideal_density(T: float, P: float, mw: float = 28.0) -> float:
        return P * mw * 1e-3 / (8.314 * T)

    assert ideal_density("25 degC", P="1 atm") == pytest.approx(ideal_density(298.15, 101325.0))
    with pytest.raises(DimensionError):
        ideal_density("1 bar", 1e5)


def test_display_sets() -> None:
    assert display(298.15, "temperature", "METRIC").magnitude() == pytest.approx(25.0)
    assert display(101325.0, "pressure", "FIELD").unit == "psia"
    with pytest.raises(UomError):
        display(1.0, "pressure", "CGS")
    with pytest.raises(UomError):
        display(1.0, "voltage", "SI")


def test_from_si_round_trips_engine_output() -> None:
    q = Quantity.from_si(4.5e5, "pressure").to("bar")
    assert q.magnitude() == pytest.approx(4.5)
    assert q.isclose(Q("450 kPa"))


def test_a_difference_has_no_reading_on_an_offset_scale() -> None:
    """Regression: a 50 K difference read as -369.67 degF."""
    difference = Q(70, "degC") - Q(20, "degC")
    assert difference.magnitude("delta_degF") == pytest.approx(90.0)
    with pytest.raises(OffsetUnitError):
        difference.to("degF")
    with pytest.raises(OffsetUnitError):
        Q(5, "delta_degC").magnitude("degC")


def test_kelvin_still_reads_on_celsius() -> None:
    assert Q(300, "K").magnitude("degC") == pytest.approx(26.85)


def test_a_scale_point_is_not_a_temperature_difference() -> None:
    assert coerce("10 K", "temperature_difference") == 10.0
    assert coerce("10 delta_degC", "temperature_difference") == 10.0
    with pytest.raises(OffsetUnitError):
        coerce("10 degC", "temperature_difference")
