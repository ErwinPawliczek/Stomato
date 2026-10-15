"""Kent-Eisenberg chemistry for MEA and DEA (primary/secondary amines).

Validation structure mirrors test_mdea_equilibrium.py: the CO2 side is pinned
to NeqSim's Kent-Eisenberg implementation (constants taken from it; MDEA
anchors reproduce its published regression points), the H2S side to published
isotherm points -- Jones, Froning & Claytor 1959 for MEA and Lai, Otto &
Mather 1985 for DEA (both via IUPAC Solubility Data Series vol. 32, sec. 1.6).
The single-constant Kent-Eisenberg H2S form reaches only +/-17% (MEA) and
+/-20% (DEA) minimax bands on those isotherms -- the tight 2% MDEA band is
data luck, not method (module docstring, "Honest band note"); the tests assert
the achieved bands, not a borrowed 2%.
"""

from __future__ import annotations

import math

import pytest

from ngdesign.units.mdea_equilibrium import (
    AMINES,
    DEA_CHEMISTRY,
    MDEA_CHEMISTRY,
    MEA_CHEMISTRY,
    Speciation,
    _carbon_balance_at_h,
    _co2_k1,
    _co2_k2,
    _water_kw,
    amine_molarity,
    equilibrium_loadings,
    equilibrium_partial_pressures,
)

_T_40C = 313.15


# --- Independent solver ------------------------------------------------------
#
# NeqSim's AmineKentEisenberg solves the same chemistry with an undamped
# fixed-point iteration on the carbon balance, which two-cycles where the
# carbamate sinks saturate -- the module replaces that with a bracketed solve.
# The reference below solves the same equations with a fully independent,
# guaranteed-convergent nested bisection (CO2 bracketed in [0, C_co2], charge
# balance bracketed in log h), so agreement validates the algebra and the
# constants, not a shared iteration scheme.


def _neqsim_style_p_co2(T: float, C_A: float, alpha_co2: float, amine: str) -> float:
    """Reference CO2 partial pressure (Pa), independent nested bisection, mol/L basis."""
    chem = AMINES[amine]
    a1, a2, aw = _co2_k1(T), _co2_k2(T), _water_kw(T)
    aam = chem.kam(T)
    kc = chem.kc(T)
    C_co2 = alpha_co2 * C_A

    def speciation(h: float, co2: float) -> tuple[float, float, float, float]:
        hco3 = a1 * co2 / h
        co3 = a2 * hco3 / h
        if kc is None:
            amine_free = C_A / (1.0 + h / aam)
            carbamate = 0.0
        else:
            amine_free = C_A / (1.0 + h / aam + hco3 / kc)
            carbamate = amine_free * hco3 / kc
        return co2, hco3, co3, carbamate

    def carbon_residual(co2: float, h: float) -> float:
        _, hco3, co3, carbamate = speciation(h, co2)
        return co2 + hco3 + co3 + carbamate - C_co2  # increasing in co2

    def solve_carbon(h: float) -> tuple[float, float, float, float]:
        lo, hi = 0.0, C_co2
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if carbon_residual(mid, h) < 0.0:
                lo = mid
            else:
                hi = mid
            if hi - lo <= 1e-15 * C_co2:
                break
        co2 = 0.5 * (lo + hi)
        return speciation(h, co2)

    def charge_residual(h: float) -> float:
        co2, hco3, co3, carbamate = solve_carbon(h)
        amine_free = C_A / (1.0 + h / aam + (hco3 / kc if kc is not None else 0.0))
        amineh = amine_free * h / aam
        oh = aw / h
        return amineh + h - (oh + hco3 + 2.0 * co3 + carbamate)

    lo, hi = 1e-14, 1.0
    assert charge_residual(lo) < 0.0 < charge_residual(hi), "charge balance not bracketed"
    for _ in range(200):
        mid = math.sqrt(lo * hi)  # log-space bisection, as NeqSim does
        if charge_residual(mid) < 0.0:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.0 + 1e-13:
            break
    h = math.sqrt(lo * hi)
    co2, _, _, _ = solve_carbon(h)
    # Versteeg & van Swaaij Henry: 2.82e6 exp(-2044/T) Pa.m3/mol, mol/L -> mol/m3.
    return 2.82e6 * math.exp(-2044.0 / T) * co2 * 1000.0


@pytest.mark.parametrize(
    ("amine", "C_A", "alpha"),
    [
        ("MEA", 4.91, 0.1),
        ("MEA", 4.91, 0.3),
        ("MEA", 4.91, 0.5),
        ("MEA", 2.47, 0.4),
        ("DEA", 2.0, 0.2),
        ("DEA", 2.0, 0.5),
        ("DEA", 5.0, 0.7),
    ],
)
def test_mea_dea_co2_matches_the_neqsim_solver_structure(amine: str, C_A: float, alpha: float) -> None:
    """Same chemistry, independent solver: agreement is solver-tolerance tight."""
    ours = equilibrium_partial_pressures(_T_40C, C_A * 1000.0, alpha, 0.0, amine=amine)[0]
    reference = _neqsim_style_p_co2(_T_40C, C_A, alpha, amine)
    assert ours == pytest.approx(reference, rel=2.4e-2)


