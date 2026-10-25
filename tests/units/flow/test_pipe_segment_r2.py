"""Adapter tests for the pipe_segment R2 two-phase marcher (spec step 4).

R2 has no closed-form reference: Beggs-Brill is an empirical holdup
correlation, and the fluid path (fixed-enthalpy PH flashes of a
propane/n-pentane mixture) comes from the PR package. The assertions
therefore check structural invariants, bookkeeping identities, refusal
behaviour, and regression pins of measured outputs. The example-basis
numbers were measured on this head with ``thermo == 'pr'``; they pin the
regression surface, they are not independent references.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow.pipe_segment_r1 import PipeSegmentR1
from ngdesign.units.flow.pipe_segment_r2 import (
    R2_MAX_SEGMENTS,
    PipeSegmentR2,
    PipeSegmentR2Error,
)
from tests.conftest import flash_feed

#: Flat line with a two-phase inlet at the flash-pressure floor: every
#: segment runs Beggs-Brill (n_bb == 20).
TWO_PHASE_FEED = {
    "T": 340.0,
    "P": 1.08e6,
    "molar_flow": 60.0,
    "composition": {"C3": 0.5, "nC5": 0.5},
}
TWO_PHASE_PARAMS = {"L_m": 1000.0, "D_m": 0.1023, "sigma_N_m": 0.01, "n_segments": 20}

#: Liquid inlet climbing a hill: flashes at node 2, then 19 BB segments.
HILL_FEED: dict[str, Any] = {
    "T": 340.0,
    "P": 1.3e6,
    "molar_flow": 60.0,
    "composition": {"C3": 0.5, "nC5": 0.5},
}
HILL_PARAMS = {
    "L_m": 1000.0,
    "D_m": 0.1023,
    "sigma_N_m": 0.01,
    "elevation_m": 80.0,
    "n_segments": 20,
}


def _profile(info: dict[str, float], n: int, key: str) -> list[float]:
    return [info[f"profile_{i:03d}_{key}"] for i in range(n + 1)]


def test_r2_marches_a_fully_two_phase_line(thermo: Thermo) -> None:
    """A two-phase inlet (allowed at R2, refused at R1) runs Beggs-Brill on
    every segment; pressure and temperature fall monotonically (Joule-
    Thomson cooling), mass quality rises."""
    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    assert inlets["inlet"].vapor_fraction > 0.001
    result = PipeSegmentR2().solve(inlets, TWO_PHASE_PARAMS, thermo)
    info = result.info
    assert info["n_two_phase_segments"] == 20.0
    Ps = _profile(info, 20, "P_Pa")
    Ts = _profile(info, 20, "T_K")
    qs = _profile(info, 20, "quality")
    assert Ps[-1] == pytest.approx(784294.0, rel=1e-5)
    assert all(a > b for a, b in zip(Ps, Ps[1:], strict=False))
    assert all(a > b for a, b in zip(Ts, Ts[1:], strict=False))
    assert all(b - a > -1e-12 for a, b in zip(qs, qs[1:], strict=False))
    assert qs[-1] == pytest.approx(0.2854, abs=2e-4)
    assert info["dT_K"] < 0


def test_r2_liquid_line_flashes_part_way(thermo: Thermo) -> None:
    """A compressed liquid climbs 80 m, crosses the flash floor about 150 m
    in, and the remainder runs two-phase: n_bb 19 of 20, q(0) == 0."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    assert inlets["inlet"].vapor_fraction == 0.0
    result = PipeSegmentR2().solve(inlets, HILL_PARAMS, thermo)
    info = result.info
    assert info["n_two_phase_segments"] == 19.0
    qs = _profile(info, 20, "quality")
    Ps = _profile(info, 20, "P_Pa")
    assert qs[0] == 0.0 and qs[1] == 0.0 and qs[2] > 0.0
    assert all(a > b for a, b in zip(Ps, Ps[1:], strict=False))
    assert Ps[-1] == pytest.approx(957365.0, rel=1e-5)


