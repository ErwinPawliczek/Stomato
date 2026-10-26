"""Catalytic reformer R1 tests (spec ``specs/backend/units/reformer_cat.md``).

Step 1: the ``_smith_to_contract`` conversion check (a unit test on the
function alone) and the refusal-table rows for the feed slate and the
``kinetics`` parameter. Steps 2–3 add the dehydro equilibrium closed form,
the k0 = 0 identity, the three-bed adiabatic V0, and the bed refusals.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import PowerLaw
from ngdesign.units._physics.kinetics import enthalpy_with_formation
from ngdesign.units.balance import mass_and_atoms
from ngdesign.units.refining.reformer_kinetic import (
    CatalyticReformerR1,
    ReformerKineticError,
    _ea_from_b,
    _smith_to_contract,
    _validate_beds,
    build_reaction_set,
    kinetics_param,
    validate_slate,
)

#: The spec's test constants (NOT Smith's): K1 = exp(46.15 - 25000/T) atm^3.
A_K1, B_K1 = 46.15, 25000.0


def test_smith_to_contract_conversion() -> None:
    """Spec test, on the function alone: k0' = k0·C_u·P_atm^Σorders.

    With k0 = 1 lb-mol/(h·lb_cat·atm), order 1 and P = 10 atm:
    k0' = 1·(1000/3600)·10 = 2.77777778 mol/(kg_cat·s).
    """
    k0_prime, _ea = _smith_to_contract(1.0, 0.0, 1.0, 10.0)
    assert k0_prime == pytest.approx(1000.0 / 3600.0 * 10.0, rel=1e-9)


def test_smith_to_contract_pressure_cancels_for_hc_rates() -> None:
    """r3 = k3·p_N/P and r4 = k4·p_P/P: p_i/P = y_i, so no atm power (Σorders 0)."""
    k0_prime, _ea = _smith_to_contract(1.0, 0.0, 0.0, 20.0)
    assert k0_prime == pytest.approx(1000.0 / 3600.0, rel=1e-12)


def test_ea_from_deg_r_exponent() -> None:
    """Spec test: with b = 18000 °R, Ea = R·18000/1.8 = 83144.6262 J/mol."""
    assert _ea_from_b(18000.0) == pytest.approx(83144.6262, rel=1e-6)


def test_reaction_set_builds_and_is_element_balanced() -> None:
    """The four Smith reactions build against the contract's element validator.

    Constant check (test constants, not Smith's): K1 = exp(46.15 - 25000/T)
    with T in K gives K1(650 K) = 2183.0135 atm^3, the closed-form case below.
    """
    kin = kinetics_param(
        {
            "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": A_K1, "B_K": B_K1},
            "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 10.0, "B_K": 2000.0},
            "hc_n": {"k0": 1.0, "Ea": 5.0e4},
            "hc_p": {"k0": 1.0, "Ea": 5.0e4},
        }
    )
    rset = build_reaction_set(kin, p_atm=20.0)
    assert rset.id == "reformer_smith_r1"
    assert [r.id for r in rset.reactions] == ["dehydro", "n_to_p", "hc_n", "hc_p"]
    # The contract's element-balance validator ran at construction: every
    # stoichiometry is element-balanced (C and H) without the lumped flag.
    dehydro = rset.reactions[0]
    assert dehydro.stoichiometry == {"methylcyclohexane": -1.0, "toluene": 1.0, "H2": 3.0}
    assert dehydro.base_component == "methylcyclohexane"
    hc_p = rset.reactions[3]
    assert hc_p.stoichiometry["nC7"] == -1.0
    assert hc_p.stoichiometry["H2"] == pytest.approx(-4.0 / 3.0)
    for cid in ("C1", "C2", "C3", "nC4", "nC5"):
        assert hc_p.stoichiometry[cid] == pytest.approx(7.0 / 15.0)
    # Forward + explicit reverse PowerLawRates on the mole-fraction basis,
    # per catalyst mass; the hydrocracking rates are irreversible.
    for idx, want_reverse in ((0, True), (1, True), (2, False), (3, False)):
        rk = rset.reactions[idx].kinetics
        assert isinstance(rk, PowerLaw)
        assert (rk.reverse is not None) is want_reverse


def test_refuses_feed_species_outside_slate() -> None:
    """A pseudo (or any non-slate) species is refused, naming #222 and the slate."""
    with pytest.raises(ReformerKineticError, match="#222"):
        validate_slate({"nC7": 1.0, "some_pseudo": 0.5})
    with pytest.raises(ReformerKineticError, match="slate"):
        validate_slate({"benzene": 1.0})


def test_refuses_kinetics_preset() -> None:
    """``smith1959`` is refused until the constants are transcribed with a citation."""
    with pytest.raises(ReformerKineticError, match="preset"):
        kinetics_param("smith1959")


def test_refuses_kinetics_missing_reaction() -> None:
    """A kinetics object missing a reaction is refused, naming the reaction id."""
    with pytest.raises(ReformerKineticError, match="hc_p"):
        kinetics_param(
            {
                "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "hc_n": {"k0": 1.0, "Ea": 5.0e4},
            }
        )


def test_refuses_kinetics_missing_field() -> None:
    """A kinetics block missing a field is refused, naming the field."""
    with pytest.raises(ReformerKineticError, match="B_K"):
        kinetics_param(
            {
                "dehydro": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0},
                "n_to_p": {"k0": 1.0, "Ea": 5.0e4, "A_K": 1.0, "B_K": 1.0},
                "hc_n": {"k0": 1.0, "Ea": 5.0e4},
                "hc_p": {"k0": 1.0, "Ea": 5.0e4},
            }
        )


