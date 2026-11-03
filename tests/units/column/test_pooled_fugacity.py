"""Pooled-liquid stages read their liquid's own split (``_ThermoBox.k_pooled``).

The oracle is the full PT flash: at a converged pooled column every stage's
contents L x + V y flash back to the solved vapour y and the solved pooled
liquid x, and the pooled K the column reads (K_i = fhat_i / (xbar_i phi_i^V))
equals the flash's y_i / xbar_i on the same state. The fixed-phase-set reading
the FD Jacobian uses agrees with the full stability test off the window's
centre.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import Column
from ngdesign.units.column.thermo_adapter import _ThermoBox
from ngdesign.units.column_shortcut.three_phase_stages import ThreePhaseStages
from tests.conftest import flash_feed

#: Re-flash agreement on the converged example: the column gates M at 1e-8,
#: measured misses 4e-8 (y) and 1e-7 (pooled x); the flash-surface solve this
#: replaced missed by 5.7e-6.
_EQ_TOL = 1e-6


@pytest.fixture(scope="module")
def solved() -> tuple[Any, dict[str, float], list[str]]:
    thermo = registry.create("thermo", "pr")
    feeds, params = ThreePhaseStages.example_case()
    feed = flash_feed(thermo, feeds["feed"])
    result = Column().solve({"feed": feed}, {**params, "pool_liquids": True}, thermo)
    return thermo, result.info, sorted(feed.composition)


def _stage(info: dict[str, float], comps: list[str], j: int) -> tuple[dict[str, float], dict[str, float]]:
    x = {c: info.get(f"stage_{j}_x_{c}", 0.0) for c in comps}
    y = {c: info.get(f"stage_{j}_y_{c}", 0.0) for c in comps}
    return x, y


def test_every_stage_reflashes_to_the_solved_vapour_and_pooled_liquid(
    solved: tuple[Any, dict[str, float], list[str]],
) -> None:
    thermo, info, comps = solved
    two_liquid = 0
    for j in range(int(info["n_stages"])):
        x, y = _stage(info, comps, j)
        liquid, vapour = info[f"stage_{j}_L_mol_s"], info[f"stage_{j}_V_mol_s"]
        z = {c: (liquid * x[c] + vapour * y[c]) / (liquid + vapour) for c in comps}
        state = thermo.flash_pt(
            {c: v for c, v in z.items() if v > 0.0}, info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"], 1.0
        )
        vap = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
        liquids = [p for p in state.phases if p.kind != PhaseKind.VAPOR]
        two_liquid += len(liquids) == 2
        share = sum(p.mole_fraction for p in liquids)
        for c in comps:
            xbar = sum(p.mole_fraction * p.composition.get(c, 0.0) for p in liquids) / share
            assert vap.composition.get(c, 0.0) == pytest.approx(y[c], abs=_EQ_TOL), (j, c)
            assert xbar == pytest.approx(x[c], abs=_EQ_TOL), (j, c)
    assert two_liquid >= 3  # the example's wet stages do split


def test_pooled_k_is_the_flash_k_on_the_same_state(solved: tuple[Any, dict[str, float], list[str]]) -> None:
    thermo, info, comps = solved
    tb = _ThermoBox(thermo, 2.0e5, 2.0e5, pool_liquids=True)
    j = 1  # a two-liquid stage of the example
    x, y = _stage(info, comps, j)
    t, p = info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"]
    assert len(tb.pooled_split(tb._trace_normalized(x), t, p)) == 2
    k = tb.k_pooled(x, y, t, p)
    assert k is not None
    liquid, vapour = info[f"stage_{j}_L_mol_s"], info[f"stage_{j}_V_mol_s"]
    z = {c: (liquid * x[c] + vapour * y[c]) / (liquid + vapour) for c in comps}
    state = thermo.flash_pt(z, t, p, 1.0)
    vap = next(ph for ph in state.phases if ph.kind == PhaseKind.VAPOR)
    liquids = [ph for ph in state.phases if ph.kind != PhaseKind.VAPOR]
    share = sum(ph.mole_fraction for ph in liquids)
    for c in comps:
        xbar = sum(ph.mole_fraction * ph.composition[c] for ph in liquids) / share
        assert k[c] == pytest.approx(vap.composition[c] / xbar, rel=1e-5), c


def test_fixed_phase_set_reading_matches_the_full_test(
    solved: tuple[Any, dict[str, float], list[str]],
) -> None:
    thermo, info, comps = solved
    j = 1
    x, y = _stage(info, comps, j)
    t, p = info[f"stage_{j}_T_K"], info[f"stage_{j}_P_Pa"]
    full = _ThermoBox(thermo, p, p, pool_liquids=True)
    fixed = _ThermoBox(thermo, p, p, pool_liquids=True)
    fixed.k_pooled(x, y, t, p)  # the reference state, fully tested
    bumped = dict(x)
    bumped["nC6"] += 1e-8  # an FD-sized perturbation
    with fixed.fixed_phase_sets():
        k_fixed = fixed.k_pooled(bumped, y, t + 1e-5, p)
    k_full = full.k_pooled(bumped, y, t + 1e-5, p)
    assert k_fixed is not None and k_full is not None
    for c in comps:
        assert k_fixed[c] == pytest.approx(k_full[c], rel=1e-7), c
