"""separator_3phase R1 tests (spec separator_3phase.md): closed form, identity, balances, refusals.

Constant checks: g = 9.80665 m/s2 lives in the Stokes owner
(``decanter_r1.stokes_velocity``); the segment area is fluids'
``A_partial_circle``, cross-checked below against the exact closed forms
``A(R/2) = R^2 (pi/3 - sqrt(3)/4)`` and ``A(R) = pi R^2 / 2``.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.separator_3phase_r1 import (
    Separator3PhaseR1,
    Separator3PhaseR1SpecError,
    capture_fraction,
    layer_areas,
    stokes_cut_diameter_m,
)
from ngdesign.units.separator import Separator3Phase
from tests.conftest import flash_feed

GEOMETRY = {"diameter_m": 1.5, "length_m": 4.5, "liquid_level_m": 0.75, "interface_level_m": 0.3}


class TestClosedFormHorizontal:
    """Hand-computed horizontal case (spec T1-T8), rtol 1e-9.

    D = 2 m (R = 1), L = 6 m, NLL h_l = 1.0 m (centre line), NIL h_i = 0.5 m;
    Q_o = 0.01, Q_w = 0.005, Q_G = 1 m3/s; rho_o = 800, rho_w = 1000 kg/m3;
    mu_o = 2e-3, mu_w = 1e-3 Pa s; g = 9.80665 m/s2.

    T1: A(0.5) = acos(0.5) - 0.5 sqrt(1 - 0.25) = pi/3 - sqrt(3)/4
        = 1.047197551 - 0.433012702 = 0.614184849 m2 = A_w;
        A(1.0) = pi/2 = 1.570796327; A_o = pi/6 + sqrt(3)/4 = 0.956611477;
        A_g = pi - pi/2 = 1.570796327 m2.
    T2: t_o = 0.956611477 * 6 / 0.01 = 573.966886 s;
        t_w = 0.614184849 * 6 / 0.005 = 737.021819 s.
    T6: water in oil, H_o = 0.5: v_req = 0.5/573.966886 = 8.71130e-4 m/s,
        d = sqrt(18 * 2e-3 * 8.71130e-4 / (9.80665 * 200)) = 1.26449611e-4 m.
        Oil in water, H_w = 0.5: v_req = 0.5/737.021819 = 6.78406e-4 m/s,
        d = sqrt(18 * 1e-3 * 6.78406e-4 / (9.80665 * 200)) = 7.89052221e-5 m.
    T5/T7: water drop d = 100 um in oil: u_t = 9.80665 * 1e-8 * 200 / (18 * 2e-3)
        = 5.44813889e-4 m/s (Re = 0.0218); s = u_t t_o = 0.312705132 m;
        h = 0.812705132: acos(1 - h) = 1.382388772, sqrt(2h - h^2) = 0.982303737,
        A(h) = 1.382388772 - 0.187294868 * 0.982303737 = 1.198408322;
        eta_wo = (1.198408322 - 0.614184849) / 0.956611477 = 0.610721789.
        Oil drop d = 50 um in water: u_t = 9.80665 * 2.5e-9 * 200 / 0.018
        = 2.72406944e-4 m/s; s = u_t t_w = 0.200769862 m; h = 0.299230138:
        acos(1 - h) = 0.794320238, sqrt(2h - h^2) = 0.713387413,
        A(h) = 0.794320238 - 0.700769862 * 0.713387413 = 0.294399839;
        eta_ow = (0.614184849 - 0.294399839) / 0.614184849 = 0.520665742.
    T8: E_w = 0.1 -> f_w = 0.1 * 0.389278211 = 0.0389278211;
        E_o = 0.05 -> f_o = 0.05 * 0.479334258 = 0.0239667129.
    """

    D, L, HL, HI = 2.0, 6.0, 1.0, 0.5

    def test_chain(self) -> None:
        areas = layer_areas("horizontal", self.D, self.HL, self.HI)
        assert areas["A_water_m2"] == pytest.approx(math.pi / 3 - math.sqrt(3) / 4, rel=1e-12)
        assert areas["A_oil_m2"] == pytest.approx(0.956611477490518, rel=1e-9)
        assert areas["A_gas_m2"] == pytest.approx(math.pi / 2, rel=1e-12)
        t_o = areas["A_oil_m2"] * self.L / 0.01
        t_w = areas["A_water_m2"] * self.L / 0.005
        assert t_o == pytest.approx(573.966886494, rel=1e-9)
        assert t_w == pytest.approx(737.021819165, rel=1e-9)
        assert stokes_cut_diameter_m(0.5 / t_o, 1000.0, 800.0, 2e-3) == pytest.approx(
            1.26449611133e-4, rel=1e-9
        )
        assert stokes_cut_diameter_m(0.5 / t_w, 1000.0, 800.0, 1e-3) == pytest.approx(
            7.89052220872e-5, rel=1e-9
        )
        u_w = 9.80665 * (100e-6) ** 2 * 200.0 / (18.0 * 2e-3)
        u_o = 9.80665 * (50e-6) ** 2 * 200.0 / (18.0 * 1e-3)
        eta_wo = capture_fraction("horizontal", self.D, self.HL, self.HI, u_w * t_o, "oil")
        eta_ow = capture_fraction("horizontal", self.D, self.HL, self.HI, u_o * t_w, "water")
        assert eta_wo == pytest.approx(0.610721789283, rel=1e-9)
        assert eta_ow == pytest.approx(0.520665741962, rel=1e-9)
        assert 0.1 * (1.0 - eta_wo) == pytest.approx(0.0389278210717, rel=1e-9)
        assert 0.05 * (1.0 - eta_ow) == pytest.approx(0.0239667129019, rel=1e-9)

    def test_full_capture_bounds(self) -> None:
        """A drop that crosses the whole layer is fully captured; s = 0 captures none."""
        assert capture_fraction("horizontal", self.D, self.HL, self.HI, 0.6, "oil") == 1.0
        assert capture_fraction("horizontal", self.D, self.HL, self.HI, 0.6, "water") == 1.0
        assert capture_fraction("horizontal", self.D, self.HL, self.HI, 0.0, "oil") == 0.0


class TestClosedFormVertical:
    """Vertical: D = 1 m, oil pad H_o = 0.5 m, Q_o = 1e-3 m3/s, mu_o = 2e-3, rho 800/1000.

    A = pi/4 = 0.785398163 m2; t_o = A H_o / Q_o = 392.699082 s;
    v_req = H_o/t_o = Q_o/A = 1.27323954e-3 m/s;
    d_cut = sqrt(18 * 2e-3 * 1.27323954e-3 / (9.80665 * 200)) = 1.52873065e-4 m.
    Capture is a step at s = H_o (counter-current plug flow).
    """

    def test_vertical(self) -> None:
        areas = layer_areas("vertical", 1.0, 0.8, 0.3)
        assert areas == {"A_gas_m2": math.pi / 4, "A_oil_m2": math.pi / 4, "A_water_m2": math.pi / 4}
        t_o = areas["A_oil_m2"] * 0.5 / 1e-3
        assert t_o == pytest.approx(392.699081699, rel=1e-9)
        assert stokes_cut_diameter_m(0.5 / t_o, 1000.0, 800.0, 2e-3) == pytest.approx(
            1.52873065390e-4, rel=1e-9
        )
        assert capture_fraction("vertical", 1.0, 0.8, 0.3, 0.5, "oil") == 1.0
        assert capture_fraction("vertical", 1.0, 0.8, 0.3, 0.4999, "oil") == 0.0
        assert capture_fraction("vertical", 1.0, 0.8, 0.3, 0.3, "water") == 1.0


def _inlets(thermo: Thermo) -> dict[str, StreamState]:
    feeds, _ = Separator3Phase.example_case()
    return {"inlet": flash_feed(thermo, feeds["inlet"])}


def _example_params() -> dict[str, Any]:
    return Separator3PhaseR1.example_case()[1]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"dP": 0.0},
        dict(GEOMETRY),
        {**GEOMETRY, "orientation": "vertical", "length_m": 3.0},
        {**_example_params(), "water_in_oil_fraction": 0.0, "oil_in_water_fraction": 0.0},
        {**_example_params(), "water_droplet_diameter_m": 50e-6, "oil_droplet_diameter_m": 40e-6},
    ],
)
def test_identity_with_r0(thermo: Thermo, params: dict[str, Any]) -> None:
    """No geometry, no droplets, zero entrainment or full capture: R0's outlets and duty exactly."""
    inlets = _inlets(thermo)
    r0 = Separator3Phase().solve(inlets, {}, thermo)
    r1 = Separator3PhaseR1().solve(inlets, params, thermo)
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W
    assert r1.power_W == 0.0


