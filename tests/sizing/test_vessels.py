"""Tests for the vessel sizers (spec S-31).

The slice-basis acceptance cases size V-101 from the locked sample basis. The
full locked slice cannot solve end to end yet (TEG contactor convergence,
strict-xfail tests/e2e/test_slice.py), so these tests solve the V-101
sub-flowsheet alone -- same unit spec, same inlet feed composition and rate
taken from the locked slice module -- with the real thermo and solver plugins.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ngdesign import registry
from ngdesign.contracts import Flowsheet, PortRef, StreamSpec, UnitSpec
from ngdesign.contracts.flowsheet import Datasheet, FeedSpec, SolvedFlowsheet
from ngdesign.contracts.plugins import Sizer, Thermo
from ngdesign.flowsheets import slice as slice_fs
from ngdesign.sizing.line_size import line_size
from ngdesign.sizing.vessels import (
    DIAMETER_STEP_M,
    PA_PER_PSIG,
    design_conditions,
    horizontal_3phase,
    mixture_density,
    volumetric_flow,
)

PORTS = ("inlet", "gas_out", "hc_out", "water_out")


def _slice_feed() -> dict[str, Any]:
    dump: dict[str, Any] = cast(FeedSpec, slice_fs.build().streams[0].feed).model_dump()
    return dump


def _solve_v101(thermo: Thermo) -> SolvedFlowsheet:
    """V-101 alone, on the locked slice basis (same feed, same services)."""
    fs = Flowsheet(
        name="v101",
        units=[UnitSpec(tag="V-101", kind="separator_3phase", params={})],
        streams=[
            StreamSpec(
                id="S-001",
                target=PortRef(unit="V-101", port="inlet"),
                service="PG",
                feed=_slice_feed(),
            ),
            StreamSpec(id="S-002", source=PortRef(unit="V-101", port="gas_out"), service="PG"),
            StreamSpec(id="S-008", source=PortRef(unit="V-101", port="hc_out"), service="PL"),
            StreamSpec(id="S-011", source=PortRef(unit="V-101", port="water_out"), service="W"),
        ],
    )
    solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(fs, thermo)
    assert solved.converged
    return solved


@pytest.fixture()
def v101_datasheet(thermo: Thermo) -> Datasheet:
    solved = _solve_v101(thermo)
    sizer = registry.get("sizer", "separator_3phase")()
    sheet: Datasheet = sizer.size("V-101", solved, {})
    return sheet


class TestHorizontalHandChecked:
    """Pure-function cases computed by hand."""

    def test_gas_capacity_sets_diameter(self) -> None:
        # K=0.1, rhoL=800, rhoG=40, Qg=1.0:
        #   v_max = 0.1*sqrt(760/40) = 0.43588989...
        #   D = sqrt(8*1.0/(pi*v_max)) = 2.41657... -> rounds up to 2.55 m
        # Liquids negligible -> L = 3*D = 7.65, L/D = 3.
        got = horizontal_3phase(
            gas_flow_m3_s=1.0,
            hc_flow_m3_s=0.001,
            water_flow_m3_s=0.0005,
            rho_gas=40.0,
            rho_hc_liquid=800.0,
            K_m_s=0.1,
        )
        assert got["diameter_m"] == pytest.approx(2.55, abs=1e-9)
        assert got["length_tt_m"] == pytest.approx(3.0 * 2.55, abs=1e-9)
        assert got["ld_ratio"] == pytest.approx(3.0, abs=1e-9)
        assert got["v_max_m_s"] == pytest.approx(0.1 * math.sqrt(760 / 40), rel=1e-12)
        assert got["liquid_volume_m3"] == pytest.approx(0.001 * 180 + 0.0005 * 300, rel=1e-12)

    def test_retention_demand_grows_diameter(self) -> None:
        # Qg=0.05 alone gives D=0.54 m; 1.8 m3 of retention cannot fit in
        # L/D=5 at that diameter, so the algorithm grows D until L/D is in
        # range: 0.540 -> L=15.70 -> D=1.772 -> L=5.316 -> rounds to 1.80 m.
        got = horizontal_3phase(
            gas_flow_m3_s=0.05,
            hc_flow_m3_s=0.01,
            water_flow_m3_s=0.0,
            rho_gas=40.0,
            rho_hc_liquid=800.0,
            K_m_s=0.1,
        )
        assert got["diameter_m"] == pytest.approx(1.8, abs=1e-9)
        assert got["length_tt_m"] == pytest.approx(5.4, abs=1e-9)
        assert got["ld_ratio"] == pytest.approx(3.0, abs=1e-9)

    def test_diameter_on_015_grid(self) -> None:
        got = horizontal_3phase(
            gas_flow_m3_s=0.6,
            hc_flow_m3_s=0.002,
            water_flow_m3_s=0.001,
            rho_gas=40.0,
            rho_hc_liquid=800.0,
            K_m_s=0.11,
        )
        assert got["diameter_m"] % DIAMETER_STEP_M == pytest.approx(0.0, abs=1e-9)
        assert 3.0 <= got["ld_ratio"] <= 5.0

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"gas_flow_m3_s": -1.0},
            {"hc_flow_m3_s": -1.0},
            {"water_flow_m3_s": -1.0},
            {"rho_gas": 0.0},
            {"rho_hc_liquid": 0.0},
            {"K_m_s": 0.0},
        ],
    )
    def test_invalid_inputs_raise(self, kwargs: dict[str, Any]) -> None:
        base = dict(
            gas_flow_m3_s=1.0,
            hc_flow_m3_s=0.001,
            water_flow_m3_s=0.0,
            rho_gas=40.0,
            rho_hc_liquid=800.0,
            K_m_s=0.1,
        )
        with pytest.raises(ValueError):
            horizontal_3phase(**{**base, **kwargs})


class TestDesignConditions:
    def test_11_percent_governs_at_high_pressure(self) -> None:
        got = design_conditions(P_op=3.447e6, T_op=293.15)
        assert got["design_pressure_Pa"] == pytest.approx(1.1 * 3.447e6, rel=1e-12)
        assert got["design_temperature_K"] == pytest.approx(318.15, rel=1e-12)

    def test_170_kpa_governs_at_low_pressure(self) -> None:
        got = design_conditions(P_op=1.0e5, T_op=300.0)
        assert got["design_pressure_Pa"] == pytest.approx(2.7e5, rel=1e-12)

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            design_conditions(P_op=0.0, T_op=300.0)
        with pytest.raises(ValueError):
            design_conditions(P_op=1e5, T_op=0.0)


class TestV101Acceptance:
    """The spec's acceptance criteria against the locked slice basis."""

    def test_diameter_and_ld(self, v101_datasheet: Datasheet) -> None:
        d = v101_datasheet.dimensions["diameter_m"]
        assert 1.0 <= d <= 3.0
        assert 3.0 <= v101_datasheet.dimensions["ld_ratio"] <= 5.0

    def test_every_sim_port_has_a_nozzle(self, v101_datasheet: Datasheet) -> None:
        nozzle_ports = [n.port for n in v101_datasheet.nozzles if n.port is not None]
        assert sorted(nozzle_ports) == sorted(PORTS)

    def test_psv_nozzle_always_exists(self, v101_datasheet: Datasheet) -> None:
        assert any(n.service == "psv" for n in v101_datasheet.nozzles)

    def test_nozzle_ids_unique(self, v101_datasheet: Datasheet) -> None:
        ids = [n.id for n in v101_datasheet.nozzles]
        assert len(ids) == len(set(ids))

    def test_design_conditions_cover_operating(self, v101_datasheet: Datasheet) -> None:
        # Design pressure >= 1.1 x operating; design temperature >= operating + 25 K
        # is guaranteed by construction; check against the V-101 inlet conditions.
        feed = _slice_feed()
        assert v101_datasheet.design_pressure_Pa >= 1.1 * feed["P"]
        assert v101_datasheet.design_temperature_K >= feed["T"] + 25.0

    def test_nozzle_nps_matches_line_sizing(self, thermo: Thermo, v101_datasheet: Datasheet) -> None:
        solved = _solve_v101(thermo)
        by_port = {n.port: n for n in v101_datasheet.nozzles if n.port is not None}
        inlet = solved.streams["S-001"]
        # Inlet nozzle NPS must equal the S-20 line sizing result on the same
        # stream state (service PG, mixture density).
        expected = line_size(
            service="PG", flow_m3_s=volumetric_flow(inlet), rho_kg_m3=mixture_density(inlet)
        )["nps_in"]
        assert by_port["inlet"].nps_in == pytest.approx(expected)
        assert by_port["hc_out"].nps_in == pytest.approx(
            line_size(
                service="PL",
                flow_m3_s=volumetric_flow(solved.streams["S-008"]),
                rho_kg_m3=mixture_density(solved.streams["S-008"]),
                role="line",
            )["nps_in"]
        )

    def test_flange_class_in_b165_set(self, v101_datasheet: Datasheet) -> None:
        for n in v101_datasheet.nozzles:
            assert n.flange_class in (150, 300, 600, 900, 1500, 2500)
            assert n.nps_in > 0
            assert n.position_mm.x != 0 or n.position_mm.y != 0 or n.position_mm.z != 0


