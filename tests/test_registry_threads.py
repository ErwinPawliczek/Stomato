"""registry.discover() is safe to call from several threads at once (API thread pool).

Two first requests racing through discovery used to run the catalogue hooks twice:
the duplicate registration raised, the discovered flag was reset, and every later
request failed the same way.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.thermo import catalogue as thermo_catalogue
from ngdesign.units import catalogue as unit_catalogue


def test_concurrent_first_discovery_runs_the_catalogue_hooks_once(monkeypatch: pytest.MonkeyPatch) -> None:
    registry.discover()  # plugin modules imported; only the hooks below re-run
    calls = {"thermo": 0, "unit": 0}

    def slow(kind: str) -> Any:
        def hook(_existing: Any = None) -> None:
            calls[kind] += 1
            time.sleep(0.05)  # widen the race window

        return hook

    monkeypatch.setattr(thermo_catalogue, "register_all", slow("thermo"))
    monkeypatch.setattr(unit_catalogue, "register_all", slow("unit"))
    monkeypatch.setattr(registry, "_discovered", False)

    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker() -> None:
        barrier.wait()
        try:
            registry.available("thermo")
        except BaseException as exc:  # collected for the assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert calls == {"thermo": 1, "unit": 1}
    assert registry._discovered
