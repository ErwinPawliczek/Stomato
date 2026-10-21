"""Variable-address layer (spec P2-01): enumeration, assignment, errors."""

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet
from ngdesign.contracts.flowsheet import SolvedFlowsheet
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.variables import assign, readable, resolve, writable


def _solved() -> tuple[Flowsheet, SolvedFlowsheet]:
    thermo = registry.create("thermo", "pr")
    fs = slice_fs.build()
    return fs, registry.create("solver", "sequential_modular").solve(fs, thermo)


def test_every_readable_address_resolves() -> None:
    fs, solved = _solved()
    addrs = readable(solved)
    assert "S-005.x.H2O" in addrs
    assert "K-101.duty_W" in addrs
    for addr in addrs:
        assert isinstance(resolve(addr, solved), float), addr


def test_every_writable_address_assigns() -> None:
    fs, _ = _solved()
    addrs = writable(fs)
    assert "K-101.params.P_out" in addrs
    assert "S-001.feed.molar_flow" in addrs
    for addr in addrs:
        fs2 = assign(fs, addr, 1.0)
        assert fs2 != fs, addr


def test_unknown_head_error_names_the_nearest_heads() -> None:
    _, solved = _solved()
    with pytest.raises(ValueError, match="S-003"):
        resolve("S-999.T", solved)
    with pytest.raises(ValueError, match="stream fields"):
        resolve("S-003.zzz", solved)
    with pytest.raises(ValueError, match="info"):
        resolve("K-101.zzz", solved)


def test_unknown_write_head_error_names_writable_heads() -> None:
    fs, _ = _solved()
    with pytest.raises(ValueError, match="writable heads"):
        assign(fs, "S-999.feed.T", 300.0)
    with pytest.raises(ValueError, match="stream writes look like"):
        assign(fs, "S-001.zzz", 300.0)


def test_unknown_component_error_lists_the_slate() -> None:
    fs, _ = _solved()
    with pytest.raises(ValueError, match="H2O"):
        assign(fs, "S-001.feed.composition.H2S", 0.5)


def test_assign_is_pure() -> None:
    fs, _ = _solved()
    snapshot = fs.model_dump_json()
    assign(fs, "K-101.params.P_out", 9e6)
    assign(fs, "S-001.feed.T", 320.0)
    assert fs.model_dump_json() == snapshot


def test_assign_updates_and_rebuilds() -> None:
    fs, _ = _solved()
    fs2 = assign(fs, "K-101.params.P_out", 9e6)
    assert fs.unit("K-101").params["P_out"] == 7e6
    assert fs2.unit("K-101").params["P_out"] == 9e6


def test_composition_write_renormalizes_the_rest() -> None:
    fs, _ = _solved()
    fs2 = assign(fs, "S-001.feed.composition.H2O", 0.5)
    comp = next(s for s in fs2.streams if s.id == "S-001").feed.composition  # type: ignore[union-attr]
    assert comp["H2O"] == pytest.approx(0.5)
    assert sum(comp.values()) == pytest.approx(1.0)


def test_pure_composition_write_zeroes_the_rest() -> None:
    fs, _ = _solved()
    fs2 = assign(fs, "S-001.feed.composition.C1", 1.0)
    comp = next(s for s in fs2.streams if s.id == "S-001").feed.composition  # type: ignore[union-attr]
    assert sum(comp.values()) == pytest.approx(1.0)
    assert comp["C1"] == pytest.approx(1.0)


def test_out_of_range_fraction_rejected() -> None:
    fs, _ = _solved()
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        assign(fs, "S-001.feed.composition.C1", 1.5)
