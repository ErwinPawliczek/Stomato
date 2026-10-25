"""Closed-form tests: multi-stream R2 pure functions (spec Tests, R2 closed form).

Every expected number below is the spec's independent reference from
``calc_multi_stream.py`` (not the module's own output). The Manglik & Bergles
(1995) correlation constants were verified against the paper's equation 34
pair as cited in the secondary literature (techno-press.org ACD 10(2) eq. 23;
IntechOpen compact-HEX chapter Table 3):

    j = 0.6522 Re^-0.5403 alpha^-0.1541 delta^0.1499 gamma^-0.0678
        [1 + 5.269e-5 Re^1.340 alpha^0.504 delta^0.456 gamma^-1.055]^0.1
    f = 9.6243 Re^-0.7422 alpha^-0.1856 delta^0.3053 gamma^-0.2659
        [1 + 7.669e-8 Re^4.429 alpha^0.920 delta^3.767 gamma^0.236]^0.1

Geometry (spec): s 1.5 mm, h_f 6.35 mm, t 0.15 mm, l 3.175 mm gives
D_h = 4 s h_f l / [2(s l + h_f l + t h_f) + t s] = 0.00232730508 m (hand check
in the test). Fin efficiency at h = 500 W/m2K, k_fin = 180 W/mK:
m = sqrt(2*500/(180*0.00015)) = 192.45009 1/m, L_f = h_f/2 = 3.175 mm,
eta_f = tanh(m L_f)/(m L_f), eta_o = 1 - (h_f/(s+h_f))(1 - eta_f).
"""

from __future__ import annotations

import pytest

from ngdesign.units.heat.multi_stream_r2 import (
    FinGeometry,
    fin_efficiency,
    manglik_bergles_f,
    manglik_bergles_j,
    osf_channels_per_layer,
    osf_free_flow_area_m2,
    osf_heat_transfer_area_m2,
    osf_hydraulic_diameter_m,
    surface_efficiency,
)

#: The spec's test geometry (m): s 1.5 mm, h_f 6.35 mm, t 0.15 mm, l 3.175 mm.
_GEOM = FinGeometry(
    fin_height_m=0.00635, fin_spacing_m=0.0015, fin_thickness_m=0.00015, strip_length_m=0.003175
)

_ALPHA, _DELTA, _GAMMA = 0.5, 0.1, 0.05


def test_hydraulic_diameter() -> None:
    """D_h of the spec geometry (rel 1e-8)."""
    assert osf_hydraulic_diameter_m(_GEOM) == pytest.approx(0.00232730508, rel=1e-8)


def test_dimensionless_parameters_from_geometry() -> None:
    """alpha = s/h_f, delta = t/l, gamma = t/s on the spec geometry."""
    assert _GEOM.alpha == pytest.approx(0.0015 / 0.00635)
    assert _GEOM.delta == pytest.approx(0.00015 / 0.003175)
    assert _GEOM.gamma == pytest.approx(0.00015 / 0.0015)


def test_areas_per_layer() -> None:
    """A_ff and A_ht follow their definitions (self-consistent, 1 m layer width)."""
    width, length = 1.0, 1.0
    n = osf_channels_per_layer(_GEOM.fin_spacing_m, _GEOM.fin_thickness_m, width)
    assert osf_free_flow_area_m2(_GEOM, width) == pytest.approx(_GEOM.fin_spacing_m * _GEOM.fin_height_m * n)
    assert osf_heat_transfer_area_m2(_GEOM, length, width) == pytest.approx(
        2.0 * (_GEOM.fin_spacing_m + _GEOM.fin_height_m) * length * n
    )


@pytest.mark.parametrize(
    ("Re", "j_expected", "f_expected"),
    [
        (1000.0, 0.0174026135, 0.108645137),
        (5000.0, 0.00883863219, 0.0670128063),
    ],
)
def test_manglik_bergles_j_and_f(Re: float, j_expected: float, f_expected: float) -> None:
    """Manglik-Bergles j and Fanning f at alpha 0.5, delta 0.1, gamma 0.05 (rel 1e-8)."""
    assert manglik_bergles_j(Re, _ALPHA, _DELTA, _GAMMA) == pytest.approx(j_expected, rel=1e-8)
    assert manglik_bergles_f(Re, _ALPHA, _DELTA, _GAMMA) == pytest.approx(f_expected, rel=1e-8)


def test_fin_and_surface_efficiency() -> None:
    """m = 192.45009 1/m, eta_f = 0.891694218, eta_o = 0.91238959 (rel 1e-8)."""
    m, eta_f = fin_efficiency(500.0, 180.0, _GEOM)
    assert m == pytest.approx(192.45009, rel=1e-8)
    assert eta_f == pytest.approx(0.891694218, rel=1e-8)
    assert surface_efficiency(500.0, 180.0, _GEOM) == pytest.approx(0.91238959, rel=1e-8)
