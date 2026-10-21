"""P1-09 amine thermo additions: the typed chemistry-window error (spec E2) and
the solvent-lean reactive flash convergence (spec E1)."""

from __future__ import annotations

import pytest

from ngdesign.amine.package import AmineChemistryError, AmineKEPackage
from ngdesign.registry import get


@pytest.fixture(name="ke")
def _ke() -> AmineKEPackage:
    ke: AmineKEPackage = get("thermo", "amine_ke")()
    return ke


def test_chemistry_error_is_value_error() -> None:
    """Spec E2: the typed error extends ValueError, so existing callers keep
    their ValueError handling."""
    assert issubclass(AmineChemistryError, ValueError)


def test_chemistry_window_error_names_temperature_and_bracket(ke: AmineKEPackage) -> None:
    """Spec E2: a state outside the fitted chemistry window raises the typed
    error carrying T and the speciation bracket, never a bare bracketing
    failure from the root finders."""
    # 77 K is far below any fitted Kent-Eisenberg window for MDEA: the
    # charge-balance root find leaves its bracket and surfaces typed.
    z = {"MDEA": 0.30, "H2O": 0.68, "CO2": 0.02}
    with pytest.raises(AmineChemistryError, match=r"T=77.*speciation bracket"):
        ke.equilibrium_pressures(z, 77.0, 0.5, 0.0)


def test_solvent_lean_vapour_flash_delegates(ke: AmineKEPackage) -> None:
    """Spec E1: trace-amine vapour states delegate to the carrier thermo instead
    of failing the reactive equilibrium solve, and the flash returns a valid
    stream state."""
    st = ke.flash_pt({"C1": 1.0 - 1e-7, "MDEA": 1e-7}, 303.15, 6.5e6, 100.0)
    assert st.molar_flow == pytest.approx(100.0)


def test_rich_liquid_flash_converges(ke: AmineKEPackage) -> None:
    """Spec E1: a solvent-rich liquid overall (the exact example lean solvent)
    converges its internal equilibrium with the 1e-12 tolerance and returns a
    physically ordered state."""
    z = {"MDEA": 0.2422, "H2O": 0.7496, "CO2": 0.0082}
    st = ke.flash_pt(z, 303.15, 6.5e6, 92.0)
    assert st.molar_flow == pytest.approx(92.0)
    assert 250.0 < st.T < 400.0
