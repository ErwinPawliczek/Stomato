"""Own tests for the P&ID builder (spec S-33).

The locked sample slice cannot be solved end to end right now: the TEG
contactor convergence is a pending decision and the e2e demo stays xfail
(tests/e2e/test_slice.py).  The solved flowsheets below are therefore
hand-built from the slice topology with realistic stream states taken from
the slice basis comments (50 MMSCFD wet gas, 3.447 MPa / 20 C into V-101,
compression to 7.0 MPa, TEG contactor, HC liquid letdown through P-101).
When the slice solves for real, the e2e test exercises this same builder.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import (
    PID,
    Datasheet,
    Direction,
    FeedSpec,
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
from ngdesign.contracts.pid import LINE_NO_RE
from ngdesign.contracts.plugins import PidRule
from ngdesign.data import components
from ngdesign.flowsheets.slice import INLET_COMPOSITION, LEAN_TEG_COMPOSITION, MMSCFD_TO_MOL_S
from ngdesign.flowsheets.slice import build as build_slice
from ngdesign.pid_rules import builder
from ngdesign.pid_rules.builder import DefaultPidBuilder
from ngdesign.pid_rules.psv_sizing import PsvSizing, relief_basis

#: Mol/s of the slice's 50 MMSCFD feed (slice.py basis).
N_FEED = 50.0 * MMSCFD_TO_MOL_S

#: Hand-set flowing densities (kg/m3) for the fixture phases; only the
#: volumetric flow and mixture density enter line sizing.
_DENSITY = {PhaseKind.VAPOR: 20.0, PhaseKind.HC_LIQUID: 600.0, PhaseKind.AQUEOUS: 1050.0}

_GAS_Z = {c: x for c, x in INLET_COMPOSITION.items() if c != "H2O"} | {"H2O": 0.001}
_HC_Z = {"C3": 0.05, "iC4": 0.04, "nC4": 0.06, "iC5": 0.04, "nC5": 0.05, "C6+": 0.76}
_RICH_TEG_Z = {"TEG": 0.75, "H2O": 0.25}


_REAL_SIZER_LOOKUP = builder._sizer_for


@pytest.fixture(autouse=True)
def _no_registered_sizers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin tests to the builder's default (no-sizer) path.

    Sibling sizer plugins (S-31/S-32) register on main and would otherwise
    take precedence over the deterministic fixture expectations here; tests
    that need the real plugins (or their own fake) override this stub."""
    monkeypatch.setattr(builder, "_sizer_for", lambda kind: None)


