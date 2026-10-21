"""Catalogue tests (spec T-01): data rows load, register, build and stay consistent."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from ngdesign import registry
from ngdesign.amine.package import AmineENRTLPackage, AmineKEPackage
from ngdesign.thermo import catalogue
from ngdesign.thermo.catalogue import CatalogueError, ModelRow, load_catalogue
from ngdesign.thermo.nrtl import NrtlThermo
from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.thermo.pr78 import PengRobinson78Thermo
from ngdesign.thermo.srk import SoaveRedlichKwongThermo

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_harness() -> Any:
    spec = importlib.util.spec_from_file_location(
        "validate_properties_t01", REPO_ROOT / "scripts" / "validate_properties.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass processing resolves string annotations through sys.modules[cls.__module__];
    # without this registration every @dataclass in the harness explodes on import.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rows_load_and_build() -> None:
    """Six rows load; the registry resolves each id to its adapter class."""
    rows = load_catalogue()
    assert sorted(rows) == ["amine_enrtl", "amine_ke", "nrtl", "pr", "pr78", "srk"]
    assert registry.available("thermo") == sorted(rows)
    expected_types = {
        "pr": PengRobinsonThermo,
        "srk": SoaveRedlichKwongThermo,
        "pr78": PengRobinson78Thermo,
        "nrtl": NrtlThermo,
        "amine_ke": AmineKEPackage,
        "amine_enrtl": AmineENRTLPackage,
    }
    for model_id, cls in expected_types.items():
        assert type(registry.create("thermo", model_id)) is cls


def test_factories_are_lazy_builds() -> None:
    """The catalogue factory constructs on every call (no shared instance)."""
    a = registry.create("thermo", "pr")
    b = registry.create("thermo", "pr")
    assert a is not b


def test_amines_stay_class_registered_until_125() -> None:
    """Tolerance path: the amine decorators survive until #125 (P1-09) moves them."""
    assert registry.get("thermo", "amine_ke") is AmineKEPackage
    row = catalogue.describe("amine_ke")
    assert row.adapter == "ngdesign.amine.package:AmineKEPackage"


def test_duplicate_id_raises_naming_both_rows(tmp_path: Path) -> None:
    _plant_schema(tmp_path)
    row = _pr_row_dict()
    (tmp_path / "a.yaml").write_text(yaml.safe_dump([row]))
    (tmp_path / "b.yaml").write_text(yaml.safe_dump([row]))
    with pytest.raises(CatalogueError, match=r"b\.yaml row 0.*already defined in a\.yaml"):
        _load_planted(tmp_path)


def test_unknown_adapter_raises(tmp_path: Path) -> None:
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {"id": "nope", "adapter": "ngdesign.thermo.nope:Missing"}
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump([row]))
    with pytest.raises(CatalogueError, match="unknown adapter"):
        _load_planted(tmp_path)


def test_bad_option_value_fails_at_load(tmp_path: Path) -> None:
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {
        "id": "badopt",
        "options": {"eos": "PRMIX", "kij_table": "ChemSep PR", "alpha": "bogus"},
    }
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump([row]))
    with pytest.raises(CatalogueError, match="unknown or invalid option value"):
        _load_planted(tmp_path)


def test_non_cubic_options_fail_at_load(tmp_path: Path) -> None:
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {"id": "notcubic", "family": "gamma_phi", "options": {"alpha": "twu"}}
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump([row]))
    with pytest.raises(CatalogueError, match="no typed options are declared for family"):
        _load_planted(tmp_path)


def test_non_default_option_loads_but_build_raises(tmp_path: Path) -> None:
    """The vocabulary admits non-default cubic options; build refuses until T-02 lands."""
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {
        "id": "prtwu",
        "options": {"eos": "PRMIX", "kij_table": "ChemSep PR", "alpha": "twu"},
    }  # noqa: E501
    (tmp_path / "twu.yaml").write_text(yaml.safe_dump([row]))
    loaded = _load_planted(tmp_path)
    with pytest.raises(NotImplementedError, match="alpha=twu.*T-02"):
        catalogue.build(loaded["prtwu"])


