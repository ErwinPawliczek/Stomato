"""Spec P1-05: parametrised reference-case suite over ``data/validation/cases.yaml``.

One test per case, across every package the case names. A failure message always shows the
expected value, the package's value, the error against the case's tolerance, and the cited
source, so a red run is assessable (model limitation vs bug) without re-reading the dataset.
Never skipped: every case runs on every package it names, every time.
"""

from __future__ import annotations

import pytest

from scripts.validate_properties import Case, Row, _load_cases, evaluate_case, packages_for, xfail_reason

pytestmark = [pytest.mark.validation, pytest.mark.slow]


def _format_row(row: Row, source: str) -> str:
    got = "n/a" if row.got is None else f"{row.got:.6g}"
    err = "n/a" if row.rel_err is None else f"{row.rel_err:.3g}"
    return f"  {row.property}: expected {row.expected:.6g}, got {got}, err {err}\n    source: {source}"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c.id)
def test_reference_case(case: Case) -> None:
    """Every comparison of one case passes on every package the case names."""
    failures: list[Row] = []
    crashes: list[str] = []
    for pkg in packages_for(case):
        try:
            failures.extend(row for row in evaluate_case(case, pkg) if not row.passed)
        except Exception as exc:  # noqa: BLE001 - a package crash is a failing case, not a suite error
            crashes.append(f"  {pkg} raised {type(exc).__name__}: {exc}\n    source: {case.source}")
    if not failures and not crashes:
        return
    detail = "\n".join([*(_format_row(row, case.source) for row in failures), *crashes])
    failed_props = frozenset(row.property for row in failures)
    reason = xfail_reason(case, failed_props | {"crash" for _ in crashes})
    if reason is not None:
        pytest.xfail(f"{reason}\n{detail}")
    pytest.fail(
        f"{case.id}: {len(failures)} failing comparison(s), {len(crashes)} package crash(es)"
        f" (source: {case.source})\n{detail}"
    )
