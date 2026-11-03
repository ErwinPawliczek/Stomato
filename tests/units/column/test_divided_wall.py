"""Dividing-wall column R2 (unit ``divided_wall``): one stage-graph MESH solve.

The example: equimolar benzene/toluene/o-xylene, 100 mol/s subcooled liquid
at 1.2 bar, 4 common top stages, 6 | 6 wall stages, 4 common bottom stages
(kettle last), the feed on prefractionator stage 3, the side product on
main-side stage 3, R = 3 and a third of the feed to each product.

Every converged result is audited from the reported profile and fresh thermo
calls only, independently of the solver's own residual:

- every graph stage's component balance re-closed from the reported stage
  flows and compositions over the four wall links (split liquid, split
  vapour, prefractionator top vapour, prefractionator bottom liquid);
- phase equilibrium as equality of fugacities on every stage of both sides;
- the vapour split against its equal pressure-drop equation, recomputed
  with the package's vapour densities and molar masses;
- the symmetric reduction to the plain column.

Wall times (serial, this machine): the example 2 s; the symmetric case 4 s.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.column.divided_wall import (
    DividedWallError,
    DividedWallR2,
    _solve_wall,
    _WallParams,
)
from tests.conftest import flash_feed

COMPS = ("benzene", "toluene", "o-xylene")


def _solve(thermo: Thermo, **over: Any) -> tuple[StreamState, dict[str, Any], UnitResult]:
    feeds, params = DividedWallR2.example_case()
    params.update(over)
    feed = flash_feed(thermo, feeds["feed"])
    return feed, params, DividedWallR2().solve({"feed": feed}, params, thermo)


@pytest.fixture(scope="module")
def example(thermo: Thermo) -> tuple[StreamState, dict[str, Any], UnitResult]:
    return _solve(thermo)


def _stage(info: dict[str, float], j: int, key: str) -> float:
    return info[f"stage_{j}_{key}"]


def _stage_component_imbalances(
    feed: StreamState, params: dict[str, Any], res: UnitResult
) -> list[tuple[int, str, float]]:
    """(stage, component, in - out) for every graph stage, mol/s, rebuilt
    from the reported profile with the wall topology written out here."""
    info = res.info
    n = int(info["n_stages"])
    g = int(info["n_graph_stages"])
    a, b = int(info["wall_above_stage"]), int(info["wall_below_stage"])
    p0 = int(info["prefractionator_first_stage"])
    pm = g - 1
    l_wall = info["wall_liquid_to_prefractionator_mol_s"]
    v_split = info["wall_vapour_to_prefractionator_mol_s"]
    l0 = info["reflux_ratio"] * info["distillate_mol_s"]
    side = params["n_top"] + params["side_draw_stage"] - 1
    feed_stage = p0 + params["feed_stage"] - 1
    out: list[tuple[int, str, float]] = []
    for j in range(g):
        for c in COMPS:

            def x(s: int, c: str = c) -> float:
                return _stage(info, s, f"x_{c}")

            def y(s: int, c: str = c) -> float:
                return _stage(info, s, f"y_{c}")

            def lf(s: int) -> float:
                return _stage(info, s, "L_mol_s")

            def vf(s: int) -> float:
                return _stage(info, s, "V_mol_s")

            flow_in = 0.0
            flow_out = lf(j) * x(j) + vf(j) * y(j)
            if j < n:  # main cascade
                flow_in += l0 * y(0) if j == 0 else lf(j - 1) * x(j - 1)
                if j + 1 < n:
                    flow_in += (vf(j + 1) - (v_split if j == b - 1 else 0.0)) * y(j + 1)
                if j == a:
                    flow_in += vf(p0) * y(p0)
                    flow_out += l_wall * x(a)
                if j == b:
                    flow_in += lf(pm) * x(pm)
                if j == side:
                    flow_out += params["side_draw_rate"] * x(side)
            else:  # prefractionator
                flow_in += l_wall * x(a) if j == p0 else lf(j - 1) * x(j - 1)
                flow_in += v_split * y(b) if j == pm else vf(j + 1) * y(j + 1)
            if j == feed_stage:
                flow_in += feed.molar_flow * feed.composition[c]
            out.append((j, c, flow_in - flow_out))
    return out


def test_example_converges_and_closes(thermo: Thermo, example: Any) -> None:
    feed, params, res = example
    info = res.info
    d, s, b = (res.outlets[p] for p in ("distillate", "side_product", "bottoms"))
    assert d.molar_flow == pytest.approx(100.0 / 3.0, rel=1e-12)
    assert s.molar_flow == pytest.approx(100.0 / 3.0, rel=1e-12)
    assert info["reflux_ratio"] == pytest.approx(3.0, rel=1e-12)
    # Whole-unit component and energy closure.
    for c in COMPS:
        f_c = feed.molar_flow * feed.composition[c]
        o_c = sum(st.molar_flow * st.composition.get(c, 0.0) for st in (d, s, b))
        assert o_c == pytest.approx(f_c, abs=1e-6 * feed.molar_flow)
    h_in = feed.molar_flow * feed.enthalpy
    h_out = sum(st.molar_flow * st.enthalpy for st in (d, s, b))
    assert h_in + res.duty_W == pytest.approx(h_out, rel=1e-9)
    # The products are separated in the right order.
    assert d.composition["benzene"] > 0.85
    assert s.composition["toluene"] > 0.7
    assert b.composition["o-xylene"] > 0.8
    # Every graph stage closes its component balance over the wall links.
    worst = max(abs(r) for _j, _c, r in _stage_component_imbalances(feed, params, res))
    assert worst < 1e-6 * feed.molar_flow
    # Positive traffic on both sides of the wall.
    assert 0.0 < info["wall_vapour_split"] < 1.0
    assert info["prefractionator_top_vapour_mol_s"] > 1.0
    assert info["prefractionator_bottom_liquid_mol_s"] > 1.0


def test_stage_equilibrium_on_both_sides(thermo: Thermo, example: Any) -> None:
    _feed, _params, res = example
    info = res.info
    for j in range(int(info["n_graph_stages"])):
        t, p = _stage(info, j, "T_K"), _stage(info, j, "P_Pa")
        x = {c: _stage(info, j, f"x_{c}") for c in COMPS}
        y = {c: _stage(info, j, f"y_{c}") for c in COMPS}
        ln_l = thermo.phase_props(x, t, p, PhaseKind.HC_LIQUID).ln_phi
        ln_v = thermo.phase_props(y, t, p, PhaseKind.VAPOR).ln_phi
        for c in COMPS:
            gap = (math.log(x[c]) + ln_l[c]) - (math.log(y[c]) + ln_v[c])
            assert abs(gap) < 1e-5, (j, c, gap)


def _side_loads(thermo: Thermo, info: dict[str, float], area_fraction: float) -> tuple[float, float]:
    """Each wall side's sum of m_V^2 / rho_V over its stages over its area^2."""
    a, b = int(info["wall_above_stage"]), int(info["wall_below_stage"])
    p0, g = int(info["prefractionator_first_stage"]), int(info["n_graph_stages"])
    loads = []
    for stages, area in ((range(p0, g), area_fraction), (range(a + 1, b), 1.0 - area_fraction)):
        total = 0.0
        for j in stages:
            y = {c: _stage(info, j, f"y_{c}") for c in COMPS}
            props = thermo.phase_props(y, _stage(info, j, "T_K"), _stage(info, j, "P_Pa"), PhaseKind.VAPOR)
            m = _stage(info, j, "V_mol_s") * props.molecular_weight / 1000.0
            total += m * m / props.density
        loads.append(total / area**2)
    return loads[0], loads[1]


