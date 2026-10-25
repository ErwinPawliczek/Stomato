"""Closed-form and geometry-refusal tests for plate_exchanger R1, step 1 (spec).

The closed-form numbers are the spec's test table 1-4, hand-computed from the
spec's equations with geometry P1 (0.5 mm amplitude, 3.7 mm wavelength, 45 deg,
0.3 x 1.2 m plates, 50 mm ports, 51 plates => 25 channels per fluid,
A_ch = b*width = 1e-3*0.3 = 3.0e-4 m2, D_h = 0.0017223766473078426 m from
``fluids.geometry.PlateExchanger``), independent of the module under test:

Case 1 (laminar branch), m 3 kg/s, rho 990, mu 6.0e-4, k 0.63, cp 4180:
  v = 3/(990*25*3.0e-4) = 0.404040404... m/s
  Re = 990*0.404040404*0.0017223766473078426/6.0e-4 = 1148.2511
  Pr = 4180*6.0e-4/0.63 = 3.98095238
  f  = [cos45/sqrt(0.18 tan45 + 0.36 sin45 + (64/1148.2511)/cos45)
        + (1 - cos45)/sqrt(3.8*(597/1148.2511 + 3.85))]^-2 = 0.892089304
  Nu = 0.122*3.98095238^(1/3)*(0.892089304*1148.2511^2*1)^0.374 = 36.0342748
  h  = Nu*k/D_h = 36.0342748*0.63/0.0017223766473078426 = 13180.3884 W/m2K
  channel dP = f*(1.2/D_h)*990*v^2/2 = 50224.5717 Pa
  v_port = 3/(990*pi*0.05^2/4) = 1.54332066 m/s
  port dP = 1.4*990*v_port^2/2 = 1650.61419 Pa
Case 2 (turbulent branch), m 8 kg/s, same fluid:
  v = 8/7.425 = 1.07744108 m/s, Re = 3062.00293,
  f0 = (1.8*log10(3062.00293) - 1.5)^-2 (Konakov), f1 = 39*Re^-0.289,
  f = 0.857073074, Nu = 73.9326645, h = 27042.6208 W/m2K
Case 3: friction spot values f(500,45) = 1.06688451, f(500,60) = 2.3862954,
  f(2500,45) = 0.867587711, f(2500,60) = 1.94223808.
Case 4: U with both films h = 13180.3884, t_p = 0.6 mm, k_p = 16:
  U = 1/(2/13180.3884 + 0.0006/16) = 5284.2784 W/m2K.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.units.heat.plate_exchanger_r1 import (
    PlateGeometryError,
    channel_Re,
    channel_velocity,
    friction_martin_vdi,
    nusselt_martin_vdi,
    overall_u,
    plate_geometry,
    port_dP,
    port_velocity,
)

GEOMETRY_P1: dict[str, Any] = {
    "amplitude_m": 5.0e-4,
    "wavelength_m": 3.7e-3,
    "chevron_angle_deg": 45.0,
    "plate_width_m": 0.3,
    "plate_length_m": 1.2,
    "port_diameter_m": 0.05,
    "n_plates": 51,
}


def test_geometry_p1() -> None:
    """Geometry P1: b = 1 mm, A_ch = 3.0e-4 m2, 25 channels/fluid, D_h from fluids."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    assert geom.b_m == pytest.approx(1.0e-3, rel=1e-8)
    assert geom.A_channel_m2 == pytest.approx(3.0e-4, rel=1e-8)
    assert geom.channels_per_fluid == pytest.approx(25.0, rel=1e-8)
    assert geom.D_h_m == pytest.approx(0.0017223766473078426, rel=1e-8)


