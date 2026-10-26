"""Tests for the R2 TEG regenerator (spec teg_regen R2).

Step-1 scope: the R0 delegation (zero stripping gas, exact identity), the
G -> 0 march limit, and one test per refusal row of the spec's table.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.registry import create
from ngdesign.units.teg_activity import activity_equilibrium_slope
from ngdesign.units.treating.teg_regen import (
    DEFAULT_P,
    DEFAULT_T_REBOILER,
    TEGRegen,
    TEGRegenError,
    _lean_water_mole_fraction,
    _mw,
)
from ngdesign.units.treating.teg_regen_r2 import TEGRegenR2
from ngdesign.units.treating.teg_stagewise import (
    TEGStageError,
    countercurrent_march,
    teg_x_of_y,
)

THERMO: Thermo = create("thermo", "pr")
PARAMS: dict[str, Any] = {
    "T_reboiler": DEFAULT_T_REBOILER,
    "P": DEFAULT_P,
    "n_stages": 2,
}


def _feed(
    composition: dict[str, float], T: float = 422.15, P: float = 1.5e5, molar_flow: float = 100.0
) -> StreamState:
    return THERMO.flash_pt(composition, T, P, molar_flow)


def _r0(rich: StreamState) -> UnitResult:
    return TEGRegen().solve({"rich_in": rich}, {"T_reboiler": DEFAULT_T_REBOILER, "P": DEFAULT_P}, THERMO)


def test_zero_stripping_gas_delegates_to_r0_exactly() -> None:
    """Identity: no gas port, a zero-flow gas, and n_stages = 0 each give
    R0's result exactly (==) on both outlets and the duty."""
    rich = _feed({"TEG": 0.84, "H2O": 0.15, "C1": 0.008, "CO2": 0.002})
    zero_gas = _feed({"N2": 1.0}, T=477.15, P=101325.0, molar_flow=0.0)

    r0 = _r0(rich)
    no_gas_params = {"T_reboiler": DEFAULT_T_REBOILER, "P": DEFAULT_P, "n_stages": 0}
    for inlets, params in [
        ({"rich_in": rich}, dict(PARAMS)),
        ({"rich_in": rich, "stripping_gas_in": zero_gas}, dict(PARAMS)),
        ({"rich_in": rich, "stripping_gas_in": zero_gas}, no_gas_params),
    ]:
        r2 = TEGRegenR2().solve(inlets, params, THERMO)
        assert r2.duty_W == r0.duty_W
        for port in ("lean_out", "water_out"):
            assert r2.outlets[port].molar_flow == r0.outlets[port].molar_flow
            assert r2.outlets[port].composition == r0.outlets[port].composition
            assert r2.outlets[port].enthalpy == r0.outlets[port].enthalpy
            assert r2.outlets[port].T == r0.outlets[port].T
            assert r2.outlets[port].P == r0.outlets[port].P
        for key, value in r0.info.items():
            assert r2.info[key] == value, key
        assert r2.info["n_stages"] == float(params["n_stages"])
        assert r2.info["stripping_gas_mol_s"] == 0.0
        assert r2.info["purity_enhancement_wt_pct"] == 0.0


def test_g0_limit_march_recovers_the_boiling_line_ratio() -> None:
    """As G -> 0 with N >= 1 the march itself stops stripping: X_N -> X_0.

    SPEC ISSUE (teg_regen R2, step 1): the spec claims "at G = 1e-9 mol/s,
    X_lean matches X_0 to rel 1e-6"; the shared march's numerics do not
    support that. Measured on this correlation (T = 477.15 K, S = 82 mol/s,
    N = 2, dry gas): the residual-scan root Y_1 ~ sqrt(S/(G k)) grows as G
    shrinks, and the liquid ratio gap falls only as sqrt(G) -- rel gap
    2.042e-5 at G = 1e-9 and 6.456e-6 at G = 1e-10, while at G = 1e-11 the
    scan (Y_1 in [1e-14, 1e6]) finds no bracket and the march raises
    TEGStageError. The assertions below use the measured gap with one order
    of headroom (rel 1e-4) and pin the singularity refusal at G = 1e-11.
    """
    T, P = DEFAULT_T_REBOILER, DEFAULT_P
    x_reb = _lean_water_mole_fraction(T, P)
    X_0 = x_reb / (1.0 - x_reb)
    y_1e9, x_1e9 = countercurrent_march(1.0e-9, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))
    assert x_1e9[-1] == pytest.approx(X_0, rel=1.0e-4)
    y_1e10, x_1e10 = countercurrent_march(1.0e-10, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))
    assert x_1e10[-1] == pytest.approx(X_0, rel=1.0e-4)
    # The gap tightens as G falls (the sqrt(G) law), and past G ~ 1e-11 the
    # shared march's bracket scan refuses: the singular limit belongs to the
    # delegation path, not the march.
    assert abs(X_0 - x_1e10[-1]) < abs(X_0 - x_1e9[-1])
    with pytest.raises(TEGStageError, match="no bracket"):
        countercurrent_march(1.0e-11, 82.0, X_0, 0.0, 2, teg_x_of_y(T, P))


