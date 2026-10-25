"""Adapter tests for the pipe_segment R2 two-phase marcher (spec step 4).

R2 has no closed-form reference: Beggs-Brill is an empirical holdup
correlation, and the fluid path (fixed-enthalpy PH flashes of a
propane/n-pentane mixture) comes from the PR package. The assertions
therefore check structural invariants, bookkeeping identities, refusal
behaviour, and independent references: the R2-to-R1 identity on an
all-liquid line, a bare-Beggs-Brill wiring check, and the shared validation
refusals. No measured model output is pinned.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fluids import Beggs_Brill

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind, StreamState
from ngdesign.units.flow.pipe_segment import PipeSegmentSpecError
from ngdesign.units.flow.pipe_segment_r1 import (
    DEFAULT_ROUGHNESS_M,
    PipeSegmentR1,
    PipeSegmentR1Error,
    march,
)
from ngdesign.units.flow.pipe_segment_r2 import (
    R2_MAX_SEGMENTS,
    VF_MAX,
    VF_MIN,
    PipeSegmentR2,
    PipeSegmentR2Error,
    _mass_quality,
    _viscosity,
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

#: Subcooled water at 0.5 MPa climbing 40 m of 3 in pipe: the fixed-enthalpy
#: PH flash crosses the saturation floor part way up and the remaining nodes
#: are AQUEOUS + VAPOR -- the pure-fluid liquid the R2 liquid-phase selection
#: must handle.
WATER_FEED = {
    "T": 400.0,
    "P": 0.5e6,
    "molar_flow": 50.0,
    "composition": {"H2O": 1.0},
}
WATER_PARAMS = {
    "L_m": 100.0,
    "D_m": 0.0779,
    "sigma_N_m": 0.04,
    "elevation_m": 40.0,
    "n_segments": 10,
}


def _profile(info: dict[str, float], n: int, key: str) -> list[float]:
    return [info[f"profile_{i:03d}_{key}"] for i in range(n + 1)]


def _node_phases(state: StreamState) -> tuple[Any, Any]:
    """The (liquid, vapour) phase of a two-phase flashed node, as R2 picks them."""
    liq = next(p for p in state.phases if p.kind is not PhaseKind.VAPOR)
    vap = next(p for p in state.phases if p.kind is PhaseKind.VAPOR)
    return liq, vap


def _mu_in(thermo_inlet: StreamState) -> float:
    dominant = max(thermo_inlet.phases, key=lambda p: p.mole_fraction)
    return _viscosity(dominant, 0.0)


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
    assert all(a > b for a, b in zip(Ps, Ps[1:], strict=False))
    assert all(a > b for a, b in zip(Ts, Ts[1:], strict=False))
    assert all(b - a > -1e-12 for a, b in zip(qs, qs[1:], strict=False))
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


def test_r2_aqueous_two_phase_line_solves(thermo: Thermo) -> None:
    """Pure water flashing AQUEOUS + VAPOR part way up: the liquid of a
    two-phase node is the single non-vapour phase (not assumed HC_LIQUID),
    so the line solves instead of crashing."""
    inlets = {"inlet": flash_feed(thermo, WATER_FEED)}
    inlet = inlets["inlet"]
    assert inlet.vapor_fraction == 0.0
    assert any(p.kind is PhaseKind.AQUEOUS for p in inlet.phases)
    result = PipeSegmentR2().solve(inlets, WATER_PARAMS, thermo)
    info = result.info
    assert 1.0 <= info["n_two_phase_segments"] < 10.0
    Ps = _profile(info, 10, "P_Pa")
    qs = _profile(info, 10, "quality")
    assert all(a > b for a, b in zip(Ps, Ps[1:], strict=False))
    assert result.outlets["outlet"].P > 0
    assert qs[-1] > 0.0


def test_r2_refuses_three_phase_node(thermo: Thermo) -> None:
    """A node with two liquid phases (HC + aqueous + vapour) is refused with
    the typed three-phase refusal: Beggs-Brill is strictly two-phase."""

    class _ThreePhaseThermo:
        def flash_ph(
            self, z: dict[str, float], P: float, H: float, molar_flow: float
        ) -> StreamState:
            state = thermo.flash_ph(z, P, H, molar_flow)
            if not (VF_MIN < state.vapor_fraction < VF_MAX):
                return state
            liq, vap = _node_phases(state)
            aqueous = liq.model_copy(update={"kind": PhaseKind.AQUEOUS})
            return state.model_copy(update={"phases": [liq, aqueous, vap]})

    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    with pytest.raises(PipeSegmentR2Error, match="three-phase"):
        PipeSegmentR2().solve(
            inlets, TWO_PHASE_PARAMS, cast(Thermo, _ThreePhaseThermo())
        )


def test_r2_equals_r1_core_march_on_all_liquid_line(thermo: Thermo) -> None:
    """R2 to R1 identity: on an all-liquid line R2 at n_segments = N is the
    R1 core march(..., n=N) without refinement, to 1e-12 relative on P_out."""
    feed = {"T": 293.15, "P": 1.0e6, "molar_flow": 50.0, "composition": {"nC4": 1.0}}
    params = {"L_m": 200.0, "D_m": 0.0779, "n_segments": 20}
    inlets = {"inlet": flash_feed(thermo, feed)}
    inlet = inlets["inlet"]
    assert inlet.vapor_fraction == 0.0
    result = PipeSegmentR2().solve(inlets, params, thermo)
    assert result.info["n_two_phase_segments"] == 0.0
    dP_K = result.info["dP_fittings_Pa"]
    z = dict(inlet.composition)
    mu_in = _mu_in(inlet)

    def props(P: float) -> tuple[float, float]:
        state = thermo.flash_ph(z, P, inlet.enthalpy, inlet.molar_flow)
        dominant = max(state.phases, key=lambda p: p.mole_fraction)
        return dominant.density, _viscosity(dominant, mu_in)

    P_core = march(
        inlet.P - dP_K,
        200.0,
        0.0779,
        0.0,
        DEFAULT_ROUGHNESS_M,
        inlet.mass_flow,
        props,
        20,
    )
    assert result.outlets["outlet"].P == pytest.approx(P_core, rel=1e-12)


def test_r2_step_matches_bare_beggs_brill(thermo: Thermo) -> None:
    """Wiring check: on a one-segment horizontal two-phase line the Heun step
    is exactly two Beggs_Brill evaluations at the flashed node properties."""
    params = {"L_m": 500.0, "D_m": 0.1023, "sigma_N_m": 0.01, "n_segments": 1}
    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    inlet = inlets["inlet"]
    result = PipeSegmentR2().solve(inlets, params, thermo)
    dP_K = result.info["dP_fittings_Pa"]
    h = 500.0
    P0 = inlet.P - dP_K
    z = dict(inlet.composition)
    mu_in = _mu_in(inlet)

    def bb(P: float, state: StreamState) -> float:
        liq, vap = _node_phases(state)
        return Beggs_Brill(
            m=inlet.mass_flow,
            x=_mass_quality(state),
            rhol=liq.density,
            rhog=vap.density,
            mul=_viscosity(liq, mu_in),
            mug=_viscosity(vap, mu_in),
            sigma=0.01,
            P=P,
            D=0.1023,
            angle=0.0,
            roughness=DEFAULT_ROUGHNESS_M,
            L=h,
            acceleration=True,
        )

    s0 = thermo.flash_ph(z, P0, inlet.enthalpy, inlet.molar_flow)
    dP1 = bb(P0, s0)
    s_star = thermo.flash_ph(z, P0 - dP1, inlet.enthalpy, inlet.molar_flow)
    dP2 = bb(P0 - dP1, s_star)
    assert result.outlets["outlet"].P == pytest.approx(P0 - (dP1 + dP2) / 2, rel=1e-12)


def test_r2_wraps_beggs_brill_regime_error(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ValueError from the correlation comes out as a typed
    PipeSegmentR2Error naming Beggs-Brill."""
    from ngdesign.units.flow import pipe_segment_r2 as mod

    def boom(**_kwargs: Any) -> float:
        raise ValueError("regime map: off the chart")

    monkeypatch.setattr(mod, "Beggs_Brill", boom)
    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    with pytest.raises(PipeSegmentR2Error, match="Beggs-Brill"):
        PipeSegmentR2().solve(inlets, TWO_PHASE_PARAMS, thermo)


