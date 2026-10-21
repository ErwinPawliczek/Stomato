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
    """Measured: 6.06 mol/s CO2 in, 0.00036 mol/s out with the gas - 99.99% removed.

    Re-recorded on the corrected solver: the previous 0.0489 mol/s slip rode a
    stage profile pinned at the 273.15 K band floor (frozen reactive K). The
    physical profile carries the absorption exotherm (stage bulge to 314 K,
    docstring of test_stage_temperatures_in_band) and the rich loading sits at
    ~0.502 mol/mol MDEA - the lean solvent's equilibrium capacity (~12 mol/s
    MDEA x 0.5) matches the CO2 feed, so near-total capture is the
    equilibrium-limited answer.
    """
    d = solved.outlets["distillate"]
    co2_out = d.molar_flow * d.composition.get("CO2", 0.0)
    # Review pin: CO2 slip below 1e-2 mol/s; the measured anchor is tighter.
    assert co2_out < 1e-2
    assert co2_out == pytest.approx(0.00036, abs=1e-3)


def test_rich_loading_in_range(solved: Any) -> None:
    """Measured rich liquid: x_MDEA=0.12765, x_CO2=0.06357 - loading 0.498 mol/mol,
    inside the MDEA 0-1 window."""
    b = solved.outlets["bottoms"]
    loading = b.composition.get("CO2", 0.0) / b.composition.get("MDEA", 1.0)
    # Review pin: rich loading in (0.45, 0.55); the measured anchor is tighter.
    assert 0.45 < loading < 0.55
    assert loading == pytest.approx(0.498, abs=0.02)


def test_stage_temperatures_in_band(solved: Any) -> None:
    """The absorption exotherm, pinned (review step 4).

    Measured on this branch: the stage profile carries the reactive exotherm -
    max stage 314.3 K against the 303.15 K lean inlet (rise 11.2 K, inside the
    spec's 0-30 K window) and the coldest stage 281.6 K, 21.6 K below the lean
    inlet (at most 25 K allowed). The old band-floor profile (max 299.29 K,
    rise -3.86 K, frozen reactive K) is gone; the physical bulge is restored.
    """
    ts = [solved.info[f"stage_{j}_T_K"] for j in range(20)]
    rise = max(ts) - 303.15
    assert 0.0 <= rise <= 30.0
    assert min(ts) > 303.15 - 25.0
