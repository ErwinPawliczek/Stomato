"""Membrane R2 tests: counter-current (M4) against the spec oracles CF3/CF4.

Common inputs and expected values from `specs/backend/units/membrane.md`:
binary O2/N2, z = (0.209, 0.791), F = 1 mol/s, P_h = 1e6 Pa,
Π_O2 = 5e-9, Π_N2 = 5e-10 (α = 10). Reference: CF3 (R2, P_l = 1e5, A = 100)
and CF4 (R2 = R1 at P_l = 0, A = 100), rtol 1e-7.
"""

from __future__ import annotations

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.membrane_r1 import MembraneR1, MembraneR1SpecError, cross_flow
from ngdesign.units.separation.membrane_r2 import MembraneR2, counter_current
from tests.conftest import flash_feed

Z = {"O2": 0.209, "N2": 0.791}
PI = {"O2": 5e-9, "N2": 5e-10}
P_H = 1e6
F = 1.0


def test_cf3_counter_current_at_pl_1e5() -> None:
    """CF3: R2 at P_l = 1e5, A = 100 — counter-current beats cross-flow (CF2)."""
    residue, permeate, area, theta, nfev = counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=100.0)
    assert area == pytest.approx(100.0)
    assert theta == pytest.approx(0.101547682, rel=1e-7)
    n_res = sum(residue.values())
    n_perm = sum(permeate.values())
    assert residue["O2"] / n_res == pytest.approx(0.162690039, rel=1e-7)
    assert permeate["O2"] / n_perm == pytest.approx(0.61873158, rel=1e-7)
    assert nfev > 0
    # Counter-current beats cross-flow at the same area (CF2: θ = 0.100888989).
    _, _, _, theta_r1 = cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=100.0)
    assert theta > theta_r1


def test_cf4_r2_equals_r1_at_pl_zero() -> None:
    """CF4: at P_l = 0 the permeate side has no effect — R2 equals R1."""
    residue_r2, permeate_r2, _, theta_r2, _ = counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=0.0, area=100.0)
    residue_r1, permeate_r1, _, theta_r1 = cross_flow(F=F, z=Z, Pi=PI, P_h=P_H, P_l=0.0, area=100.0)
    assert theta_r2 == pytest.approx(0.128104867, rel=1e-7)
    assert theta_r1 == pytest.approx(0.128104867, rel=1e-7)
    n_res2, n_perm2 = sum(residue_r2.values()), sum(permeate_r2.values())
    assert residue_r2["O2"] / n_res2 == pytest.approx(0.140173754, rel=1e-7)
    assert permeate_r2["O2"] / n_perm2 == pytest.approx(0.67743863, rel=1e-7)
    for c in Z:
        assert residue_r2[c] == pytest.approx(residue_r1[c], rel=1e-8)
        assert permeate_r2[c] == pytest.approx(permeate_r1[c], rel=1e-8)


def test_counter_current_stage_cut_mode() -> None:
    """Design mode: brentq on θ_R2(A) − θ finds the area that hits the cut."""
    residue, permeate, area, theta, _ = counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, stage_cut=0.1)
    assert theta == pytest.approx(0.1, rel=1e-6)
    assert area > 0.0
    # The area matches the rating-mode solution at that area's stage cut.
    _, _, _, theta_at, _ = counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, area=area)
    assert theta_at == pytest.approx(0.1, rel=1e-6)
    assert sum(residue.values()) + sum(permeate.values()) == pytest.approx(F, rel=1e-12)


def test_counter_current_validation_refusals() -> None:
    """The R1 refusal table applies to R2 (shared validation)."""
    with pytest.raises(MembraneR1SpecError, match="permeances_mol_m2_s_Pa"):
        counter_current(F=F, z=Z, Pi={"O2": 5e-9}, P_h=P_H, P_l=1e5, area=100.0)
    with pytest.raises(MembraneR1SpecError, match="P_permeate"):
        counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=2e6, area=100.0)
    with pytest.raises(MembraneR1SpecError, match="area_m2"):
        counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5)
    with pytest.raises(MembraneR1SpecError, match="stage_cut"):
        counter_current(F=F, z=Z, Pi=PI, P_h=P_H, P_l=1e5, stage_cut=1.0)


