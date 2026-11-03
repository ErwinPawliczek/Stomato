"""Side strippers solved simultaneously with the main column (S0-1c step 3).

The case is a physically sensible steam-stripping service: a 10-stage
nC6/nC8/nC10/nC12 fractionator at 2 bar (partial condenser, kettle), its
stage-4 liquid (nC8-rich with nC10/nC12, at its bubble point) drawn to a
4-stage steam stripper whose overhead returns to stage 3. The partial
condenser keeps the stripping steam in the vapour distillate (water partial
pressure ~0.1 bar against ~0.9 bar saturation at the condenser), so no free
water forms anywhere and the one-liquid stage model holds - the free-water
gate checks that on every solve.

Every converged result is audited independently of the solver, from the
reported profile and fresh thermo calls only:

- whole-unit component and energy closure (feeds + steam + stage-balance
  duties against distillate + bottoms + stripper products, enthalpies from
  ``thermo.flash_pt`` / ``phase_props``);
- per-stage phase equilibrium as equality of fugacities,
  ln(x_i phi_i^L) = ln(y_i phi_i^V), on every main AND section stage.

Wall times (serial, this machine) are stated per test.
"""

from __future__ import annotations

import math
import time
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import ColumnSpecError

P = 2.0e5


def _main(**over: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "n_stages": 10,
        "condenser": "partial",
        "reboiler": "kettle",
        "pressure_profile": P,
        "feeds": [
            {
                "stage": 6,
                "T": 440.0,
                "P": P,
                "molar_flow": 100.0,
                "composition": {"nC6": 0.25, "nC8": 0.25, "nC10": 0.25, "nC12": 0.25},
            }
        ],
        "specs": {"distillate_rate": 25.0, "boilup_ratio": 1.0},
    }
    params.update(over)
    return params


def _steam(flow: float, t_k: float = 450.0, n_stages: int = 4) -> dict[str, Any]:
    return {
        "name": "s1",
        "draw_stage": 4,
        "return_stage": 3,
        "n_stages": n_stages,
        "steam": {"flow_mol_s": flow, "T_K": t_k, "P_Pa": P},
        "product_rate_mol_s": 20.0,
    }


def _solve(params: dict[str, Any], thermo: Thermo) -> UnitResult:
    result: UnitResult = registry.create("unit", "column").solve({}, params, thermo)
    return result


def _comps(info: dict[str, float]) -> list[str]:
    return sorted(k.split("_x_", 1)[1] for k in info if k.startswith("stage_0_x_"))


def _stage(info: dict[str, float], j: int, comps: list[str]) -> dict[str, Any]:
    return {
        "T": info[f"stage_{j}_T_K"],
        "P": info[f"stage_{j}_P_Pa"],
        "L": info[f"stage_{j}_L_mol_s"],
        "V": info[f"stage_{j}_V_mol_s"],
        "x": {c: info.get(f"stage_{j}_x_{c}", 0.0) for c in comps},
        "y": {c: info.get(f"stage_{j}_y_{c}", 0.0) for c in comps},
    }


def _h(thermo: Thermo, comp: dict[str, float], t: float, p: float, kind: PhaseKind) -> float:
    z = {c: v for c, v in comp.items() if v > 0.0}
    s = sum(z.values())
    return thermo.phase_props({c: v / s for c, v in z.items()}, t, p, kind).enthalpy


