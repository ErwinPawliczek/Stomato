"""Closed-form tests for the cooling tower R1 Merkel integrator (spec U-R2).

Hand computation (docstring-as-oracle; independent numbers, not the module's
own output). Saturated-air enthalpy per ASHRAE Fundamentals 2017 SI, Ch. 1:
Hyland-Wexler p_ws over liquid (eq. 6),

    ln p_ws = C8/T + C9 + C10 T + C11 T^2 + C12 T^3 + C13 ln T,

with C8 = -5.8002206e3, C9 = 1.3914993, C10 = -4.8640239e-2,
C11 = 4.1764768e-5, C12 = -1.4452093e-8, C13 = 6.5459673;
W_s = 0.621945 p_ws / (P - p_ws);  h = 1.006 t + W (2501 + 1.86 t) kJ/kg_da.
At P = 101325 Pa and T = 303.15 K: p_ws = 4246.03024 Pa (ASHRAE Table 3
prints 4.2467 kPa at 30 C, consistent) and h_s = 99.731526 kJ/kg_da.

With T_in = 313.15 K, T_out = 303.15 K, L/G = 1.2, c_pw = 4.186 kJ/(kg K)
and h_a,in = 72.0 kJ/kg_da, the Chebyshev points are
T_i = 303.15 + f_i * 10 for f = (0.1, 0.4, 0.6, 0.9), i.e. 304.15, 307.15,
309.15, 312.15 K, and

    dh_i = h_s(T_i) - [72.0 + 1.2 * 4.186 * (T_i - 303.15)]
         = 28.0517468, 30.5546328, 33.6545199, 40.7852585 kJ/kg_da,

so KaV/L = 4.186 * 10 / 4 * sum 1/dh_i = 1.28310338. The tower
characteristic at C = 1.7, n = 0.6, L/G = 1.2 is 1.7 * 1.2^-0.6 = 1.52384282.
"""

from __future__ import annotations

import math

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.heat.cooling_tower import CoolingTower
from ngdesign.units.heat.cooling_tower_r1 import (
    CHEBYSHEV_FRACTIONS,
    CoolingTowerConvergenceError,
    CoolingTowerSpecError,
    CoolingTowerR1,
    merkel_number_chebyshev,
    operating_line,
    tower_characteristic,
)

P_ATM = 1.01325e5

# ASHRAE Fundamentals 2017 SI Ch. 1, eq. 6 (Hyland-Wexler, over liquid).
_C8 = -5.8002206e3
_C9 = 1.3914993
_C10 = -4.8640239e-2
_C11 = 4.1764768e-5
_C12 = -1.4452093e-8
_C13 = 6.5459673


def _ashrae_p_ws(T: float) -> float:
    """Hyland-Wexler saturation pressure over liquid water, Pa."""
    return math.exp(_C8 / T + _C9 + _C10 * T + _C11 * T**2 + _C12 * T**3 + _C13 * math.log(T))


def _ashrae_h_s(T: float, P: float = P_ATM) -> float:
    """ASHRAE saturated-air enthalpy at T (K), kJ/kg dry air, at total P (Pa)."""
    t = T - 273.15
    p_ws = _ashrae_p_ws(T)
    w_s = 0.621945 * p_ws / (P - p_ws)
    return 1.006 * t + w_s * (2501.0 + 1.86 * t)


def test_ashrae_anchors() -> None:
    """The test's own constants against ASHRAE Table 3's 4.2467 kPa at 30 C."""
    assert _ashrae_p_ws(303.15) == pytest.approx(4246.03024, abs=1e-2)
    assert _ashrae_h_s(303.15) == pytest.approx(99.731526, abs=1e-5)


def test_closed_form_chebyshev_merkel() -> None:
    """The hand-computed Merkel number of the module docstring, rel 1e-8."""
    T_in, T_out, L_over_G, c_pw, h_a_in = 313.15, 303.15, 1.2, 4.186, 72.0
    ka_v_l = merkel_number_chebyshev(T_in, T_out, L_over_G, c_pw, _ashrae_h_s, h_a_in)
    assert ka_v_l == pytest.approx(1.28310338, rel=1e-8)

    # The printed Chebyshev ordinates, per the docstring hand computation.
    span = T_in - T_out
    h_a = operating_line(h_a_in, L_over_G, c_pw, T_out)
    expected_dh = (28.0517468, 30.5546328, 33.6545199, 40.7852585)
    for f, dh in zip(CHEBYSHEV_FRACTIONS, expected_dh, strict=True):
        T_i = T_out + f * span
        assert _ashrae_h_s(T_i) - h_a(T_i) == pytest.approx(dh, abs=1e-7)


