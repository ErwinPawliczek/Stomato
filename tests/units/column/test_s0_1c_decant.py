"""Total-condenser free-water decant (S0-1c step 4).

The case: a 10-stage nC6/nC8/nC10/nC12 column at 2 bar carrying 10 % water
in its feed (a wet naphtha-gas-oil cut), a 4-stage steam stripper on stage 4
and a total condenser. The overhead vapour holds more water than the
hydrocarbon condensate can dissolve at the stage-1 temperature, so the decant
draws the excess off as free water and the reflux/distillate carry the
saturated hydrocarbon liquid only - inside the condenser stage balance.

Independent checks, from the reported result and fresh thermo calls only:

- the distillate's water sits exactly at saturation: its water fugacity
  equals pure liquid water's at the stage-1 state (Michelsen's pure-water
  tangent plane at zero);
- the condenser closes: V_1 y_1 = (L_0 + D) x_D + W per component;
- the whole unit closes in components and energy at 1e-8, with the
  condenser and kettle duties recomputed from their own stage balances.

Specs distillate_rate + boilup_rate: one secant tear (the reflux), the
boilup pinned. Measured ~13-25 s serial.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column import ColumnSpecError, solve_column_full
from tests.units.column.test_s0_1c_strippers import _comps, _h, _stage, fugacity_equilibrium

P = 2.0e5
FEED = {"nC6": 0.225, "nC8": 0.225, "nC10": 0.225, "nC12": 0.225, "H2O": 0.10}


def _params(decant: bool) -> dict[str, Any]:
    return {
        "n_stages": 10,
        "condenser": "total",
        "reboiler": "kettle",
        "pressure_profile": P,
        "feeds": [{"stage": 6, "T": 400.0, "P": P, "molar_flow": 100.0, "composition": dict(FEED)}],
        "specs": {"distillate_rate": 25.0, "boilup_rate": 70.4},
        "condenser_water_decant": decant,
        "side_strippers": [
            {
                "name": "s1",
                "draw_stage": 4,
                "return_stage": 3,
                "n_stages": 4,
                "steam": {"flow_mol_s": 2.0, "T_K": 450.0, "P_Pa": P},
                "product_rate_mol_s": 20.0,
            }
        ],
    }


@pytest.fixture(scope="module")
def decanted(thermo: Thermo) -> tuple[UnitResult, dict[str, StreamState]]:
    return solve_column_full({}, _params(True), thermo)


def test_decant_draws_the_free_water_and_closes(
    decanted: tuple[UnitResult, dict[str, StreamState]], thermo: Thermo
) -> None:
    """The steam-stripped column with the decant converges, draws free water,
    and closes the condenser and the whole unit at 1e-8 (measured: whole-unit
    component 1e-16 scale, energy 1e-15 scale, condenser per-component 1e-15
    scale)."""
    r, internal = decanted
    info = r.info
    comps = _comps(info)
    w = info["water_decant_mol_s"]
    d = info["distillate_mol_s"]
    assert w > 1.0, w
    assert d == pytest.approx(25.0, rel=5e-3)
    s0 = _stage(info, 0, comps)
    x_d = dict(r.outlets["distillate"].composition)
    l0 = info["reflux_ratio"] * d
    # Condenser balance per component: V_1 y_1 = (L_0 + D) x_D + W (pure water).
    for c in comps:
        out = (l0 + d) * x_d.get(c, 0.0) + (w if c == "H2O" else 0.0)
        assert abs(s0["V"] * s0["y"][c] - out) <= 1e-8 * s0["V"], c
    # The distillate carries exactly the water the hydrocarbon liquid holds at
    # saturation at the stage-1 state: water fugacity = pure liquid water's.
    ln_phi = thermo.phase_props(x_d, s0["T"], s0["P"], PhaseKind.HC_LIQUID).ln_phi
    pure = thermo.phase_props({"H2O": 1.0}, s0["T"], s0["P"], PhaseKind.AQUEOUS).ln_phi
    assert abs(math.log(x_d["H2O"]) + ln_phi["H2O"] - pure["H2O"]) < 1e-9
    # Every stage at equilibrium (fugacity equality), main and section.
    assert fugacity_equilibrium(r, thermo) < 1e-6

    # Whole unit, independently: feeds + steam + stage-balance duties =
    # distillate + decant + bottoms + stripper product.
    n = 10
    st = [_stage(info, j, comps) for j in range(int(info["n_graph_stages"]))]
    hl = [_h(thermo, s["x"], s["T"], s["P"], PhaseKind.HC_LIQUID) for s in st]
    hv = [_h(thermo, s["y"], s["T"], s["P"], PhaseKind.VAPOR) for s in st]
    h_feed = thermo.flash_pt(FEED, 400.0, P, 100.0).enthalpy * 100.0
    h_steam = thermo.flash_pt({"H2O": 1.0}, 450.0, P, 2.0).enthalpy * 2.0
    h_xd = _h(thermo, x_d, s0["T"], s0["P"], PhaseKind.HC_LIQUID)
    h_w = thermo.phase_props({"H2O": 1.0}, s0["T"], s0["P"], PhaseKind.HC_LIQUID).enthalpy
    q_cond = s0["V"] * hv[0] - (l0 + d) * h_xd - w * h_w
    q_reb = st[n - 1]["V"] * hv[n - 1] + st[n - 1]["L"] * hl[n - 1] - st[n - 2]["L"] * hl[n - 2]
    b = info["bottoms_mol_s"]
    prod = info["stripper_s1_product_mol_s"]
    h_out = d * h_xd + w * h_w + b * hl[n - 1] + prod * hl[13]
    e_rel = abs(h_feed + h_steam + q_reb - q_cond - h_out) / max(abs(h_feed), abs(h_out), q_reb, q_cond)
    assert e_rel < 1e-8, e_rel
    m_in = {c: 100.0 * FEED.get(c, 0.0) + (2.0 if c == "H2O" else 0.0) for c in comps}
    m_out = {
        c: d * x_d.get(c, 0.0) + (w if c == "H2O" else 0.0) + b * st[n - 1]["x"][c] + prod * st[13]["x"][c]
        for c in comps
    }
    m_rel = max(abs(m_in[c] - m_out[c]) for c in comps) / 102.0
    assert m_rel < 1e-8, m_rel
    # The reported condenser duty is its stage balance. The reported reboiler
    # duty closes the boundary stream table, whose distillate and decant are
    # reported at the condensate's bubble point (the total condenser's
    # product state) rather than at the stage-1 state of the condenser
    # balance: it differs from the kettle's stage balance by exactly that
    # product-state enthalpy (measured ~3e5 W here), to 1e-8.
    assert info["condenser_duty_W"] == pytest.approx(q_cond, rel=1e-8)
    dist, dec = r.outlets["distillate"], internal["water_decant"]
    shift = d * dist.enthalpy + w * dec.enthalpy - d * h_xd - w * h_w
    assert info["reboiler_duty_W"] - q_reb == pytest.approx(shift, rel=1e-8, abs=1e-8 * q_reb)
    assert dec.T == dist.T and dec.composition == {"H2O": 1.0} and dec.molar_flow == w
    assert internal["s1"].molar_flow == pytest.approx(20.0, rel=1e-12)


def test_decant_off_with_free_water_refuses(thermo: Thermo) -> None:
    """The same column without the decant must return its condensate water as
    reflux, which supersaturates the top tray: the typed free-water refusal
    naming stage 1. It is reached on the graph Newton's best iterate (measured
    M = 0.29 after the pass budget: the one-liquid column has no solution
    there), not after convergence - the physical verdict, typed, instead of a
    convergence error. ~25 s."""
    with pytest.raises(ColumnSpecError, match="free water on stage 1"):
        solve_column_full({}, _params(False), thermo)
