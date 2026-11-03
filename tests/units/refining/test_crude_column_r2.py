"""crude_column R2: the steam-stripped atmospheric column over the stage graph.

One solve of the catalogue example (the 16-cut light crude, 12 stages, three
3-stage steam strippers, pooled stage liquids) backs the closure, product and
equilibrium checks; the refusals are spec errors raised before any solve.
The equilibrium oracle is the package's full PT flash: every stage's contents
L x + V y flash back to the solved vapour and pooled liquid.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.refining._cuts import RefiningSpecError
from ngdesign.units.refining.crude_column_r2 import CrudeColumnR2
from tests.conftest import flash_feed

#: One worker solves the example once for every test that reads it.
pytestmark = pytest.mark.xdist_group("crude_column_r2")

#: Closure tolerance (relative to the condenser duty / the feed flow).
_CLOSE = 1e-6
#: Re-flash agreement on the converged column (the graph gate is M 1e-6).
_EQ_TOL = 1e-5


@pytest.fixture(scope="module")
def solved() -> tuple[Any, dict[str, Any], Any]:
    thermo = registry.create("thermo", "pr")
    feeds, params = CrudeColumnR2.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = registry.create("unit", "crude_column").solve(inlets, {**params, "model": "R2"}, thermo)
    return thermo, inlets, result


def test_example_closes_components_and_energy_without_a_phantom_duty(
    solved: tuple[Any, dict[str, Any], Any],
) -> None:
    _, inlets, result = solved
    flow_in: dict[str, float] = {}
    for s in inlets.values():
        for c, n in s.component_flows().items():
            flow_in[c] = flow_in.get(c, 0.0) + n
    flow_out: dict[str, float] = {}
    for s in result.outlets.values():
        for c, n in s.component_flows().items():
            flow_out[c] = flow_out.get(c, 0.0) + n
    total = sum(flow_in.values())
    for c in set(flow_in) | set(flow_out):
        assert flow_out.get(c, 0.0) == pytest.approx(flow_in.get(c, 0.0), abs=_CLOSE * total), c
    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    condenser = result.info["condenser_duty_W"]
    assert h_in + result.duty_W == pytest.approx(h_out, abs=_CLOSE * abs(condenser))
    # No reboiler: the stage balances and the boundary closure agree (the
    # one-liquid model reported -66 kW here).
    assert abs(result.info["closure_residual_W"]) < _CLOSE * abs(condenser)
    assert result.duty_W == pytest.approx(-condenser, abs=_CLOSE * abs(condenser))


def test_products_meet_their_specs_and_order_by_volatility(solved: tuple[Any, dict[str, Any], Any]) -> None:
    _, _, result = solved
    _, params = CrudeColumnR2.example_case()
    out = result.outlets
    assert out["overhead"].molar_flow == pytest.approx(params["distillate_rate_mol_s"], rel=1e-9)
    for port in ("kero_out", "diesel_out", "ago_out"):
        assert out[port].molar_flow == pytest.approx(
            params["strippers"][port]["product_rate_mol_s"], rel=1e-9
        )
    temps = [out[p].T for p in ("overhead", "kero_out", "diesel_out", "ago_out", "bottoms")]
    assert temps == sorted(temps)
    assert out["overhead"].vapor_fraction == 1.0
    # The reduced crude leaves as the pooled liquid: two liquids on the PR package.
    assert len([p for p in out["bottoms"].phases if p.kind != PhaseKind.VAPOR]) == 2
    assert 0.0 < result.info["overflash_frac"] < 0.1


def test_every_stage_reflashes_to_its_solved_vapour_and_pooled_liquid(
    solved: tuple[Any, dict[str, Any], Any],
) -> None:
    thermo, _, result = solved
    info = result.info
    comps = sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_0_x_"))
    two_liquid = 0
    for j in range(int(info["n_graph_stages"])):
        liquid, vapour = info[f"stage_{j}_L_mol_s"], info[f"stage_{j}_V_mol_s"]
        x = {c: info[f"stage_{j}_x_{c}"] for c in comps}
        y = {c: info[f"stage_{j}_y_{c}"] for c in comps}
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
    assert two_liquid >= 3  # flash zone and below


def _example() -> tuple[dict[str, Any], dict[str, Any], Any]:
    thermo = registry.create("thermo", "pr")
    feeds, params = CrudeColumnR2.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}, params, thermo


def test_refuses_unknown_parameters() -> None:
    inlets, params, thermo = _example()
    with pytest.raises(RefiningSpecError, match="pumparounds"):
        CrudeColumnR2().solve(inlets, {**params, "pumparounds": []}, thermo)


def test_refuses_a_missing_stripper() -> None:
    inlets, params, thermo = _example()
    strippers = dict(params["strippers"])
    del strippers["ago_out"]
    with pytest.raises(RefiningSpecError, match="strippers"):
        CrudeColumnR2().solve(inlets, {**params, "strippers": strippers}, thermo)


def test_refuses_a_draw_below_the_flash_zone() -> None:
    inlets, params, thermo = _example()
    strippers = {**params["strippers"], "ago_out": {**params["strippers"]["ago_out"], "draw_stage": 10}}
    with pytest.raises(RefiningSpecError, match="draw_stage"):
        CrudeColumnR2().solve(inlets, {**params, "strippers": strippers}, thermo)


def test_refuses_more_stripper_steam_than_the_header_carries() -> None:
    inlets, params, thermo = _example()
    strippers = {port: {**spec, "steam_mol_s": 7.0} for port, spec in params["strippers"].items()}
    with pytest.raises(RefiningSpecError, match="steam"):
        CrudeColumnR2().solve(inlets, {**params, "strippers": strippers}, thermo)


def test_refuses_impure_steam() -> None:
    inlets, params, thermo = _example()
    wet = flash_feed(
        thermo, {"T": 500.0, "P": 2.0e5, "molar_flow": 19.0, "composition": {"H2O": 0.9, "N2": 0.1}}
    )
    with pytest.raises(RefiningSpecError, match="pure water"):
        CrudeColumnR2().solve({**inlets, "stripping_steam": wet}, params, thermo)
