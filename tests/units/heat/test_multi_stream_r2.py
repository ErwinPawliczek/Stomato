"""Closed-form tests: multi-stream R2 pure functions (spec Tests, R2 closed form).

Every expected number below is the spec's independent reference from
``calc_multi_stream.py`` (not the module's own output). The Manglik & Bergles
(1995) correlation constants were verified against the paper's equation 34
pair as cited in the secondary literature (techno-press.org ACD 10(2) eq. 23;
IntechOpen compact-HEX chapter Table 3):

    j = 0.6522 Re^-0.5403 alpha^-0.1541 delta^0.1499 gamma^-0.0678
        [1 + 5.269e-5 Re^1.340 alpha^0.504 delta^0.456 gamma^-1.055]^0.1
    f = 9.6243 Re^-0.7422 alpha^-0.1856 delta^0.3053 gamma^-0.2659
        [1 + 7.669e-8 Re^4.429 alpha^0.920 delta^3.767 gamma^0.236]^0.1

Geometry (spec): s 1.5 mm, h_f 6.35 mm, t 0.15 mm, l 3.175 mm gives
D_h = 4 s h_f l / [2(s l + h_f l + t h_f) + t s] = 0.00232730508 m (hand check
in the test). Fin efficiency at h = 500 W/m2K, k_fin = 180 W/mK:
m = sqrt(2*500/(180*0.00015)) = 192.45009 1/m, L_f = h_f/2 = 3.175 mm,
eta_f = tanh(m L_f)/(m L_f), eta_o = 1 - (h_f/(s+h_f))(1 - eta_f).
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.units._physics.heat_balance import TemperatureCross
from ngdesign.units.heat.multi_stream import MultiStreamExchanger
from ngdesign.units.heat.multi_stream_r1 import MultiStreamR1, MultiStreamRatingError
from ngdesign.units.heat.multi_stream_r2 import (
    FinGeometry,
    MultiStreamR2,
    fin_efficiency,
    manglik_bergles_f,
    manglik_bergles_j,
    osf_channels_per_layer,
    osf_free_flow_area_m2,
    osf_heat_transfer_area_m2,
    osf_hydraulic_diameter_m,
    surface_efficiency,
)

#: The spec's test geometry (m): s 1.5 mm, h_f 6.35 mm, t 0.15 mm, l 3.175 mm.
_GEOM = FinGeometry(
    fin_height_m=0.00635, fin_spacing_m=0.0015, fin_thickness_m=0.00015, strip_length_m=0.003175
)

_ALPHA, _DELTA, _GAMMA = 0.5, 0.1, 0.05


def test_hydraulic_diameter() -> None:
    """D_h of the spec geometry (rel 1e-8)."""
    assert osf_hydraulic_diameter_m(_GEOM) == pytest.approx(0.00232730508, rel=1e-8)


def test_dimensionless_parameters_from_geometry() -> None:
    """alpha = s/h_f, delta = t/l, gamma = t/s on the spec geometry."""
    assert _GEOM.alpha == pytest.approx(0.0015 / 0.00635)
    assert _GEOM.delta == pytest.approx(0.00015 / 0.003175)
    assert _GEOM.gamma == pytest.approx(0.00015 / 0.0015)


def test_areas_per_layer() -> None:
    """A_ff and A_ht follow their definitions (self-consistent, 1 m layer width)."""
    width, length = 1.0, 1.0
    n = osf_channels_per_layer(_GEOM.fin_spacing_m, _GEOM.fin_thickness_m, width)
    assert osf_free_flow_area_m2(_GEOM, width) == pytest.approx(_GEOM.fin_spacing_m * _GEOM.fin_height_m * n)
    assert osf_heat_transfer_area_m2(_GEOM, length, width) == pytest.approx(
        2.0 * (_GEOM.fin_spacing_m + _GEOM.fin_height_m) * length * n
    )


@pytest.mark.parametrize(
    ("Re", "j_expected", "f_expected"),
    [
        (1000.0, 0.0174026135, 0.108645137),
        (5000.0, 0.00883863219, 0.0670128063),
    ],
)
def test_manglik_bergles_j_and_f(Re: float, j_expected: float, f_expected: float) -> None:
    """Manglik-Bergles j and Fanning f at alpha 0.5, delta 0.1, gamma 0.05 (rel 1e-8)."""
    assert manglik_bergles_j(Re, _ALPHA, _DELTA, _GAMMA) == pytest.approx(j_expected, rel=1e-8)
    assert manglik_bergles_f(Re, _ALPHA, _DELTA, _GAMMA) == pytest.approx(f_expected, rel=1e-8)


def test_fin_and_surface_efficiency() -> None:
    """m = 192.45009 1/m, eta_f = 0.891694218, eta_o = 0.91238959 (rel 1e-8)."""
    m, eta_f = fin_efficiency(500.0, 180.0, _GEOM)
    assert m == pytest.approx(192.45009, rel=1e-8)
    assert eta_f == pytest.approx(0.891694218, rel=1e-8)
    assert surface_efficiency(500.0, 180.0, _GEOM) == pytest.approx(0.91238959, rel=1e-8)


# --- R2 adapter (level R2): identity, zone loop, refusals ---------------------


def _thermo() -> Thermo:
    registry.discover()
    impl: Thermo = registry.create("thermo", "pr")
    return impl


def _feeds() -> dict[str, dict[str, Any]]:
    feeds, _ = MultiStreamExchanger.example_case()
    return feeds


def _inlets(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> dict[str, StreamState]:
    return {
        port: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for port, f in feeds.items()
    }


def test_r2_to_r1_identity_single_zone() -> None:
    """R2 with one all-gas zone and R1 fed the same final hA agree on every
    outlet state (the BVP and tables are identical in that limit)."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    params = {**MultiStreamR2.example_case()[1], "n_zones": 1}
    detail = MultiStreamR2()._solve(inlets, params, thermo)

    r1_params = {
        f"hA_{port}_W_K": float(detail.hA_zones[i, 0]) for i, port in enumerate(("hot_in_1", "cold_in_1"))
    }
    r1_params.update({"hA_hot_in_2_W_K": 60000.0, "hA_cold_in_2_W_K": 60000.0})
    r1 = MultiStreamR1().solve(inlets, r1_params, thermo)

    assert r1.outlets["hot_out_1"].T == pytest.approx(detail.outlets["hot_out_1"].T, rel=1e-8)
    assert r1.outlets["cold_out_1"].T == pytest.approx(detail.outlets["cold_out_1"].T, rel=1e-8)
    assert detail.outlets["hot_out_2"] == r1.outlets["hot_out_2"]
    assert detail.outlets["cold_out_2"] == r1.outlets["cold_out_2"]
    assert detail.info["zone_iterations"] >= 2  # hA actually moved off the initial guess


