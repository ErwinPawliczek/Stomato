"""`kij_table: none` — the plain cubic EOS with every k_ij = 0 (rows srk-kij0, pr-kij0)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from thermo import PRMIX, SRKMIX, CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVL

from ngdesign import registry
from ngdesign.thermo import catalogue
from ngdesign.thermo._state import KIJ_TABLE_NONE
from ngdesign.thermo._trace import describe_flasher_parameters
from ngdesign.thermo.catalogue import CatalogueError
from ngdesign.thermo.cubic import PrKij0Thermo, SrkKij0Thermo

REPO_ROOT = Path(__file__).resolve().parents[2]
IDS = ("C3", "nC4", "nC5")
Z = {"C3": 0.3, "nC4": 0.3, "nC5": 0.4}
P = 689475.729  # 100 psia


def test_rows_build_their_adapters() -> None:
    registry.discover()
    assert type(registry.create("thermo", "srk-kij0")) is SrkKij0Thermo
    assert type(registry.create("thermo", "pr-kij0")) is PrKij0Thermo
    assert catalogue.describe("srk-kij0").options["kij_table"] == KIJ_TABLE_NONE


@pytest.mark.parametrize("row", ["srk-kij0", "pr-kij0"])
def test_flasher_kijs_are_zero(row: str) -> None:
    registry.discover()
    flasher = registry.create("thermo", row)._build_flasher_vl(IDS)
    assert flasher.gas.eos_kwargs["kijs"] == [[0.0] * 3 for _ in range(3)]
    full = registry.create("thermo", row)._build_flasher(IDS)
    assert full.gas.eos_kwargs["kijs"] == [[0.0] * 3 for _ in range(3)]


def test_ipdb_row_keeps_its_kijs() -> None:
    """Same constants, only the k_ij matrix differs from the IPDB row."""
    registry.discover()
    a = registry.create("thermo", "srk")._build_flasher_vl(IDS)
    b = registry.create("thermo", "srk-kij0")._build_flasher_vl(IDS)
    assert a.gas.eos_kwargs["kijs"][0][2] != 0.0
    for key in ("Tcs", "Pcs", "omegas"):
        assert a.gas.eos_kwargs[key] == b.gas.eos_kwargs[key]


@pytest.mark.parametrize(("row", "eos"), [("srk-kij0", SRKMIX), ("pr-kij0", PRMIX)])
def test_bubble_point_matches_plain_thermo_eos(row: str, eos: type) -> None:
    """Independent cross-check: thermo's mixture EOS with kijs = 0 on the same constants."""
    registry.discover()
    pkg = registry.create("thermo", row)
    kw = pkg._build_flasher_vl(IDS).gas.eos_kwargs
    consts, props = ChemicalConstantsPackage.from_IDs(["propane", "n-butane", "n-pentane"])
    eos_kwargs = {"Tcs": kw["Tcs"], "Pcs": kw["Pcs"], "omegas": kw["omegas"]}
    gas = CEOSGas(eos, eos_kwargs, HeatCapacityGases=props.HeatCapacityGases)
    liq = CEOSLiquid(eos, eos_kwargs, HeatCapacityGases=props.HeatCapacityGases)
    ref = FlashVL(consts, props, liquid=liq, gas=gas).flash(P=P, VF=0.0, zs=[0.3, 0.3, 0.4])
    assert pkg.bubble_point(Z, P=P).T == pytest.approx(ref.T, abs=1e-4)  # two saturation solvers


def test_seader_10_9_feed_bubble_point() -> None:
    """Seader-Henley-Roper 3rd ed. Ex. 10.9 prints 123.5 F for its CHEMCAD-SRK feed bubble point."""
    registry.discover()
    T = registry.create("thermo", "srk-kij0").bubble_point(Z, P=P).T
    assert (T - 273.15) * 1.8 + 32.0 == pytest.approx(123.5, abs=0.05)


def test_trace_names_zero_kij() -> None:
    registry.discover()
    pkg = registry.create("thermo", "srk-kij0")
    described = describe_flasher_parameters(pkg._build_flasher(IDS), IDS, "srk", KIJ_TABLE_NONE)
    leaves = [leaf for leaf in described["leaves"] if leaf["prop"] == "kij"]
    assert [leaf["label"] for leaf in leaves] == ["k_ij = 0 (none)"]
    assert leaves[0]["quality"] == "cited"


def _plant(tmp_path: Path, row: dict[str, object]) -> None:
    import os
    from unittest import mock

    (tmp_path / "_schema.yaml").write_text(
        (REPO_ROOT / "data" / "thermo_models" / "_schema.yaml").read_text()
    )
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump([row]))
    with mock.patch.dict(os.environ, {"STOMATO_THERMO_MODELS_DIR": str(tmp_path)}):
        catalogue.load_catalogue()


def test_kij_table_mismatch_fails_at_load(tmp_path: Path) -> None:
    rows = yaml.safe_load((REPO_ROOT / "data" / "thermo_models" / "cubic.yaml").read_text())
    row = next(r for r in rows if r["id"] == "srk-kij0")
    bad = row | {"id": "bad", "options": {**row["options"], "kij_table": "ChemSep PR"}}
    with pytest.raises(CatalogueError, match="kij_table"):
        _plant(tmp_path, bad)
