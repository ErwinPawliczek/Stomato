"""T-05 literature anchors for the kvalue correlation family.

Sources (retrieved this task, see the PR body for retrieval notes):
- Binary methane/propane K-values: Reamer, Sage & Lacey, Ind. Eng. Chem. 42 (1950)
  534, as compiled in the IUPAC Solubility Data Series vol. 27/28 (Methane),
  pp. 270-271. K_C1 = y_C1/x_C1, K_C3 = (1-y_C1)/(1-x_C1). The spec's
  Seader-Henley-Roper section 2.11 worked-example table is not available from
  accessible published sources, so the compiled binary measurements carry the
  same 5 % criterion (recorded as a spec deviation).
- Braun K10: the chart at 1 bar / 300 K reads K_C3 = 10.0 -- the low-pressure
  ideal-K asymptote of the Braun K10 charts (Cajander, Hipkin & Lenoir 1960).
- LKP density: GPSA Engineering Data Book compressibility example, methane at
  750 psia / 60 F: rho = 38.12 kg/m3, Z = 0.905 (values from a web compilation
  of the GPSA sample; flagged in the PR body).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind


def _pkg(model_id: str) -> Any:
    return registry.create("thermo", model_id)


def test_ideal_equals_psat_over_p() -> None:
    """The spec's exactness check: ideal K is Psat/P to machine precision."""
    pkg = _pkg("ideal-raoult")
    P = 500000.0
    k = pkg.k_values({"C3": 0.5, "nC4": 0.5}, 300.0, P)
    assert k is not None
    assert k["C3"] == pytest.approx(pkg.pure_psat("C3", 300.0) / P, rel=1e-12)
    assert k["nC4"] == pytest.approx(pkg.pure_psat("nC4", 300.0) / P, rel=1e-12)


def test_braun_k10_propane_at_1bar() -> None:
    """Braun K10 chart value for propane at 1 bar / 300 K within 10 %."""
    pkg = _pkg("braun-k10")
    # Binary feed: the low-pressure asymptote K_i = Psat_i/P is composition-free.
    k = pkg.k_values({"C3": 0.5, "nC4": 0.5}, 300.0, 100000.0)
    assert k is not None
    chart = 10.0  # Braun K10 chart reading: low-pressure ideal-K asymptote
    assert abs(k["C3"] - chart) / chart <= 0.10
    assert k["C3"] == pytest.approx(pkg.pure_psat("C3", 300.0) / 100000.0, rel=1e-9)


def test_chao_seader_reamer_sage_277_59k() -> None:
    """Chao-Seader on the Reamer-Sage-Lacey C1/C3 state at 277.59 K, 4.826 MPa."""
    pkg = _pkg("chao-seader")
    k = pkg.k_values({"C1": 0.2834, "C3": 0.7166}, 277.59, 4826000.0)
    assert k is not None
    assert k["C1"] == pytest.approx(2.87036, rel=0.05)
    assert k["C3"] == pytest.approx(0.2602, rel=0.05)


def test_grayson_streed_saturation_anchors() -> None:
    """Grayson-Streed bubble pressure against databank saturation points (8 %)."""
    pkg = _pkg("grayson-streed")
    for cid, T in (("C3", 300.0), ("CO2", 265.0)):
        psat = pkg.pure_psat(cid, T)
        bub = pkg.bubble_point({cid: 1.0}, T=T)
        assert bub is not None
        assert bub.P == pytest.approx(psat, rel=0.08)


def test_lkp_reamer_sage_294_26k() -> None:
    """Lee-Kesler-Ploecker on the Reamer-Sage-Lacey C1/C3 state at 294.26 K."""
    pkg = _pkg("lee-kesler-ploecker")
    k = pkg.k_values({"C1": 0.1987, "C3": 0.8013}, 294.26, 4137000.0)
    assert k is not None
    assert k["C1"] == pytest.approx(3.54202, rel=0.05)
    assert k["C3"] == pytest.approx(0.369649, rel=0.05)


def test_lkp_gpsa_methane_vapour_density() -> None:
    """GPSA natural-gas example: LKP methane vapour density within 2 %."""
    pkg = _pkg("lee-kesler-ploecker")
    T, P = 288.706, 5171071.2  # 60 F, 750 psia
    vals = pkg.phase_props({"C1": 1.0}, T, P, PhaseKind.VAPOR)
    assert vals.density == pytest.approx(38.12, rel=0.02)


def test_henry_sander_methane_in_water() -> None:
    """Henry row on the methane-in-water anchor at 298.2 K, 4.54 MPa (10 %)."""
    pkg = _pkg("henry-sander")
    k = pkg.k_values({"C1": 0.001, "H2O": 0.999}, 298.2, 4540000.0)
    assert k is not None
    assert k["C1"] == pytest.approx(999.3, rel=0.10)
