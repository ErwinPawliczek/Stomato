"""Tests for the S-34 relief load and PSV sizing on the P&ID."""

from __future__ import annotations

import pytest
from thermo import ChemicalConstantsPackage

from ngdesign import registry
from ngdesign.contracts import (
    Direction,
    Flowsheet,
    Nozzle,
    PhaseKind,
    PidEquipment,
    PortRef,
    StreamSpec,
    UnitSpec,
    Vec3,
)
from ngdesign.data import components
from ngdesign.flowsheets.samples import sample_pid
from ngdesign.flowsheets.slice import MMSCFD_TO_MOL_S
from ngdesign.flowsheets.slice import build as build_slice
from ngdesign.pid_rules.psv_sizing import (
    _DEFAULT_BASIS,
    PsvSizing,
    VesselRelief,
    blocked_case,
    fire_case,
    relief_basis,
    size_psv,
)
from ngdesign.sizing.psv_gas import api526_orifice, psv_api520_gas

RULE = "psv_sizing"

#: S-09 API 520 correlation, evaluated in the probe run of the V-101 slice basis:
#: 50 MMSCFD load, vapor MW 19.705974858874683, Z 0.8863507971362715, ideal-gas
#: k 1.2437791845027308 at the 338.15 K design temperature, set at 4.0 MPa.
BLOCKED_AREA_IN2 = 2.6632501123105823


def _rule(**kwargs) -> PsvSizing:
    return registry.create("pid_rule", RULE, **kwargs)


def _sized_note(pid: object) -> str:
    """The note on the inline item referencing the first PSV valve."""
    for ln in pid.lines:  # type: ignore[attr-defined]
        for item in ln.items:
            if item.ref is not None and item.ref.startswith("PSV-"):
                return item.note
    return ""


def test_finds_unsized_psv_on_bare_sample() -> None:
    violations = _rule().check(sample_pid())
    assert len(violations) == 1
    assert violations[0].rule == RULE
    assert violations[0].target == "V-101"


def test_apply_sizes_then_clean_and_idempotent() -> None:
    rule = _rule()
    fixed = rule.apply(sample_pid())
    note = _sized_note(fixed)
    assert note.startswith("API 526 ")
    assert note == "API 526 L orifice (blocked outlet case governs, 2.663 in2 at 4.40 MPa)"
    assert rule.check(fixed) == []
    assert rule.apply(fixed).model_dump() == fixed.model_dump()


def test_default_basis_tracks_slice_feed() -> None:
    # The sample basis is the slice's V-101 feed: 50 MMSCFD (flowsheets/slice.py).
    assert _DEFAULT_BASIS["V-101"].blocked_load_mol_s == 50 * MMSCFD_TO_MOL_S


def test_blocked_case_matches_probe_oracle() -> None:
    basis = _DEFAULT_BASIS["V-101"]
    got = blocked_case(basis, set_pressure_Pa=4.0e6, design_temperature_K=338.15)
    assert got.case == "blocked outlet"
    assert got.relieving_pressure_Pa == pytest.approx(1.1 * 4.0e6)
    assert got.load_mol_s == 50 * MMSCFD_TO_MOL_S
    assert got.area_in2 == pytest.approx(BLOCKED_AREA_IN2, rel=1e-6)
    assert api526_orifice(got.area_in2) == "L"


def test_fire_case_from_spec_constants() -> None:
    basis = VesselRelief(
        blocked_load_mol_s=1.0,
        k=1.3,
        M_g_mol=18.0,
        Z=0.9,
        wetted_area_m2=10.0,
        latent_heat_J_mol=12000.0,
    )
    fire = fire_case(basis, set_pressure_Pa=4.0e6, design_temperature_K=338.15)
    assert fire is not None
    assert fire.relieving_pressure_Pa == pytest.approx(1.21 * 4.0e6)
    # Independent hand derivation from the spec constants (API 521, USC, F = 1):
    a_ft2 = 10.0 / 0.3048**2
    q_btu_h = 21000.0 * a_ft2**0.82
    q_w = q_btu_h * 1055.05585262 / 3600.0
    load_mol_s = q_w / 12000.0
    assert fire.load_mol_s == pytest.approx(load_mol_s)
    expected = psv_api520_gas(
        W_lb_h=load_mol_s * 18.0 * 3600.0 / (1000.0 * 0.45359237),
        T_R=338.15 * 9 / 5,
        Z=0.9,
        M=18.0,
        k=1.3,
        P1_psia=4.84e6 / (4.4482216152605 / 0.0254**2),
        Kd=0.975,
        Kb=1.0,
        Kc=1.0,
    )["area_in2"]
    assert fire.area_in2 == pytest.approx(expected)


def test_fire_case_skipped_without_datasheet() -> None:
    basis = VesselRelief(blocked_load_mol_s=100.0, k=1.3, M_g_mol=18.0, Z=0.9)
    assert fire_case(basis, set_pressure_Pa=4.0e6, design_temperature_K=338.15) is None
    got = size_psv(basis, set_pressure_Pa=4.0e6, design_temperature_K=338.15)
    assert [c.case for c in got.cases] == ["blocked outlet"]
    assert got.governing == "blocked outlet"
    assert got.orifice == api526_orifice(got.area_in2)