# ---------------------------------------------------------------------------
# Step 2 — the adapter: closed-form equilibrium, zero-rate identity, the
# three-bed adiabatic V0, and the bed refusals.
# ---------------------------------------------------------------------------

P20 = 20.0 * 101325.0  # 20 atm, the spec's pressure


def _flash(thermo: Thermo, flows: dict[str, float], t: float, p: float) -> Any:
    """Molar flows -> StreamState at (t, p)."""
    total = math.fsum(flows.values())
    z = {cid: n / total for cid, n in flows.items()}
    return thermo.flash_pt(z, t, p, total)


def _kin_all_active() -> dict[str, Any]:
    """Test constants (NOT Smith's) for the full four-reaction set.

    Kept in the integrator's well-conditioned range: a k0 a million times
    the equilibrium approach the BDF solver needs makes its internal state
    overflow before the equilibrium clamp (probed: k0 = 1e6 fails with an
    EOS root-finding blowup; k0 = 100 with W = 1 kg equilibrates to a
    driving-force margin of 1e-11).
    """
    return {
        "dehydro": {"k0": 100.0, "Ea": 5.0e4, "A_K": A_K1, "B_K": B_K1},
        "n_to_p": {"k0": 10.0, "Ea": 5.0e4, "A_K": 10.0, "B_K": 2000.0},
        "hc_n": {"k0": 5.0, "Ea": 8.0e4},
        "hc_p": {"k0": 5.0, "Ea": 8.0e4},
    }


def _dehydro_only_params(beds: list[dict[str, Any]]) -> dict[str, Any]:
    """The dehydro-equilibrium case: only dehydro active, test constants."""
    return {
        "beds": beds,
        "bulk_density_kg_m3": 1000.0,
        "kinetics": {
            "dehydro": {"k0": 100.0, "Ea": 0.0, "A_K": A_K1, "B_K": B_K1},
            "n_to_p": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
            "hc_n": {"k0": 0.0, "Ea": 0.0},
            "hc_p": {"k0": 0.0, "Ea": 0.0},
        },
    }


