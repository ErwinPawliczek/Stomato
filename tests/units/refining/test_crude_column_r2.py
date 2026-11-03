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

#: Any test that may run a solve (the module fixtures' or its own): one
#: crude-column solve measured ~30 s alone and 37-44 s as a fixture setup
#: under -n 6 (before 15ce74c: 50 s, 58-81 s); a loaded host still varies 2x.
_SOLVES = pytest.mark.timeout(600)

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


def _assert_closes(inlets: dict[str, Any], result: Any) -> None:
    """Whole-unit component and energy closure, and no phantom reboiler duty."""
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
    # The net duty is the condenser's plus every pumparound cooler's.
    coolers = sum(v for k, v in result.info.items() if k.startswith("pa_") and k.endswith("_duty_W"))
    assert result.duty_W == pytest.approx(coolers - condenser, abs=_CLOSE * abs(condenser))


@_SOLVES
def test_example_closes_components_and_energy_without_a_phantom_duty(
    solved: tuple[Any, dict[str, Any], Any],
) -> None:
    _, inlets, result = solved
    _assert_closes(inlets, result)


@_SOLVES
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


@_SOLVES
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
    with pytest.raises(RefiningSpecError, match="reboiler"):
        CrudeColumnR2().solve(inlets, {**params, "reboiler": "kettle"}, thermo)


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


#: The usual two heat-removal loops of an atmospheric column: a top
#: pumparound under the condenser and a diesel pumparound off the diesel
#: draw tray, each returned one stage up as subcooled liquid.
_PUMPAROUNDS: list[dict[str, Any]] = [
    {"name": "top", "draw_stage": 3, "return_stage": 2, "flow_mol_s": 300.0, "return_T_K": 380.0},
    {"name": "diesel", "draw_stage": 7, "return_stage": 6, "flow_mol_s": 100.0, "return_T_K": 450.0},
]
#: The pumparound case's own worker (one solve for its tests).
_PA_GROUP = pytest.mark.xdist_group("pa")


def _solve_pa(pumparounds: list[dict[str, Any]]) -> tuple[Any, dict[str, Any], Any]:
    inlets, params, thermo = _example()
    return thermo, inlets, CrudeColumnR2().solve(inlets, {**params, "pumparounds": pumparounds}, thermo)


def _snapshot(result: Any) -> dict[str, Any]:
    """Every reported number of a result, for exact comparisons."""
    out: dict[str, Any] = {"duty_W": result.duty_W, "info": dict(result.info)}
    for port, s in result.outlets.items():
        out[port] = (s.T, s.P, s.molar_flow, s.enthalpy, dict(s.composition))
    return out


@pytest.fixture(scope="module")
def solved_pa() -> tuple[Any, dict[str, Any], Any]:
    return _solve_pa(_PUMPAROUNDS)


@_PA_GROUP
@_SOLVES
def test_pumparound_case_closes_components_and_energy(solved_pa: tuple[Any, dict[str, Any], Any]) -> None:
    _, inlets, result = solved_pa
    _assert_closes(inlets, result)
    for pa in _PUMPAROUNDS:
        assert result.info[f"pa_{pa['name']}_duty_W"] < 0.0
        assert result.info[f"pa_{pa['name']}_return_T_K"] == pa["return_T_K"]
    # The products still meet their specs with the loops in.
    assert result.outlets["overhead"].molar_flow == pytest.approx(430.0, rel=1e-9)
    assert result.outlets["diesel_out"].molar_flow == pytest.approx(98.15, rel=1e-9)


@_PA_GROUP
@_SOLVES
def test_pumparound_duty_is_the_loop_liquids_enthalpy_change(
    solved_pa: tuple[Any, dict[str, Any], Any],
) -> None:
    """Each cooler duty is flow x (h(return T) - h(draw T)) of the drawn
    liquid, recomputed on a fresh package instance from the reported draw
    stage state; the subcooled return is one homogeneous liquid there."""
    _, _, result = solved_pa
    info = result.info
    fresh = registry.create("thermo", "pr")
    for pa in _PUMPAROUNDS:
        j = pa["draw_stage"] - 1
        x = {k.split("_x_", 1)[1]: v for k, v in info.items() if k.startswith(f"stage_{j}_x_") and v > 0.0}
        p = info[f"stage_{j}_P_Pa"]
        t_draw = info[f"pa_{pa['name']}_draw_T_K"]
        assert t_draw == info[f"stage_{j}_T_K"]
        returned = fresh.flash_pt(x, pa["return_T_K"], p, 1.0)
        assert [ph.kind for ph in returned.phases] == [PhaseKind.HC_LIQUID]
        h_draw = fresh.phase_props(x, t_draw, p, PhaseKind.HC_LIQUID).enthalpy
        duty = pa["flow_mol_s"] * (returned.enthalpy - h_draw)
        assert info[f"pa_{pa['name']}_duty_W"] == pytest.approx(duty, rel=1e-9)


@_PA_GROUP
@_SOLVES
def test_pumparound_case_is_deterministic(solved_pa: tuple[Any, dict[str, Any], Any]) -> None:
    assert _snapshot(_solve_pa(_PUMPAROUNDS)[2]) == _snapshot(solved_pa[2])


@_SOLVES
def test_idle_pumparounds_are_exactly_the_column_without_them(
    solved: tuple[Any, dict[str, Any], Any],
) -> None:
    """Zero-flow loops carry nothing: every number matches the example."""
    idle = [{**pa, "flow_mol_s": 0.0} for pa in _PUMPAROUNDS]
    result = _solve_pa(idle)[2]
    snap = _snapshot(result)
    snap["info"] = {k: v for k, v in snap["info"].items() if not k.startswith("pa_")}
    assert snap == _snapshot(solved[2])
    assert all(result.info[f"pa_{pa['name']}_duty_W"] == 0.0 for pa in idle)


def test_refuses_a_pumparound_at_the_flash_zone() -> None:
    inlets, params, thermo = _example()
    loop = {"name": "fz", "draw_stage": 10, "return_stage": 9, "flow_mol_s": 10.0, "return_T_K": 500.0}
    with pytest.raises(RefiningSpecError, match="above the flash zone"):
        CrudeColumnR2().solve(inlets, {**params, "pumparounds": [loop]}, thermo)


def test_refuses_an_overhead_the_flash_zone_cannot_vaporise() -> None:
    """455 mol/s of overhead needs a negative overflash: at zero overflash
    the flash-zone envelope leaves 142.16 mol/s of bottoms, so the products
    above it can take at most 876.84 mol/s (overhead 448.72 at the example
    side rates), and they ask for 883.12. Refused before the column solve."""
    inlets, params, thermo = _example()
    with pytest.raises(RefiningSpecError, match="negative overflash") as err:
        CrudeColumnR2().solve(inlets, {**params, "distillate_rate_mol_s": 455.0}, thermo)
    limit = float(str(err.value).split("enough for ")[1].split(" mol/s")[0])
    assert limit == pytest.approx(876.837, abs=1e-3)
