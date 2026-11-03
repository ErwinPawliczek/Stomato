"""The property cache keys on exact (composition, T, P) (issue #332).

Rounded keys made every rounding cell return whichever state was computed first:
K values were piecewise constant, depended on evaluation order, and corrupted
finite-difference T derivatives. Neighbouring states must now get their own
results, while identical inputs still hit the cache.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.thermo import _state

_Z = {"C1": 0.4, "C3": 0.35, "nC4": 0.25}
_T, _P = 250.0, 2.0e6


def _counting(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls = [0]
    real = _state.run_flash

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls[0] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(_state, "run_flash", counted)
    return calls


def test_identical_inputs_hit_the_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    thermo = registry.create("thermo", "pr")
    calls = _counting(monkeypatch)
    first = thermo.flash_pt(_Z, _T, _P, 1.0)
    second = thermo.flash_pt(dict(_Z), _T, _P, 1.0)
    assert calls[0] == 1
    assert second == first


def test_a_neighbouring_temperature_gets_its_own_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1e-8 K sat inside one former 1e-6 K rounding cell and returned the first
    # state's result; now it is a separate flash with its own enthalpy.
    thermo = registry.create("thermo", "pr")
    calls = _counting(monkeypatch)
    a = thermo.flash_pt(_Z, _T, _P, 1.0)
    b = thermo.flash_pt(_Z, _T + 1e-8, _P, 1.0)
    assert calls[0] == 2
    assert b.T == _T + 1e-8
    assert b.enthalpy != a.enthalpy


def test_a_neighbouring_composition_gets_its_own_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    thermo = registry.create("thermo", "pr")
    calls = _counting(monkeypatch)
    thermo.flash_pt(_Z, _T, _P, 1.0)
    z2 = {"C1": 0.4 + 1e-12, "C3": 0.35, "nC4": 0.25 - 1e-12}
    b = thermo.flash_pt(z2, _T, _P, 1.0)
    assert calls[0] == 2
    assert b.composition["C1"] == pytest.approx(z2["C1"], rel=0, abs=1e-15)


def test_cache_key_is_exact() -> None:
    key = _state.cache_key({"C3": 0.35, "C1": 0.4}, 250.000000001, 2000000.0004)
    assert key == ((("C1", 0.4), ("C3", 0.35)), 250.000000001, 2000000.0004)