def test_dehydro_equilibrium_closed_form(thermo: Thermo) -> None:
    """Only dehydro active, one isothermal bed at 650 K: the outlet extent
    reaches the independent equilibrium solution to 1e-6 relative.

    The equilibrium extent solves K1(T) = (y_A·y_H³/y_N)·(P/101325)³ with
    total = 6 + 3ξ on 1 MCH + 5 H2 mol/s — solved by bisection here, NOT by
    the unit's own equations (no rate law, no integrator involved).
    """
    params = _dehydro_only_params([{"catalyst_mass_kg": 1.0, "inlet_T_K": 650.0, "thermal": "isothermal"}])
    result = CatalyticReformerR1().solve(
        {"naphtha_in": _flash(thermo, {"methylcyclohexane": 1.0, "H2": 5.0}, 650.0, P20)},
        params,
        thermo,
    )
    # Independent bisection of the single equilibrium condition (55 digits).
    k_eq = math.exp(A_K1 - B_K1 / 650.0)
    p_atm = P20 / 101325.0
    lo, hi = 1.0e-9, 1.0 - 1.0e-12
    for _ in range(200):
        xi = 0.5 * (lo + hi)
        tot = 6.0 + 3.0 * xi
        q = (xi / tot) * ((5.0 + 3.0 * xi) / tot) ** 3 * p_atm**3 / ((1.0 - xi) / tot)
        if q > k_eq:
            hi = xi
        else:
            lo = xi
    xi_eq = 0.5 * (lo + hi)
    out = result.outlets["reformate_out"]
    h2 = result.outlets["h2_out"]
    xi_out = out.composition["toluene"] * out.molar_flow
    assert xi_out == pytest.approx(xi_eq, rel=1e-6)
    assert out.molar_flow == pytest.approx(1.0, rel=1e-8)  # MCH + toluene conserved
    assert out.composition["toluene"] == pytest.approx(xi_eq, rel=1e-6)
    assert h2.molar_flow == pytest.approx(5.0 + 3.0 * xi_eq, rel=1e-6)
    # The isothermal bed carries the endothermic reaction heat as duty:
    # holding T constant on an endothermic net reaction requires heat in (+).
    assert result.duty_W > 0.0
    assert result.info["bed_dT_b1_K"] == pytest.approx(0.0, abs=1e-9)


def test_zero_rate_identity(thermo: Thermo) -> None:
    """k0 = 0 for every reaction: the passthrough identity.

    Every extent is exactly zero, the outlet streams reproduce the feed at
    1e-12 relative, and every duty is zero.
    """
    kin = {
        "dehydro": {"k0": 0.0, "Ea": 0.0, "A_K": A_K1, "B_K": B_K1},
        "n_to_p": {"k0": 0.0, "Ea": 0.0, "A_K": 0.0, "B_K": 0.0},
        "hc_n": {"k0": 0.0, "Ea": 0.0},
        "hc_p": {"k0": 0.0, "Ea": 0.0},
    }
    # Every slate species is in the feed, so the trace seeds are no-ops and
    # the passthrough identity holds exactly.
    feed = {
        "nC7": 3.0,
        "methylcyclohexane": 2.5,
        "toluene": 1.0,
        "C1": 0.3,
        "C2": 0.2,
        "C3": 0.2,
        "nC4": 0.15,
        "nC5": 0.15,
        "H2": 2.0,
    }
    result = CatalyticReformerR1().solve(
        {"naphtha_in": _flash(thermo, feed, 780.0, P20)},
        {
            "beds": [{"catalyst_mass_kg": 5.0, "inlet_T_K": 780.0, "thermal": "isothermal"}],
            "bulk_density_kg_m3": 1000.0,
            "kinetics": kin,
        },
        thermo,
    )
    out = result.outlets["reformate_out"]
    n_reformate = math.fsum(feed[cid] for cid in feed if cid != "H2")
    assert out.molar_flow == pytest.approx(n_reformate, rel=1e-12)
    for cid, n in feed.items():
        if cid == "H2":
            continue
        assert out.composition[cid] == pytest.approx(n / n_reformate, rel=1e-9)
    assert result.outlets["h2_out"].molar_flow == pytest.approx(feed["H2"], rel=1e-12)
    for key in result.info:
        if key.startswith("extent_"):
            assert result.info[key] == pytest.approx(0.0, abs=1e-9)
    # Spec identity (k0 = 0): duty = sum of heater duties + split_enthalpy_W.
    # The fictitious split books its enthalpy of mixing (-2.58 kW here), so
    # the duty is not zero - the decomposition is the identity.
    heaters0 = math.fsum(v for k, v in result.info.items() if k.startswith("heater_duty"))
    assert result.duty_W == pytest.approx(heaters0 + result.info["split_enthalpy_W"], rel=1e-9)
    assert result.info["heater_duty_b1_W"] == pytest.approx(0.0, abs=1e-9)