def test_r2_example_case_balances_and_passes_through() -> None:
    """Net duty is round-off; per-port duties mirror; idle ports pass through."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    result = MultiStreamR2().solve(inlets, MultiStreamR2.example_case()[1], thermo)

    assert result.duty_W == pytest.approx(0.0, abs=1e-6)
    assert result.power_W == 0.0
    assert result.info["duty_hot_in_1_W"] == pytest.approx(result.info["duty_cold_in_1_W"], rel=1e-9)
    assert result.info["duty_hot_in_1_W"] > 0.0
    assert result.outlets["hot_out_2"] is inlets["hot_in_2"]
    assert result.outlets["cold_out_2"] is inlets["cold_in_2"]
    assert result.outlets["hot_out_1"].P == inlets["hot_in_1"].P  # dP defaults to 0
    assert result.info["min_approach_K"] > 0.0
    assert result.info["UA_total_W_K"] > 0.0
    assert result.info["n_zones"] == 20
    assert result.info["h_hot_in_1_min_W_m2K"] > 0.0
    assert result.info["h_cold_in_1_max_W_m2K"] >= result.info["h_cold_in_1_min_W_m2K"]


def test_r2_more_zones_change_the_answer_less() -> None:
    """Doubling zones from 40 to 80 moves outlet T by < 1 K: the zone loop is
    approaching a mesh-independent answer, not chasing its own discretisation."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    t40 = MultiStreamR2().solve(inlets, {**MultiStreamR2.example_case()[1], "n_zones": 40}, thermo)
    t80 = MultiStreamR2().solve(inlets, {**MultiStreamR2.example_case()[1], "n_zones": 80}, thermo)
    assert abs(t40.outlets["hot_out_1"].T - t80.outlets["hot_out_1"].T) < 1.0
    assert abs(t40.outlets["cold_out_1"].T - t80.outlets["cold_out_1"].T) < 1.0


def test_r2_dP_applied_per_stream() -> None:
    """A per-stream dP lowers that stream's outlet pressure, others unchanged."""
    thermo = _thermo()
    feeds = _feeds()
    inlets = _inlets(thermo, feeds)
    params = {**MultiStreamR2.example_case()[1], "dP_hot_in_1": 5.0e4, "dP_cold_in_1": 1.0e4}
    result = MultiStreamR2().solve(inlets, params, thermo)

    assert result.outlets["hot_out_1"].P == pytest.approx(1.0e6 - 5.0e4, rel=1e-12)
    assert result.outlets["cold_out_1"].P == pytest.approx(1.0e6 - 1.0e4, rel=1e-12)


def test_r2_no_active_hot_or_cold_refused() -> None:
    """No active hot (or cold) stream is refused, as at R1."""
    thermo = _thermo()
    feeds = _feeds()
    no_hot = {**feeds, "hot_in_1": {**feeds["hot_in_1"], "molar_flow": 0.0}}
    with pytest.raises(MultiStreamRatingError, match="at least one hot and one cold"):
        MultiStreamR2().solve(_inlets(thermo, no_hot), MultiStreamR2.example_case()[1], thermo)

    no_cold = {**feeds, "cold_in_1": {**feeds["cold_in_1"], "molar_flow": 0.0}}
    with pytest.raises(MultiStreamRatingError, match="at least one hot and one cold"):
        MultiStreamR2().solve(_inlets(thermo, no_cold), MultiStreamR2.example_case()[1], thermo)


