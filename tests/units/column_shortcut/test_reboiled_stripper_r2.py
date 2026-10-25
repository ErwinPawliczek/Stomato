"""Reboiled stripper R2 tests (spec U-R2 reboiled_stripper).

Identity: the adapter's outlets equal a direct ``Column().solve`` with the
mapped params (condenser "none", kettle reboiler, feed stage 1, the spec
passed through) bit-for-bit -- the R2 identity is to the column row, not to
the R0 Kremser level (no exact Kremser-vs-MESH reduction exists).

Basis feed: C1/NC4 = 0.1/0.9, 300 K, 2 MPa, 100 mol/s, N = 4 -- the P1-09/P1-10
one-tear stripper anchor feed. The spec's original nC4/nC5 bench was withdrawn
by the orchestrator's ruling on PR #292: the kettle-only column core does not
converge its rate specs nor that bench feed (column-core rate-spec convergence
defect, #248 -- reported, not worked around here). Independent expected values
only, per the ruling:

- the locked P1 anchors, ``tests/units/test_column_feed_determined.py``
  (constant check: D = 10.4437 and B = 89.5563 mol/s at boilup ratio 0.5,
  printed in the merged P1-10 acceptance test);
- ``thermo`` bubble/dew points, computed here from the outlet compositions,
  never taken from the column;
- mass and energy closure from arithmetic.

Refusals: one test per row of the spec's refusal table. The
``reboiler_duty_W`` refusal fires before any column call (the kettle-only
column core hits a singular Newton system for that spec -- a core defect
reported to the orchestrator, not worked around here).

Rate specs pass through to the column unchanged; today they do not converge
(#248), pinned with ``xfail(strict=True)`` so the tests flip loudly when the
core lands.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, ColumnConvergenceError, ColumnSpecError
from ngdesign.units.column.spec import _SPEC_TOL
from ngdesign.units.column_shortcut.reboiled_stripper_r2 import (
    ReboiledStripperR2,
    ReboiledStripperR2Error,
)

FEED: dict[str, Any] = {
    "T": 300.0,
    "P": 2e6,
    "molar_flow": 100.0,
    "composition": {"C1": 0.1, "NC4": 0.9},
}

# Locked P1-10 anchors (printed in tests/units/test_column_feed_determined.py,
# the merged acceptance test): N = 4, boilup_ratio 0.5 on this feed.
_ANCHOR_D = 10.4437
_ANCHOR_B = 89.5563


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


@pytest.fixture(scope="module")
def boilup_case(thermo: Thermo) -> UnitResult:
    """The N = 4 boilup_ratio 0.5 anchor solve, shared by the cheap tests."""
    return ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(), thermo)


@pytest.mark.timeout(600)
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


@pytest.mark.timeout(600)
def test_locked_p1_anchor_products(boilup_case: UnitResult) -> None:
    """Product rates hit the locked P1-10 anchors (independent printed values).

    Constant check: D = 10.4437 and B = 89.5563 mol/s, printed in the merged
    P1-10 acceptance test ``tests/units/test_column_feed_determined.py``
    (parametrize row ``(4, 0.5, 10.4437, 89.5563, ...)``). Tolerance matches
    that test's own ``abs=5e-3`` gate -- not widened.
    """
    d = boilup_case.outlets["overhead"].molar_flow
    b = boilup_case.outlets["bottoms"].molar_flow
    assert d == pytest.approx(_ANCHOR_D, abs=5e-3)
    assert b == pytest.approx(_ANCHOR_B, abs=5e-3)


@pytest.mark.timeout(600)
def test_material_identity_mass_closure(boilup_case: UnitResult) -> None:
    """Total and per-component balances close from arithmetic (U-R1 V0 rule)."""
    feed = _feed(FEED)
    overhead = boilup_case.outlets["overhead"]
    bottoms = boilup_case.outlets["bottoms"]
    d = overhead.molar_flow
    b = bottoms.molar_flow
    f = feed.molar_flow
    assert d + b == pytest.approx(f, rel=1e-8)
    for cid, z in feed.composition.items():
        out = d * overhead.composition.get(cid, 0.0) + b * bottoms.composition.get(cid, 0.0)
        assert out == pytest.approx(f * z, rel=1e-6)


@pytest.mark.timeout(600)
def test_energy_closure(boilup_case: UnitResult) -> None:
    "nH_in + duty_W = nH_out at 1e-8 (U-R1 energy rule; power_W = 0)."
    feed = _feed(FEED)
    overhead = boilup_case.outlets["overhead"]
    bottoms = boilup_case.outlets["bottoms"]
    h_in = feed.molar_flow * feed.enthalpy
    h_out = overhead.molar_flow * overhead.enthalpy + bottoms.molar_flow * bottoms.enthalpy
    duty = boilup_case.duty_W
    assert h_in + duty == pytest.approx(h_out, rel=1e-8)


@pytest.mark.timeout(600)
def test_phase_state_kettle_bubble_overhead_dew(boilup_case: UnitResult, thermo: Thermo) -> None:
    """The kettle bottoms is saturated liquid, the stage-1 overhead saturated
    vapour -- checked against thermo bubble/dew points, never column outputs."""
    p = FEED["P"]
    bottoms = boilup_case.outlets["bottoms"]
    overhead = boilup_case.outlets["overhead"]
    kettle_t = boilup_case.info["stage_4_T_K"]
    top_t = boilup_case.info["stage_1_T_K"]
    bubble_t = thermo.bubble_point(dict(bottoms.composition), P=p).T
    dew_t = thermo.dew_point(dict(overhead.composition), P=p).T
    assert abs(bottoms.T - bubble_t) < 1e-4
    assert abs(kettle_t - bubble_t) < 1e-4
    assert abs(overhead.T - dew_t) < 1e-4
    assert abs(top_t - dew_t) < 1e-4


@pytest.mark.timeout(600)
def test_spec_achieved_boilup_ratio_within_gate(boilup_case: UnitResult) -> None:
    """Converged boilup ratio within the column's own spec gate."""
    assert abs(boilup_case.info["spec_achieved"] - 0.5) / 0.5 < _SPEC_TOL
    assert boilup_case.info["spec_name"] == 1.0


