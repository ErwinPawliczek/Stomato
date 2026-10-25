"""Hydrocyclone R1 closed-form tests (spec specs/backend/units/hydrocyclone.md).

Basis (a Lapple standard-proportion gas cyclone, D = 0.5 m, so W = 0.125 m,
H = 0.25 m, D_e = 0.25 m, L_b = L_c = 1.0 m), Q = 0.5 m3/s, rho_f = 1.2 kg/m3,
mu = 1.8e-5 Pa.s, rho_p = 2000 kg/m3.

Hand-computed anchor values (the numbers below are re-derived here from the
spec's equations, not from the implementation):

- H1: v_i = Q/(W*H) = 0.5/(0.125*0.25) = 16 m/s.
- H2: N_e = (L_b + L_c/2)/H = (1.0 + 0.5)/0.25 = 6.
- H3: d50 = sqrt(9*mu*W/(2*pi*N_e*v_i*|rho_p - rho_f|))
      = sqrt(9*1.8e-5*0.125/(2*pi*6*16*1998.8))
      = sqrt(2.025e-5/1.20584e6) = 4.09828629e-6 m.
- H4: eta(5 um)  = 1/(1 + (4.09828629/5)^2)    = 0.598144072;
      eta(10 um) = 1/(1 + (4.09828629/10)^2)   = 0.856194068.
- H6: N_H = K*H*W/De^2 = 16*0.25*0.125/0.0625 = 8;
      dP = 0.5*1.2*16^2*8 = 1228.8 Pa.
- H5: E = int_0^1 eta(d_RR*(-ln(1-F))^(1/n)) dF by 64-point Gauss-Legendre
      with d_RR = 10 um, n = 1.5 gives 0.685967673. An independent midpoint
      rule with 2e6 points gives 0.685967816; the 1.4e-7 difference is
      quadrature, so the test pins GL64 (spec CF4).
- H7 (CF5): particle underflow fraction E + (1 - E)*R_f
      = 0.685967673 + 0.314032327*0.1 = 0.717370906.
- Light-particle branch: rho_p < rho_f sends the separated fraction to the
  overflow, so with E = 0.6 and R_f = 0.2 the underflow fraction is
  (1 - 0.6)*0.2 = 0.08 exactly.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.hydrocyclone import Hydrocyclone
from ngdesign.units.separation.hydrocyclone_r1 import (
    DEFAULT_K_INLET,
    HydrocycloneR1,
    HydrocycloneR1SpecError,
    effective_turns,
    grade_efficiency,
    inlet_velocity,
    lapple_cut_diameter,
    overall_efficiency,
    shepherd_lapple_number,
    shepherd_lapple_pressure_drop,
    underflow_fraction,
)
from tests.conftest import flash_feed

_W, _H, _D_E, _L_B, _L_C = 0.125, 0.25, 0.25, 1.0, 1.0
_Q, _RHO_F, _MU, _RHO_P = 0.5, 1.2, 1.8e-5, 2000.0


def _d50() -> float:
    v_i = inlet_velocity(_Q, _W, _H)
    return lapple_cut_diameter(_MU, _W, effective_turns(_L_B, _L_C, _H), v_i, _RHO_P, _RHO_F)


def test_cf1_inlet_velocity_turns_and_cut_diameter() -> None:
    v_i = inlet_velocity(_Q, _W, _H)
    N_e = effective_turns(_L_B, _L_C, _H)
    assert v_i == pytest.approx(16.0, rel=1e-9)
    assert N_e == pytest.approx(6.0, rel=1e-9)
    assert _d50() == pytest.approx(4.09828629e-6, rel=1e-9)


def test_cf2_grade_efficiency_at_5_and_10_um() -> None:
    d50 = _d50()
    assert grade_efficiency(d50, 5e-6) == pytest.approx(0.598144072, rel=1e-9)
    assert grade_efficiency(d50, 10e-6) == pytest.approx(0.856194068, rel=1e-9)


def test_cf3_shepherd_lapple_pressure_drop() -> None:
    N_H = shepherd_lapple_number(_H, _W, _D_E)
    assert N_H == pytest.approx(8.0, rel=1e-12)
    assert shepherd_lapple_pressure_drop(_RHO_F, inlet_velocity(_Q, _W, _H), N_H) == pytest.approx(
        1228.8, rel=1e-12
    )


def test_cf4_overall_efficiency_gl64_rosin_rammler() -> None:
    assert overall_efficiency(_d50(), 10e-6, 1.5) == pytest.approx(0.685967673, rel=1e-9)


def test_cf5_particle_underflow_fraction_with_fluid_split() -> None:
    E = overall_efficiency(_d50(), 10e-6, 1.5)
    assert underflow_fraction(E, 0.1, light_particle=False) == pytest.approx(0.717370906, rel=1e-9)


def test_light_particle_branch_reports_to_overflow() -> None:
    """H7 with rho_p < rho_f: underflow fraction (1 - E)*R_f; E = 0.6, R_f = 0.2."""
    assert underflow_fraction(0.6, 0.2, light_particle=True) == pytest.approx(0.08, rel=1e-12)


# --- adapter: identity against R0, refusals --------------------------------


def _identity_inlets(thermo: Thermo) -> dict[str, StreamState]:
    """The R0 example basis: H2O 0.95 / nC5 0.05 at 323.15 K, 0.5 MPa."""
    feeds, _ = Hydrocyclone().example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _identity_params() -> dict[str, Any]:
    params: dict[str, Any] = dict(HydrocycloneR1.example_case()[1])
    return params


def test_identity_r1_matches_r0_on_its_own_fractions(thermo: Thermo) -> None:
    inlets = _identity_inlets(thermo)
    r1 = HydrocycloneR1().solve(inlets, _identity_params(), thermo)
    fractions = {cid: r1.info[f"underflow_fraction_{cid}"] for cid in inlets["inlet"].composition}
    r0 = Hydrocyclone().solve(
        inlets, {"underflow_fractions": fractions, "dP": r1.info["dP_Pa"]}, thermo
    )
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W


def test_r1_example_case_flows_end_to_end(thermo: Thermo) -> None:
    """V0-style sanity on the R1 example: balances close via R0's split."""
    inlets = _identity_inlets(thermo)
    result = HydrocycloneR1().solve(inlets, _identity_params(), thermo)
    total_out = sum(s.molar_flow for s in result.outlets.values())
    assert total_out == pytest.approx(inlets["inlet"].molar_flow, rel=1e-9)
    light = result.outlets["overflow"].composition["nC5"]
    coarse = result.outlets["underflow"].composition["nC5"]
    assert light > coarse  # oil droplets report to the overflow (H7 light branch)


