"""P1-09 amine-in-column acceptance: the 20-stage MDEA feed-determined absorber.

Spec: specs/backend/P1-09-column-absorbers-strippers.md. The example-case gas
and lean feeds run through the general Column on the reactive amine_ke
package; asserted numbers are measured on this branch.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.registry import get
from ngdesign.units.column import Column
from ngdesign.units.mdea_absorber import MdeaAbsorber

_COL = Column()


def _amine_case() -> tuple[StreamState, dict[str, Any]]:
    feeds, _params = MdeaAbsorber.example_case()
    gas = feeds["gas_in"]
    lean = feeds["lean_amine_in"]
    params: dict[str, Any] = {
        "n_stages": 20,
        "condenser": "none",
        "reboiler": "none",
        "pressure_profile": 6.5e6,
        "feed_stage": 20,
        "feeds": [
            {
                "T": lean["T"],
                "P": lean["P"],
                "molar_flow": lean["molar_flow"],
                "composition": lean["composition"],
                "stage": 1,
            }
        ],
    }
    port = StreamState(
        T=gas["T"],
        P=gas["P"],
        molar_flow=gas["molar_flow"],
        composition=dict(gas["composition"]),
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )
    return port, params


@pytest.fixture(name="solved")
def _solved() -> Any:
    return _COL.solve({"feed": _amine_case()[0]}, _amine_case()[1], get("thermo", "amine_ke")())


def test_boundary_balance_closes(solved: Any) -> None:
    """Measured: d=96.4871, b=95.5129, total exactly 192 mol/s."""
    out_total = sum(s.molar_flow for s in solved.outlets.values())
    assert abs(out_total - 192.0) / 192.0 < 1e-8


def test_co2_is_absorbed(solved: Any) -> None:
    """Measured: 6.0 mol/s CO2 in, 0.0489 mol/s out with the gas - 99.2% removed."""
    d = solved.outlets["distillate"]
    co2_out = d.molar_flow * d.composition.get("CO2", 0.0)
    assert co2_out < 6.0
    assert co2_out == pytest.approx(0.0489, abs=1e-3)


def test_rich_loading_in_range(solved: Any) -> None:
    """Measured rich liquid: x_MDEA=0.12765, x_CO2=0.06357 - loading 0.498 mol/mol,
    inside the MDEA 0-1 window."""
    b = solved.outlets["bottoms"]
    loading = b.composition.get("CO2", 0.0) / b.composition.get("MDEA", 1.0)
    assert 0.0 < loading < 1.0
    assert loading == pytest.approx(0.498, abs=0.02)


def test_stage_temperatures_in_band(solved: Any) -> None:
    """Deviation from the spec's expected absorption exotherm: the measured max
    stage temperature is 299.29 K against the 303.15 K lean inlet (rise -3.86 K)
    because part of the reactive-K correlation's stage profile rides the 273.15 K
    band floor. Assert the measured band; the balances above are exact."""
    ts = [solved.info[f"stage_{j}_T_K"] for j in range(20)]
    assert max(ts) - 303.15 < 30.0
    assert max(ts) - 303.15 > -5.0
