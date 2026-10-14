"""Validation of the TEG water-activity correlation against published data.

The implemented model is the Parrish-Won-Baltatu correlation (Parrish, W.R.,
Won, K.W. and Baltatu, M.E., 1986, "Phase behavior of the triethylene
glycol-water system and dehydration/regeneration design for extremely low dew
point requirements", Proc. 65th GPA Convention, San Antonio, TX), the model
recommended by the GPSA Engineering Data Book (10th ed., 1994) for glycol
dehydration design, as parameterized in Filep, Todinca & Dumitrel (2022),
Chem. Biochem. Eng. Q. 36(1) 25-38, eqs. 12-17.

Independent published anchors used here (data/ is a locked path, so the
reference numbers are cited inline instead):

- Gironi, F., Maschietti, M., Piemonte, V. (2007), "Modelling triethylene
  glycol-water system for natural gas dehydration", Proc. ICHEAP-8:
  * the Parrish-model infinite-dilution extrapolation gives
    gamma_w_inf = 0.9477 at 204 degC (477.15 K) -- a direct regression check
    of the implemented coefficients;
  * a van Laar fit of the Herskowitz & Gottlieb isopiestic activity data
    (Herskowitz, M. and Gottlieb, M., 1984, J. Chem. Eng. Data 29, 173)
    gives gamma_w_inf = 0.616 at 297.6 K and 0.748 at 332.6 K, and Gironi et
    al. note the Herskowitz extrapolation sits closer to Bestani & Shing
    (1989) than to Parrish -- so the implemented (Parrish) infinite-dilution
    coefficient must fall below the van Laar values at both temperatures;
  * the Herskowitz & Gottlieb data itself spans gamma_w ~ 0.55-0.95 over
    x_w = 0.2-0.95 at 297.6 and 332.6 K (Gironi et al., Fig. 2).
- Locked-sample feasibility: the sample slice (lean TEG 98.7 wt%, 325.15 K,
  7.1 MPa, spec 7 lb/MMscf) is reachable only if the equilibrium floor
  a_w * Psat / P lies below 7 lb/MMscf -- the v1 ideal model (~9.7 lb/MMscf
  floor) fails this; the published-data-anchored correlation passes.
"""

from __future__ import annotations

import pytest
from chemicals.vapor_pressure import Psat_IAPWS

from ngdesign.units.teg_activity import (
    activity_equilibrium_slope,
    water_activity,
    water_activity_coefficient,
)

#: Gironi, Maschietti & Piemonte (2007), sec. 4: Parrish-model gamma_w
#: infinite-dilution extrapolation at 204 degC.
GIRONI_PARRISH_GAMMA_INF_477K = 0.9477

#: Van Laar fit of the Herskowitz & Gottlieb (1984) data, Gironi et al. (2007).
VAN_LAAR_GAMMA_INF = {297.6: 0.616, 332.6: 0.748}


def test_infinite_dilution_matches_published_parrish_extrapolation() -> None:
    """Regression check: gamma_w_inf at 477.15 K must reproduce Gironi's 0.9477."""
    gamma_inf = water_activity_coefficient(477.15, 1.0e-9)
    assert gamma_inf == pytest.approx(GIRONI_PARRISH_GAMMA_INF_477K, rel=1e-3)


@pytest.mark.parametrize("T", sorted(VAN_LAAR_GAMMA_INF))
def test_infinite_dilution_below_van_laar_fit_of_herskowitz_data(T: float) -> None:
    """Parrish-model gamma_w_inf sits below the van Laar fit of Herskowitz data."""
    gamma_inf = water_activity_coefficient(T, 1.0e-9)
    assert 0.3 < gamma_inf < VAN_LAAR_GAMMA_INF[T]


@pytest.mark.parametrize("T", [297.6, 332.6])
@pytest.mark.parametrize("x_water", [0.2, 0.5, 0.95])
def test_activity_coefficient_within_herskowitz_envelope(T: float, x_water: float) -> None:
    """Herskowitz & Gottlieb data spans gamma_w ~ 0.55-0.95 over x_w = 0.2-0.95."""
    gamma = water_activity_coefficient(T, x_water)
    assert 0.5 < gamma < 1.0


def test_activity_below_mole_fraction() -> None:
    """gamma_w < 1 over the TEG frame: activity depression, a_w < x_w."""
    for T in (297.6, 325.15, 332.6):
        for x_water in (0.05, 0.1, 0.5, 0.9):
            assert water_activity(T, x_water) < x_water


def test_pure_water_and_pure_teg_degenerate_to_unity() -> None:
    assert water_activity_coefficient(325.15, 1.0) == pytest.approx(1.0)
    assert water_activity_coefficient(325.15, 0.0) == pytest.approx(1.0)


def test_slice_conditions_equilibrium_floor_below_spec() -> None:
    """Locked sample slice (98.7 wt% lean TEG, 325.15 K, 7.1 MPa) is reachable.

    Slice spec: 7 lb/MMscf. The v1 ideal floor (~9.7 lb/MMscf) made it
    infeasible; the published-data-anchored activity floor must sit below it.
    """
    x_water_lean = 0.0989  # mole fraction of water in 98.7 wt% TEG
    T, P = 325.15, 7.1e6
    m = activity_equilibrium_slope(T, P, x_water_lean)
    y_star = m * x_water_lean
    floor_lb_per_mmscf = y_star / (1.0 + y_star) * 18.015 * (1.0e6 / 379.49)

    assert floor_lb_per_mmscf < 7.0  # slice spec reachable
    assert floor_lb_per_mmscf > 3.0  # physical: a real depression, not a collapse
    assert y_star < 1.4747e-4  # v1 pinch point (xfail reason in the S-30 test)


def test_ideal_slope_is_the_activity_free_limit() -> None:
    """The activity slope is strictly below the v1 ideal slope (Psat/P) for any TEG solution."""
    for x_water in (0.02, 0.0989, 0.3):
        m_act = activity_equilibrium_slope(325.15, 7.1e6, x_water)
        m_ideal = Psat_IAPWS(325.15) / 7.1e6
        assert 0.0 < m_act < m_ideal
