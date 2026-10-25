"""Closed-form, identity and refusal tests for the reciprocating_compressor R1 level.

Spec: ``specs/backend/units/reciprocating_compressor.md``.

Closed-form basis (hand-computed from the spec's equations, stage 1 of the
example case, bore 0.34 m, stroke 0.20 m, rod 0.06 m, N = 900 rpm):

- A_p = pi*0.34^2/4 = 0.0907920277 m^2; A_r = pi*0.06^2/4 = 0.00282743339 m^2
- PD = (2*A_p - A_r)*S*N/60 = (2*0.0907920277 - 0.00282743339)*0.20*900/60
     = 0.17875662201*3 = 0.536269866 m^3/s per cylinder (n_cyl = 1)
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.flow import reciprocating_compressor as r0_mod
from ngdesign.units.flow import reciprocating_compressor_r1 as r1_mod
from tests.conftest import flash_feed


@pytest.fixture
def basis(thermo: Thermo) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    """The example case: flashed inlets, R0 params on stage-1 clearance, R1 params."""
    feeds, r1_params = r1_mod.ReciprocatingCompressorR1.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    r0_params = {key: value for key, value in r1_params.items() if key not in ("cylinders", "speed_rpm")}
    r0_params["clearance"] = r1_params["cylinders"][0]["clearance"]
    return inlets, r0_params, r1_params


def test_example_case_solves(thermo: Thermo) -> None:
    """The R1 example solves to a fully specified outlet."""
    feeds, params = r1_mod.ReciprocatingCompressorR1.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, params, thermo)
    outlet = result.outlets["outlet"]
    assert outlet.T > 0.0 and outlet.P > 0.0 and outlet.molar_flow > 0.0


def test_reduces_to_r0(thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]) -> None:
    """Outlets, power and duty equal R0's exactly, for any geometry."""
    inlets, r0_params, r1_params = basis
    r0 = r0_mod.ReciprocatingCompressor().solve(inlets, r0_params, thermo)
    r1 = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    assert r1.outlets["outlet"] == r0.outlets["outlet"]
    assert r1.power_W == r0.power_W
    assert r1.duty_W == r0.duty_W


def test_volumetric_efficiency_reduces_to_r0_without_z_correction(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """With z_ratio_correction: false, stage-1 E_v is R0's formula exactly."""
    inlets, r0_params, r1_params = basis
    r0 = r0_mod.ReciprocatingCompressor().solve(inlets, r0_params, thermo)
    r1 = r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "z_ratio_correction": False}, thermo)
    assert r1.info["volumetric_efficiency_stage1"] == r0.info["volumetric_efficiency"]


