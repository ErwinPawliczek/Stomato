"""shell_tube R2 tests (``specs/backend/units/shell_tube.md``)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import RatingConvergenceError, RatingError, u_outside_tube
from ngdesign.units.heat.shell_tube_r1 import ShellTubeR1
from ngdesign.units.heat.shell_tube_r2 import (
    PhaseRegimeNotRated,
    ShellTubeR2,
    fixed_point_wall,
    latent_heat_J_kg,
    nusselt_bank_h,
)


def _r1_inlet(thermo: Thermo) -> tuple[dict[str, Any], dict[str, Any]]:
    feeds, params = ShellTubeR1.example_case()
    f = feeds["inlet"]
    return {"inlet": thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])}, params


def _r2_inlet(thermo: Thermo) -> tuple[dict[str, Any], dict[str, Any]]:
    feeds, params = ShellTubeR2.example_case()
    f = feeds["inlet"]
    return {"inlet": thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])}, params


def test_nusselt_bank_closed_form() -> None:
    """Spec values: h'_fg = 317000 J/kg, h_1 = 1682.81386, bank at N_r = 10: 946.315775."""
    args = (600.0, 20.0, 0.10, 2.0e-4, 2500.0, 3.0e5, 330.0, 320.0, 0.01905)
    assert nusselt_bank_h(*args, 1) == pytest.approx(1682.81386, rel=1e-8)
    assert nusselt_bank_h(*args, 10) == pytest.approx(946.315775, rel=1e-8)


def test_fixed_point_closes_the_wall_balance() -> None:
    """Constant h and U: T_w = T_sat - U*(T_sat - T_other)/h, by hand 340 - 0.4*40 = 324 K."""
    h, t_w = fixed_point_wall(lambda _t: 1000.0, 340.0, 300.0, lambda _h: 400.0)
    assert h == 1000.0
    assert t_w == pytest.approx(324.0, abs=1e-5)


def test_fixed_point_cap_is_typed() -> None:
    """An h that keeps moving with the wall never settles: a named refusal."""
    state = {"n": 0.0}

    def moving(_t: float) -> float:
        state["n"] += 1.0
        return float(100.0 + (-1.0) ** state["n"] * 50.0)

    with pytest.raises(RatingConvergenceError, match="did not converge"):
        fixed_point_wall(moving, 340.0, 300.0, lambda _h: 80.0)


@pytest.mark.parametrize("passes", [1, 2])
def test_one_zone_reduces_to_r1(thermo: Thermo, passes: int) -> None:
    """Q = UA*F*LMTD is algebraically epsilon-NTU on the same mean films.

    This duty measures F = 0.504 on a 1-2 shell, so F_min is set below it: the
    default 0.75 refuses the arrangement, which test_a_temperature_cross covers.
    """
    inlets, params = _r1_inlet(thermo)
    params = {**params, "tube_passes": passes}
    r1 = ShellTubeR1().solve(inlets, params, thermo)
    r2 = ShellTubeR2().solve(inlets, {**params, "n_zones": 1, "F_min": 0.4}, thermo)
    assert r2.info["Q_W"] == pytest.approx(r1.info["Q_W"], rel=1e-7)
    assert r2.outlets["outlet"].T == pytest.approx(r1.outlets["outlet"].T, rel=1e-7)
    assert r2.outlets["outlet"].P == pytest.approx(r1.outlets["outlet"].P, rel=1e-12)


def test_zones_refine_a_single_phase_duty_only_slightly(thermo: Thermo) -> None:
    inlets, params = _r1_inlet(thermo)
    params = {**params, "tube_passes": 1}
    one = ShellTubeR2().solve(inlets, {**params, "n_zones": 1}, thermo)
    many = ShellTubeR2().solve(inlets, {**params, "n_zones": 8}, thermo)
    assert many.info["Q_W"] == pytest.approx(one.info["Q_W"], rel=2e-2)


def test_latent_heat_of_a_pure_component(thermo: Thermo) -> None:
    """Regression: flash_pvf gives a pure component's bubble liquid at any vf, so h_fg read 0.

    Propane at 1 MPa: the enthalpy step across T_sat, above 2e5 J/kg by a wide margin.
    """
    assert latent_heat_J_kg(thermo, {"C3": 1.0}, 1.0e6) > 2.0e5


def test_condenser_closes_area_and_changes_phase(thermo: Thermo) -> None:
    inlets, params = _r2_inlet(thermo)
    res = ShellTubeR2().solve(inlets, params, thermo)
    out = res.outlets["outlet"]
    assert inlets["inlet"].vapor_fraction == 1.0
    assert out.vapor_fraction < 1.0
    assert res.info["A_required_m2"] == pytest.approx(res.info["A_m2"], rel=1e-6)
    assert res.info["zone_U_max_W_m2K"] > res.info["zone_U_min_W_m2K"]
    assert res.duty_W == pytest.approx(-res.info["Q_W"], rel=1e-9)
    assert res.info["F_LMTD"] >= 0.75


