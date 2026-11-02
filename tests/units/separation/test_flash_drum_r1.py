"""flash_drum R1 tests (``specs/backend/units/flash_drum.md``)."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.flash_drum import FlashDrum, FlashDrumSpecError
from ngdesign.units.separation.flash_drum_r1 import FlashDrumR1, FlashDrumR1SpecError


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = FlashDrum.example_case()
    return {k: thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"]) for k, f in feeds.items()}


def _carry(**change: Any) -> dict[str, Any]:
    """The -2 MW case: the spec's +500 kW example measures all vapour (T_out 316.3 K),
    so it cannot show carry-over; -2 MW leaves gas 799, liquid 28, aqueous 2.2 mol/s."""
    return {**FlashDrumR1.example_case()[1], **change}


R0_DUTY = {"outlet_P": 3.0e6, "duty_W": -2.0e6}


def test_no_diameter_is_r0(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    r0 = FlashDrum().solve(inlets, R0_DUTY, thermo)
    r1 = FlashDrumR1().solve(inlets, R0_DUTY, thermo)
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W
    assert r1.info["T_out_K"] == r0.info["T_out_K"]
    assert r1.info["D_min_m"] > 0.0


def test_no_entrainment_is_r0(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    r0 = FlashDrum().solve(inlets, R0_DUTY, thermo)
    r1 = FlashDrumR1().solve(inlets, _carry(inlet_entrained_fraction=0.0), thermo)
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W


def test_carryover_is_proportional_by_mass(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    r0 = FlashDrum().solve(inlets, R0_DUTY, thermo)
    r1 = FlashDrumR1().solve(inlets, _carry(), thermo)
    f = r1.info["carryover_mol_fraction"]
    assert f > 0.0
    liq0, aq0 = r0.outlets["liquid_out"], r0.outlets["aqueous_out"]
    liq1, aq1 = r1.outlets["liquid_out"], r1.outlets["aqueous_out"]
    assert (liq0.molar_flow - liq1.molar_flow) / liq0.molar_flow == pytest.approx(f, rel=1e-12)
    if aq0.molar_flow > 0.0:
        assert (aq0.molar_flow - aq1.molar_flow) / aq0.molar_flow == pytest.approx(f, rel=1e-12)
    mass_l = liq0.mass_flow + aq0.mass_flow
    expected = _carry()["inlet_entrained_fraction"] * mass_l * r1.info["fines_fraction"]
    assert r1.info["carryover_kg_s"] == pytest.approx(expected, rel=1e-12)


def test_duty_spec_survives_carryover(thermo: Thermo) -> None:
    """Isothermal, isobaric redistribution between coexisting phases."""
    r1 = FlashDrumR1().solve(_inlets(thermo), _carry(), thermo)
    assert abs(r1.duty_W + 2.0e6) <= 1e-8 * 2.0e6


def test_moles_close_with_carryover(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    r1 = FlashDrumR1().solve(inlets, _carry(), thermo)
    n_in = sum(s.molar_flow for s in inlets.values())
    n_out = sum(s.molar_flow for s in r1.outlets.values())
    assert n_out == pytest.approx(n_in, rel=1e-12)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"diameter_m": 0.0}, "diameter_m"),
        ({"K_m_s": 0.0}, "K_m_s"),
        ({"inlet_entrained_fraction": 1.5}, "inlet_entrained_fraction"),
        ({"droplet_d_rr_m": 0.0}, "droplet_d_rr_m"),
        ({"droplet_n_rr": 0.0}, "droplet_n_rr"),
        ({"inlet_entrained_fraction": None}, "requires inlet_entrained_fraction"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    with pytest.raises(FlashDrumR1SpecError, match=match):
        FlashDrumR1().solve(_inlets(thermo), _carry(**change), thermo)


def test_gas_viscosity_needed_when_absent(thermo: Thermo) -> None:
    class Bare:
        def __getattr__(self, name: str) -> Any:
            return getattr(thermo, name)

        def flash_pt(self, *args: Any) -> Any:
            state = thermo.flash_pt(*args)
            return state.model_copy(
                update={"phases": [p.model_copy(update={"viscosity": None}) for p in state.phases]}
            )

    params = _carry()
    del params["gas_viscosity_Pa_s"]
    with pytest.raises(FlashDrumR1SpecError, match="gas_viscosity_Pa_s"):
        FlashDrumR1().solve(_inlets(thermo), params, Bare())


def test_single_phase_needs_no_sizing_but_refuses_carryover(thermo: Thermo) -> None:
    inlet = thermo.flash_pt({"C1": 1.0}, 350.0, 1.0e6, 1.0)
    r0 = FlashDrum().solve({"inlet": inlet}, {}, thermo)
    assert FlashDrumR1().solve({"inlet": inlet}, {}, thermo).outlets == r0.outlets
    with pytest.raises(FlashDrumR1SpecError, match="both a gas and a liquid"):
        FlashDrumR1().solve({"inlet": inlet}, _carry(duty_W=None), thermo)


def test_r0_refusals_propagate(thermo: Thermo) -> None:
    with pytest.raises(FlashDrumSpecError, match="exactly one of duty_W and vapor_fraction"):
        FlashDrumR1().solve(_inlets(thermo), _carry(vapor_fraction=0.5), thermo)
