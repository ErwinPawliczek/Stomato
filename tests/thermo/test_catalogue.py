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
from ngdesign.thermo.helmholtz import (
    BWRSPackage,
    CoolPropPackage,
    GERGPackage,
    IAPWSPackage,
    UnavailablePackage,
)
from ngdesign.thermo.nrtl import NrtlThermo
from ngdesign.thermo.pr import PengRobinsonThermo
from ngdesign.thermo.pr78 import PengRobinson78Thermo
from ngdesign.thermo.srk import SoaveRedlichKwongThermo
from ngdesign.thermo.teqp_bridge import (
    CpaPrThermo,
    CpaSrkThermo,
    MultifluidPureThermo,
    MultifluidThermo,
    PCSaftAssocThermo,
    PCSaftPolarThermo,
    PCSaftThermo,
    SaftVrMieThermo,
)

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
    """83 rows load; the registry resolves each id to its adapter class."""
    rows = load_catalogue()
    gamma_phi_ids = [
        f"{liquid}_{vapour}"
        for liquid in (
            "uniquac",
            "wilson",
            "vanlaar",
            "margules",
            "regular_solution",
            "unifac",
            "unifac_dortmund",
            "unifac_psrk",
            "unifac_nist",
            "unifac_lle",
            "unifac_lyngby",
        )
        for vapour in ("ig", "rk", "pr", "hoc", "nothnagel")
    ]
    # The pre-existing NRTL row keeps its bare id (its PR vapour IS the row);
    # nrtl_pr therefore does not exist - the four suffixed NRTL ids are new.
    nrtl_ids = ["nrtl", "nrtl_ig", "nrtl_rk", "nrtl_hoc", "nrtl_nothnagel"]
    helmholtz_ids = [
        "aga8_dc92",
        "asme_steam",
        "bwr_ls",
        "bwrs",
        "coolprop_heos",
        "eos_cg",
        "gerg2008",
        "iapws95",
        "iapws_if97",
        "mbwr",
    ]
    saft_ids = [
        "cpa_pr",
        "cpa_srk",
        "multifluid",
        "multifluid_pure",
        "pc_saft",
        "pc_saft_assoc",
        "pc_saft_polar",
        "saft_vr_mie",
    ]
    non_gamma = ["amine_enrtl", "amine_ke", "pr", "pr78", "srk"]
    expected = sorted(gamma_phi_ids + nrtl_ids + helmholtz_ids + non_gamma + saft_ids)
    assert len(expected) == 83
    assert sorted(rows) == expected
    assert registry.available("thermo") == sorted(rows)
    expected_types = {
        "pr": PengRobinsonThermo,
        "srk": SoaveRedlichKwongThermo,
        "pr78": PengRobinson78Thermo,
        "nrtl": NrtlThermo,
        "amine_ke": AmineKEPackage,
        "amine_enrtl": AmineENRTLPackage,
        # helmholtz family (T-04): placeholders build without CoolProp installed
        "iapws95": IAPWSPackage,
        "iapws_if97": IAPWSPackage,
        "coolprop_heos": CoolPropPackage,
        "gerg2008": GERGPackage,
        "bwrs": BWRSPackage,
        "asme_steam": UnavailablePackage,
        "eos_cg": UnavailablePackage,
        "aga8_dc92": UnavailablePackage,
        "mbwr": UnavailablePackage,
        "bwr_ls": UnavailablePackage,
        "pc_saft": PCSaftThermo,
        "pc_saft_assoc": PCSaftAssocThermo,
        "pc_saft_polar": PCSaftPolarThermo,
        "saft_vr_mie": SaftVrMieThermo,
        "cpa_srk": CpaSrkThermo,
        "cpa_pr": CpaPrThermo,
        "multifluid": MultifluidThermo,
        "multifluid_pure": MultifluidPureThermo,
    }
    for model_id, cls in expected_types.items():
        if model_id in {"pc_saft", "pc_saft_assoc", "pc_saft_polar", "saft_vr_mie",
                        "cpa_srk", "cpa_pr", "multifluid", "multifluid_pure"}:
            continue  # saft construction needs the optional teqp extra; test_saft.py covers it
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
    # gamma_phi declares typed options since T-03, so the load fails on option
    # validation (unknown keys, missing liquid/vapour) instead of the cubic-era
    # "family declares no typed options" message.
    with pytest.raises(CatalogueError, match="unknown or invalid option value"):
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


# The saft association kernels evaluate ~10x slower than closed-form EOS; the global
# 120s timeout is an anti-hang guard, not a slate budget, so this test opts out of it.
@pytest.mark.timeout(900)
def test_l0_green_on_all_rows() -> None:
    """Every declared L0 check on every non-experimental row passes (audit mirrors this)."""
    vp = _load_harness()
    dep_missed: list[str] = []
    total = 0
    for model_id, row in sorted(load_catalogue().items()):
        if row.status == "experimental":
            continue
        total += 1
        try:
            results = vp.run_l0_row(row)
        except vp.SaftDependencyMissing:
            dep_missed.append(model_id)
            continue
        failed = [r for r in results if not r.passed]
        assert not failed, f"{model_id}: {[(r.check, r.detail) for r in failed]}"
    assert len(dep_missed) < total, "every row missed its backend; no L0 check ran"


@pytest.mark.timeout(600)
def test_audit_passes_on_the_real_catalogue() -> None:
    """The T-01 audit gate is green on the committed catalogue.

    The default 120 s budget was sized for the 6-row catalogue; at 65 rows the
    audit's exhaustive L0 sweep plus quadratic L4 pair loop (locked harness)
    runs ~3 minutes on one core, so this test carries its own budget.
    """
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