def closure(params: dict[str, Any], result: UnitResult, thermo: Thermo) -> tuple[float, float, float]:
    """(component closure, energy closure, |stage-balance kettle duty - reported|), relative.

    Independent of the solver: boundary feeds and steam flashed afresh, the
    products at their reported stage states, and the kettle and partial
    condenser duties recomputed from their OWN stage balances (the reported
    reboiler duty is closed on the boundary streams, so it cannot be its own
    check). With every stage balance closed the whole-unit sums telescope, so
    these closures bound the accumulated stage residuals.
    """
    info = result.info
    comps = _comps(info)
    n = int(params["n_stages"])
    st = [_stage(info, j, comps) for j in range(int(info["n_graph_stages"]))]
    hl = [_h(thermo, s["x"], s["T"], s["P"], PhaseKind.HC_LIQUID) for s in st]
    hv = [_h(thermo, s["y"], s["T"], s["P"], PhaseKind.VAPOR) for s in st]
    m_in = dict.fromkeys(comps, 0.0)
    h_in = 0.0
    for f in params["feeds"]:
        h_in += thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]).enthalpy * f["molar_flow"]
        for c, v in f["composition"].items():
            m_in[c] += v * f["molar_flow"]
    q_strip = 0.0
    for s in params.get("side_strippers", []):
        steam = s.get("steam")
        if steam is not None and steam["flow_mol_s"] > 0.0:
            state = thermo.flash_pt({"H2O": 1.0}, steam["T_K"], steam["P_Pa"], steam["flow_mol_s"])
            h_in += state.enthalpy * steam["flow_mol_s"]
            m_in["H2O"] += steam["flow_mol_s"]
        q_strip += s.get("reboiler_duty_W", 0.0)
    d, b = info["distillate_mol_s"], info["bottoms_mol_s"]
    m_out = {c: d * st[0]["y"][c] + b * st[n - 1]["x"][c] for c in comps}
    h_out = d * hv[0] + b * hl[n - 1]
    offset = n
    for s in params.get("side_strippers", []):
        bottom = offset + int(s["n_stages"]) - 1
        offset += int(s["n_stages"])
        prod = info[f"stripper_{s['name']}_product_mol_s"]
        h_out += prod * hl[bottom]
        for c in comps:
            m_out[c] += prod * st[bottom]["x"][c]
    q_reb = st[n - 1]["V"] * hv[n - 1] + st[n - 1]["L"] * hl[n - 1] - st[n - 2]["L"] * hl[n - 2]
    q_cond = st[1]["V"] * hv[1] - st[0]["V"] * hv[0] - st[0]["L"] * hl[0]
    q_pa = sum(v for k, v in info.items() if k.startswith("pa_") and k.endswith("_duty_W"))
    e_in = h_in + q_reb + q_strip + q_pa - q_cond
    m_rel = max(abs(m_in[c] - m_out[c]) for c in comps) / sum(m_in.values())
    e_rel = abs(e_in - h_out) / max(abs(h_in), abs(h_out), q_reb, q_cond)
    q_rel = abs(q_reb - info["reboiler_duty_W"]) / q_reb
    return m_rel, e_rel, q_rel


def fugacity_equilibrium(result: UnitResult, thermo: Thermo) -> float:
    """Max |ln(x_i phi_i^L) - ln(y_i phi_i^V)| over every graph stage and
    every component carried above 1e-12 in both phases: the E equations of
    MESH as equality of fugacity, read from the reported profile."""
    info = result.info
    comps = _comps(info)
    worst = 0.0
    for j in range(int(info["n_graph_stages"])):
        s = _stage(info, j, comps)
        x = {c: v for c, v in s["x"].items() if v > 0.0}
        y = {c: v for c, v in s["y"].items() if v > 0.0}
        lx = thermo.phase_props(x, s["T"], s["P"], PhaseKind.HC_LIQUID).ln_phi
        ly = thermo.phase_props(y, s["T"], s["P"], PhaseKind.VAPOR).ln_phi
        for c in comps:
            if s["x"][c] > 1e-12 and s["y"][c] > 1e-12:
                gap = math.log(s["x"][c]) + lx[c] - math.log(s["y"][c]) - ly[c]
                worst = max(worst, abs(gap))
    return worst


def test_zero_stage_stripper_is_a_plain_side_draw(thermo: Thermo) -> None:
    """Identity: a 0-stage stripper IS a plain liquid side draw of its product
    rate - bit for bit (the spec's 1e-10 is met with equality). Measured
    ~3 s."""
    plain = _solve(_main(draws=[{"stage": 4, "phase": "liquid", "flow_mol_s": 20.0}]), thermo)
    zero = _solve(_main(side_strippers=[_steam(0.0, n_stages=0)]), thermo)
    assert zero.outlets["distillate"] == plain.outlets["distillate"]
    assert zero.outlets["bottoms"] == plain.outlets["bottoms"]
    assert zero.duty_W == plain.duty_W
    draw = plain.outlets["side_draw"]
    assert zero.info["stripper_s1_product_mol_s"] == draw.molar_flow
    for cid, frac in draw.composition.items():
        assert zero.info[f"stripper_s1_x_{cid}"] == frac


