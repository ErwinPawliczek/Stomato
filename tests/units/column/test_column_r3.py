"""column R3 (rate-based distillation, Murphree trays): reductions, closed forms, refusals.

Oracles:
1. ``stage_model="murphree"`` at E = 1 is R2's MESH stage for stage: with R2's achieved
   specs it reproduces R2 to R2's own convergence (partial condenser; a total condenser
   carries R2's reflux-temperature convention, see test 3);
2. ``stage_model="rate_based"`` reduces to R2 as ``transfer_factor`` grows;
3. closed forms from the plan's equations (specs/backend/units/column_r3.md): the total
   condenser and the Murphree row recomputed with independent ``phase_props`` and
   ``bubble_point`` calls;
4. typed refusals; 5. V0 on the example case.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column
from ngdesign.units.column.column_r3 import ColumnR3
from ngdesign.units.column.rate_based_units import RateBasedSpecError
from tests.conftest import flash_feed

_BASE_KEYS = ("n_stages", "condenser", "feed_stage", "pressure_profile")


def _feed(thermo: Thermo) -> dict[str, StreamState]:
    feeds, _ = ColumnR3.example_case()
    return {"feed": flash_feed(thermo, feeds["feed"])}


def _murphree_params(**extra: Any) -> dict[str, Any]:
    _, params = ColumnR3.example_case()
    return {**{k: params[k] for k in _BASE_KEYS}, "stage_model": "murphree", **extra}


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-12)


def _outlet_dev(a: UnitResult, b: UnitResult) -> tuple[float, float]:
    """(max mole-fraction or relative-flow deviation, max |dT| K) over distillate and bottoms."""
    dev, dt = 0.0, 0.0
    for port in ("distillate", "bottoms"):
        sa, sb = a.outlets[port], b.outlets[port]
        dev = max(dev, _rel(sa.molar_flow, sb.molar_flow))
        dev = max(dev, *(abs(sa.composition[c] - x) for c, x in sb.composition.items()))
        dt = max(dt, abs(sa.T - sb.T))
    return dev, dt


def _r2_partial(thermo: Thermo, inlets: dict[str, StreamState]) -> tuple[UnitResult, dict[str, float]]:
    _, r2_params = Column.example_case()
    r2 = Column().solve(
        inlets, {**r2_params, "condenser": "partial", "specs": {"distillate_rate": 45.0, "boilup_ratio": 3.0}}, thermo
    )
    # R2 meets specs only to its spec gate (5e-3); compare the same physical column.
    return r2, {"distillate_rate": r2.info["distillate_mol_s"], "boilup_ratio": r2.info["boilup_ratio"]}


# --------------------------------------------------------------------------------------
# 1-2. Reductions to R2
# --------------------------------------------------------------------------------------


def test_murphree_unit_efficiency_reduces_to_r2(thermo: Thermo) -> None:
    inlets = _feed(thermo)
    r2, specs = _r2_partial(thermo, inlets)
    r3 = ColumnR3().solve(inlets, _murphree_params(condenser="partial", specs=specs), thermo)
    dev, dt = _outlet_dev(r3, r2)
    assert dev < 1e-7  # measured 1.2e-9 (mole fractions)
    assert dt < 1e-5  # measured 1.9e-7 K
    for key in ("condenser_duty_W", "reboiler_duty_W"):
        assert _rel(r3.info[key], r2.info[key]) < 1e-7  # measured 2.4e-9, 2.6e-9
    # stage for stage (partial condenser: R3 block j is R2 stage j)
    for j in range(16):
        assert abs(r3.info[f"stage_{j}_TV_K"] - r2.info[f"stage_{j}_T_K"]) < 1e-5
        assert _rel(r3.info[f"stage_{j}_V_mol_s"], r2.info[f"stage_{j}_V_mol_s"]) < 1e-7


def test_rate_based_reduces_to_r2_as_transfer_grows(thermo: Thermo) -> None:
    inlets = _feed(thermo)
    r2, specs = _r2_partial(thermo, inlets)
    _, params = ColumnR3.example_case()
    devs = []
    for factor in (1.0, 1e4):
        r3 = ColumnR3().solve(
            inlets, {**params, "condenser": "partial", "specs": specs, "transfer_factor": factor}, thermo
        )
        dev, dt = _outlet_dev(r3, r2)
        devs.append(dev)
        if factor > 1.0:
            assert dev < 1e-5  # measured 1.9e-6 (mole fractions)
            assert dt < 1e-3  # measured 1.2e-4 K
            assert _rel(r3.info["reboiler_duty_W"], r2.info["reboiler_duty_W"]) < 1e-5  # measured 1.3e-7
    assert devs[0] > 1e-3  # finite transfer separates less: measured 1.9e-2 at factor 1
    assert devs[1] < devs[0]


def test_total_condenser_rate_limit_equals_murphree_and_tracks_r2(thermo: Thermo) -> None:
    """Total condenser: R3's own equilibrium limit (rate-based at factor 1e4 vs Murphree
    E = 1, the same equations) agrees to the transfer limit. Against R2 the profiles
    differ by R2's convention of returning the reflux at the stage-1 temperature (R3:
    saturated, bubble-point reflux) - measured 3.3e-3 in product mole fractions and
    0.2 K on stage temperatures."""
    inlets = _feed(thermo)
    _, params = ColumnR3.example_case()
    rate = ColumnR3().solve(inlets, {**params, "transfer_factor": 1e4}, thermo)
    tray = ColumnR3().solve(inlets, _murphree_params(specs=params["specs"]), thermo)
    dev, dt = _outlet_dev(rate, tray)
    assert dev < 1e-5  # measured 2.0e-6
    assert dt < 1e-3
    r2 = Column().solve(inlets, Column.example_case()[1], thermo)
    for j in range(1, 17):  # R3 block j = R2 stage j-1 under a total condenser
        assert abs(tray.info[f"stage_{j}_TV_K"] - r2.info[f"stage_{j - 1}_T_K"]) < 0.5
        assert abs(tray.info[f"stage_{j}_x_C3"] - r2.info[f"stage_{j - 1}_x_C3"]) < 1e-2


# --------------------------------------------------------------------------------------
# 3. Closed forms
# --------------------------------------------------------------------------------------


def test_total_condenser_closed_form(thermo: Thermo) -> None:
    """Hand calculation from the plan's total-condenser block, R = 2.5, D = 45 mol/s:
    L_0 = R D = 112.5 mol/s, V_1 = L_0 + D = 157.5 mol/s, x_D = x_reflux = y_1, the
    condensate at its bubble point T_0 = T_bub(x_D, P), and
    Q_c = V_1 h_V(y_1, T_1) - (L_0 + D) h_L(x_D, T_0) with the package enthalpies."""
    inlets = _feed(thermo)
    res = ColumnR3().solve(inlets, _murphree_params(specs={"reflux_ratio": 2.5, "distillate_rate": 45.0}), thermo)
    info = res.info
    P = 1.5e6
    assert info["stage_0_L_mol_s"] == pytest.approx(112.5, rel=1e-9)
    assert info["stage_0_V_mol_s"] == pytest.approx(45.0, rel=1e-9)
    assert info["stage_1_V_mol_s"] == pytest.approx(157.5, rel=1e-9)
    x_d = {c: info[f"stage_0_x_{c}"] for c in ("C3", "iC4")}
    y_1 = {c: info[f"stage_1_y_{c}"] for c in ("C3", "iC4")}
    for c in x_d:
        assert info[f"stage_0_y_{c}"] == pytest.approx(x_d[c], abs=1e-12)  # D and L share x_D
        assert x_d[c] == pytest.approx(y_1[c], abs=1e-9)  # total condensation
    t0 = info["stage_0_TV_K"]
    assert t0 == pytest.approx(thermo.bubble_point(x_d, P=P).T, abs=1e-6)
    h_v = thermo.phase_props(y_1, info["stage_1_TV_K"], P, PhaseKind.VAPOR).enthalpy
    h_l = thermo.phase_props(x_d, t0, P, PhaseKind.HC_LIQUID).enthalpy
    assert info["condenser_duty_W"] == pytest.approx(157.5 * (h_v - h_l), rel=1e-7)
    d = res.outlets["distillate"]
    assert d.vapor_fraction < 1e-6  # saturated liquid product
    assert d.T == pytest.approx(t0, abs=1e-4)


@pytest.mark.parametrize("eff", [0.6, [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.6, 0.7, 0.8, 0.9]])
def test_murphree_row_closed_form(thermo: Thermo, eff: float | list[float]) -> None:
    """Murphree (1925): y_n = y_in + E (y*_n - y_in). Binary C3/iC4, total condenser:
    tray n (blocks 1..15) receives vapour from block n+1 (no vapour feed: the feed is
    liquid), y*_n the incipient vapour of an independent ``bubble_point(x_n, P)`` at
    whose temperature the tray sits. E = 0.6 gives e.g. y_C3 = y_in + 0.6 (y* - y_in)."""
    inlets = _feed(thermo)
    _, params = ColumnR3.example_case()
    res = ColumnR3().solve(inlets, _murphree_params(specs=params["specs"], murphree_efficiency=eff), thermo)
    info = res.info
    effs = eff if isinstance(eff, list) else [eff] * 15
    for n in range(1, 16):
        x = {c: info[f"stage_{n}_x_{c}"] for c in ("C3", "iC4")}
        bub = thermo.bubble_point(x, P=1.5e6)
        assert info[f"stage_{n}_TV_K"] == pytest.approx(bub.T, abs=1e-5)  # measured 1.1e-6 K
        y_in = info[f"stage_{n + 1}_y_C3"]
        expected = y_in + effs[n - 1] * (bub.incipient_composition["C3"] - y_in)
        # to the independent bubble_point's own convergence (measured 1.8e-9)
        assert info[f"stage_{n}_y_C3"] == pytest.approx(expected, abs=1e-7)
        assert info[f"stage_{n}_EMV_C3"] == pytest.approx(effs[n - 1], abs=1e-6)
    full = ColumnR3().solve(inlets, _murphree_params(specs=params["specs"]), thermo)
    # a less efficient column separates less at the same R and D
    assert res.outlets["distillate"].composition["C3"] < full.outlets["distillate"].composition["C3"]


def test_spec_pairs_round_trip(thermo: Thermo) -> None:
    """Duty and bottoms-rate specs reproduce the ratio specs' column (same equations)."""
    inlets = _feed(thermo)
    base = ColumnR3().solve(inlets, _murphree_params(specs={"reflux_ratio": 2.5, "distillate_rate": 45.0}), thermo)
    qc, qr, vb = base.info["condenser_duty_W"], base.info["reboiler_duty_W"], base.info["boilup_ratio"]
    pairs: list[dict[str, float]] = [
        {"condenser_duty_W": qc, "boilup_ratio": vb},
        {"reflux_ratio": 2.5, "reboiler_duty_W": qr},
        {"bottoms_rate": 55.0, "boilup_ratio": vb},
        {"reflux_ratio": 2.5, "bottoms_rate": 55.0},
    ]
    for specs in pairs:
        res = ColumnR3().solve(inlets, _murphree_params(specs=specs), thermo)
        assert res.info["reflux_ratio"] == pytest.approx(2.5, rel=1e-6), specs
        assert res.info["distillate_mol_s"] == pytest.approx(45.0, rel=1e-6), specs


