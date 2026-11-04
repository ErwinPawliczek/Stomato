"""COSMO-SAC 2010 (cosmo_sac_ig) against the published benchmark of Bell et al. (2020).

Two oracles, both read from usnistgov/COSMOSAC (commit 1b82456b, retrieved 2026-11-04):

- profiles/validation_data.zip, validation_data.csv: the reference implementation's ln gamma
  for profile pairs at 298.15 K, z = (0.3, 0.7) (Bell et al., J. Chem. Theory Comput. 16,
  2635 (2020), the benchmark set). The csv's lngamma includes the dsp term; the 2010 model
  value is lngamma - lngamma_disp.
- tests/catch_tests.cpp: Hsieh, Lin & Vrabec, Fluid Phase Equilib. 367, 109 (2014), Table 6,
  infinite-dilution ln gamma split into combinatorial and residual parts (tolerance 2e-3 on
  the residual, as in the reference test: the paper's profiles predate the UD re-processing).
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.thermo.cosmo_sac import CosmoSac, cosmo_sac_ln_gammas, load_profile
from ngdesign.thermo.ge_models import gammas_from_ge

# (CAS 0, CAS 1, lngamma0, lngamma1, lngamma0_disp, lngamma1_disp) from validation_data.csv
BENCHMARK_298K = [
    (
        "67-64-1",
        "75-05-8",
        0.1422687324893092,
        0.03825136734271359,
        0.029399056019566217,
        0.005399826615838694,
    ),
    (
        "67-66-3",
        "64-17-5",
        0.301206746548173,
        -0.0044967078300816345,
        0.07219201549465169,
        0.01325975794799725,
    ),
    (
        "142-82-5",
        "110-82-7",
        -0.015203487591861437,
        -0.0033048346327944887,
        0.0,
        0.0,
    ),
    (
        "64-17-5",
        "75-05-8",
        0.6326543650092366,
        0.16169784563175313,
        0.02007939316546319,
        0.0036880518059014024,
    ),
    (
        "67-56-1",
        "71-43-2",
        0.9387156675795554,
        0.3001374126951058,
        0.2835824556335939,
        0.05208657348372133,
    ),
    (
        "67-56-1",
        "110-54-3",
        1.3721584038572625,
        0.36089126520225806,
        0.26165270456734213,
        0.04805866002257305,
    ),
    (
        "71-43-2",
        "75-05-8",
        0.48934394594551023,
        0.08564783158886852,
        0.06384552537209202,
        0.011726729149976089,
    ),
    (
        "107-06-2",
        "108-88-3",
        0.02493832822387139,
        0.005010303128384482,
        0.007630803545757555,
        0.0014015761614656734,
    ),
]

# (solute CAS, solvent CAS, T, ln gamma comb, ln gamma res) - Hsieh 2014 Table 6
HSIEH_2014_TABLE6 = [
    ("109-66-0", "142-82-5", 293.15, -0.0317, 0.0001),
    ("109-66-0", "71-43-2", 298.15, -0.0075, 0.8001),
    ("109-66-0", "107-06-2", 298.15, -0.0146, 1.2032),
    ("109-66-0", "75-05-8", 298.15, -0.1610, 3.3610),
    ("109-66-0", "67-64-1", 298.15, -0.0513, 1.1924),
    ("71-43-2", "121-44-8", 323.5, -0.0413, 0.2426),
    ("108-88-3", "141-78-6", 298.2, 0.0094, -0.0185),
    ("67-66-3", "110-54-3", 301.0, -0.0434, 0.3346),
    ("67-64-1", "71-36-3", 298.0, -0.0255, 0.5548),
    ("109-66-0", "64-17-5", 298.0, -0.1214, 1.8569),
    ("71-43-2", "7732-18-5", 298.0, -1.0519, 8.4222),
    ("109-66-0", "7732-18-5", 298.15, -1.3733, 12.3241),
]


@pytest.mark.parametrize(("a", "b", "lg0", "lg1", "d0", "d1"), BENCHMARK_298K)
def test_reproduces_the_bell_2020_benchmark(
    a: str, b: str, lg0: float, lg1: float, d0: float, d1: float
) -> None:
    profiles = [load_profile(a, a), load_profile(b, b)]
    got = cosmo_sac_ln_gammas(298.15, [0.3, 0.7], profiles)
    assert got[0] == pytest.approx(lg0 - d0, abs=1e-6)
    assert got[1] == pytest.approx(lg1 - d1, abs=1e-6)


@pytest.mark.parametrize(("solute", "solvent", "T", "comb", "res"), HSIEH_2014_TABLE6)
def test_infinite_dilution_matches_hsieh_2014_table6(
    solute: str, solvent: str, T: float, comb: float, res: float
) -> None:
    profiles = [load_profile(solute, solute), load_profile(solvent, solvent)]
    total = cosmo_sac_ln_gammas(T, [0.0, 1.0], profiles)[0]
    assert total == pytest.approx(comb + res, abs=2e-3)


def test_ge_derivatives_are_consistent() -> None:
    profiles = [load_profile("MeOH", "67-56-1"), load_profile("H2O", "7732-18-5")]
    model = CosmoSac(xs=[0.4, 0.6], T=330.0, profiles=profiles)
    lng = model.ln_gammas()
    assert [float(g) for g in gammas_from_ge(model)] == pytest.approx(
        [2.718281828459045**v for v in lng], rel=1e-6
    )
    # Gibbs-Duhem: sum x_i d ln gamma_i = 0 along x
    d = model.d2GE_dxixjs()
    assert 0.4 * (d[0][0] - d[0][1]) + 0.6 * (d[1][0] - d[1][1]) == pytest.approx(0.0, abs=1e-3)
    # pure limit: ln gamma of a pure component is zero
    assert cosmo_sac_ln_gammas(330.0, [1.0, 0.0], profiles)[0] == pytest.approx(0.0, abs=1e-10)


def test_unshipped_component_refuses() -> None:
    with pytest.raises(ValueError, match="no COSMO-SAC sigma profile"):
        registry.create("thermo", "cosmo_sac_ig").bubble_point({"MeOH": 0.5, "MEG": 0.5}, P=101325.0)


def test_row_bubble_point_on_gao_methanol_water() -> None:
    point = registry.create("thermo", "cosmo_sac_ig").bubble_point(
        {"MeOH": 0.3442, "H2O": 0.6558}, P=101325.0
    )
    # Gao et al. 2012 Table 3: 349.05 K measured; the predictive model lands within 0.5 %
    assert point.T == pytest.approx(349.05, rel=5e-3)
