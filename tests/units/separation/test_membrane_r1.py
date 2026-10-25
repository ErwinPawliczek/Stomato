"""Membrane R1 tests: cross-flow reference cases and the local-permeate check.

Reference numbers are the spec's printed values (`specs/backend/units/
membrane.md`, tests CF1/CF2), produced by the hand-written RK4/bisection
script `scratchpad/unit-specs/calc_membrane.py` (20,000 steps, no scipy and
no ngdesign). Common inputs: binary O2/N2, z = (0.209, 0.791), F = 1 mol/s,
P_h = 1e6 Pa, Π_O2 = 5e-9, Π_N2 = 5e-10 mol/(m2 s Pa) (alpha = 10).

Closed form (CF1, P_l = 0): the Rayleigh equation for a cross-flow module
with no permeate-side pressure — with alpha = Π_O2/Π_N2 = 10 the residue
satisfies ``n_O2/n_O2,0 = (n_N2/n_N2,0)^alpha`` (Geankoplis 4th ed. §13.5,
Rayleigh form), which the CF1 test checks independently of the integration.
"""

from __future__ import annotations

import pytest

from ngdesign.units.separation.membrane_r1 import (
    MembraneR1SpecError,
    cross_flow,
    local_permeate,
)

Z = {"O2": 0.209, "N2": 0.791}
PI = {"O2": 5e-9, "N2": 5e-10}
P_H = 1e6
F = 1.0


def _x_of(flows: dict[str, float]) -> dict[str, float]:
    total = sum(flows.values())
    return {c: v / total for c, v in flows.items()}


def test_cf1_stage_cut_rayleigh_closed_form() -> None:
    """CF1 (P_l = 0, stage cut 0.2): Rayleigh closed form and the spec values.

    Hand-computed basis: at P_l = 0 the flux is J_i = Π_i P_h x_i, so the
    feed-side balance dn_O2/dn_N2 = (Π_O2/Π_N2) n_O2/n_N2 integrates to the
    Rayleigh relation n_O2/0.209 = (n_N2/0.791)^10. Solving it with the
    stage-cut balance Σp = 0.2 F gives the residue x_O2 = 0.10094162 and the
    permeate y_O2 = 0.641233521; the area is A = 169.155932 m2.
    """
    residue, permeate, area, theta = cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=0.0, stage_cut=0.2)
    x = _x_of(residue)
    y = _x_of(permeate)
    n_O2_0, n_N2_0 = F * Z["O2"], F * Z["N2"]
    rayleigh = residue["O2"] / n_O2_0 - (residue["N2"] / n_N2_0) ** 10.0
    assert abs(rayleigh) < 1e-9  # Rayleigh closed form
    assert x["O2"] == pytest.approx(0.10094162, rel=1e-7)
    assert y["O2"] == pytest.approx(0.641233521, rel=1e-7)
    assert area == pytest.approx(169.155932, rel=1e-6)
    assert theta == pytest.approx(0.2, rel=1e-9)


def test_cf2_rating_mode() -> None:
    """CF2 (P_l = 1e5 Pa, A = 100 m2): spec values theta, y_O2, x_O2."""
    residue, permeate, area, theta = cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=100.0)
    assert area == pytest.approx(100.0)
    assert theta == pytest.approx(0.100888989, rel=1e-7)
    y = _x_of(permeate)
    x = _x_of(residue)
    assert y["O2"] == pytest.approx(0.615516887, rel=1e-7)
    assert x["O2"] == pytest.approx(0.163384857, rel=1e-7)


def test_cf2_molar_balance() -> None:
    """Residue + permeate flows reproduce the feed (moles closed to 1e-12)."""
    residue, permeate, _, _ = cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=100.0)
    for cid in Z:
        assert residue[cid] + permeate[cid] == pytest.approx(F * Z[cid], rel=1e-12)


def test_local_permeate_sum_and_flux_identity() -> None:
    """At P_l > 0: Σy = 1 to 1e-14 and S y_i = Π_i(P_h x_i − P_l y_i) to 1e-12."""
    x = {"O2": 0.3, "N2": 0.5, "CH4": 0.2}
    Pi = {"O2": 5e-9, "N2": 5e-10, "CH4": 2e-10}
    P_h, P_l = 1e6, 1e5
    y, S = local_permeate(x, Pi, P_h, P_l)
    assert sum(y.values()) == pytest.approx(1.0, abs=1e-14)
    for cid in x:
        flux = Pi[cid] * (P_h * x[cid] - P_l * y[cid])
        assert S * y[cid] == pytest.approx(flux, rel=1e-12, abs=1e-24)


def test_local_permeate_zero_pressure_closed_form() -> None:
    """At P_l = 0 the closed form y_i ∝ Π_i P_h x_i with S = Σ Π_i P_h x_i."""
    x = {"O2": 0.3, "N2": 0.5, "CH4": 0.2}
    Pi = {"O2": 5e-9, "N2": 5e-10, "CH4": 2e-10}
    y, S = local_permeate(x, Pi, 1e6, 0.0)
    assert S == pytest.approx(sum(Pi[c] * 1e6 * x[c] for c in x), rel=1e-15)
    for cid in x:
        assert y[cid] == pytest.approx(Pi[cid] * 1e6 * x[cid] / S, rel=1e-15)


def test_refuses_missing_permeance_component() -> None:
    with pytest.raises(MembraneR1SpecError, match="permeances_mol_m2_s_Pa"):
        cross_flow(F=F, z=Z, Pi={"O2": 5e-9}, P_h=P_H, P_l=1e5, area=100.0)


def test_refuses_extra_permeance_component() -> None:
    with pytest.raises(MembraneR1SpecError, match="permeances_mol_m2_s_Pa"):
        cross_flow(F=F, z=Z, Pi={**PI, "CH4": 1e-10}, P_h=P_H, P_l=1e5, area=100.0)


def test_refuses_nonpositive_permeance() -> None:
    with pytest.raises(MembraneR1SpecError, match="permeances_mol_m2_s_Pa"):
        cross_flow(F=F, z=Z, Pi={"O2": 0.0, "N2": 5e-10}, P_h=P_H, P_l=1e5, area=100.0)


def test_refuses_bad_P_permeate() -> None:
    with pytest.raises(MembraneR1SpecError, match="P_permeate"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=-1.0, area=100.0)
    with pytest.raises(MembraneR1SpecError, match="P_permeate"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=P_H, area=100.0)


def test_refuses_both_or_neither_area_and_stage_cut() -> None:
    with pytest.raises(MembraneR1SpecError, match="area_m2"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=100.0, stage_cut=0.2)
    with pytest.raises(MembraneR1SpecError, match="area_m2"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5)


def test_refuses_bad_area_and_stage_cut_values() -> None:
    with pytest.raises(MembraneR1SpecError, match="area_m2"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=-1.0)
    with pytest.raises(MembraneR1SpecError, match="stage_cut"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, stage_cut=0.0)
    with pytest.raises(MembraneR1SpecError, match="stage_cut"):
        cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, stage_cut=1.0)
