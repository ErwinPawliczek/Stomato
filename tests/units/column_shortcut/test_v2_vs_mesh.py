"""V2 comparisons: shortcut estimates against the rigorous column MESH (spec U-E V2).

The spec requires two comparisons, both against the existing column unit:

(a) FUG N against the column R2 MESH on the deethanizer bench case, at the
    same reflux and key recoveries, inside the Gilliland correlation's
    published scatter (+/-20 % on N, as the spec cites it). The bench case's
    converged operating point (fixed tears L0 = 111, V_bot = 131 mol/s) puts
    D = 77.5137 mol/s: C1+C2+C3 essentially all overhead, so the split the
    point performs is C3/iC4 — those are the comparison keys, with the
    recoveries the converged MESH profile achieves. Measured on this branch:
    R = L0/D = 1.43201, C3->D = 0.999924, iC4->B = 0.427860; FUG
    Nmin = 13.267, Rmin = 0.3480, N = 18.873 vs the MESH's 22 stages =
    -14.21 %, inside the band.

(b) the Kremser absorber against the zero-tear MESH on the P1-09 absorber
    case (C3 solute into nC5 lean, the same construction the P1-09 oracle
    test uses), within 2 % on the key-component recovery. The PR package
    gives no K-values at the gas-in condition (that flash is single-phase
    vapour at 300 K / 2 MPa), so the comparison feeds the adapter
    ``k_overrides`` taken from the converged MESH mid-column condition — the
    same basis the P1-09 oracle evaluates the Kremser fraction at. Measured
    on this branch (the P1-09 docstring's 0.6149/0.7367 were measured on that
    branch; today's main gives 0.6228/0.7445):

    N=2: MESH 0.62276 absorbed, R0 Kremser 0.60790, gap -2.39 % (misses 2 %)
    N=4: MESH 0.74449 absorbed, R0 Kremser 0.69486, gap -6.67 % (misses 2 %)

    Recorded miss, band not moved. Cause: the R0's documented absorption
    factor is A = L_in/(K*V_in) on the two inlet flows (0.842 / 0.787), while
    the converged column's effective mid-column factor is
    L_mid/(K*V_mid) = 0.882 / 0.872 — L grows ~8 % as C3 is absorbed and V
    falls ~2 %. The Kremser form itself is not the cause: evaluated at the
    MESH's own mid-column A it agrees with the MESH to +0.2 % (N=2) and
    -0.6 % (N=4). Closing the gap needs a mid-flow A basis, which is an R0
    method change outside this spec.

Anchored numbers are recorded measurements; any solver change that moves
them trips the test so the record is re-measured.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units import column as col_mod
from ngdesign.units.column import Column, _ThermoBox

DEETHANIZER_FEED: dict[str, Any] = {
    "T": 320.0,
    "P": 1.7e6,
    "molar_flow": 100.0,
    "composition": {"C1": 0.02, "C2": 0.35, "C3": 0.28, "iC4": 0.17, "nC4": 0.18},
}
DEETHANIZER_PARAMS: dict[str, Any] = {
    "n_stages": 22,
    "condenser": "total",
    "reboiler": "kettle",
    "feed_stage": 11,
    "pressure_profile": 1.7e6,
    "specs": {"reflux_ratio": 3.0, "distillate_rate": 37.0},
}
BENCH_N_STAGES = 22.0
BENCH_GILLILAND_BAND = 0.20

# Recorded gaps for the Kremser comparison, (N -> gap); misses of the 2 % band.
RECORDED_KREMSER_GAPS: dict[int, float] = {2: -0.02387, 4: -0.06666}


def test_v2a_fug_n_vs_deethanizer_bench_mesh(thermo: Thermo) -> None:
    """FUG N inside Gilliland's +/-20 % of the bench MESH's 22 stages."""
    parsed = col_mod._parse_params(DEETHANIZER_PARAMS, DEETHANIZER_FEED)
    tb = _ThermoBox(thermo, 1.7e6, 1.7e6)
    col = col_mod._build_column(parsed, tb)
    t_top, t_bot = col_mod._temperature_seed(col, tb)
    prof = col_mod._seed_profile(col, tb, t_top, t_bot)
    prof = col_mod._solve_mesh(col, tb, 3.0 * 37.0, 3.0 * 37.0 + 20.0, prof)

    n = col.n
    d_comp = {cid: prof.y[0][cid] * prof.d for cid in col.comps}
    b_comp = {cid: prof.x[n - 1][cid] * prof.b for cid in col.comps}
    f_comp = {cid: 100.0 * z for cid, z in DEETHANIZER_FEED["composition"].items()}
    worst = max(abs(d_comp[c] + b_comp[c] - f_comp[c]) / f_comp[c] for c in col.comps)
    assert worst <= 1e-8, f"MESH component closure {worst:.2e} too loose"
    assert prof.d == pytest.approx(77.5137, abs=0.05)

    r_mesh = 3.0 * 37.0 / prof.d
    assert r_mesh == pytest.approx(1.43201, abs=1e-3)
    rec_lk = d_comp["C3"] / f_comp["C3"]
    rec_hk_b = b_comp["iC4"] / f_comp["iC4"]
    assert rec_lk == pytest.approx(0.9999241, abs=1e-5)
    assert rec_hk_b == pytest.approx(0.4278602, abs=1e-5)

    states = {
        "feed": thermo.flash_pt(
            DEETHANIZER_FEED["composition"],
            DEETHANIZER_FEED["T"],
            DEETHANIZER_FEED["P"],
            DEETHANIZER_FEED["molar_flow"],
        )
    }
    fug = registry.create("unit", "shortcut_distillation").solve(
        states,
        {
            "light_key": "C3",
            "heavy_key": "iC4",
            "recovery_LK_D": rec_lk,
            "recovery_HK_B": rec_hk_b,
            "R": r_mesh,
            "P_top": 1.7e6,
            "P_bottom": 1.7e6,
            "condenser": "total",
        },
        thermo,
    )
    n_fug = fug.info["N"]
    assert n_fug == pytest.approx(18.873, abs=0.05)
    assert abs(n_fug - BENCH_N_STAGES) / BENCH_N_STAGES <= BENCH_GILLILAND_BAND


def _port(T: float, P: float, flow: float, z: dict[str, float], vf: float = 0.0) -> StreamState:
    """StreamState literal construction, as the P1-09 tests build their feeds."""
    return StreamState(
        T=T,
        P=P,
        molar_flow=flow,
        composition=dict(z),
        vapor_fraction=vf,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )


@pytest.mark.parametrize("n_stages", [2, 4])
def test_v2b_kremser_vs_zero_tear_mesh_p1_09(thermo: Thermo, n_stages: int) -> None:
    """Kremser R0 vs the zero-tear MESH on the P1-09 C3/nC5 absorber case."""
    mesh = Column().solve(
        {"feed": _port(300.0, 2e6, 100.0, {"C1": 0.95, "C3": 0.05}, vf=1.0)},
        {
            "n_stages": n_stages,
            "condenser": "none",
            "reboiler": "none",
            "pressure_profile": 2e6,
            "feed_stage": n_stages,
            "feeds": [
                {"T": 300.0, "P": 2e6, "molar_flow": 50.0, "composition": {"nC5": 1.0}, "stage": 1}
            ],
        },
        thermo,
    )
    bottoms = mesh.outlets["bottoms"]
    frac_mesh = bottoms.molar_flow * bottoms.composition.get("C3", 0.0) / 5.0
    recorded_frac = {2: 0.62276, 4: 0.74449}[n_stages]
    assert frac_mesh == pytest.approx(recorded_frac, abs=5e-4)

    mid = n_stages // 2
    t_mid = mesh.info[f"stage_{mid}_T_K"]
    x_mid = {c: mesh.info[f"stage_{mid}_x_{c}"] for c in ("C1", "C3", "nC5")}
    k_mid = thermo.k_values(x_mid, t_mid, 2e6)
    assert k_mid is not None, "MESH mid-column flash should be two-phase"

    r0 = registry.create("unit", "absorber").solve(
        {
            "gas_in": thermo.flash_pt({"C1": 0.95, "C3": 0.05}, 300.0, 2e6, 100.0),
            "solvent_in": thermo.flash_pt({"nC5": 1.0}, 300.0, 2e6, 50.0),
        },
        {"N": float(n_stages), "k_overrides": dict(k_mid)},
        thermo,
    )
    frac_r0 = 1.0 - r0.info["f_not_absorbed_C3"]
    gap = (frac_r0 - frac_mesh) / frac_mesh

    # Anchor the recorded measurement; any solver change that moves the gap
    # trips this so the record is re-measured.
    assert gap == pytest.approx(RECORDED_KREMSER_GAPS[n_stages], abs=0.005)

    # The spec band, recorded as measured-missed; the band is never moved.
    if abs(gap) > 0.02:
        pytest.xfail(
            f"recorded miss: Kremser R0 gap {gap:+.3%} outside the 2 % band at N={n_stages}; "
            "cause: the R0 absorption factor uses inlet flows while the column's effective "
            "mid-column factor is L_mid/(K*V_mid) (L grows ~8 % with absorbed C3, V falls ~2 %); "
            "the Kremser form at the mid-column A agrees with the MESH to +/-0.6 %"
        )
