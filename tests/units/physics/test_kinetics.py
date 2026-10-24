"""Spec U-R acceptance: reaction physics — rates, extents, K_eq, heat of reaction."""

from __future__ import annotations

import math

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.reactions import Equilibrium, PowerLaw, Reaction, ReactionSet
from ngdesign.data import component_record
from ngdesign.units._physics import (
    KineticsError,
    ReactionExtentError,
    apply_extents,
    enthalpy_with_formation,
    equilibrium_constant,
    heat_of_reaction,
    ln_keq,
    rate,
    stoich_matrix,
    yield_shift,
)

#: CODATA 2018 molar gas constant, J/(mol K).
R_CODATA = 8.31446261815324


def _wgsr() -> Reaction:
    return Reaction(
        id="wgsr",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        equilibrium=Equilibrium(form="from_gibbs"),
        provenance="SVA ch. 13 water-gas shift reaction",
    )


def _combustion_set() -> ReactionSet:
    return ReactionSet(
        id="combustion",
        reactions=[
            Reaction(
                id="methane_combustion",
                # N2 is inert: on the slate, out of the stoichiometry.
                stoichiometry={"CH4": -1.0, "O2": -2.0, "CO2": 1.0, "H2O": 2.0},
                base_component="CH4",
                provenance="SVA ch. 4 complete combustion",
            )
        ],
        components=["CH4", "O2", "N2", "CO2", "H2O"],
    )


def test_wgsr_delta_g_298_matches_published_nist_value() -> None:
    # ΔG°298(WGSR) = −28.62 kJ/mol, assembled from the NIST-JANAF formation
    # Gibbs energies: Gf(CO2) − Gf(CO) − Gf(H2O).
    delta_g_298 = -ln_keq(_wgsr(), 298.15) * R_CODATA * 298.15
    assert delta_g_298 == pytest.approx(-28_620.0, rel=0.005)


def test_wgsr_keq_matches_nist_janaf_within_1_percent() -> None:
    # NIST-JANAF 4th ed. tables (CO C-093, CO2 C-095, H2O H-064), tabulated
    # ΔfG°: Σν·ΔfG° gives ΔrG°(T) = −20474 (500 K), −13068 (700 K), −6249
    # (900 K) J/mol → K = 137.7, 9.443, 2.305. The 1 % gate is the spec's
    # acceptance criterion for the reaction-path assembly in ln_keq.
    janaf_delta_g = {500.0: -20_474.0, 700.0: -13_068.0, 900.0: -6_249.0}
    for t, delta_g in janaf_delta_g.items():
        k = equilibrium_constant(_wgsr(), t)
        k_janaf = math.exp(-delta_g / (R_CODATA * t))
        assert k > 0.0
        assert k / k_janaf == pytest.approx(1.0, abs=0.01)


def test_wgsr_keq_secondary_moe_correlation_check() -> None:
    # Secondary check, Moe 1962 (Chem. Eng. Prog. 58(3), 33–36):
    # log10 K = 2073/T − 2.029. Moe published no numeric accuracy figure;
    # contemporary reviews characterize it as "sufficiently good for design
    # computations". Measured against the NIST-JANAF tables the correlation
    # itself runs K_moe/K_janaf = 0.95 (500 K), 0.90 (700 K), 0.82 (900 K), so
    # the code sits K/K_moe = 1.04 (500 K), 1.11 (700 K), 1.22 (900 K); this
    # secondary gate is ±0.2 around 1.1 — the 1 % JANAF gate above is the
    # acceptance criterion.
    for t in (500.0, 700.0, 900.0):
        k = equilibrium_constant(_wgsr(), t)
        k_moe = 10.0 ** (2073.0 / t - 2.029)
        assert k > 0.0
        assert k / k_moe == pytest.approx(1.1, abs=0.2)


def test_wgsr_keq_decreases_with_temperature_exothermic() -> None:
    ks = [equilibrium_constant(_wgsr(), t) for t in (500.0, 700.0, 900.0)]
    assert ks[0] > ks[1] > ks[2]


def test_ln_keq_polynomial_evaluates_inside_window_only() -> None:
    reaction = Reaction(
        id="polynomial_wgsr",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        equilibrium=Equilibrium(
            form="polynomial",
            polynomial={0.0: 4.333, -1.0: 4273.0},
            t_window=(400.0, 900.0),
        ),
        provenance="test-only polynomial wiring check",
    )
    assert ln_keq(reaction, 600.0) == pytest.approx(4.333 + 4273.0 / 600.0, rel=1e-12)
    with pytest.raises(KineticsError, match="window"):
        ln_keq(reaction, 1000.0)


