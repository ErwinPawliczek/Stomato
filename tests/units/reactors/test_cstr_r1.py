"""Closed-form tests for the kinetic CSTR, level R1 (units/cstr.md, tests).

R1-A — isothermal first order, gas (through the adapter, against the hand
solution): nC4 -> iC4, k0 = 1.0e3 1/s, Ea = 5.0e4 J/mol, feed pure nC4 at
1.0 mol/s, 500 K, 2.0e5 Pa, V = 2.0 m3. Constant T and total flow (delta n
= 0), so y_nC4,out = 1 - X and the CSTR design equation gives

    Da = k(T)·V·c_tot/F_A0 = 0.575299226,  X = Da/(1 + Da) = 0.365199967,

with k(500 K) = k0·exp(-Ea/(R·500 K)) and c_tot = P/(R·T) = 48.11 mol/m3.
Expected F_nC4 = 0.634800033 mol/s. Tolerance 1e-9 relative.

R1-B — isothermal second order with delta n != 0 (2 C2H4 -> 1-butene) is
NOT implemented: the databank has no ethylene or butene component, and
pseudo-components carry no formula, so `formation_enthalpy_298` raises
MissingFormationData and the energy closure through `thermal_outlet` cannot
run. See the PR's SPEC ISSUE comment.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units._physics.kinetics import R
from ngdesign.units.reactors.cstr import CstrR1
from tests.conftest import flash_feed


def _isom_params(volume_m3: float = 2.0, **overrides: Any) -> dict[str, Any]:
    """The R1-A parameter set: first-order nC4 -> iC4, concentration basis."""
    params: dict[str, Any] = {
        "reaction_set": {
            "id": "cstr_isom_case",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "n-butane isomerization, first-order gas-phase lump "
                    "(Fogler, Elements of CRE, 4th ed., CSTR design equation)",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 1.0e3,
                        "Ea": 5.0e4,
                        "orders": {"nC4": 1.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "volume_m3": volume_m3,
        "thermal": "isothermal",
    }
    params.update(overrides)
    return params


def test_r1a_isothermal_first_order_closed_form(thermo: Thermo) -> None:
    """R1-A: the adapter reproduces Da/(1 + Da) to 1e-9 relative."""
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = flash_feed(thermo, feed)

    unit = CstrR1()
    result = unit.solve({"inlet": inlet}, _isom_params(), thermo)

    k = 1.0e3 * math.exp(-5.0e4 / (R * 500.0))
    c_tot = 2.0e5 / (R * 500.0)
    da = k * 2.0 * c_tot / 1.0
    x_expected = da / (1.0 + da)
    # The spec's printed digits carry their own rounding (9 decimals): the
    # exact X is 0.36519996748..., printed as 0.365199967.
    assert math.isclose(x_expected, 0.365199967, abs_tol=5e-10)

    n_out = result.outlets["outlet"].component_flows()
    assert math.isclose(n_out["nC4"], 1.0 - x_expected, rel_tol=1e-9)
    assert math.isclose(n_out["iC4"], x_expected, rel_tol=1e-9)
    assert math.isclose(n_out["nC4"], 0.634800033, abs_tol=5e-10)
    assert math.isclose(n_out["iC4"], 0.365199967, abs_tol=5e-10)
    assert math.isclose(result.info["conversion_nC4_isom"], x_expected, rel_tol=1e-9)
    assert math.isclose(result.info["extent_isom_mol_s"], x_expected, rel_tol=1e-9)
    # Isothermal: the outlet stays at the inlet temperature and the closure gap is 0.
    assert result.outlets["outlet"].T == pytest.approx(500.0, rel=1e-12)
    assert abs(result.info["T_closure_gap_K"]) < 1e-9
    # The isothermal duty carries the reaction heat (exothermic: removed).
    assert result.duty_W < 0.0