def test_vapour_split_meets_equal_pressure_drop(thermo: Thermo, example: Any) -> None:
    _feed, _params, res = example
    info = res.info
    pre, main = _side_loads(thermo, info, 0.5)
    assert pre == pytest.approx(main, rel=1e-6)
    assert info["wall_vapour_split_specified"] == 0.0
    v_b = _stage(info, int(info["wall_below_stage"]), "V_mol_s")
    assert info["wall_vapour_to_prefractionator_mol_s"] == pytest.approx(info["wall_vapour_split"] * v_b)


def test_wall_area_moves_the_vapour_split(thermo: Thermo) -> None:
    _feed, _params, res = _solve(thermo, wall_area_fraction=0.3)
    pre, main = _side_loads(thermo, res.info, 0.3)
    assert pre == pytest.approx(main, rel=1e-6)
    assert res.info["wall_vapour_split"] < 0.4  # a narrower prefractionator takes less vapour


def test_specified_vapour_split_holds(thermo: Thermo) -> None:
    feed, params, res = _solve(thermo, vapour_split=0.4)
    info = res.info
    assert info["wall_vapour_split"] == pytest.approx(0.4, rel=1e-12)
    assert info["wall_vapour_split_specified"] == 1.0
    worst = max(abs(r) for _j, _c, r in _stage_component_imbalances(feed, params, res))
    assert worst < 1e-6 * feed.molar_flow
    # The pressure-drop row is not imposed: 0.4 is off the equal-dP split.
    assert abs(info["wall_dp_imbalance"]) > 1e-2