def test_fire_governs_when_larger() -> None:
    basis = VesselRelief(
        blocked_load_mol_s=1.0,
        k=1.3,
        M_g_mol=18.0,
        Z=0.9,
        wetted_area_m2=50.0,
        latent_heat_J_mol=5000.0,
    )
    got = size_psv(basis, set_pressure_Pa=1.0e6, design_temperature_K=350.0)
    assert got.governing == "fire"
    fire = next(c for c in got.cases if c.case == "fire")
    assert fire.relieving_pressure_Pa == pytest.approx(1.21e6)
    assert got.area_in2 == fire.area_in2
    assert got.orifice == api526_orifice(fire.area_in2)


def test_rule_uses_explicit_basis() -> None:
    basis = VesselRelief(
        blocked_load_mol_s=10.0,
        k=1.3,
        M_g_mol=18.0,
        Z=0.9,
        wetted_area_m2=5.0,
        latent_heat_J_mol=9000.0,
    )
    rule = _rule(basis={"V-101": basis})
    fixed = rule.apply(sample_pid())
    assert _sized_note(fixed).startswith("API 526 ")
    assert rule.check(fixed) == []
    expected = size_psv(basis, set_pressure_Pa=4.0e6, design_temperature_K=338.15)
    assert f"API 526 {expected.orifice} orifice" in _sized_note(fixed)
    assert expected.governing == "fire"


def test_rule_without_basis_for_tag_stays_flagged() -> None:
    rule = _rule(basis={})
    fixed = rule.apply(sample_pid())
    assert _sized_note(fixed) == ""
    violations = rule.check(fixed)
    assert [v.target for v in violations] == ["PSV-1001"]
    assert "no API 526 orifice" in violations[0].message
    assert rule.apply(fixed).model_dump() == fixed.model_dump()


def test_vessel_without_psv_nozzle_ignored() -> None:
    pid = sample_pid()
    pid.equipment.append(_ko_drum_without_psv_nozzle())
    violations = _rule().check(pid)
    assert all(v.target != "V-900" for v in violations)


def _ko_drum_without_psv_nozzle() -> PidEquipment:
    return PidEquipment(
        tag="V-900",
        kind="ko_drum",
        design_pressure_Pa=1.0e6,
        design_temperature_K=323.15,
        nozzles=[
            Nozzle(
                id="N1",
                service="inlet",
                port=None,
                nps_in=4,
                flange_class=150,
                position_mm=Vec3(x=0, y=0, z=1000),
                facing=Direction.W,
            )
        ],
    )


def _ideal_gas_k(composition: dict[str, float], T_K: float) -> float:
    """Ideal-gas k = Cp/(Cp - R) at T from thermo's HeatCapacityGases (test-side)."""
    comp = {c: z for c, z in composition.items() if z > 0}
    ids = sorted(comp)
    cas = [str(components()[c]["cas"]) for c in ids]
    _, corrs = ChemicalConstantsPackage.from_IDs(cas)
    cp = sum(z * corrs.HeatCapacityGases[ids.index(c)].T_dependent_property(T_K) for c, z in comp.items())
    return cp / (cp - 8.31446261815324)


def test_basis_from_solved_slice_v101() -> None:
    """Sized slice V-101: the real solved slice feed drives the relief basis."""
    feed = build_slice().inlets("V-101")[0]
    fs = Flowsheet(
        name="v101-only",
        units=[UnitSpec(tag="V-101", kind="separator_3phase", params={})],
        streams=[
            StreamSpec(
                id=feed.id,
                target=PortRef(unit="V-101", port="inlet"),
                service="PG",
                feed=feed.feed,
            )
        ],
    )
    thermo = registry.create("thermo", "pr")
    solved = registry.create("solver", "sequential_modular").solve(fs, thermo)
    s1 = solved.streams["S-001"]
    vapor = next(p for p in s1.phases if p.kind == PhaseKind.VAPOR)

    basis = relief_basis(solved, k_gas=_ideal_gas_k(vapor.composition, s1.T))
    assert set(basis) == {"V-101"}
    got = basis["V-101"]
    assert got.blocked_load_mol_s == 50 * MMSCFD_TO_MOL_S
    assert got.M_g_mol == pytest.approx(vapor.molecular_weight)
    assert got.Z == pytest.approx(vapor.z_factor)
    assert got.T_rel_K == pytest.approx(s1.T)

    rule = _rule(basis=basis)
    fixed = rule.apply(sample_pid())
    assert _sized_note(fixed).startswith("API 526 ")
    assert rule.check(fixed) == []
    assert rule.apply(fixed).model_dump() == fixed.model_dump()


def test_compose_with_vessel_psv() -> None:
    vessel_psv = registry.create("pid_rule", "vessel_psv")
    mine = _rule()
    # vessel_psv first, then sizing.
    pid = mine.apply(vessel_psv.apply(sample_pid()))
    assert vessel_psv.check(pid) == []
    assert mine.check(pid) == []
    # Reverse order reaches the same fixed point.
    pid = vessel_psv.apply(mine.apply(sample_pid()))
    assert vessel_psv.check(pid) == []
    assert mine.check(pid) == []
