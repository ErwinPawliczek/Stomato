"""PFR R1 tests (spec U-R2 wave, ``specs/backend/units/pfr.md``).

R1-A closed form at the integrator and adapter level, the zero-rate
identity, the adiabatic consistency check, uniform-duty behaviour, the
O(1)-in-V flash budget, equilibrium-approach behaviour, and one test per
refusal table row that R1 can reach.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.reactors._shared import reaction_set_param
from ngdesign.units.reactors.pfr import PfrR1
from ngdesign.units.reactors.plug_flow import (
    PlugFlowError,
    integrate_plug_flow,
)

#: Closed-form R1-A values (spec tests): k = 5.97912989e-3 s-1,
#: c = 48.108942 mol/m3, Da = 0.575299226, X = 0.437463482 (exact,
#: delta n = 0).  F_nC4 = 0.562536518, F_iC4 = 0.437463482 mol/s.
X_R1A = 0.437463482


def _flash(thermo: Thermo, feed: dict[str, Any]) -> Any:
    return thermo.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])


def _r1a() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """The R1-A case: nC4 -> iC4, first order, isothermal, V = 2 m3."""
    return PfrR1.example_case()


def test_r1a_closed_form_integrator(thermo: Thermo) -> None:
    """R1-A at the integrator level: the outlet flows match the hand calc."""
    feeds, params = _r1a()
    inlet = _flash(thermo, feeds["inlet"])
    profile = integrate_plug_flow(
        inlet,
        reaction_set_param(params["reaction_set"]),
        thermo,
        volume_m3=float(params["volume_m3"]),
        energy="isothermal",
    )
    f_nC4 = 1.0 - profile.extents[-1][0]
    f_iC4 = profile.extents[-1][0]
    assert f_iC4 == pytest.approx(X_R1A, rel=1e-7)
    assert f_nC4 == pytest.approx(1.0 - X_R1A, rel=1e-7)
    assert all(t == pytest.approx(500.0, abs=1e-6) for t in profile.T_K)


def test_r1a_closed_form_adapter(thermo: Thermo) -> None:
    """R1-A through the adapter: outlet amounts and the reported extents."""
    feeds, params = _r1a()
    result = PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params, thermo)
    out = result.outlets["outlet"]
    total = out.molar_flow
    assert total * out.composition["iC4"] == pytest.approx(X_R1A, rel=1e-7)
    assert total * out.composition["nC4"] == pytest.approx(1.0 - X_R1A, rel=1e-7)
    assert result.info["extent_isom_mol_s"] == pytest.approx(X_R1A, rel=1e-7)
    assert result.info["T_profile_out_K"] == pytest.approx(500.0, abs=1e-6)
    # The isothermal closure carries the reaction heat: finite and reported.
    assert math.isfinite(result.duty_W)


def test_r1_flash_count_does_not_scale_with_volume(thermo: Thermo) -> None:
    """Reference count: solving at 1 and 4 m3 costs the same flashes (O(1) in V)."""
    from scripts.bench_baseline import CountingThermo

    feeds, params = _r1a()
    counts = []
    for volume in (1.0, 4.0):
        counting = CountingThermo(thermo)
        params_v = dict(params, volume_m3=volume)
        PfrR1().solve({"inlet": _flash(counting, feeds["inlet"])}, params_v, counting)
        counts.append(counting.flashes)
    assert counts[0] == counts[1]


def test_r1_zero_rate_identity(thermo: Thermo) -> None:
    """With every k0 = 0 the outlet is the inlet re-flashed at (T_in, P_in), duty 0."""
    params_zero: dict[str, Any] = {
        "reaction_set": {
            "id": "nc4_isom_zero",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "zero-rate identity case",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 0.0,
                        "Ea": 5.0e4,
                        "orders": {"nC4": 1.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "volume_m3": 2.0,
        "thermal": "isothermal",
    }
    feeds, _ = _r1a()
    result = PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params_zero, thermo)
    out = result.outlets["outlet"]
    assert out.T == pytest.approx(500.0, abs=1e-9)
    assert out.P == pytest.approx(2.0e5, abs=1e-6)
    assert abs(result.duty_W) < 1.0e-9
    assert out.composition["nC4"] == pytest.approx(1.0, abs=1e-12)
    assert out.composition.get("iC4", 0.0) == pytest.approx(0.0, abs=1e-12)


def test_r1_adiabatic_consistency(thermo: Thermo) -> None:
    """Adiabatic nC4 -> iC4: V0 closes at 1e-8 and T_out > T_in.

    The energy ODE uses the closure-consistent reaction enthalpy
    (review of this PR, blocking items 1 and B): eq. 5's dH is the
    databank formation-enthalpy lift ``heat_of_reaction(r, 298.15)`` plus
    ``sum(nu_i * h_bar_i)``, each h_bar_i a partial molar enthalpy of the
    actual mixture (a central finite difference of the mixture enthalpy
    flow from ``thermo.phase_props``), the same basis the outlet closure
    (``thermal_outlet``) balances.  The residual ``T_closure_gap_K`` is
    the closure's flash-based solve against the ODE's dH; measured
    -6.6e-7 K on ``ideal-raoult`` for this case, so 1e-5 K is asserted
    inside the plan's 1e-3 K ceiling.

    Case note (review, non-blocking): the spec's preferred
    2 C2H4 -> 1-butene case was checked — ``ideal-raoult`` resolves C2H4
    and 1-butene with formation data — and this nC4 -> iC4 case is kept
    as the review-approved fallback.
    """
    from ngdesign import registry

    try:
        raw = registry.create("thermo", "ideal-raoult")
    except Exception:  # pragma: no cover - package availability
        pytest.skip("ideal-raoult not registered")
    params: dict[str, Any] = {
        "reaction_set": {
            "id": "nc4_isom_ad",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "adiabatic consistency case (review-approved fallback: "
                    "nC4 -> iC4, dH ~ -8 kJ/mol; the preferred 2 C2H4 -> 1-butene "
                    "dimerisation data were checked and are available — kept as the "
                    "review-approved fallback)",
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
        "volume_m3": 2.0,
        "thermal": "adiabatic",
    }
    feed = {"T": 500.0, "P": 2.0e5, "molar_flow": 1.0, "composition": {"nC4": 1.0}}
    inlet = raw.flash_pt(feed["composition"], feed["T"], feed["P"], feed["molar_flow"])
    result = PfrR1().solve({"inlet": inlet}, params, raw)
    out = result.outlets["outlet"]
    assert result.duty_W == pytest.approx(0.0, abs=1.0e-8)
    assert out.T > 500.0
    gap = result.info["T_closure_gap_K"]
    assert abs(gap) < 1.0e-5


def test_r1_uniform_duty(thermo: Thermo) -> None:
    """Uniform duty: the closure returns exactly the stated duty; the ODE heats."""
    feeds, params = _r1a()
    duty = 5000.0
    params_duty = dict(params, thermal={"duty_W": duty})
    result = PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params_duty, thermo)
    # The fixed-duty closure returns exactly the stated duty and solves T_out.
    assert result.duty_W == pytest.approx(duty, rel=1e-9)
    out = result.outlets["outlet"]
    assert out.T > 500.0
    # The ODE profile end temperature agrees with the formation-basis closure
    # to the package-consistency level (see the adiabatic test's docstring).
    assert result.info["T_profile_out_K"] == pytest.approx(out.T, abs=0.05)


def test_r1_equilibrium_approaches_k(thermo: Thermo) -> None:
    """An equilibrium-limited power law (no explicit reverse) approaches Q = K.

    Since #245, ``kinetics.rate`` multiplies the forward rate by
    (1 - Q/K) with Q the ideal-gas activity quotient, so an equilibrium
    model without an explicit reverse is a valid limitation.  Long V at
    fixed T must drive the outlet composition to equilibrium: Q at the
    outlet equals K(T) to 1e-6 relative (review blocking item 2).
    """
    from ngdesign.units._physics.kinetics import equilibrium_constant

    params_eq: dict[str, Any] = {
        "reaction_set": {
            "id": "nc4_isom_eq",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "equilibrium-approach case (review item 2)",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 1.0e3,
                        "Ea": 5.0e4,
                        "orders": {"nC4": 1.0},
                        "basis": "concentration",
                    },
                    "equilibrium": {"form": "from_gibbs"},
                }
            ],
        },
        # tau = V / (F R T / P) ~ 4.8e3 s against k ~ 5.98e-3 s-1:
        # k*tau ~ 29, so the relaxation to Q = K is complete at 1e-6.
        "volume_m3": 100.0,
        "thermal": "isothermal",
    }
    feeds, _ = _r1a()
    result = PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params_eq, thermo)
    out = result.outlets["outlet"]
    rset = reaction_set_param(params_eq["reaction_set"])
    k_eq = equilibrium_constant(rset.reactions[0], out.T)
    q = (out.composition["iC4"] * out.P / 1.0e5) / (out.composition["nC4"] * out.P / 1.0e5)
    assert q == pytest.approx(k_eq, rel=1e-6)


def test_r1_refuses_volume_nonpositive(thermo: Thermo) -> None:
    feeds, params = _r1a()
    with pytest.raises(PlugFlowError, match="volume_m3"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, dict(params, volume_m3=0.0), thermo)


def test_r1_refuses_rate_units(thermo: Thermo) -> None:
    feeds, params = _r1a()
    reaction = params["reaction_set"]["reactions"][0]
    bad = dict(
        params,
        reaction_set=dict(
            params["reaction_set"],
            reactions=[
                dict(
                    reaction,
                    kinetics=dict(reaction["kinetics"], rate_units="mol/(L·s)"),
                )
            ],
        ),
    )
    with pytest.raises(PlugFlowError, match="rate_units"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, bad, thermo)


def test_r1_refuses_missing_bulk_density(thermo: Thermo) -> None:
    feeds, params = _r1a()
    reaction = params["reaction_set"]["reactions"][0]
    cat = dict(
        params,
        reaction_set=dict(
            params["reaction_set"],
            reactions=[
                dict(
                    reaction,
                    kinetics=dict(reaction["kinetics"], rate_units="mol/(kg_cat·s)"),
                )
            ],
        ),
    )
    with pytest.raises(PlugFlowError, match="bulk_density_kg_m3"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, cat, thermo)


def test_r1_refuses_no_kinetics(thermo: Thermo) -> None:
    feeds, params = _r1a()
    bare = dict(
        params,
        reaction_set=dict(
            params["reaction_set"],
            reactions=[{k: v for k, v in params["reaction_set"]["reactions"][0].items() if k != "kinetics"}],
        ),
    )
    with pytest.raises(PlugFlowError, match="has no kinetics"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, bare, thermo)


def test_r1_refuses_bad_thermal_mode(thermo: Thermo) -> None:
    """An unknown thermal mode is a typed PlugFlowError naming thermal."""
    feeds, params = _r1a()
    with pytest.raises(PlugFlowError, match="thermal mode"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, dict(params, thermal="radiative"), thermo)


def test_r1_refuses_unknown_reacting_phase(thermo: Thermo) -> None:
    """An unknown reacting_phase is refused with a typed error naming it."""
    feeds, params = _r1a()
    with pytest.raises(PlugFlowError, match="reacting_phase"):
        PfrR1().solve(
            {"inlet": _flash(thermo, feeds["inlet"])},
            dict(params, reacting_phase="plasma"),
            thermo,
        )


def test_r1_refuses_rhs_cap(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exhausting the RHS evaluation cap is refused as a typed error.

    The cap itself is exercised physically at 20,000 in bench runs; here
    the guard branch is reached deterministically by lowering the cap.
    """
    import ngdesign.units.reactors.plug_flow as plug_flow

    monkeypatch.setattr(plug_flow, "RHS_CAP", 50)
    feeds, params = _r1a()
    with pytest.raises(PlugFlowError, match="RHS evaluation cap"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params, thermo)


