"""Two-tear column convergence integrity (P1-13, issues #248 / #332).

- Exact-residual acceptance applies to every tear count: a Newton trial that
  improves the pass's frozen rows but worsens the exact (refreshed-thermo)
  residual is rejected, and the pre-step state is restored.
- A two-tear mesh that misses its gate raises ``ColumnConvergenceError`` with
  the measured residuals; the NS-floor bypass is a zero/one-tear rule.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units import column as col_mod
from ngdesign.units.column import specs as specs_mod
from ngdesign.units.column.inside_out import _build_column, _seed_profile, _temperature_seed
from ngdesign.units.column.naphtali_sandholm import _DenseNSEngine, _ns_try_accept
from ngdesign.units.column.spec import ColumnConvergenceError, _parse_params
from ngdesign.units.column.thermo_adapter import _ThermoBox


def _two_tear_params() -> dict[str, Any]:
    """The C3/iC4 example: total condenser + kettle, so reflux and boilup are both tears."""
    return {
        "n_stages": 10,
        "condenser": "total",
        "reboiler": "kettle",
        "feed_stage": 5,
        "pressure_profile": 1.5e6,
        "specs": {"reflux_ratio": 2.5, "distillate_rate": 45.0},
    }


def _feed() -> dict[str, Any]:
    return {"T": 320.0, "P": 1.5e6, "molar_flow": 100.0, "composition": {"C3": 0.45, "iC4": 0.55}}


def _engine(thermo: Thermo) -> tuple[Any, _ThermoBox, Any, _DenseNSEngine]:
    parsed = _parse_params(_two_tear_params(), _feed())
    tb = _ThermoBox(thermo, 1.5e6, 1.5e6)
    col = _build_column(parsed, tb)
    assert col.n_tears == 2
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))
    prof = col_mod._solve_mesh(col, tb, 112.5, 132.5, prof)
    tear = prof.V[col.n - 1]
    return col, tb, prof, _DenseNSEngine(col, tb, prof, tear)


def test_two_tear_engine_uses_exact_residual_acceptance(thermo: Thermo) -> None:
    _, _, _, eng = _engine(thermo)
    assert eng.live_norm


def test_two_tear_step_worsening_the_exact_residual_is_rejected(thermo: Thermo) -> None:
    """A trial that the frozen rows accept but the exact residual rejects leaves the state untouched.

    The trial is a real Newton-sized move on the converged profile: shift every
    stage temperature 2 K. The residual handed to the acceptance reports the
    rows improved (as a frozen-row linearisation can), while the exact
    refreshed-thermo norm of the moved state is far worse - the measured #248
    mechanism (exact M 4.2e-6 -> 0.997 accepted on the old two-tear path).
    """
    col, _, prof, eng = _engine(thermo)
    eng.ex_m, eng.ex_h = eng.exact_norms(prof)
    u, _residuals = eng.begin_pass()
    before = copy.deepcopy(prof)
    t_base = col.n * len(col.comps)
    svec = [0.0] * len(u)
    for j in range(col.n):
        svec[t_base + j] = 2.0
    accepted, _, _ = _ns_try_accept(
        svec,
        u,
        len(u),
        lambda _u: [0.0] * len(u),  # frozen rows claim a perfect step
        eng.m_norm_of,
        eng.h_norm_of,
        1.0,
        1.0,
        eng.live_norm,
        eng.ex_m,
        eng.ex_h,
        prof,
        eng.apply,
        eng.exact_norms,
    )
    assert not accepted
    assert prof.T == before.T
    assert prof.V == before.V
    for x_now, x_before in zip(prof.x, before.x, strict=True):
        assert x_now == pytest.approx(x_before, rel=1e-14)  # restored through pack/unpack
    moved = copy.deepcopy(before)
    eng.apply(moved, [u[i] + svec[i] for i in range(len(u))])
    worse_m, worse_h = eng.exact_norms(moved)
    assert max(worse_m, worse_h) > max(eng.ex_m, eng.ex_h)


def test_two_tear_ns_failure_is_not_bypassed_by_the_floor(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A two-tear mesh whose Newton fails raises; ``_at_ns_floor`` is never consulted."""
    parsed = _parse_params(_two_tear_params(), _feed())
    tb = _ThermoBox(thermo, 1.5e6, 1.5e6)
    col = _build_column(parsed, tb)
    prof = _seed_profile(col, tb, *_temperature_seed(col, tb))

    def failing_ns(*_args: Any, **_kwargs: Any) -> Any:
        raise ColumnConvergenceError("Naphtali-Sandholm fallback stalled: injected")

    def floor_must_not_run(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("the NS-floor bypass ran on a two-tear column")

    monkeypatch.setattr(specs_mod, "_naphtali_sandholm", failing_ns)
    monkeypatch.setattr(specs_mod, "_at_ns_floor", floor_must_not_run)
    monkeypatch.setattr(specs_mod, "_OUTER_MAX", 1)
    with pytest.raises(ColumnConvergenceError, match=r"M=.*H="):
        col_mod._solve_mesh(col, tb, 112.5, 132.5, prof)
