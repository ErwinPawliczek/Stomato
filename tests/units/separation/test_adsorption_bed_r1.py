"""Closed-form, identity and refusal tests for the adsorption-bed R1.

Numbers are the spec's (``specs/backend/units/adsorption_bed.md``), computed
by ``scratchpad/unit-specs/calc_adsorption_bed.py`` from the spec equations
A1-A7; inputs are illustrative test inputs, not data.

CF1  q_m = 12 mol/kg, b = 5e-3 1/Pa, P = 7e6, y = 1e-3:
     p = y*P = 7000 Pa, q* = 12*5e-3*7000/(1 + 5e-3*7000)
         = 420/36 = 11.6666667 mol/kg.
CF2  + CO2 (q_m = 4, b = 1e-5, y = 0.015): p_CO2 = 105000 Pa,
     denom = 1 + 35 + 1.05 = 37.05,
     q_H2O = 420/37.05 = 11.3360324, q_CO2 = 4.2/37.05 = 0.113360324 mol/kg.
CF3  rho_b = 700, D = 1.5, L = 4.0:
     m_bed = 700*(pi/4)*1.5^2*4.0 = 4948.00843 kg.
     1000 mol/s feed, 100 % H2O removal: N_dot = 1000 mol/s,
     t_s = q* * m_bed / N_dot = 57.726765 s;
     LUB 0.5 m: t_b = t_s*(1 - 0.5/4.0) = 50.5109194 s.

     SPEC ISSUE (flagged on the PR): the spec prints t_s = 57726.765 s and
     t_b = 50510.9194 s -- exactly 1000x the A4 result for its own stated
     inputs. The printed values are q* * m_bed, the bed's molar capacity,
     i.e. the division by N_dot = 1000 mol/s was dropped (they correspond to
     a 1 mol/s adsorbate rate). A4 as written is implemented and asserted;
     the print's rounding is carried in the tolerance, never the factor.

Tolerances: the spec prints 9 significant digits, whose own rounding is up
to ~3e-9 relative, so the printed values are asserted at rel = 1e-8 (the
source's rounding, per U-R2); rel = 1e-9 cannot be met by a 9-digit print
itself. CF4's identity stays at the spec's 1e-12 because it compares two
computations, not a print.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation._util import stream_molar_mass
from ngdesign.units.separation.adsorption_bed import AdsorptionBed
from ngdesign.units.separation.adsorption_bed_r1 import (
    AdsorptionBedR1,
    AdsorptionBedR1SpecError,
    affinity_at_temperature,
    breakthrough_time,
    equilibrium_loadings,
    packed_bed_mass,
    stoichiometric_time,
)
from tests.conftest import flash_feed

P_FEED = 7.0e6

LANGMUIR_H2O = {"q_max_mol_kg": 12.0, "b_1_Pa": 5e-3}


def r1_params(**over: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "removal_fraction": {"H2O": 0.95},
        "langmuir": {"H2O": dict(LANGMUIR_H2O)},
        "bed_mass_kg": 500.0,
    }
    params.update(over)
    return params


def example_inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = AdsorptionBed.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def test_cf1_single_langmuir() -> None:
    """A1 reduces to the plain Langmuir isotherm for one adsorbate."""
    q = equilibrium_loadings({"H2O": 12.0}, {"H2O": 5e-3}, {"H2O": 1e-3 * P_FEED})
    assert 1e-3 * P_FEED == pytest.approx(7000.0, rel=1e-12)
    assert q["H2O"] == pytest.approx(11.6666667, rel=1e-8)


def test_cf2_extended_langmuir() -> None:
    """A1 with a competitor: the shared denominator suppresses both loadings."""
    q = equilibrium_loadings(
        {"H2O": 12.0, "CO2": 4.0},
        {"H2O": 5e-3, "CO2": 1e-5},
        {"H2O": 1e-3 * P_FEED, "CO2": 0.015 * P_FEED},
    )
    assert q["H2O"] == pytest.approx(11.3360324, rel=1e-8)
    assert q["CO2"] == pytest.approx(0.113360324, rel=1e-8)


def test_cf3_geometry_lub_pure_functions() -> None:
    """A3 bed mass from geometry, A4 stoichiometric time, A5 LUB breakthrough."""
    m_bed = packed_bed_mass(700.0, 1.5, 4.0)
    assert m_bed == pytest.approx(4948.00843, rel=1e-9)
    q_star = equilibrium_loadings(
        {"H2O": 12.0}, {"H2O": 5e-3}, {"H2O": 1e-3 * P_FEED}
    )["H2O"]
    t_s = stoichiometric_time(q_star, m_bed, 1000.0)
    assert t_s == pytest.approx(57.726765, rel=1e-8)
    t_b = breakthrough_time(t_s, 0.5, 4.0)
    assert t_b == pytest.approx(50.5109194, rel=1e-8)
    # No LUB (or zero LUB) leaves the stoichiometric time.
    assert breakthrough_time(t_s, 0.0, 4.0) == t_s
    assert breakthrough_time(t_s, 0.5, None) == t_s


def test_cf3_adapter_geometry_case(thermo: Thermo) -> None:
    """The spec's CF3 basis through the adapter: 1000 mol/s of H2O removed.

    Feed 1e6 mol/s with y_H2O = 1e-3 (N2 balance), 100 % H2O removal,
    geometry bed 700 kg/m3, D = 1.5 m, L = 4.0 m, LUB = 0.5 m.
    """
    feed = {
        "T": 322.15,
        "P": P_FEED,
        "molar_flow": 1.0e6,
        "composition": {"H2O": 1e-3, "N2": 1.0 - 1e-3},
    }
    inlets = {"feed_in": flash_feed(thermo, feed)}
    params = r1_params(
        removal_fraction={"H2O": 1.0},
        bed_mass_kg=None,
        bed_density_kg_m3=700.0,
        bed_diameter_m=1.5,
        bed_length_m=4.0,
        lub_m=0.5,
    )
    result = AdsorptionBedR1().solve(inlets, params, thermo)
    assert result.info["bed_mass_kg"] == pytest.approx(4948.00843, rel=1e-9)
    assert result.info["q_eq_mol_kg_H2O"] == pytest.approx(11.6666667, rel=1e-8)
    assert result.info["t_stoich_s_H2O"] == pytest.approx(57.726765, rel=1e-8)
    assert result.info["t_break_s_H2O"] == pytest.approx(50.5109194, rel=1e-8)
    assert result.info["cycle_time_s"] == pytest.approx(50.5109194, rel=1e-8)
    assert result.info["limiting_component_index"] == 0.0
    # A7: the same loading in mass units, q* * MW/1000.
    assert result.info["q_eq_kg_kg_H2O"] == pytest.approx(
        result.info["q_eq_mol_kg_H2O"] * stream_molar_mass({"H2O": 1.0}) / 1000.0,
        rel=1e-12,
    )


def test_cf4_r0_equivalence(thermo: Thermo) -> None:
    """Single adsorbate, no LUB, bed by mass: R1's cycle time == R0's at 1e-12.

    The R0 capacity equivalent is q* * MW/1000 with the actual
    component-database MW (checked against the spec's printed 18.01528).
    The printed capacity 0.210178267 is the CF1 basis (y_H2O = 1e-3); the
    identity itself runs on the example feed with the capacity computed from
    its own y, so it holds at 1e-12 whatever the feed.
    """
    mw_h2o = stream_molar_mass({"H2O": 1.0})
    assert mw_h2o == pytest.approx(18.01528, rel=1e-9)
    q_star_1e3 = 12.0 * 5e-3 * (1e-3 * P_FEED) / (1.0 + 5e-3 * 1e-3 * P_FEED)
    assert q_star_1e3 * mw_h2o / 1000.0 == pytest.approx(0.210178267, rel=1e-8)

    inlets = example_inlets(thermo)
    y = inlets["feed_in"].composition["H2O"]
    q_star = 12.0 * 5e-3 * (y * P_FEED) / (1.0 + 5e-3 * y * P_FEED)
    capacity = q_star * mw_h2o / 1000.0

    r1 = AdsorptionBedR1().solve(inlets, r1_params(), thermo)
    r0 = AdsorptionBed().solve(
        inlets,
        {
            "removal_fraction": {"H2O": 0.95},
            "capacity_kg_per_kg": capacity,
            "bed_mass_kg": 500.0,
        },
        thermo,
    )
    assert r1.info["cycle_time_s"] == pytest.approx(r0.info["cycle_time_s"], rel=1e-12)
    # R0's own cycle time on the CF3 basis with the printed capacity:
    # 0.210178267 * 4948.00843 kg / (1000 mol/s * MW/1000) = 57.726765 s.
    feed = {
        "T": 322.15,
        "P": P_FEED,
        "molar_flow": 1.0e6,
        "composition": {"H2O": 1e-3, "N2": 1.0 - 1e-3},
    }
    inlets3 = {"feed_in": flash_feed(thermo, feed)}
    r0_cf3 = AdsorptionBed().solve(
        inlets3,
        {
            "removal_fraction": {"H2O": 1.0},
            "capacity_kg_per_kg": 0.210178267,
            "bed_mass_kg": 4948.008429403923,
        },
        thermo,
    )
    assert r0_cf3.info["cycle_time_s"] == pytest.approx(57.726765, rel=1e-8)


def test_outlets_identical_to_r0(thermo: Thermo) -> None:
    """R1 changes no stream: the outlets, duty and power equal R0's exactly."""
    inlets = example_inlets(thermo)
    r1 = AdsorptionBedR1().solve(inlets, r1_params(), thermo)
    r0 = AdsorptionBed().solve(
        inlets, {"removal_fraction": {"H2O": 0.95}, "bed_mass_kg": 500.0}, thermo
    )
    assert r1.outlets == r0.outlets
    assert r1.duty_W == r0.duty_W
    assert r1.power_W == r0.power_W
    # R0's adsorbate mass rate is carried through into R1's info.
    assert r1.info["adsorbate_mass_rate_kg_s"] == r0.info["adsorbate_mass_rate_kg_s"]


def test_affinity_at_reference_temperature_is_unchanged() -> None:
    """A2 at T = T_ref reproduces b_ref exactly (the exp argument vanishes)."""
    assert affinity_at_temperature(5e-3, -40000.0, 322.15, 322.15) == pytest.approx(
        5e-3, rel=1e-15
    )
    # And the affinity falls with rising T for an exothermic dH.
    assert affinity_at_temperature(5e-3, -40000.0, 353.15, 322.15) < 5e-3


def test_refuse_langmuir_empty(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="langmuir"):
        AdsorptionBedR1().solve(inlets, r1_params(langmuir={}), thermo)


def test_refuse_langmuir_component_not_in_removal(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="langmuir"):
        AdsorptionBedR1().solve(
            inlets, r1_params(langmuir={"CO2": dict(LANGMUIR_H2O)}), thermo
        )


def test_refuse_removal_without_langmuir(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="langmuir"):
        AdsorptionBedR1().solve(
            inlets, r1_params(removal_fraction={"H2O": 0.95, "CO2": 0.5}), thermo
        )


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param({"q_max_mol_kg": 0.0, "b_1_Pa": 5e-3}, id="q_max_zero"),
        pytest.param({"q_max_mol_kg": -1.0, "b_1_Pa": 5e-3}, id="q_max_negative"),
        pytest.param({"q_max_mol_kg": 12.0, "b_1_Pa": 0.0}, id="b_zero"),
        pytest.param({"q_max_mol_kg": 12.0, "b_1_Pa": -1e-3}, id="b_negative"),
    ],
)
def test_refuse_nonpositive_langmuir_parameters(
    thermo: Thermo, entry: dict[str, float]
) -> None:
    """q_m <= 0 or b <= 0 refuses, naming langmuir and the component id."""
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="langmuir.*H2O"):
        AdsorptionBedR1().solve(inlets, r1_params(langmuir={"H2O": entry}), thermo)


