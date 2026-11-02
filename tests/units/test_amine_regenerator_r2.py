"""MDEA regenerator R2: a reboiled MESH stripper on the reactive amine package.

Independent oracles, none read from the solver's own gate:
- component closure over the boundary streams;
- a stage audit from the reported profile: every stage's component balance,
  and a re-flash of each stage's L + V contents on the package, which must
  hand back the reported vapour (stage_audit.py);
- physics: lean loadings below the rich ones, and more boilup strips more.
Measured wall times: 2-6 s per solve.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.amine_regenerator_r2 import (
    DEFAULT_FEED_T,
    DEFAULT_REGENERATOR_P,
    AmineRegeneratorR2Error,
    MdeaRegeneratorR2,
)
from tests.conftest import flash_feed
from tests.units.column.stage_audit import equilibrium_residuals, material_residuals, read_stages


def _solve(thermo: Thermo, **overrides: Any) -> tuple[StreamState, UnitResult]:
    feeds, params = MdeaRegeneratorR2.example_case()
    rich = flash_feed(thermo, feeds["rich_amine_in"])
    return rich, MdeaRegeneratorR2().solve({"rich_amine_in": rich}, {**params, **overrides}, thermo)


@pytest.fixture(name="solved", scope="module")
def solved_fixture() -> tuple[Thermo, StreamState, UnitResult]:
    thermo: Thermo = registry.create("thermo", "pr")
    return (thermo, *_solve(thermo))


def test_components_close(solved: Any) -> None:
    _, rich, res = solved
    for cid, z in rich.composition.items():
        out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in res.outlets.values())
        assert out == pytest.approx(rich.molar_flow * z, rel=1e-9), cid


def test_stage_audit(solved: Any) -> None:
    """Measured: material 8.6e-13, equilibrium 1.2e-5 (bounds sit at the reactive 1e-3 stage gate)."""
    _, rich, res = solved
    package = registry.create("thermo", "amine_ke")
    comps = sorted(rich.composition)
    feed = package.flash_pt(dict(rich.composition), DEFAULT_FEED_T, DEFAULT_REGENERATOR_P, rich.molar_flow)
    stages = read_stages(res.info, comps)
    assert max(material_residuals(stages, comps, {0: [feed]})) < 1e-9
    assert max(equilibrium_residuals(package, stages)) < 1e-3


def test_stripping_physics(solved: Any) -> None:
    thermo, _, res = solved
    info = res.info
    assert info["lean_co2_loading"] < 0.1 * info["rich_co2_loading"]
    assert info["lean_h2s_loading"] < 0.2 * info["rich_h2s_loading"]
    assert res.outlets["acid_gas_out"].vapor_fraction == pytest.approx(1.0)
    assert info["reboiler_T_K"] > res.outlets["acid_gas_out"].T
    _, more = _solve(thermo, boilup_rate=30.0)
    assert more.info["lean_co2_loading"] < info["lean_co2_loading"]
    assert more.info["lean_h2s_loading"] < info["lean_h2s_loading"]
    assert more.info["reboiler_duty_W"] > info["reboiler_duty_W"]


def test_energy_split(solved: Any) -> None:
    _, rich, res = solved
    h_in = rich.molar_flow * rich.enthalpy
    h_out = sum(s.molar_flow * s.enthalpy for s in res.outlets.values())
    assert res.duty_W == pytest.approx(h_out - h_in, rel=1e-12)
    assert res.info["preheat_duty_W"] > 0.0 and res.info["reboiler_duty_W"] > 0.0
    assert res.info["preheat_duty_W"] + res.info["reboiler_duty_W"] == pytest.approx(res.duty_W, rel=1e-6)


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({"boilup_rate": 20.0, "reflux": 1.0}, "unknown parameter"),
        ({"boilup_rate": 20.0, "n_stages": 1}, "n_stages"),
        ({}, "boilup_rate"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    feeds, _ = MdeaRegeneratorR2.example_case()
    rich = flash_feed(thermo, feeds["rich_amine_in"])
    with pytest.raises(AmineRegeneratorR2Error, match=match):
        MdeaRegeneratorR2().solve({"rich_amine_in": rich}, params, thermo)