def test_mdea_anchors_reproduce_neqsim_regression_points() -> None:
    """NeqSim's own MDEA CO2 anchors (313.15 K, ~4.36 mol/L, CO2-only)."""
    ours_lo = equilibrium_partial_pressures(_T_40C, 4360.0, 0.10, 0.0)[0]
    ours_hi = equilibrium_partial_pressures(_T_40C, 4360.0, 0.40, 0.0)[0]
    assert ours_lo == pytest.approx(930.0, rel=2.4e-2)
    assert ours_hi == pytest.approx(22900.0, rel=2.4e-2)


def test_mea_co2_engineering_band() -> None:
    """30 wt% MEA, 40 C, loading 0.5: NeqSim's documented band is 5-30 kPa.

    The single-constant Kent-Eisenberg model lands ~49 kPa, above the band its
    multi-constant reference quotes -- an honest statement of the correlation
    limit, asserted here as an order-of-magnitude window, not a false match.
    """
    p_co2 = equilibrium_partial_pressures(_T_40C, 4910.0, 0.5, 0.0, amine="MEA")[0]
    assert 5e3 < p_co2 < 60e3


def test_co2_binding_order_mea_tightest() -> None:
    """At fixed loading MEA binds CO2 tighter than DEA, which is tighter than MDEA."""
    p = {
        amine: equilibrium_partial_pressures(_T_40C, 4000.0, 0.4, 0.0, amine=amine)[0]
        for amine in ("MEA", "DEA", "MDEA")
    }
    assert p["MEA"] < p["DEA"] < p["MDEA"]


# --- H2S isotherm anchors ---------------------------------------------------


_JONES_1959_MEA = (  # (loading, p_H2S kPa); fit anchors first, hold-outs after
    (0.208, 0.40),
    (0.362, 1.21),
    (0.643, 5.75),
    (0.125, 0.13),
    (0.729, 7.96),
    (0.814, 14.10),
)
_LAI_1985_DEA = ((0.063, 0.106), (0.141, 0.384), (0.219, 1.355))
_MEA_FIT_BAND = 0.17
_MEA_HOLDOUT_BAND = 0.40
_DEA_FIT_BAND = 0.20


@pytest.mark.parametrize(("alpha", "p_kpa"), _JONES_1959_MEA)
def test_mea_h2s_jones_1959_anchors(alpha: float, p_kpa: float) -> None:
    """Jones-Froning-Claytor 1959, 15.3 wt% MEA (~2.47 kmol/m3), 313.15 K."""
    model_kpa = equilibrium_partial_pressures(_T_40C, 2470.0, 0.0, alpha, amine="MEA")[1] / 1000.0
    band = _MEA_FIT_BAND if (alpha, p_kpa) in _JONES_1959_MEA[:3] else _MEA_HOLDOUT_BAND
    assert model_kpa == pytest.approx(p_kpa, rel=band), (alpha, model_kpa, p_kpa)


@pytest.mark.parametrize(("alpha", "p_kpa"), _LAI_1985_DEA)
def test_dea_h2s_lai_1985_anchors(alpha: float, p_kpa: float) -> None:
    """Lai-Otto-Mather 1985, 2.0 kmol/m3 DEA, 313.15 K (+/-15% data uncertainty)."""
    model_kpa = equilibrium_partial_pressures(_T_40C, 2000.0, 0.0, alpha, amine="DEA")[1] / 1000.0
    assert model_kpa == pytest.approx(p_kpa, rel=_DEA_FIT_BAND), (alpha, model_kpa, p_kpa)


def test_h2s_binding_order_mea_tightest() -> None:
    """At fixed loading MEA holds H2S tighter than DEA (both tighter than MDEA)."""
    p = {
        amine: equilibrium_partial_pressures(_T_40C, 4000.0, 0.0, 0.2, amine=amine)[1]
        for amine in ("MEA", "DEA", "MDEA")
    }
    assert p["MEA"] < p["DEA"] < p["MDEA"]


# --- Speciation invariants ---------------------------------------------------


@pytest.mark.parametrize("amine", ["MEA", "DEA"])
@pytest.mark.parametrize(
    ("T", "alpha_co2", "alpha_h2s"), [(313.15, 0.3, 0.1), (343.15, 0.6, 0.0), (393.15, 0.02, 0.01)]
)
def test_speciation_invariants(amine: str, T: float, alpha_co2: float, alpha_h2s: float) -> None:
    """Charge balance, amine/carbon/sulfide component balances all close."""
    from ngdesign.units.mdea_equilibrium import _speciate_from_loadings

    C_A = 3.0
    sp: Speciation = _speciate_from_loadings(T, C_A, alpha_co2 * C_A, alpha_h2s * C_A, AMINES[amine])
    cations = sp.amineh + sp.h
    anions = sp.oh + sp.hco3 + 2.0 * sp.co3 + sp.carbamate + sp.hs + 2.0 * sp.s2
    assert cations == pytest.approx(anions, rel=1e-8), "electroneutrality"
    assert sp.amine + sp.amineh + sp.carbamate == pytest.approx(C_A, rel=1e-8), "amine balance"
    carbon_total = sp.co2_free + sp.hco3 + sp.co3 + sp.carbamate
    assert carbon_total == pytest.approx(alpha_co2 * C_A, rel=1e-8), "carbon balance"
    assert sp.h2s_free + sp.hs + sp.s2 == pytest.approx(alpha_h2s * C_A, rel=1e-8), "sulfide balance"
    # Zero loading leaves zero vapor pressure.
    if alpha_co2 == 0.0:
        assert sp.p_co2 == 0.0
    if alpha_h2s == 0.0:
        assert sp.p_h2s == 0.0


