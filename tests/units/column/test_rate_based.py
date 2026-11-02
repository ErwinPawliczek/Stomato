"""Rate-based (R3) absorber and reboiled stripper: independent checks.

Oracles:
1. equilibrium limit - as ``transfer_factor`` grows the rate-based column must reduce
   to the R2 MESH column on the same stages (stated tolerances below, measured values
   in comments);
2. per-stage component and energy closure recomputed from the reported profile with
   the package's own ``phase_props`` enthalpies (not the solver's frozen models);
3. interface equilibrium recomputed from the package fugacity coefficients;
4. Murphree vapour efficiencies within (0, 1) for finite rates and rising towards 1.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column.rate_based_transport import (
    ComponentTransport,
    chapman_enskog,
    component_transport,
)
from ngdesign.units.column.rate_based_units import AbsorberR3, RateBasedSpecError, ReboiledStripperR3
from ngdesign.units.column_shortcut.absorber_r2 import AbsorberR2
from ngdesign.units.column_shortcut.reboiled_stripper_r2 import ReboiledStripperR2
from tests.conftest import flash_feed


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> dict[str, StreamState]:
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-12)


def _cids(info: dict[str, float], j: int) -> list[str]:
    prefix = f"stage_{j}_y_"
    return [k[len(prefix) :] for k in info if k.startswith(prefix)]


# --------------------------------------------------------------------------------------
# 1. Equilibrium limit
# --------------------------------------------------------------------------------------


def test_absorber_reduces_to_r2_as_transfer_grows(thermo: Thermo) -> None:
    feeds, params = AbsorberR3.example_case()
    inlets = _inlets(thermo, feeds)
    r2 = AbsorberR2().solve(inlets, {"n_stages": params["n_stages"]}, thermo)
    devs = []
    for factor in (1e2, 1e4):
        r3 = AbsorberR3().solve(inlets, {**params, "transfer_factor": factor}, thermo)
        dev = 0.0
        for port in ("gas_out", "rich_out"):
            a, b = r3.outlets[port], r2.outlets[port]
            dev = max(dev, _rel(a.molar_flow, b.molar_flow))
            for cid, frac in b.composition.items():
                dev = max(dev, abs(a.composition[cid] - frac))
            assert abs(a.T - b.T) < (0.5 if factor < 1e3 else 0.01)
        devs.append(dev)
    # measured: 2e-4 at 1e2, 1.8e-7 at 1e4 (flows and mole fractions)
    assert devs[1] < 1e-5
    assert devs[1] < devs[0]


def test_stripper_reduces_to_r2_as_transfer_grows(thermo: Thermo) -> None:
    feeds, params = ReboiledStripperR3.example_case()
    inlets = _inlets(thermo, feeds)
    r2 = ReboiledStripperR2().solve(inlets, {"n_stages": 3, "spec": {"boilup_ratio": 0.2}}, thermo)
    # R2 meets its spec only to the column core's loose spec gate (issue 248):
    # measured boilup 0.20049. Compare the same physical column - R3 on R2's achieved
    # boilup - so the oracle measures the stage model, not R2's spec tolerance.
    boilup = r2.info["boilup_ratio"]
    r3 = ReboiledStripperR3().solve(
        inlets, {**params, "spec": {"boilup_ratio": boilup}, "transfer_factor": 1e4}, thermo
    )
    for port in ("overhead", "bottoms"):
        a, b = r3.outlets[port], r2.outlets[port]
        assert _rel(a.molar_flow, b.molar_flow) < 1e-4  # measured 7e-7 (overhead)
        assert abs(a.T - b.T) < 0.01
        for cid, frac in b.composition.items():
            assert abs(a.composition[cid] - frac) < 1e-4
    assert _rel(r3.info["reboiler_duty_W"], r2.info["reboiler_duty_W"]) < 1e-4  # measured 1e-6


# --------------------------------------------------------------------------------------
# 2. Stage closure with the package enthalpies; 3. interface equilibrium
# --------------------------------------------------------------------------------------


def _h(thermo: Thermo, info: dict[str, float], j: int, phase: str, cids: list[str], P: float) -> float:
    """Enthalpy flow (W) of one stage's leaving phase from a fresh phase_props build."""
    key = "y" if phase == "V" else "x"
    comp = {c: info[f"stage_{j}_{key}_{c}"] for c in cids}
    s = sum(comp.values())
    comp = {c: v / s for c, v in comp.items()}
    T = info[f"stage_{j}_T{phase}_K"]
    kind = PhaseKind.VAPOR if phase == "V" else PhaseKind.HC_LIQUID
    return info[f"stage_{j}_{phase}_mol_s"] * thermo.phase_props(comp, T, P, kind).enthalpy