def _refuse(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    inlets = _identity_inlets(thermo)
    with pytest.raises(HydrocycloneR1SpecError, match=match):
        HydrocycloneR1().solve(inlets, params, thermo)


def test_refuses_empty_or_unknown_particle_components(thermo: Thermo) -> None:
    p = _identity_params()
    p["particle_components"] = []
    _refuse(thermo, p, "particle_components")
    p["particle_components"] = ["SiO2"]
    _refuse(thermo, p, "particle_components")


def test_refuses_bad_particle_density(thermo: Thermo) -> None:
    p = _identity_params()
    del p["particle_density_kg_m3"]
    _refuse(thermo, p, "particle_density_kg_m3")
    p["particle_density_kg_m3"] = 0.0
    _refuse(thermo, p, "particle_density_kg_m3")


def test_refuses_zero_density_difference(thermo: Thermo) -> None:
    inlets = _identity_inlets(thermo)
    probe = HydrocycloneR1().solve(inlets, _identity_params(), thermo)
    rho_f = float(probe.info["rho_fluid_kg_m3"])
    p = _identity_params()
    p["particle_density_kg_m3"] = rho_f
    _refuse(thermo, p, "density difference")


def test_refuses_missing_or_nonpositive_geometry(thermo: Thermo) -> None:
    p = _identity_params()
    del p["inlet_width_m"]
    _refuse(thermo, p, "inlet_width_m")
    p = _identity_params()
    p["inlet_height_m"] = -1.0
    _refuse(thermo, p, "inlet_height_m")
    p = _identity_params()
    del p["body_length_m"], p["cone_length_m"]
    p.pop("N_e", None)
    _refuse(thermo, p, "N_e")
    p = _identity_params()
    p["N_e"] = 0.0
    _refuse(thermo, p, "N_e")


def test_refuses_missing_or_doubled_particle_size_form(thermo: Thermo) -> None:
    p = _identity_params()
    del p["particle_diameter_m"]
    _refuse(thermo, p, "particle_diameter_m")
    p = _identity_params()
    p["d_rr_m"], p["n_rr"] = 10e-6, 1.5
    _refuse(thermo, p, "particle_diameter_m")


def test_refuses_fluid_underflow_fraction_outside_range(thermo: Thermo) -> None:
    p = _identity_params()
    p["fluid_underflow_fraction"] = 1.0
    _refuse(thermo, p, "fluid_underflow_fraction")
    p["fluid_underflow_fraction"] = -0.1
    _refuse(thermo, p, "fluid_underflow_fraction")


def test_refuses_missing_dP_and_outlet_diameter(thermo: Thermo) -> None:
    p = _identity_params()
    del p["outlet_diameter_m"]
    _refuse(thermo, p, "outlet_diameter_m")


def test_refuses_unavailable_fluid_viscosity(thermo: Thermo) -> None:
    """A continuous phase reporting no viscosity is refused unless overridden."""
    inlets = _identity_inlets(thermo)
    inlet = inlets["inlet"]
    dry_phases = [ph.model_copy(update={"viscosity": None}) for ph in inlet.phases]
    inlets = {"inlet": inlet.model_copy(update={"phases": dry_phases})}
    p = _identity_params()
    p.pop("fluid_viscosity_Pa_s", None)
    _refuse(thermo, p, "fluid_viscosity_Pa_s")


def test_k_inlet_default_is_16() -> None:
    assert DEFAULT_K_INLET == 16.0
