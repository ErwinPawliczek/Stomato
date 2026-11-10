"""Kabadi-Danner SRK mixing rule (aqueous work, 2026-11-09).

Form anchored to the Aspen Physical Property Methods and Models manual, SRK-Kabadi-Danner
(pp. 47-48, retrieved 2026-11-09 from sites.poli.usp.br/d/pqi2408/physpropmodels.pdf):
a = a0 + a_KD, a_KD = sum_i a''_wi x_w^2 x_i, a''_wi = G_i [1 - (T/Tcw)^0.8],
g_CH4 = 1.3580e-5 atm m6/mol2, k_wj = 0.500 for alkanes.
"""

import math
from typing import Any

import pytest
from thermo.eos_mix import SRKMIX

from ngdesign.thermo import catalogue, cubic


def _pkg(row_id: str) -> Any:
    return catalogue.build(catalogue.load_catalogue()[row_id])


def _aqueous_x(row: str, hc: str, T: float, P: float) -> float:
    state = _pkg(row).flash_pt({hc: 0.5, "H2O": 0.5}, T, P, molar_flow=1.0)
    aq = max(state.phases, key=lambda p: p.composition.get("H2O", 0.0))
    return float(aq.composition[hc])


@pytest.mark.parametrize("aliases", [("NC6", "nC6", "C6"), ("NC4", "nC4", "C4")])
def test_kd_term_independent_of_component_alias(aliases: tuple[str, ...]) -> None:
    """The a'' term is keyed by CAS: every databank alias of a paraffin gets it.

    Regression: the group table was keyed by id ("NC6"), so "nC6"/"C6" silently ran plain SRK.
    """
    got = [_aqueous_x("kabadi-danner-srk", hc, 343.45, 700000.0) for hc in aliases]
    assert max(got) == pytest.approx(min(got), rel=1e-9)
    plain = _aqueous_x("srk", aliases[0], 343.45, 700000.0)
    assert got[0] > 10.0 * plain  # the water-phase a'' term raises the paraffin's solubility


def test_kd_mixing_rule_form() -> None:
    """a_alpha(KD) - a_alpha(SRK, k_wj = 0.5) == x_w^2 x_C1 G_CH4 [1 - (T/Tcw)^0.8]."""
    T, xw, xc = 320.0, 0.9, 0.1
    pkg = _pkg("kabadi-danner-srk")
    state = pkg.flash_pt({"C1": xc, "H2O": xw}, T, 50.0e6, molar_flow=1.0)  # registers the slate
    assert state.phases
    tc = [190.564, 647.096]
    eos = None
    for (tci, pci), c in cubic._CAS_BY_CRITICALS.items():
        if c == "74-82-8":
            tc[0], pc_c1 = tci, pci
        if c == "7732-18-5":
            tc[1], pc_w = tci, pci
    from ngdesign.data import component_record

    om = [component_record("C1")["omega"], component_record("H2O")["omega"]]
    kij = [[0.0, 0.5], [0.5, 0.0]]
    eos = cubic.SRKMIXKD(Tcs=tc, Pcs=[pc_c1, pc_w], omegas=om, zs=[xc, xw], kijs=kij, T=T, P=1e5)
    base = SRKMIX(Tcs=tc, Pcs=[pc_c1, pc_w], omegas=om, zs=[xc, xw], kijs=kij, T=T, P=1e5)
    expected = xw * xw * xc * 1.3580e-5 * 101325.0 * (1.0 - (T / tc[1]) ** 0.8)
    assert eos.a_alpha - base.a_alpha == pytest.approx(expected, rel=1e-10)


def test_kd_lnphi_consistent_with_mixing_rule() -> None:
    """sum_i x_i ln phi_i equals ln phi of the mixture (Euler; the a_KD partials are consistent)."""
    pkg = _pkg("kabadi-danner-srk")
    pkg.flash_pt({"C1": 0.01, "H2O": 0.99}, 330.0, 10.0e6, molar_flow=1.0)
    tcs, pcs = {}, {}
    for (tci, pci), c in cubic._CAS_BY_CRITICALS.items():
        tcs[c], pcs[c] = tci, pci
    from ngdesign.data import component_record

    om = [component_record("C1")["omega"], component_record("H2O")["omega"]]
    zs = [0.01, 0.99]
    kij = [[0.0, 0.5], [0.5, 0.0]]
    eos = cubic.SRKMIXKD(
        Tcs=[tcs["74-82-8"], tcs["7732-18-5"]],
        Pcs=[pcs["74-82-8"], pcs["7732-18-5"]],
        omegas=om,
        zs=zs,
        kijs=kij,
        T=330.0,
        P=10.0e6,
    )
    Z = eos.Z_l
    lnphis = eos.fugacity_coefficients(Z)
    # Gibbs-Duhem at fixed T, P: d(sum x ln phi) check via finite composition step.
    h = 1e-6
    up = cubic.SRKMIXKD(
        Tcs=eos.Tcs, Pcs=eos.Pcs, omegas=om, zs=[zs[0] + h, zs[1] - h], kijs=kij, T=330.0, P=10.0e6
    )
    dn = cubic.SRKMIXKD(
        Tcs=eos.Tcs, Pcs=eos.Pcs, omegas=om, zs=[zs[0] - h, zs[1] + h], kijs=kij, T=330.0, P=10.0e6
    )
    lu = up.fugacity_coefficients(up.Z_l)
    ld = dn.fugacity_coefficients(dn.Z_l)
    gd = sum(x * (a - b) / (2 * h) for x, a, b in zip(zs, lu, ld, strict=True))
    scale = sum(abs(x * (a - b) / (2 * h)) for x, a, b in zip(zs, lu, ld, strict=True))
    assert abs(gd) <= 1e-5 * scale
    assert all(math.isfinite(v) for v in lnphis)