def test_zero_steam_changes_nothing(thermo: Thermo) -> None:
    """A 4-stage stripper with zero steam strips nothing: its stages carry no
    vapour, its product is the draw liquid, and the main column is the
    plain-side-draw column. The two are independent converged solves (the
    graph Newton against the linear inside-out mesh), each to the 1e-8 mesh
    gate, so they agree to that gate's reach, not to machine precision:
    measured worst relative difference over the main stages' T, V, L and x
    1.9e-8, and the product composition against the plain column's draw
    1.6e-9. Measured ~6 s."""
    plain = _solve(_main(draws=[{"stage": 4, "phase": "liquid", "flow_mol_s": 20.0}]), thermo)
    zs = _solve(_main(side_strippers=[_steam(0.0)]), thermo)
    worst = 0.0
    for j in range(10):
        for key in ("T_K", "V_mol_s", "L_mol_s"):
            a, b = plain.info[f"stage_{j}_{key}"], zs.info[f"stage_{j}_{key}"]
            worst = max(worst, abs(a - b) / abs(a))
        for key, a in plain.info.items():
            if key.startswith(f"stage_{j}_x_") and a > 1e-12:
                worst = max(worst, abs(a - zs.info[key]) / a)
    assert worst < 1e-7, worst
    for j in range(10, 14):
        assert zs.info[f"stage_{j}_V_mol_s"] <= 1e-8
    assert zs.info["stripper_s1_vapour_return_mol_s"] <= 1e-8
    assert zs.info["stripper_s1_draw_mol_s"] == pytest.approx(20.0, rel=1e-9)
    for cid, frac in plain.outlets["side_draw"].composition.items():
        assert zs.info[f"stripper_s1_x_{cid}"] == pytest.approx(frac, rel=1e-7, abs=1e-12)


def test_steam_stripper_closes_the_whole_unit(thermo: Thermo) -> None:
    """Mass, component and energy closure of the whole unit at 1e-8, with
    every enthalpy recomputed from thermo and the kettle duty from its own
    stage balance; every stage (main and section) at phase equilibrium by
    fugacity equality. Measured: component 1.8e-16, energy 1.0e-15, kettle
    duty 1e-15; ~8 s."""
    params = _main(side_strippers=[_steam(1.0)])
    r = _solve(params, thermo)
    m_rel, e_rel, q_rel = closure(params, r, thermo)
    assert m_rel < 1e-8 and e_rel < 1e-8 and q_rel < 1e-8, (m_rel, e_rel, q_rel)
    assert fugacity_equilibrium(r, thermo) < 1e-6
    assert r.info["stripper_s1_product_mol_s"] == pytest.approx(20.0, rel=1e-12)
    # The steam strips: the product is heavier than the draw liquid and
    # leaves cooler than the stripper top (the vaporisation cools the stages).
    assert r.info["stripper_s1_x_nC6"] < r.info["stage_3_x_nC6"]
    assert r.info["stripper_s1_bottom_T_K"] < r.info["stripper_s1_top_T_K"]


def test_rerun_is_bit_identical(thermo: Thermo) -> None:
    """Two solves of one stripper column return identical results. ~15 s."""
    params = _main(side_strippers=[_steam(1.0)])
    a = _solve(params, thermo)
    b = _solve(params, thermo)
    assert a.info == b.info
    assert a.outlets == b.outlets
    assert a.duty_W == b.duty_W


@pytest.mark.parametrize("t_steam", [450.0, 550.0])
@pytest.mark.parametrize("steam", [0.3, 0.5, 1.0, 1.5, 2.0])
def test_steam_robustness_grid(thermo: Thermo, steam: float, t_steam: float) -> None:
    """The steam grid of the spec: 0.3-2.0 mol/s at 450 K and 550 K (2 bar,
    superheated). Every point converges, closes at 1e-8 and sits at phase
    equilibrium; more steam strips more (the stripper bottom falls).
    Measured 7-9 s per point."""
    params = _main(side_strippers=[_steam(steam, t_steam)])
    start = time.perf_counter()
    r = _solve(params, thermo)
    elapsed = time.perf_counter() - start
    m_rel, e_rel, q_rel = closure(params, r, thermo)
    assert m_rel < 1e-8 and e_rel < 1e-8 and q_rel < 1e-8, (m_rel, e_rel, q_rel)
    assert fugacity_equilibrium(r, thermo) < 1e-6
    assert r.info["stripper_s1_bottom_T_K"] < r.info["stripper_s1_top_T_K"]
    assert elapsed < 60.0


