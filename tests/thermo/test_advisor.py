"""T-08 acceptance: the advisor's ranked recommendations.

- The slice (sour gas + TEG dehydration) ranks pr/srk first, with the water warning.
- The MDEA loop ranks the amine rows first.
- A methanol/water column at 1 bar prefers gamma-phi NRTL; cubics are demoted
  with the polarity reason.
- A slate a gamma-phi candidate has no binary parameters for gets the refusal
  warning and the demotion below every gamma-phi candidate that covers it.
- ``experimental`` rows never rank; the ranking is deterministic.
"""

from __future__ import annotations

from ngdesign.contracts import FeedSpec, Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.flowsheets import amine_loop
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.thermo.advisor import recommend


def _column(composition: dict[str, float], P_Pa: float = 1.0e5) -> Flowsheet:
    """A single-feed one-unit flowsheet at the given conditions (spec test cases)."""
    return Flowsheet(
        name="column",
        units=[UnitSpec(tag="T-201", kind="heater", params={})],
        streams=[
            StreamSpec(
                id="F-201",
                target=PortRef(unit="T-201", port="inlet"),
                feed=FeedSpec(T=320.0, P=P_Pa, molar_flow=100.0, composition=composition),
            ),
            StreamSpec(id="P-201", source=PortRef(unit="T-201", port="outlet")),
        ],
    )


_GAMMA_PREFIXES = ("nrtl", "uniquac", "wilson", "vanlaar", "margules", "regular_solution", "unifac")


def test_slice_ranks_pr_and_srk_first_with_water_warning() -> None:
    recs = recommend(slice_fs.build())
    assert [rec.id for rec in recs[:2]] == ["pr", "srk"]
    for rec in recs[:2]:
        assert any("water" in warning for warning in rec.warnings)


def test_mdea_loop_ranks_amine_rows_first() -> None:
    recs = recommend(amine_loop.build())
    assert {rec.id for rec in recs[:2]} == {"amine_ke", "amine_enrtl"}


def test_methanol_water_column_prefers_nrtl_and_demotes_cubics() -> None:
    recs = recommend(_column({"MeOH": 0.6, "H2O": 0.4}))
    assert recs[0].id.startswith("nrtl")
    first_cubic = next(rec for rec in recs if rec.id in ("pr", "srk", "pr78", "rk"))
    assert any("polar" in reason for reason in first_cubic.reasons)
    assert recs[0].score > first_cubic.score


def test_missing_pair_demotes_nrtl_below_candidates_that_cover_the_slate() -> None:
    # The ChemSep NRTL databank has no MDEA/MeOH pair (measured: the probe refuses).
    recs = recommend(_column({"MeOH": 0.6, "MDEA": 0.4}))
    by_id = {rec.id: rec for rec in recs}
    nrtl_rec = by_id["nrtl"]
    assert any("missing binary parameters" in w and "MDEA" in w for w in nrtl_rec.warnings)
    # Demotion is relative to the rows it competes with: every gamma-phi candidate
    # whose parameters cover the slate must outrank the demoted one.
    covered = [
        rec
        for rec in recs
        if rec.id.startswith(_GAMMA_PREFIXES)
        and not any("missing binary parameters" in w for w in rec.warnings)
    ]
    assert covered, "expected at least one gamma-phi candidate to cover the slate"
    assert min(rec.score for rec in covered) > nrtl_rec.score


def test_experimental_rows_never_rank() -> None:
    recs = recommend(slice_fs.build())
    assert all(rec.status != "experimental" for rec in recs)
    ids = {rec.id for rec in recs}
    assert "hoc_dimer" not in ids  # experimental dimerization row
    # T-15c: pc_saft was promoted to provisional and ranks like any other
    # provisional row; the experimental-never-rank property above still holds.
    assert "pc_saft" in ids


def test_virial_vapour_rows_rank_as_provisional() -> None:
    # T-03b: the HOC/Nothnagel virial-vapour rows left experimental status and
    # rank like any other provisional row (promotion to validated is T-15's
    # call once the #100 MeOH/H2O series is re-transcribed).
    recs = recommend(slice_fs.build())
    by_id = {rec.id: rec for rec in recs}
    assert by_id["nrtl_hoc"].status == "provisional"
    assert by_id["wilson_nothnagel"].status == "provisional"


def test_recommendation_is_deterministic() -> None:
    fs = slice_fs.build()
    assert recommend(fs) == recommend(fs)