def test_symmetric_wall_reduces_to_the_plain_column(thermo: Thermo) -> None:
    """Feed above the wall, no side draw, liquid split = area fraction = 0.3:
    both wall sides carry the plain column's stage profile at 0.3 / 0.7 of
    its flows, the equal-dP root is beta = 0.3, and the products and duties
    are the plain column's."""
    feed = flash_feed(
        thermo,
        {"T": 370.0, "P": 1.2e5, "molar_flow": 100.0, "composition": dict.fromkeys(COMPS, 1.0 / 3.0)},
    )
    wp = _WallParams(
        n_top=4,
        n_pre=5,
        n_main=5,
        n_bottom=5,
        feed_stage=1,
        liquid_split=0.3,
        vapour_split=None,
        area_fraction=0.3,
    )
    plain = {
        "n_stages": wp.n,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": wp.n_top,
        "pressure_profile": 1.2e5,
        "specs": {"reflux_ratio": 2.0, "distillate_rate": 40.0},
    }
    ref = Column().solve({"feed": feed}, plain, thermo).info
    # The plain column meets its distillate spec to the spec loop's gate
    # (measured D = 39.9937 on 40); the wall solve pins V_1 = L_0 + D
    # exactly, so it runs on the reflux and distillate the plain column
    # actually reached and the two are compared at the same column state.
    plain["specs"] = {"reflux_ratio": ref["reflux_ratio"], "distillate_rate": ref["distillate_mol_s"]}
    wall = _solve_wall(feed, dict(plain), wp, wp.n_top, thermo).info
    assert wall["wall_vapour_split"] == pytest.approx(0.3, abs=1e-6)
    assert wall["condenser_duty_W"] == pytest.approx(ref["condenser_duty_W"], rel=1e-6)
    assert wall["reboiler_duty_W"] == pytest.approx(ref["reboiler_duty_W"], rel=1e-6)
    a, p0 = int(wall["wall_above_stage"]), int(wall["prefractionator_first_stage"])
    for j in range(wp.n):
        assert wall[f"stage_{j}_T_K"] == pytest.approx(ref[f"stage_{j}_T_K"], abs=1e-4)
    for k in range(wp.n_pre):
        main_side, pre = a + 1 + k, p0 + k
        assert wall[f"stage_{pre}_T_K"] == pytest.approx(ref[f"stage_{main_side}_T_K"], abs=1e-4)
        v_ref = ref[f"stage_{main_side}_V_mol_s"]
        assert wall[f"stage_{pre}_V_mol_s"] == pytest.approx(0.3 * v_ref, rel=1e-5)
        assert wall[f"stage_{main_side}_V_mol_s"] == pytest.approx(0.7 * v_ref, rel=1e-5)
        for c in COMPS:
            assert wall[f"stage_{pre}_x_{c}"] == pytest.approx(ref[f"stage_{main_side}_x_{c}"], abs=1e-6)


def test_deterministic(thermo: Thermo, example: Any) -> None:
    _feed, _params, first = example
    _feed2, _params2, second = _solve(thermo)
    assert second.info == first.info
    assert second.duty_W == first.duty_W
    for port in ("distillate", "side_product", "bottoms"):
        assert second.outlets[port] == first.outlets[port]


@pytest.mark.parametrize(
    ("over", "match"),
    [
        ({"weir_height_m": 0.05}, "unknown parameters"),
        ({"feed_stage": 7}, "feed_stage"),
        ({"side_draw_stage": 0}, "side_draw_stage"),
        ({"liquid_split": 1.0}, "liquid_split"),
        ({"vapour_split": 0.0}, "vapour_split"),
        ({"n_bottom": 1}, "n_bottom"),
        ({"specs": {"reflux_ratio": 3.0, "boilup_ratio": 2.0}}, "specs"),
    ],
)
def test_refusals(thermo: Thermo, over: dict[str, Any], match: str) -> None:
    with pytest.raises(DividedWallError, match=match):
        _solve(thermo, **over)
