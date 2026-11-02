"""The depletion refusal: real exhaustion refuses, integration noise does not."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors._shared import reaction_set_param
from ngdesign.units.reactors.batch_reactor import BatchReactor, BatchReactorError
from ngdesign.units.reactors.pfr import PfrR1
from ngdesign.units.reactors.plug_flow import PlugFlowError, project_extents


def _case(k0: float, order: float, volume: float) -> tuple[Any, dict[str, Any]]:
    feeds, params = PfrR1.example_case()
    rs = params["reaction_set"]
    orders = {"nC4": order} if order else {}
    kin = {**rs["reactions"][0]["kinetics"], "k0": k0, "Ea": 0.0, "orders": orders}
    rset = {**rs, "reactions": [{**rs["reactions"][0], "kinetics": kin}]}
    return feeds, {**params, "reaction_set": rset, "volume_m3": volume}


def _inlet(thermo: Thermo, feeds: dict[str, Any]) -> Any:
    f = feeds["inlet"]
    return thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])


def test_first_order_runs_to_completion_at_da_60(thermo: Thermo) -> None:
    """exp(-60) of the feed is far below any tolerance; a first-order rate cannot exhaust
    its reactant, so this completes where the old event refused it near exp(-18)."""
    c = 2.0e5 / (8.31446261815324 * 500.0)
    feeds, params = _case(1.0, 1.0, 60.0 / c)
    out = PfrR1().solve({"inlet": _inlet(thermo, feeds)}, params, thermo).outlets["outlet"]
    flows = out.component_flows()
    assert flows["iC4"] == pytest.approx(1.0, rel=1e-7)
    assert flows.get("nC4", 0.0) >= 0.0
    assert flows.get("nC4", 0.0) < 1.0e-7


def test_zero_order_exhaustion_still_refuses(thermo: Thermo) -> None:
    """A rate that does not fall with its reactant passes the band and is refused."""
    feeds, params = _case(1.0, 0.0, 2.0)
    with pytest.raises(PlugFlowError, match="depletes component 'nC4'"):
        PfrR1().solve({"inlet": _inlet(thermo, feeds)}, params, thermo)


def test_batch_shares_the_rule(thermo: Thermo) -> None:
    params = dict(BatchReactor.example_case()[1])
    rs = params["reaction_set"]
    inlet = thermo.flash_pt({"nC4": 1.0}, 500.0, 2.0e5, 1.0)

    def with_kinetics(k0: float, orders: dict[str, float]) -> dict[str, Any]:
        kin = {**rs["reactions"][0]["kinetics"], "k0": k0, "Ea": 0.0, "orders": orders}
        return {**rs, "reactions": [{**rs["reactions"][0], "kinetics": kin}]}

    params.update(reaction_set=with_kinetics(1.0, {"nC4": 1.0}), batch_time_s=60.0, turnaround_s=0.0)
    res = BatchReactor().solve({"charge_in": inlet}, params, thermo)
    assert res.info["conversion_nC4_isom"] == pytest.approx(1.0 - math.exp(-60.0), rel=1e-7)
    params["reaction_set"] = with_kinetics(1.0, {})
    with pytest.raises(BatchReactorError, match="depletes component 'nC4'"):
        BatchReactor().solve({"charge_in": inlet}, params, thermo)


def test_project_extents_is_stoichiometric() -> None:
    """A -1e-10 flow is taken off the consuming extent and nothing else moves."""
    rset = reaction_set_param(PfrR1.example_case()[1]["reaction_set"])
    assert project_extents(rset, {"nC4": 1.0}, [0.5]) == [0.5]
    out = project_extents(rset, {"nC4": 1.0}, [1.0 + 1.0e-10])
    assert 1.0 - out[0] >= 0.0
    assert out[0] == pytest.approx(1.0, rel=1e-11)