def test_heat_of_reaction_nh3_synthesis_at_298() -> None:
    # N2 + 3 H2 -> 2 NH3: ΔH°298 = −91.8 kJ per extent. The databank ships
    # ΔfH°(NH3, g) = −45.558 kJ/mol; NIST-JANAF H-083 tabulates −45.898
    # kJ/mol — a 340 J/mol (0.74 %) databank offset. The ±0.3 kJ/mol
    # tolerance is anchored to the databank value and is NOT widened to cover
    # the offset: it must stay tight enough to catch wiring regressions, and
    # the offset is databank property uncertainty, not a code error. Elements
    # contribute exactly 0.
    reaction = Reaction(
        id="nh3_synthesis",
        stoichiometry={"N2": -1.0, "H2": -3.0, "NH3": 2.0},
        base_component="N2",
        provenance="SVA ch. 13 ammonia synthesis stoichiometry",
    )
    per_extent = heat_of_reaction(reaction, 298.15)
    assert per_extent / 2.0 == pytest.approx(-45_558.0, abs=300.0)


def test_first_order_rate_matches_closed_form() -> None:
    # Wiring check for basis and orders: rate == k0·exp(−Ea/(R·T))·y_CO·P/(R·T),
    # computed independently here from the cited CODATA constant.
    reaction = Reaction(
        id="wgsr_first_order",
        stoichiometry={"CO": -1.0, "H2O": -1.0, "CO2": 1.0, "H2": 1.0},
        base_component="CO",
        kinetics=PowerLaw(
            rate_units="mol/(m3·s)",
            k0=3.0,
            Ea=50_000.0,
            orders={"CO": 1.0},
            basis="concentration",
        ),
        provenance="test-only closed-form wiring check",
    )
    t, p = 500.0, 200_000.0
    z = {"CO": 0.2, "H2O": 0.3, "CO2": 0.1, "H2": 0.4}
    expected = 3.0 * math.exp(-50_000.0 / (R_CODATA * t)) * z["CO"] * p / (R_CODATA * t)
    assert rate(reaction, t, p, z) == pytest.approx(expected, rel=1e-12)


def test_rate_without_kinetics_is_zero() -> None:
    assert rate(_wgsr(), 500.0, 1e5, {"CO": 0.25}) == 0.0


def test_apply_extents_conserves_mass() -> None:
    rset = _combustion_set()
    n_in = {"CH4": 1.0, "O2": 2.5, "N2": 9.4, "CO2": 0.0, "H2O": 0.0}
    n_out = apply_extents(n_in, rset, [0.5])
    mass_in = sum(n * component_record(c)["mw"] for c, n in n_in.items())
    mass_out = sum(n * component_record(c)["mw"] for c, n in n_out.items())
    assert mass_out == pytest.approx(mass_in, rel=1e-12)
    assert n_out["CH4"] == pytest.approx(0.5)
    assert n_out["CO2"] == pytest.approx(0.5)
    assert n_out["H2O"] == pytest.approx(1.0)


def test_apply_extents_refuses_negative_components_naming_them() -> None:
    rset = _combustion_set()
    with pytest.raises(ReactionExtentError) as excinfo:
        apply_extents({"CH4": 1.0, "O2": 2.5, "N2": 9.4}, rset, [2.0])
    assert "CH4" in str(excinfo.value)


def test_apply_extents_refuses_extent_count_mismatch() -> None:
    with pytest.raises(KineticsError, match="extents"):
        apply_extents({"CH4": 1.0}, _combustion_set(), [0.5, 0.5])


def test_stoich_matrix_rejects_component_outside_slate() -> None:
    reaction = _wgsr()
    rset = ReactionSet(id="wgsr_set", reactions=[reaction], components=list(reaction.stoichiometry))
    with pytest.raises(KineticsError) as excinfo:
        stoich_matrix(rset, ["CO", "H2O", "CO2"])
    assert "H2" in str(excinfo.value)


def test_stoich_matrix_layout_matches_slate_order() -> None:
    rset = _combustion_set()
    slate = ["CH4", "O2", "N2", "CO2", "H2O"]
    matrix = stoich_matrix(rset, slate)
    assert matrix == [[-1.0, -2.0, 0.0, 1.0, 2.0]]


def test_enthalpy_with_formation_matches_heat_of_reaction(thermo: Thermo) -> None:
    # Solve three pure-vapour streams at 298.15 K with the registered PR
    # package and check that the formation-lifted product−reactant enthalpy
    # difference equals the ideal-gas heat of reaction (the small pure-vapour
    # reference offsets of the cubic package nearly cancel across species).
    reaction = Reaction(
        id="nh3_synthesis",
        stoichiometry={"N2": -1.0, "H2": -3.0, "NH3": 2.0},
        base_component="N2",
        provenance="SVA ch. 13 ammonia synthesis stoichiometry",
    )
    state_n2 = thermo.flash_pt({"N2": 1.0}, 298.15, 1000.0, 1.0)
    state_h2 = thermo.flash_pt({"H2": 1.0}, 298.15, 1000.0, 3.0)
    state_nh3 = thermo.flash_pt({"NH3": 1.0}, 298.15, 1000.0, 2.0)
    delta_h = (
        enthalpy_with_formation(state_nh3)
        - enthalpy_with_formation(state_n2)
        - enthalpy_with_formation(state_h2)
    )
    assert delta_h == pytest.approx(heat_of_reaction(reaction, 298.15), rel=2e-3)