# --------------------------------------------------------------------------------------
# 4. Refusals
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        ({"n_stages": 2}, "n_stages"),
        ({"condenser": "none"}, "condenser"),
        ({"reboiler": "none"}, "reboiler"),
        ({"feed_stage": 17}, "feed_stage"),
        ({"stage_model": "equilibrium"}, "stage_model"),
        ({"bogus": 1}, "unknown"),
        ({"murphree_efficiency": 0.7}, "unknown"),  # a Murphree key in rate-based mode
        ({"transfer_factor": -1.0}, "transfer_factor"),
        ({"column_diameter_m": None}, "column_diameter_m"),
        ({"pressure_profile": [1.5e6] * 3}, "pressure_profile"),
        ({"specs": {"reflux_ratio": 2.5}}, "specs"),
        ({"specs": {"distillate_rate": 45.0, "bottoms_rate": 55.0}}, "D \\+ B = F"),
        ({"specs": {"reflux_ratio": 2.5, "condenser_duty_W": 1e6}}, "same end"),
        ({"specs": {"boilup_ratio": 2.5, "reboiler_duty_W": 1e6}}, "same end"),
        ({"specs": {"reflux_ratio": 2.5, "product_purity": 0.9}}, "product_purity"),
        ({"specs": {"reflux_ratio": -2.5, "distillate_rate": 45.0}}, "reflux_ratio"),
        ({"specs": {"reflux_ratio": 2.5, "distillate_rate": 100.0}}, "distillate_rate"),
    ],
)
def test_refusals(thermo: Thermo, patch: dict[str, Any], match: str) -> None:
    _, params = ColumnR3.example_case()
    with pytest.raises(RateBasedSpecError, match=match):
        ColumnR3().solve(_feed(thermo), {**params, **patch}, thermo)


