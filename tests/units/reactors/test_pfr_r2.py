"""PFR R2 tests (spec U-R2 wave, ``specs/backend/units/pfr.md``).

Step 4 (pressure): the R2-a Ergun closed form at the integrator and adapter
level, and the R2 -> R1 reduction identity (adiabatic, no bed, same volume:
same integrator path, P constant, outlets equal to 1e-10 relative).
Step 5 adds the wall-heat closed form, the refusals and the catalogue.
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors._shared import reaction_set_param
from ngdesign.units.reactors.pfr import PfrR1, PfrR2
from ngdesign.units.reactors.plug_flow import ErgunBed, integrate_plug_flow

#: Closed-form R2-a values (spec tests): Fogler eq. 4-33,
#: P/P0 = sqrt(1 - 2 beta0 L / P0).  A_c = 1.96349541e-3 m2,
#: G = 1.42671075 kg/(m2 s), rho0 = 2.24615839 kg/m3, beta0 = 6027.72916 Pa/m.
P_OUT_R2A = 167166.21  # Pa (delta P = 32833.7903 Pa)


def _flash(thermo: Thermo, feed: dict[str, Any]) -> Any:
    return thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


def _ideal_raoult() -> Thermo:
    from ngdesign import registry

    try:
        raw = registry.create("thermo", "ideal-raoult")
    except Exception:  # pragma: no cover - registration drift only
        pytest.skip("ideal-raoult not registered")
    return cast(Thermo, raw)


def _r2a() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """The R2-a case: inert N2 through an Ergun bed, isothermal."""
    feed = {
        "T": 300.0,
        "P": 2.0e5,
        "molar_flow": 0.1,
        "composition": {"N2": 1.0},
    }
    params: dict[str, Any] = {
        "reaction_set": {"id": "r2a_inert", "components": ["N2"], "reactions": []},
        "tube_diameter_m": 0.05,
        "length_m": 5.0,
        "n_tubes": 1,
        "thermal": "isothermal",
        "bed": {"particle_diameter_m": 0.003, "voidage": 0.4},
        "viscosity_Pa_s": 1.8e-5,
    }
    return {"inlet": feed}, params


def test_r2a_closed_form_integrator() -> None:
    """R2-a at the integrator level: P_out matches Fogler eq. 4-33."""
    thermo = _ideal_raoult()
    feeds, params = _r2a()
    inlet = _flash(thermo, feeds["inlet"])
    a_cross = math.pi * 0.05**2 / 4.0
    profile = integrate_plug_flow(
        inlet,
        reaction_set_param(params["reaction_set"]),
        thermo,
        volume_m3=1.0 * a_cross * 5.0,
        energy="isothermal",
        tube_diameter_m=0.05,
        length_m=5.0,
        n_tubes=1,
        viscosity_Pa_s=1.8e-5,
        ergun=ErgunBed(particle_diameter_m=0.003, voidage=0.4),
    )
    assert profile.P_Pa[-1] == pytest.approx(P_OUT_R2A, rel=1e-6)
    assert all(t == pytest.approx(300.0, abs=1e-6) for t in profile.T_K)
    # Isothermal inert: the ODE integrates no heat at all.
    assert profile.Q_W == pytest.approx(0.0, abs=1e-9)


def test_r2a_closed_form_adapter() -> None:
    """R2-a through the adapter: P_out_Pa / dP_Pa reported, inert duty 0."""
    thermo = _ideal_raoult()
    feeds, params = _r2a()
    result = PfrR2().solve({"inlet": _flash(thermo, feeds["inlet"])}, params, thermo)
    assert result.info["P_out_Pa"] == pytest.approx(P_OUT_R2A, rel=1e-6)
    # The closed-form anchor is P_out at 1e-6 relative (+/- 0.167 Pa); delta P
    # = P0 - P_out carries that same absolute error band (measured 32833.838
    # vs 32833.790 Pa), so its tolerance is absolute, not relative.
    assert result.info["dP_Pa"] == pytest.approx(2.0e5 - P_OUT_R2A, abs=0.17)
    # Inert and isothermal: the physical duty is zero (dT/dV = 0 in the ODE,
    # no reaction), but the closure compares H at (T_in, P_out) against H at
    # (T_in, P_in) and ideal-raoult N2's enthalpy has a small pressure
    # dependence; measured 0.196 W here.  The ODE's accumulated heat is
    # exactly zero (checked in the integrator test below).
    assert abs(result.duty_W) < 1.0
    out = result.outlets["outlet"]
    assert out.T == pytest.approx(300.0, abs=1e-6)
    assert out.molar_flow == pytest.approx(0.1, rel=1e-9)


def test_r2_reduces_to_r1() -> None:
    """Adiabatic, no bed, volume = n_t A_c L: R2's outlet equals R1's to 1e-10."""
    thermo = _ideal_raoult()
    tube_d, length, n_t = 0.4, 6.0, 3
    a_cross = math.pi * tube_d**2 / 4.0
    volume = n_t * a_cross * length
    reaction_set = {
        "id": "nc4_isom_r2r1",
        "components": ["nC4", "iC4"],
        "reactions": [
            {
                "id": "isom",
                "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                "base_component": "nC4",
                "provenance": "R2 -> R1 reduction identity",
                "kinetics": {
                    "rate_units": "mol/(m3·s)",
                    "k0": 1.0e3,
                    "Ea": 5.0e4,
                    "orders": {"nC4": 1.0},
                    "basis": "concentration",
                },
            }
        ],
    }
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = _flash(thermo, feed)
    r1 = PfrR1().solve(
        {"inlet": inlet},
        {"reaction_set": reaction_set, "volume_m3": volume, "thermal": "adiabatic"},
        thermo,
    )
    r2 = PfrR2().solve(
        {"inlet": inlet},
        {
            "reaction_set": reaction_set,
            "tube_diameter_m": tube_d,
            "length_m": length,
            "n_tubes": n_t,
            "thermal": "adiabatic",
        },
        thermo,
    )
    out1, out2 = r1.outlets["outlet"], r2.outlets["outlet"]
    assert out2.T == pytest.approx(out1.T, rel=1e-10)
    assert out2.molar_flow == pytest.approx(out1.molar_flow, rel=1e-10)
    for cid, y1 in out1.composition.items():
        assert out2.composition[cid] == pytest.approx(y1, rel=1e-10)
    assert r2.duty_W == pytest.approx(0.0, abs=1e-9)
    # No bed, no drop: P stays at P_in on both paths.
    assert out2.P == pytest.approx(out1.P, abs=1e-6)
