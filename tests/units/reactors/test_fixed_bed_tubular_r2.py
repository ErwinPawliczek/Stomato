"""fixed_bed_tubular R2 tests (``specs/backend/units/fixed_bed_tubular.md``)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors.fixed_bed_tubular import FixedBedError, FixedBedTubularR2
from ngdesign.units.reactors.pfr import PfrR2

EMPTY: dict[str, Any] = {"id": "inert", "components": ["N2"], "reactions": []}


def _ideal() -> Thermo:
    registry.discover()
    raw: Thermo = registry.create("thermo", "ideal-raoult")
    return raw


def _params(flow: str, **coolant: float) -> dict[str, Any]:
    return {
        "reaction_set": EMPTY,
        "n_tubes": 1,
        "tube_diameter_m": 0.05,
        "length_m": 5.0,
        "U_W_m2K": 5.0,
        "coolant": {"mass_flow_kg_s": 1.0e-3, "cp_J_kgK": 4180.0, "T_in_K": 300.0, "flow": flow, **coolant},
    }


@pytest.mark.parametrize(
    ("flow", "t_tube", "t_coolant", "q"),
    [
        # Incropera epsilon-NTU with C_t = 2.92127371, C_c = 4.18 W/K, NTU = 1.3442735.
        ("counter", 303.763492, 304.358504, 18.2185465),  # epsilon = 0.623650789
        ("co", 304.713554, 303.694535, 15.4431565),  # epsilon = 0.528644626
    ],
)
def test_inert_exchanger_matches_epsilon_ntu(flow: str, t_tube: float, t_coolant: float, q: float) -> None:
    thermo = _ideal()
    inlet = thermo.flash_pt({"N2": 1.0}, 310.0, 2.0e5, 0.1)
    res = FixedBedTubularR2().solve({"inlet": inlet}, _params(flow), thermo)
    assert res.outlets["outlet"].T == pytest.approx(t_tube, abs=2e-3)
    assert res.info["coolant_T_out_K"] == pytest.approx(t_coolant, abs=2e-3)
    assert res.info["coolant_duty_W"] == pytest.approx(q, rel=2e-3)
    assert res.duty_W == pytest.approx(-q, rel=2e-3)


def test_infinite_coolant_reduces_to_pfr_r2() -> None:
    """Infinite capacity holds T_c constant: pfr R2 with the same fixed coolant T."""
    thermo = _ideal()
    inlet = thermo.flash_pt({"N2": 1.0}, 310.0, 2.0e5, 0.1)
    params = _params("co", mass_flow_kg_s=1.0e12)
    fixed = FixedBedTubularR2().solve({"inlet": inlet}, params, thermo)
    pfr = PfrR2().solve(
        {"inlet": inlet},
        {
            "reaction_set": EMPTY,
            "n_tubes": 1,
            "tube_diameter_m": 0.05,
            "length_m": 5.0,
            "thermal": {"coolant_T_K": 300.0, "U_W_m2K": 5.0},
        },
        thermo,
    )
    assert fixed.outlets["outlet"].T == pytest.approx(pfr.outlets["outlet"].T, rel=1e-8)
    assert fixed.duty_W == pytest.approx(pfr.duty_W, rel=1e-6)


def test_hot_spot_with_counter_current_coolant(thermo: Thermo) -> None:
    feeds, params = FixedBedTubularR2.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    res = FixedBedTubularR2().solve({"inlet": inlet}, params, thermo)
    out = res.outlets["outlet"]
    assert res.info["T_max_K"] > max(float(inlet.T), float(out.T))
    assert res.info["shooting_iterations"] >= 3
    assert res.info["coolant_T_out_K"] > params["coolant"]["T_in_K"]
    assert res.info["dP_Pa"] > 0.0


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"n_tubes": 0}, "n_tubes"),
        ({"tube_diameter_m": 0.0}, "tube_diameter_m"),
        ({"length_m": -1.0}, "length_m"),
        ({"U_W_m2K": 0.0}, "U_W_m2K"),
    ],
)
def test_parameter_refusals(change: dict[str, Any], match: str) -> None:
    thermo = _ideal()
    inlet = thermo.flash_pt({"N2": 1.0}, 310.0, 2.0e5, 0.1)
    with pytest.raises(FixedBedError, match=match):
        FixedBedTubularR2().solve({"inlet": inlet}, {**_params("co"), **change}, thermo)


@pytest.mark.parametrize(
    ("coolant", "match"),
    [
        ({"mass_flow_kg_s": 0.0}, "mass_flow_kg_s"),
        ({"cp_J_kgK": -1.0}, "cp_J_kgK"),
        ({"flow": "cross"}, "coolant.flow"),
    ],
)
def test_coolant_refusals(coolant: dict[str, Any], match: str) -> None:
    thermo = _ideal()
    inlet = thermo.flash_pt({"N2": 1.0}, 310.0, 2.0e5, 0.1)
    params = _params("co")
    params["coolant"] = {**params["coolant"], **coolant}
    with pytest.raises(FixedBedError, match=match):
        FixedBedTubularR2().solve({"inlet": inlet}, params, thermo)


def test_shooting_that_cannot_bracket_is_refused() -> None:
    """f(s) is one-signed when the trial always returns the wrong side."""

    class Run:
        extra = ((1000.0,),)

    with pytest.raises(FixedBedError, match="could not bracket"):
        FixedBedTubularR2._shoot(lambda _s: Run, 300.0, 310.0)
