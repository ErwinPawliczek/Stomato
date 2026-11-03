"""``liquid_split``: the liquid-liquid equilibrium of a liquid at (T, P), no vapour.

The oracle is the package's own PT flash: where the flash of z holds no vapour,
its liquids ARE z's liquid-liquid split, and ``liquid_split`` must return the
same liquids (fractions and compositions) to the successive substitution's
tolerance. A liquid the flash keeps in one phase returns the single-phase
build itself. The fixed-phase-set mode (seeded, no stability test) must land
on the same split as the full test.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.stream import PhaseKind

#: Mole-fraction agreement between the split and the flash's liquids: both
#: stop thermo's successive substitution at PT_SS_TOL (1e-13 on the fugacity
#: error), measured to agree to ~1e-11.
_TOL = 1e-8


@pytest.fixture(scope="module")
def pr() -> Any:
    return registry.create("thermo", "pr")


def _liquids(state: Any) -> list[Any]:
    return [p for p in state.phases if p.kind != PhaseKind.VAPOR]


def test_water_hydrocarbon_split_matches_the_flash(pr: Any) -> None:
    z = {"H2O": 0.4, "nC7": 0.35, "nC10": 0.25}
    T, P = 330.0, 5.0e5
    state = pr.flash_pt(z, T, P, 1.0)
    assert state.vapor_fraction == 0.0
    flash_liquids = sorted(_liquids(state), key=lambda p: p.composition["H2O"])
    assert len(flash_liquids) == 2
    split = sorted(pr.liquid_split(z, T, P), key=lambda p: p.composition["H2O"])
    assert len(split) == 2
    for mine, theirs in zip(split, flash_liquids, strict=True):
        assert mine.mole_fraction == pytest.approx(theirs.mole_fraction, abs=_TOL)
        for cid in z:
            assert mine.composition[cid] == pytest.approx(theirs.composition[cid], abs=_TOL)
        assert mine.enthalpy == pytest.approx(theirs.enthalpy, rel=1e-8)


def test_homogeneous_liquid_is_the_single_phase_build(pr: Any) -> None:
    z = {"nC6": 0.5, "nC8": 0.5}
    T, P = 320.0, 2.0e5
    split = pr.liquid_split(z, T, P)
    assert len(split) == 1
    built = pr.phase_props(z, T, P, PhaseKind.HC_LIQUID)
    assert split[0].mole_fraction == 1.0
    assert split[0].enthalpy == built.enthalpy
    assert split[0].ln_phi == built.ln_phi


def test_seeded_and_fixed_phase_set_splits_agree_with_the_full_test(pr: Any) -> None:
    z = {"H2O": 0.4, "nC7": 0.35, "nC10": 0.25}
    T, P = 330.0, 5.0e5
    full = pr.liquid_split(z, T, P)
    seed = [p.composition for p in full]
    seeded = pr.liquid_split(z, T, P, seed=seed)
    # A nearby state re-split from the seed without a stability test.
    fixed = pr.liquid_split(z, T + 1e-4, P, seed=seed, stability=False)
    full_near = pr.liquid_split(z, T + 1e-4, P)
    for a, b in ((full, seeded), (full_near, fixed)):
        assert len(a) == len(b) == 2
        pa = sorted(a, key=lambda p: p.composition["H2O"])
        pb = sorted(b, key=lambda p: p.composition["H2O"])
        for x, y in zip(pa, pb, strict=True):
            assert x.mole_fraction == pytest.approx(y.mole_fraction, abs=_TOL)
            for cid in z:
                assert x.composition[cid] == pytest.approx(y.composition[cid], abs=_TOL)


def test_fixed_phase_set_without_a_seed_reads_one_liquid(pr: Any) -> None:
    z = {"H2O": 0.4, "nC7": 0.35, "nC10": 0.25}
    split = pr.liquid_split(z, 330.0, 5.0e5, stability=False)
    assert len(split) == 1
