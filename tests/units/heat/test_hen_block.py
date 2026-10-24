"""Adapter tests: the HEN block (spec U-C 10)."""

from __future__ import annotations

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo

P = 1.01325e5


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _kemp_feeds(thermo: Thermo) -> dict[str, StreamState]:
    """Kemp four-stream basis: CP/cp_molar(N2) stand-in flows (mol/s)."""
    return {
        "hot_in_1": thermo.flash_pt({"N2": 1.0}, 443.15, P, 101.01),
        "hot_in_2": thermo.flash_pt({"N2": 1.0}, 423.15, P, 50.505),
        "cold_in_1": thermo.flash_pt({"N2": 1.0}, 293.15, P, 67.34),
        "cold_in_2": thermo.flash_pt({"N2": 1.0}, 353.15, P, 134.68),
    }


def _kemp_params() -> dict[str, float]:
    return {
        "T_out_hot_in_1": 333.15,
        "T_out_hot_in_2": 303.15,
        "T_out_cold_in_1": 408.15,
        "T_out_cold_in_2": 413.15,
        "dT_min": 10.0,
    }


def test_kemp_targets() -> None:
    """QHmin about 20 kW, QCmin about 60 kW, pinch 90/80 C (dTmin 10 K).

    The stand-in flows carry the package cp curve, so the targets sit within
    a few percent of Kemp's constant-cp hand values (measured 19,495 / 59,221 W).
    """
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    result = unit.solve(_kemp_feeds(thermo), _kemp_params(), thermo)
    assert result.info["QH_min_W"] == pytest.approx(20000.0, rel=0.05)
    assert result.info["QC_min_W"] == pytest.approx(60000.0, rel=0.05)
    assert result.info["pinch_T_hot_K"] == pytest.approx(363.15, abs=0.5)
    assert result.info["pinch_T_cold_K"] == pytest.approx(353.15, abs=0.5)
    assert result.info["dT_min_K"] == 10.0
    # Cascade arithmetic: QHmin + QCmin = (total hot - total cold) deficit.
    assert result.info["QH_min_W"] + result.info["QC_min_W"] == pytest.approx(80000.0, rel=0.05)


def test_all_active_streams_reach_their_targets() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    result = unit.solve(_kemp_feeds(thermo), _kemp_params(), thermo)
    params = _kemp_params()
    assert result.outlets["hot_out_1"].T == pytest.approx(params["T_out_hot_in_1"], abs=0.05)
    assert result.outlets["hot_out_2"].T == pytest.approx(params["T_out_hot_in_2"], abs=0.05)
    assert result.outlets["cold_out_1"].T == pytest.approx(params["T_out_cold_in_1"], abs=0.05)
    assert result.outlets["cold_out_2"].T == pytest.approx(params["T_out_cold_in_2"], abs=0.05)
    # Positional pairing: the outlet for hot_in_1 is hot_out_1.
    assert result.outlets["hot_out_1"].molar_flow == pytest.approx(101.01, rel=1e-9)


def test_zero_flow_ports_pass_through() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    feeds = _kemp_feeds(thermo)
    feeds["hot_in_2"] = thermo.flash_pt({"N2": 1.0}, 423.15, P, 0.0)
    params = _kemp_params()
    del params["T_out_hot_in_2"]  # a zero-flow port needs no target
    result = unit.solve(feeds, params, thermo)
    assert result.outlets["hot_out_2"].molar_flow == 0.0
    assert result.outlets["hot_out_2"].T == pytest.approx(423.15, abs=1e-9)
    assert result.info["QH_min_W"] > 0.0


def test_missing_target_refused() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    params = _kemp_params()
    del params["T_out_cold_in_1"]
    with pytest.raises(ValueError, match="has no T_out_cold_in_1 target"):
        unit.solve(_kemp_feeds(thermo), params, thermo)


def test_backward_targets_refused() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    params = _kemp_params()
    params["T_out_hot_in_1"] = 453.15  # hot must cool
    with pytest.raises(ValueError, match="must be below"):
        unit.solve(_kemp_feeds(thermo), params, thermo)
    params = _kemp_params()
    params["T_out_cold_in_1"] = 283.15  # cold must heat
    with pytest.raises(ValueError, match="must be above"):
        unit.solve(_kemp_feeds(thermo), params, thermo)


def test_dTmin_guard() -> None:
    thermo = _thermo()
    unit = registry.create("unit", "hen_block")
    params = _kemp_params()
    params["dT_min"] = 0.0
    with pytest.raises(ValueError, match="must be > 0"):
        unit.solve(_kemp_feeds(thermo), params, thermo)