class TestVerticalSizers:
    def test_hand_checked_vertical_diameter(self) -> None:
        # Reuse the hand-checked Souders-Brown numbers: K=0.06, rhoL=1000,
        # rhoG=50, Q=0.5 -> v=0.261534, D_min=1.56004 -> rounds up to 1.65 m.
        from ngdesign.sizing.vessels import vertical_diameter

        got = vertical_diameter(gas_flow_m3_s=0.5, rho_gas=50.0, rho_liquid=1000.0, K_m_s=0.06)
        assert got["diameter_m"] == pytest.approx(1.65, abs=1e-9)
        assert got["v_max_m_s"] == pytest.approx(0.06 * math.sqrt(950 / 50), rel=1e-12)

    def test_registry_names(self) -> None:
        for name in ("separator_3phase", "scrubber", "teg_contactor"):
            plugin = cast(Sizer, registry.get("sizer", name))
            assert plugin.unit_kind == name

    def test_scrubber_sizer_on_solved_unit(self, thermo: Thermo) -> None:
        """A standalone scrubber sizes with the same convention as V-101."""
        fs = Flowsheet(
            name="scrub",
            units=[UnitSpec(tag="V-201", kind="scrubber", params={})],
            streams=[
                StreamSpec(
                    id="S-101",
                    target=PortRef(unit="V-201", port="inlet"),
                    service="PG",
                    feed=_slice_feed(),
                ),
                StreamSpec(id="S-102", source=PortRef(unit="V-201", port="gas_out"), service="PG"),
                StreamSpec(id="S-103", source=PortRef(unit="V-201", port="liquid_out"), service="PL"),
            ],
        )
        solved: SolvedFlowsheet = registry.create("solver", "sequential_modular").solve(fs, thermo)
        assert solved.converged
        sizer = registry.get("sizer", "scrubber")()
        sheet = sizer.size("V-201", solved, {})
        nozzle_ports = sorted(n.port for n in sheet.nozzles if n.port is not None)
        assert nozzle_ports == ["gas_out", "inlet", "liquid_out"]
        assert any(n.service == "psv" for n in sheet.nozzles)
        assert sheet.dimensions["diameter_m"] > 0

    def test_design_pressure_conversion_constant(self) -> None:
        # 1 psig in Pa -- anchors PA_PER_PSIG against the definition.
        assert PA_PER_PSIG == pytest.approx(6894.757293168, rel=1e-12)
