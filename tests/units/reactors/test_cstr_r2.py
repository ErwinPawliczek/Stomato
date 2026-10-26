"""Closed-form and consistency tests for the kinetic CSTR, level R2
(units/cstr.md, tests).

R2 consistency — no printed closed form exists for a VLE CSTR, so the test
recomputes the rate independently of the adapter: the isothermal two-phase
case solves to an extent xi with |nu|·xi = V_L·r, where V_L is the reacting
(hc_liquid) phase's holdup volume and r = k·x_nC5·c_L its first-order rate,
both recomputed from the returned outlet's own liquid ``Phase``. Tolerance
1e-9 relative.

Identity — R2 reduces to R1 on a single-phase vessel: with one phase present
V_k = V_r exactly, and the residuals (hence the solution) match R1 to 1e-12.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R, enthalpy_with_formation
from ngdesign.units.reactors.cstr import CstrError, CstrR1, CstrR2
from tests.conftest import flash_feed


def _r2_params(volume_m3: float = 0.5, **overrides: Any) -> dict[str, Any]:
    """The two-phase R2 basis: liquid nC5 -> iC5 beside a C1 vapour phase."""
    _feeds, params = CstrR2.example_case()
    params["volume_m3"] = volume_m3
    params.update(overrides)
    return params


def _r2_inlet(thermo: Thermo) -> Any:
    feeds, _params = CstrR2.example_case()
    return flash_feed(thermo, feeds["inlet"])


def test_r2_two_phase_consistency(thermo: Thermo) -> None:
    """|nu|·xi_reported = V_L·r with V_L and r recomputed from the outlet's
    own liquid Phase (units/cstr.md, R2 closed-form-equivalent)."""
    result = CstrR2().solve({"inlet": _r2_inlet(thermo)}, _r2_params(), thermo)
    outlet = result.outlets["outlet"]

    # The vessel is genuinely two-phase at the solution.
    assert 0.0 < outlet.vapor_fraction < 1.0
    liquid = [p for p in outlet.phases if p.kind == "hc_liquid"][0]
    total = outlet.molar_flow

    # Independent recomputation from the returned outlet's own liquid Phase:
    # V_L = V·(n_L·MW_L/rho_L)/sum_p(n_p·MW_p/rho_p), r = k(T)·x_nC5·c_L with
    # c_L = 1000·rho_L/MW_L (mol/m3) and k = k0·exp(-Ea/(R·T)) = k0 here.
    phase_volumes = [total * p.mole_fraction * p.molecular_weight / p.density for p in outlet.phases]
    li = [i for i, p in enumerate(outlet.phases) if p.kind == "hc_liquid"][0]
    v_l = 0.5 * phase_volumes[li] / math.fsum(phase_volumes)
    c_l = 1000.0 * liquid.density / liquid.molecular_weight
    k = 2.0e-4 * math.exp(-0.0 / (R * outlet.T))
    r_rate = k * liquid.composition["nC5"] * c_l

    xi = result.info["extent_isom_mol_s"]
    assert math.isclose(1.0 * xi, v_l * r_rate, rel_tol=1e-9)
    # And the outlet composition matches the extent: nC5 = 0.7 - xi.
    n_out = outlet.component_flows()
    assert math.isclose(n_out["nC5"], 0.7 - xi, rel_tol=1e-9)
    assert math.isclose(n_out["iC5"], xi, rel_tol=1e-9)


def test_r2_reduces_to_r1_single_phase(thermo: Thermo) -> None:
    """On a single-phase liquid vessel R2 equals R1 to 1e-12 relative: the
    flash gives one hc_liquid phase, so V_k = V_r and the residuals coincide."""
    _feeds, params = CstrR1.example_case()
    liquid_r1 = dict(params)
    liquid_r1["reacting_phase"] = "liquid"
    feed = {"T": 300.0, "P": 3.0e6, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)  # subcooled liquid nC4 at 300 K

    r1 = CstrR1().solve({"inlet": inlet}, liquid_r1, thermo)
    r2 = CstrR2().solve({"inlet": inlet}, {**liquid_r1, "reacting_phase": "hc_liquid"}, thermo)

    assert r2.info["extent_isom_mol_s"] == pytest.approx(r1.info["extent_isom_mol_s"], rel=1e-12)
    r1_out = r1.outlets["outlet"].component_flows()
    r2_out = r2.outlets["outlet"].component_flows()
    for cid, flow in r1_out.items():
        assert r2_out[cid] == pytest.approx(flow, rel=1e-12)


def test_r2_holdup_override(thermo: Thermo) -> None:
    """holdup_m3 replaces the phase-ratio holdup: setting it to the solved
    phase-ratio V_L reproduces the same extent, a smaller holdup converts less."""
    solved = CstrR2().solve({"inlet": _r2_inlet(thermo)}, _r2_params(), thermo)
    outlet = solved.outlets["outlet"]
    total = outlet.molar_flow
    phase_volumes = [total * p.mole_fraction * p.molecular_weight / p.density for p in outlet.phases]
    li = [i for i, p in enumerate(outlet.phases) if p.kind == "hc_liquid"][0]
    v_l = 0.5 * phase_volumes[li] / math.fsum(phase_volumes)

    equal = CstrR2().solve({"inlet": _r2_inlet(thermo)}, _r2_params(holdup_m3=v_l), thermo)
    assert equal.info["extent_isom_mol_s"] == pytest.approx(solved.info["extent_isom_mol_s"], rel=1e-9)

    smaller = CstrR2().solve({"inlet": _r2_inlet(thermo)}, _r2_params(holdup_m3=v_l / 2.0), thermo)
    assert smaller.info["extent_isom_mol_s"] < solved.info["extent_isom_mol_s"] * 0.75


def test_r2_absent_reacting_phase_rate_zero(thermo: Thermo) -> None:
    """A reacting phase absent from the vessel gives rate 0: the outlet is the
    inlet re-flashed and the extent vanishes."""
    feeds, _params = CstrR2.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])
    params = _r2_params(reacting_phase="aqueous")  # no aqueous phase in this vessel

    result = CstrR2().solve({"inlet": inlet}, params, thermo)

    assert result.info["extent_isom_mol_s"] == pytest.approx(0.0, abs=1e-15)
    n_out = result.outlets["outlet"].component_flows()
    assert math.isclose(n_out["nC5"], 0.7, rel_tol=1e-12)
    assert result.outlets["outlet"].T == pytest.approx(300.0, rel=1e-12)


def test_r2_adiabatic_energy_closure(thermo: Thermo) -> None:
    """Adiabatic two-phase vessel: V0 closes at 1e-8 and the Newton and
    thermal_outlet temperatures agree to 1e-6 K."""
    result = CstrR2().solve({"inlet": _r2_inlet(thermo)}, _r2_params(thermal="adiabatic"), thermo)
    outlet = result.outlets["outlet"]

    h_in = enthalpy_with_formation(_r2_inlet(thermo))
    h_out = enthalpy_with_formation(outlet)
    assert h_in + result.duty_W == pytest.approx(h_out, rel=1e-8)  # duty 0, adiabatic
    assert abs(result.info["T_closure_gap_K"]) < 1e-6


def test_r2_refusals(thermo: Thermo) -> None:
    """The R2 refusal-table rows: a bad reacting_phase and holdup_m3 outside
    (0, volume_m3]."""
    inlet = _r2_inlet(thermo)
    unit = CstrR2()

    with pytest.raises(CstrError, match="reacting_phase"):
        unit.solve({"inlet": inlet}, _r2_params(reacting_phase="plasma"), thermo)
    with pytest.raises(CstrError, match="holdup_m3"):
        unit.solve({"inlet": inlet}, _r2_params(holdup_m3=-0.1), thermo)
    with pytest.raises(CstrError, match="holdup_m3"):
        unit.solve({"inlet": inlet}, _r2_params(holdup_m3=0.0), thermo)
    with pytest.raises(CstrError, match="holdup_m3"):
        unit.solve({"inlet": inlet}, _r2_params(holdup_m3=0.6, volume_m3=0.5), thermo)


def test_r2_example_case_roundtrip(thermo: Thermo) -> None:
    """example_case feeds and params solve and report the documented keys."""
    feeds, params = CstrR2.example_case()
    inlet = flash_feed(thermo, feeds["inlet"])

    result = CstrR2().solve({"inlet": inlet}, params, thermo)

    for key in (
        "extent_isom_mol_s",
        "conversion_nC5_isom",
        "newton_iterations",
        "T_start_K",
        "T_newton_K",
        "T_closure_gap_K",
    ):
        assert key in result.info
