"""Tests for the shared P&ID rule helpers (spec P0-05)."""

from __future__ import annotations

from ngdesign.contracts import Direction, Nozzle, PidEquipment, Vec3
from ngdesign.pid_rules._common import psv_nozzle


def _eq(services: list[str]) -> PidEquipment:
    return PidEquipment(
        tag="V-101",
        kind="ko_drum",
        design_pressure_Pa=4.0e6,
        design_temperature_K=338.15,
        nozzles=[
            Nozzle(
                id=f"N{i}",
                service=service,
                port=None,
                nps_in=4,
                flange_class=300,
                position_mm=Vec3(x=0.0, y=0.0, z=1000.0),
                facing=Direction.UP,
            )
            for i, service in enumerate(services, start=1)
        ],
    )


def test_finds_the_psv_nozzle() -> None:
    found = psv_nozzle(_eq(["inlet", "psv", "drain"]))
    assert found is not None
    assert found.id == "N2"
    assert found.service == "psv"


def test_returns_none_without_a_psv_nozzle() -> None:
    assert psv_nozzle(_eq(["inlet", "drain"])) is None


def test_returns_none_for_empty_nozzle_list() -> None:
    assert psv_nozzle(_eq([])) is None
