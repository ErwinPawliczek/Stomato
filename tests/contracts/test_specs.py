"""Design-spec contract validation (spec P2-01, AG-01)."""

import pytest
from pydantic import ValidationError

from ngdesign.contracts import Flowsheet
from ngdesign.contracts.specs import DesignSpec
from ngdesign.flowsheets import slice as slice_fs


def _spec(**kw: object) -> DesignSpec:
    base: dict[str, object] = {
        "id": "DS-001",
        "target": "S-003.T",
        "value": 390.0,
        "manipulated": "K-101.params.P_out",
        "lower": 6e6,
        "upper": 14e6,
    }
    return DesignSpec(**{**base, **kw})


def _fs(*specs: DesignSpec) -> Flowsheet:
    fs = slice_fs.build()
    return Flowsheet(**{**fs.model_dump(), "design_specs": [s.model_dump() for s in specs]})


def test_valid_specs_build() -> None:
    fs = _fs(_spec())
    assert fs.design_specs[0].id == "DS-001"


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate design spec ids"):
        _fs(_spec(), _spec())


def test_lower_not_below_upper_rejected() -> None:
    with pytest.raises(ValidationError):
        _spec(lower=14e6, upper=6e6)
    with pytest.raises(ValidationError):
        _spec(lower=8e6, upper=8e6)


def test_unknown_head_rejected() -> None:
    with pytest.raises(ValidationError, match="neither a stream id nor a unit tag"):
        _fs(_spec(target="S-999.T"))
    with pytest.raises(ValidationError, match="neither a stream id nor a unit tag"):
        _fs(_spec(manipulated="X-999.params.P_out"))


def test_unparseable_target_rejected() -> None:
    # S-003 exists, but 'zzz' is not a read field.
    with pytest.raises(ValidationError, match="stream fields"):
        _fs(_spec(target="S-003.zzz"))


def test_unparseable_manipulated_rejected() -> None:
    # K-101 exists, but unit writes look like '<tag>.params.<key>'.
    with pytest.raises(ValidationError, match="unit writes look like"):
        _fs(_spec(manipulated="K-101.setpoint"))


def test_write_on_non_feed_stream_rejected() -> None:
    # S-003 has a source, so it has no feed spec to write.
    with pytest.raises(ValidationError, match="has no feed spec"):
        _fs(_spec(manipulated="S-003.feed.T"))
