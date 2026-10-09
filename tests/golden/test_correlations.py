"""Golden-case harness for every correlation. LOCKED.

For each data/golden/<name>.yaml, the correlation plugin registered as <name> is called
with each case's inputs and must reproduce every expected value within tolerance_rel.
Unimplemented correlations are SKIPPED, not failed. Implementing one = un-skipping it.
"""

import math

import pytest
import yaml

from ngdesign import registry
from ngdesign.data import DATA_DIR

GOLDEN = sorted((DATA_DIR / "golden").glob("*.yaml"))
CASES = [
    (p.stem, i, case, yaml.safe_load(p.read_text())["tolerance_rel"])
    for p in GOLDEN
    for i, case in enumerate(yaml.safe_load(p.read_text())["cases"])
]


@pytest.mark.parametrize(("name", "idx", "case", "tol"), CASES, ids=[f"{c[0]}-{c[1]}" for c in CASES])
def test_golden(name: str, idx: int, case: dict, tol: float) -> None:
    if name not in registry.available("correlation"):
        pytest.skip(f"correlation {name!r} not implemented yet")
    fn = registry.create("correlation", name)
    got = fn(**case["inputs"])
    for key, want in case["expected"].items():
        assert key in got, f"{name}: missing output {key!r}"
        if isinstance(want, (int, float)) and not isinstance(want, bool):
            assert math.isclose(got[key], want, rel_tol=tol, abs_tol=1e-12), (
                f"{name} case {idx} {key}: got {got[key]}, want {want}"
            )
        else:
            assert got[key] == want, f"{name} case {idx} {key}: got {got[key]!r}, want {want!r}"