@pytest.mark.timeout(600)
def test_spec_achieved_component_recovery_within_gate(thermo: Thermo) -> None:
    """NC4 recovery 0.9 to the bottoms, within the column's spec gate.

    The measured value comes from the outlet flows (B*x_B,NC4 over the feed's
    NC4), not from the column's info.
    """
    spec: dict[str, Any] = {"component_recovery": {"component": "NC4", "value": 0.9, "product": "bottoms"}}
    result = ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec=spec), thermo)
    assert abs(result.info["spec_achieved"] - 0.9) / 0.9 < _SPEC_TOL
    assert result.info["spec_name"] == 4.0


@pytest.mark.xfail(strict=True, reason="column-core rate-spec convergence: #248")
@pytest.mark.timeout(600)
def test_rate_spec_bottoms_rate_converges(thermo: Thermo) -> None:
    """bottoms_rate passes through to the column; convergence blocked by #248."""
    result = ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec={"bottoms_rate": 90.0}), thermo)
    b = result.outlets["bottoms"].molar_flow
    assert abs(b - 90.0) / 90.0 < _SPEC_TOL


@pytest.mark.xfail(strict=True, reason="column-core rate-spec convergence: #248")
@pytest.mark.timeout(600)
def test_rate_spec_distillate_rate_converges(thermo: Thermo) -> None:
    """distillate_rate passes through to the column; convergence blocked by #248."""
    result = ReboiledStripperR2().solve(
        {"feed": _feed(FEED)}, _params(spec={"distillate_rate": 10.0}), thermo
    )
    d = result.outlets["overhead"].molar_flow
    assert abs(d - 10.0) / 10.0 < _SPEC_TOL


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


def test_refusal_reboiler_duty_w_before_column_call(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """reboiler_duty_W is refused before the column is ever called."""
    monkeypatch.setattr(
        Column, "solve", lambda *a, **k: pytest.fail("reboiler_duty_W must be refused pre-column")
    )
    with pytest.raises(ReboiledStripperR2Error, match="reboiler_duty_W.*singular|singular.*reboiler_duty_W"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec={"reboiler_duty_W": 1e6}), thermo)


def test_refusal_pressure_profile_wrong_length(thermo: Thermo) -> None:
    with pytest.raises(ReboiledStripperR2Error, match="pressure_profile"):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(pressure_profile=[2e6, 2e6, 2e6]), thermo)


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
    unchanged -- no except around the column call."""
    bad_spec = {"component_recovery": {"component": "H2O", "value": 0.9, "product": "bottoms"}}
    with pytest.raises(ColumnSpecError):
        ReboiledStripperR2().solve({"feed": _feed(FEED)}, _params(spec=bad_spec), thermo)


def test_error_types() -> None:
    """ColumnConvergenceError propagates as itself (typed RuntimeError)."""
    assert issubclass(ColumnConvergenceError, RuntimeError)
    assert issubclass(ReboiledStripperR2Error, ValueError)
