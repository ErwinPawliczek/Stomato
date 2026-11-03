"""Amine regenerators R2 (MDEA/MEA/DEA): reboiled MESH strippers on the reactive amine package.

Independent oracles, none read from the solver's own gate:
- component closure over the boundary streams;
- a stage audit from the reported profile: every stage's component balance,
  and a re-flash of each stage's L + V contents on the package, which must
  hand back the reported vapour (stage_audit.py);
- physics: lean loadings below the rich ones, and more boilup strips more.
Measured wall times: 2-8 s per solve; MEA below 35 mol/s (the boilup
continuation) 32 s at 30 mol/s.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.amine_regenerator_r2 import (
    DEFAULT_FEED_T,
    DEFAULT_REGENERATOR_P,
    AmineRegeneratorR2Error,
    DeaRegeneratorR2,
    MdeaRegeneratorR2,
    MeaRegeneratorR2,
)
from tests.conftest import flash_feed
from tests.units.column.stage_audit import equilibrium_residuals, material_residuals, read_stages

CLASSES = [MdeaRegeneratorR2, MeaRegeneratorR2, DeaRegeneratorR2]


def _solve(cls: type[MdeaRegeneratorR2], thermo: Thermo, **overrides: Any) -> tuple[StreamState, UnitResult]:
    feeds, params = cls.example_case()
    rich = flash_feed(thermo, feeds["rich_amine_in"])
    return rich, cls().solve({"rich_amine_in": rich}, {**params, **overrides}, thermo)


@pytest.fixture(name="solved", scope="module", params=CLASSES, ids=lambda c: c.AMINE)
def solved_fixture(request: pytest.FixtureRequest) -> tuple[Any, ...]:
    thermo: Thermo = registry.create("thermo", "pr")
    return (request.param, thermo, *_solve(request.param, thermo))


def test_components_close(solved: Any) -> None:
    _, _, rich, res = solved
    for cid, z in rich.composition.items():
        out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in res.outlets.values())
        assert out == pytest.approx(rich.molar_flow * z, rel=1e-9), cid


def test_stage_audit(solved: Any) -> None:
    """Reported-profile stage balances and a package re-flash of every stage's contents."""
    _, _, rich, res = solved
    package = registry.create("thermo", "amine_ke")
    comps = sorted(rich.composition)
    feed = package.flash_pt(dict(rich.composition), DEFAULT_FEED_T, DEFAULT_REGENERATOR_P, rich.molar_flow)
    stages = read_stages(res.info, comps)
    assert max(material_residuals(stages, comps, {0: [feed]})) < 1e-9
    assert max(equilibrium_residuals(package, stages)) < 1e-6


def test_stripping_physics(solved: Any) -> None:
    cls, thermo, _, res = solved
    info = res.info
    assert info["lean_co2_loading"] < 0.1 * info["rich_co2_loading"]
    assert info["lean_h2s_loading"] < 0.2 * info["rich_h2s_loading"]
    assert res.outlets["acid_gas_out"].vapor_fraction == pytest.approx(1.0)
    assert info["reboiler_T_K"] > res.outlets["acid_gas_out"].T
    _, more = _solve(cls, thermo, boilup_rate=cls.EXAMPLE_BOILUP + 10.0)
    assert more.info["lean_co2_loading"] < info["lean_co2_loading"]
    assert more.info["lean_h2s_loading"] < info["lean_h2s_loading"]
    assert more.info["reboiler_duty_W"] > info["reboiler_duty_W"]


def test_energy_split(solved: Any) -> None:
    _, _, rich, res = solved
    h_in = rich.molar_flow * rich.enthalpy
    h_out = sum(s.molar_flow * s.enthalpy for s in res.outlets.values())
    assert res.duty_W == pytest.approx(h_out - h_in, rel=1e-12)
    assert res.info["preheat_duty_W"] > 0.0 and res.info["reboiler_duty_W"] > 0.0
    split = res.info["basis_shift_W"] + res.info["preheat_duty_W"] + res.info["reboiler_duty_W"]
    assert split == pytest.approx(res.duty_W, rel=1e-6)


@pytest.mark.parametrize(
    ("params", "match"),
    [
        ({"boilup_rate": 20.0, "reflux": 1.0}, "unknown parameter"),
        ({"boilup_rate": 20.0, "n_stages": 1}, "n_stages"),
        ({}, "boilup_rate"),
    ],
)
def test_refusals(thermo: Thermo, params: dict[str, Any], match: str) -> None:
    feeds, _ = MdeaRegeneratorR2.example_case()
    rich = flash_feed(thermo, feeds["rich_amine_in"])
    with pytest.raises(AmineRegeneratorR2Error, match=match):
        MdeaRegeneratorR2().solve({"rich_amine_in": rich}, params, thermo)


