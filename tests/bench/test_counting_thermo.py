"""CountingThermo proxy: counts flashes correctly and is transparent (spec P0-06)."""

from __future__ import annotations

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import StreamState
from scripts.bench_baseline import CountingThermo

Z: dict[str, float] = {"N2": 0.01, "CO2": 0.02, "C1": 0.85, "C2": 0.07, "C3": 0.03, "nC4": 0.02}
T = 310.0
P = 4.0e6
FLOW = 10.0


def test_counts_each_flash_kind(thermo: Thermo) -> None:
    counting = CountingThermo(thermo)
    counting.flash_pt(dict(Z), T, P, FLOW)
    a = counting.flash_pt(dict(Z), T, P, FLOW)
    counting.flash_ph(dict(Z), P, a.enthalpy, FLOW)
    counting.flash_ps(dict(Z), P, a.entropy, FLOW)
    assert counting.flashes_pt == 2
    assert counting.flashes_ph == 1
    assert counting.flashes_ps == 1
    assert counting.flash_wall_s > 0.0


def test_transparent_same_stream_state(thermo: Thermo) -> None:
    """The proxy returns the wrapped plugin's own answer, not a reshaped copy."""
    counting = CountingThermo(thermo)
    wrapped_pt = counting.flash_pt(dict(Z), T, P, FLOW)
    raw_pt = thermo.flash_pt(dict(Z), T, P, FLOW)
    assert isinstance(wrapped_pt, StreamState)
    assert wrapped_pt == raw_pt

    wrapped_ph = counting.flash_ph(dict(Z), P, raw_pt.enthalpy, FLOW)
    raw_ph = thermo.flash_ph(dict(Z), P, raw_pt.enthalpy, FLOW)
    assert wrapped_ph == raw_ph

    wrapped_ps = counting.flash_ps(dict(Z), P, raw_pt.entropy, FLOW)
    raw_ps = thermo.flash_ps(dict(Z), P, raw_pt.entropy, FLOW)
    assert wrapped_ps == raw_ps


def test_satisfies_thermo_protocol(thermo: Thermo) -> None:
    counting = CountingThermo(thermo)
    assert isinstance(counting, Thermo)


def test_wall_time_accumulates(thermo: Thermo) -> None:
    counting = CountingThermo(thermo)
    counting.flash_pt(dict(Z), T, P, FLOW)
    first = counting.flash_wall_s
    assert first >= 0.0
    counting.flash_pt(dict(Z), T, P, FLOW)
    assert counting.flash_wall_s >= first