def _air_feed(thermo: Thermo) -> StreamState:
    """The R0 example feed: Geankoplis Ex. 13.4-2 air basis (100 mol/s)."""
    return flash_feed(
        thermo,
        {"T": 298.15, "P": 2.533125e5, "molar_flow": 100.0, "composition": {"O2": 0.209, "N2": 0.791}},
    )


def test_adapter_r2_equals_r1_equal_permeances(thermo: Thermo) -> None:
    """R2 -> R1: equal permeances make the local permeate y_i = x_i, so the
    counter-current module equals the cross-flow module at the same area."""
    inlet = _air_feed(thermo)
    params = {
        "permeances_mol_m2_s_Pa": {"O2": 1e-9, "N2": 1e-9},
        "P_permeate": 2.533125e4,
        "area_m2": 50.0,
    }
    r2 = MembraneR2().solve({"feed_in": inlet}, params, thermo)
    r1 = MembraneR1().solve({"feed_in": inlet}, params, thermo)
    for port in ("permeate", "residue"):
        a, b = r2.outlets[port], r1.outlets[port]
        assert a.P == pytest.approx(b.P)
        assert a.T == pytest.approx(b.T)
        assert a.molar_flow == pytest.approx(b.molar_flow, rel=1e-8)
        for cid in ("O2", "N2"):
            assert a.molar_flow * a.composition[cid] == pytest.approx(
                b.molar_flow * b.composition[cid], rel=1e-8
            )


def test_adapter_r2_beats_r1_selective(thermo: Thermo) -> None:
    """Unit-level: the counter-current module enriches more than cross-flow at
    the same area (CF3 vs CF2 at adapter scale). Balances: moles 1e-12,
    energy 1e-8 (U-R2 rule); info carries shooting_nfev."""
    inlet = _air_feed(thermo)
    params = {
        "permeances_mol_m2_s_Pa": {"O2": 1e-8, "N2": 1e-9},
        "P_permeate": 2.533125e4,
        "area_m2": 200.0,
    }
    r2 = MembraneR2().solve({"feed_in": inlet}, params, thermo)
    r1 = MembraneR1().solve({"feed_in": inlet}, params, thermo)
    assert r2.info["permeate_y_O2"] > r1.info["permeate_y_O2"]
    assert r2.info["shooting_nfev"] > 0
    n_in = inlet.molar_flow
    n_out = sum(s.molar_flow for s in r2.outlets.values())
    assert n_out == pytest.approx(n_in, rel=1e-12)
    h_in = inlet.enthalpy * inlet.molar_flow
    h_out = sum(s.enthalpy * s.molar_flow for s in r2.outlets.values())
    assert r2.duty_W == pytest.approx(h_out - h_in, rel=1e-8)
    assert r2.power_W == 0.0


def test_adapter_r2_stage_cut_design_mode(thermo: Thermo) -> None:
    """Design mode through the adapter: brentq finds the area for theta = 0.1."""
    inlet = _air_feed(thermo)
    result = MembraneR2().solve(
        {"feed_in": inlet},
        {
            "permeances_mol_m2_s_Pa": {"O2": 1e-8, "N2": 1e-9},
            "P_permeate": 2.533125e4,
            "stage_cut": 0.1,
        },
        thermo,
    )
    assert result.info["stage_cut"] == pytest.approx(0.1, rel=1e-6)
    assert result.info["area_m2"] > 0.0
    n_out = sum(s.molar_flow for s in result.outlets.values())
    assert n_out == pytest.approx(inlet.molar_flow, rel=1e-12)


def test_adapter_r2_refuses_bad_params(thermo: Thermo) -> None:
    """The shared adapter refusals apply to R2."""
    inlet = _air_feed(thermo)
    base = {"permeances_mol_m2_s_Pa": {"O2": 1e-8, "N2": 1e-9}}
    with pytest.raises(MembraneR1SpecError, match="P_permeate"):
        MembraneR2().solve({"feed_in": inlet}, {**base, "P_permeate": 0.0, "area_m2": 50.0}, thermo)
    with pytest.raises(MembraneR1SpecError, match="exactly one"):
        MembraneR2().solve({"feed_in": inlet}, {**base, "P_permeate": 2.533125e4}, thermo)
    with pytest.raises(MembraneR1SpecError, match="permeances_mol_m2_s_Pa"):
        MembraneR2().solve({"feed_in": inlet}, {"P_permeate": 2.533125e4, "area_m2": 50.0}, thermo)