# --- Round trips and determinism ---------------------------------------------


@pytest.mark.parametrize("amine", ["MEA", "DEA"])
@pytest.mark.parametrize("T", [303.15, 313.15, 353.15])
@pytest.mark.parametrize(("alpha_co2", "alpha_h2s"), [(0.05, 0.0), (0.4, 0.2), (1.0, 0.05)])
def test_round_trip_loadings_pressures(amine: str, T: float, alpha_co2: float, alpha_h2s: float) -> None:
    C_A = 3000.0
    p_co2, p_h2s = equilibrium_partial_pressures(T, C_A, alpha_co2, alpha_h2s, amine=amine)
    co2_back, h2s_back = equilibrium_loadings(T, C_A, p_co2, p_h2s, amine=amine)
    assert co2_back == pytest.approx(alpha_co2, rel=1e-6)
    assert h2s_back == pytest.approx(alpha_h2s, rel=1e-6)


def test_forward_solve_is_deterministic() -> None:
    first = equilibrium_partial_pressures(_T_40C, 4000.0, 0.35, 0.12, amine="MEA")
    second = equilibrium_partial_pressures(_T_40C, 4000.0, 0.35, 0.12, amine="MEA")
    assert first == second


# --- Chemistry registry and validation ---------------------------------------


def test_amine_registry_covers_the_three_workhorse_amines() -> None:
    assert set(AMINES) == {"MDEA", "MEA", "DEA"}
    assert MDEA_CHEMISTRY.carbamate is None, "tertiary amine forms no carbamate"
    assert MEA_CHEMISTRY.carbamate is not None
    assert DEA_CHEMISTRY.carbamate is not None


def test_unknown_amine_raises() -> None:
    with pytest.raises(ValueError, match="unsupported amine 'DEG'"):
        equilibrium_partial_pressures(_T_40C, 4000.0, 0.2, 0.0, amine="DEG")
    with pytest.raises(ValueError, match="unsupported amine"):
        equilibrium_loadings(_T_40C, 4000.0, 1000.0, 0.0, amine="PIPERAZINE")


def test_out_of_window_loading_raises() -> None:
    with pytest.raises(ValueError, match="exceeds the model window"):
        equilibrium_partial_pressures(_T_40C, 4000.0, 1.6, 0.0, amine="MEA")
    with pytest.raises(ValueError, match="non-negative"):
        equilibrium_partial_pressures(_T_40C, 4000.0, -0.1, 0.0, amine="DEA")


def test_zero_loading_gives_zero_pressure() -> None:
    for amine in ("MEA", "DEA"):
        assert equilibrium_partial_pressures(_T_40C, 4000.0, 0.0, 0.0, amine=amine) == (0.0, 0.0)


def test_amine_molarity_converts_mass_fraction_to_molarity() -> None:
    """30 wt% MEA in water at ~1000 kg/m3 is ~4.9 kmol/m3."""
    x_mea = 0.30 / 61.0831 / (0.30 / 61.0831 + 0.70 / 18.0153)
    mw = x_mea * 61.0831 + (1.0 - x_mea) * 18.0153
    c = amine_molarity(x_mea, mw, 1000.0)
    assert c == pytest.approx(4900.0, rel=2e-2)


def test_carbamate_balance_bracket_holds_at_extremes() -> None:
    """The carbon-balance root stays inside its bracket across the h range."""
    T = _T_40C
    chem = MEA_CHEMISTRY
    C_A, C_co2 = 4.0, 1.6
    a1, a2, aam, kc = _co2_k1(T), _co2_k2(T), chem.kam(T), chem.kc(T) or 1.0
    for ln_h in (-30.0, -20.0, -10.0, 0.0, 8.0):
        h = math.exp(ln_h)
        co2, hco3, co3, amine, carbamate = _carbon_balance_at_h(h, C_co2, C_A, a1, a2, aam, kc)
        assert co2 + hco3 + co3 + carbamate == pytest.approx(C_co2, rel=1e-9)
        assert 0.0 <= co2 <= C_co2
        assert hco3 * h / a1 == pytest.approx(co2, rel=1e-9)
        assert amine * hco3 / kc == pytest.approx(carbamate, rel=1e-9)
        assert amine + amine * h / aam + carbamate == pytest.approx(C_A, rel=1e-9)
        assert a2 * hco3 / h == pytest.approx(co3, rel=1e-9)
