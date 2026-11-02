"""multi_stream R2 tests; closed forms from the spec's calc_multi_stream.py."""

from __future__ import annotations

from typing import Any

import ht
import pytest

from ngdesign.contracts import PhaseKind
from ngdesign.contracts.plugins import Thermo
from ngdesign.data import components
from ngdesign.units.heat.multi_stream_r1 import MultiStreamR1, MultiStreamRatingError
from ngdesign.units.heat.multi_stream_r2 import (
    Layers,
    MultiStreamR2,
    fin_efficiency,
    manglik_bergles_j,
    plate_fin_dh,
    stream_h,
    surface_efficiency,
)
from ngdesign.units.heat.rating import PropertyUnavailable, film_props


@pytest.mark.parametrize(("re", "j"), [(1000.0, 0.0174026135), (5000.0, 0.00883863219)])
def test_manglik_bergles_j(re: float, j: float) -> None:
    assert manglik_bergles_j(re, 0.5, 0.1, 0.05) == pytest.approx(j, rel=1e-8)


def test_hydraulic_diameter() -> None:
    assert plate_fin_dh(1.5e-3, 6.35e-3, 1.5e-4, 3.175e-3) == pytest.approx(0.00232730508, rel=1e-8)


def test_fin_and_surface_efficiency() -> None:
    """h 500, k_f 180, t 0.15 mm, h_f 6.35 mm: m = 192.45009 1/m, eta_f 0.891694218."""
    eta_f = fin_efficiency(500.0, 180.0, 1.5e-4, 6.35e-3)
    assert eta_f == pytest.approx(0.891694218, rel=1e-8)
    assert surface_efficiency(eta_f, 1.5e-3, 6.35e-3) == pytest.approx(0.91238959, rel=1e-8)


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = MultiStreamR2.example_case()
    return {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}


def test_one_zone_reduces_to_r1(thermo: Thermo) -> None:
    """One zone, single phase: R1 at R2's own conductances gives R2's outlets."""
    inlets = _inlets(thermo)
    params = {**MultiStreamR2.example_case()[1], "n_zones": 1}
    r2 = MultiStreamR2().solve(inlets, params, thermo)
    r1_params = {f"hA_{p}_W_K": r2.info[f"hA_{p}_W_K"] for p in ("hot_in_1", "cold_in_1")}
    r1 = MultiStreamR1().solve(inlets, r1_params, thermo)
    for port in ("hot_out_1", "cold_out_1"):
        assert r2.outlets[port].T == pytest.approx(r1.outlets[port].T, rel=1e-8)