def test_n_stages_non_integer_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    params = dict(PARAMS, n_stages=2.5)
    with pytest.raises(TEGRegenError, match="n_stages"):
        TEGRegenR2().solve({"rich_in": rich}, params, THERMO)


def test_negative_n_stages_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    with pytest.raises(TEGRegenError, match="n_stages"):
        TEGRegenR2().solve({"rich_in": rich}, dict(PARAMS, n_stages=-1), THERMO)


def test_stripping_gas_carrying_teg_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    gas = _feed({"N2": 0.995, "TEG": 0.005}, T=477.15, P=101325.0, molar_flow=2.0)
    with pytest.raises(TEGRegenError, match="stripping gas"):
        TEGRegenR2().solve({"rich_in": rich, "stripping_gas_in": gas}, dict(PARAMS), THERMO)


def test_pressure_above_water_saturation_is_refused() -> None:
    """R0's own no-boiling refusal, reached through the R2 gas path."""
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    gas = _feed({"N2": 1.0}, T=477.15, P=3.0e6, molar_flow=2.0)
    with pytest.raises(TEGRegenError, match="no boiling"):
        TEGRegenR2().solve(
            {"rich_in": rich, "stripping_gas_in": gas},
            {"T_reboiler": 477.15, "P": 3.0e6, "n_stages": 2},
            THERMO,
        )


def test_unknown_param_key_is_refused() -> None:
    rich = _feed({"TEG": 0.95, "H2O": 0.05})
    with pytest.raises(TEGRegenError, match="unknown"):
        TEGRegenR2().solve({"rich_in": rich}, dict(PARAMS, extra_key=1.0), THERMO)


# ---------------------------------------------------------------------------
# Step 2: closed-form table, monotonicity, boiling line, V0, example case.
# ---------------------------------------------------------------------------

#: Spec table (calc_teg_regen.py numbers): N, G, Y_1, lean x_H2O, lean TEG wt%.
#: S = 82.0 mol/s TEG, dry stripping gas (Y_{N+1} = 0), T_reb = 477.15 K,
#: P = 101325 Pa. The wt% column is on the databank MWs via the ratio formula
#: wt = MW_TEG / (MW_TEG + X_lean * MW_H2O); read back from the table's
#: 10-digit x column it reproduces to ~2.4e-7 relative (N = 3), so the wt%
#: assertion carries the source's own rounding at rel 1e-6.
_TABLE = [
    (1, 2.0, 1.20119822, 0.0319781273, 99.6052706),
    (2, 2.0, 1.62378146, 0.0222225357, 99.7280930),
    (3, 2.0, 1.82457116, 0.0175179409, 99.7865581),
    (4, 2.0, 1.93751541, 0.0148516561, 99.8194748),
    (2, 5.0, 0.826941334, 0.0117686245, 99.8573419),
]


@pytest.mark.parametrize(("n_stages", "g", "y1", "x_lean", "wt_pct"), _TABLE)
def test_closed_form_table(n_stages: int, g: float, y1: float, x_lean: float, wt_pct: float) -> None:
    """The march, driven directly at the table's inputs, reproduces the
    spec's columns (rel 1e-7; wt% to the x-column rounding, rel 1e-6)."""
    T, P = DEFAULT_T_REBOILER, DEFAULT_P
    x_reb = _lean_water_mole_fraction(T, P)
    X_0 = x_reb / (1.0 - x_reb)
    y_profile, x_profile = countercurrent_march(g, 82.0, X_0, 0.0, n_stages, teg_x_of_y(T, P))
    assert y_profile[0] == pytest.approx(y1, rel=1.0e-7)
    x_computed = x_profile[-1] / (1.0 + x_profile[-1])
    assert x_computed == pytest.approx(x_lean, rel=1.0e-7)
    X = x_profile[-1]
    mw_teg = _mw("TEG")
    mw_water = _mw("H2O")
    wt_computed = 100.0 * mw_teg / (mw_teg + X * mw_water)
    assert wt_computed == pytest.approx(wt_pct, rel=1.0e-6)