def _flows(info: dict[str, float], j: int, phase: str, cids: list[str]) -> dict[str, float]:
    key = "y" if phase == "V" else "x"
    return {c: info[f"stage_{j}_{phase}_mol_s"] * info[f"stage_{j}_{key}_{c}"] for c in cids}


def test_absorber_stage_closure_and_interface(thermo: Thermo) -> None:
    feeds, params = AbsorberR3.example_case()
    inlets = _inlets(thermo, feeds)
    res = AbsorberR3().solve(inlets, params, thermo)
    info = res.info
    n = params["n_stages"]
    cids = _cids(info, 0)
    P = 2e6
    gas, solvent = inlets["gas_in"], inlets["solvent_in"]
    f_tot = gas.molar_flow + solvent.molar_flow
    for j in range(n):
        v_in = _flows(info, j + 1, "V", cids) if j + 1 < n else gas.component_flows()
        l_in = _flows(info, j - 1, "L", cids) if j > 0 else solvent.component_flows()
        v_out, l_out = _flows(info, j, "V", cids), _flows(info, j, "L", cids)
        for c in cids:
            flux = info[f"stage_{j}_N_{c}_mol_s"]
            # separate vapour and liquid balances, coupled only by the flux
            assert abs(v_out[c] - v_in.get(c, 0.0) + flux) < 1e-7 * f_tot
            assert abs(l_out[c] - l_in.get(c, 0.0) - flux) < 1e-7 * f_tot
        h_v_in = _h(thermo, info, j + 1, "V", cids, P) if j + 1 < n else gas.molar_flow * gas.enthalpy
        h_l_in = _h(thermo, info, j - 1, "L", cids, P) if j > 0 else solvent.molar_flow * solvent.enthalpy
        h_v, h_l = _h(thermo, info, j, "V", cids, P), _h(thermo, info, j, "L", cids, P)
        scale = abs(h_v_in) + abs(h_l_in)
        e = info[f"stage_{j}_energy_flux_W"]
        assert abs(h_v + h_l - h_v_in - h_l_in) < 1e-7 * scale  # stage energy
        assert abs(h_v - h_v_in + e) < 1e-7 * scale  # vapour-side energy with E
        # interface equilibrium: yI = (phi_L(xI)/phi_V(yI)) xI at T_I
        xi = {c: info[f"stage_{j}_xI_{c}"] for c in cids}
        yi = {c: info[f"stage_{j}_yI_{c}"] for c in cids}
        ti = info[f"stage_{j}_TI_K"]
        pl = thermo.phase_props(xi, ti, P, PhaseKind.HC_LIQUID)
        pv = thermo.phase_props(yi, ti, P, PhaseKind.VAPOR)
        for c in cids:
            assert yi[c] == pytest.approx(math.exp(pl.ln_phi[c] - pv.ln_phi[c]) * xi[c], rel=1e-7)
    # the outlet flash adds at most a round-off-scale boundary residual (duty_W)
    assert info["energy_residual_rel"] < 1e-8


def test_stripper_kettle_and_stage_closure(thermo: Thermo) -> None:
    feeds, params = ReboiledStripperR3.example_case()
    inlets = _inlets(thermo, feeds)
    res = ReboiledStripperR3().solve(inlets, params, thermo)
    info = res.info
    n = params["n_stages"]
    cids = _cids(info, 0)
    P = feeds["feed"]["P"]
    feed = inlets["feed"]
    assert info["boilup_ratio"] == pytest.approx(0.2, rel=1e-8)
    # kettle: liquid in = vapour + bottoms out; energy closes on the reported duty
    l_in = _flows(info, n - 2, "L", cids)
    v_k, l_k = _flows(info, n - 1, "V", cids), _flows(info, n - 1, "L", cids)
    for c in cids:
        assert abs(l_in[c] - v_k[c] - l_k[c]) < 1e-7 * feed.molar_flow
    h_k = _h(thermo, info, n - 1, "V", cids, P) + _h(thermo, info, n - 1, "L", cids, P)
    h_in = _h(thermo, info, n - 2, "L", cids, P)
    assert h_k - h_in == pytest.approx(info["reboiler_duty_W"], rel=1e-6)
    assert abs(info["energy_residual_W"]) < 1e-6 * abs(info["reboiler_duty_W"])
    # top segment energy (feed liquid in, vapour from segment 2)
    h_top = _h(thermo, info, 0, "V", cids, P) + _h(thermo, info, 0, "L", cids, P)
    h_top_in = feed.molar_flow * feed.enthalpy + _h(thermo, info, 1, "V", cids, P)
    assert abs(h_top - h_top_in) < 1e-7 * abs(h_top_in)


