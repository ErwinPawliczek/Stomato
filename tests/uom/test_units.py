"""Unit parsing and conversion, against exact definitions (NIST SP 811 Appendix B)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ngdesign.uom.dimension import KINDS, DimensionError, UnknownUnitError, kind_dimension
from ngdesign.uom.quantity import Q, convert
from ngdesign.uom.sets import UNIT_SETS
from ngdesign.uom.units import parse_unit


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (1.0, "atm", "Pa", 101325.0),  # defined
        (1.0, "bar", "Pa", 1e5),  # defined
        (1.0, "lb", "kg", 0.45359237),  # international pound, exact
        (1.0, "in", "mm", 25.4),  # international inch, exact
        (1.0, "ft", "m", 0.3048),  # exact
        (1.0, "gal", "in3", 231.0),  # US gallon, exact
        (1.0, "bbl", "gal", 42.0),  # oil barrel, exact
        (1.0, "cal", "J", 4.184),  # thermochemical calorie, exact
        (1.0, "kWh", "MJ", 3.6),  # exact
        (1.0, "atm", "torr", 760.0),  # exact
        (1.0, "cP", "mPa s", 1.0),  # exact
        (1.0, "cSt", "mm2/s", 1.0),  # exact
        (1.0, "lbmol", "mol", 453.59237),  # exact
        (1.0, "h", "s", 3600.0),
        (1.0, "M", "mol/m3", 1000.0),
        (1.0, "mol L-1 s-1", "mol/(m3 s)", 1000.0),
        (1.0, "J/(mol K)", "J/mol/K", 1.0),
        (1.0, "kg·m/s²", "N", 1.0),
        (1.0, "kg m/s2", "N", 1.0),
        (1.0, "W/m2 K", "W/(m2 K)", 1.0),
        (5.0, "%", "1", 0.05),
        (1.0, "1/s", "s-1", 1.0),
        (1.0, "m^3/h", "m**3/h", 1.0),
        (1.0, "m³/h", "m3/h", 1.0),
        (1.0, "s⁻¹", "1/s", 1.0),
    ],
)
def test_exact_definitions(value: float, source: str, target: str, expected: float) -> None:
    assert convert(value, source, target) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (0.0, "degC", "K", 273.15),
        (100.0, "degC", "degF", 212.0),
        (32.0, "degF", "K", 273.15),
        (-40.0, "degF", "degC", -40.0),
        (0.0, "degF", "degR", 459.67),
        (0.0, "barg", "Pa", 101325.0),
        (0.0, "psig", "atm", 1.0),
        (0.0, "psig", "kPag", 0.0),
        (500.0, "psia", "psig", 500.0 - 101325.0 / 6894.757293168361),
    ],
)
def test_offset_scales(value: float, source: str, target: str, expected: float) -> None:
    assert convert(value, source, target) == pytest.approx(expected, abs=1e-9)


def test_offset_unit_inside_a_compound_is_an_interval() -> None:
    # 1 Btu(IT)/(lb degF) = 4.1868 kJ/(kg K): the factor is exact by the IT calorie definition.
    assert convert(1.0, "Btu/lb-degF", "kJ/(kg K)") == pytest.approx(4.1868, rel=1e-12)
    assert convert(1.0, "degC/min", "K/s") == pytest.approx(1.0 / 60.0)


def test_standard_gas_volumes_are_ideal_gas_amounts() -> None:
    # n/V = P/(RT): 1 Nm3 is 44.6 mol, and the lbmol molar volume at 60 degF and 14.696
    # psia that the repo's units/_examples.py constant (379.49 ft3/lbmol) quotes.
    assert convert(1.0, "Nm3", "mol") == pytest.approx(101325.0 / (8.314462618 * 273.15), rel=1e-9)
    assert 1e0 / convert(1.0, "scf", "lbmol") == pytest.approx(379.49, rel=2e-4)
    assert convert(1.0, "MMSCFD", "mol/s") == pytest.approx(1e6 * convert(1.0, "scf", "mol") / 86400.0)


def test_si_prefixes_do_not_shadow_named_units() -> None:
    assert parse_unit("min").factor == 60.0  # not milli-inch
    assert parse_unit("h").factor == 3600.0
    assert parse_unit("kPa").factor == 1000.0
    assert parse_unit("mol").factor == 1.0
    assert parse_unit("mmol").factor == pytest.approx(1e-3)
    assert parse_unit("MPa").factor == 1e6
    assert parse_unit("µg").factor == pytest.approx(1e-9)
    assert parse_unit("Mt").factor == 1e9  # megatonne


@pytest.mark.parametrize("name", ["F", "C", "R"])
def test_ambiguous_symbols_are_refused_with_guidance(name: str) -> None:
    with pytest.raises(UnknownUnitError, match="ambiguous"):
        parse_unit(name)


@pytest.mark.parametrize("bad", ["furlong", "kg/", "m/(s", "m)", "kg^", "@", "3.5.2"])
def test_garbage_is_refused(bad: str) -> None:
    with pytest.raises(UnknownUnitError):
        parse_unit(bad)


@pytest.mark.parametrize(
    ("source", "target"), [("kg", "m"), ("psia", "K"), ("J/mol", "J/kg"), ("m3", "kg"), ("kg/h", "kmol/h")]
)
def test_dimension_mismatch_is_refused(source: str, target: str) -> None:
    with pytest.raises(DimensionError):
        convert(1.0, source, target)


def test_every_unit_set_entry_matches_its_kind() -> None:
    for name, table in UNIT_SETS.items():
        for kind, unit in table.items():
            assert parse_unit(unit).dimension == kind_dimension(kind), f"{name}: {kind} -> {unit}"


def test_unit_sets_cover_the_same_kinds() -> None:
    assert set(UNIT_SETS["SI"]) == set(UNIT_SETS["METRIC"]) == set(UNIT_SETS["FIELD"])
    assert set(UNIT_SETS["SI"]) <= set(KINDS)


_LINEAR = ["Pa", "psia", "bar", "atm", "kPa", "mmHg", "inH2O"]
_THERMAL = ["K", "degC", "degF", "degR"]
_finite = st.floats(min_value=1e-6, max_value=1e9, allow_nan=False)


@given(_finite, st.sampled_from(_LINEAR), st.sampled_from(_LINEAR))
def test_pressure_round_trip(value: float, a: str, b: str) -> None:
    assert convert(convert(value, a, b), b, a) == pytest.approx(value, rel=1e-9)


@given(_finite, st.sampled_from(_THERMAL), st.sampled_from(_THERMAL))
def test_temperature_round_trip(value: float, a: str, b: str) -> None:
    assert convert(convert(value, a, b), b, a) == pytest.approx(value, rel=1e-9, abs=1e-6)


@given(_finite)
def test_quantity_string_form_matches_constructor(value: float) -> None:
    assert Q(f"{value!r} kPa").si == pytest.approx(Q(value, "kPa").si)


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [
        (1.0, "Btu/lb·degF", "kJ/(kg K)", 4.1868),
        (1.0, "W/m²·K", "W/(m2 K)", 1.0),
        (1.0, "J/kg·K", "J/(kg K)", 1.0),
        (1.0, "m/s-1.5", "m s^1.5", 1.0),
        (4.0, "m^1/2", "(m)^0.5", 4.0),
        (1.0, "(m/s)2", "m2/s2", 1.0),
    ],
)
def test_review_regressions(value: float, source: str, target: str, expected: float) -> None:
    assert convert(value, source, target) == pytest.approx(expected, rel=1e-12)


def test_star_after_a_slash_is_refused_as_ambiguous() -> None:
    with pytest.raises(UnknownUnitError, match="ambiguous"):
        parse_unit("J/mol*K")


def test_a_bare_number_inside_a_unit_is_refused() -> None:
    with pytest.raises(UnknownUnitError):
        parse_unit("kg 2 m")


def test_parenthesised_offset_unit_stays_a_scale() -> None:
    assert convert(25.0, "(degC)", "K") == pytest.approx(298.15)
