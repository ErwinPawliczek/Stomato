"""Rackett and COSTALD liquid-density rows: density changes, nothing else does.

Anchors: saturated propane 492.62 kg/m3 at 300 K, 2 MPa, and n-hexane 653.17 kg/m3 at
300 K, 0.1 MPa, both from the reference equations in CoolProp (Lemmon & Span), read
once and quoted here so that the test does not need the optional dependency.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind
from ngdesign.thermo.liquid_density import costald_volume, rackett_volume, rackett_zra

ROWS = [("pr", "pr-rackett"), ("srk", "srk-rackett"), ("pr", "pr-costald"), ("srk", "srk-costald")]
PROPANE_300K_2MPA = 492.62
HEXANE_300K_100KPA = 653.17


def _pkg(row: str) -> Any:
    return registry.create("thermo", row)


@pytest.mark.parametrize(("base", "row"), ROWS)
def test_liquid_density_moves_towards_reference(base: str, row: str) -> None:
    """The EOS is 8-10 % off these liquids; the row lands within 1.5 %."""
    for cid, T, P, ref in (
        ("propane", 300.0, 2e6, PROPANE_300K_2MPA),
        ("n-hexane", 300.0, 1e5, HEXANE_300K_100KPA),
    ):
        got = _pkg(row).flash_pt({cid: 1.0}, T, P, 1.0).phases[0].density
        eos = _pkg(base).flash_pt({cid: 1.0}, T, P, 1.0).phases[0].density
        assert abs(got - ref) < abs(eos - ref)
        assert got == pytest.approx(ref, rel=0.015)


@pytest.mark.parametrize(("base", "row"), ROWS)
def test_vle_and_enthalpy_are_the_base_rows(base: str, row: str) -> None:
    z = {"methane": 0.6, "propane": 0.4}
    a = _pkg(base).flash_pt(z, 250.0, 5e6, 1.0)
    b = _pkg(row).flash_pt(z, 250.0, 5e6, 1.0)
    assert b.vapor_fraction == a.vapor_fraction
    assert b.enthalpy == a.enthalpy
    assert b.phases[1].composition == a.phases[1].composition
    assert b.phases[0].density == a.phases[0].density  # the vapour's volume is untouched
    assert b.phases[1].density != a.phases[1].density


def test_costald_is_compressed_and_rackett_is_not() -> None:
    """Only the Tait term sees pressure; CoolProp puts 10 MPa at +1.6 % for n-hexane."""
    z = {"n-hexane": 1.0}
    costald = _pkg("pr-costald")
    rackett = _pkg("pr-rackett")
    rise = (
        costald.phase_props(z, 300.0, 1e7, PhaseKind.HC_LIQUID).density
        / costald.phase_props(z, 300.0, 1e5, PhaseKind.HC_LIQUID).density
    )
    assert rise == pytest.approx(1.0158, abs=0.004)
    assert rackett.phase_props(z, 300.0, 1e7, PhaseKind.HC_LIQUID).density == pytest.approx(
        rackett.phase_props(z, 300.0, 1e5, PhaseKind.HC_LIQUID).density, rel=1e-12
    )


@pytest.mark.parametrize(("base", "row"), ROWS)
def test_above_the_mixture_tc_the_eos_volume_stands(base: str, row: str) -> None:
    z = {"methane": 0.9, "propane": 0.1}
    a = _pkg(base).phase_props(z, 300.0, 5e6, PhaseKind.HC_LIQUID).density
    assert _pkg(row).phase_props(z, 300.0, 5e6, PhaseKind.HC_LIQUID).density == a


def test_helpers_give_none_above_tc_and_the_published_zra() -> None:
    assert rackett_zra(0.0) == pytest.approx(0.29056)
    assert rackett_volume(400.0, [1.0], [369.8], [4.25e6], [0.152], [44.1]) is None
    assert costald_volume(400.0, 1e6, [1.0], [369.8], [2e-4], [0.152]) is None