def test_r2_example_case_solves(thermo: Thermo) -> None:
    """The shipped example basis solves with consistent bookkeeping."""
    feeds, params = PipeSegmentR2.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = PipeSegmentR2().solve(inlets, params, thermo)
    info = result.info
    assert result.outlets["outlet"].P > 0
    assert info["n_two_phase_segments"] >= 1
    assert info["dP_total_Pa"] == pytest.approx(
        inlets["inlet"].P - result.outlets["outlet"].P, rel=1e-12
    )


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
    """Validation refusals are the typed spec error and name their parameter
    (shared with R1)."""
    inlets = {"inlet": flash_feed(thermo, HILL_FEED)}
    base = dict(HILL_PARAMS)
    with pytest.raises(PipeSegmentSpecError, match="L_m"):
        PipeSegmentR2().solve(inlets, dict(base, L_m=0.0), thermo)
    with pytest.raises(PipeSegmentSpecError, match="n_segments"):
        PipeSegmentR2().solve(inlets, dict(base, n_segments=0), thermo)
    with pytest.raises(PipeSegmentSpecError, match="n_segments"):
        PipeSegmentR2().solve(
            inlets, dict(base, n_segments=R2_MAX_SEGMENTS + 1), thermo
        )


def test_r1_refuses_what_r2_accepts(thermo: Thermo) -> None:
    """Level complement: the two-phase inlet R1 refuses ('use R2') is the
    case R2 exists to solve."""
    inlets = {"inlet": flash_feed(thermo, TWO_PHASE_FEED)}
    with pytest.raises(PipeSegmentR1Error, match="two-phase inlet"):
        PipeSegmentR1().solve(
            inlets,
            {"L_m": TWO_PHASE_PARAMS["L_m"], "D_m": TWO_PHASE_PARAMS["D_m"]},
            thermo,
        )
    result = PipeSegmentR2().solve(inlets, TWO_PHASE_PARAMS, thermo)
    assert result.outlets["outlet"].P > 0
