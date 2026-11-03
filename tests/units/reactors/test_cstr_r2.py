"""cstr R2 tests (``specs/backend/units/cstr.md``): phase-resolved rate in a VLE vessel."""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts import PhaseKind
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors.cstr import CstrError, CstrPhaseError, CstrR1, CstrR2


def _inlet(thermo: Thermo) -> Any:
    feeds, _ = CstrR2.example_case()
    f = feeds["inlet"]
    return thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])


def test_rate_runs_in_the_liquid_of_the_outlet(thermo: Thermo) -> None:
    """Independent of the adapter: V_L from the outlet's own phases and r = k*x*c_L.

    The vessel is two-phase, so V_L < V; then |nu|*xi = V_L*r to the Newton tolerance.
    """
    params = CstrR2.example_case()[1]
    res = CstrR2().solve({"inlet": _inlet(thermo)}, params, thermo)
    out = res.outlets["outlet"]
    assert 0.0 < out.vapor_fraction < 1.0
    liquid = next(p for p in out.phases if p.kind is PhaseKind.HC_LIQUID)
    vapour = next(p for p in out.phases if p.kind is PhaseKind.VAPOR)
    vol = [p.mole_fraction * p.molecular_weight / p.density for p in (liquid, vapour)]
    v_l = params["volume_m3"] * vol[0] / sum(vol)
    c_l = 1000.0 * liquid.density / liquid.molecular_weight
    r = 1.0e-3 * liquid.composition["nC5"] * c_l
    assert res.info["extent_isom_mol_s"] == pytest.approx(v_l * r, rel=1e-9)
    assert 0.0 < v_l < params["volume_m3"]


def test_holdup_overrides_the_phase_ratio(thermo: Thermo) -> None:
    params = {**CstrR2.example_case()[1], "holdup_m3": 0.5}
    res = CstrR2().solve({"inlet": _inlet(thermo)}, params, thermo)
    liquid = next(p for p in res.outlets["outlet"].phases if p.kind is PhaseKind.HC_LIQUID)
    r = 1.0e-3 * liquid.composition["nC5"] * 1000.0 * liquid.density / liquid.molecular_weight
    assert res.info["extent_isom_mol_s"] == pytest.approx(0.5 * r, rel=1e-9)


def test_absent_phase_reacts_nothing(thermo: Thermo) -> None:
    """A rate in the aqueous phase of a water-free vessel is zero, not an error."""
    params = {**CstrR2.example_case()[1], "reacting_phase": "aqueous"}
    inlet = _inlet(thermo)
    res = CstrR2().solve({"inlet": inlet}, params, thermo)
    assert res.info["extent_isom_mol_s"] == pytest.approx(0.0, abs=1e-12)
    assert res.duty_W == pytest.approx(0.0, abs=1e-6 * abs(inlet.enthalpy * inlet.molar_flow))


def test_reduces_to_r1_in_a_single_phase(thermo: Thermo) -> None:
    """All vapour, no holdup: V_k = V, and the residuals are R1's."""
    feeds, params = CstrR1.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    r1 = CstrR1().solve({"inlet": inlet}, params, thermo)
    r2 = CstrR2().solve({"inlet": inlet}, {**params, "reacting_phase": "vapor"}, thermo)
    assert r2.info["extent_isom_mol_s"] == pytest.approx(r1.info["extent_isom_mol_s"], rel=1e-12)
    assert r2.outlets["outlet"].T == r1.outlets["outlet"].T


def test_liquid_reduces_to_r1(thermo: Thermo) -> None:
    feeds, params = CstrR2.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], 2.0e6, f["molar_flow"])
    assert inlet.vapor_fraction == 0.0
    r1 = CstrR1().solve({"inlet": inlet}, {**params, "reacting_phase": "liquid"}, thermo)
    r2 = CstrR2().solve({"inlet": inlet}, params, thermo)
    assert r2.info["extent_isom_mol_s"] == pytest.approx(r1.info["extent_isom_mol_s"], rel=1e-12)


def test_r1_still_refuses_the_two_phase_vessel(thermo: Thermo) -> None:
    params = {**CstrR2.example_case()[1], "reacting_phase": "liquid"}
    with pytest.raises(CstrPhaseError, match="use level R2"):
        CstrR1().solve({"inlet": _inlet(thermo)}, params, thermo)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"reacting_phase": "liquid"}, "reacting_phase"),
        ({"holdup_m3": 0.0}, "holdup_m3"),
        ({"holdup_m3": 3.0}, "holdup_m3"),
    ],
)
def test_refusals(thermo: Thermo, change: dict[str, Any], match: str) -> None:
    with pytest.raises(CstrError, match=match):
        CstrR2().solve({"inlet": _inlet(thermo)}, {**CstrR2.example_case()[1], **change}, thermo)