@pytest.mark.parametrize(
    ("patch", "match"),
    [
        ({"murphree_efficiency": 1.5}, "murphree_efficiency"),
        ({"murphree_efficiency": [0.5] * 3}, "murphree_efficiency"),
        ({"column_diameter_m": 1.5}, "unknown"),  # a packing key in Murphree mode
    ],
)
def test_murphree_refusals(thermo: Thermo, patch: dict[str, Any], match: str) -> None:
    _, params = ColumnR3.example_case()
    with pytest.raises(RateBasedSpecError, match=match):
        ColumnR3().solve(_feed(thermo), _murphree_params(specs=params["specs"], **patch), thermo)


# --------------------------------------------------------------------------------------
# 5. V0 on the example case
# --------------------------------------------------------------------------------------


def test_example_case_closes_balances(thermo: Thermo) -> None:
    inlets = _feed(thermo)
    _, params = ColumnR3.example_case()
    res = ColumnR3().solve(inlets, params, thermo)
    feed = inlets["feed"]
    out: dict[str, float] = {}
    for s in res.outlets.values():
        for c, n in s.component_flows().items():
            out[c] = out.get(c, 0.0) + n
    for c, n in feed.component_flows().items():
        assert abs(out[c] - n) < 1e-8 * feed.molar_flow
    h_in = feed.molar_flow * feed.enthalpy
    h_out = sum(s.molar_flow * s.enthalpy for s in res.outlets.values())
    assert abs(h_in + res.duty_W - h_out) <= 1e-8 * max(abs(h_in), abs(h_out))
    # the model's duties close the boundary balance too (not only duty_W by construction)
    assert res.info["energy_residual_rel"] < 1e-8
    assert res.info["onda_in_range"] == 1.0
    assert res.info["reflux_ratio"] == pytest.approx(2.5, rel=1e-9)
    assert res.info["distillate_mol_s"] == pytest.approx(45.0, rel=1e-9)