# --- yield_shift (spec U-F step 1) -----------------------------------------


def _smr_yield_shift_basis() -> tuple[dict[str, float], list[str], list[str], list[float], dict[str, float]]:
    """Closed-form basis: steam-methane reforming lumped at fixed conversion.

    CH4 + H2O -> CO + 3H2 at X = 0.7 on a 10 CH4 + 40 H2O feed (with 5 N2
    passing through): outlet moles CH4 3, H2O 33, CO 7, H2 21, N2 5. The mass
    yields are the exact product masses over the consumed-feed mass, so the
    shift reproduces the outlet mole numbers exactly.
    """
    n_in = {"CH4": 10.0, "H2O": 40.0, "N2": 5.0}
    n_expect = {"CH4": 3.0, "H2O": 33.0, "CO": 7.0, "H2": 21.0, "N2": 5.0}
    feed_cids = ["CH4", "H2O"]
    products = ["CH4", "H2O", "CO", "H2"]
    consumed_mass = 10.0 * component_record("CH4")["mw"] + 40.0 * component_record("H2O")["mw"]
    yields_mass = [
        3.0 * component_record("CH4")["mw"] / consumed_mass,
        33.0 * component_record("H2O")["mw"] / consumed_mass,
        7.0 * component_record("CO")["mw"] / consumed_mass,
        21.0 * component_record("H2")["mw"] / consumed_mass,
    ]
    return n_in, feed_cids, products, yields_mass, n_expect


def test_yield_shift_matches_closed_form_moles() -> None:
    n_in, feed_cids, products, yields_mass, n_expect = _smr_yield_shift_basis()
    n_out = yield_shift(n_in, feed_cids, yields_mass, products)
    assert set(n_out) == set(n_expect)
    for cid, expected in n_expect.items():
        assert n_out[cid] == pytest.approx(expected, abs=1e-9)


def test_yield_shift_conserves_mass() -> None:
    n_in, feed_cids, products, yields_mass, n_expect = _smr_yield_shift_basis()
    mass_in = math.fsum(n * component_record(cid)["mw"] for cid, n in n_in.items())
    n_out = yield_shift(n_in, feed_cids, yields_mass, products)
    mass_out = math.fsum(n * component_record(cid)["mw"] for cid, n in n_out.items())
    assert mass_out == pytest.approx(mass_in, rel=1e-12)


def test_yield_shift_refuses_yields_off_one_naming_the_sum() -> None:
    n_in, feed_cids, _products, _yields_mass, _n_expect = _smr_yield_shift_basis()
    bad = [0.3, 0.3, 0.3, 0.2]  # sums to 1.1
    with pytest.raises(KineticsError, match="sum to 1.1"):
        yield_shift(n_in, feed_cids, bad, ["CH4", "H2O", "CO", "H2"])


def test_yield_shift_refuses_negative_yield_naming_the_product() -> None:
    n_in, feed_cids, _products, _yields_mass, _n_expect = _smr_yield_shift_basis()
    with pytest.raises(KineticsError, match="negative mass yield for \\['CO'\\]"):
        yield_shift(n_in, feed_cids, [0.2, 0.7, -0.1, 0.2], ["CH4", "H2O", "CO", "H2"])


def test_yield_shift_refuses_missing_feed_component_naming_it() -> None:
    n_in, _feed_cids, products, yields_mass, _n_expect = _smr_yield_shift_basis()
    with pytest.raises(KineticsError, match="feed component 'C2H6' is not in the mixture"):
        yield_shift(n_in, ["C2H6"], yields_mass, products)


def test_yield_shift_refuses_misaligned_products_and_yields() -> None:
    n_in, feed_cids, _products, _yields_mass, _n_expect = _smr_yield_shift_basis()
    with pytest.raises(KineticsError, match="4 product ids for 3 mass yields"):
        yield_shift(n_in, feed_cids, [0.5, 0.3, 0.2], ["CH4", "H2O", "CO", "H2"])


def test_yield_shift_refuses_duplicate_product_naming_it() -> None:
    n_in, feed_cids, _products, _yields_mass, _n_expect = _smr_yield_shift_basis()
    with pytest.raises(KineticsError, match="duplicate product 'CO'"):
        yield_shift(n_in, feed_cids, [0.5, 0.5], ["CO", "CO"])


def test_yield_shift_refuses_non_finite_yield_naming_the_product() -> None:
    n_in, feed_cids, _products, _yields_mass, _n_expect = _smr_yield_shift_basis()
    # NaN passes both the negative check (NaN < 0 is False) and a naive sum
    # check (abs(NaN - 1) > 1e-9 is False), so it must be refused explicitly.
    with pytest.raises(KineticsError, match=r"mass yield for \['CO'\] is not finite"):
        yield_shift(n_in, feed_cids, [0.2, 0.7, float("nan"), 0.1], ["CH4", "H2O", "CO", "H2"])