def test_refuse_capacity_given(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="capacity_kg_per_kg"):
        AdsorptionBedR1().solve(inlets, r1_params(capacity_kg_per_kg=0.10), thermo)


def test_refuse_both_bed_forms(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="bed_mass_kg"):
        AdsorptionBedR1().solve(
            inlets,
            r1_params(bed_density_kg_m3=700.0, bed_diameter_m=1.5, bed_length_m=4.0),
            thermo,
        )


def test_refuse_no_bed_form(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="bed_mass_kg"):
        AdsorptionBedR1().solve(inlets, r1_params(bed_mass_kg=None), thermo)


def test_refuse_partial_geometry(thermo: Thermo) -> None:
    """Density and diameter without a length is no bed form at all."""
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="bed_mass_kg"):
        AdsorptionBedR1().solve(
            inlets,
            r1_params(bed_mass_kg=None, bed_density_kg_m3=700.0, bed_diameter_m=1.5),
            thermo,
        )


def test_refuse_negative_lub(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="lub_m"):
        AdsorptionBedR1().solve(inlets, r1_params(lub_m=-0.1), thermo)


def test_refuse_lub_at_or_beyond_bed_length(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="lub_m"):
        AdsorptionBedR1().solve(
            inlets,
            r1_params(
                bed_mass_kg=None,
                bed_density_kg_m3=700.0,
                bed_diameter_m=1.5,
                bed_length_m=4.0,
                lub_m=4.0,
            ),
            thermo,
        )


def test_refuse_lub_without_bed_length(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="lub_m"):
        AdsorptionBedR1().solve(inlets, r1_params(lub_m=0.5), thermo)


def test_refuse_dH_without_T_ref(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="T_ref_K"):
        AdsorptionBedR1().solve(
            inlets, r1_params(dH_ads_J_mol={"H2O": -40000.0}), thermo
        )


def test_refuse_T_ref_without_dH(thermo: Thermo) -> None:
    inlets = example_inlets(thermo)
    with pytest.raises(AdsorptionBedR1SpecError, match="T_ref_K"):
        AdsorptionBedR1().solve(inlets, r1_params(T_ref_K=322.15), thermo)