def test_rating_info(thermo: Thermo) -> None:
    res = Separator3PhaseR1().solve(_inlets(thermo), dict(GEOMETRY), thermo)
    info = res.info
    assert info["v_ratio"] == pytest.approx(info["v_gas_m_s"] / info["v_max_m_s"], rel=1e-14)
    assert info["v_gas_m_s"] == pytest.approx(info["Q_gas_m3_s"] / info["A_gas_m2"], rel=1e-14)
    assert info["t_res_oil_s"] == pytest.approx(info["A_oil_m2"] * 4.5 / info["Q_oil_m3_s"], rel=1e-14)
    assert info["gas_settling_velocity_m_s"] == pytest.approx(info["v_gas_m_s"] * 0.75 / 4.5, rel=1e-14)
    assert "eta_water_in_oil" not in info


def test_carryover_balances(thermo: Thermo) -> None:
    """V0 with liquid-liquid carry-over: moles at 1e-9 of the feed, energy closure at 1e-8.

    The R0 split itself closes components only to ~3.4e-11 of the feed flow on
    this case (PR flash convergence), so moles are checked at 1e-9, inside the
    U-R2 V0 bound of 1e-8.
    """
    inlets = _inlets(thermo)
    r0 = Separator3Phase().solve(inlets, {}, thermo)
    res = Separator3PhaseR1().solve(inlets, _example_params(), thermo)
    assert 0.0 < res.info["eta_water_in_oil"] < 1.0
    assert 0.0 < res.info["eta_oil_in_water"] < 1.0
    inlet = inlets["inlet"]
    for cid, n_in in inlet.component_flows().items():
        n_out = sum(s.component_flows().get(cid, 0.0) for s in res.outlets.values())
        assert n_out == pytest.approx(n_in, rel=0.0, abs=1e-9 * inlet.molar_flow)
    h_in = inlet.enthalpy * inlet.molar_flow
    h_out = sum(s.enthalpy * s.molar_flow for s in res.outlets.values())
    assert h_in + res.duty_W == pytest.approx(h_out, rel=1e-8)
    assert res.outlets["gas_out"] == r0.outlets["gas_out"]
    hc_water = res.outlets["hc_out"].component_flows()["H2O"]
    assert hc_water > r0.outlets["hc_out"].component_flows().get("H2O", 0.0)
    f_w = res.info["carryover_water_to_oil_kg_s"] / r0.outlets["water_out"].mass_flow
    assert f_w == pytest.approx(0.1 * (1.0 - res.info["eta_water_in_oil"]), rel=1e-12)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"orientation": "sideways"}, "orientation"),
        ({"length_m": None}, "requires"),
        ({"diameter_m": -1.0}, "diameter_m"),
        ({"length_m": 0.0}, "length_m"),
        ({"interface_level_m": 0.8}, "interface_level_m"),
        ({"liquid_level_m": 1.5}, "liquid_level_m"),
        ({"orientation": "vertical", "length_m": 0.7}, "liquid_level_m"),
        ({"water_in_oil_fraction": 1.2}, "water_in_oil_fraction"),
        ({"oil_droplet_diameter_m": None}, "oil_droplet_diameter_m"),
        ({"water_in_oil_fraction": None}, "water_in_oil_fraction"),
        ({"K_m_s": 0.0}, "K_m_s"),
        ({"oil_viscosity_Pa_s": -1.0}, "oil_viscosity_Pa_s"),
        ({"water_droplet_diameter_m": 2e-3}, "Stokes"),
        ({"diameter_m": "big"}, "diameter_m"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    params = {k: v for k, v in {**_example_params(), **change}.items() if v is not None}
    with pytest.raises(Separator3PhaseR1SpecError, match=match):
        Separator3PhaseR1().solve(_inlets(thermo), params, thermo)


def test_droplets_without_geometry_refused(thermo: Thermo) -> None:
    with pytest.raises(Separator3PhaseR1SpecError, match="geometry"):
        Separator3PhaseR1().solve(
            _inlets(thermo), {"water_in_oil_fraction": 0.1, "water_droplet_diameter_m": 1e-5}, thermo
        )


def test_missing_phase_refused(thermo: Thermo) -> None:
    """A dry feed has no water outlet: rating refuses, the R0 identity path does not."""
    inlet = thermo.flash_pt({"C1": 0.9, "nC5": 0.1}, 300.0, 3.0e6, 1.0)
    r0 = Separator3Phase().solve({"inlet": inlet}, {}, thermo)
    assert Separator3PhaseR1().solve({"inlet": inlet}, {}, thermo).outlets == r0.outlets
    with pytest.raises(Separator3PhaseR1SpecError, match="all three"):
        Separator3PhaseR1().solve({"inlet": inlet}, dict(GEOMETRY), thermo)


def test_viscosity_needed_when_absent(thermo: Thermo) -> None:
    class Bare:
        def __getattr__(self, name: str) -> Any:
            return getattr(thermo, name)

        def flash_pt(self, *args: Any) -> Any:
            state = thermo.flash_pt(*args)
            return state.model_copy(
                update={"phases": [p.model_copy(update={"viscosity": None}) for p in state.phases]}
            )

    inlets = _inlets(thermo)
    with pytest.raises(Separator3PhaseR1SpecError, match="gas_viscosity_Pa_s"):
        Separator3PhaseR1().solve(inlets, dict(GEOMETRY), Bare())
    res = Separator3PhaseR1().solve(
        inlets,
        {**GEOMETRY, "gas_viscosity_Pa_s": 1e-5, "oil_viscosity_Pa_s": 2e-4, "water_viscosity_Pa_s": 1e-3},
        Bare(),
    )
    assert res.info["mu_oil_Pa_s"] == 2e-4


def test_inverted_densities_refused(thermo: Thermo) -> None:
    class Swapped:
        def __getattr__(self, name: str) -> Any:
            return getattr(thermo, name)

        def flash_pt(self, *args: Any) -> Any:
            state = thermo.flash_pt(*args)
            return state.model_copy(
                update={
                    "phases": [
                        p.model_copy(update={"density": 500.0}) if p.kind.value == "aqueous" else p
                        for p in state.phases
                    ]
                }
            )

    with pytest.raises(Separator3PhaseR1SpecError, match="denser"):
        Separator3PhaseR1().solve(_inlets(thermo), dict(GEOMETRY), Swapped())
