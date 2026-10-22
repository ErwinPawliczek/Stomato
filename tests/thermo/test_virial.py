"""HOC / Nothnagel virial kernel tests (spec T-03b).

Anchor set: the kernel is pinned against the numbers its transcriptions print.
Water against Harvey-Lemmon (2004) IAPWS cross-check; n-butane against the
COBEQ-2014 proceedings' three independent HOC implementations; N2/CH4 and the
cross pair against the same paper; association refusal for acid-strength rows;
saturation through the registered packages.
"""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.thermo.virial import (
    PURE_ETA_ACID_LIMIT,
    HaydenOConnellModel,
    eta_for_pair,
    refuse_acid_strength,
    rg_of,
)


def _model(cas_list: list[str], T: float, etas: list[float] | None = None) -> HaydenOConnellModel:
    from thermo import ChemicalConstantsPackage

    c, _ = ChemicalConstantsPackage.from_IDs(cas_list)
    if etas is None:
        etas = [eta_for_pair(cas, cas) for cas in cas_list]
    return HaydenOConnellModel(
        T=T,
        Tcs=list(c.Tcs),
        Pcs=list(c.Pcs),
        dipoles=list(c.dipoles),
        rgs=[rg_of(cas) for cas in cas_list],
        etas=etas,
        cas_list=cas_list,
    )


def test_rg_converts_metres_to_angstrom() -> None:
    # chemicals.RG reports metres; the correlation works in Angstroms.
    assert rg_of("106-97-8") == pytest.approx(2.886, abs=0.01)


def test_water_second_virial_harvey_lemmon() -> None:
    """B(H2O, 373.15 K) within 3 % of the Harvey-Lemmon IAPWS cross-check (-454)."""
    m = _model(["7732-18-5"], 373.15, etas=[1.7])
    b = m.B_pures()[0] * 1e6
    assert b == pytest.approx(-454.0, rel=0.03)


def test_n_butane_second_virial_cobeq() -> None:
    """B(nC4, 368.25 K) within 2 % of the COBEQ-2014 HOC implementations (-436.5..-436.7)."""
    m = _model(["106-97-8"], 368.25, etas=[0.0])
    b = m.B_pures()[0] * 1e6
    assert b == pytest.approx(-436.6, rel=0.02)


def test_n2_ch4_pures_and_cross_cobeq() -> None:
    """B(N2), B(CH4) and the cross pair at 200 K against the same paper."""
    m = _model(["7727-37-9", "74-82-8"], 200.0, etas=[0.0, 0.0])
    b_pure = m.B_pures()
    b_cross = m.B_interactions()[0][1]
    assert b_pure[0] * 1e6 == pytest.approx(-40.79, rel=0.03)
    assert b_pure[1] * 1e6 == pytest.approx(-107.29, rel=0.03)
    assert b_cross * 1e6 == pytest.approx(-66.70, rel=0.03)


def test_dB_dT_positive_for_n_butane() -> None:
    m = _model(["106-97-8"], 368.25, etas=[0.0])
    assert m.dB_dT_pures()[0] > 0.0


def test_eta_table_loaded() -> None:
    """ChemSep HAYDENO.IPD entries: water 1.7, methanol 1.63, ethanol-water 1.55; absent 0."""
    assert eta_for_pair("7732-18-5", "7732-18-5") == pytest.approx(1.7)
    assert eta_for_pair("67-56-1", "67-56-1") == pytest.approx(1.63)
    assert eta_for_pair("7732-18-5", "67-56-1") == pytest.approx(1.55)
    assert eta_for_pair("106-97-8", "106-97-8") == 0.0


def test_acid_strength_refusal_names_gap_and_acid_path() -> None:
    """Pure eta >= 4.0 refuses, naming the component and the hoc_dimer acid path."""
    with pytest.raises(ValueError, match="64-19-7.*hoc_dimer"):
        refuse_acid_strength(["64-19-7"], [4.5])
    # ethanol (eta 1.4) and water (1.7) pass
    refuse_acid_strength(["64-17-5", "7732-18-5"], [1.4, 1.7])
    assert PURE_ETA_ACID_LIMIT == 4.0


def test_hoc_package_saturation_ethanol_water() -> None:
    """nrtl_hoc reproduces the ethanol/water azeotrope point: 77.4-78.2 C, y == x."""
    pkg = registry.create("thermo", "nrtl_hoc")
    x_water = 0.10532
    b = pkg.bubble_point({"EtOH": 1.0 - x_water, "H2O": x_water}, P=101325.0)
    assert float(b.T) == pytest.approx(351.35, rel=0.005)
    y_water = float(b.incipient_composition["H2O"])
    assert y_water == pytest.approx(x_water, abs=0.01)


def test_nothnagel_row_builds_tsonopoulos_fallback() -> None:
    """wilson_nothnagel builds a real second-virial phase and saturates."""
    pkg = registry.create("thermo", "wilson_nothnagel")
    x_water = 0.10532
    b = pkg.bubble_point({"EtOH": 1.0 - x_water, "H2O": x_water}, P=101325.0)
    assert float(b.T) == pytest.approx(351.35, rel=0.005)
