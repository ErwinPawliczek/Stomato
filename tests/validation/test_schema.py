"""Schema checks for the P1-05 validation fixtures and cases file."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ngdesign import registry
from scripts.validate_properties import ABSOLUTE_ERROR_PROPERTIES, TOLERANCE_POLICY, _load_cases, packages_for

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
        if case.source.startswith("coolprop:") or case.skip_reason:
            continue  # pending/experimental: citations verified at pack review (task T10)
        lowered = case.source.lower()
        assert "retrieved" in lowered or "read" in lowered, (
            f"{case.id}: source lacks a retrieval date: {case.source}"
        )
        assert any(
            k in lowered
            for k in (
                "journal",
                "doi",
                "series",
                "fig",
                "table",
                "p.",
                "pp.",
                "symposium",
                # NIST-recommended software citation: repository-hosted reference
                # code is the publication origin (e.g. usnistgov/AGA8 check values).
                "github.com",
            )
        ), f"{case.id}: source lacks a publication locator: {case.source}"


def test_all_expected_properties_are_evaluated_by_the_harness() -> None:
    for case in _load_cases():
        if case.skip_reason:
            continue  # pending/experimental: bound ahead of the model, skipped visibly
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
    available = set(registry.available("thermo"))
    for case in _load_cases():
        if case.package == "all" or case.skip_reason:
            continue  # pending:<id>/experimental rows are unregistered by design (skipped visibly)
        for pkg in packages_for(case):
            assert pkg in available, f"{case.id}: unexpected package {pkg}"


def test_package_list_expands_and_drops_pending() -> None:
    """``package: [a, pending:b]`` runs on a only, naming b as skipped; no duplicates."""
    multi = [c for c in _load_cases() if c.packages]
    for case in multi:
        assert all(not p.startswith("pending:") for p in case.packages), case.id
        assert len(set(case.packages)) == len(case.packages), f"{case.id}: duplicate package names"
        assert not set(case.packages) & set(case.skipped_packages), case.id


def test_skips_are_visible_and_reasoned() -> None:
    """A pending/experimental case is skipped only with a reason naming it (task T10).

    Guards both directions: no silently dropped case, and no skip on a case that
    should run.
    """
    from scripts.validate_properties import _row_status

    for case in _load_cases():
        for dropped in case.skipped_packages:
            # a list case's dropped member is named (run_all prints its reason)
            assert dropped.startswith("pending:") or _row_status(dropped) == "experimental", case.id
        if "," in case.package:
            # list case: skipped as a whole only when no member is live
            names = case.package.split(",")
            if case.skip_reason:
                assert all(n in case.skip_reason for n in names), case.id
            continue
        if case.package.startswith("pending:"):
            assert case.skip_reason, f"{case.id}: pending package skipped without a reason"
            assert case.package in case.skip_reason, f"{case.id}: skip reason does not name the package"
        elif _row_status(case.package) == "experimental":
            assert case.skip_reason, f"{case.id}: experimental row skipped without a reason"
            assert case.package in case.skip_reason, f"{case.id}: skip reason does not name the package"
        else:
            assert not case.skip_reason, f"{case.id}: unexpected skip: {case.skip_reason}"


def test_results_json_row_schema_when_present() -> None:
    results = REPO_ROOT / "data" / "validation" / "results.json"
    if not results.exists():
        return  # results.json is regenerated output; cases.yaml is the committed source of truth
    payload = json.loads(results.read_text())
    for row in payload["rows"]:
        assert set(row) == {"case", "package", "property", "expected", "got", "rel_err", "pass"}, (
            f"results.json row schema drifted: {sorted(row)}"
        )


def test_liquid_comp_reads_the_liquid_richest_in_the_named_component() -> None:
    """`liquid_rich_in` picks the organic-rich liquid of an LLE split; the default stays water-rich."""
    from types import SimpleNamespace

    from ngdesign.contracts.stream import PhaseKind
    from scripts.validate_properties import _liquid_rich_in

    def phase(kind: PhaseKind, **x: float) -> SimpleNamespace:
        return SimpleNamespace(kind=kind, composition=x)

    # Activity-coefficient packages may label both liquids of a water/organic split aqueous.
    state = SimpleNamespace(
        phases=[
            phase(PhaseKind.VAPOR, BuOH=0.9, H2O=0.1),
            phase(PhaseKind.AQUEOUS, BuOH=0.02, H2O=0.98),
            phase(PhaseKind.AQUEOUS, BuOH=0.45, H2O=0.55),
        ]
    )
    assert _liquid_rich_in(state) == {"BuOH": 0.02, "H2O": 0.98}
    assert _liquid_rich_in(state, "BuOH") == {"BuOH": 0.45, "H2O": 0.55}
    # The vapour is never read, and H2O keeps preferring the aqueous label.
    labelled = SimpleNamespace(
        phases=[phase(PhaseKind.HC_LIQUID, BuOH=0.0, H2O=0.99), phase(PhaseKind.AQUEOUS, BuOH=0.1, H2O=0.9)]
    )
    assert _liquid_rich_in(labelled) == {"BuOH": 0.1, "H2O": 0.9}
    assert _liquid_rich_in(SimpleNamespace(phases=[phase(PhaseKind.VAPOR, H2O=1.0)]), "BuOH") is None