def test_r2_example_case_solves_and_pins_measured_values(thermo: Thermo) -> None:
    """The shipped example basis reproduces the measured head values."""
    feeds, params = PipeSegmentR2.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = PipeSegmentR2().solve(inlets, params, thermo)
    info = result.info
    assert result.outlets["outlet"].P > 0
    assert info["n_two_phase_segments"] >= 1
    assert info["dP_total_Pa"] == pytest.approx(inlets["inlet"].P - result.outlets["outlet"].P, rel=1e-12)


def test_r2_dP_total_matches_inlet_minus_outlet(thermo: Thermo) -> None:
    """Bookkeeping identity: dP_total_Pa equals P_in - P_out to round-off."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    result = PipeSegmentR2().solve(inlets, HILL_PARAMS, thermo)
    expected = HILL_FEED["P"] - result.outlets["outlet"].P
    assert result.info["dP_total_Pa"] == pytest.approx(expected, rel=1e-12)


def test_r2_reports_N_half_check_within_bound(thermo: Thermo) -> None:
    """The N/2 discretisation check is reported and small against the total
    drop (0.2 percent on the example basis)."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    result = PipeSegmentR2().solve(inlets, HILL_PARAMS, thermo)
    check = result.info["dP_check_N_half_Pa"]
    assert abs(check) <= 0.002 * result.info["dP_total_Pa"]


def test_r2_profile_has_n_plus_one_nodes(thermo: Thermo) -> None:
    """The profile carries n+1 nodes with x, P, T, quality at each."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    result = PipeSegmentR2().solve(inlets, HILL_PARAMS, thermo)
    info = result.info
    xs = _profile(info, 20, "x_m")
    assert xs[0] == 0.0 and xs[-1] == pytest.approx(HILL_PARAMS["L_m"])
    for key in ("P_Pa", "T_K", "quality"):
        assert len(_profile(info, 20, key)) == 21


def test_r2_requires_sigma_on_a_two_phase_node(thermo: Thermo) -> None:
    """Surface tension is never invented: a line that flashes two-phase
    refuses without sigma_N_m, and refuses a non-positive sigma."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    no_sigma = {k: v for k, v in HILL_PARAMS.items() if k != "sigma_N_m"}
    with pytest.raises(PipeSegmentR2Error, match="sigma_N_m"):
        PipeSegmentR2().solve(inlets, no_sigma, thermo)
    bad_sigma = dict(HILL_PARAMS, sigma_N_m=-0.01)
    with pytest.raises(PipeSegmentR2Error, match="sigma_N_m"):
        PipeSegmentR2().solve(inlets, bad_sigma, thermo)


def test_r2_refuses_overdriven_flow(thermo: Thermo) -> None:
    """A flow the line cannot carry drives the march through zero pressure;
    the refusal is typed and names the failure."""
    feed = dict(TWO_PHASE_FEED, molar_flow=300.0, P=1.2e6)
    inlets = {"inlet": flash_feed(thermo, feed)}
    with pytest.raises(PipeSegmentR2Error, match="pressure falls to zero"):
        PipeSegmentR2().solve(inlets, TWO_PHASE_PARAMS, thermo)


def test_r2_refuses_bad_geometry(thermo: Thermo) -> None:
    """Validation refusals name their parameter (shared with R1)."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    base = dict(HILL_PARAMS)
    with pytest.raises(Exception, match="L_m"):
        PipeSegmentR2().solve(inlets, dict(base, L_m=0.0), thermo)
    with pytest.raises(Exception, match="n_segments"):
        PipeSegmentR2().solve(inlets, dict(base, n_segments=0), thermo)
    with pytest.raises(Exception, match="n_segments"):
        PipeSegmentR2().solve(inlets, dict(base, n_segments=R2_MAX_SEGMENTS + 1), thermo)


def test_r1_refuses_what_r2_accepts(thermo: Thermo) -> None:
    """Level complement: the two-phase inlet R1 refuses ('use R2') is the
    case R2 exists to solve."""
    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    with pytest.raises(Exception, match="two-phase inlet"):
        PipeSegmentR1().solve(
            inlets,
            {"L_m": TWO_PHASE_PARAMS["L_m"], "D_m": TWO_PHASE_PARAMS["D_m"]},
            thermo,
        )
    result = PipeSegmentR2().solve(inlets, TWO_PHASE_PARAMS, thermo)
    assert result.outlets["outlet"].P > 0