def test_zone_films_are_reported_and_close_each_zone_u(thermo: Thermo) -> None:
    """Regression (validation run 2026-11-04): the zone film coefficients are in info.

    Reporting only, no behaviour change: each zone's U recomputes from its own
    reported (tube, shell) films through the same series-resistance formula,
    the zone_U extremes are those of the recomputed set, and the means are the
    equal-duty zone means.
    """
    inlets, params = _r2_inlet(thermo)
    params = {**params, "k_wall_W_mK": 45.0, "R_f_tube_m2K_W": 1.0e-4, "R_f_shell_m2K_W": 2.0e-4}
    res = ShellTubeR2().solve(inlets, params, thermo)
    info = res.info
    n = int(info["n_zones"])
    h_t = [info[f"zone_{k:02d}_h_tube_W_m2K"] for k in range(n)]
    h_s = [info[f"zone_{k:02d}_h_shell_W_m2K"] for k in range(n)]
    us = [
        u_outside_tube(
            h_i=t,
            h_o=s,
            Do=params["tube_OD_m"],
            Di=params["tube_ID_m"],
            k_wall=45.0,
            R_fi=1.0e-4,
            R_fo=2.0e-4,
        )
        for t, s in zip(h_t, h_s, strict=True)
    ]
    assert min(us) == pytest.approx(info["zone_U_min_W_m2K"], rel=1e-12)
    assert max(us) == pytest.approx(info["zone_U_max_W_m2K"], rel=1e-12)
    assert info["h_shell_mean_W_m2K"] == pytest.approx(sum(h_s) / n, rel=1e-12)
    assert info["h_tube_mean_W_m2K"] == pytest.approx(sum(h_t) / n, rel=1e-12)


def test_tube_side_condensation_uses_shah(thermo: Thermo) -> None:
    inlets, params = _r2_inlet(thermo)
    params = {**params, "process_side": "tube"}
    del params["tube_rows_vertical"]
    res = ShellTubeR2().solve(inlets, params, thermo)
    assert res.outlets["outlet"].vapor_fraction < 1.0


def test_tube_side_boiling_uses_liu_winterton(thermo: Thermo) -> None:
    """A subcooled C3/nC4 liquid boiled in the tubes by a hot gas on the shell."""
    params = dict(ShellTubeR2.example_case()[1])
    params.update(
        process_side="tube",
        utility_composition={"N2": 1.0},
        utility_T_K=420.0,
        utility_P_Pa=5.0e6,
        utility_molar_flow=100.0,
    )
    inlet = thermo.flash_pt({"C3": 0.5, "nC4": 0.5}, 330.0, 2.5e6, 4.0)
    assert inlet.vapor_fraction == 0.0
    res = ShellTubeR2().solve({"inlet": inlet}, params, thermo)
    assert res.outlets["outlet"].vapor_fraction > 0.0


def test_shell_side_boiling_refused(thermo: Thermo) -> None:
    params = dict(ShellTubeR2.example_case()[1])
    params.update(
        process_side="shell",
        utility_composition={"N2": 1.0},
        utility_T_K=420.0,
        utility_P_Pa=5.0e6,
        utility_molar_flow=100.0,
    )
    inlet = thermo.flash_pt({"C3": 0.5, "nC4": 0.5}, 330.0, 2.5e6, 8.0)
    with pytest.raises(PhaseRegimeNotRated, match="shell-side boiling"):
        ShellTubeR2().solve({"inlet": inlet}, params, thermo)


def test_shell_condensation_needs_rows(thermo: Thermo) -> None:
    inlets, params = _r2_inlet(thermo)
    del params["tube_rows_vertical"]
    with pytest.raises(RatingError, match="tube_rows_vertical"):
        ShellTubeR2().solve(inlets, params, thermo)


def test_equal_inlets_refused(thermo: Thermo) -> None:
    inlets, params = _r1_inlet(thermo)
    with pytest.raises(TemperatureCross, match="inlet temperatures"):
        ShellTubeR2().solve(inlets, {**params, "utility_T_K": float(inlets["inlet"].T)}, thermo)


def test_a_temperature_cross_names_the_shells_required(thermo: Thermo) -> None:
    """A 1-2 exchanger cooling hard against a close utility fails F_min after converging."""
    inlets, params = _r1_inlet(thermo)
    params = {
        **params,
        "tube_length_m": 60.0,
        "n_tubes": 600,
        "utility_T_K": 318.0,
        "F_min": 0.95,
        "n_zones": 4,
    }
    with pytest.raises(TemperatureCross, match="shells_required"):
        ShellTubeR2().solve(inlets, params, thermo)


def test_n_zones_range(thermo: Thermo) -> None:
    inlets, params = _r1_inlet(thermo)
    with pytest.raises(ValueError, match="n_zones"):
        ShellTubeR2().solve(inlets, {**params, "n_zones": 0}, thermo)
