"""P0-04 identity oracle: the refactored pr/srk/pr78 produce byte-identical streams.

Expected StreamStates were generated ONCE from pre-change main (commit 3ecd285,
`scripts/gen_cubic_fixtures.py` run on a clean checkout before the refactor —
uv run python scripts/gen_cubic_fixtures.py) and committed as
tests/thermo/fixtures/cubic_identity.yaml. Six states span the slice feed
(two-phase, dense gas, liquid, near-critical, water-rich, sour); the dense-gas
case is single-phase and exercises the stability re-check path.
"""

from __future__ import annotations

import copy
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from ngdesign import registry

FIXTURE = Path(__file__).parent / "fixtures" / "cubic_identity.yaml"
REL_TOL = 1e-12


@cache
def _fixture() -> dict[str, Any]:
    with open(FIXTURE) as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def _compare(actual: Any, expected: Any, path: str) -> None:
    """Recursive comparison: floats to 1e-12 relative, everything else exactly."""
    if isinstance(expected, dict):
        assert isinstance(actual, dict), path
        assert set(actual) == set(expected), f"{path}: key sets differ"
        for key in expected:
            _compare(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), path
        assert len(actual) == len(expected), f"{path}: length differs"
        for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _compare(a, e, f"{path}[{i}]")
    elif isinstance(expected, float):
        assert actual == pytest.approx(expected, rel=REL_TOL), f"{path}: {actual} != {expected}"
    else:
        assert actual == expected, f"{path}: {actual!r} != {expected!r}"


@pytest.mark.parametrize(
    "state_name", ["two_phase", "dense_gas", "liquid", "near_critical", "water_rich", "sour"]
)
@pytest.mark.parametrize("package", ["pr", "srk", "pr78"])
def test_cubic_identity(package: str, state_name: str) -> None:
    """StreamState after the P0-04 refactor equals the pre-change one to 1e-12."""
    case = _fixture()["packages"][package][state_name]
    thermo = registry.create("thermo", package)
    molar_flow = _fixture()["molar_flow"]

    state = thermo.flash_pt(dict(case["z"]), float(case["T"]), float(case["P"]), float(molar_flow))

    assert len(state.phases) == case["n_phases"], f"{package}/{state_name}: phase count changed"
    _compare(copy.deepcopy(state.model_dump(mode="json")), case["expected"], f"{package}.{state_name}")
