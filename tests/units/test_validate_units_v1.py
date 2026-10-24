"""Spec U-01: the unit harness's V1 worked-case runner and reactive V0 balances.

``scripts/validate_units.py`` owns its checks outside pytest (like the thermo
audit); these tests drive its functions on synthetic cases so the runner's
pass/miss/assessed/finding rules are pinned before round-1 units add real ones.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from ngdesign import registry
from ngdesign.units.catalogue import UnitRow, load_rows, register_all

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_units.py"


@pytest.fixture(scope="module")
def vu() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_units_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    registry.discover()
    register_all()
    return module


@pytest.fixture(scope="module")
def rows() -> dict[str, UnitRow]:
    return load_rows()


def _measured_mixer_T(vu: ModuleType, rows: dict[str, UnitRow]) -> float:
    solved = vu.solve_level(rows["mixer"], "R0", vu._thermo())
    return float(solved.outlets["outlet"].T)


def _run(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: Any, cases: list[dict[str, Any]]
) -> Any:
    family = tmp_path / "logical"
    family.mkdir()
    (family / "cases.yaml").write_text(yaml.safe_dump(cases))
    monkeypatch.setattr(vu, "VALIDATION_DIR", tmp_path)
    return vu.run_v1(rows)


def _case(value: float, **extra: Any) -> dict[str, Any]:
    case: dict[str, Any] = {
        "id": "V-mixer-synthetic",
        "unit": "mixer",
        "level": "R0",
        "source": "synthetic: the harness's own measurement",
        "expected": [{"quantity": "outlet.outlet.T", "value": value, "tol_abs": 1e-6}],
    }
    case.update(extra)
    return case


def test_v1_case_matching_its_expected_value_passes(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    T = _measured_mixer_T(vu, rows)
    results, findings = _run(vu, rows, tmp_path, monkeypatch, [_case(T)])
    assert findings == []
    assert len(results) == 1 and results[0].passed


def test_v1_unassessed_miss_is_a_finding(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    T = _measured_mixer_T(vu, rows)
    results, findings = _run(vu, rows, tmp_path, monkeypatch, [_case(T + 1.0)])
    assert not results[0].passed
    assert [f.case for f in findings] == ["V-mixer-synthetic"]
    assert "unassessed miss" in findings[0].detail


def test_v1_assessed_miss_is_recorded_not_a_finding(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    T = _measured_mixer_T(vu, rows)
    results, findings = _run(
        vu, rows, tmp_path, monkeypatch, [_case(T + 1.0, assessed="measured +1 K; explained")]
    )
    assert findings == []
    assert not results[0].passed
    page = vu.unit_page(rows["mixer"], results)
    assert "assessed miss" in page and "measured +1 K; explained" in page


def test_v1_case_without_source_or_expected_is_a_finding(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(0.0, source="")
    case["expected"] = []
    _results, findings = _run(vu, rows, tmp_path, monkeypatch, [case])
    details = " | ".join(f.detail for f in findings)
    assert "no source citation" in details and "no expected values" in details


def test_v1_bad_quantity_path_is_an_error_not_a_pass(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(0.0)
    case["expected"] = [{"quantity": "outlet.nope.T", "value": 0.0, "tol_abs": 1.0}]
    results, findings = _run(vu, rows, tmp_path, monkeypatch, [case])
    assert results[0].error is not None and "nope" in results[0].error
    assert findings


def test_v1_params_overlay_and_feeds_override(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case feeds replace the example feeds: a single 300 K feed mixes to 300 K."""
    feed = {"T": 300.0, "P": 2.0e6, "molar_flow": 5.0, "composition": {"C1": 1.0}}
    case = _case(300.0, feeds={"inlet_1": feed})
    case["expected"] = [{"quantity": "outlet.outlet.T", "value": 300.0, "tol_abs": 1e-6}]
    results, findings = _run(vu, rows, tmp_path, monkeypatch, [case])
    assert findings == [], findings
    assert results[0].passed


def test_level_validation_id_without_case_is_a_finding(
    vu: ModuleType, rows: dict[str, UnitRow], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mixer = rows["mixer"]
    level = mixer.levels["R0"].model_copy(update={"validation": ("V-missing",)})
    patched = {**rows, "mixer": mixer.model_copy(update={"levels": {"R0": level}})}
    _results, findings = _run(vu, patched, tmp_path, monkeypatch, [])
    assert [(f.case, f.unit) for f in findings] == [("V-missing", "mixer")]


def test_mass_elements_balance_checks_mass_and_atoms(vu: ModuleType, rows: dict[str, UnitRow]) -> None:
    """2 H2 + O2 -> 2 H2O closes on mass and atoms though moles fall 3 -> 2."""
    thermo = vu._thermo()
    row = rows["mixer"].model_copy(update={"balance": "mass_elements"})
    feed = thermo.flash_pt({"H2": 2.0 / 3.0, "O2": 1.0 / 3.0}, 1200.0, 1.0e5, 3.0)
    product = thermo.flash_pt({"H2O": 1.0}, 1200.0, 1.0e5, 2.0)
    solved = vu.Solved(row, "R0", {"inlet_1": feed}, {"outlet": product}, 0.0, 0.0, {})
    assert vu.check_material(solved) is None
    short = thermo.flash_pt({"H2O": 1.0}, 1200.0, 1.0e5, 1.9)
    bad = vu.Solved(row, "R0", {"inlet_1": feed}, {"outlet": short}, 0.0, 0.0, {})
    assert vu.check_material(bad) is not None
    molar = vu.Solved(rows["mixer"], "R0", {"inlet_1": feed}, {"outlet": product}, 0.0, 0.0, {})
    assert "mol/s in" in str(vu.check_material(molar))
