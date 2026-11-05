"""Chao-Seader / Grayson-Streed fidelity checks against published worked numbers.

Sources (retrieved 2026-11-04):
- Henley, E. J. & Seader, J. D., Equilibrium-Stage Separation Operations in Chemical
  Engineering, Wiley 1981, p. 188-189: eqs. 5-11..5-13, the Grayson-Streed constant
  table and Example 5.2 (benzene, Tr 0.8489, Pr 0.5745, omega 0.2115696:
  log nu0_0 = -0.271485, log nu0_1 = -0.254672, log nu0 = -0.325366). archive.org scan
  'equilibrium-stage-separation-operations-in-chemical-engineering'.
- Saxena, A. C., Hydrocarbon vapor-liquid equilibria in the presence of hydrogen
  sulphide and carbon dioxide, thesis 1966, archive.org 'Saxena1966', Table 5:
  an independent implementation's predicted K-values. Printed p. 126 (Chao-Seader
  constants, methane/n-pentane at 100 F): 500 psia, exp K 5.88 / 0.071, predicted
  K_C1 5.49; 1000 psia, exp K 3.08 / 0.077, predicted K_C1 3.04. Printed p. 129
  (Grayson-Streed constants, methane/n-butane at 100 F, 400 psia, exp K 6.75 / 0.200):
  predicted K_C1 5.74, K_nC4 0.193.
The phase compositions are the experimental ones, x_C1 = (1 - K2)/(K1 - K2),
y_C1 = K1 x_C1; Saxena evaluated at his own flash compositions (L ~ 51 %), so his
three-digit predictions are matched to 1 %. With the former methane omega_cs = 0.011
the methane K-values came out 11 % low (4.88, 2.70, 5.11).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.thermo import kvalue

_PSIA = 6894.757293168
_T_100F = 310.9278


def _pkg(model_id: str) -> Any:
    return registry.create("thermo", model_id)


def _k_at_experimental_phases(model_id: str, heavy: str, k1: float, k2: float, psia: float) -> list[float]:
    pkg = _pkg(model_id)
    sup = pkg._support(("C1", heavy))
    x1 = (1.0 - k2) / (k1 - k2)
    y1 = k1 * x1
    return list(pkg._model_k(sup, [x1, 1.0 - x1], [y1, 1.0 - y1], _T_100F, psia * _PSIA))


def test_grayson_streed_nu0_reproduces_henley_seader_example_5_2() -> None:
    """GS simple-fluid nu0 with the printed constants (A1 = -2.10899)."""
    nu = kvalue._nu0("grayson_streed", 78.11, 0.2115696, 0.8489, 0.5745, 1.0, 1.0)
    assert math.log10(nu) == pytest.approx(-0.325366, abs=2e-6)


@pytest.mark.parametrize(
    ("psia", "k1_exp", "k2_exp", "k1_saxena"),
    [(500.0, 5.88, 0.071, 5.49), (1000.0, 3.08, 0.077, 3.04)],
)
def test_chao_seader_methane_k_matches_saxena(
    psia: float, k1_exp: float, k2_exp: float, k1_saxena: float
) -> None:
    k = _k_at_experimental_phases("chao-seader", "nC5", k1_exp, k2_exp, psia)
    assert k[0] == pytest.approx(k1_saxena, rel=0.01)


def test_grayson_streed_methane_k_matches_saxena() -> None:
    k = _k_at_experimental_phases("grayson-streed", "nC4", 6.75, 0.200, 400.0)
    assert k[0] == pytest.approx(5.74, rel=0.01)
    assert k[1] == pytest.approx(0.193, rel=0.01)


def test_chao_seader_bubble_point_has_a_vapour_incipient_phase() -> None:
    """Regression: the bubble search converged on a liquid-root "vapour" (1.57 MPa, y_C1 0.32).

    The loop was seeded with K evaluated at y = z; the Redlich-Kwong cubic then has only
    its liquid root for the vapour side. Sage et al. 1942 (IUPAC SDS 27/28 p. 306)
    measured 4.137 MPa, y_C1 0.943 at this state.
    """
    pkg = _pkg("chao-seader")
    sat = pkg.bubble_point({"C1": 0.1911, "nC5": 0.8089}, T=310.93)
    assert 3.0e6 < sat.P < 4.6e6
    assert sat.incipient_composition["C1"] > 0.9


@pytest.mark.parametrize("model_id", ["chao-seader", "grayson-streed", "lee-kesler-ploecker"])
def test_flash_below_bubble_pressure_is_two_phase(model_id: str) -> None:
    """Regression: a C1/nC5 feed at 2 MPa (bubble point above 3 MPa) flashed as all liquid.

    The single-phase test used K(x = z, y = z), i.e. a liquid-composition vapour.
    """
    pkg = _pkg(model_id)
    z = {"C1": 0.1911, "nC5": 0.8089}
    state = pkg.flash_pt(z, 310.93, 2.0e6, 1.0)
    assert 0.0 < state.vapor_fraction < 1.0
