"""AGA8 DC92 port tests (spec T-16a step 3).

The check values are the 16-digit values printed by NIST's public-domain
reference test ``AGA8CODE/C/Detail_test_01.cpp`` (usnistgov/AGA8 @
``3bdb9ab8ff317c618b0b59d1b704c2c86ddc5fce``) for the 21-component example gas
at 400 K / 50 000 kPa. The reference test's own tolerance is 1e-8 absolute;
this suite matches every value to its printed digits (measured max deviation
7e-12), so 1e-8 is kept as the assertion bound.
"""

from __future__ import annotations

import pytest

from ngdesign.thermo.aga8 import (
    Aga8Dc92Error,
    aga8_dc92_properties,
    dc92_species,
)

# Detail_test_01.cpp composition (C order 1..21).
_NIST_EXAMPLE_GAS = {
    "C1": 0.77824, "N2": 0.02, "CO2": 0.06, "C2": 0.08, "C3": 0.03,
    "IC4": 0.0015, "NC4": 0.003, "IC5": 0.0005, "NC5": 0.00165,
    "NC6": 0.00215, "NC7": 0.00088, "NC8": 0.00024, "NC9": 0.00015,
    "NC10": 0.00009, "H2": 0.004, "O2": 0.005, "CO": 0.002, "H2O": 0.0001,
    "H2S": 0.0025, "He": 0.007, "Ar": 0.001,
}

# (property, reference value from Detail_test_01.cpp / Detail.cpp main)
_CHECK_VALUES = [
    ("molar_mass", 20.54333051),
    ("molar_density", 12.80792403648801),
    ("z_factor", 1.173801364147326),
    ("internal_energy", -2739.134175817231),
    ("enthalpy", 1164.699096269404),
    ("entropy", -38.54882684677111),
    ("cv", 39.12076154430332),
    ("cp", 58.54617672380667),
    ("sound_speed", 712.6393684057903),
    ("gibbs", 16584.22983497785),
    ("joule_thomson", 7.432969304794577e-05),
    ("isentropic_exponent", 2.672509225184606),
]


@pytest.mark.parametrize(("prop", "expected"), _CHECK_VALUES)
def test_nist_check_values(prop: str, expected: float) -> None:
    """The port reproduces the NIST printed check values (1e-8 abs)."""
    r = aga8_dc92_properties(_NIST_EXAMPLE_GAS, 400.0, 50000.0)
    assert getattr(r, prop) == pytest.approx(expected, abs=1e-8)


def test_pressure_roundtrip() -> None:
    """The converged state reproduces the requested pressure (P = D*R*T*Z)."""
    r = aga8_dc92_properties(_NIST_EXAMPLE_GAS, 400.0, 50000.0)
    assert r.pressure == pytest.approx(50000.0, abs=1e-6)
    recomputed = r.molar_density * 8.31451 * 400.0 * r.z_factor
    assert recomputed == pytest.approx(r.pressure, rel=1e-12)


def test_species_count() -> None:
    assert len(set(dc92_species())) == 21


def test_refuses_component_outside_species_set() -> None:
    with pytest.raises(Aga8Dc92Error, match="MEOH"):
        aga8_dc92_properties({"MEOH": 1.0}, 300.0, 1000.0)


def test_refuses_multiple_root_state() -> None:
    """CO2 at 265 K below its vapour pressure: gas and dense roots coexist."""
    with pytest.raises(Aga8Dc92Error, match="multiple density roots"):
        aga8_dc92_properties({"CO2": 1.0}, 265.0, 3500.0)


def test_gas_state_matches_ideal_limit() -> None:
    """A near-vacuum gas state: Z is 1 within the second-virial correction."""
    r = aga8_dc92_properties({"C1": 1.0}, 400.0, 1.0)
    assert r.z_factor == pytest.approx(1.0, abs=2e-5)


def test_negative_fraction_refused() -> None:
    with pytest.raises(Aga8Dc92Error, match="negative mole fraction"):
        aga8_dc92_properties({"C1": 1.5, "C3": -0.5}, 300.0, 1000.0)


def test_empty_composition_refused() -> None:
    with pytest.raises(Aga8Dc92Error, match="empty"):
        aga8_dc92_properties({}, 300.0, 1000.0)


def test_composition_normalised() -> None:
    """Fractions not summing to one are normalised, not silently used."""
    r_exact = aga8_dc92_properties({"C1": 0.9, "C3": 0.1}, 300.0, 2000.0)
    r_off = aga8_dc92_properties({"C1": 0.81, "C3": 0.09}, 300.0, 2000.0)
    assert r_off.z_factor == pytest.approx(r_exact.z_factor, rel=1e-12)
    assert r_off.molar_mass == pytest.approx(r_exact.molar_mass, rel=1e-12)
    assert r_off.molar_density == pytest.approx(r_exact.molar_density, rel=1e-12)
