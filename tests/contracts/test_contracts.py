"""Contract sanity: samples validate, validators reject bad data. LOCKED."""

import pytest
from pydantic import ValidationError

from ngdesign.contracts import FeedSpec, Flowsheet, LineEnd, PidLine, StreamSpec, UnitSpec
from ngdesign.flowsheets import samples
from ngdesign.flowsheets import slice as slice_fs


def test_slice_flowsheet_valid():
    fs = slice_fs.build()
    assert len(fs.units) == 6
    assert {s.id for s in fs.streams if s.source is None} == {"S-001", "S-006"}


def test_samples_valid():
    pid = samples.sample_pid()
    assert {e.tag for e in pid.equipment} == {"V-101", "P-101", "K-101"}
    line = samples.sample_routed_line()
    assert line.components[0].kind.value == "flange_weld_neck"


def test_composition_must_sum_to_one():
    with pytest.raises(ValidationError):
        FeedSpec(T=300, P=1e6, molar_flow=1, composition={"C1": 0.5})


def test_unknown_unit_reference_rejected():
    with pytest.raises(ValidationError):
        Flowsheet(
            name="x",
            units=[UnitSpec(tag="V-101", kind="k")],
            streams=[StreamSpec(id="S1", source=None, target=None)],
        )


def test_bad_line_number_rejected():
    with pytest.raises(ValidationError):
        PidLine(
            number="6in-PG-1",
            nps_in=6,
            fluid_code="PG",
            pipe_class="B1",
            design_pressure_Pa=1e6,
            design_temperature_K=300,
            start=LineEnd(boundary="A"),
            end=LineEnd(boundary="B"),
        )