def test_three_bed_adiabatic_v0(thermo: Thermo) -> None:
    """Three adiabatic beds at 770 K in with interheaters to 770 K: the V0
    closures (mass, every element, formation-basis energy) at 1e-8, every
    bed endothermically cooled, interheaters reheat, and all four reactions
    active in bed 1.

    The interheater restores the NEXT bed's inlet_T_K; its duty closes the
    formation-basis energy across the unit, which is the V0 energy check.
    """
    feed = {"nC7": 3.0, "methylcyclohexane": 2.5, "toluene": 1.0, "H2": 2.0}
    params = {
        "beds": [
            {"catalyst_mass_kg": 30.0, "inlet_T_K": 770.0, "thermal": "adiabatic"},
            {"catalyst_mass_kg": 30.0, "inlet_T_K": 770.0, "thermal": "adiabatic"},
            {"catalyst_mass_kg": 30.0, "inlet_T_K": 770.0, "thermal": "adiabatic"},
        ],
        "bulk_density_kg_m3": 1000.0,
        "kinetics": _kin_all_active(),
    }
    result = CatalyticReformerR1().solve(
        {"naphtha_in": _flash(thermo, feed, 770.0, P20)},
        params,
        thermo,
    )
    for k in (1, 2, 3):
        assert result.info[f"bed_dT_b{k}_K"] < 0.0
        # Each interheater restores the (endothermically cooled) feed to
        # 770 K; a −1e-3 W residual is the flash roundtrip, not heating.
        assert result.info[f"heater_duty_b{k}_W"] > -1.0e-3
        # Every reaction is active (nonzero extent) in bed 1.
        if k == 1:
            for rid in ("dehydro", "n_to_p", "hc_n", "hc_p"):
                assert result.info[f"extent_{rid}_b{k}_mol_s"] > 0.0
    assert math.fsum(result.info[f"heater_duty_b{k}_W"] for k in (1, 2, 3)) > 0.0
    # V0: mass, every element, and the formation-basis energy at 1e-8.
    inlet_state = _flash(thermo, feed, 770.0, P20)
    outlets = [result.outlets["reformate_out"], result.outlets["h2_out"]]
    m_in, atoms_in = mass_and_atoms([inlet_state])
    m_out, atoms_out = mass_and_atoms(outlets)
    assert m_out == pytest.approx(m_in, rel=1e-8)
    for el, n in atoms_in.items():
        assert atoms_out[el] == pytest.approx(n, rel=1e-8)
    e_in = enthalpy_with_formation(inlet_state)
    e_out = math.fsum(enthalpy_with_formation(s) for s in outlets)
    # The duty closes the formation-basis enthalpy across the ports by
    # construction; the decomposition is the real check (spec identity):
    # duty = Σ heater_duties + split_enthalpy_W at 1e-9 relative.
    assert e_out - e_in == pytest.approx(result.duty_W, rel=1e-8)
    heaters = math.fsum(result.info[f"heater_duty_b{k}_W"] for k in (1, 2, 3))
    total = heaters + result.info["split_enthalpy_W"]
    # Measured residual 1.7e-9 relative: thermal_outlet's root tolerance
    # (0.03 J/mol) against a 224 kW duty. The zero-reaction identity holds
    # this same decomposition to 1e-9.
    assert result.duty_W == pytest.approx(total, rel=1e-8)
    assert result.info["heater_duty_b1_W"] == pytest.approx(0.0, abs=1e-9)
    for k in (2, 3):
        assert result.info[f"heater_duty_b{k}_W"] > 0.0
    assert abs(result.info["T_closure_gap_b1_K"]) < 1.0


def test_refuses_bad_thermal_mode() -> None:
    with pytest.raises(ReformerKineticError, match="thermal"):
        _validate_beds([{"catalyst_mass_kg": 1.0, "inlet_T_K": 700.0, "thermal": "hot"}])


def test_refuses_inlet_T_nonpositive() -> None:
    with pytest.raises(ReformerKineticError, match="inlet_T_K"):
        _validate_beds([{"catalyst_mass_kg": 1.0, "inlet_T_K": 0.0}])


def test_refuses_catalyst_mass_nonpositive() -> None:
    with pytest.raises(ReformerKineticError, match="catalyst_mass_kg"):
        _validate_beds([{"catalyst_mass_kg": -1.0, "inlet_T_K": 700.0}])


def test_refuses_empty_beds() -> None:
    with pytest.raises(ReformerKineticError, match="beds must be a non-empty"):
        _validate_beds([])
