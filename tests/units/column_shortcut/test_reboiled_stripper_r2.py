"""Reboiled stripper R2 tests (spec U-R2 reboiled_stripper).

Identity: the adapter's outlets equal a direct ``Column().solve`` with the
mapped params (condenser "none", kettle reboiler, feed stage 1, the spec
passed through) bit-for-bit — the R2 identity is to the column row, not to
the R0 Kremser level (no exact Kremser-vs-MESH reduction exists).

Refusals: one test per row of the spec's refusal table. The
``reboiler_duty_W`` refusal fires before any column call (the kettle-only
column core hits a singular Newton system for that spec — a core defect
reported to the orchestrator, not worked around here).

Basis feed for the solves: nC4/nC5 = 0.3/0.7, 330 K, 5 bar, 100 mol/s,
N = 4, boilup_ratio 0.5 — the spec's measured bench case (converges in
under 6 s).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, ColumnConvergenceError, ColumnSpecError
from ngdesign.units.column.spec import _SPEC_TOL
from ngdesign.units.column_shortcut.reboiled_stripper_r2 import (
    ReboiledStripperR2,
    ReboiledStripperR2Error,
)

FEED: dict[str, Any] = {
    "T": 330.0,
    "P": 5e6,
    "molar_flow": 100.0,
    "composition": {"nC4": 0.3, "nC5": 0.7},
}


def _feed(state: dict[str, Any]) -> StreamState:
    return StreamState(
        T=state["T"],
        P=state["P"],
        molar_flow=state["molar_flow"],
        composition=dict(state["composition"]),
        vapor_fraction=0.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[],
    )


def _params(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"n_stages": 4, "spec": {"boilup_ratio": 0.5}}
    base.update(over)
    return base


def test_identity_to_column_row(thermo: Thermo) -> None:
    """Adapter outlets == Column().solve with the mapped params, bit-for-bit."""
    mapped: dict[str, Any] = {
        "n_stages": 4,
        "condenser": "none",
        "reboiler": "kettle",
        "feed_stage": 1,
        "pressure_profile": FEED["P"],
        "specs": {"boilup_ratio": 0.5},
    }
    direct = Column().solve({"feed": _feed(FEED)}, mapped, thermo)
    via_adapter = ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(), thermo)

    assert via_adapter.outlets.keys() == {"overhead", "bottoms"}
    assert via_adapter.outlets["overhead"] == direct.outlets["distillate"]
    assert via_adapter.outlets["bottoms"] == direct.outlets["bottoms"]
    # duty_W is the column's net duty (the physical reboiler duty here: no
    # condenser), defined by the column's exact overall balance.
    assert via_adapter.duty_W == direct.info["reboiler_duty_W"]
    assert via_adapter.power_W == 0.0
    for key in ("reboiler_duty_W", "boilup_ratio", "distillate_mol_s", "bottoms_mol_s"):
        assert via_adapter.info[key] == direct.info[key]
    stage_keys = [k for k in direct.info if k.startswith("stage_")]
    assert stage_keys and all(via_adapter.info[k] == direct.info[k] for k in stage_keys)


def test_refusal_n_stages_missing(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="n_stages"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, {"spec": {"boilup_ratio": 0.5}}, thermo)


def test_refusal_n_stages_non_integer(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="n_stages"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(n_stages=4.5), thermo)


def test_refusal_n_stages_below_two(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="n_stages"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(n_stages=1), thermo)


def test_refusal_spec_missing(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="spec"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, {"n_stages": 4}, thermo)


def test_refusal_spec_two_keys(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="spec"):
        ReboiledStripperR2().solve(
            {"feed": _feed(FEED)},
            _params(spec={"boilup_ratio": 0.5, "bottoms_rate": 60.0}),
            thermo,
        )


def test_refusal_spec_key_outside_allowed_set(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="spec"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec={"reflux_ratio": 2.0}), thermo)


def test_refusal_reboiler_duty_w_before_column_call(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reboiler_duty_W is refused before the column is ever called."""
    monkeypatch.setattr(
        Column, "solve", lambda *a, **k: pytest.fail("reboiler_duty_W must be refused pre-column")
    )
    with pytest.raises(
        ReboiledStripperR2Error, match="reboiler_duty_W.*singular|singular.*reboiler_duty_W"
    ):
        ReboiledStripperR2().solve(
            {"feed": _feed(FEED)}, _params(spec={"reboiler_duty_W": 1e6}), thermo
        )


def test_refusal_pressure_profile_wrong_length(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="pressure_profile"):
        ReboiledStripperR2().solve(
            {"feed": _feed(FEED)}, _params(pressure_profile=[5e6, 5e6, 5e6]), thermo
        )


def test_refusal_pressure_profile_nonpositive(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="pressure_profile"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(pressure_profile=-1.0), thermo)


def test_refusal_feed_zero_flow(thermo: Thermo) -> None:
    zero = dict(FEED, molar_flow=0.0)
    with pytest.raises(ReboiledStripperR2Error, match="feed"):
        ReboiledStripperR2().solve({"feed": _feed(zero)}, _params(), thermo)


def test_refusal_unknown_param_key(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="unknown"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(vapour_flow=1.0), thermo)


def test_column_failure_reraised_unchanged(thermo: Thermo) -> None:
    """A column-level failure (component not in the feed support) propagates
    unchanged — no except around the column call."""
    bad_spec = {"component_recovery": {"component": "H2O", "value": 0.9, "product": "bottoms"}}
    with pytest.raises(ColumnSpecError):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec=bad_spec), thermo)


def test_spec_achieved_boilup_ratio_within_gate(thermo: Thermo) -> None:
    """Converged boilup ratio within the column's own spec gate (measured on
    main 2026-10-25: 0.501683 vs target 0.5)."""
    result = ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(), thermo)
    assert abs(result.info["spec_achieved"] - 0.5) / 0.5 < _SPEC_TOL
    assert result.info["spec_name"] == 1.0


def test_error_types() -> None:
    """ColumnConvergenceError propagates as itself (typed RuntimeError)."""
    assert issubclass(ColumnConvergenceError, RuntimeError)
    assert issubclass(ReboiledStripperR2Error, ValueError)