# --------------------------------------------------------------------------------------
# 4. Murphree efficiencies
# --------------------------------------------------------------------------------------


def _effs(info: dict[str, float]) -> list[float]:
    return [v for k, v in info.items() if "_EMV_" in k]


@pytest.mark.parametrize("unit", [AbsorberR3, ReboiledStripperR3])
def test_murphree_between_zero_and_one_and_rising(thermo: Thermo, unit: Any) -> None:
    feeds, params = unit.example_case()
    inlets = _inlets(thermo, feeds)
    means = []
    for factor in (0.1, 1.0, 1e4):
        effs = _effs(unit().solve(inlets, {**params, "transfer_factor": factor}, thermo).info)
        assert effs
        if factor < 10:
            assert all(0.0 < e < 1.0 for e in effs), effs  # measured 0.02-0.84
        else:
            assert all(abs(e - 1.0) < 1e-3 for e in effs), effs
        means.append(sum(effs) / len(effs))
    assert means[0] < means[1] < means[2]


# --------------------------------------------------------------------------------------
# Specs, refusals, transport
# --------------------------------------------------------------------------------------


def test_stripper_duty_and_distillate_specs_round_trip(thermo: Thermo) -> None:
    feeds, params = ReboiledStripperR3.example_case()
    inlets = _inlets(thermo, feeds)
    base = ReboiledStripperR3().solve(inlets, params, thermo)
    q = base.info["reboiler_duty_W"]
    by_q = ReboiledStripperR3().solve(inlets, {**params, "spec": {"reboiler_duty_W": q}}, thermo)
    assert by_q.info["boilup_ratio"] == pytest.approx(0.2, rel=1e-6)
    d = base.outlets["overhead"].molar_flow
    by_d = ReboiledStripperR3().solve(inlets, {**params, "spec": {"distillate_rate": d}}, thermo)
    assert by_d.info["boilup_ratio"] == pytest.approx(0.2, rel=1e-6)


@pytest.mark.parametrize(
    ("unit", "patch"),
    [
        (AbsorberR3, {"n_stages": 0}),
        (AbsorberR3, {"bogus": 1}),
        (AbsorberR3, {"surface_tension_N_m": -1.0}),
        (AbsorberR3, {"pressure_profile": [2e6, 2e6]}),
        (ReboiledStripperR3, {"n_stages": 1}),
        (ReboiledStripperR3, {"spec": {"component_recovery": 0.9}}),
        (ReboiledStripperR3, {"spec": {"boilup_ratio": 0.2, "bottoms_rate": 1.0}}),
        (ReboiledStripperR3, {"spec": {"bottoms_rate": 1e3}}),
    ],
)
def test_refusals(thermo: Thermo, unit: Any, patch: dict[str, Any]) -> None:
    feeds, params = unit.example_case()
    with pytest.raises(RateBasedSpecError):
        unit().solve(_inlets(thermo, feeds), {**params, **patch}, thermo)


def test_chapman_enskog_matches_poling_bar_form() -> None:
    """BSL eq. 17.3-12 (atm) equals Poling-Prausnitz-O'Connell eq. 11-3.2 (bar,
    0.00266, M_AB = 2/(1/M_A + 1/M_B)) - both forms read from their sources."""
    from chemicals.lennard_jones import collision_integral_Neufeld_Janzen_Aziz

    a, b = component_transport("C1"), component_transport("NC4")
    T, P = 320.0, 5e5
    sigma = 0.5 * (a.sigma_lj + b.sigma_lj)
    omega = collision_integral_Neufeld_Janzen_Aziz(T / math.sqrt(a.eps_k * b.eps_k), 1, 1)
    m_ab = 2.0 / (1.0 / a.mw + 1.0 / b.mw)
    poling = 0.00266 * T**1.5 / ((P / 1e5) * math.sqrt(m_ab) * sigma**2 * omega) * 1e-4
    assert chapman_enskog(T, P, a, b) == pytest.approx(poling, rel=2e-3)
    assert isinstance(a, ComponentTransport)
