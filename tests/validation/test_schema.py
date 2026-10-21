"""Schema checks for the P1-05 validation fixtures and cases file."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validate_properties import ABSOLUTE_ERROR_PROPERTIES, TOLERANCE_POLICY, _load_cases

REPO_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = REPO_ROOT / "data" / "validation" / "cases.yaml"


def _raw() -> dict[str, object]:
    raw = yaml.safe_load(CASES_PATH.read_text())
    assert isinstance(raw, dict)
    return raw


def test_coolprop_version_recorded() -> None:
    meta = _raw().get("meta") or {}
    assert isinstance(meta, dict)
    version = meta.get("coolprop_version")
    assert isinstance(version, str) and version.count(".") >= 1, (
        "meta.coolprop_version must record the CoolProp version used for pure_cases"
    )


def test_every_case_has_source_and_feed() -> None:
    for case in _load_cases():
        assert case.source, f"{case.id}: missing source"
        assert case.z, f"{case.id}: missing z"
        assert abs(sum(case.z.values()) - 1.0) < 1e-6, f"{case.id}: z does not sum to 1"
        assert case.expected, f"{case.id}: no expected values (run --regen-coolprop)"
        assert case.components, f"{case.id}: missing components"


def test_literature_sources_cite_origin_and_retrieval_date() -> None:
    for case in _load_cases():
        if case.source.startswith("coolprop:"):
            continue
        lowered = case.source.lower()
        assert "retrieved" in lowered or "read" in lowered, (
            f"{case.id}: source lacks a retrieval date: {case.source}"
        )
        assert any(
            k in lowered for k in ("journal", "doi", "series", "fig", "table", "p.", "pp.", "symposium")
        ), f"{case.id}: source lacks a publication locator: {case.source}"


def test_all_expected_properties_are_evaluated_by_the_harness() -> None:
    for case in _load_cases():
        unevaluated = set(case.expected) - set(TOLERANCE_POLICY)
        assert not unevaluated, (
            f"{case.id}: expected properties the harness cannot evaluate: {sorted(unevaluated)}"
        )


def test_all_overrides_are_declared_in_policy() -> None:
    for case in _load_cases():
        undeclared = set(case.tolerance) - set(TOLERANCE_POLICY)
        assert not undeclared, f"{case.id}: tolerance for unknown property {sorted(undeclared)}"


def test_composition_tolerances_are_absolute() -> None:
    for prop in ABSOLUTE_ERROR_PROPERTIES:
        assert TOLERANCE_POLICY[prop] < 0.5, f"{prop}: composition tolerance must be absolute (mole fraction)"


def test_all_case_packages_are_registered_names() -> None:
    for case in _load_cases():
        if case.package == "all":
            continue
        assert case.package in {"pr", "srk", "pr78", "nrtl", "pc_saft", "cpa_srk"}, (
            f"{case.id}: unexpected package {case.package}"
        )


def test_results_json_row_schema_when_present() -> None:
    results = REPO_ROOT / "data" / "validation" / "results.json"
    if not results.exists():
        return  # results.json is regenerated output; cases.yaml is the committed source of truth
    payload = json.loads(results.read_text())
    for row in payload["rows"]:
        assert set(row) == {"case", "package", "property", "expected", "got", "rel_err", "pass"}, (
            f"results.json row schema drifted: {sorted(row)}"
        )
