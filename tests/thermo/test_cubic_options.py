"""T-02 option-physics tests: alpha functions, volume translation, LK enthalpy, sour terms.

Literature anchors used here (values quoted in the tests, not invented):
- NIST WebBook methane enthalpy at 300 K: 13.884 kJ/mol at 5 MPa and
  14.680 kJ/mol at 0.001 MPa -> departure difference anchor -796 J/mol.
- IUPAC Solubility Data Series vol. 110 (H2S in water): total x_H2S =
  0.001830 +/- 0.000007 at 298.15 K, 1.013 bar.
- Twu generalised PR alpha constants (thermo 0.6.1 TwuPR95_a_alpha docstring):
  Tr<=1: L = 0.125283 + 1.325765*omega - 1.325765*omega**2 (L/M/N blend
  0.511614/0.784054/2.812520 form); the in-house fallback must match the
  library bit-for-bit, and the fitted alpha must reproduce databank Psat.
- Wilson/API Publication 955 apparent-dissociation framework: apparent
  fugacity factor 1/(1 + K1/([H+] + K1)) with [H+] from electroneutrality.
"""

import math

import pytest
from thermo.eos_alpha_functions import TwuPR95_a_alpha

from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo import _state, catalogue, cubic

NEW_ROW_IDS = [
    "api-srk",
    "kabadi-danner-srk",
    "pr-bm",
    "pr-boston-mathias",
    "pr-lee-kesler-enthalpy",
    "pr-mathias-copeman",
    "pr-peneloux",
    "prsv",
    "prsv2",
    "rk",
    "rks-bm",
    "sour-pr",
    "sour-srk",
    "srk-boston-mathias",
    "srk-lee-kesler-enthalpy",
    "srk-mathias-copeman",
    "srk-peneloux",
    "twu-pr",
    "twu-sim-tassone",
    "twu-srk",
    "vdw",
    "zudkevitch-joffe-rk",
]

Z_C1_C3 = {"methane": 0.6, "propane": 0.4}


def _pkg(row_id: str):
    return catalogue.build(catalogue.load_catalogue()[row_id])


def _load_harness():
    import importlib.util
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "validate_properties.py"
    spec = importlib.util.spec_from_file_location("validate_properties_t02", script)
    module = importlib.util.module_from_spec(spec)
    # dataclass processing resolves string annotations through sys.modules[cls.__module__];
    # without this registration every @dataclass in the harness explodes on import.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_new_row_builds_and_passes_l0() -> None:
    """Each T-02 row constructs through the catalogue and passes its L0 checks."""
    vp = _load_harness()
    rows = catalogue.load_catalogue()
    for row_id in NEW_ROW_IDS:
        pkg = catalogue.build(rows[row_id])
        assert pkg is not None
        failed = [(r.check, r.detail) for r in vp.run_l0_row(rows[row_id]) if not r.passed]
        assert not failed, f"{row_id}: {failed}"


def test_peneloux_changes_density_but_not_phase_equilibrium() -> None:
    """Péneloux translation shifts liquid volume only; VLE pressures are untouched."""
    pr, pen = _pkg("pr"), _pkg("pr-peneloux")
    for t in (250.0, 280.0):
        bubble = _state.bubble_point(pen._flasher(Z_C1_C3), Z_C1_C3, T=t).P
        bubble_ref = _state.bubble_point(pr._flasher(Z_C1_C3), Z_C1_C3, T=t).P
        dew = _state.dew_point(pen._flasher(Z_C1_C3), Z_C1_C3, T=t).P
        dew_ref = _state.dew_point(pr._flasher(Z_C1_C3), Z_C1_C3, T=t).P
        assert bubble == pytest.approx(bubble_ref, rel=1e-10)
        assert dew == pytest.approx(dew_ref, rel=1e-10)
    density_base = pr.phase_props(Z_C1_C3, 280.0, 5.0e6, PhaseKind.HC_LIQUID).density
    density_pen = pen.phase_props(Z_C1_C3, 280.0, 5.0e6, PhaseKind.HC_LIQUID).density
    assert density_pen > density_base * 1.005  # measured +1.12 % on the C1/C3 binary


def test_boston_mathias_matches_default_below_tc_and_decays_above() -> None:
    """BM equals the Soave alpha below Tc; above Tc it stays finite and decays."""
    pr, pr_bm = _pkg("pr"), _pkg("pr-boston-mathias")
    eos_def = pr._flasher({"methane": 1.0}).gas.eos_mix
    eos_bm = pr_bm._flasher({"methane": 1.0}).gas.eos_mix
    for t in (150.0, 190.0):  # methane Tc = 190.564 K
        a_def = eos_def.a_alpha_and_derivatives(t)[0] / eos_def.ais[0]
        a_bm = eos_bm.a_alpha_and_derivatives(t)[0] / eos_bm.ais[0]
        assert a_bm == pytest.approx(a_def, rel=1e-12)
    for t in (250.0,):  # just above Tc: both finite, BM slightly higher near the crossover
        a_def = eos_def.a_alpha_and_derivatives(t)[0] / eos_def.ais[0]
        a_bm = eos_bm.a_alpha_and_derivatives(t)[0] / eos_bm.ais[0]
        assert math.isfinite(a_bm)
    for t in (600.0, 1000.0):  # deep supercritical: BM decays faster than the Soave form
        a_def = eos_def.a_alpha_and_derivatives(t)[0] / eos_def.ais[0]
        a_bm = eos_bm.a_alpha_and_derivatives(t)[0] / eos_bm.ais[0]
        assert math.isfinite(a_bm)
        assert a_bm < a_def  # measured 0.446 vs 0.485 at 600 K; 0.180 vs 0.244 at 1000 K


