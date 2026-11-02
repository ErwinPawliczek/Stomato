# mypy: disable-error-code="no-untyped-call"
"""Free-water rows: the water-rich phase follows IAPWS-95, the hydrocarbon phases do not move.

Anchors: Psat(H2O, 350 K) = 41.682 kPa and rho_L(300 K, 0.1 MPa) = 996.56 kg/m3, IAPWS-95
through ``chemicals.iapws``, the same equation the row implements, and the 298.15 K
values of the Wagner & Pruss (2002) tables, h_L - h_V = -43.99 kJ/mol.
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from chemicals.iapws import iapws95_Psat

from ngdesign import registry
from ngdesign.thermo.free_water import pure_water_offset, steam_table_residuals

FEED = {"C1": 0.5, "nC5": 0.3, "H2O": 0.2}


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


@pytest.mark.parametrize(
    ("base", "row"), [("pr", "pr-free-water"), ("kabadi-danner-srk", "kabadi-danner-free-water")]
)
def test_aqueous_density_is_the_steam_table(base: str, row: str) -> None:
    """SRK and PR put liquid water at 850-870 kg/m3; the row reports IAPWS-95 water."""
    state = _pkg(row).flash_pt(FEED, 300.0, 2e6, 1.0)
    aqueous = next(p for p in state.phases if p.kind.value == "aqueous")
    assert aqueous.density == pytest.approx(997.4, rel=0.002)
    base_state = _pkg(base).flash_pt(FEED, 300.0, 2e6, 1.0)
    assert next(p for p in base_state.phases if p.kind.value == "aqueous").density < 900.0


@pytest.mark.parametrize("row", ["pr-free-water", "kabadi-danner-free-water"])
def test_water_in_the_gas_over_free_water_follows_the_steam_table_psat(row: str) -> None:
    """y_w P phi_V = x_w f0_w: the row's K_w tracks Psat, the EOS's own does not."""
    T, P = 350.0, 1e6
    z = {"N2": 0.8, "H2O": 0.2}
    state = _pkg(row).flash_pt(z, T, P, 1.0)
    vapour = state.phases[0]
    aqueous = next(p for p in state.phases if p.kind.value == "aqueous")
    f_liquid = aqueous.composition["H2O"] * P * math.exp(aqueous.ln_phi["H2O"])
    psat = iapws95_Psat(T)
    assert f_liquid == pytest.approx(psat, rel=0.02)
    assert vapour.composition["H2O"] == pytest.approx(psat / P, rel=0.06)


def test_row_moves_the_water_fugacity_towards_the_steam_table() -> None:
    T, P = 400.0, 3e6
    z = {"N2": 0.8, "H2O": 0.2}
    ref = P * math.exp(steam_table_residuals(T, P)[0])

    def fugacity(row: str) -> float:
        phase = next(p for p in _pkg(row).flash_pt(z, T, P, 1.0).phases if p.kind.value == "aqueous")
        return float(phase.composition["H2O"] * P * math.exp(phase.ln_phi["H2O"]))

    assert fugacity("pr-free-water") == pytest.approx(ref, rel=2e-3)
    assert abs(fugacity("pr-free-water") - ref) < abs(fugacity("pr") - ref)


def test_dry_hydrocarbon_flash_is_the_base_row_exactly() -> None:
    z = {"C1": 0.6, "C3": 0.4}
    a = _pkg("pr").flash_pt(z, 250.0, 2e6, 1.0)
    b = _pkg("pr-free-water").flash_pt(z, 250.0, 2e6, 1.0)
    assert b.enthalpy == a.enthalpy
    assert b.phases[0].composition == a.phases[0].composition


def test_latent_heat_of_pure_water_matches_the_steam_table() -> None:
    """H_V - H_L on the row: EOS vapour departure, IAPWS-95 liquid; 43.99 kJ/mol at 298.15 K."""
    from ngdesign.contracts.stream import PhaseKind

    z = {"H2O": 1.0}
    T = 298.15
    p = iapws95_Psat(T)
    pkg = _pkg("pr-free-water")
    d_h = (
        pkg.phase_props(z, T, p, PhaseKind.VAPOR).enthalpy
        - pkg.phase_props(z, T, p * 1.01, PhaseKind.AQUEOUS).enthalpy
    )
    assert d_h == pytest.approx(43990.0, rel=0.01)


def test_steam_table_residuals_are_molar() -> None:
    ln_phi, h_res, _, volume = steam_table_residuals(300.0, 1e5)
    assert volume == pytest.approx(0.018015268 / 996.56, rel=1e-3)
    assert h_res < -40000.0  # about one latent heat below the ideal gas
    assert ln_phi < 0.0


def test_metastable_liquid_below_psat_is_evaluated_at_psat() -> None:
    psat = iapws95_Psat(300.0)
    at_sat = steam_table_residuals(300.0, psat * 1.000001)
    below = steam_table_residuals(300.0, psat * 0.5)
    assert below[3] == pytest.approx(at_sat[3], rel=1e-5)
    assert below[0] - at_sat[0] == pytest.approx(0.6931, abs=1e-3)


def test_no_eos_liquid_root_gives_no_offset_above_the_critical_point() -> None:
    assert pure_water_offset("PR", 647.1, 22.064e6, 0.344, 700.0, 1e4) is None
