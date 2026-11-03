"""A pinned kettle boilup is a specification: a failing mesh is never retreated off it.

``mesh_at`` (units/column/specs.py; the partial-condenser pin is
test_pinned_tears.py) retreats a failing tear geometrically
(0.8x ... 0.26x) and backtracks it toward the last converged seed. Both are
legitimate for a FREE tear: the secant reads the tear it actually solved and
walks on. A PINNED tear (a kettle's ``boilup_rate``, a partial condenser's
``distillate_rate``) has its spec removed from the residual set, so a profile
solved at a retreated tear came back as the answer at the wrong boilup. The
mesh is made to fail at exactly the requested boilup; the column must refuse
rather than return a converged profile at a boilup nobody asked for.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column import ColumnConvergenceError, solve_column_full
from ngdesign.units.column import specs as specs_mod

P = 10.0e5
BOILUP = 40.0


def _params() -> dict[str, Any]:
    """A feed-determined 6-stage kettle stripper: no condenser, boilup pinned."""
    return {
        "n_stages": 6,
        "condenser": "none",
        "reboiler": "kettle",
        "pressure_profile": P,
        "feeds": [
            {
                "stage": 1,
                "T": 320.0,
                "P": P,
                "molar_flow": 100.0,
                "composition": {"C3": 0.3, "nC4": 0.4, "nC5": 0.3},
            }
        ],
        "specs": {"boilup_rate": BOILUP},
    }


def test_converged_at_the_pinned_boilup(thermo: Thermo) -> None:
    """Unpatched, the stripper converges and its kettle vapour is the spec."""
    r, _internal = solve_column_full({}, _params(), thermo)
    assert r.info["stage_5_V_mol_s"] == pytest.approx(BOILUP, rel=1e-9)


def test_failure_at_the_pinned_boilup_is_not_retreated(
    thermo: Thermo, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = specs_mod._solve_mesh
    asked: list[float | None] = []

    def failing_at_spec(col: Any, tb: Any, top: Any, bot: Any, *args: Any, **kwargs: Any) -> Any:
        asked.append(bot)
        if bot is not None and abs(bot - BOILUP) < 1e-12:
            raise ColumnConvergenceError("forced failure at the pinned boilup")
        return real(col, tb, top, bot, *args, **kwargs)

    monkeypatch.setattr(specs_mod, "_solve_mesh", failing_at_spec)
    with pytest.raises(ColumnConvergenceError):
        solve_column_full({}, _params(), thermo)
    # Every mesh the column tried sat at the pinned boilup.
    assert asked
    assert all(b is not None and abs(b - BOILUP) < 1e-12 for b in asked), asked