def test_duties_balance_with_zones(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    res = MultiStreamR2().solve(inlets, MultiStreamR2.example_case()[1], thermo)
    assert res.info["duty_hot_in_1_W"] == pytest.approx(res.info["duty_cold_in_1_W"], rel=1e-6)
    assert res.info["h_hot_in_1_max_W_m2K"] >= res.info["h_hot_in_1_min_W_m2K"] > 0.0
    assert res.info["zone_iterations"] >= 1.0


def test_two_hot_ports_need_their_geometry(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    inlets["hot_in_2"] = thermo.flash_pt({"N2": 1.0}, 450.0, 1.0e6, 100.0)
    with pytest.raises(MultiStreamRatingError, match="n_layers_hot_in_2"):
        MultiStreamR2().solve(inlets, MultiStreamR2.example_case()[1], thermo)


def _condenser(thermo: Thermo) -> tuple[dict[str, Any], dict[str, Any]]:
    inlets = {
        "hot_in_1": thermo.flash_pt({"C3": 1.0}, 330.0, 1.0e6, 2.0),
        "hot_in_2": thermo.flash_pt({"C3": 1.0}, 330.0, 1.0e6, 0.0),
        "cold_in_1": thermo.flash_pt({"N2": 1.0}, 280.0, 1.0e6, 40.0),
        "cold_in_2": thermo.flash_pt({"N2": 1.0}, 280.0, 1.0e6, 0.0),
    }
    params: dict[str, Any] = {"layer_width_m": 0.3, "length_m": 1.0, "n_zones": 4}
    for port, layers in (("hot_in_1", 6), ("cold_in_1", 6)):
        params.update(
            {
                f"n_layers_{port}": layers,
                f"fin_height_{port}_m": 6.35e-3,
                f"fin_spacing_{port}_m": 1.5e-3,
                f"fin_thickness_{port}_m": 1.5e-4,
                f"strip_length_{port}_m": 3.175e-3,
            }
        )
    return inlets, params


def test_condensing_stream_changes_phase_and_balances(thermo: Thermo) -> None:
    inlets, params = _condenser(thermo)
    res = MultiStreamR2().solve(inlets, params, thermo)
    assert res.outlets["hot_out_1"].vapor_fraction < 1.0
    assert res.info["duty_hot_in_1_W"] == pytest.approx(res.info["duty_cold_in_1_W"], rel=1e-6)
    assert res.info["h_hot_in_1_max_W_m2K"] > res.info["h_hot_in_1_min_W_m2K"]


LAYERS = Layers(
    n_layers=6,
    fin_height_m=6.35e-3,
    fin_spacing_m=1.5e-3,
    fin_thickness_m=1.5e-4,
    strip_length_m=3.175e-3,
    width_m=0.3,
    length_m=1.0,
    k_fin=180.0,
)


def _two_phase(thermo: Thermo) -> tuple[Any, Any, Any, float, float]:
    """A C3/nC4 mixture at vf 0.5: state, liquid, vapour, mass quality, Kay's Pc."""
    state = thermo.flash_pvf({"C3": 0.9, "nC4": 0.1}, 1.0e6, 0.5, 2.0)
    liquid = next(p for p in state.phases if p.kind is not PhaseKind.VAPOR)
    vapour = next(p for p in state.phases if p.kind is PhaseKind.VAPOR)
    mv = vapour.mole_fraction * vapour.molecular_weight
    x = mv / (mv + liquid.mole_fraction * liquid.molecular_weight)
    db = components()
    return state, liquid, vapour, x, 0.9 * float(db["C3"]["pc_Pa"]) + 0.1 * float(db["nC4"]["pc_Pa"])


def test_condensing_h_is_shah_per_channel(thermo: Thermo) -> None:
    """Wiring by hand: mass flow per channel, D_h, mass quality, and the mixture Pc."""
    state, liquid, _, x, pc = _two_phase(thermo)
    film = film_props(thermo, dict(liquid.composition), state.T, state.P, liquid.kind)
    per_channel = 0.08 / (6 * 0.3 / 1.65e-3)
    expected = ht.Shah(
        per_channel,
        x,
        plate_fin_dh(1.5e-3, 6.35e-3, 1.5e-4, 3.175e-3),
        film.rho_kg_m3,
        film.mu_Pa_s,
        film.k_W_mK,
        film.cp_J_kgK,
        state.P,
        pc,
    )
    assert stream_h(LAYERS, state, True, 280.0, thermo, 0.08) == pytest.approx(expected, rel=1e-9)


def test_boiling_h_is_liu_winterton_with_the_wall_superheat(thermo: Thermo) -> None:
    state, liquid, vapour, x, pc = _two_phase(thermo)
    film = film_props(thermo, dict(liquid.composition), state.T, state.P, liquid.kind)
    expected = ht.Liu_Winterton(
        0.08 / (6 * 0.3 / 1.65e-3),
        x,
        plate_fin_dh(1.5e-3, 6.35e-3, 1.5e-4, 3.175e-3),
        film.rho_kg_m3,
        vapour.density,
        film.mu_Pa_s,
        film.k_W_mK,
        film.cp_J_kgK,
        liquid.molecular_weight,
        state.P,
        pc,
        5.0,
    )
    assert stream_h(LAYERS, state, False, state.T + 5.0, thermo, 0.08) == pytest.approx(expected, rel=1e-9)


def test_single_phase_h_is_colburn(thermo: Thermo) -> None:
    """h = j*G*cp*Pr**(-2/3) by hand from the same film and the spec's j."""
    state = thermo.flash_pt({"N2": 1.0}, 300.0, 1.0e6, 40.0)
    film = film_props(thermo, dict(state.composition), state.T, state.P, state.phases[0].kind)
    mass = float(state.mass_flow)
    g = mass / LAYERS.free_flow_m2
    re = g * LAYERS.d_h / film.mu_Pa_s
    j = manglik_bergles_j(re, 1.5 / 6.35, 1.5e-4 / 3.175e-3, 0.1)
    expected = j * g * film.cp_J_kgK * film.Pr ** (-2.0 / 3.0)
    assert stream_h(LAYERS, state, True, 280.0, thermo, mass) == pytest.approx(expected, rel=1e-9)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"layer_width_m": 0.0}, "layer_width_m"),
        ({"length_m": -1.0}, "length_m"),
        ({"fin_height_hot_in_1_m": 0.0}, "fin_height_hot_in_1_m"),
        ({"n_zones": 0}, "n_zones"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {**MultiStreamR2.example_case()[1], **change}
    with pytest.raises(MultiStreamRatingError, match=match):
        MultiStreamR2().solve(_inlets(thermo), params, thermo)


def test_missing_transport_property_is_named(thermo: Thermo) -> None:
    class NoTransport:
        def __getattr__(self, name: str) -> Any:
            return getattr(thermo, name)

        def phase_props(self, *args: Any, **kwargs: Any) -> Any:
            return thermo.phase_props(*args, **kwargs).model_copy(update={"viscosity": None})

    with pytest.raises(PropertyUnavailable, match="viscosity"):
        MultiStreamR2().solve(_inlets(thermo), MultiStreamR2.example_case()[1], NoTransport())
