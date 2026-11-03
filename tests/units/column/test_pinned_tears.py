"""A pinned tear is the spec itself: the mesh retreat never moves it (specs.py).

A distillate-rate spec on a partial condenser pins the top tear (D = V_1), and
the spec residuals skip it. The zero/one-tear retreat used to scale every tear
by 0.8, 0.64, ... when the mesh failed at the requested one, so a column whose
mesh failed at the pinned D came back "converged" at 0.8 D (measured: a
12-stage crude column with three steam side strippers pinned at
D = 474.64 mol/s reported 379.71). Now a mesh failure at a pinned tear is the
column's failure.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import Column, ColumnConvergenceError, specs

_P = 1.5e5
_D = 45.0


def _params() -> dict[str, Any]:
    """A steam-stripped wide-boiling column: 10 stages, partial condenser, no
    reboiler, nC5-nC14 at 560 K on stage 9 and 2 mol/s of steam under it (the
    relaxation start's test column, without its side stripper)."""
    return {
        "n_stages": 10,
        "condenser": "partial",
        "reboiler": "none",
        "pressure_profile": _P,
        "feeds": [
            {
                "stage": 9,
                "T": 560.0,
                "P": _P,
                "molar_flow": 100.0,
                "composition": {"nC5": 0.25, "nC8": 0.25, "nC11": 0.25, "nC14": 0.25},
            },
            {"stage": 10, "T": 500.0, "P": _P, "molar_flow": 2.0, "composition": {"H2O": 1.0}},
        ],
        "specs": {"distillate_rate": _D},
        "initialization": "relaxation",
    }


def test_partial_rectifier_meets_its_pinned_distillate(thermo: Thermo) -> None:
    """Control: the rectifier solves at the pinned D."""
    res = Column().solve({}, _params(), thermo)
    assert res.info["distillate_mol_s"] == pytest.approx(_D, rel=1e-12)


def test_mesh_failure_at_a_pinned_tear_is_not_retreated(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mesh fails at the pinned D (forced); the column raises instead of
    returning the profile the retreat would find at 0.8 D."""
    real = specs._solve_mesh
    asked: list[float | None] = []

    def failing_at_pin(col: Any, tb: Any, top: float | None, bot: float | None, *a: Any, **k: Any) -> Any:
        asked.append(top)
        if top is not None and abs(top - _D) < 1e-9:
            raise ColumnConvergenceError("forced mesh failure at the pinned distillate")
        return real(col, tb, top, bot, *a, **k)

    monkeypatch.setattr(specs, "_solve_mesh", failing_at_pin)
    with pytest.raises(ColumnConvergenceError, match="forced mesh failure"):
        Column().solve({}, _params(), thermo)
    assert all(top == pytest.approx(_D) for top in asked if top is not None)
