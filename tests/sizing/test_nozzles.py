"""Tests for the shared nozzle helpers (spec P0-05).

Covers the reconciled behaviour where the two former copies differed: the
``role`` default on ``nozzle_nps_in`` (machines.py required it, vessels.py
defaulted to ``"line"``) and the port-map return type of ``connected``.
"""

from __future__ import annotations

import pytest

from ngdesign.contracts import (
    Direction,
    Flowsheet,
    Nozzle,
    Phase,
    PhaseKind,
    PortRef,
    SolvedFlowsheet,
    StreamSpec,
    StreamState,
    UnitResult,
    UnitSpec,
    Vec3,
)
from ngdesign.sizing._nozzles import (
    PA_PER_PSIG,
    connected,
    min_flange_class,
    mixture_density,
    nozzle,
    nozzle_nps_in,
    volumetric_flow,
)
from ngdesign.sizing.flange_rating import min_flange_class as b16_5_min_flange_class
from ngdesign.sizing.line_size import line_size


def _liquid_state(T: float = 300.0, P: float = 1.0e6, molar_flow: float = 100.0) -> StreamState:
    """Single liquid phase: 100 mol/s at MW 62 g/mol and rho 850 kg/m3."""
    phase = Phase(
        kind=PhaseKind.HC_LIQUID,
        mole_fraction=1.0,
        composition={"C1": 1.0},
        density=850.0,
        molecular_weight=62.0,
    )
    return StreamState(
        T=T,
        P=P,
        molar_flow=molar_flow,
        composition={"C1": 1.0},
        vapor_fraction=0.0,
        enthalpy=-1.0e4,
        entropy=80.0,
        phases=[phase],
    )


def _solved_two_units() -> SolvedFlowsheet:
    flowsheet = Flowsheet(
        name="p005-fixture",
        units=[UnitSpec(tag="P-101", kind="pump"), UnitSpec(tag="E-101", kind="air_cooler")],
        streams=[
            StreamSpec(
                id="S-001",
                source=PortRef(unit="P-101", port="outlet"),
                target=PortRef(unit="E-101", port="inlet"),
                service="PL",
            )
        ],
    )
    state = _liquid_state()
    return SolvedFlowsheet(
        flowsheet=flowsheet,
        streams={"S-001": state},
        units={
            "P-101": UnitResult(outlets={}, duty_W=0.0, power_W=1.0e4),
            "E-101": UnitResult(outlets={}, duty_W=1.0e5, power_W=0.0),
        },
        converged=True,
    )


# ---------------------------------------------------------------- volumetric_flow / mixture_density


def test_volumetric_flow_sums_phase_mass_over_density() -> None:
    state = _liquid_state()
    mass_kg_s = state.molar_flow * 62.0 / 1000.0
    assert volumetric_flow(state) == pytest.approx(mass_kg_s / 850.0)


def test_volumetric_flow_empty_phases_raises() -> None:
    state = _liquid_state()
    empty = state.model_copy(update={"phases": []})
    with pytest.raises(ValueError, match="no phases"):
        volumetric_flow(empty)


def test_mixture_density_is_mass_over_volume() -> None:
    state = _liquid_state()
    assert mixture_density(state) == pytest.approx(850.0)


def test_mixture_density_zero_flow_raises() -> None:
    state = _liquid_state(molar_flow=0.0)
    with pytest.raises(ValueError, match="zero volumetric flow"):
        mixture_density(state)


# ------------------------------------------------------------------------ connected


def test_connected_maps_every_port_of_the_unit() -> None:
    solved = _solved_two_units()
    pump_ports = connected(solved, "P-101")
    assert set(pump_ports) == {"outlet"}
    spec, state = pump_ports["outlet"]
    assert spec.id == "S-001" and state is solved.streams["S-001"]

    ex_ports = connected(solved, "E-101")
    assert set(ex_ports) == {"inlet"}
    assert ex_ports["inlet"][0].id == "S-001"


def test_connected_unit_without_streams_is_empty() -> None:
    solved = _solved_two_units()
    assert connected(solved, "E-101") is not None  # sanity: dict type
    lone = SolvedFlowsheet(
        flowsheet=Flowsheet(
            name="lone",
            units=[UnitSpec(tag="V-101", kind="scrubber")],
            streams=[],
        ),
        streams={},
        units={"V-101": UnitResult(outlets={}, duty_W=0.0, power_W=0.0)},
        converged=True,
    )
    assert connected(lone, "V-101") == {}


# ---------------------------------------------------------------------- nozzle_nps_in


def test_nps_matches_line_size_with_default_role() -> None:
    state = _liquid_state()
    expected = line_size(
        service="PL", flow_m3_s=volumetric_flow(state), rho_kg_m3=mixture_density(state), role="line"
    )["nps_in"]
    # Reconciled signature: role defaults to "line" (the machines.py copy had no default).
    assert nozzle_nps_in("PL", state) == pytest.approx(float(expected))
    assert nozzle_nps_in("PL", state) == nozzle_nps_in("PL", state, role="line")


def test_nps_suction_role_differs_from_line_for_liquid() -> None:
    state = _liquid_state()
    line_nps = nozzle_nps_in("PL", state, role="line")
    suction_nps = nozzle_nps_in("PL", state, role="suction")
    # Suction limits are tighter, so they never pick a smaller NPS than the line limits.
    assert suction_nps >= line_nps


def test_nps_unknown_service_raises() -> None:
    with pytest.raises(ValueError, match="unknown service"):
        nozzle_nps_in("XX", _liquid_state())


# --------------------------------------------------------------------- min_flange_class


def test_min_flange_class_converts_to_b165_units() -> None:
    design_p_pa, design_t_k = 3.5e6, 350.0
    psig = design_p_pa / PA_PER_PSIG
    temp_f = (design_t_k - 273.15) * 9.0 / 5.0 + 32.0
    assert min_flange_class(design_p_pa, design_t_k, "1.1") == b16_5_min_flange_class("1.1", psig, temp_f)


def test_min_flange_class_monotonic_in_pressure() -> None:
    low = min_flange_class(1.0e6, 320.0, "1.1")
    high = min_flange_class(8.0e6, 320.0, "1.1")
    assert high >= low


# ----------------------------------------------------------------------------- nozzle


def test_nozzle_builds_mm_geometry() -> None:
    n = nozzle(3, "vent", None, 2.0, Vec3(x=0.0, y=0.1, z=0.3), Direction.UP, 300)
    assert isinstance(n, Nozzle)
    assert n.id == "N3"
    assert n.service == "vent"
    assert n.port is None
    assert n.nps_in == 2.0
    assert n.flange_class == 300
    assert n.position_mm == Vec3(x=0.0, y=100.0, z=300.0)
    assert n.facing == Direction.UP


def test_nozzle_carries_process_port() -> None:
    n = nozzle(1, "PG", "inlet", 6.0, Vec3(x=-0.5, y=0.0, z=0.0), Direction.W, 150)
    assert n.port == "inlet"
    assert n.id == "N1"
