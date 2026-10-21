"""P2-04 acceptance: the CLI `study` command over a project JSON file."""

from __future__ import annotations

from pathlib import Path

from ngdesign.cli import main
from ngdesign.contracts import Project
from ngdesign.flowsheets import slice as slice_fs


def _project_json(tmp_path: Path) -> str:
    path = tmp_path / "project.json"
    path.write_text(
        Project(name="slice", flowsheet=slice_fs.build(), layout={}).model_dump_json(),
        encoding="utf-8",
    )
    return str(path)


def test_study_command_prints_markdown_and_writes_csv(tmp_path: Path, capsys: object) -> None:
    project = _project_json(tmp_path)
    csv_path = tmp_path / "out.csv"
    code = main(
        [
            "study",
            project,
            "--input",
            "K-101.params.P_out=8.0e6:9.0e6:3",
            "--output",
            "K-101.power_W",
            "--output",
            "E-101.duty_W",
            "--csv",
            str(csv_path),
        ]
    )
    assert code == 0
    stdout = str(capsys.readouterr().out)  # type: ignore[attr-defined]
    assert "K-101.params.P_out" in stdout and "status" in stdout
    assert "wrote" in stdout and str(csv_path) in stdout
    lines = csv_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 4  # header + 3 cases
    assert lines[0] == "K-101.params.P_out,K-101.power_W,E-101.duty_W,status,iterations,wall_s"


def test_study_command_accepts_single_literal_value(tmp_path: Path) -> None:
    code = main(
        [
            "study",
            _project_json(tmp_path),
            "--input",
            "K-101.params.P_out=8e6",
            "--output",
            "K-101.power_W",
        ]
    )
    assert code == 0  # a bare value is the one-element comma-list form


def test_study_command_reports_failed_cases_and_bad_files(tmp_path: Path) -> None:
    # A failing case stays a row (the table grades it); a missing project file
    # is a CLI error with exit code 2, not a traceback.
    code = main(
        [
            "study",
            _project_json(tmp_path),
            "--input",
            "K-101.params.P_out=8e6,-1.0",
            "--output",
            "K-101.power_W",
        ]
    )
    assert code == 0
    code = main(
        [
            "study",
            str(tmp_path / "nope.json"),
            "--input",
            "K-101.params.P_out=8e6",
            "--output",
            "K-101.power_W",
        ]
    )
    assert code == 2


def test_study_command_rejects_single_point_range(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(SystemExit):
        main(
            [
                "study",
                _project_json(tmp_path),
                "--input",
                "K-101.params.P_out=8.0e6:9.0e6:1",
                "--output",
                "K-101.power_W",
            ]
        )
