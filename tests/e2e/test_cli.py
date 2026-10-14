"""S-35 acceptance: the CLI runs the demo and writes every drawing to disk."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ngdesign.cli import main


@pytest.mark.slice
def test_cli_writes_every_drawing(tmp_path: Path) -> None:
    assert main(["slice", "--out", str(tmp_path)]) == 0
    isos = sorted(tmp_path.glob("iso_*.svg"))
    assert len(isos) >= 5
    for svg in [tmp_path / "pfd.svg", tmp_path / "pid.svg", *isos]:
        ET.fromstring(svg.read_text(encoding="utf-8"))
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    for name in ("pfd.svg", "pid.svg", *(p.name for p in isos)):
        assert name in index


@pytest.mark.slice
def test_cli_is_deterministic(tmp_path: Path) -> None:
    """Two runs produce byte-identical drawings: the chain is pure."""
    main(["slice", "--out", str(tmp_path / "a")])
    main(["slice", "--out", str(tmp_path / "b")])
    for name in ("pfd.svg", "pid.svg", "index.html"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()