def test_r1_refuses_integration_failed(thermo: Thermo, monkeypatch: pytest.MonkeyPatch) -> None:
    """A solver failure (``solve_ivp`` success=False) refuses as a typed error."""
    import ngdesign.units.reactors.plug_flow as plug_flow

    class _FailedSolution:
        success = False
        message = "fake solver failure"

    monkeypatch.setattr(plug_flow, "solve_ivp", lambda *args, **kwargs: _FailedSolution())
    feeds, params = _r1a()
    with pytest.raises(PlugFlowError, match="integration failed"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params, thermo)


def test_r1_refuses_depletion(thermo: Thermo) -> None:
    """A zero-order rate consumes its reactant linearly and must be refused."""
    params_zero: dict[str, Any] = {
        "reaction_set": {
            "id": "nc4_zero_order",
            "components": ["nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "zero-order depletion refusal case",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 0.05,
                        "Ea": 0.0,
                        "orders": {},
                        "basis": "concentration",
                    },
                }
            ],
        },
        # F0 = 1 mol/s, r = 0.05 mol/(m3 s): depleted at V = 20 m3.
        "volume_m3": 25.0,
        "thermal": "isothermal",
    }
    feeds, _ = _r1a()
    with pytest.raises(PlugFlowError, match="depletes"):
        PfrR1().solve({"inlet": _flash(thermo, feeds["inlet"])}, params_zero, thermo)