def test_closed_form_laminar_branch() -> None:
    """Case 1: v, Re, Pr, f, Nu, h, channel dP, port v and port dP at 3 kg/s."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    v = channel_velocity(3.0, 990.0, geom.A_channel_m2, geom.channels_per_fluid)
    assert v == pytest.approx(0.404040404, rel=1e-8)
    Re = channel_Re(990.0, v, geom.D_h_m, 6.0e-4)
    assert Re == pytest.approx(1148.2511, rel=1e-8)
    Pr = 4180.0 * 6.0e-4 / 0.63
    assert Pr == pytest.approx(3.98095238, rel=1e-8)
    f = friction_martin_vdi(Re, 45.0)
    assert f == pytest.approx(0.892089304, rel=1e-8)
    Nu = nusselt_martin_vdi(Re, Pr, 45.0, f)
    assert Nu == pytest.approx(36.0342748, rel=1e-8)
    h = Nu * 0.63 / geom.D_h_m
    assert h == pytest.approx(13180.3884, rel=1e-8)
    channel_dp = f * (1.2 / geom.D_h_m) * 990.0 * v * v / 2.0
    assert channel_dp == pytest.approx(50224.5717, rel=1e-8)
    v_port = port_velocity(3.0, 990.0, 0.05)
    assert v_port == pytest.approx(1.54332066, rel=1e-8)
    assert port_dP(990.0, v_port) == pytest.approx(1650.61419, rel=1e-8)


def test_closed_form_turbulent_branch() -> None:
    """Case 2: the Konakov branch at Re 3062.00293."""
    geom = plate_geometry(dict(GEOMETRY_P1))
    v = channel_velocity(8.0, 990.0, geom.A_channel_m2, geom.channels_per_fluid)
    assert v == pytest.approx(1.07744108, rel=1e-8)
    Re = channel_Re(990.0, v, geom.D_h_m, 6.0e-4)
    assert Re == pytest.approx(3062.00293, rel=1e-8)
    f = friction_martin_vdi(Re, 45.0)
    assert f == pytest.approx(0.857073074, rel=1e-8)
    Nu = nusselt_martin_vdi(Re, 4180.0 * 6.0e-4 / 0.63, 45.0, f)
    assert Nu == pytest.approx(73.9326645, rel=1e-8)
    assert Nu * 0.63 / geom.D_h_m == pytest.approx(27042.6208, rel=1e-8)


@pytest.mark.parametrize(
    ("re", "angle", "expected"),
    [
        (500.0, 45.0, 1.06688451),
        (500.0, 60.0, 2.3862954),
        (2500.0, 45.0, 0.867587711),
        (2500.0, 60.0, 1.94223808),
    ],
)
def test_friction_spot_values(re: float, angle: float, expected: float) -> None:
    """Case 3: the explicit VDI form matches the spec's four spot values."""
    assert friction_martin_vdi(re, angle) == pytest.approx(expected, rel=1e-8)


def test_overall_u() -> None:
    """Case 4: U with both films at 13180.3884 W/m2K, 0.6 mm plate, k 16."""
    u = overall_u(
        h_hot=13180.3884,
        h_cold=13180.3884,
        t_plate_m=6.0e-4,
        k_plate=16.0,
        R_f_hot=0.0,
        R_f_cold=0.0,
    )
    assert u == pytest.approx(5284.2784, rel=1e-8)


def test_missing_param_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="amplitude_m"):
        plate_geometry({k: v for k, v in GEOMETRY_P1.items() if k != "amplitude_m"})


def test_nonpositive_geometry_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="plate_width_m"):
        plate_geometry({**GEOMETRY_P1, "plate_width_m": 0.0})


def test_too_few_plates_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="n_plates"):
        plate_geometry({**GEOMETRY_P1, "n_plates": 2})


def test_chevron_angle_out_of_range_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="chevron_angle_deg"):
        plate_geometry({**GEOMETRY_P1, "chevron_angle_deg": 85.0})


def test_bad_correlation_refuses() -> None:
    with pytest.raises(PlateGeometryError, match="correlation"):
        plate_geometry({**GEOMETRY_P1, "correlation": "taborek"})