def test_piston_displacement_closed_form(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Hand-computed PD (see module docstring): 0.536269866 / 0.360968996 m3/s."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    cyl1, cyl2 = r1_params["cylinders"]
    a_r = math.pi * cyl1["rod_diameter_m"] ** 2 / 4.0
    a_p1 = math.pi * cyl1["bore_m"] ** 2 / 4.0
    a_p2 = math.pi * cyl2["bore_m"] ** 2 / 4.0
    expected1 = (2.0 * a_p1 - a_r) * cyl1["stroke_m"] * r1_params["speed_rpm"] / 60.0
    expected2 = (2.0 * a_p2 - a_r) * cyl2["stroke_m"] * r1_params["speed_rpm"] / 60.0
    # Plan's printed values (geometric quantities, rel 1e-9).
    assert result.info["displacement_stage1_m3_s"] == pytest.approx(0.536269866, rel=1e-9)
    assert result.info["displacement_stage2_m3_s"] == pytest.approx(0.360968996, rel=1e-9)
    assert result.info["displacement_stage1_m3_s"] == pytest.approx(expected1, rel=1e-12)
    assert result.info["displacement_stage2_m3_s"] == pytest.approx(expected2, rel=1e-12)


def test_stage_table_thermo_quantities(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """E_v and capacity against the spec's independent-script table (rel 1e-7)."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    assert result.info["Q_suction_stage1_m3_s"] == pytest.approx(0.491529703, rel=1e-7)
    assert result.info["Q_suction_stage2_m3_s"] == pytest.approx(0.308587799, rel=1e-7)
    assert result.info["volumetric_efficiency_stage1"] == pytest.approx(0.939062958, rel=1e-7)
    assert result.info["volumetric_efficiency_stage2"] == pytest.approx(0.939750548, rel=1e-7)
    assert result.info["capacity_stage1_m3_s"] == pytest.approx(0.503591167, rel=1e-7)
    assert result.info["capacity_stage2_m3_s"] == pytest.approx(0.339220812, rel=1e-7)
    # Capacity exceeds the required suction flow on both stages.
    assert result.info["capacity_ratio_stage1"] > 1.0
    assert result.info["capacity_ratio_stage2"] > 1.0


def test_capacity_refusal_small_bore(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Stage-1 bore 0.30 m gives capacity 0.3903 < 0.4915 m3/s: refused."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    cylinders[0]["bore_m"] = 0.30
    with pytest.raises(r1_mod.RecipCapacityError, match="capacity"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)


def test_refuses_stage_cylinder_count_mismatch(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """One cylinder entry for two stages: refused."""
    inlets, _r0_params, r1_params = basis
    with pytest.raises(r1_mod.RecipR1SpecError, match="cylinders"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets, {**r1_params, "cylinders": r1_params["cylinders"][:1]}, thermo
        )


def test_refuses_rod_at_or_above_bore(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """rod_diameter_m >= bore_m is refused, naming the field and the stage."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    cylinders[0]["rod_diameter_m"] = cylinders[0]["bore_m"]
    with pytest.raises(r1_mod.RecipR1SpecError, match="rod_diameter_m"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)


def test_refuses_bad_action(thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]) -> None:
    """An acting type outside {double, single_head_end} is refused."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    cylinders[1]["action"] = "triple"
    with pytest.raises(r1_mod.RecipR1SpecError, match="action"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)


def test_refuses_clearance_key_at_r1(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """The R0 scalar clearance key is replaced by per-cylinder clearance."""
    inlets, _r0_params, r1_params = basis
    with pytest.raises(r1_mod.RecipR1SpecError, match="clearance"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "clearance": 0.05}, thermo)


# --- Step 2: gas rod loads and the clearance pocket -------------------------


def _r0_ratio(thermo: Thermo, inlets: dict[str, Any], r1_params: dict[str, Any]) -> float:
    """R0's pressure_ratio_per_stage (the ladder the re-traversal and rod loads use)."""
    r0_params = {key: value for key, value in r1_params.items() if key not in ("cylinders", "speed_rpm")}
    r0_params["clearance"] = r1_params["cylinders"][0]["clearance"]
    r0 = r0_mod.ReciprocatingCompressor().solve(inlets, r0_params, thermo)
    return float(r0.info["pressure_ratio_per_stage"])


def _stage_pressures(inlets: dict[str, Any], ratio: float, n: int) -> list[float]:
    """Stage boundary pressures: [P_s1, P_d1=P_s2, ..., P_dn]."""
    p_in = float(inlets["inlet"].P)
    return [p_in * ratio**i for i in range(n + 1)]


def test_rod_loads_double_acting_closed_form(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Stage-1 compression/tension loads match the hand-applied API 618 formula."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    cyl1 = r1_params["cylinders"][0]
    a_p = math.pi * cyl1["bore_m"] ** 2 / 4.0
    a_r = math.pi * cyl1["rod_diameter_m"] ** 2 / 4.0
    p_cc = 101325.0
    ratio = _r0_ratio(thermo, inlets, r1_params)
    p_s, p_d = _stage_pressures(inlets, ratio, int(r1_params["n_stages"]))[:2]
    f_compression = p_d * a_p - p_s * (a_p - a_r) - p_cc * a_r
    f_tension = -(p_s * a_p - p_d * (a_p - a_r) - p_cc * a_r)
    assert result.info["rod_load_compression_stage1_N"] == pytest.approx(f_compression, rel=1e-12)
    assert result.info["rod_load_tension_stage1_N"] == pytest.approx(f_tension, rel=1e-12)
    # The plan's printed rod loads (thermo-dependent, rel 1e-7), both stages.
    assert result.info["rod_load_compression_stage1_N"] == pytest.approx(173274.417, rel=1e-7)
    assert result.info["rod_load_tension_stage1_N"] == pytest.approx(149253.574, rel=1e-7)
    assert result.info["rod_load_compression_stage2_N"] == pytest.approx(183813.856, rel=1e-7)
    assert result.info["rod_load_tension_stage2_N"] == pytest.approx(146919.708, rel=1e-7)


def test_rod_loads_single_head_end_uses_crankcase(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Single-acting head end: the crank-end pressure is the crankcase pressure."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    # Single-acting halves stage-1 capacity, so add a second cylinder to keep
    # it above the required suction flow (otherwise the capacity refusal fires
    # before the rod loads are computed).
    cylinders[0]["action"] = "single_head_end"
    cylinders[0]["n_cylinders"] = 2
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)
    cyl1 = cylinders[0]
    a_p = math.pi * cyl1["bore_m"] ** 2 / 4.0
    p_cc = 101325.0
    ratio = _r0_ratio(thermo, inlets, r1_params)
    p_s, p_d = _stage_pressures(inlets, ratio, int(r1_params["n_stages"]))[:2]
    assert result.info["rod_load_compression_stage1_N"] == pytest.approx((p_d - p_cc) * a_p, rel=1e-12)
    assert result.info["rod_load_tension_stage1_N"] == pytest.approx(-(p_s - p_cc) * a_p, rel=1e-12)


def test_rod_load_limit_refusal_compression(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """A compression allowable 5% below the computed load is refused."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    load = result.info["rod_load_compression_stage2_N"]
    with pytest.raises(r1_mod.RecipRodLoadError, match="compression"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets, {**r1_params, "rod_load_limit_N": {"compression": 0.95 * load}}, thermo
        )


def test_rod_load_limit_refusal_tension(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """A tension allowable 5% below the computed load is refused."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    load = result.info["rod_load_tension_stage2_N"]
    with pytest.raises(r1_mod.RecipRodLoadError, match=r"rod load \(tension\)"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets, {**r1_params, "rod_load_limit_N": {"tension": 0.95 * load}}, thermo
        )


def test_rod_load_within_allowable_passes(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Allowables 10% above both computed loads do not raise."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    limits = {
        "compression": 1.10
        * max(
            result.info["rod_load_compression_stage1_N"],
            result.info["rod_load_compression_stage2_N"],
        ),
        "tension": 1.10
        * abs(
            min(
                result.info["rod_load_tension_stage1_N"],
                result.info["rod_load_tension_stage2_N"],
            )
        ),
    }
    r1 = r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "rod_load_limit_N": limits}, thermo)
    assert r1.info["rod_load_compression_stage1_N"] == result.info["rod_load_compression_stage1_N"]


def test_clearance_pocket_matches_flow(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Setting the clearance to the reported c_req drives capacity ratio to 1."""
    inlets, _r0_params, r1_params = basis
    first = r1_mod.ReciprocatingCompressorR1().solve(
        inlets, {**r1_params, "capacity_control": "clearance_pocket"}, thermo
    )
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    for i in (1, 2):
        cylinders[i - 1]["clearance"] = first.info[f"clearance_required_stage{i}"]
    second = r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)
    assert second.info["capacity_ratio_stage1"] == pytest.approx(1.0, rel=1e-9)
    assert second.info["capacity_ratio_stage2"] == pytest.approx(1.0, rel=1e-9)
    # Outlets are unchanged: the pocket changes capacity, not the balances.
    assert second.outlets["outlet"] == first.outlets["outlet"]


def test_clearance_pocket_infeasible_refusal(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Oversized cylinders need c_req >= 1: the pocket cannot trim that far."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    for c in cylinders:
        c["bore_m"] = 0.50
        c["clearance"] = 0.0
    with pytest.raises(r1_mod.RecipCapacityError, match="cannot be trimmed"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets,
            {
                **r1_params,
                "cylinders": cylinders,
                "capacity_control": "clearance_pocket",
            },
            thermo,
        )


def test_refuses_rod_load_limit_shape(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """A non-mapping rod_load_limit_N is refused, naming the parameter."""
    inlets, _r0_params, r1_params = basis
    with pytest.raises(r1_mod.RecipR1SpecError, match="rod_load_limit_N"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "rod_load_limit_N": 1.0e6}, thermo)


# --- Review round 1: every plan refusal is reached by a test -----------------


def test_refuses_speed_rpm_missing(thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]) -> None:
    """speed_rpm is required at R1."""
    inlets, _r0_params, r1_params = basis
    params = {key: value for key, value in r1_params.items() if key != "speed_rpm"}
    with pytest.raises(r1_mod.RecipR1SpecError, match="speed_rpm"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, params, thermo)


def test_refuses_speed_rpm_nonpositive(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """speed_rpm <= 0 is refused."""
    inlets, _r0_params, r1_params = basis
    with pytest.raises(r1_mod.RecipR1SpecError, match="speed_rpm"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "speed_rpm": 0.0}, thermo)


def test_refuses_bad_capacity_control(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """capacity_control outside {none, clearance_pocket} is refused."""
    inlets, _r0_params, r1_params = basis
    with pytest.raises(r1_mod.RecipR1SpecError, match="capacity_control"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets, {**r1_params, "capacity_control": "starvation"}, thermo
        )


def test_refuses_nonpositive_volumetric_efficiency(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """Clearance near 1 on stage 2 with a large loss allowance drives E_v <= 0.

    Stage-2 factor (Zs/Zd)*r^(1/k2) - 1 = 0.40283 (plan table stage-2 Zs/Zd
    0.874642142/0.885541882, k2 = 1.20058113), so clearance 0.99 with loss
    0.65 gives E_v = 1 - 0.65 - 0.99*0.40283 < 0. R0's own VE refusal only
    sees stage 1's clearance (0.10), so this reaches R1's stage-2 check.
    """
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    cylinders[1]["clearance"] = 0.99
    # Stage 1 must still deliver the flow at loss 0.65 (E_v1 = 1 - 0.65
    # - 0.10*0.40937 = 0.309), so five example cylinders: 5*0.53627*0.309
    # = 0.829 m3/s > Q_s1 0.4915 m3/s. Then stage 2's E_v goes negative.
    cylinders[0]["n_cylinders"] = 5
    with pytest.raises(r1_mod.RecipCapacityError, match="stage 2: volumetric efficiency"):
        r1_mod.ReciprocatingCompressorR1().solve(
            inlets, {**r1_params, "cylinders": cylinders, "loss_allowance": 0.65}, thermo
        )


@pytest.mark.parametrize(
    ("stage_index", "field", "value"),
    [
        (0, "bore_m", 0.0),
        (0, "stroke_m", 0.0),
        (0, "n_cylinders", 0),
        (0, "clearance", 1.0),
        (1, "bore_m", 0.0),
        (1, "clearance", -0.5),
    ],
)
def test_refuses_bad_geometry_names_field_and_stage(
    thermo: Thermo,
    basis: tuple[dict[str, Any], Any, dict[str, Any]],
    stage_index: int,
    field: str,
    value: float,
) -> None:
    """bore/stroke/n_cylinders <= 0 and clearance outside [0, 1) are refused,
    each naming the field and the stage."""
    inlets, _r0_params, r1_params = basis
    cylinders = [dict(c) for c in r1_params["cylinders"]]
    cylinders[stage_index][field] = value
    with pytest.raises(r1_mod.RecipR1SpecError, match=rf"stage {stage_index + 1}: {field}"):
        r1_mod.ReciprocatingCompressorR1().solve(inlets, {**r1_params, "cylinders": cylinders}, thermo)


def test_missing_z_factor_refusal_is_defensive_on_pr(
    thermo: Thermo, basis: tuple[dict[str, Any], Any, dict[str, Any]]
) -> None:
    """The missing-Z refusal cannot fire on the pr package: every vapour phase
    it builds carries z_factor (thermo/_state.py computes z on every gas phase,
    and the plan's table prints Z_s/Z_d for all four stage states). Asserted
    here as the measured evidence that the branch is a defensive guard."""
    inlets, _r0_params, r1_params = basis
    result = r1_mod.ReciprocatingCompressorR1().solve(inlets, r1_params, thermo)
    flashed = {
        port: flash_feed(thermo, feed)
        for port, feed in r1_mod.ReciprocatingCompressorR1.example_case()[0].items()
    }
    for port, state in {**inlets, **flashed}.items():
        for phase in state.phases:
            if phase.kind == "vapor":
                assert phase.z_factor is not None, f"{port} vapour phase has no z_factor"
    # And the solve itself succeeded with the correction on (default params).
    assert result.outlets["outlet"].P > 0.0