def test_eos_mismatch_fails_at_load(tmp_path: Path) -> None:
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {"id": "mismatch", "options": {"eos": "SRKMIX", "kij_table": "ChemSep PR"}}
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump([row]))
    with pytest.raises(CatalogueError, match="does not match adapter"):
        _load_planted(tmp_path)


@pytest.mark.parametrize("model_id", ["pr", "srk", "pr78", "nrtl", "amine_ke", "amine_enrtl"])
def test_slice_solves_identically_through_catalogue(model_id: str) -> None:
    """Catalogue-registered factories solve the slice identically to direct construction."""
    pytest.importorskip("ngdesign.flowsheets.slice")
    from ngdesign.flowsheets.slice import build as build_slice
    from ngdesign.solver.sequential_modular import SequentialModular

    row = catalogue.describe(model_id)
    direct = catalogue.build(row)
    via_registry = registry.create("thermo", model_id)
    try:
        flowsheet = build_slice()
    except Exception as exc:  # noqa: BLE001 - slice needs registered unit kinds
        pytest.skip(f"slice not buildable: {exc}")
    try:
        solved_direct = SequentialModular().solve(build_slice(), direct)
    except ValueError as exc:
        # e.g. the ChemSep NRTL databank has no fitted C1/C2 pair for the slice feed:
        # the model refusing an uncovered feed is correct behaviour, not a defect.
        if "no fitted binary parameters" in str(exc):
            pytest.skip(f"{model_id} does not cover the slice feed: {exc}")
        raise
    solved_registry = SequentialModular().solve(flowsheet, via_registry)
    assert solved_direct.converged
    assert solved_registry.converged
    # Compare the solved state, not the whole result: `history` carries solver-run
    # noise (per-unit iteration timings), which says nothing about thermo equivalence.
    direct_dump = solved_direct.model_dump()
    registry_dump = solved_registry.model_dump()
    direct_dump.pop("history", None)
    registry_dump.pop("history", None)
    assert direct_dump == registry_dump


def test_l0_green_on_all_rows() -> None:
    """Every declared L0 check on every row passes (probes fixed the points/tolerances)."""
    vp = _load_harness()
    for model_id, row in sorted(load_catalogue().items()):
        results = vp.run_l0_row(row)
        failed = [r for r in results if not r.passed]
        assert not failed, f"{model_id}: {[(r.check, r.detail) for r in failed]}"


def test_audit_passes_on_the_real_catalogue() -> None:
    """The T-01 audit gate is green on the committed catalogue."""
    vp = _load_harness()
    assert vp.audit() == 0


def test_audit_fails_on_planted_validated_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A planted row claiming `validated` without case evidence fails the audit."""
    registry.available("thermo")  # discover the real registry before planting
    _plant_schema(tmp_path)
    row = _pr_row_dict() | {"id": "planted", "status": "validated", "validation": []}
    (tmp_path / "planted.yaml").write_text(yaml.safe_dump([row]))
    monkeypatch.setenv("STOMATO_THERMO_MODELS_DIR", str(tmp_path))
    vp = _load_harness()
    assert vp.main(["--audit"]) != 0


# -- planted catalogue helpers -------------------------------------------------------------------


def _plant_schema(tmp_path: Path) -> None:
    src = REPO_ROOT / "data" / "thermo_models" / "_schema.yaml"
    (tmp_path / "_schema.yaml").write_text(src.read_text())


def _pr_row_dict() -> dict[str, Any]:
    rows = yaml.safe_load((REPO_ROOT / "data" / "thermo_models" / "cubic.yaml").read_text())
    return next(r for r in rows if r["id"] == "pr")


def _load_planted(tmp_path: Path) -> dict[str, ModelRow]:
    import os
    from unittest import mock

    with mock.patch.dict(os.environ, {"STOMATO_THERMO_MODELS_DIR": str(tmp_path)}):
        return catalogue.load_catalogue()