def test_unit_level_lean_purity_matches_the_table() -> None:
    """The R2 adapter with S = 82.0 mol/s TEG (0.82 / 0.18 at 100 mol/s),
    N = 2 and G = 2.0 mol/s dry C1 lands on the spec's 99.7280930 wt%."""
    rich = _feed({"TEG": 0.82, "H2O": 0.18})
    gas = _feed({"C1": 1.0}, T=DEFAULT_T_REBOILER, P=DEFAULT_P, molar_flow=2.0)
    result = TEGRegenR2().solve({"rich_in": rich, "stripping_gas_in": gas}, dict(PARAMS), THERMO)
    assert result.info["lean_teg_mass_fraction"] * 100.0 == pytest.approx(99.7280930, rel=1.0e-6)
    assert result.info["lean_water_mole_fraction"] == pytest.approx(0.0222225357, rel=1.0e-6)
    assert result.info["stage_1_y_H2O"] == pytest.approx(1.62378146 / (1.0 + 1.62378146), rel=1.0e-6)
    # Gas dries upward: the top stage carries less water than the bottom one.
    assert 0.0 < result.info["stage_2_y_H2O"] < result.info["stage_1_y_H2O"]


def test_boiling_line_matches_the_spec_numbers() -> None:
    """R0 identity at the spec's printed values: Psat = 1689056.3499963796 Pa,
    x_reb = 0.058674712754515884, gamma at x_reb = 1.0224015555612633."""
    T, P = DEFAULT_T_REBOILER, DEFAULT_P
    x_reb = _lean_water_mole_fraction(T, P)
    assert x_reb == pytest.approx(0.058674712754515884, rel=1.0e-12)
    slope_reb = activity_equilibrium_slope(T, P, x_reb)
    assert slope_reb * x_reb == pytest.approx(1.0, abs=1.0e-10)
    psat = activity_equilibrium_slope(T, P, 1.0 - 1.0e-9) * P
    assert psat == pytest.approx(1689056.3499963796, rel=1.0e-12)
    assert slope_reb * P / psat == pytest.approx(1.0224015555612633, rel=1.0e-12)


def test_purity_increases_strictly_with_stages_and_gas() -> None:
    """Physics direction: lean TEG wt% rises strictly with N at fixed G and
    with G at fixed N (all five from the spec table)."""
    wt_by_n = {row[0]: row[4] for row in _TABLE if row[1] == 2.0}
    assert wt_by_n[1] < wt_by_n[2] < wt_by_n[3] < wt_by_n[4]
    wt_by_g = {row[1]: row[4] for row in _TABLE if row[0] == 2}
    assert wt_by_g[2.0] < wt_by_g[5.0]


def test_v0_balances_close_on_the_example_case() -> None:
    """Total moles, per-component flows and energy close at 1e-8 on the
    adapter's own example basis (the V0 rule)."""
    feeds, params = TEGRegenR2.example_case()
    inlets = {
        name: THERMO.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for name, f in feeds.items()
    }
    result = TEGRegenR2().solve(inlets, params, THERMO)
    flow_in = sum(s.molar_flow for s in inlets.values())
    flow_out = sum(o.molar_flow for o in result.outlets.values())
    assert flow_out == pytest.approx(flow_in, rel=1.0e-8)

    def _component(state: Any, cid: str) -> float:
        return float(state.composition.get(cid, 0.0) * state.molar_flow)

    for cid in ("TEG", "H2O", "C1"):
        n_in = sum(_component(s, cid) for s in inlets.values())
        n_out = sum(_component(o, cid) for o in result.outlets.values())
        assert n_out == pytest.approx(n_in, rel=1.0e-8), cid

    h_in = sum(s.enthalpy * s.molar_flow for s in inlets.values())
    h_out = sum(o.enthalpy * o.molar_flow for o in result.outlets.values())
    assert h_out == pytest.approx(h_in + result.duty_W, rel=1.0e-8)

    # And the reported stage count / gas flow echo the example params.
    assert result.info["n_stages"] == 2.0
    assert result.info["stripping_gas_mol_s"] == 2.0
    assert result.info["activity_extrapolated"] == 1.0


def test_purity_enhancement_over_the_boiling_line_is_reported() -> None:
    """The R2 lean sits above the R0 boiling-line value by the computed
    enhancement (N = 2, G = 2: 99.7280930 vs 99.2577928 wt%)."""
    rich = _feed({"TEG": 0.82, "H2O": 0.18})
    gas = _feed({"C1": 1.0}, T=DEFAULT_T_REBOILER, P=DEFAULT_P, molar_flow=2.0)
    result = TEGRegenR2().solve({"rich_in": rich, "stripping_gas_in": gas}, dict(PARAMS), THERMO)
    assert result.info["lean_teg_mass_fraction_boiling_line"] * 100.0 == pytest.approx(
        99.25779284649195, rel=1.0e-7
    )
    assert result.info["purity_enhancement_wt_pct"] == pytest.approx(
        99.7280930 - 99.25779284649195, abs=1.0e-6
    )
    assert result.info["stage_1_x_H2O"] > 0.0222225357
    assert result.info["stage_2_x_H2O"] == pytest.approx(0.0222225357, rel=1.0e-6)
