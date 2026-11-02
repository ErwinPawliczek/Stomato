"""Side stripper section R2: stage audit and cross-level check against R0 Kremser."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining.side_strip_r2 import SideStripR2, SideStripR2Error
from tests.conftest import flash_feed
from tests.units.column.stage_audit import (
    energy_residuals,
    equilibrium_residuals,
    material_residuals,
    read_stages,
)

COMPS = ["H2O", "nC10", "nC12", "nC8"]


def _inlets(thermo: Thermo, steam: float = 2.0) -> dict[str, Any]:
    feeds, _ = SideStripR2.example_case()
    feeds["steam_in"]["molar_flow"] = steam
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def test_stage_audit(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    res = SideStripR2().solve(inlets, {"n_stages": 4}, thermo)
    stages = read_stages(res.info, COMPS)
    feeds = {0: [inlets["draw_in"]], 3: [inlets["steam_in"]]}
    assert max(material_residuals(stages, COMPS, feeds)) < 1e-5
    assert max(energy_residuals(thermo, stages, feeds)) < 2e-3
    assert max(equilibrium_residuals(thermo, stages)) < 1e-3


def test_section_cools_downward_and_strips_the_light_end(thermo: Thermo) -> None:
    """The flash of light ends cools the liquid: R0's single T cannot show this."""
    inlets = _inlets(thermo)
    res = SideStripR2().solve(inlets, {"n_stages": 4}, thermo)
    temps = [res.info[f"stage_{j}_T_K"] for j in range(4)]
    assert temps == sorted(temps, reverse=True)
    assert res.outlets["bottoms_out"].composition["nC8"] < 0.2
    assert res.outlets["overhead_out"].composition["nC8"] > 0.2


def test_more_steam_strips_more(thermo: Thermo) -> None:
    low = SideStripR2().solve(_inlets(thermo, 1.0), {"n_stages": 4}, thermo)
    high = SideStripR2().solve(_inlets(thermo, 2.0), {"n_stages": 4}, thermo)
    assert high.info["stripped_frac"] > low.info["stripped_frac"]


def test_v2_against_r0_kremser(thermo: Thermo) -> None:
    """R0 at the R2 section's mean temperature lands on the same stripped fraction."""
    inlets = _inlets(thermo)
    res = SideStripR2().solve(inlets, {"n_stages": 4}, thermo)
    mean_t = sum(res.info[f"stage_{j}_T_K"] for j in range(4)) / 4.0
    r0 = registry.create("unit", "side_strip").solve(
        inlets, {"model": "R0", "T": mean_t, "N": 4.0, "P": 2.0e5}, thermo
    )
    assert r0.info["stripped_frac"] == pytest.approx(res.info["stripped_frac"], rel=0.25)


def test_refusals(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    for params in ({}, {"n_stages": 1}, {"n_stages": 4, "x": 1}):
        with pytest.raises(SideStripR2Error):
            SideStripR2().solve(inlets, params, thermo)
    with pytest.raises(SideStripR2Error):
        SideStripR2().solve({"draw_in": inlets["draw_in"]}, {"n_stages": 4}, thermo)