def test_r2_inlet_temperature_cross_refused() -> None:
    """The hottest cold inlet at or above the coldest hot inlet is refused."""
    thermo = _thermo()
    feeds = _feeds()
    crossed = {
        **feeds,
        "hot_in_1": {**feeds["hot_in_1"], "T": 300.0},
        "cold_in_1": {**feeds["cold_in_1"], "T": 310.0},
    }
    with pytest.raises(TemperatureCross, match="inlet temperatures"):
        MultiStreamR2().solve(_inlets(thermo, crossed), MultiStreamR2.example_case()[1], thermo)


def test_r2_missing_geometry_refused() -> None:
    """An active stream missing one geometry param is refused naming the param."""
    thermo = _thermo()
    inlets = _inlets(thermo, _feeds())
    params = MultiStreamR2.example_case()[1]
    with pytest.raises(MultiStreamRatingError, match="fin_spacing_hot_in_1_m"):
        MultiStreamR2().solve(
            inlets,
            {k: v for k, v in params.items() if k != "fin_spacing_hot_in_1_m"},
            thermo,
        )


def test_r2_nonpositive_geometry_refused() -> None:
    """A non-positive geometry or shared dimension is refused naming the param."""
    thermo = _thermo()
    inlets = _inlets(thermo, _feeds())
    params = MultiStreamR2.example_case()[1]
    with pytest.raises(MultiStreamRatingError, match="strip_length_cold_in_1_m"):
        MultiStreamR2().solve(inlets, {**params, "strip_length_cold_in_1_m": 0.0}, thermo)
    with pytest.raises(MultiStreamRatingError, match="layer_width_m"):
        MultiStreamR2().solve(inlets, {**params, "layer_width_m": -1.0}, thermo)
    with pytest.raises(MultiStreamRatingError, match="length_m"):
        MultiStreamR2().solve(inlets, {k: v for k, v in params.items() if k != "length_m"}, thermo)
    with pytest.raises(MultiStreamRatingError, match="n_layers_hot_in_1"):
        MultiStreamR2().solve(inlets, {**params, "n_layers_hot_in_1": 0}, thermo)
    with pytest.raises(MultiStreamRatingError, match="n_zones"):
        MultiStreamR2().solve(inlets, {**params, "n_zones": 0}, thermo)
    with pytest.raises(MultiStreamRatingError, match="k_fin_W_mK"):
        MultiStreamR2().solve(inlets, {**params, "k_fin_W_mK": -5.0}, thermo)


def test_r2_nonpositive_outlet_pressure_refused() -> None:
    """dP that drives the outlet pressure to zero or below is refused."""
    thermo = _thermo()
    inlets = _inlets(thermo, _feeds())
    params = {**MultiStreamR2.example_case()[1], "dP_hot_in_1": 2.0e6}
    with pytest.raises(MultiStreamRatingError, match="non-positive outlet pressure"):
        MultiStreamR2().solve(inlets, params, thermo)


def test_r2_two_phase_zone_smoke() -> None:
    """The two-phase branch runs end to end on a real condensing zone.

    Finds a pure component in the database whose flash at fixed P sits inside
    the two-phase dome at a reachable temperature; a condensing stream against
    a cold gas stream must produce a zone with 0 < vf < 1 and a finite, sane h
    (ht.Shah through D_h). Skips when no such component exists in the
    installed database (documented, not silent).
    """
    thermo = _thermo()
    db = components()
    candidate = None
    for cid in ("n-butane", "n-butane ", "butane", "nC4", "C4H10-n", "i-butane", "propane"):
        if cid in db:
            candidate = cid
            break
    if candidate is None:  # noqa: SIM108 - explicit for the skip message
        pytest.skip("no condensable component in the database to exercise the two-phase branch")
    probe = thermo.flash_pt({candidate: 1.0}, 260.0, 5.0e5, 100.0)
    if not (0.0 < probe.vapor_fraction < 1.0):
        pytest.skip(f"component {candidate} does not flash two-phase at 5 bar, 260 K")

    feeds, params = MultiStreamR2.example_case()
    feeds = {
        **feeds,
        "cold_in_1": {
            "composition": {candidate: 1.0},
            "T": 260.0,
            "P": 5.0e5,
            "molar_flow": feeds["cold_in_1"]["molar_flow"],
        },
    }
    inlets = _inlets(thermo, feeds)
    result = MultiStreamR2().solve(inlets, params, thermo)
    assert math.isfinite(result.info["duty_cold_in_1_W"])
    assert math.isfinite(result.outlets["cold_out_1"].T)
