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


# One xdist worker runs the whole module (``--dist loadgroup`` in pyproject.toml), so the
# module-scoped solve below is paid once per CI run, not once per worker.
pytestmark = pytest.mark.xdist_group("column_amine")


# Module scope: the fixture's one mesh solve (~35 s carrier / ~120 s exothermic
# continuation) is deterministic, so the four assertions below share a single
# converged solution instead of paying four solves. The explicit timeout marker
# accommodates the continuation solve's wall time against the suite-wide
# pytest-timeout=120 in pyproject.toml.
@pytest.fixture(name="solved", scope="module")
def _solved() -> Any:
    return _COL.solve({"feed": _amine_case()[0]}, _amine_case()[1], get("thermo", "amine_ke")())


# P1-11 step 3 (ruling on issue #153): the exact gate reads y = K(T, x) * x from the
# live package for EVERY package - one definition of "converged". The P1-09 accepted
# absorber state was anchor-consistent, not equilibrium-consistent: the same state
# reads M = 1.13e-2, H = 2.67e-3 under the honest gate (measured) against the
# 1e-2 / 1e-2 gates, so the mesh raised ColumnConvergenceError.
#
# P1-11 R1 (ruling on #153, 2026-10-23): the exothermic van 't Hoff reference ships
# as the package default (_heat_scale = 1.0). The mesh closes it cold through the
# generic heat-of-reaction continuation in _solve_mesh (scales 0.0 -> 1.0, warm-
# chained), after the exact-residual NS alignment (pass-frozen refreshed y = K*x
# trial seeds). Measured closure: max_T 304.34 K (+1.19 K exotherm rise), CO2 slip
# 8.9068e-6 mol/s, rich loading 0.5021. The balance, absorption, loading and
# temperature-band assertions run unmarked against the converged state; the band
# test's deferred physics question is resolved by the R1 ruling (exothermic is the
# shipped reference, the equilibrium-consistent profile carries a small positive
# exotherm).


@pytest.mark.timeout(600)
def test_boundary_balance_closes(solved: Any) -> None:
    """Boundary balance over the real feed and outlet streams.

    Measured on the converged state (P1-11 R1): total closure exact, worst
    component C3 at 1.13e-11 relative on a 192 mol/s feed. The 1e-6 relative
    bound is the honest-gate acceptance criterion.
    """
    port, params = _amine_case()
    feed_total = port.molar_flow + sum(f["molar_flow"] for f in params["feeds"])
    out_total = sum(s.molar_flow for s in solved.outlets.values())
    assert abs(out_total - feed_total) / feed_total < 1e-6
    # Per-component closure: the gas feed lives on the StreamState port, the
    # lean solvent in the params feed dictionaries - read the two separately.
    feed_comp: dict[str, float] = {}
    for cid, x in port.composition.items():
        feed_comp[cid] = feed_comp.get(cid, 0.0) + x * port.molar_flow
    for f in params["feeds"]:
        for cid, x in f["composition"].items():
            feed_comp[cid] = feed_comp.get(cid, 0.0) + x * f["molar_flow"]
    out_comp: dict[str, float] = {}
    for s in solved.outlets.values():
        for cid, x in s.composition.items():
            out_comp[cid] = out_comp.get(cid, 0.0) + x * s.molar_flow
    for cid, flow in feed_comp.items():
        got = out_comp.get(cid, 0.0)
        assert abs(got - flow) / max(flow, 1e-12) < 1e-6, cid


@pytest.mark.timeout(600)
def test_co2_is_absorbed(solved: Any) -> None:
    """Measured on the converged state (R1 exothermic reference): CO2 slip
    8.9068e-6 mol/s with the gas.

    The old 0.0489 mol/s slip rode a stage profile pinned at the 273.15 K band
    floor (frozen reactive K). The physical profile carries the absorption
    exotherm and the rich loading sits at 0.5021 mol/mol MDEA - the lean
    solvent's equilibrium capacity (~12 mol/s MDEA x 0.5) matches the CO2
    feed, so near-total capture is the equilibrium-limited answer.
    """
    d = solved.outlets["distillate"]
    co2_out = d.molar_flow * d.composition.get("CO2", 0.0)
    # Review pin: CO2 slip below 1e-2 mol/s; the measured anchor is tighter.
    assert co2_out < 1e-2
    assert co2_out == pytest.approx(8.9068e-6, rel=0.05)


@pytest.mark.timeout(600)
def test_rich_loading_in_range(solved: Any) -> None:
    """Measured on the converged state: rich loading 0.5021 mol/mol MDEA,
    inside the MDEA 0-1 window and the solvent's equilibrium capacity."""
    b = solved.outlets["bottoms"]
    loading = b.composition.get("CO2", 0.0) / b.composition.get("MDEA", 1.0)
    # Review pin: rich loading in (0.45, 0.55); the measured anchor is tighter.
    assert 0.45 < loading < 0.55
    assert loading == pytest.approx(0.5021, abs=0.005)


@pytest.mark.timeout(600)
def test_stage_temperatures_in_band(solved: Any) -> None:
    """The absorption exotherm, pinned (review step 4).

    Measured on the CONVERGED state (P1-11 R1): max stage 304.34 K, a +1.19 K
    rise against the 303.15 K lean inlet - inside the spec's 0-30 K exotherm
    window. The pre-closure state carried a 314.3 K bulge (rise 11.2 K) but
    read M = 1.13e-2 under the honest equilibrium-consistent gate, i.e. it was
    not a converged state; the earlier carrier-reference closure sat at
    -0.20 K because the carrier sign removes the exotherm. The R1 ruling
    (issue #153, 2026-10-23) ships the exothermic reference, so the small
    positive rise is the equilibrium-consistent answer.
    """
    ts = [solved.info[f"stage_{j}_T_K"] for j in range(20)]
    rise = max(ts) - 303.15
    assert 0.0 <= rise <= 30.0
    assert min(ts) > 303.15 - 25.0
