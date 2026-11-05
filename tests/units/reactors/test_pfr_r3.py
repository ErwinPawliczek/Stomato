"""PFR R3 tests (``specs/backend/units/pfr.md``): effectiveness and deactivation."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors.pfr import PfrR1, PfrR2, PfrR3, activity, thiele_effectiveness
from ngdesign.units.reactors.plug_flow import PlugFlowError

D = 1.0  # a wide tube keeps the bed pressure drop far below the test tolerance
L = 1.0e-3 / (math.pi * D**2 / 4.0)  # V = 1e-3 m3
BED = {"particle_diameter_m": 0.05, "voidage": 0.4}


def _case() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Spec R3 case: first order, Ea = 0, k0 = 9.6 1/s per reactor volume, V = 1e-3 m3."""
    feeds, base = PfrR1.example_case()
    rs = base["reaction_set"]
    kin = {**rs["reactions"][0]["kinetics"], "k0": 9.6, "Ea": 0.0}
    rset = {**rs, "reactions": [{**rs["reactions"][0], "kinetics": kin}]}
    return feeds, {"reaction_set": rset, "tube_diameter_m": D, "length_m": L}


def _inlet(thermo: Thermo, feeds: dict[str, dict[str, Any]]) -> Any:
    f = feeds["inlet"]
    return thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])


def test_closed_form(thermo: Thermo) -> None:
    """k_p = 9.6/(1-0.4) = 16 1/s; sphere phi = 1.5e-3*sqrt(1*16/1e-6) = 6;
    eta = (3/36)*(6*coth(6) - 1) = 0.416672811 (Fogler eq. 12-32);
    a = 1/(1 + 1e-6*2.592e5) = 0.794155019; Da0 = 9.6*c*V/F = 0.461845843 with
    c = P/(R*T); X = 1 - exp(-a*eta*Da0) = 0.141721023, against 0.36988053 with
    eta = a = 1.
    """
    feeds, params = _case()
    params.update(
        bed=BED,
        viscosity_Pa_s=1.2e-5,
        pellet={"radius_m": 1.5e-3, "effective_diffusivity_m2_s": 1.0e-6},
        deactivation={"order": 2.0, "k_d_per_s": 1.0e-6, "time_on_stream_s": 2.592e5},
    )
    res = PfrR3().solve({"inlet": _inlet(thermo, feeds)}, params, thermo)
    assert res.info["activity"] == pytest.approx(0.794155019, rel=1e-8)
    assert res.info["extent_isom_mol_s"] == pytest.approx(0.141721023, rel=1e-7)


def test_eta_and_activity_forms() -> None:
    # Exact first-order sphere, eta = (3/phi^2)(phi coth phi - 1) (Fogler 4th ed. eq. 12-32,
    # p. 829). Example 12-3 (pp. 840-841) prints eta = 0.856 at phi = 1.65; at phi = 16.5
    # the exact form gives 0.1708 (the book prints 0.182 from the large-phi limit 3/phi).
    # Regression: the earlier shape-normalized tanh(phi/3)/(phi/3) gave 0.910 at 1.65.
    assert thiele_effectiveness(1.65) == pytest.approx(0.856, abs=5e-4)
    assert thiele_effectiveness(16.5) == pytest.approx(0.170798898, rel=1e-8)
    assert thiele_effectiveness(2.0) == pytest.approx(0.805972081, rel=1e-8)
    # Series branch (phi < 0.1): continuous with the closed form and free of cancellation.
    assert thiele_effectiveness(0.1) == pytest.approx(3.0 / 0.01 * (0.1 / math.tanh(0.1) - 1.0), rel=1e-12)
    assert thiele_effectiveness(1e-6) == pytest.approx(1.0 - 1e-12 / 15.0, rel=1e-15)
    assert thiele_effectiveness(300.0) == pytest.approx(3.0 / 300.0 * (1.0 - 1.0 / 300.0), rel=1e-12)
    a1 = activity({"deactivation": {"order": 1.0, "k_d_per_s": 2.0, "time_on_stream_s": 0.5}})
    assert a1 == pytest.approx(math.exp(-1.0), rel=1e-14)
    a2 = activity({"deactivation": {"order": 0.0, "k_d_per_s": 2.0, "time_on_stream_s": 0.25}})
    assert a2 == pytest.approx(0.5, rel=1e-14)
    assert activity({"deactivation": {"order": 0.0, "k_d_per_s": 2.0, "time_on_stream_s": 5.0}}) == 0.0
    assert activity({}) == 1.0


def test_reduces_to_r2(thermo: Thermo) -> None:
    """No deactivation and effectiveness 1: R3 is R2 (1e-12)."""
    feeds, params = _case()
    inlet = _inlet(thermo, feeds)
    r2 = PfrR2().solve({"inlet": inlet}, params, thermo)
    r3 = PfrR3().solve({"inlet": inlet}, {**params, "effectiveness": {"isom": 1.0}}, thermo)
    for cid, n in r2.outlets["outlet"].component_flows().items():
        assert r3.outlets["outlet"].component_flows()[cid] == pytest.approx(n, rel=1e-12)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"effectiveness": {"isom": 0.0}}, "effectiveness"),
        ({"effectiveness": {"nope": 0.5}}, "effectiveness"),
        ({"deactivation": {"order": -1.0, "k_d_per_s": 1.0, "time_on_stream_s": 1.0}}, "order"),
        ({"deactivation": {"order": 1.0, "k_d_per_s": -1.0, "time_on_stream_s": 1.0}}, "k_d_per_s"),
        ({"deactivation": {"order": 1.0, "k_d_per_s": 1.0, "time_on_stream_s": -1.0}}, "time_on_stream_s"),
        ({"deactivation": {"order": 1.0}}, "k_d_per_s"),
        ({"pellet": {"radius_m": 1e-3, "effective_diffusivity_m2_s": 1e-6}}, "bed.voidage"),
        ({"pellet": {"radius_m": 0.0, "effective_diffusivity_m2_s": 1e-6}}, "radius_m"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    feeds, params = _case()
    with pytest.raises(PlugFlowError, match=match):
        PfrR3().solve({"inlet": _inlet(thermo, feeds)}, {**params, **change}, thermo)


def test_non_power_law_needs_explicit_effectiveness(thermo: Thermo) -> None:
    feeds, params = _case()
    rs = params["reaction_set"]
    kin = {**rs["reactions"][0]["kinetics"], "orders": {"nC4": 1.0, "iC4": 0.5}}
    params["reaction_set"] = {**rs, "reactions": [{**rs["reactions"][0], "kinetics": kin}]}
    params.update(bed=BED, pellet={"radius_m": 1e-3, "effective_diffusivity_m2_s": 1e-6})
    with pytest.raises(PlugFlowError, match="effectiveness"):
        PfrR3().solve({"inlet": _inlet(thermo, feeds)}, params, thermo)