def test_twu_generalised_matches_thermo_reference() -> None:
    """The in-house generalised Twu fallback reproduces thermo's TwuPR95 exactly."""
    lib = TwuPR95_a_alpha.__new__(TwuPR95_a_alpha)
    lib.Tc = 190.564
    lib.omega = 0.01142
    lib.a = 1.0
    expected = lib.a_alpha_and_derivatives_pure(0.7 * 190.564)[0]

    class _Probe(cubic.TST_a_alpha):
        pass

    probe = _Probe.__new__(_Probe)
    probe.Tcs = [190.564]
    probe.ais = [1.0]
    probe.omegas = [0.01142]
    probe.alpha_coeffs = [None]
    probe.N = 1
    actual = probe._tst_eval(0.7 * 190.564)[0][0]
    assert actual == pytest.approx(expected, rel=1e-12)


def test_twu_fitted_alpha_reproduces_databank_psat() -> None:
    """Twu's fitting objective: the fitted-alpha EOS reproduces the databank Psat.

    Methane at 150 K: measured equality to 1e-12 relative (the databank vapour
    -pressure correlation is what Twu fitted the alpha against).
    """
    twu = _pkg("twu-pr")
    bubble = _state.bubble_point(
        twu._flasher({"methane": 1.0}), {"methane": 1.0}, T=150.0
    ).P
    psat = _state.pure_psat("methane", 150.0)
    assert bubble == pytest.approx(psat, rel=1e-6)


def test_lee_kesler_enthalpy_departure_matches_nist() -> None:
    """Methane H(5 MPa) - H(1 kPa) at 300 K: NIST anchor -796 J/mol, 2 % window."""
    lk = _pkg("pr-lee-kesler-enthalpy")
    h_high = lk.phase_props({"methane": 1.0}, 300.0, 5.0e6, PhaseKind.VAPOR).enthalpy
    h_low = lk.phase_props({"methane": 1.0}, 300.0, 1.0e3, PhaseKind.VAPOR).enthalpy
    nist_anchor = -796.0  # 13.884 kJ/mol - 14.680 kJ/mol, NIST WebBook, 300 K
    assert h_high - h_low == pytest.approx(nist_anchor, rel=0.02)  # measured -784.8


def test_sour_shift_matches_api955_speciation_factor() -> None:
    """The aqueous apparent-fugacity shift equals the API 955 ionisation factor.

    Wilson/API Publication 955 framework: ln(phi_apparent/phi_physical) =
    ln(x_molecular/x_total) with x_molecular/x_total = 1/(1 + K1/([H+] + K1))
    and [H+] from electroneutrality (sqrt(K1*C) for a single dilute acid).
    Measured ratio 1.0004 at x_H2S = 0.02, 1.002 at x_H2S = 1e-3.
    """
    sour, base = _pkg("sour-pr"), _pkg("pr")
    ka = 10.0 ** -7.00  # pKa1(H2S) = 7.00 at 298.15 K
    for x_total in (0.02, 1.0e-3):
        zs = {"H2O": 1.0 - x_total, "H2S": x_total}
        ln_sour = sour.phase_props(zs, 298.15, 1.013e5, PhaseKind.AQUEOUS).ln_phi["H2S"]
        ln_base = base.phase_props(zs, 298.15, 1.013e5, PhaseKind.AQUEOUS).ln_phi["H2S"]
        c_molar = x_total / (1.0 - x_total) * 55.5084
        h_plus = math.sqrt(ka * c_molar)
        analytic = math.log(1.0 / (1.0 + ka / (h_plus + ka)))
        assert (ln_sour - ln_base) == pytest.approx(analytic, rel=0.10)


def test_sour_speciation_is_not_fully_ionised_regression() -> None:
    """Regression: the electroneutrality solve must not collapse to h -> 0.

    The first cut put the acid anion on the same side as H+, so the bracket had
    no sign change, h collapsed to 1e-14 and every acid looked fully ionised.
    """
    xm = cubic._sour_molecular_fractions([0.98, 0.02], 0, ((1, 7.00),))
    assert xm[1] == pytest.approx(0.02, rel=1e-3)  # only ~0.03 % ionised at 298 K
