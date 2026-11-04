"""The validation harness's `solubility` case type, driven on the ideal_solid row.

scripts/validate_properties.py compares expected {solute: x_sat} at T against a
package's solubility(cid, T) surface (added 2026-11-03 so the special-family SLE
row is harness-evaluable). The cases here are built in memory from the
IUPAC-NIST Solubility Database points the row's unit tests already cite; the
same points are bound as reference cases in data/validation/special/cases.yaml
(2026-11-04), which tests/validation runs.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@cache
def _harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "validate_properties_solubility", REPO_ROOT / "scripts" / "validate_properties.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass processing resolves annotations through sys.modules[cls.__module__]
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _case(vp: Any, case_id: str, solute: str, T: float, x: float) -> Any:
    return vp.Case(
        id=case_id,
        package="ideal_solid",
        components=[solute, "benzene"],
        z={solute: x, "benzene": 1.0 - x},
        source="IUPAC-NIST Solubility Database (see tests/thermo/test_special.py)",
        expected={"solubility": {solute: x}},
        T=T,
        section="binary_cases",
    )


def test_solubility_rows_pass_inside_the_band() -> None:
    """Naphthalene/benzene 298.15 K (x 0.292, sysID 59_123): +3.4 % inside the 5 % band."""
    vp = _harness()
    rows = vp.evaluate_case(_case(vp, "sle-naph-298", "naphthalene", 298.15, 0.292), "ideal_solid")
    assert len(rows) == 1
    row = rows[0]
    assert row.property == "solubility"
    assert row.passed
    assert row.rel_err == pytest.approx(0.0335, abs=0.002)


def test_solubility_row_fails_outside_the_band() -> None:
    """Anthracene/benzene 298.15 K (x 0.00713, sysID 58_57): the +32 % ideal miss stays red."""
    vp = _harness()
    (row,) = vp.evaluate_case(_case(vp, "sle-anth-298", "anthracene", 298.15, 0.00713), "ideal_solid")
    assert not row.passed
    assert 0.25 < row.rel_err < 0.45


def test_package_without_the_surface_yields_a_failing_row() -> None:
    """A VLE package has no solubility(cid, T): the comparison fails, never skips."""
    vp = _harness()
    (row,) = vp.evaluate_case(_case(vp, "sle-naph-pr", "naphthalene", 298.15, 0.292), "pr")
    assert row.got is None
    assert not row.passed


def test_tolerance_policy_declares_solubility() -> None:
    vp = _harness()
    assert vp.TOLERANCE_POLICY["solubility"] == 0.05


def test_advisor_sinks_the_sle_row_below_every_flash_package() -> None:
    """ideal_solid ranks (validated since 2026-11-04) but claims no vapour: last, with the warning."""
    from ngdesign.flowsheets import slice as slice_fs
    from ngdesign.thermo.advisor import recommend

    recs = recommend(slice_fs.build())
    by_id = {rec.id: rec for rec in recs}
    sle = by_id["ideal_solid"]
    assert sle.status == "validated"
    assert any("not a vapour-liquid flash package" in w for w in sle.warnings)
    assert sle.score < min(rec.score for rec in recs if rec.id != "ideal_solid")
