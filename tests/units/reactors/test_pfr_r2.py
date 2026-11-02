"""PFR R2 tests (``specs/backend/units/pfr.md``): Ergun and wall heat closed forms."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors.pfr import PfrR1, PfrR2
from ngdesign.units.reactors.plug_flow import ErgunBed, PlugFlowError

#: Empty reaction set: the inert closed forms.
EMPTY: dict[str, Any] = {"id": "inert", "components": ["N2"], "reactions": []}
TUBE: dict[str, Any] = {"tube_diameter_m": 0.05, "length_m": 5.0, "n_tubes": 1}
BED: dict[str, Any] = {"particle_diameter_m": 0.003, "voidage": 0.4}


def _ideal() -> Thermo:
    registry.discover()
    raw: Thermo = registry.create("thermo", "ideal-raoult")
    return raw


def _n2(thermo: Thermo, t: float, flow: float = 0.1) -> Any:
    return thermo.flash_pt({"N2": 1.0}, t, 2.0e5, flow)


def test_ergun_closed_form() -> None:
    """R2-a, Fogler eq. 4-33: isothermal ideal gas in a packed bed.

    A_c = pi*0.05**2/4 = 1.96349541e-3 m2; G = 0.1*0.0280134/A_c = 1.42671 kg/(m2 s);
    rho0 = P0*M/(R*T) = 2.246158 kg/m3; beta0 = G(1-phi)/(rho0*Dp*phi**3) *
    [150(1-phi)mu/Dp + 1.75*G] = 6027.729 Pa/m; P/P0 = sqrt(1 - 2*beta0*L/P0),
    so P_out = 167166.21 Pa.  Hand value, not model output.
    """
    thermo = _ideal()
    params = {**TUBE, "reaction_set": EMPTY, "thermal": "isothermal", "bed": BED, "viscosity_Pa_s": 1.8e-5}
    res = PfrR2().solve({"inlet": _n2(thermo, 300.0)}, params, thermo)
    assert res.outlets["outlet"].P == pytest.approx(167166.21, rel=1e-6)
    assert res.info["dP_Pa"] == pytest.approx(32833.79, rel=1e-5)


def test_wall_heat_closed_form() -> None:
    """R2-b: T_out = T_c + (T0 - T_c)exp(-U*a_w*V/(F*cp)).

    U*a_w*V = 5*(4/0.05)*1.96349541e-3*5 = 3.92699082 W/K; cp = 29.2132106
    J/(mol K) gives T_out = 301.303674 K and Q = -10.7981558 W.
    """
    thermo = _ideal()
    params = {**TUBE, "reaction_set": EMPTY, "thermal": {"coolant_T_K": 300.0, "U_W_m2K": 5.0}}
    res = PfrR2().solve({"inlet": _n2(thermo, 305.0)}, params, thermo)
    assert res.outlets["outlet"].T == pytest.approx(301.303674, abs=2e-4)
    assert res.duty_W == pytest.approx(-10.7981558, rel=1e-3)


def test_reduces_to_r1_adiabatic(thermo: Thermo) -> None:
    """No bed, no coolant, same volume: R2 is R1 (1e-10 relative)."""
    feeds, base = PfrR1.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    r1 = PfrR1().solve({"inlet": inlet}, {**base, "thermal": "adiabatic"}, thermo)
    d = 0.2
    params = {
        "reaction_set": base["reaction_set"],
        "tube_diameter_m": d,
        "length_m": 2.0 / (math.pi * d**2 / 4.0),
        "thermal": "adiabatic",
    }
    r2 = PfrR2().solve({"inlet": inlet}, params, thermo)
    a, b = r1.outlets["outlet"], r2.outlets["outlet"]
    assert b.T == pytest.approx(a.T, rel=1e-10)
    assert b.P == a.P
    for cid, n in a.component_flows().items():
        assert b.component_flows()[cid] == pytest.approx(n, rel=1e-10)


def test_parallel_tubes_share_the_flow() -> None:
    """Doubling flow and tubes leaves the per-tube hydraulics, hence dP, unchanged."""
    thermo = _ideal()
    common = {**TUBE, "reaction_set": EMPTY, "bed": BED, "viscosity_Pa_s": 1.8e-5}
    one = PfrR2().solve({"inlet": _n2(thermo, 300.0)}, common, thermo)
    two = PfrR2().solve({"inlet": _n2(thermo, 300.0, 0.2)}, {**common, "n_tubes": 2}, thermo)
    assert two.info["dP_Pa"] == pytest.approx(one.info["dP_Pa"], rel=1e-7)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"tube_diameter_m": 0.0, "particle_diameter_m": 1e-3, "voidage": 0.4}, "tube_diameter_m"),
        ({"tube_diameter_m": 0.1, "particle_diameter_m": 0.0, "voidage": 0.4}, "particle_diameter_m"),
        ({"tube_diameter_m": 0.1, "particle_diameter_m": 1e-3, "voidage": 1.0}, "voidage"),
        ({"tube_diameter_m": 0.1, "particle_diameter_m": 1e-3, "voidage": 0.4, "n_tubes": 0}, "n_tubes"),
    ],
)
def test_bed_refusals(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(PlugFlowError, match=match):
        ErgunBed(**kwargs)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"length_m": 0.0}, "length_m"),
        ({"tube_diameter_m": -1.0}, "tube_diameter_m"),
        ({"n_tubes": 0}, "n_tubes"),
        ({"volume_m3": 1.0}, "volume_m3"),
        ({"thermal": {"T_out": 300.0}}, "thermal mode"),
    ],
)
def test_geometry_refusals(change: dict[str, Any], match: str) -> None:
    thermo = _ideal()
    params = {**TUBE, "reaction_set": EMPTY, **change}
    with pytest.raises(PlugFlowError, match=match):
        PfrR2().solve({"inlet": _n2(thermo, 300.0)}, params, thermo)


def test_viscosity_required_when_the_package_has_none() -> None:
    """No silent default: a package without viscosity needs viscosity_Pa_s."""

    class NoViscosity:
        def __init__(self, inner: Thermo) -> None:
            self.inner = inner

        def __getattr__(self, name: str) -> Any:
            return getattr(self.inner, name)

        def phase_props(self, *args: Any, **kwargs: Any) -> Any:
            return self.inner.phase_props(*args, **kwargs).model_copy(update={"viscosity": None})

    inner = _ideal()
    params = {**TUBE, "reaction_set": EMPTY, "bed": BED}
    with pytest.raises(PlugFlowError, match="viscosity_Pa_s"):
        PfrR2().solve({"inlet": _n2(inner, 300.0)}, params, NoViscosity(inner))


def test_pressure_floor_refused() -> None:
    """A bed long enough to drop 90 % of P is refused, not truncated."""
    thermo = _ideal()
    params = {**TUBE, "length_m": 500.0, "reaction_set": EMPTY, "bed": BED, "viscosity_Pa_s": 1.8e-5}
    with pytest.raises(PlugFlowError, match="pressure drop exceeds"):
        PfrR2().solve({"inlet": _n2(thermo, 300.0)}, params, thermo)


def test_r1_refuses_a_bed(thermo: Thermo) -> None:
    feeds, params = PfrR1.example_case()
    f = feeds["inlet"]
    inlet = thermo.flash_pt(f["composition"], f["T"], f["P"], f["molar_flow"])
    with pytest.raises(PlugFlowError, match="use level R2"):
        PfrR1().solve({"inlet": inlet}, {**params, "bed": BED}, thermo)
