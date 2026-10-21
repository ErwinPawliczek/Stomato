"""Compose validation (spec P3-03): ``docker compose config`` must parse
``deploy/compose.yaml`` cleanly. Skipped when the docker CLI is absent
(CI installs it; a bare dev checkout without docker still runs the suite).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

COMPOSE_FILE = Path(__file__).resolve().parents[2] / "deploy" / "compose.yaml"

docker = shutil.which("docker")

pytestmark = [
    pytest.mark.skipif(docker is None, reason="docker CLI not available"),
    pytest.mark.skipif(not COMPOSE_FILE.exists(), reason="deploy/compose.yaml missing"),
]


def _config() -> dict[str, Any]:
    """The interpolated compose config (json), asserting it validates."""
    assert docker is not None
    result = subprocess.run(
        [docker, "compose", "-f", str(COMPOSE_FILE), "config", "--format", "json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    config: dict[str, Any] = json.loads(result.stdout)
    return config


def test_compose_config_is_valid() -> None:
    """The compose file parses and interpolates with the committed defaults."""
    assert _config()["services"]


def test_compose_serves_two_api_replicas_behind_web() -> None:
    """The Phase 3 shape: 2 api replicas, worker + web + bundled stores."""
    services = _config()["services"]
    assert services["api"]["deploy"]["replicas"] == 2
    assert services["worker"]["command"] == ["worker"]
    assert services["db-init"]["command"] == ["db-init"]
    assert services["api"]["depends_on"]["db-init"]["condition"] == "service_completed_successfully"
    assert services["web"]["ports"][0]["published"] == "8080"