@pytest.fixture(name="mea_low", scope="module")
def mea_low_fixture() -> tuple[StreamState, UnitResult, UnitResult]:
    """MEA at boilup 30 mol/s, where the cold heat-of-reaction ladder stalls
    (scale-0 NS, M = 5.9): the column solves it cold at the 60 mol/s anchor and
    walks the kettle tear down warm (specs._boilup_continuation). Measured
    32 s; the example (40 mol/s) is solved alongside for the trend. Both users
    share one xdist group so the fixture solves once."""
    thermo: Thermo = registry.create("thermo", "pr")
    rich, low = _solve(MeaRegeneratorR2, thermo, boilup_rate=30.0)
    _, example = _solve(MeaRegeneratorR2, thermo)
    return rich, low, example


@pytest.mark.xdist_group("mea_low")
def test_mea_low_boilup_converges(mea_low: tuple[StreamState, UnitResult, UnitResult]) -> None:
    """The continuation's answer is a converged column at exactly the requested boilup."""
    rich, res, _ = mea_low
    for cid, z in rich.composition.items():
        out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in res.outlets.values())
        assert out == pytest.approx(rich.molar_flow * z, rel=1e-9), cid
    package = registry.create("thermo", "amine_ke")
    comps = sorted(rich.composition)
    feed = package.flash_pt(dict(rich.composition), DEFAULT_FEED_T, DEFAULT_REGENERATOR_P, rich.molar_flow)
    stages = read_stages(res.info, comps)
    assert stages[-1].V == pytest.approx(30.0, rel=1e-12)
    assert max(material_residuals(stages, comps, {0: [feed]})) < 1e-9
    assert max(equilibrium_residuals(package, stages)) < 1e-6
    assert res.outlets["acid_gas_out"].vapor_fraction == pytest.approx(1.0)


@pytest.mark.xdist_group("mea_low")
def test_mea_low_boilup_strips_less(mea_low: tuple[StreamState, UnitResult, UnitResult]) -> None:
    """Less boilup strips less: leaner duty, richer lean solvent, a cooler kettle.

    Measured 30 mol/s: lean CO2 0.057 (above the 0.1 x rich = 0.040 bound the
    example meets - MEA needs about 36 mol/s for it), H2S 0.011, 1.35 MW.
    """
    _, low, example = mea_low
    assert example.info["lean_co2_loading"] < low.info["lean_co2_loading"] < low.info["rich_co2_loading"]
    assert example.info["lean_h2s_loading"] < low.info["lean_h2s_loading"] < low.info["rich_h2s_loading"]
    assert low.info["reboiler_duty_W"] < example.info["reboiler_duty_W"]
    assert low.info["reboiler_T_K"] < example.info["reboiler_T_K"]


def test_dea_low_boilup_acid_gas_is_vapour(thermo: Thermo) -> None:
    """DEA at 20 mol/s: the wet top vapour re-flashes as vapour and the duty follows the boilup.

    It used to re-flash as a false liquid (package sum z K = 0.93 at a
    CO2/amine of ~5700), 11 kJ/mol low, and the kettle duty read 703 kW against
    1.05 MW at 26 mol/s. Measured now 909 kW. The column converges, but lean H2S
    0.0345 misses the physics check's 0.2 x rich = 0.030 bound (example: 25 mol/s).
    """
    rich, res = _solve(DeaRegeneratorR2, thermo, boilup_rate=20.0)
    for cid, z in rich.composition.items():
        out = sum(s.molar_flow * s.composition.get(cid, 0.0) for s in res.outlets.values())
        assert out == pytest.approx(rich.molar_flow * z, rel=1e-9), cid
    assert res.outlets["acid_gas_out"].vapor_fraction == pytest.approx(1.0)
    _, example = _solve(DeaRegeneratorR2, thermo)
    q_low, q_ex = res.info["reboiler_duty_W"], example.info["reboiler_duty_W"]
    # Duty per extra mol/s of boilup sits near the latent heat of the wet
    # vapour (~40 kJ/mol), not the ~5x jump of a phase-flipped top stream.
    slope = (q_ex - q_low) / (DeaRegeneratorR2.EXAMPLE_BOILUP - 20.0)
    assert 1.0e4 < slope < 6.0e4
    assert res.info["lean_h2s_loading"] > example.info["lean_h2s_loading"]
