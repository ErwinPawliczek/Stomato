"""Tests for shell_tube R2, the zoned phase-change rating level (spec U-R2).

Pure functions are checked against hand-computed closed forms (Incropera eqs.
10.9/10.46/10.47 on the classic steam-at-1-atm case); the adapter is checked
on the spec's condensing example (a C3/nC4 vapour at 360 K, 1.5 MPa, 380 mol/s
condensed by cooling water on geometry G1 with the process on the shell) and
the refusal table: shell-side boiling, a missing tube_rows_vertical for a
shell-side condensation zone, and the multi-pass F_min cross naming the
minimum shells in series.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.rating import RatingConvergenceError
from ngdesign.units.heat.shell_tube_r2 import (
    GRAVITY,
    PhaseRegimeNotRated,
    ShellTubeGeometryError,
    ShellTubeR2,
    h_prime_fg,
    nusselt_bank,
    nusselt_h1,
    wall_temperature_fixed_point,
)


def _thermo() -> Any:
    registry.discover()
    impl: Any = registry.create("thermo", "pr")
    return impl


def _inlet(thermo: Any, **over: Any) -> tuple[Any, dict[str, Any]]:
    """The example case's process feed as a StreamState, plus the params."""
    feeds, params = ShellTubeR2.example_case()
    feed = {**feeds["inlet"], **over}
    state = thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
    return state, params


# --- closed-form film-condensation functions ---------------------------------

#: Steam condensing at 1 atm on a horizontal 20 mm tube, Tw = 353.15 K;
#: liquid water properties at the film temperature 363.15 K (Incropera 10.11).
STEAM_CASE = {
    "rho_l": 963.7,
    "rho_v": 0.596,
    "k_l": 0.675,
    "mu_l": 3.04e-4,
    "cp_l": 4217.0,
    "h_fg": 2.257e6,
    "T_sat": 373.15,
    "T_w": 353.15,
    "D_o": 0.02,
}


def test_h_prime_fg_matches_hand_value() -> None:
    """h'_fg = h_fg + 0.68*cp*(T_sat - T_w) (Incropera eq. 10.9)."""
    c = STEAM_CASE
    hp = h_prime_fg(c["h_fg"], c["cp_l"], c["T_sat"], c["T_w"])
    assert hp == pytest.approx(c["h_fg"] + 0.68 * c["cp_l"] * 20.0, rel=1e-12)


def test_nusselt_h1_matches_hand_value() -> None:
    """Eq. 10.46 evaluated by hand for the steam case (independent formula)."""
    c = STEAM_CASE
    hp = c["h_fg"] + 0.68 * c["cp_l"] * (c["T_sat"] - c["T_w"])
    want = (
        0.729
        * (
            GRAVITY
            * c["rho_l"]
            * (c["rho_l"] - c["rho_v"])
            * c["k_l"] ** 3
            * hp
            / (c["mu_l"] * (c["T_sat"] - c["T_w"]) * c["D_o"])
        )
        ** 0.25
    )
    h1 = nusselt_h1(
        c["rho_l"],
        c["rho_v"],
        c["k_l"],
        c["mu_l"],
        c["cp_l"],
        c["h_fg"],
        c["T_sat"],
        c["T_w"],
        c["D_o"],
    )
    assert h1 == pytest.approx(want, rel=1e-12)


def test_nusselt_bank_correction() -> None:
    """Eq. 10.47: h_1 * N_r^(-1/4) for the mean tubes per vertical row."""
    h1 = 11075.5
    assert nusselt_bank(h1, 10.0) == pytest.approx(h1 * 10.0**-0.25, rel=1e-12)
    assert nusselt_bank(h1, 1.0) == pytest.approx(h1, rel=1e-12)


def test_wall_fixed_point_converges_and_refuses() -> None:
    """Contraction converges; an in-band two-cycle hits the iteration cap; a
    map leaving the open band is reported as diverged."""
    t_sat, t_util = 350.0, 300.0
    target = 320.0
    got = wall_temperature_fixed_point(
        t_sat,
        t_util,
        boiling=False,
        next_wall=lambda tw: tw - 0.5 * (tw - target),
    )
    assert got == pytest.approx(target, abs=1e-5)
    mid = 0.5 * (t_sat + t_util)
    with pytest.raises(RatingConvergenceError, match="did not converge"):
        wall_temperature_fixed_point(
            t_sat,
            t_util,
            boiling=False,
            next_wall=lambda tw: (
                t_util + 0.25 * (t_sat - t_util) if tw > mid else t_util + 0.75 * (t_sat - t_util)
            ),
        )
    with pytest.raises(RatingConvergenceError, match="diverged"):
        wall_temperature_fixed_point(
            t_sat,
            t_util,
            boiling=False,
            next_wall=lambda tw: t_sat + 1.0,
        )


# --- adapter: the spec's condensing example and the refusal table ------------


def test_example_condenser_rates_and_energy_balance() -> None:
    """The C3/nC4 condenser rates: sane duty, area margin, F and zone health."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    result = ShellTubeR2().solve({"inlet": state}, params, thermo)
    info = result.info
    duty = float(result.duty_W)
    # Cooling/condensation: the process duty is negative and equals Q_W.
    assert duty < 0.0
    assert float(info["Q_W"]) == pytest.approx(duty, rel=1e-12)
    assert float(info["utility_duty_W"]) == pytest.approx(duty, rel=1e-12)
    assert abs(duty) > 1.0e6
    # The installed area covers the zoned demand with a positive margin.
    assert 0.0 < float(info["A_required_m2"]) < float(info["A_m2"])
    # The rated point has no internal cross and a healthy correction factor.
    assert float(info["min_zone_dT_K"]) > 0.0
    assert float(info["F_LMTD"]) >= 0.75
    assert float(info["kern_in_range"]) == 1.0
    # The process outlet is cooler and partly condensed; the water warmed.
    outlet = result.outlets["outlet"]
    assert outlet.T < state.T
    assert 0.0 < float(outlet.vapor_fraction) < 1.0
    assert 303.15 < float(info["utility_T_out_K"]) < 360.0


def test_shell_side_boiling_refuses() -> None:
    """A two-phase stream being HEATED on the shell is refused at R2."""
    thermo = _thermo()
    wet = thermo.flash_pt({"nC4": 0.5, "nC5": 0.5}, 310.0, 2.0e5, 100.0)
    assert 0.0 < float(wet.vapor_fraction) < 1.0
    feeds, params = ShellTubeR2.example_case()
    hot_utility = {
        **params,
        "utility_composition": {"H2O": 1.0},
        "utility_T_K": 400.0,
        "utility_P_Pa": 2.0e5,
        "utility_molar_flow": 500.0,
    }
    with pytest.raises(PhaseRegimeNotRated, match="shell-side boiling"):
        ShellTubeR2().solve({"inlet": wet}, hot_utility, thermo)


def test_condensing_shell_requires_tube_rows_vertical() -> None:
    """A shell-side condensation zone without tube_rows_vertical refuses."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    broken = {k: v for k, v in params.items() if k != "tube_rows_vertical"}
    with pytest.raises(ShellTubeGeometryError, match="tube_rows_vertical"):
        ShellTubeR2().solve({"inlet": state}, broken, thermo)


def test_F_min_refusal_reports_shells_required() -> None:
    """F below F_min at the converged duty raises, naming shells_required."""
    thermo = _thermo()
    state, params = _inlet(thermo)
    with pytest.raises(TemperatureCross, match="shells_required"):
        ShellTubeR2().solve({"inlet": state}, {**params, "F_min": 0.95}, thermo)
