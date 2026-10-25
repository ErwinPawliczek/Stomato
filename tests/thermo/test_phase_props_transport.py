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
