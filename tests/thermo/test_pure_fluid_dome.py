"""Pure-fluid PH and PS flashes inside the vapour dome (issue #310).

A single component's two-phase state is Tsat(P) plus the lever rule. Before the
fix, PS raised ZeroDivisionError there and PH returned one phase at Tsat holding
the whole enthalpy. Independent checks: the target property is returned exactly;
T is the package's own bubble temperature (``flash_pvf``, the databank vapour
pressure curve); PH and PS agree on the same state; the midpoint enthalpy gives
the lever-rule vapour fraction; targets outside the dome take the old route.
"""

from __future__ import annotations

from typing import cast

import pytest

from ngdesign import registry
from ngdesign.contracts import PhaseKind
from ngdesign.contracts.plugins import Thermo

INTO_DOME = [
    ({"H2O": 1.0}, 500.0, 1.0e6, 3.0e5),
    ({"H2O": 1.0}, 500.0, 1.0e6, 2.0e3),
    ({"N2": 1.0}, 100.0, 1.0e7, 1.0e5),
]


@pytest.fixture(scope="module")
def thermo() -> Thermo:
    return cast(Thermo, registry.create("thermo", "pr"))


@pytest.mark.parametrize(("z", "T0", "P0", "P1"), INTO_DOME)
def test_isentropic_expansion_lands_two_phase(
    thermo: Thermo, z: dict[str, float], T0: float, P0: float, P1: float
) -> None:
    start = thermo.flash_pt(z, T0, P0, 1.0)
    out = thermo.flash_ps(z, P1, start.entropy, 1.0)
    assert 0.0 < out.vapor_fraction < 1.0
    assert len(out.phases) == 2
    assert out.entropy == pytest.approx(start.entropy, rel=1e-12)
    assert out.T == pytest.approx(thermo.flash_pvf(z, P1, 0.0, 1.0).T, rel=1e-9)


@pytest.mark.parametrize(("z", "T0", "P0", "P1"), INTO_DOME)
def test_ph_round_trip_matches_ps(
    thermo: Thermo, z: dict[str, float], T0: float, P0: float, P1: float
) -> None:
    out = thermo.flash_ps(z, P1, thermo.flash_pt(z, T0, P0, 1.0).entropy, 1.0)
    back = thermo.flash_ph(z, P1, out.enthalpy, 1.0)
    assert back.T == pytest.approx(out.T, rel=1e-9)
    assert back.vapor_fraction == pytest.approx(out.vapor_fraction, rel=1e-9)
    assert back.entropy == pytest.approx(out.entropy, rel=1e-9)


def test_midpoint_enthalpy_is_half_vapour(thermo: Thermo) -> None:
    # Lever rule: H = (H_l + H_v)/2 gives beta = 1/2 exactly. H_l and H_v are the
    # saturated phases at (Tsat, P), read from the package's own phase_props.
    z, P = {"H2O": 1.0}, 2.0e3
    t_sat = thermo.flash_pvf(z, P, 0.0, 1.0).T
    h_l = thermo.phase_props(z, t_sat, P, PhaseKind.AQUEOUS).enthalpy
    h_v = thermo.phase_props(z, t_sat, P, PhaseKind.VAPOR).enthalpy
    out = thermo.flash_ph(z, P, 0.5 * (h_l + h_v), 1.0)
    assert out.vapor_fraction == pytest.approx(0.5, rel=1e-12)
    assert out.T == t_sat


@pytest.mark.parametrize(
    ("z", "T", "P"),
    [({"H2O": 1.0}, 700.0, 5.0e5), ({"H2O": 1.0}, 300.0, 2.0e5), ({"N2": 1.0}, 300.0, 1.0e5)],
)
def test_single_phase_targets_keep_the_old_route(
    thermo: Thermo, z: dict[str, float], T: float, P: float
) -> None:
    # Superheated vapour, subcooled liquid and a supercritical gas: the dome
    # handler declines, so PH/PS round trips return the PT state (single phase).
    state = thermo.flash_pt(z, T, P, 1.0)
    for out in (thermo.flash_ph(z, P, state.enthalpy, 1.0), thermo.flash_ps(z, P, state.entropy, 1.0)):
        assert len(out.phases) == 1
        assert out.T == pytest.approx(T, rel=1e-6)


def test_water_normal_boiling_point(thermo: Thermo) -> None:
    # Steam tables (IAPWS-IF97): Tsat(101325 Pa) = 373.124 K. The package's pure
    # saturation is the databank vapour-pressure correlation, accurate to about
    # 0.1 % in P near the normal boiling point, i.e. a few hundredths of a kelvin.
    assert thermo.flash_pvf({"H2O": 1.0}, 101_325.0, 0.0, 1.0).T == pytest.approx(373.124, abs=0.05)
