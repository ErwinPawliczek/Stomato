"""Crude assay conversion and cutting (spec A-01).

Oracle policy: every test asserts a number printed in an open source or a
structural identity (roundtrip, conservation, continuity), never a value
computed only by the code under test.

Sources used (also cited at the constants in ``ngdesign.data.assay``):
- Riazi, M.R., *Characterization and Properties of Petroleum Fractions*,
  ASTM MNL50 (2005), section 3.2.2.1 p. 102: the D86->TBP worked example
  printed next to the API TDB 3A1.1 constant table (the pairing is also
  transcribed in the public "ASTM D86 to TBP (Riazi Method)" table, e.g.
  scribd.com/document/365519104): D86 36.5/54.1/76.9/101.5/131.0/171.0 C at
  0/10/30/50/70/90 vol% converts to TBP 14.1/33.4/68.9/101.6/135.1/180.5 C.
- ASTM D1160 annex A7 / API TDB 5A1.19 Maxwell-Bonnell constants as
  transcribed in public copies of the annex: at 10 mmHg the high-pressure
  branch gives A = 0.001956, and the transcribed worked arithmetic
  300 C @ 10 mmHg -> AET ~ 465 C (464.4 C at full precision). NOTE: the
  annex constants must be applied with pressure consistently; read in kPa
  the two branches are continuous at the 2 mmHg switch, while the mmHg
  low-branch transcription is 13 % discontinuous there - see the continuity
  test and the module docstring.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml

from ngdesign.contracts import Assay, DistillationCurve
from ngdesign.data import register_pseudo
from ngdesign.data.assay import (
    CompletedCurve,
    CutScheme,
    _all_bases,
    complete_curve,
    cut,
    cut_slate,
    d86_to_tbp_points,
    d1160_aet_c,
    d2887_to_tbp_points,
    effective_watson_k,
    sg_distribution,
    tbp_to_d86_points,
    to_tbp,
    watson_k_from_meabp,
)

# The printed worked example: D86 deg C at 0/10/30/50/70/90 vol%
_D86_C = [36.5, 54.1, 76.9, 101.5, 131.0, 171.0]
_D86_PERCENTS = [0.0, 10.0, 30.0, 50.0, 70.0, 90.0]
_TBP_PRINTED_C = [14.1, 33.4, 68.9, 101.6, 135.1, 180.5]


def _simple_tbp_curve() -> DistillationCurve:
    """A synthetic whole-crude-shaped TBP curve (LV%), 0..95 %."""
    pts = [(0, 293.15), (10, 320.15), (30, 400.15), (50, 480.15), (70, 580.15), (90, 700.15), (95, 760.15)]
    return DistillationCurve(kind="TBP", basis="LV%", points=[(p, t) for p, t in pts])


def _assay_from_yaml(name: str) -> Assay:
    path = Path(__file__).parents[2] / "data" / "assays" / name
    with open(path) as f:
        return Assay.model_validate(yaml.safe_load(f))


# ------------------------------------------------------------------ D86 <-> TBP


def test_d86_to_tbp_reproduces_riazi_worked_example() -> None:
    """Riazi 2005 (MNL50) section 3.2.2.1 p. 102, printed example to its rounding."""
    points = [(p, t + 273.15) for p, t in zip(_D86_PERCENTS, _D86_C, strict=False)]
    out = d86_to_tbp_points(points)
    assert [p for p, _ in out] == _D86_PERCENTS
    for (_, t_k), printed_c in zip(out, _TBP_PRINTED_C, strict=False):
        assert t_k - 273.15 == pytest.approx(printed_c, abs=1.0)


def test_tbp_to_d86_roundtrip() -> None:
    """Spec A-01: TBP -> D86 -> TBP round trip within 0.5 K."""
    original = [
        (10.0, 320.15),
        (30.0, 400.15),
        (50.0, 480.15),
        (70.0, 580.15),
        (90.0, 700.15),
        (95.0, 760.15),
    ]
    back = tbp_to_d86_points(d86_to_tbp_points(original))
    assert all(t2 == pytest.approx(t1, abs=0.5) for (_, t1), (_, t2) in zip(original, back, strict=False))


def test_d86_grid_points_stay_inside_coverage() -> None:
    """The pointwise conversion never extrapolates past the measured envelope."""
    short = [(10.0, 320.15), (30.0, 400.15), (50.0, 480.15)]
    out = dict(d86_to_tbp_points(short))
    assert set(out) == {10.0, 30.0, 50.0}  # grid points outside coverage are dropped
    with pytest.raises(ValueError, match="50 %"):
        d2887_to_tbp_points([(10.0, 560.15), (30.0, 610.15), (35.0, 630.15)])  # 50 % uncovered


# ------------------------------------------------------------------ D1160


def test_d1160_aet_reproduces_maxwell_bonnell_example() -> None:
    """ASTM D1160 annex A7 constants: A(10 mmHg) = 0.001956 and AET ~ 465 C example."""
    # 10 mmHg = 1.33322 kPa (the module takes kPa; the printed annex takes mmHg
    # and 5.994295 - 0.972546*log10(P_mmHg) == 5.143222 - 0.972546*log10(P_kPa))
    aet_c = d1160_aet_c(300.0, 10.0 * 0.133322)
    assert aet_c == pytest.approx(464.4, abs=1.5)
    # the atmospheric-pressure identity: AET(101.325 kPa) = the vapor temperature
    assert d1160_aet_c(400.0, 101.325) == pytest.approx(400.0, abs=0.3)
    assert d1160_aet_c(150.0, 101.325) == pytest.approx(150.0, abs=0.3)


def test_d1160_branches_continuous_at_switch() -> None:
    """Both constant branches agree at the 2 mmHg switch (module docstring note).

    The mmHg reading of the transcribed low branch is 13 % discontinuous at
    2 mmHg; the kPa reading implemented here is continuous to < 0.05 %.
    """
    switch = 2.0 * 0.133322
    t_vapor_c = 250.0
    high = d1160_aet_c(t_vapor_c, switch + 1e-6)
    low = d1160_aet_c(t_vapor_c, switch - 1e-6)
    assert high == pytest.approx(low, rel=5e-4)


def test_d1160_to_tbp_full_curve() -> None:
    """A 10 mmHg D1160 curve converts to a monotone completed TBP curve."""
    curve = DistillationCurve(
        kind="D1160",
        basis="LV%",
        points=[(0, 323.15), (10, 400.15), (30, 480.15), (50, 545.15), (70, 615.15), (90, 700.15)],
        P_kPa=10.0 * 0.133322,
    )
    completed = to_tbp(curve)
    temps = [t for _, t in completed.points]
    assert all(t2 > t1 for t1, t2 in zip(temps, temps[1:], strict=False))
    assert completed.points[0][0] == 0.0 and completed.points[-1][0] == 100.0


# ------------------------------------------------------------------ D2887


def test_d2887_tbp50_equals_sd50_and_monotone() -> None:
    """API 3A3.1 anchors TBP(50%) = SD(50%); intervals expand outward monotonically."""
    sd = [(10, 560.15), (30, 610.15), (50, 650.15), (70, 700.15), (90, 760.15)]
    out = dict(d2887_to_tbp_points([(p, t) for p, t in sd]))
    assert out[50.0] == pytest.approx(650.15, abs=1e-9)
    temps = [t for _, t in sorted(out.items())]
    assert all(t2 > t1 for t1, t2 in zip(temps, temps[1:], strict=False))
    # simulated distillation is narrower than true TBP: endpoints spread outward
    assert out[10.0] < 560.15 and out[90.0] > 760.15
    assert out[30.0] < 610.15 and out[70.0] > 700.15


# ------------------------------------------------------------------ completion


def test_completion_endpoints_inside_curve_bounds() -> None:
    """The fitted 0/100 % endpoints bracket the measured range (Riazi model)."""
    completed = complete_curve(
        [(10.0, 355.15), (30.0, 459.15), (50.0, 554.15), (70.0, 655.15), (90.0, 825.15)]
    )
    assert completed.points[0][1] < 355.15
    assert completed.points[-1][1] > 825.15
    # the piecewise-linear interpolation passes through the measured points
    for percent, temp in [(30.0, 459.15), (50.0, 554.15), (90.0, 825.15)]:
        found = next(t for p, t in completed.points if p == percent)
        assert found == pytest.approx(temp, abs=1e-9)


def test_completion_requires_coverage() -> None:
    with pytest.raises(ValueError, match="10 % and 90 %"):
        complete_curve([(20.0, 400.15), (50.0, 500.15), (80.0, 620.15)])


# ------------------------------------------------------------------ gravity


def test_watson_k_identity_on_cut() -> None:
    """One constant Watson K across all cuts; sg(T) = (1.8 T)^(1/3)/K per cut."""
    curve = _simple_tbp_curve()
    bulk_sg = 0.72
    k_est = effective_watson_k(curve, bulk_sg)
    slate = cut_slate(curve, bulk_sg, scheme=CutScheme.equal_count(5))
    ks = [watson_k_from_meabp(d.sg, d.Tb) for d in slate.pseudos]
    assert all(k == pytest.approx(ks[0], rel=1e-12) for k in ks)  # uniform constant-K model
    assert ks[0] == pytest.approx(k_est, rel=1e-2)  # VABP estimate within the Jensen offset


def test_sg_distribution_matches_watson_definition() -> None:
    temps = [400.0, 500.0, 600.0]
    k_w = 11.8
    for t, sg in zip(temps, sg_distribution(temps, k_w), strict=False):
        assert (1.8 * t) ** (1.0 / 3.0) / sg == pytest.approx(k_w, rel=1e-12)


def test_cut_slate_bulk_sg_recombines() -> None:
    """Spec A-01 (stronger than its 0.5 API gate): exact volume recombination."""
    curve = _simple_tbp_curve()
    bulk_sg = 0.72
    slate = cut_slate(curve, bulk_sg, scheme=CutScheme.equal_count(8))
    blended_sg = sum(f * d.sg for cid, f in slate.volume.items() for d in slate.pseudos if d.id == cid)
    api_in = 141.5 / bulk_sg - 131.5
    api_out = 141.5 / blended_sg - 131.5
    assert api_out == pytest.approx(api_in, abs=0.5)  # the spec gate
    assert blended_sg == pytest.approx(bulk_sg, rel=1e-9)  # the volume-average anchor


# ------------------------------------------------------------------ cutting


def test_cutting_conserves_fractions() -> None:
    """Spec A-01: mole/mass/volume each sum to 1 within 1e-12."""
    curve = _simple_tbp_curve()
    slate = cut_slate(
        curve, 0.72, light_ends={"nC4": 0.02}, light_ends_basis="volume", scheme=CutScheme.equal_count(6)
    )
    for basis in ("mole", "mass", "volume"):
        assert sum(getattr(slate, basis).values()) == pytest.approx(1.0, abs=1e-12)
    assert set(slate.mole) == set(slate.mass) == set(slate.volume)
    assert slate.light_end_ids == ("nC4",)
    assert slate.volume["nC4"] == pytest.approx(0.02, rel=1e-9)  # declared on the curve basis


def test_pseudo_ids_deterministic_and_props_inside_cut() -> None:
    """Spec A-01: ids are <assay id>_NBP<Tb>; Tb ascends; sg rises with Tb."""
    curve = _simple_tbp_curve()
    slate = cut_slate(curve, 0.72, assay_id="refinery", scheme=CutScheme.equal_count(5))
    assert all(d.id == f"refinery_NBP{d.Tb:.0f}" for d in slate.pseudos)
    tbs = [d.Tb for d in slate.pseudos]
    sgs = [d.sg for d in slate.pseudos]
    assert all(t2 > t1 for t1, t2 in zip(tbs, tbs[1:], strict=False))
    assert all(s2 > s1 for s1, s2 in zip(sgs, sgs[1:], strict=False))
    assert all(0.5 < sg < 1.5 for sg in sgs)


def test_basis_conversion_mass_curve() -> None:
    """A wt% curve converts through sg/mw: volume = mass/sg, mole = mass/mw."""
    curve = DistillationCurve(kind="TBP", basis="wt%", points=_simple_tbp_curve().points)
    slate = cut_slate(curve, 0.72, scheme=CutScheme.equal_count(4))
    for basis in ("mole", "mass", "volume"):
        assert sum(getattr(slate, basis).values()) == pytest.approx(1.0, abs=1e-12)
    from ngdesign.data import _riazi_daubert_mw

    scale_sg = sum(v * d.sg for d in slate.pseudos for v in [slate.volume[d.id]])
    scale_mw = sum(slate.mole[d.id] * _riazi_daubert_mw(d.Tb, d.sg) for d in slate.pseudos)
    for d in slate.pseudos:
        m, v, x = slate.mass[d.id], slate.volume[d.id], slate.mole[d.id]
        assert v * d.sg / scale_sg == pytest.approx(m, rel=1e-9)  # m proportional to v*sg
        assert x * _riazi_daubert_mw(d.Tb, d.sg) / scale_mw == pytest.approx(m, rel=1e-9)


def test_light_ends_mismatched_basis_rejected() -> None:
    curve = _simple_tbp_curve()
    with pytest.raises(ValueError, match="'volume' for an LV%"):
        cut_slate(curve, 0.72, light_ends={"nC4": 0.02}, light_ends_basis="mass")
    with pytest.raises(ValueError, match="light_ends_basis"):
        cut_slate(curve, 0.72, light_ends={"nC4": 0.02})


# ------------------------------------------------------------------ example assay + flash bridge


@pytest.fixture(scope="module")
def example_slate() -> object:
    """The Bagajewicz & Ji 2001 light crude cut with its light ends."""
    assay = _assay_from_yaml("bagajewicz_ji_2001_light.yaml")
    return cut(assay, CutScheme.equal_count(10))


def test_example_assay_cuts_to_valid_slate(example_slate: object) -> None:
    for basis in ("mole", "mass", "volume"):
        assert sum(getattr(example_slate, basis).values()) == pytest.approx(1.0, abs=1e-12)
    ids = set(example_slate.mole)
    assert {"C2", "C3", "iC4", "nC4", "iC5", "nC5"} <= ids
    assert all(example_slate.volume[cid] > 0.0 for cid in ids)


def test_example_assay_slate_flashes_with_pr(example_slate: object) -> None:
    """Spec A-01 bridge: the slate feeds a PR PT flash (one run, no refusal)."""
    from ngdesign import registry
    from ngdesign.contracts.plugins import Thermo

    slate = example_slate
    for definition in slate.pseudos:
        register_pseudo(definition.id, definition.name, definition.Tb, definition.sg)
    z = slate.mole
    thermo: Thermo = registry.create("thermo", "pr")
    state = thermo.flash_pt(z, 600.0, 2.0e5, 100.0)  # crude-column flash-zone-ish
    assert state.phases
    assert math.isclose(sum(p.mole_fraction for p in state.phases), 1.0, abs_tol=1e-9)
    for cid in z:
        back = sum(p.mole_fraction * p.composition[cid] for p in state.phases)
        assert back == pytest.approx(z[cid], abs=1e-6)


# ------------------------------------------------------------------ contract records


def test_contract_validators() -> None:
    with pytest.raises(ValueError, match="P_kPa"):
        DistillationCurve(kind="D1160", basis="LV%", points=[(0, 300.0), (10, 350.0), (50, 450.0)])
    with pytest.raises(ValueError, match="strictly increasing"):
        DistillationCurve(kind="TBP", basis="LV%", points=[(0, 300.0), (10, 350.0), (50, 350.0)])
    with pytest.raises(ValueError, match="exactly one"):
        Assay(id="x", curve=_simple_tbp_curve(), sg=0.72, api_gravity=36.0, provenance={"curve": "test"})


def test_completed_curve_type_roundtrip() -> None:
    """to_tbp passes a TBP curve through completed and fit-annotated."""
    completed: CompletedCurve = to_tbp(_simple_tbp_curve())
    assert completed.fit_b > 0.0 and completed.fit_a > 0.0
    percents = [p for p, _ in completed.points]
    assert percents == sorted(percents)
    assert percents[0] == 0.0 and percents[-1] == 100.0


def test_all_bases_normalizes() -> None:
    volume, mass, mole = _all_bases([0.5, 0.3, 0.2], "LV%", [0.7, 0.75, 0.8], [90.0, 110.0, 140.0])
    for values in (volume, mass, mole):
        assert sum(values) == pytest.approx(1.0, abs=1e-12)
    with pytest.raises(ValueError, match="unsupported curve basis"):
        _all_bases([1.0], "mol%", [0.7], [90.0])
