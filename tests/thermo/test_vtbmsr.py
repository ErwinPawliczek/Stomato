"""VTBMSR-III density-only adapter tests (catalogue row ``vtbmsr3``, board job CQ1).

Oracle: Mangold, Pilz, Bjelic & Vogel, J. Supercrit. Fluids 153 (2019) 104476,
doi:10.1016/j.supflu.2019.02.016 (CC BY 4.0), Table 8. It prints the paper's own
VTBMSR-III relative molar-volume error against the Japas & Franck water-air data for
18 states (air x_O2/x_N2 = 1/4, as the paper assumes). A faithful implementation of
the same model with the same parameters reproduces those errors. The printed errors
are rounded to 0.1 % and the water fractions to 3 decimals; the measured max
|ours - paper| over all 18 points is 0.65 percentage points. The bound below is 1.0
percentage point, chosen as the printed-rounding allowance plus margin.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo.vtbmsr import (
    VtbmsrError,
    VtbmsrPackage,
    load_parameters,
    mixture_volume,
    rks_constants,
    sqrt_alpha,
    volume_translation,
)

REPO = Path(__file__).resolve().parents[2]

# Mangold 2019 Table 8: (x_H2O, T [K], P [MPa], reference v [1e-6 m3/mol], VTBMSR-III error [%]).
TABLE_8 = [
    (0.791, 620.5, 27.0, 120.8, 0.4),
    (0.795, 638.5, 44.0, 68.6, -0.6),
    (0.797, 640.0, 68.3, 46.7, -4.0),
    (0.797, 642.0, 102.0, 37.3, -6.8),
    (0.798, 645.5, 152.9, 31.8, -10.1),
    (0.798, 650.0, 195.3, 29.5, -12.3),
    (0.798, 652.0, 214.8, 28.7, -13.1),
    (0.798, 653.5, 231.5, 28.1, -13.7),
    (0.798, 657.0, 263.9, 27.2, -15.0),
    (0.791, 673.0, 33.3, 120.8, -0.3),
    (0.795, 673.0, 52.2, 68.9, 0.3),
    (0.797, 673.0, 80.9, 46.7, -2.6),
    (0.797, 673.0, 118.6, 37.4, -6.4),
    (0.798, 673.0, 172.6, 31.9, -10.7),
    (0.798, 673.0, 214.2, 29.5, -12.7),
    (0.798, 673.0, 233.0, 28.7, -13.5),
    (0.798, 673.0, 249.3, 28.1, -14.1),
    (0.798, 673.0, 279.5, 27.2, -15.4),
]


def _air(x_h2o: float) -> dict[str, float]:
    x_air = 1.0 - x_h2o
    return {"H2O": x_h2o, "O2": x_air / 5.0, "N2": 4.0 * x_air / 5.0}


@pytest.mark.parametrize(("x_h2o", "T", "p_mpa", "v_ref", "paper_err"), TABLE_8)
def test_reproduces_mangold_table8_model_errors(
    x_h2o: float, T: float, p_mpa: float, v_ref: float, paper_err: float
) -> None:
    v = mixture_volume(load_parameters(), _air(x_h2o), T, p_mpa * 1e6)
    ours = (v * 1e6 - v_ref) / v_ref * 100.0
    assert abs(ours - paper_err) <= 1.0, f"ours {ours:.2f} % vs Mangold {paper_err} %"


def test_rks_constants_match_table1_omegas() -> None:
    """Eqs. 15-16 give Omega_a = 0.42748, Omega_b = 0.08664 (Mangold 2019 Table 1)."""
    R = 8.31446261815324
    a_c, b = rks_constants(300.0, 5e6)
    assert a_c * 5e6 / (R * 300.0) ** 2 == pytest.approx(0.42748, abs=5e-6)
    assert b * 5e6 / (R * 300.0) == pytest.approx(0.08664, abs=5e-6)


def test_alpha_and_translation_continuous_at_tc() -> None:
    """Eq. 22a/22b both give sqrt(alpha) = 1 at Tr = 1; eq. 20 meets eq. 17 at Tr = 1."""
    w = load_parameters().components["H2O"]
    below = sqrt_alpha(w.omega, w.p0, w.p1, w.p2, 1.0 - 1e-9)
    above = sqrt_alpha(w.omega, w.p0, w.p1, w.p2, 1.0 + 1e-9)
    assert below == pytest.approx(1.0, abs=1e-7)
    assert above == pytest.approx(1.0, abs=1e-7)
    _, b = rks_constants(w.Tc, w.Pc)
    c_lo = volume_translation(w.c0, w.c1, w.c2, b, 1.0 - 1e-9)
    c_hi = volume_translation(w.c0, w.c1, w.c2, b, 1.0 + 1e-9)
    assert c_hi == pytest.approx(c_lo, rel=1e-6)
    assert c_lo == pytest.approx(w.c0 + w.c1 / w.c2, rel=1e-6)


def test_parameters_agree_with_t3_pack_params_csv() -> None:
    """Cross-check of the transcription: every value used equals the T3 pack's params.csv."""
    rows = list(csv.DictReader((REPO / "data/validation/packs/T3/params.csv").open()))
    pack: dict[tuple[str, str, str], float] = {}
    for r in rows:
        try:
            pack[(r["compound"], r["set"], r["parameter"])] = float(r["value"])
        except ValueError:
            continue  # the "0 (all three)" rows for the zero pairs
    p = load_parameters()
    water = p.components["H2O"]
    for name in ("p0", "p1", "p2"):
        assert getattr(water, name) == pack[("H2O(v/sc)", "3", name)]
    for name in ("c0", "c1", "c2"):
        assert getattr(water, name) == pack[("H2O(l)", "2", name)]  # Table 5 prints one c-set for water
    assert p.components["O2"].p0 == pack[("O2", "1 (ci) / x1 (pi)", "p0")]
    assert p.components["O2"].c0 == pack[("O2", "1 (ci) / x1 (pi)", "c0")]
    assert p.components["N2"].p1 == pack[("N2", "1", "p1")]
    assert p.components["CO2"].p2 == pack[("CO2", "1 (T5) / 2 (SI)", "p2")]
    assert p.components["CO2"].c0 == pack[("CO2", "1", "c0")]
    for pair, key in (
        (("H2O", "O2"), "H2O/O2"),
        (("H2O", "N2"), "H2O/N2"),
        (("H2O", "CO2"), "H2O/CO2"),
        (("CO2", "N2"), "CO2/N2"),
    ):
        kb = p.kb[frozenset(pair)]
        assert kb == tuple(pack[(key, "2 (reg. density)", f"kb{i}")] for i in range(3))
    for cid, compound in (("H2O", "H2O"), ("O2", "O2"), ("N2", "N2"), ("CO2", "CO2")):
        c = p.components[cid]
        assert c.Tc == pack[(compound, "-", "Tc")]
        assert c.Pc == pack[(compound, "-", "pc")] * 1e6
        assert c.omega == pack[(compound, "-", "omega")]


