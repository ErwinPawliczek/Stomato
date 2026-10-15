"""Tests for line sizing by service velocity limits (spec S-20)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.sizing.line_size import CANDIDATE_NPS_IN, line_size

FT3_TO_M3 = 0.028316846592
DAY_TO_S = 86400.0


def test_gas_50_mmscfd_at_3_4_mpa() -> None:
    """50 MMSCFD gas at 3.4 MPa (rho ~ 28 kg/m3) sizes to NPS 8..12.

    Actual flow: Q_std * (P_std/P) * Z with Z ~ 0.88 at 3.4 MPa, near-standard T.
    At rho = 28 kg/m3 the momentum limit rho*v^2 <= 6000 Pa governs (v <= 14.6 m/s).
    """
    q_std = 50e6 * FT3_TO_M3 / DAY_TO_S
    q_act = q_std * (101325.0 / 3.4e6) * 0.88
    got = line_size(service="PG", flow_m3_s=q_act, rho_kg_m3=28.0)
    assert 8 <= got["nps_in"] <= 12
    assert got["limit_hit"] == "rho_v2"
    assert got["velocity_m_s"] <= math.sqrt(6000.0 / 28.0)
    assert got["velocity_m_s"] <= 0.8 * 100.0 / math.sqrt(28.0 * 0.0624279606) * 0.3048


def test_liquid_discharge_0_02_m3_s() -> None:
    """A 0.02 m3/s liquid pump discharge lands on NPS 3 or 4."""
    got = line_size(service="PL", flow_m3_s=0.02, rho_kg_m3=700.0)
    assert 3 <= got["nps_in"] <= 4
    assert got["velocity_m_s"] <= 3.0


def test_monotonic_in_flow() -> None:
    """More flow never gives a smaller pipe, for gas and liquid alike.

    Flows stay within NPS 24's capacity for each service's velocity limits.
    """
    for service, rho, flows in (
        ("PG", 28.0, (0.05, 0.1, 0.2, 0.5, 1.0)),
        ("PL", 700.0, (0.005, 0.01, 0.05, 0.1, 0.2)),
    ):
        sizes = [line_size(service=service, flow_m3_s=q, rho_kg_m3=rho)["nps_in"] for q in flows]
        assert sizes == sorted(sizes), f"{service} not monotonic: {sizes}"


def test_glycol_limit_1_5_m_s() -> None:
    """GL caps at 1.5 m/s: 0.01 m3/s needs at least the area a 1.5 m/s jet uses."""
    got = line_size(service="GL", flow_m3_s=0.01, rho_kg_m3=1100.0)
    assert got["velocity_m_s"] <= 1.5
    assert got["nps_in"] >= 4


def test_suction_not_smaller_than_discharge() -> None:
    """The tighter suction limits never pick a smaller pipe than discharge."""
    for q in (0.005, 0.01, 0.02):
        suction = line_size(service="PL", flow_m3_s=q, rho_kg_m3=700.0, role="suction")
        discharge = line_size(service="PL", flow_m3_s=q, rho_kg_m3=700.0, role="discharge")
        assert suction["nps_in"] >= discharge["nps_in"]
        assert suction["velocity_m_s"] <= 1.5


def test_return_keys_and_rho_v2() -> None:
    got = line_size(service="PG", flow_m3_s=0.4, rho_kg_m3=28.0)
    assert set(got) == {"nps_in", "velocity_m_s", "rho_v2", "limit_hit"}
    assert math.isclose(got["rho_v2"], 28.0 * got["velocity_m_s"] ** 2, rel_tol=1e-12)
    assert got["limit_hit"] in {"v_max", "rho_v2", "erosional_api14e"}


def test_uses_candidate_nps_list() -> None:
    """The returned NPS is always one of the candidates."""
    for q in (0.002, 0.02, 0.2):
        assert line_size(service="PL", flow_m3_s=q, rho_kg_m3=700.0)["nps_in"] in CANDIDATE_NPS_IN


@pytest.mark.parametrize(
    "kwargs",
    [
        {"service": "XX", "flow_m3_s": 0.1, "rho_kg_m3": 700.0},  # unknown service
        {"service": "PL", "flow_m3_s": 0.0, "rho_kg_m3": 700.0},  # zero flow
        {"service": "PL", "flow_m3_s": -0.1, "rho_kg_m3": 700.0},  # negative flow
        {"service": "PL", "flow_m3_s": 0.1, "rho_kg_m3": 0.0},  # zero density
        {"service": "PL", "flow_m3_s": 0.1, "rho_kg_m3": -700.0},  # negative density
        {"service": "PG", "flow_m3_s": 0.1, "rho_kg_m3": 28.0, "role": "nozzle"},  # unknown role
        {"service": "PG", "flow_m3_s": 0.1, "rho_kg_m3": 28.0, "C": -100.0},  # bad C
    ],
)
def test_invalid_inputs_raise(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        line_size(**kwargs)


def test_plugin_registered() -> None:
    """The plugin is discoverable under kind correlation as line_size."""
    assert "line_size" in registry.available("correlation")
    plugin = registry.create("correlation", "line_size")
    got = plugin(**{"service": "PL", "flow_m3_s": 0.02, "rho_kg_m3": 700.0})
    assert got["nps_in"] in CANDIDATE_NPS_IN
