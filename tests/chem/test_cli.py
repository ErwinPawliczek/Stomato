"""The ``ngdesign chem`` command line."""

from __future__ import annotations

import pytest

from ngdesign.cli import main


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> str:
    assert main(["chem", *argv]) == 0
    return capsys.readouterr().out


def test_lookup_prints_cited_properties(capsys: pytest.CaptureFixture[str]) -> None:
    out = _run(capsys, "lookup", "methane")
    assert "74-82-8" in out
    assert "Hf_gas" in out
    assert "atct" in out


def test_lookup_search(capsys: pytest.CaptureFixture[str]) -> None:
    assert "71-43-2" in _run(capsys, "lookup", "benzene", "--search")


def test_balance(capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(capsys, "balance", "C3H8 + O2 -> CO2 + H2O").strip() == "C3H8 + 5 O2 -> 3 CO2 + 4 H2O"


def test_react_reads_units_and_prints_a_unit_set(capsys: pytest.CaptureFixture[str]) -> None:
    out = _run(capsys, "react", "N2 + H2 -> NH3", "--T", "400 degC")
    assert "kJ/mol" in out
    assert "ln K" in out
    assert "degC" in _run(capsys, "react", "N2 + H2 -> NH3", "--T", "400 degC", "--units", "METRIC")


def test_equilibrium(capsys: pytest.CaptureFixture[str]) -> None:
    out = _run(
        capsys,
        "equilibrium",
        "--feed",
        "CH4=1",
        "H2O=3",
        "--species",
        "CH4",
        "H2O",
        "CO",
        "CO2",
        "H2",
        "--T",
        "800 degC",
        "--P",
        "1 bar",
    )
    assert "H2" in out


def test_saturation_both_ways(capsys: pytest.CaptureFixture[str]) -> None:
    assert "Psat" in _run(capsys, "saturation", "water", "--T", "100 degC")
    assert "Tsat" in _run(capsys, "saturation", "water", "--P", "1 atm")


def test_convert(capsys: pytest.CaptureFixture[str]) -> None:
    assert float(_run(capsys, "convert", "1", "atm", "kPa")) == pytest.approx(101.325)
    assert float(_run(capsys, "convert", "100", "kg/h", "kmol/h", "--mw", "20")) == pytest.approx(5.0)


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert "row_counts" in _run(capsys, "info")
