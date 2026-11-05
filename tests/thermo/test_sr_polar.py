"""SR-POLAR (VTBMSR-III) density-only package tests (spec T11).

Layer 1 pins the paper's own worked numbers and the closed-form branch values;
layer 2 reproduces the T3 pack's nine Table 8 cases and checks the implementation
against the paper's own error column (the pack's intended binding check); layer 3
pins the refusal surface — what a density-only package must refuse, not return.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Callable
from pathlib import Path

import pytest

from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo.sr_polar import (
    SRPolarError,
    SRPolarPackage,
    _load_params,
    sr_polar_alpha,
    sr_polar_c_translation,
    sr_polar_m,
    sr_polar_molar_volume,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_CSV = REPO_ROOT / "data" / "validation" / "packs" / "T3" / "data.csv"

H2O = dict(omega=0.344, p0=-1.92140347, p1=-1.1392853, p2=0.22028766)


def _pack_cases() -> list[dict[str, str]]:
    with open(PACK_CSV, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# -- layer 1: the paper's worked values and closed-form branches -----------------


def test_m_matches_paper_worked_value() -> None:
    """m(omega=0.344) = 1.000461240 (T3 pack notes, worked example)."""
    assert sr_polar_m(0.344) == pytest.approx(1.000461240, abs=5e-10)


def test_alpha_subcritical_matches_paper_worked_value() -> None:
    """alpha(620.5 K, H2O set 3) = 1.059912028 (T3 pack notes, eq. 22a)."""
    tr = 620.5 / 647.14
    alpha = sr_polar_alpha(tr, sr_polar_m(H2O["omega"]), H2O["p0"], H2O["p1"], H2O["p2"])
    assert alpha == pytest.approx(1.059912028, abs=5e-10)


def test_alpha_supercritical_closed_form() -> None:
    """Tr > 1 branch (multiplication form): d = 1 + m/2 - p0(1 + p1 + p2),
    cd = 1 - 1/d, alpha = [exp(cd (1 - Tr^d))]^2 = exp(2 cd (1 - Tr^d)) —
    the squaring lives in the exponent's factor 2 (eq. 22b)."""
    m = sr_polar_m(H2O["omega"])
    d = 1.0 + 0.5 * m - H2O["p0"] * (1.0 + H2O["p1"] + H2O["p2"])
    cd = 1.0 - 1.0 / d
    tr = 1.1
    expected = math.exp(2.0 * cd * (1.0 - tr**d))
    alpha = sr_polar_alpha(tr, m, H2O["p0"], H2O["p1"], H2O["p2"])
    assert alpha == pytest.approx(expected, rel=1e-12)


def test_volume_translation_supercritical_zero_translation() -> None:
    """N2 ships c0 = c1 = c2 = 0: no volume translation in any regime (eq. 19)."""
    pure, _ = _load_params()
    p = pure["N2"]
    assert sr_polar_c_translation(0.9, p.b, p.c0, p.c1, p.c2) == 0.0
    assert sr_polar_c_translation(1.05, p.b, p.c0, p.c1, p.c2) == 0.0


def test_volume_translation_o2_supercritical_uses_general_branch() -> None:
    """O2 (c1 = 0, c0 != 0): c = c0 above Tr = 1 — and the subcritical
    reciprocal below, so the two regimes meet at Tr = 1 (eq. 17/19 continuity)."""
    pure, _ = _load_params()
    p = pure["O2"]
    assert sr_polar_c_translation(1.05, p.b, p.c0, p.c1, p.c2) == p.c0
    sub = sr_polar_c_translation(1.0, p.b, p.c0, p.c1, p.c2)
    assert sub == pytest.approx(p.c0, rel=1e-12)


def test_volume_translation_subcritical_matches_paper_worked_value() -> None:
    """c(620.5 K, H2O set 2) = 1.204378e-05 m3/mol (T3 pack notes, eq. 17)."""
    pure, _ = _load_params()
    p = pure["H2O"]
    c = sr_polar_c_translation(620.5 / 647.14, p.b, p.c0, p.c1, p.c2)
    assert c == pytest.approx(1.204378e-05, abs=5e-12)


def test_params_carry_every_binary_pair() -> None:
    """All six pairs of the published quaternary have k_b parameters."""
    _, binary = _load_params()
    ids = ("H2O", "O2", "N2", "CO2")
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            assert frozenset((a, b)) in binary, f"missing k_b for {a}/{b}"


# -- layer 2: the pack's Table 8 cases vs the paper's own error column -----------


