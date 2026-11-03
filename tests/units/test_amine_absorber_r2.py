"""Amine absorbers R2 (MDEA/MEA/DEA): countercurrent MESH absorbers on the reactive amine package.

Independent oracles, none read from the solver's own gate:
- component closure over the boundary streams;
- a stage audit from the reported profile: every stage's component balance,
  and a re-flash of each stage's L + V contents on the package, which must
  hand back the reported vapour (stage_audit.py);
- the column is adiabatic: its own closure is below 1 W, the reported duty is
  only the inlets' basis shift onto the package;
- physics: acid gas leaves the gas, the solvent loads, and the absorption
  heat warms the column above both inlets.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.amine_absorber_r2 import (
    AmineAbsorberR2Error,
    DeaAbsorberR2,
    MdeaAbsorberR2,
    MeaAbsorberR2,
)
from tests.conftest import flash_feed
from tests.units.column.stage_audit import equilibrium_residuals, material_residuals, read_stages

CLASSES = [MdeaAbsorberR2, MeaAbsorberR2, DeaAbsorberR2]


def _inlets(cls: type[MdeaAbsorberR2], thermo: Thermo) -> dict[str, StreamState]:
    feeds, _ = cls.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


@pytest.fixture(name="solved", scope="module", params=CLASSES, ids=lambda c: c.AMINE)
def solved_fixture(
    request: pytest.FixtureRequest,
) -> tuple[type[MdeaAbsorberR2], dict[str, StreamState], UnitResult]:
    cls = request.param
    thermo: Thermo = registry.create("thermo", "pr")
    inlets = _inlets(cls, thermo)
    _, params = cls.example_case()
    return cls, inlets, cls().solve(inlets, params, thermo)


def test_components_close(solved: Any) -> None:
    _, inlets, res = solved
    comps = set().union(*(s.composition for s in inlets.values()))
    total = sum(s.molar_flow for s in inlets.values())
    for cid in comps:
        n_in = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in inlets.values())
        n_out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in res.outlets.values())
        assert abs(n_out - n_in) < 1e-9 * total, cid


def test_stage_audit(solved: Any) -> None:
    """Reported-profile stage balances and a package re-flash of every stage's contents."""
    _, inlets, res = solved
    package = registry.create("thermo", "amine_ke")
    gas, lean = inlets["gas_in"], inlets["lean_amine_in"]
    comps = sorted(set(gas.composition) | set(lean.composition))
    n = int(res.info["n_stages"])
    gas_feed = package.flash_pt(dict(gas.composition), gas.T, gas.P, gas.molar_flow)
    lean_feed = package.flash_pt(dict(lean.composition), lean.T, gas.P, lean.molar_flow)
    stages = read_stages(res.info, comps)
    assert max(material_residuals(stages, comps, {0: [lean_feed], n - 1: [gas_feed]})) < 1e-9
    assert max(equilibrium_residuals(package, stages)) < 1e-6


def test_adiabatic_column(solved: Any) -> None:
    _, inlets, res = solved
    h_in = sum(s.molar_flow * s.enthalpy for s in inlets.values())
    h_out = sum(s.molar_flow * s.enthalpy for s in res.outlets.values())
    assert res.duty_W == pytest.approx(h_out - h_in, rel=1e-12)
    assert abs(res.info["column_closure_W"]) < 1.0
    assert res.info["basis_shift_W"] + res.info["column_closure_W"] == pytest.approx(res.duty_W, abs=1e-3)


def test_absorption_physics(solved: Any) -> None:
    cls, inlets, res = solved
    gas, lean = inlets["gas_in"], inlets["lean_amine_in"]
    sweet, rich = res.outlets["gas_out"], res.outlets["rich_amine_out"]
    for acid in ("CO2", "H2S"):
        assert sweet.composition.get(acid, 0.0) < 0.1 * gas.composition[acid]
        lean_loading = lean.composition.get(acid, 0.0) / lean.composition[cls.AMINE]
        assert res.info[f"rich_{acid.lower()}_loading"] > lean_loading
    assert sweet.vapor_fraction == pytest.approx(1.0)
    # The absorption heat leaves with the rich solvent: the bottom of the
    # column runs above both feeds, within the column's band (feed T + 80 K).
    assert rich.T > max(gas.T, lean.T)
    assert res.info["max_stage_T_K"] < max(gas.T, lean.T) + 80.0


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({"reflux": 1.0}, "unknown parameter"),
        ({"n_stages": 1}, "n_stages"),
        ({"n_stages": 2.5}, "n_stages"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    with pytest.raises(AmineAbsorberR2Error, match=match):
        MdeaAbsorberR2().solve(_inlets(MdeaAbsorberR2, thermo), params, thermo)


def test_refuses_other_amine(thermo: Thermo) -> None:
    with pytest.raises(AmineAbsorberR2Error, match="carries no MEA"):
        MeaAbsorberR2().solve(_inlets(MdeaAbsorberR2, thermo), {}, thermo)
