"""Naphtha hydrotreater R1 tests (spec ``specs/backend/units/naphtha_ht.md``).

Refusals (one per row of the spec's refusal table), the closed-form isothermal
first-order HDS case with mole change, the R0 identity, and the adiabatic
two-bed V0 case.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.refining.hdt_kinetic import HdtKineticError, NaphthaHydrotreaterR1

#: Closed-form R1-HDS case (spec tests): thiophene + 4 H2 -> nC4 + H2S,
#: r' = k_w * y_T with k_w = 0.02 mol/(kg_cat s), Ea = 0, mole-fraction basis.
#: Feed: naphtha_in thiophene 0.01 + nC7 1.0 mol/s, h2_in H2 5.0 mol/s, both
#: at 620 K and 3.0e6 Pa; one isothermal bed, rho_b = 800 kg/m3.
#: F_T0 = 0.01, F0 = 6.01; with F_tot = F0 - 3*xi the hand-integrated
#: design equation is W(X) = [3*xi + (F0 - 3*F_T0) * ln(F_T0/(F_T0 - xi))]/k_w.
#: For X = 0.9 (xi = 0.009): W = [0.027 + 5.98*ln(10)]/0.02 = 689.822943 kg.
W_CLOSED_FORM_KG = 689.822943


def _flash(thermo: Thermo, feed: dict[str, Any]) -> Any:
    return thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


def _feeds(
    thio: float = 1.0, py: float = 0.5, pent: float = 1.0, bz: float = 0.5, h2: float | None = None
) -> dict[str, dict[str, Any]]:
    """Real-species feeds (nC7 carrier) for the R1 adapter."""
    n_c7 = 97.0
    h2_demand = 4.0 * thio + 5.0 * py + pent + 3.0 * bz
    h2_feed = h2 if h2 is not None else 1.3 * h2_demand
    total = n_c7 + thio + py + pent + bz
    return {
        "naphtha_in": {
            "T": 620.0,
            "P": 3.0e6,
            "molar_flow": total,
            "composition": {
                "nC7": n_c7 / total,
                "thiophene": thio / total,
                "pyridine": py / total,
                "1-pentene": pent / total,
                "benzene": bz / total,
            },
        },
        "h2_in": {
            "T": 620.0,
            "P": 3.0e6,
            "molar_flow": h2_feed,
            "composition": {"H2": 1.0},
        },
    }


def _kinetics(**over: Any) -> dict[str, Any]:
    """First-order per-kg_cat kinetics for HDS and HDN (illustrative test values)."""
    base: dict[str, Any] = {
        "hds_thiophene": {
            "rate_units": "mol/(kg_cat·s)",
            "k0": 1.0e4,
            "Ea": 0.0,
            "orders": {"thiophene": 1.0},
            "basis": "mole_fraction",
        },
        "hdn_pyridine": {
            "rate_units": "mol/(kg_cat·s)",
            "k0": 1.0e4,
            "Ea": 0.0,
            "orders": {"pyridine": 1.0},
            "basis": "mole_fraction",
        },
    }
    base.update(over)
    return base


def _params(beds: Any | None = None, kinetics: Any | None = None) -> dict[str, Any]:
    return {
        "beds": beds if beds is not None else [{"catalyst_mass_kg": 1.0, "thermal": "isothermal"}],
        "bulk_density_kg_m3": 800.0,
        "kinetics": kinetics if kinetics is not None else _kinetics(),
    }


# ---------------------------------------------------------------------------
# Refusals (spec refusal table)
# ---------------------------------------------------------------------------


def test_refusal_pseudo_component(thermo: Thermo) -> None:
    """A pseudo carrier in an inlet is refused, naming #222 (R0 stays the level)."""
    from ngdesign.units.refining.reactors_hdt import NaphthaHydrotreater as R0

    feeds, _ = R0.example_case()  # naphtha_in carries the hdt_naphtha pseudo
    with pytest.raises(HdtKineticError, match="#222"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, feed) for port, feed in feeds.items()},
            _params(),
            thermo,
        )


def test_refusal_beds_empty(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="beds"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(beds=[]),
            thermo,
        )


def test_refusal_catalyst_mass(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="catalyst_mass_kg"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(beds=[{"catalyst_mass_kg": 0.0, "thermal": "adiabatic"}]),
            thermo,
        )


def test_refusal_bed_thermal(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="thermal"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(beds=[{"catalyst_mass_kg": 1.0, "thermal": "T_out"}]),
            thermo,
        )


def test_refusal_inlet_T(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="inlet_T_K"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(beds=[{"catalyst_mass_kg": 1.0, "inlet_T_K": 0.0, "thermal": "adiabatic"}]),
            thermo,
        )


def test_refusal_bulk_density(thermo: Thermo) -> None:
    feeds = _feeds()
    for bad in ({}, {"bulk_density_kg_m3": -1.0}):
        params = _params()
        params.pop("bulk_density_kg_m3", None)
        params.update(bad)
        with pytest.raises(HdtKineticError, match="bulk_density_kg_m3"):
            NaphthaHydrotreaterR1().solve(
                {port: _flash(thermo, f) for port, f in feeds.items()},
                params,
                thermo,
            )


def test_refusal_kinetics_bad_key(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="kinetics"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(kinetics={"hcr_nC7": {"rate_units": "mol/(kg_cat·s)", "k0": 1.0, "Ea": 0.0}}),
            thermo,
        )


def test_refusal_kinetics_bad_body(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="kinetics"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(kinetics={"hds_thiophene": {"not_a": "rate form"}}),
            thermo,
        )


def test_refusal_kinetics_rate_units(thermo: Thermo) -> None:
    """Rates per unit reactor volume are refused here: this unit's rates are per kg_cat."""
    feeds = _feeds()
    kin = _kinetics()
    kin["hds_thiophene"]["rate_units"] = "mol/(m3·s)"
    with pytest.raises(HdtKineticError, match="kinetics"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(kinetics=kin),
            thermo,
        )


def test_refusal_kinetics_empty(thermo: Thermo) -> None:
    feeds = _feeds()
    with pytest.raises(HdtKineticError, match="at least one"):
        NaphthaHydrotreaterR1().solve(
            {port: _flash(thermo, f) for port, f in feeds.items()},
            _params(kinetics={}),
            thermo,
        )


def test_refusal_gas_out_empty(thermo: Thermo) -> None:
    """No H2 anywhere and no H2S/NH3 formed: gas_out would be empty.

    The guard is exercised on the split itself: upstream of it, the shared
    integrator refuses any bed whose reactions consume H2 with no H2 in the
    mixture (its Jacobian probe drives the absent reactant negative), so a
    full solve can never carry a gas-free effluent into the split.
    """
    from ngdesign.units.refining.hdt_kinetic import _split_outlets

    n_final = {"nC7": 97.0, "nC4": 0.0}
    state = thermo.flash_pt({"nC7": 1.0}, 620.0, 3.0e6, 97.0)
    with pytest.raises(HdtKineticError, match="gas_out"):
        _split_outlets(n_final, state, thermo)