def test_registered_row_flash_pt_is_density_only() -> None:
    pkg = registry.create("thermo", "vtbmsr3")
    state = pkg.flash_pt(_air(0.797), 642.0, 102e6, 1.0)
    assert len(state.phases) == 1
    ph = state.phases[0]
    assert ph.kind is PhaseKind.VAPOR
    assert ph.density > 0.0
    assert ph.z_factor is not None and ph.z_factor > 0.0
    assert math.isnan(ph.enthalpy) and math.isnan(ph.cp) and math.isnan(state.enthalpy)
    props = pkg.phase_props(_air(0.797), 642.0, 102e6, PhaseKind.VAPOR)
    assert props.density == ph.density


def test_refuses_outside_scope() -> None:
    pkg = VtbmsrPackage()
    with pytest.raises(VtbmsrError, match="pseudo-critical"):
        pkg.flash_pt({"H2O": 1.0}, 400.0, 10e6, 1.0)  # compressed liquid water
    with pytest.raises(VtbmsrError, match="parameters for"):
        pkg.flash_pt({"H2O": 0.5, "C1": 0.5}, 700.0, 10e6, 1.0)
    with pytest.raises(VtbmsrError):
        pkg.phase_props(_air(0.797), 642.0, 102e6, PhaseKind.AQUEOUS)
    with pytest.raises(VtbmsrError):
        pkg.bubble_point(_air(0.797), T=642.0)
    with pytest.raises(VtbmsrError):
        pkg.flash_ph(_air(0.797), 102e6, 0.0, 1.0)
    assert pkg.pure_psat("H2O", 500.0) is None
    assert pkg.k_values(_air(0.797), 642.0, 102e6) is None