@pytest.fixture()
def _real_sizers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt a test back into the sizer plugins registered on the tree.

    The composition tests are integration tests: the vessels' psv nozzles are
    owned by their sizer datasheets (S-14) and psv_sizing sizes the relief
    from them, so the rules cannot reach a clean check on the no-sizer path."""
    monkeypatch.setattr(builder, "_sizer_for", _REAL_SIZER_LOOKUP)


def _renorm(z: dict[str, float]) -> dict[str, float]:
    total = sum(z.values())
    return {c: x / total for c, x in z.items()}


def _mw(z: dict[str, float]) -> float:
    comps = components()
    return sum(x * float(comps[c]["mw"]) for c, x in z.items())


def _phase(kind: PhaseKind, mole_fraction: float, z: dict[str, float], density: float) -> Phase:
    z = _renorm(z)
    return Phase(
        kind=kind,
        mole_fraction=mole_fraction,
        composition=z,
        density=density,
        molecular_weight=_mw(z),
        # PR gas Z at these conditions (hand value): relief_basis (S-34) needs it.
        z_factor=0.9 if kind == PhaseKind.VAPOR else None,
    )


def _state(T: float, P: float, n: float, z: dict[str, float], *phases: Phase) -> StreamState:
    vapor = next((p.mole_fraction for p in phases if p.kind == PhaseKind.VAPOR), 0.0)
    return StreamState(
        T=T,
        P=P,
        molar_flow=n,
        composition=_renorm(z),
        vapor_fraction=vapor,
        enthalpy=0.0,
        entropy=0.0,
        phases=list(phases),
    )


def _slice_states() -> dict[str, StreamState]:
    """One realistic state per slice stream, from the slice basis comments."""
    n_gas = 0.987 * N_FEED
    n_hc = 0.011 * N_FEED
    n_water = 0.002 * N_FEED
    return {
        # V-101 feed: vapor + HC liquid + free water (slice.py basis comment).
        "S-001": _state(
            293.15,
            3.447e6,
            N_FEED,
            INLET_COMPOSITION,
            _phase(PhaseKind.VAPOR, 0.987, _GAS_Z, 28.7),
            _phase(PhaseKind.HC_LIQUID, 0.011, _HC_Z, 700.0),
            _phase(PhaseKind.AQUEOUS, 0.002, {"H2O": 1.0}, 1000.0),
        ),
        "S-002": _state(293.15, 3.44e6, n_gas, _GAS_Z, _phase(PhaseKind.VAPOR, 1.0, _GAS_Z, 28.7)),
        "S-003": _state(423.15, 7.0e6, n_gas, _GAS_Z, _phase(PhaseKind.VAPOR, 1.0, _GAS_Z, 40.8)),
        "S-004": _state(322.15, 6.965e6, n_gas, _GAS_Z, _phase(PhaseKind.VAPOR, 1.0, _GAS_Z, 62.1)),
        "S-005": _state(322.15, 6.9e6, n_gas, _GAS_Z, _phase(PhaseKind.VAPOR, 1.0, _GAS_Z, 61.5)),
        "S-006": _state(
            325.15,
            7.1e6,
            3.2,
            dict(LEAN_TEG_COMPOSITION),
            _phase(PhaseKind.AQUEOUS, 1.0, LEAN_TEG_COMPOSITION, 1075.0),
        ),
        "S-007": _state(326.15, 6.9e6, 3.9, _RICH_TEG_Z, _phase(PhaseKind.AQUEOUS, 1.0, _RICH_TEG_Z, 1040.0)),
        "S-008": _state(293.15, 3.4e6, n_hc, _HC_Z, _phase(PhaseKind.HC_LIQUID, 1.0, _HC_Z, 700.0)),
        "S-009": _state(294.15, 1.5e6, n_hc, _HC_Z, _phase(PhaseKind.HC_LIQUID, 1.0, _HC_Z, 700.0)),
        "S-010": _state(333.15, 1.45e6, n_hc, _HC_Z, _phase(PhaseKind.HC_LIQUID, 1.0, _HC_Z, 680.0)),
        "S-011": _state(
            293.15, 3.3e6, n_water, {"H2O": 1.0}, _phase(PhaseKind.AQUEOUS, 1.0, {"H2O": 1.0}, 1000.0)
        ),
    }


def _slice_units() -> dict[str, UnitResult]:
    """Unit results as the S-30 solver would report them for the states above:
    same info keys the S-30 unit plugins write, positive shaft power/duty,
    because the S-31/S-32 sizers read them back and reject zero-power solves."""
    n_hc = 0.011 * N_FEED
    q_pump = n_hc * _mw(_HC_Z) / 1000.0 / 700.0  # HC liquid volumetric flow, m3/s
    d_pump = 3.4e6 - 1.5e6  # P-101 head rise, Pa
    return {
        "V-101": UnitResult(outlets={}),
        "K-101": UnitResult(
            outlets={},
            power_W=1.5e6,
            info={
                "T_out_isentropic": 337.9,
                "pressure_ratio": 7.0e6 / 3.44e6,
                "polytropic_head_J_kg": 1676.0,
            },
        ),
        "E-101": UnitResult(outlets={}, duty_W=-2.6e6),
        "T-101": UnitResult(outlets={}),
        "P-101": UnitResult(
            outlets={},
            power_W=q_pump * d_pump / 0.65,
            info={"head_m": d_pump / (700.0 * 9.81), "Q_m3_s": q_pump},
        ),
        "E-102": UnitResult(outlets={}, duty_W=5.3e4),
    }


def _solved_slice() -> SolvedFlowsheet:
    fs = build_slice()
    # The locked slice carries no utility temperatures for E-102 (a design
    # decision, not a simulation result); the test supplies them the way the
    # end-to-end flow must when the shell_tube sizer runs for real.
    units = [
        u.model_copy(update={"params": {**u.params, "utility_T_in": 422.0, "utility_T_out": 415.0}})
        if u.tag == "E-102"
        else u
        for u in fs.units
    ]
    fs = fs.model_copy(update={"units": units})
    return SolvedFlowsheet(
        flowsheet=fs,
        streams=_slice_states(),
        units=_slice_units(),
        converged=True,
        iterations=1,
    )


def _built() -> PID:
    return DefaultPidBuilder().build(_solved_slice())


def _mini_solved(phase: Phase, T: float, P: float, z: dict[str, float], service: str) -> SolvedFlowsheet:
    """One heater with a feed and a product: the minimal solved flowsheet for
    pipe-class selection checks."""
    unit = UnitSpec(tag="E-201", kind="heater", params={})
    fs = Flowsheet(
        name="mini",
        units=[unit],
        streams=[
            StreamSpec(
                id="S-101",
                target=PortRef(unit="E-201", port="inlet"),
                service=service,
                feed=FeedSpec(T=T, P=P, molar_flow=100.0, composition=_renorm(z)),
            ),
            StreamSpec(id="S-102", source=PortRef(unit="E-201", port="outlet"), service=service),
        ],
    )
    state = _state(T, P, 100.0, z, phase)
    return SolvedFlowsheet(
        flowsheet=fs,
        streams={"S-101": state, "S-102": state.model_copy()},
        units={"E-201": UnitResult(outlets={"outlet": state})},
        converged=True,
        iterations=1,
    )


def test_builder_registered_as_default() -> None:
    assert registry.get("pid_builder", "default") is DefaultPidBuilder


def test_slice_pid_valid_and_complete() -> None:
    pid = _built()
    fs = _solved_slice().flowsheet
    assert [e.tag for e in pid.equipment] == [u.tag for u in fs.units]
    assert len(pid.lines) == len(fs.streams)
    assert [ln.stream_id for ln in pid.lines] == [s.id for s in fs.streams]
    assert len({ln.stream_id for ln in pid.lines}) == len(fs.streams)
    for ln in pid.lines:
        assert LINE_NO_RE.match(ln.number), ln.number
    assert pid.valves == [] and pid.instruments == []  # bare: the rules add these


def test_line_numbers_run_from_1001_in_stream_order() -> None:
    pid = _built()
    services = {s.id: s.service for s in _solved_slice().flowsheet.streams}
    for i, ln in enumerate(pid.lines):
        parts = ln.number.split("-")
        assert int(parts[-2]) == 1001 + i
        assert parts[-1] == ln.pipe_class
        assert parts[0] == f'{ln.nps_in:g}"'
        assert parts[1] == services[ln.stream_id]  # fluid code from StreamSpec.service


def test_line_ends_hit_port_nozzles_or_boundaries() -> None:
    pid = _built()
    fs = _solved_slice().flowsheet
    by_tag = {e.tag: e for e in pid.equipment}
    for stream, ln in zip(fs.streams, pid.lines, strict=True):
        for ref, end in ((stream.source, ln.start), (stream.target, ln.end)):
            if ref is None:
                assert end.boundary == f"BL-{stream.id}"
            else:
                assert end.equipment == ref.unit
                noz = next(n for n in by_tag[ref.unit].nozzles if n.id == end.nozzle)
                assert noz.port == ref.port


def test_design_conditions_max_of_equipment_ends() -> None:
    pid = _built()
    conds = {e.tag: (e.design_pressure_Pa, e.design_temperature_K) for e in pid.equipment}
    # Pinned to the no-sizer path (autouse fixture): equipment design
    # conditions are the max operating P/T over connected streams (the
    # fixture states above).
    assert conds["K-101"] == (pytest.approx(7.0e6), pytest.approx(423.15))
    assert conds["V-101"][0] == pytest.approx(3.447e6)
    by_stream = {ln.stream_id: ln for ln in pid.lines}
    # S-003 (K-101 -> E-101): both ends at 7.0 MPa, 423 K -> class-600 D1.
    assert by_stream["S-003"].design_pressure_Pa == pytest.approx(7.0e6)
    assert by_stream["S-003"].design_temperature_K == pytest.approx(423.15)
    assert by_stream["S-003"].pipe_class == "D1"
    # S-002 (V-101 -> K-101): the compressor end governs the max -> D1 too.
    assert by_stream["S-002"].pipe_class == "D1"
    # Sweet low-pressure lines stay carbon steel class 300.
    assert by_stream["S-008"].pipe_class == "B1"
    assert by_stream["S-010"].design_pressure_Pa == pytest.approx(1.5e6)
    assert by_stream["S-010"].pipe_class == "B1"


@pytest.mark.parametrize(
    ("kind", "T", "P", "z", "service", "expected"),
    [
        (PhaseKind.VAPOR, 300.0, 2.0e6, {"C1": 0.8, "C2": 0.2}, "PG", "B1"),
        (PhaseKind.HC_LIQUID, 240.0, 2.0e6, {"C3": 1.0}, "PL", "L1"),
        (PhaseKind.AQUEOUS, 300.0, 2.0e6, {"MDEA": 0.75, "H2O": 0.25}, "GL", "S1"),
        (PhaseKind.VAPOR, 300.0, 2.0e6, {"H2S": 0.3, "C1": 0.7}, "PG", "S1"),
    ],
    ids=("default-B1", "cold-L1", "amine-S1", "sour-S1"),
)
def test_pipe_class_selection(
    kind: PhaseKind, T: float, P: float, z: dict[str, float], service: str, expected: str
) -> None:
    solved = _mini_solved(_phase(kind, 1.0, z, _DENSITY[kind]), T, P, z, service)
    pid = DefaultPidBuilder().build(solved)
    assert [ln.pipe_class for ln in pid.lines] == [expected, expected]


def test_default_nozzles_cover_every_declared_port() -> None:
    pid = _built()
    by_tag = {e.tag: e for e in pid.equipment}
    for spec in _solved_slice().flowsheet.units:
        cls = registry.get("unit", spec.kind)
        for port in (*cls.inlet_ports, *cls.outlet_ports):
            nozzles = [n for n in by_tag[spec.tag].nozzles if n.port == port]
            assert len(nozzles) == 1, (spec.tag, port)


def test_pressure_vessel_psv_nozzles_come_from_datasheets(_real_sizers: None) -> None:
    pid = _built()
    for eq in pid.equipment:
        psv = [n for n in eq.nozzles if n.service == "psv"]
        if eq.kind in ("separator_3phase", "teg_contactor"):
            assert len(psv) == 1, eq.tag  # the sizers own the psv nozzles (S-14)
        else:
            assert psv == [], eq.tag


def test_machine_nozzles_use_conventional_services() -> None:
    pid = _built()
    by_tag = {e.tag: e for e in pid.equipment}
    # K-101 is the sample's only machine: the authorized data correction
    # turned P-101 into a jt_valve (inlet/outlet ports, no sizer).
    for tag in ("K-101",):
        services = {n.service: n.port for n in by_tag[tag].nozzles}
        assert services == {"suction": "inlet", "discharge": "outlet"}


class _StubVesselSizer:
    """Stand-in sizer for separator_3phase (the real S-31 sizer lands later)."""

    unit_kind = "separator_3phase"

    def size(self, tag: str, solved: SolvedFlowsheet, params: dict[str, Any]) -> Datasheet:
        return Datasheet(
            tag=tag,
            kind=self.unit_kind,
            design_pressure_Pa=4.0e6,
            design_temperature_K=338.15,
            dimensions={"diameter": 1.5, "length_tt": 6.0},
            nozzles=[
                Nozzle(
                    id="N1",
                    service="inlet",
                    port=None,
                    nps_in=8.0,
                    flange_class=300,
                    position_mm=Vec3(x=0, y=0, z=1500),
                    facing=Direction.W,
                ),
                Nozzle(
                    id="N2",
                    service="gas_out",
                    port=None,
                    nps_in=8.0,
                    flange_class=300,
                    position_mm=Vec3(x=5000, y=0, z=2600),
                    facing=Direction.UP,
                ),
                Nozzle(
                    id="N3",
                    service="hc_out",
                    port=None,
                    nps_in=2.0,
                    flange_class=300,
                    position_mm=Vec3(x=3500, y=0, z=0),
                    facing=Direction.DOWN,
                ),
                Nozzle(
                    id="N4",
                    service="water_out",
                    port=None,
                    nps_in=2.0,
                    flange_class=300,
                    position_mm=Vec3(x=4500, y=0, z=0),
                    facing=Direction.DOWN,
                ),
                Nozzle(
                    id="N5",
                    service="psv",
                    port=None,
                    nps_in=3.0,
                    flange_class=300,
                    position_mm=Vec3(x=2500, y=0, z=2600),
                    facing=Direction.UP,
                ),
            ],
            notes=[],
        )


def test_datasheet_nozzles_adopted_and_conditions_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        builder, "_sizer_for", lambda kind: _StubVesselSizer() if kind == "separator_3phase" else None
    )
    pid = _built()
    v101 = next(e for e in pid.equipment if e.tag == "V-101")
    # Datasheet design conditions, not the stream maxima.
    assert v101.design_pressure_Pa == pytest.approx(4.0e6)
    assert v101.design_temperature_K == pytest.approx(338.15)
    # The sizer's portless nozzles were adopted: ports filled, positions kept.
    by_port = {n.port: n for n in v101.nozzles if n.port is not None}
    assert set(by_port) == {"inlet", "gas_out", "hc_out", "water_out"}
    assert by_port["inlet"].position_mm.z == pytest.approx(1500.0)
    # Exactly one psv nozzle: the sizer provided it, the builder adds none.
    assert len([n for n in v101.nozzles if n.service == "psv"]) == 1
    # S-001 (feed -> V-101) takes the vessel's datasheet design pressure.
    s001 = next(ln for ln in pid.lines if ln.stream_id == "S-001")
    assert s001.design_pressure_Pa == pytest.approx(4.0e6)
    assert s001.pipe_class == "B1"


def test_prepopulated_datasheet_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_kind: str) -> None:
        raise AssertionError("sizer lookup must not run when the solved flowsheet carries a datasheet")

    solved = _solved_slice()
    solved.datasheets["V-101"] = Datasheet(
        tag="V-101",
        kind="separator_3phase",
        design_pressure_Pa=4.2e6,
        design_temperature_K=350.0,
        dimensions={},
        nozzles=[],
        notes=[],
    )
    monkeypatch.setattr(
        builder,
        "_sizer_for",
        lambda kind: fail if kind == "separator_3phase" else None,
    )
    pid = DefaultPidBuilder().build(solved)
    v101 = next(e for e in pid.equipment if e.tag == "V-101")
    assert v101.design_pressure_Pa == pytest.approx(4.2e6)
    # An empty datasheet nozzle table falls back to default nozzles per port.
    assert {n.port for n in v101.nozzles if n.port is not None} == {"inlet", "gas_out", "hc_out", "water_out"}
    # No synthetic psv nozzle: the sizers own those (S-14) and this unit's
    # datasheet is empty here.
    assert not any(n.service == "psv" for n in v101.nozzles)


def test_unsolved_stream_is_an_error() -> None:
    solved = _solved_slice()
    del solved.streams["S-002"]
    with pytest.raises(ValueError, match="S-002"):
        DefaultPidBuilder().build(solved)


def test_unflashed_stream_is_an_error() -> None:
    solved = _solved_slice()
    solved.streams["S-002"] = solved.streams["S-002"].model_copy(update={"phases": []})
    with pytest.raises(ValueError, match="S-002"):
        DefaultPidBuilder().build(solved)


def test_non_fluid_code_service_is_an_error() -> None:
    solved = _mini_solved(
        _phase(PhaseKind.VAPOR, 1.0, {"C1": 1.0}, 15.0), 300.0, 2.0e6, {"C1": 1.0}, "process"
    )
    with pytest.raises(ValueError, match="S-101"):
        DefaultPidBuilder().build(solved)


_K_GAS = 1.24  # ideal-gas Cp/Cv of the relieving vapor; S-34 assigns k to the caller


def _rules() -> list[tuple[str, PidRule]]:
    """The production rule set for the solved slice: every registered rule,
    with psv_sizing carrying the relief basis built from the solved fixture
    (the registry default knows only the S-34 sample's V-101)."""
    basis = relief_basis(_solved_slice(), k_gas=_K_GAS)
    return [
        (name, PsvSizing(basis=basis) if name == "psv_sizing" else registry.create("pid_rule", name))
        for name in registry.available("pid_rule")
    ]


def test_every_registered_rule_applies_clean(_real_sizers: None) -> None:
    pid = _built()
    for name, rule in _rules():
        assert rule.check(rule.apply(pid)) == [], name


def test_rules_compose_to_a_clean_fixed_point(_real_sizers: None) -> None:
    pid = _built()
    for _ in range(5):
        before = pid.model_dump()
        for _name, rule in _rules():
            pid = rule.apply(pid)
        if pid.model_dump() == before:
            break
    else:
        pytest.fail("rules did not reach a fixed point in 5 passes")
    for name, rule in _rules():
        assert rule.check(pid) == [], name


def test_renderer_consumes_builder_output() -> None:
    pid = _built()
    svg = registry.create("diagram", "pid").render(pid)
    assert "<svg" in svg
