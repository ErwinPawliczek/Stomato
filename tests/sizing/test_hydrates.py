"""Tests for the hydrate-suppression correlations (Hammerschmidt, Nielsen-Bucklin)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.sizing.hydrates import hammerschmidt_formation, nielsen_bucklin_suppression

PA_PER_PSI = 6894.757293168


def test_hammerschmidt_published_example() -> None:
    """T = 8.9*P^0.285/(SG^0.249 - 0.28).

    Published worked example, citing GPSA: P = 1000 psia, SG = 0.65 gives
    ~102.6 degF with rounded hand arithmetic; the exact correlation value is
    103.0859 degF = 312.6422 K. Asserting to correlation-level rounding, not
    tighter than the source quote.
    """
    got = hammerschmidt_formation(P_Pa=1000.0 * PA_PER_PSI, gas_specific_gravity=0.65)
    T_F = got["T_hydrate_K"] * 9.0 / 5.0 - 459.67
    assert abs(T_F - 102.6) < 1.0


def test_formation_increases_with_pressure() -> None:
    """A hydrate curve is monotone in P at fixed gravity."""
    low = hammerschmidt_formation(P_Pa=1000.0 * PA_PER_PSI, gas_specific_gravity=0.65)["T_hydrate_K"]
    high = hammerschmidt_formation(P_Pa=1500.0 * PA_PER_PSI, gas_specific_gravity=0.65)["T_hydrate_K"]
    assert high > low


def test_nielsen_bucklin_published_anchor() -> None:
    """dT = -72*ln(1 - x_M), x_M the aqueous methanol mole fraction.

    Published anchor (Nielsen & Bucklin 1983; quoted in Nyvlt, "Solid-Liquid
    Phase Equilibria" p.229, and MDPI Crystals 8(6):124 eq. 2):
    x_M = 0.20 -> dT = 16.07 degC. The aqueous mass fraction that yields
    x_M = 0.20 for MeOH (M = 32.04 g/mol, water M = 18.015) is 0.30778098...
    """
    w = 0.3077809798270893  # solves x_M = (w/32.04)/((w/32.04) + (1-w)/18.015) = 0.2
    got = nielsen_bucklin_suppression(inhibitor_mass_fraction=w, inhibitor_molar_mass=32.04)
    assert math.isclose(got["x_M"], 0.2, rel_tol=1e-9)
    # Assert to the correlation's own quoted precision (0.01 degC), not tighter.
    assert math.isclose(got["dT_suppression_K"], 16.07, abs_tol=0.01)


def test_meg_inhibitor_runs_within_scope() -> None:
    """MEG (M = 62.068 g/mol) also evaluates through the same mole-fraction form."""
    got = nielsen_bucklin_suppression(inhibitor_mass_fraction=0.35, inhibitor_molar_mass=62.068)
    assert got["x_M"] == pytest.approx(0.135162, rel=1e-5)
    assert got["dT_suppression_K"] > 0


def test_first_golden_formation_case() -> None:
    """Case 0 of data/golden/hammerschmidt_formation.yaml, input-for-input."""
    got = hammerschmidt_formation(P_Pa=6894757.293168, gas_specific_gravity=0.65)
    assert math.isclose(got["T_hydrate_K"], 312.642189, rel_tol=1e-6)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"P_Pa": 0.0, "gas_specific_gravity": 0.65},
        {"P_Pa": -1000.0, "gas_specific_gravity": 0.65},
        {"P_Pa": 6894757.293168, "gas_specific_gravity": 0.0},
        {"P_Pa": 6894757.293168, "gas_specific_gravity": -0.65},
        # SG so light that SG**0.249 - 0.28 vanishes (correlation undefined).
        {"P_Pa": 6894757.293168, "gas_specific_gravity": 0.28 ** (1.0 / 0.249)},
    ],
)
def test_formation_invalid_inputs_raise(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        hammerschmidt_formation(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"inhibitor_mass_fraction": 0.0, "inhibitor_molar_mass": 32.04},
        {"inhibitor_mass_fraction": -0.1, "inhibitor_molar_mass": 32.04},
        {"inhibitor_mass_fraction": 1.0, "inhibitor_molar_mass": 32.04},
        {"inhibitor_mass_fraction": 0.30778, "inhibitor_molar_mass": 0.0},
        {"inhibitor_mass_fraction": 0.30778, "inhibitor_molar_mass": -32.04},
    ],
)
def test_suppression_invalid_inputs_raise(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        nielsen_bucklin_suppression(**kwargs)


def test_suppression_validity_limit_enforced() -> None:
    """x_M > 0.8 is outside the published validity and must raise at call time."""
    # w = 0.95 with M = 32.04 gives x_M ~ 0.915 > 0.8.
    with pytest.raises(ValueError, match="validity"):
        nielsen_bucklin_suppression(inhibitor_mass_fraction=0.95, inhibitor_molar_mass=32.04)


@pytest.mark.parametrize("name", ["hammerschmidt_formation", "nielsen_bucklin_suppression"])
def test_plugins_registered(name: str) -> None:
    """Both plugins are discoverable through the registry."""
    assert name in registry.available("correlation")
    assert registry.create("correlation", name) is not None