def test_r1_refuses_two_phase(thermo: Thermo) -> None:
    """A C1/nC5 mixture cooled at uniform duty condenses and is refused."""
    params_cool: dict[str, Any] = {
        "reaction_set": {
            "id": "nc4_isom_cool",
            "components": ["C1", "nC5", "nC4", "iC4"],
            "reactions": [
                {
                    "id": "isom",
                    "stoichiometry": {"nC4": -1.0, "iC4": 1.0},
                    "base_component": "nC4",
                    "provenance": "two-phase refusal case (spec: a feed that condenses)",
                    "kinetics": {
                        "rate_units": "mol/(m3·s)",
                        "k0": 1.0e-3,
                        "Ea": 0.0,
                        "orders": {"nC4": 1.0},
                        "basis": "concentration",
                    },
                }
            ],
        },
        "volume_m3": 1.0,
        "thermal": {"duty_W": -15000.0},
    }
    # A trace of nC4 keeps the kinetics well-defined (the order references it)
    # while the -15 kW uniform duty drives the C1/nC5 mixture through its dew point.
    feed = {
        "T": 350.0,
        "P": 2.0e5,
        "molar_flow": 1.0,
        "composition": {"C1": 0.49, "nC5": 0.5, "nC4": 0.01},
    }
    with pytest.raises(PlugFlowError, match="two-phase"):
        PfrR1().solve({"inlet": _flash(thermo, feed)}, params_cool, thermo)
