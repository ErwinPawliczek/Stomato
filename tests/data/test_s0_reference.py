"""S0 reference consistency checks (spec S0-D).

Every expected value asserted here is a number printed in the cited sources
(Bagajewicz design-paper series, author-hosted PDFs); the tests only check
the printed numbers against each other (sums, orderings, printed ranges) —
never a value computed by engine code. Transcription was verified against
rendered images of the printed pages; see
docs/validation/s0-crude-reference-findings.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REFERENCE_PATH = _REPO_ROOT / "data" / "validation_units" / "refining" / "s0_reference.yaml"
_ASSAY_PATH = _REPO_ROOT / "data" / "assays" / "bagajewicz_ji_2001_light.yaml"

# Printed product rates are rounded to 0.1-1 m3/h; the paper's own column
# sums deviate from the 795 m3/h feed by at most 1.0 m3/h (one-PA design:
# 796.0). 1.5 m3/h is the smallest round bound covering that printed rounding.
_RATE_SUM_TOL_M3_H = 1.5

_MMHG_PER_PSIA = 51.7149  # unit identity, not a source constant


def _load_reference() -> dict[str, Any]:
    with _REFERENCE_PATH.open() as f:
        return cast(dict[str, Any], yaml.safe_load(f))


def _load_assay() -> dict[str, Any]:
    with _ASSAY_PATH.open() as f:
        return cast(dict[str, Any], yaml.safe_load(f))


@pytest.mark.parametrize(
    ("design", "expected_sum"),
    [
        ("one_pumparound", 796.0),
        ("two_pumparound", 795.3),
        ("three_pumparound", 795.55),
    ],
)
def test_atmospheric_rates_sum_to_feed(design: str, expected_sum: float) -> None:
    ref = _load_reference()
    designs = ref["atmospheric_column"]["designs"]
    rates = cast(dict[str, float], designs[design]["product_rates_m3_h"])
    assert sum(rates.values()) == pytest.approx(expected_sum, abs=1e-9)
    feed = float(ref["feed"]["throughput_m3_h"])
    assert abs(sum(rates.values()) - feed) <= _RATE_SUM_TOL_M3_H


def test_complete_plant_rates_sum_to_feed() -> None:
    ref = _load_reference()
    plant = ref["complete_plant"]
    rates = cast(dict[str, float], plant["product_rates_m3_h"])
    # Printed internal row: total distillates.
    distillates = sum(rates[k] for k in ("naphtha", "kerosene", "diesel", "gas_oil", "LVGO", "HVGO"))
    assert distillates == pytest.approx(float(plant["total_distillates_m3_h"]), abs=0.01)
    feed = float(ref["feed"]["throughput_m3_h"])
    assert abs(sum(rates.values()) - feed) <= _RATE_SUM_TOL_M3_H


def test_vacuum_products_balance_their_feed() -> None:
    ref = _load_reference()
    rates = cast(dict[str, float], ref["complete_plant"]["product_rates_m3_h"])
    vacuum_feed = rates["LVGO"] + rates["HVGO"] + rates["vacuum_overhead"] + rates["vacuum_residue"]
    atmospheric_distillates = sum(rates[k] for k in ("naphtha", "kerosene", "diesel", "gas_oil"))
    vacuum_feed_from_atm = float(ref["feed"]["throughput_m3_h"]) - atmospheric_distillates
    # Both sides are sums of printed values rounded to 0.01-0.1 m3/h; the
    # printed rounding alone can account for ~0.3 m3/h here (vacuum products
    # 210.082 vs feed-minus-distillates 209.78). The printed-rounding bound
    # is the same one the feed-sum check uses.
    assert vacuum_feed == pytest.approx(vacuum_feed_from_atm, abs=_RATE_SUM_TOL_M3_H)


def test_d86_95_points_ascending() -> None:
    ref = _load_reference()
    specs = cast(dict[str, Any], ref["atmospheric_column"]["product_specs"]["d86_95pct_C"])
    vacuum = ref["vacuum_column"]
    naphtha = float(specs["naphtha"])
    kerosene = float(specs["kerosene"])
    diesel = float(specs["diesel"])
    # The gas-oil spec prints a range ("377-410 C"): its lower bound must
    # still exceed the diesel point and not exceed the vacuum LVGO point.
    gas_oil_low = float(str(specs["gas_oil"]).split("-")[0])
    lvgo = float(vacuum["lvgo_d86_95pct_C"])
    assert naphtha < kerosene < diesel < gas_oil_low <= lvgo


@pytest.mark.parametrize("design", ["one_pumparound", "two_pumparound", "three_pumparound"])
def test_withdrawal_and_flash_temps_ordered(design: str) -> None:
    ref = _load_reference()
    d = ref["atmospheric_column"]["designs"][design]
    temps = cast(dict[str, float], d["withdrawal_temps_C"])
    flash = float(d["flash_zone_temp_C"])
    assert temps["kerosene"] < temps["diesel"] < temps["gas_oil"] < temps["residue"] < flash
    pumparounds = cast(dict[str, Any], d["pumparounds"])
    draw_temps = [float(cast(list[Any], pumparounds[pa]["temp_range_C"])[0]) for pa in pumparounds]
    assert draw_temps == sorted(draw_temps)
    assert all(t < flash for t in draw_temps)


def test_gaps_meet_their_printed_kn_dk_specs() -> None:
    # The paper's final scheme meets the kerosene-naphtha and
    # diesel-kerosene gap specs exactly at their bounds ([P1] Table 9 vs
    # Table 4). The gasoil-diesel gap is deliberately NOT asserted against
    # its printed spec range: the source's own achieved values (0.91 / -2.0 /
    # -2.9 C) fall outside the printed spec range (-5.6 to -11 C) — recorded
    # as printed in the YAML, discrepancy is the source's.
    ref = _load_reference()
    gaps = cast(dict[str, float], ref["atmospheric_column"]["designs"]["three_pumparound"]["gaps_C"])
    assert gaps["kerosene_naphtha_5_95"] >= 16.7
    assert gaps["diesel_kerosene_5_95"] >= 0.0


def test_vacuum_flashzone_pressure_inside_printed_band() -> None:
    # [V1] Table 1 prints 1.90 psia; [V1] text prints the control band
    # 25-100 mmHg. Two printed items of the same source must agree.
    ref = _load_reference()
    psia = float(ref["vacuum_column"]["flash_zone_pressure_psia"])
    mmhg = psia * _MMHG_PER_PSIA
    assert 25.0 <= mmhg <= 100.0


def test_energy_consumption_falls_as_pumparounds_are_added() -> None:
    # Printed trend, [P1] Table 6 then Table 9.
    ref = _load_reference()
    designs = ref["atmospheric_column"]["designs"]
    e_one = float(designs["one_pumparound"]["energy_consumption_MW"])
    e_two = float(designs["two_pumparound"]["energy_consumption_MW"])
    e_three = float(designs["three_pumparound"]["energy_consumption_MW"])
    assert e_one > e_two > e_three


def test_cross_source_feed_identity() -> None:
    # [P1] Table 1 and [V1] Table A.1 print the same feedstock; the assay
    # file's sg is derived from the printed 36.0 deg API / 845 kg/m3.
    ref = _load_reference()
    assay = _load_assay()
    assert assay["id"] == ref["feed"]["assay"]
    assert "795" in str(ref["feed"]["provenance"])
    assert assay["curve"]["kind"] == "TBP"


def test_not_recorded_names_the_atmospheric_pressure_gap() -> None:
    ref = _load_reference()
    not_recorded = " ".join(str(item) for item in ref["not_recorded"])
    assert "flash-zone pressure" in not_recorded