def test_eos_back_solves_case_pressure() -> None:
    """Rebuilding p from the kernel's own root reproduces the case pressure.

    Internal consistency of the cubic solve: p = RT/(u - b) - a/(u (u + b))
    with u = v + c must return exactly the flashed pressure.
    """
    from ngdesign.thermo._state import R_IDEAL

    pure, binary = _load_params()
    z = {"H2O": 0.791, "O2": 0.0418, "N2": 0.1672}
    T, P = 620.5, 27.0e6
    v = sr_polar_molar_volume(z, T, P)
    # Rebuild a_mix / b_mix / c_mix exactly as the kernel does.
    ids = sorted(z)
    a_mix = b_mix = c_mix = 0.0
    for i, ci in enumerate(ids):
        pi = pure[ci]
        ti = T / pi.tc_k
        ai = pi.a_c * sr_polar_alpha(ti, sr_polar_m(pi.omega), pi.p0, pi.p1, pi.p2)
        a_mix += z[ci] ** 2 * ai
        b_mix += z[ci] ** 2 * pi.b
        c_mix += z[ci] * sr_polar_c_translation(ti, pi.b, pi.c0, pi.c1, pi.c2)
        for cj in ids[i + 1 :]:
            pj = pure[cj]
            tj = T / pj.tc_k
            aj = pj.a_c * sr_polar_alpha(tj, sr_polar_m(pj.omega), pj.p0, pj.p1, pj.p2)
            a_mix += 2.0 * z[ci] * z[cj] * (ai * aj) ** 0.5
            kb = binary[frozenset((ci, cj))].kb(T)
            b_mix += z[ci] * z[cj] * (pi.b + pj.b) * (1.0 - kb)
    u = v + c_mix
    p_back = R_IDEAL * T / (u - b_mix) - a_mix / (u * (u + b_mix))
    assert p_back == pytest.approx(P, rel=1e-8)


@pytest.mark.parametrize("case", _pack_cases(), ids=lambda c: c["case_id"])
def test_pack_cases_reproduce_paper_error_column(case: dict[str, str]) -> None:
    """The pack's intended binding check: our density error vs the paper's own
    VTBMSR-III error column, within 1 percentage point on every point."""
    z = {
        "H2O": float(case["x_H2O"]),
        "O2": float(case["z_O2"]),
        "N2": float(case["z_N2"]),
    }
    v = sr_polar_molar_volume(z, float(case["T_K"]), float(case["P_Pa"]))
    v_ref = float(case["v_ref_m3_per_mol"])
    our_err_pct = (v - v_ref) / v_ref * 100.0
    paper_err_pct = float(case["VTBMSR3_rel_err_pct"])
    assert abs(our_err_pct - paper_err_pct) <= 1.0, (
        f"{case['case_id']}: our error {our_err_pct:+.2f}% vs the paper's "
        f"{paper_err_pct:+.2f}% (limit 1.0 pp)"
    )


# -- layer 3: the density-only refusal surface -----------------------------------


@pytest.fixture()
def pkg() -> SRPolarPackage:
    return SRPolarPackage(("H2O", "O2", "N2"))


Z = {"H2O": 0.791, "O2": 0.0418, "N2": 0.1672}


def test_flash_pt_labels_water_dominant_state_aqueous(pkg: SRPolarPackage) -> None:
    state = pkg.flash_pt(Z, 620.5, 27.0e6, 1.0)
    assert len(state.phases) == 1
    assert state.phases[0].kind is PhaseKind.AQUEOUS
    assert state.vapor_fraction == 0.0


def test_flash_pt_labels_non_water_dominant_state_vapour(pkg: SRPolarPackage) -> None:
    state = pkg.flash_pt({"N2": 0.9, "O2": 0.1}, 200.0, 5.0e6, 1.0)
    assert state.phases[0].kind is PhaseKind.VAPOR
    assert state.vapor_fraction == 1.0


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.flash_ph(Z, 27.0e6, 0.0, 1.0),
        lambda p: p.flash_ps(Z, 27.0e6, 0.0, 1.0),
        lambda p: p.flash_tvf(Z, 620.5, 0.5, 1.0),
        lambda p: p.bubble_point(Z, T=620.5),
        lambda p: p.bubble_point(Z, P=27.0e6),
        lambda p: p.dew_point(Z, T=620.5),
        lambda p: p.dew_point(Z, P=27.0e6),
        lambda p: p.phase_props(Z, 620.5, 27.0e6, PhaseKind.HC_LIQUID),
        lambda p: p.derivatives(Z, 620.5, 27.0e6, PhaseKind.AQUEOUS),
    ],
)
def test_unsupported_operations_refuse_with_named_error(
    call: Callable[[SRPolarPackage], None], pkg: SRPolarPackage
) -> None:
    with pytest.raises(SRPolarError):
        call(pkg)


def test_pure_psat_and_k_values_are_none(pkg: SRPolarPackage) -> None:
    """No vapour-pressure model exists: not applicable, not zero."""
    assert pkg.pure_psat("H2O", 620.5) is None
    assert pkg.k_values(Z, 620.5, 27.0e6) is None


def test_unsupported_component_refuses() -> None:
    with pytest.raises(SRPolarError, match="H2O/O2/N2/CO2"):
        sr_polar_molar_volume({"H2O": 0.5, "C1": 0.5}, 400.0, 1.0e6)


def test_instances_are_deterministic() -> None:
    a = SRPolarPackage().flash_pt(Z, 620.5, 27.0e6, 1.0).model_dump()
    b = SRPolarPackage().flash_pt(Z, 620.5, 27.0e6, 1.0).model_dump()
    assert a == b