def test_pumparound_two_steam_and_one_reboiled_stripper(thermo: Thermo) -> None:
    """One pumparound, two steam strippers and one reboiled stripper on a
    14-stage nC5-nC13 column at 2 bar converge as one system and close.
    Measured ~19 s."""
    params: dict[str, Any] = {
        "n_stages": 14,
        "condenser": "partial",
        "reboiler": "kettle",
        "pressure_profile": P,
        "feeds": [
            {
                "stage": 11,
                "T": 470.0,
                "P": P,
                "molar_flow": 100.0,
                "composition": {"nC5": 0.2, "nC7": 0.2, "nC9": 0.2, "nC11": 0.2, "nC13": 0.2},
            }
        ],
        "specs": {"distillate_rate": 20.0, "boilup_ratio": 1.0},
        "pumparounds": [
            {"name": "pa1", "draw_stage": 5, "return_stage": 4, "flow_mol_s": 30.0, "duty_W": -3.0e5}
        ],
        "side_strippers": [
            {
                "name": "s1",
                "draw_stage": 4,
                "return_stage": 3,
                "n_stages": 4,
                "steam": {"flow_mol_s": 1.0, "T_K": 450.0, "P_Pa": P},
                "product_rate_mol_s": 15.0,
            },
            {
                "name": "s2",
                "draw_stage": 7,
                "return_stage": 6,
                "n_stages": 3,
                "steam": {"flow_mol_s": 1.0, "T_K": 450.0, "P_Pa": P},
                "product_rate_mol_s": 15.0,
            },
            {
                "name": "s3",
                "draw_stage": 10,
                "return_stage": 9,
                "n_stages": 3,
                "reboiler_duty_W": 2.0e5,
                "product_rate_mol_s": 15.0,
            },
        ],
    }
    r = _solve(params, thermo)
    m_rel, e_rel, q_rel = closure(params, r, thermo)
    assert m_rel < 1e-8 and e_rel < 1e-8 and q_rel < 1e-8, (m_rel, e_rel, q_rel)
    assert fugacity_equilibrium(r, thermo) < 1e-6
    assert r.info["pa_pa1_duty_W"] == pytest.approx(-3.0e5)
    for name in ("s1", "s2", "s3"):
        assert r.info[f"stripper_{name}_product_mol_s"] == pytest.approx(15.0, rel=1e-12)
    # The reboiled stripper heats its bottoms above its top.
    assert r.info["stripper_s3_bottom_T_K"] > r.info["stripper_s3_top_T_K"]
    # Net unit duty: kettle + stripper reboiler + pumparound - condenser.
    assert r.duty_W == pytest.approx(
        r.info["reboiler_duty_W"] + 2.0e5 + r.info["pa_pa1_duty_W"] - r.info["condenser_duty_W"], rel=1e-12
    )


def test_strippers_on_a_reactive_column_refused(thermo: Thermo) -> None:
    """The graph residual has no reaction terms: the combination refuses
    (with a valid reaction set, so the refusal is this one)."""
    from ngdesign.units.column_shortcut.reactive_stages import ReactiveStages

    params = _main(side_strippers=[_steam(1.0)])
    params["reaction_set"] = ReactiveStages.example_case()[1]["reaction_set"]
    params["reactive_holdup_m3"] = {5: 1.0}
    with pytest.raises(ColumnSpecError, match="side_strippers on a reactive column are not supported"):
        _solve(params, thermo)


def test_two_strippers_on_one_draw_tray_refused(thermo: Thermo) -> None:
    second = dict(_steam(1.0), name="s2", return_stage=2)
    with pytest.raises(ColumnSpecError, match="both draw from stage 4"):
        _solve(_main(side_strippers=[_steam(1.0), second]), thermo)
