"""Reactive stages R2: hand-evaluated rates, reductions and the equilibrium limit.

Oracles independent of the solver and of ``kinetics.rate``:
- each stage's generation is recomputed by hand from the Fogler Example 11-3
  closed forms at the REPORTED T and x;
- zero holdup reduces to the plain column;
- at large holdup every reactive stage sits on x_iC4/x_nC4 = K_C(T), the van 't
  Hoff line of the same example.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.data.formation import formation_enthalpy_298
from ngdesign.units.column.spec import ColumnSpecError
from ngdesign.units.column_shortcut.reactive_stages import ReactiveStages, ReactiveStagesError
from tests.conftest import flash_feed
from tests.units.column.stage_audit import energy_residuals, material_residuals, read_stages

COMPS = ["iC4", "nC4"]
R = 8.31446261815324


def _k_f(t: float) -> float:
    return 31.1 / 3600.0 * math.exp(-65700.0 / R * (1.0 / t - 1.0 / 360.0))


def _k_c(t: float) -> float:
    return 3.03 * math.exp(6900.0 / R * (1.0 / t - 1.0 / 333.0))


def _rate(t: float, x_n: float, x_i: float) -> float:
    return 9300.0 / 0.9 * _k_f(t) * (x_n - x_i / _k_c(t))


def _solve(thermo: Thermo, **over: Any) -> tuple[Any, Any]:
    feeds, params = ReactiveStages.example_case()
    feed = flash_feed(thermo, feeds["feed"])
    return feed, ReactiveStages().solve({"feed": feed}, {**params, **over}, thermo)


def test_stage_audit_with_hand_rates(thermo: Thermo) -> None:
    feed, res = _solve(thermo)
    stages = read_stages(res.info, COMPS)
    source: list[dict[str, float]] = []
    heat: dict[int, float] = {}
    dhf = {c: formation_enthalpy_298(c) for c in COMPS}
    for j, st in enumerate(stages):
        if j == 7:  # the kettle carries no holdup
            source.append({})
            continue
        xi = 0.05 * _rate(st.T, st.x["nC4"], st.x["iC4"])
        assert res.info[f"stage_{j}_generation_iC4"] == pytest.approx(xi, rel=1e-3)
        source.append({"iC4": xi, "nC4": -xi})
        heat[j] = -xi * (dhf["iC4"] - dhf["nC4"])
    assert max(material_residuals(stages, COMPS, {0: [feed]}, source=source)) < 1e-5
    assert max(energy_residuals(thermo, stages, {0: [feed]}, duties=heat, skip=frozenset({7}))) < 2e-3
    # Audit sensitivity: without the reaction the same profile does not close.
    assert max(material_residuals(stages, COMPS, {0: [feed]})) > 1e-3


def test_total_moles_and_formation_basis(thermo: Thermo) -> None:
    feed, res = _solve(thermo)
    d, b = res.outlets["distillate"], res.outlets["bottoms"]
    assert d.molar_flow + b.molar_flow == pytest.approx(100.0, rel=1e-9)  # A <-> B keeps moles
    made = sum(s.molar_flow * s.composition["iC4"] for s in (d, b)) - 10.0
    assert made > 1.0
    # An exothermic isomerization on the databank's formation enthalpies.
    assert res.info["reaction_heat_W"] == pytest.approx(
        -made * (formation_enthalpy_298("iC4") - formation_enthalpy_298("nC4")), rel=1e-3
    )


def test_vanishing_holdup_is_the_plain_column(thermo: Thermo) -> None:
    _, params = ReactiveStages.example_case()
    tiny = {str(s): 1e-12 for s in range(1, 8)}
    feed, res = _solve(thermo, reactive_holdup_m3=tiny)
    plain_params = {k: v for k, v in params.items() if k not in ("reaction_set", "reactive_holdup_m3")}
    plain = registry.create("unit", "column").solve({"feed": feed}, plain_params, thermo)
    for j in range(8):
        assert res.info[f"stage_{j}_T_K"] == pytest.approx(plain.info[f"stage_{j}_T_K"], abs=1e-3), j
        assert res.info[f"stage_{j}_x_iC4"] == pytest.approx(plain.info[f"stage_{j}_x_iC4"], rel=1e-3), j


@pytest.mark.timeout(300)
def test_large_holdup_reaches_reaction_equilibrium(thermo: Thermo) -> None:
    """Holdup >> F/k: every reactive stage's liquid is on K_C(T), the book's line."""
    _, res = _solve(thermo, reactive_holdup_m3={str(s): 30.0 for s in range(1, 8)})
    for j in range(1, 7):
        ratio = res.info[f"stage_{j}_x_iC4"] / res.info[f"stage_{j}_x_nC4"]
        assert ratio == pytest.approx(_k_c(res.info[f"stage_{j}_T_K"]), rel=0.03), j


def _set_with(**kinetics: Any) -> dict[str, Any]:
    rset = ReactiveStages.example_case()[1]["reaction_set"]
    rset["reactions"][0]["kinetics"].update(kinetics)
    return dict(rset)


def test_gas_concentration_basis_refused(thermo: Thermo) -> None:
    with pytest.raises(ColumnSpecError, match="ideal-gas concentration"):
        _solve(thermo, reaction_set=_set_with(basis="concentration"))


def test_equilibrium_limitation_without_reverse_refused(thermo: Thermo) -> None:
    rset = _set_with(reverse=None)
    rset["reactions"][0]["equilibrium"] = {"form": "from_gibbs"}
    with pytest.raises(ColumnSpecError, match="activity"):
        _solve(thermo, reaction_set=rset)


def test_holdup_on_the_kettle_refused(thermo: Thermo) -> None:
    with pytest.raises(ColumnSpecError, match="reboiler stage"):
        _solve(thermo, reactive_holdup_m3={"8": 0.05})


def test_missing_reaction_set_refused(thermo: Thermo) -> None:
    feeds, params = ReactiveStages.example_case()
    bare = {k: v for k, v in params.items() if k != "reaction_set"}
    with pytest.raises(ReactiveStagesError):
        ReactiveStages().solve({"feed": flash_feed(thermo, feeds["feed"])}, bare, thermo)
