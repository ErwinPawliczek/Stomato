"""phase_props carries transport properties (a directly built phase keeps its correlations).

Reference values are handbook data at 300 K, not model outputs: water
mu = 0.8538 mPa·s, k = 0.6103 W/(m K) (IAPWS 2008 viscosity and IAPWS 2011
conductivity formulations, as tabulated in Incropera 7th ed. Table A.6);
N2 at 1 atm mu = 17.89 µPa·s, k = 0.0259 W/(m K) (Incropera Table A.4).
Tolerances cover the correlations' stated accuracy, a few percent.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind


def test_liquid_water_transport_properties() -> None:
    props = registry.create("thermo", "pr").phase_props({"H2O": 1.0}, 300.0, 2.0e5, PhaseKind.AQUEOUS)
    assert props.viscosity == pytest.approx(0.8538e-3, rel=0.03)
    assert props.thermal_conductivity == pytest.approx(0.6103, rel=0.03)


def test_nitrogen_gas_transport_properties() -> None:
    props = registry.create("thermo", "pr").phase_props({"N2": 1.0}, 300.0, 101_325.0, PhaseKind.VAPOR)
    assert props.viscosity == pytest.approx(17.89e-6, rel=0.03)
    assert props.thermal_conductivity == pytest.approx(0.0259, rel=0.03)


def test_a_dissolved_gas_does_not_collapse_liquid_conductivity() -> None:
    """Regression: 10 mol% methane in liquid n-butane gave 5.8e-4 W/(m K).

    Methane is supercritical at 280 K and its pure-liquid fit extrapolated to its floor,
    which DIPPR 9H's inverse square let dominate. Dilute supercritical components are now
    left out of the rule; a liquid with more of them refuses. Subcritical ones are kept.
    """
    from ngdesign import registry
    from ngdesign.contracts.stream import PhaseKind

    package = registry.create("thermo", "pr")
    pure = package.phase_props({"nC4": 1.0}, 280.0, 2e6, PhaseKind.HC_LIQUID).thermal_conductivity
    dilute = package.phase_props(
        {"C1": 0.1, "nC4": 0.9}, 280.0, 2e6, PhaseKind.HC_LIQUID
    ).thermal_conductivity
    assert pure is not None and dilute is not None
    assert dilute == pytest.approx(pure, rel=0.02)
    rich = package.phase_props({"C1": 0.3, "nC4": 0.7}, 280.0, 2e6, PhaseKind.HC_LIQUID).thermal_conductivity
    assert rich is None


def test_a_subcritical_component_past_its_fit_keeps_its_value() -> None:
    """Propane at 340 K is below its 369.8 K critical point: still a liquid, still counted."""
    from ngdesign import registry
    from ngdesign.contracts.stream import PhaseKind

    package = registry.create("thermo", "pr")
    k = package.phase_props({"C3": 0.5, "nC4": 0.5}, 340.0, 1.2e6, PhaseKind.HC_LIQUID).thermal_conductivity
    assert k is not None and 0.05 < k < 0.15
