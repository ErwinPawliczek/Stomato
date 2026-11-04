"""Stability-test cost of a many-component PT flash (``_state._DistinctTrialStabilityTester``).

thermo 0.6.1's ``StabilityTester.incipient_guesses`` draws its N random trial
compositions with ``seed(0)`` inside the outer loop once N*N > 1000, so for
N >= 32 it replays the same N compositions N times. A PT flash that finds its
feed stable walked every replay: the side_strip example's bottoms flash
(48 components, 500 K, 3 bar) ran 2,356 Michelsen trial iterations (45 s) for
100 distinct trials, which timed the unit-balance oracle out in the parallel
suite. The bounds below are counts, not wall time.
"""

from __future__ import annotations

from typing import Any

import pytest
import thermo.flash.flash_vl as flash_vl
from thermo.property_package import StabilityTester

from ngdesign import registry
from tests.conftest import flash_feed


def _side_strip_draw() -> dict[str, float]:
    side_strip: Any = registry.get("unit", "side_strip")
    feeds, _params = side_strip.example_case()
    return dict(feeds["draw_in"]["composition"])


def test_trials_are_distinct_and_keep_thermo_order() -> None:
    """Each distinct trial is handed out once, in thermo's own order (no index shift)."""
    z = _side_strip_draw()
    thermo_pkg: Any = registry.create("thermo", "pr")
    flasher = thermo_pkg._flasher(z)
    ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
    zs = [z[cid] for cid in ids]
    n = len(zs)
    assert n * n > 1000  # thermo's replaying branch

    ours = list(flasher.stab.incipient_guesses(500.0, 3.0e5, zs))
    raw = list(StabilityTester.incipient_guesses(flasher.stab, 500.0, 3.0e5, zs))

    assert len({tuple(g) for g in ours}) == len(ours)
    # Wilson (4) + pure (N) + random (N) distinct trials; thermo hands out 4 + N + N*N.
    assert len(ours) == 4 + 2 * n
    assert len(raw) == 4 + n + n * n
    assert ours == raw[: len(ours)]
    assert {tuple(g) for g in raw[len(ours) :]} <= {tuple(g) for g in ours}


def test_non_trailing_repeat_is_kept() -> None:
    """A repeat followed by a new trial is still handed out, so no trial index shifts.

    With water and ``expect_aqueous`` thermo hands the pure-water trial out first
    and again in its pure block; that repeat is mid-sequence and stays.
    """
    z = _side_strip_draw()
    z["H2O"] = 0.05
    total = sum(z.values())
    z = {cid: x / total for cid, x in z.items()}
    thermo_pkg: Any = registry.create("thermo", "pr")
    flasher = thermo_pkg._flasher(z)
    ids = tuple(sorted(cid for cid, x in z.items() if x > 0.0))
    zs = [z[cid] for cid in ids]
    n = len(zs)
    kwargs = {"expect_liquid": True, "expect_aqueous": True, "existing_phases": 2}

    ours = list(flasher.stab.incipient_guesses(500.0, 3.0e5, zs, **kwargs))
    raw = list(StabilityTester.incipient_guesses(flasher.stab, 500.0, 3.0e5, zs, **kwargs))

    assert len(raw) == 1 + 4 + n + n * n
    assert len(ours) == 1 + 4 + 2 * n  # the pure-water repeat kept, the replayed tail dropped
    assert ours == raw[: len(ours)]


def test_side_strip_flash_stability_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    """The side_strip example's flashes stay well under the replayed-trial cost.

    Measured: 2,366 stability iterations before the fix, 110 after.
    """
    calls = 0
    original = flash_vl.stability_iteration_Michelsen

    def counted(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(flash_vl, "stability_iteration_Michelsen", counted)
    thermo_pkg: Any = registry.create("thermo", "pr")
    cls: Any = registry.get("unit", "side_strip")
    feeds, params = cls.example_case()
    inlets = {name: flash_feed(thermo_pkg, feed) for name, feed in feeds.items()}
    result = registry.create("unit", "side_strip").solve(inlets, params, thermo_pkg)

    assert set(result.outlets) == {"overhead_out", "bottoms_out"}
    assert calls <= 200