def test_operating_line_touching_saturation_is_an_infinite_tower() -> None:
    """Any dh_i <= 0 means the operating line touches saturation: KaV/L = +inf."""
    # h_s ~ 100 kJ/kg_da everywhere below an operating line anchored at 120.
    ka_v_l = merkel_number_chebyshev(313.15, 303.15, 1.2, 4.186, lambda T: 100.0, 120.0)
    assert ka_v_l == math.inf


def test_tower_characteristic() -> None:
    """KaV/L = C (L/G)^-n: 1.7 * 1.2^-0.6 = 1.52384282."""
    assert tower_characteristic(1.7, 0.6, 1.2) == pytest.approx(1.52384282, rel=1e-8)


# --- Adapter (step 2) -----------------------------------------------------


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _r1_feeds(thermo: Thermo) -> dict[str, object]:
    """The R0 example feeds, flashed: water 313.15 K against humid 299.817 K air."""
    feeds, _params = CoolingTower.example_case()
    water = feeds["water_in"]
    air = feeds["air_in"]
    return {
        "water_in": thermo.flash_pt(water["composition"], water["T"], water["P"], water["molar_flow"]),
        "air_in": thermo.flash_pt(air["composition"], air["T"], air["P"], air["molar_flow"]),
    }


def test_r1_identity_reduces_to_r0() -> None:
    """R1 equals R0 run at R1's solved approach, bit for bit, on the example feeds."""
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    result = CoolingTowerR1().solve(
        feeds,
        {"characteristic_C": 1.7, "characteristic_n": 0.6, "cycles_of_concentration": 3.0},
        thermo,
    )
    approach = result.info["approach_K"]
    assert 1.0 <= approach <= 15.0

    r0 = CoolingTower().solve(feeds, {"approach_K": approach, "cycles_of_concentration": 3.0}, thermo)
    for port in ("water_out", "air_out"):
        a, b = result.outlets[port], r0.outlets[port]
        assert a.T == b.T
        assert a.P == b.P
        assert a.molar_flow == b.molar_flow
        assert a.enthalpy == b.enthalpy
        assert a.composition == b.composition


def test_larger_C_gives_a_strictly_smaller_water_outlet() -> None:
    """Monotonicity: a larger tower characteristic cools further (C in 1.0, 1.7, 2.5)."""
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    T_out = [
        CoolingTowerR1()
        .solve(feeds, {"characteristic_C": C, "characteristic_n": 0.6}, thermo)
        .outlets["water_out"]
        .T
        for C in (1.0, 1.7, 2.5)
    ]
    assert T_out[0] > T_out[1] > T_out[2]


def test_refuses_nonpositive_characteristic_C() -> None:
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    with pytest.raises(CoolingTowerSpecError, match="characteristic_C"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 0.0, "characteristic_n": 0.6}, thermo)


def test_refuses_negative_characteristic_n() -> None:
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    with pytest.raises(CoolingTowerSpecError, match="characteristic_n"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 1.7, "characteristic_n": -0.1}, thermo)


def test_refuses_approach_K_at_r1() -> None:
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    with pytest.raises(CoolingTowerSpecError, match="approach_K is solved at R1"):
        CoolingTowerR1().solve(
            feeds, {"characteristic_C": 1.7, "characteristic_n": 0.6, "approach_K": 5.0}, thermo
        )


def test_refuses_water_at_or_below_the_wet_bulb() -> None:
    """A saturated inlet air returns the dry bulb as its wet bulb; water below it is refused."""
    thermo = _thermo()
    y_sat = thermo.pure_psat("H2O", 305.0) / P_ATM
    feeds = {
        "water_in": thermo.flash_pt({"H2O": 1.0}, 300.0, P_ATM, 100.0),
        "air_in": thermo.flash_pt({"N2": 1.0 - y_sat, "H2O": y_sat}, 305.0, P_ATM, 3000.0),
    }
    with pytest.raises(CoolingTowerSpecError, match="wet bulb"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 1.7, "characteristic_n": 0.6}, thermo)


def test_refuses_zero_flow_water() -> None:
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    feeds["water_in"] = thermo.flash_pt({"H2O": 1.0}, 313.15, P_ATM, 0.0)
    with pytest.raises(ValueError, match="water"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 1.7, "characteristic_n": 0.6}, thermo)


def test_refuses_zero_flow_air() -> None:
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    feeds["air_in"] = thermo.flash_pt({"N2": 0.98, "H2O": 0.02}, 299.817, P_ATM, 0.0)
    with pytest.raises(ValueError, match="air"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 1.7, "characteristic_n": 0.6}, thermo)


def test_refuses_when_no_merkel_root_exists() -> None:
    """A characteristic no real tower can meet leaves r < 0 over the whole bracket."""
    thermo = _thermo()
    feeds = _r1_feeds(thermo)
    with pytest.raises(CoolingTowerConvergenceError, match="Merkel"):
        CoolingTowerR1().solve(feeds, {"characteristic_C": 1.0e6, "characteristic_n": 0.0}, thermo)
