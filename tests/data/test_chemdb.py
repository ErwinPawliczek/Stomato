"""Integrity of the cited chemical database, and agreement between its sources."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict

import CoolProp.CoolProp as CP
import pytest

from ngdesign.data import DATA_DIR, chemdb, components
from ngdesign.data.formula import FormulaError, parse_formula
from ngdesign.uom.quantity import convert
from ngdesign.uom.units import parse_unit

_DIR = DATA_DIR / "chemdb"


def _properties() -> list[dict[str, str]]:
    with (_DIR / "properties.csv").open(encoding="utf8", newline="") as handle:
        return list(csv.DictReader(handle))


def _cas_check_digit_valid(cas: str) -> bool:
    """CAS Registry check digit: the digits, weighted from the right, sum mod 10."""
    digits = cas.replace("-", "")
    body, check = digits[:-1], int(digits[-1])
    return sum((i + 1) * int(d) for i, d in enumerate(reversed(body))) % 10 == check


def test_the_database_is_large_and_its_manifest_is_true() -> None:
    manifest = json.loads((_DIR / "MANIFEST.json").read_text())
    species = chemdb.all_species()
    assert len(species) >= 10_000
    assert manifest["row_counts"]["species"] == len(species)
    assert manifest["row_counts"]["properties"] == len(_properties())


def test_every_row_cites_a_known_source_with_its_grade() -> None:
    sources = chemdb.sources()
    for source, grade in {(r["source"], r["grade"]) for r in _properties()}:
        assert source in sources, source
        assert sources[source]["grade"] == grade, source


def test_every_correlation_table_cites_a_known_source() -> None:
    sources = chemdb.sources()
    for name in ("shomate.csv", "antoine.csv", "wagner.csv", "cp_gas.csv"):
        with (_DIR / name).open(encoding="utf8", newline="") as handle:
            for row in csv.DictReader(handle):
                assert row["source"] in sources, f"{name}: {row['source']}"


def test_every_source_has_a_citation() -> None:
    for key, record in chemdb.sources().items():
        assert len(record["citation"]) > 20, key


def test_exactly_one_selected_value_per_species_and_property() -> None:
    selected: Counter[tuple[str, str]] = Counter()
    groups = set()
    for row in _properties():
        groups.add((row["cas"], row["property"]))
        if row["selected"] == "1":
            selected[(row["cas"], row["property"])] += 1
    assert set(selected) == groups
    assert set(selected.values()) == {1}


def test_selection_never_prefers_a_worse_grade() -> None:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in _properties():
        groups[(row["cas"], row["property"])].append(row)
    overridden = 0
    for rows in groups.values():
        chosen = next(r for r in rows if r["selected"] == "1")
        if chosen["grade"] != min(r["grade"] for r in rows):
            overridden += 1
    # the only exceptions are the outlier overrides, each of them logged in AUDIT.txt
    logged = (_DIR / "AUDIT.txt").read_text().count("outvoted ")
    assert overridden <= logged


def test_every_value_is_finite_with_a_stated_si_unit() -> None:
    for row in _properties():
        assert math.isfinite(float(row["value"]))
        parse_unit(row["unit"])
        if row["uncertainty"]:
            assert float(row["uncertainty"]) >= 0.0


@pytest.mark.parametrize(
    "prop", ["Tb", "Tm", "Tc", "Pc", "Vc", "S0_gas", "Cp_gas", "Cp_liquid", "Hvap", "Hfus"]
)
def test_quantities_that_must_be_positive_are(prop: str) -> None:
    offenders = [r for r in _properties() if r["property"] == prop and float(r["value"]) <= 0.0]
    assert offenders == []


def test_cas_numbers_pass_their_check_digit() -> None:
    bad = [s.cas for s in chemdb.all_species() if not _cas_check_digit_valid(s.cas)]
    assert bad == []


def test_inchikeys_are_well_formed() -> None:
    pattern = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
    assert [s.cas for s in chemdb.all_species() if s.inchikey and not pattern.match(s.inchikey)] == []


def test_stated_molar_mass_agrees_with_the_formula() -> None:
    wrong = []
    for species in chemdb.all_species():
        if species.mw is None or re.search(r"[DT]|\[", species.formula):
            continue
        try:
            mass = parse_formula(species.formula).molar_mass
        except FormulaError:
            continue
        if abs(mass - species.mw) > max(0.01 * species.mw, 0.1):
            wrong.append((species.cas, species.formula, species.mw, mass))
    assert wrong == []


def test_identity_is_cross_checked_against_pubchem() -> None:
    species = chemdb.all_species()
    with_pubchem = [s for s in species if s.identity_source == "pubchem"]
    assert len(with_pubchem) > 0.9 * len(species)
    assert all(s.pubchem_cid for s in with_pubchem)


@pytest.mark.parametrize(
    ("query", "cas"),
    [
        ("7732-18-5", "7732-18-5"),
        ("water", "7732-18-5"),
        ("WATER", "7732-18-5"),
        ("H2O", "7732-18-5"),
        ("NH3", "7664-41-7"),  # any atom order
        ("CH3OH", "67-56-1"),
        ("C1", "74-82-8"),  # curated slate id
        ("MEK", "78-93-3"),  # synonym bank
        ("VNWKTOKETHGBQD-UHFFFAOYSA-N", "74-82-8"),  # InChIKey
    ],
)
def test_lookup(query: str, cas: str) -> None:
    assert chemdb.find(query).cas == cas


def test_a_formula_never_silently_picks_an_isomer() -> None:
    # Regression: the synonym bank answers C2H5OH with dimethyl ether.
    with pytest.raises(chemdb.AmbiguousSpeciesError, match="ethanol"):
        chemdb.find("C2H5OH")
    with pytest.raises(chemdb.AmbiguousSpeciesError, match="butane"):
        chemdb.find("C4H10")


def test_oligomer_tables_do_not_land_on_the_monomer() -> None:
    """Regression: JANAF indexes the HF hexamer under HF's CAS."""
    assert all(abs(r.value) < 400_000.0 for r in chemdb.values("HF", "Hf_gas"))


def test_two_registry_numbers_for_one_molecule_are_not_an_ambiguity() -> None:
    assert chemdb.find("Al").cas == "7429-90-5"


def test_a_neutral_formula_never_resolves_to_an_ion() -> None:
    assert chemdb.find("OH").charge == 0


def test_a_shared_name_goes_to_the_documented_neutral_species() -> None:
    # Regression: "iron" reached an ion record carrying a single entropy.
    assert chemdb.find("iron").cas == "7439-89-6"
    assert chemdb.find("Fe").cas == "7439-89-6"


@pytest.mark.parametrize("name", ["glucose", "urea", "styrene", "vinyl chloride", "citric acid", "aspirin"])
def test_common_chemicals_outside_the_thermodynamic_tables_are_present(name: str) -> None:
    assert chemdb.find(name).formula


def test_unknown_species_is_refused() -> None:
    with pytest.raises(chemdb.UnknownSpeciesError):
        chemdb.find("unobtainium")


def test_missing_property_is_refused_not_defaulted() -> None:
    with pytest.raises(chemdb.MissingPropertyError):
        chemdb.value("water", "not_a_property")
    assert chemdb.maybe("water", "not_a_property") is None


def test_search_finds_by_substring() -> None:
    assert any(s.cas == "71-43-2" for s in chemdb.search("benzene"))


def test_the_curated_slate_is_covered() -> None:
    for cid, record in components().items():
        assert chemdb.find(cid).cas == record["cas"]


def test_values_returns_every_source_selected_first() -> None:
    rows = chemdb.values("methane", "Hf_gas")
    assert len({r.source for r in rows}) >= 3
    assert rows[0].selected
    assert chemdb.value("methane", "Hf_gas").source == "atct"


@pytest.mark.parametrize(
    ("species", "fluid"),
    [
        ("water", "Water"),
        ("methane", "Methane"),
        ("ethane", "Ethane"),
        ("propane", "Propane"),
        ("n-butane", "n-Butane"),
        ("n-hexane", "n-Hexane"),
        ("benzene", "Benzene"),
        ("toluene", "Toluene"),
        ("carbon dioxide", "CO2"),
        ("nitrogen", "Nitrogen"),
        ("oxygen", "Oxygen"),
        ("ammonia", "Ammonia"),
        ("methanol", "Methanol"),
        ("ethanol", "Ethanol"),
    ],
)
def test_critical_point_and_boiling_point_match_the_reference_eos(species: str, fluid: str) -> None:
    assert chemdb.value(species, "Tc").value == pytest.approx(CP.PropsSI("Tcrit", fluid), rel=0.005)
    # 2.1 % apart for ethanol: IUPAC 6.137 MPa, the Dillon-Penoncello EOS 6.268 MPa
    assert chemdb.value(species, "Pc").value == pytest.approx(CP.PropsSI("pcrit", fluid), rel=0.025)
    if fluid != "CO2":  # sublimes at 1 atm: no normal boiling point exists
        tb = CP.PropsSI("T", "P", 101325, "Q", 0, fluid)
        assert chemdb.value(species, "Tb").value == pytest.approx(tb, abs=1.0)


def test_evaluated_formation_enthalpies_agree_across_sources() -> None:
    """ATcT and JANAF are separate evaluations and should agree on the typical species.

    The tail is real: JANAF's radicals and fluorides date from the 1970s, which is why
    ATcT ranks first. A wrong table on the wrong CAS shows up in the worst case.
    """
    differences = []
    for species in chemdb.all_species():
        rows = {r.source: r.value for r in chemdb.values(species.cas, "Hf_gas")}
        if "atct" in rows and "janaf" in rows:
            differences.append(abs(rows["atct"] - rows["janaf"]))
    assert len(differences) > 50
    differences.sort()
    assert differences[len(differences) // 2] < 3_000.0
    assert differences[-1] < 250_000.0


def test_formation_values_keep_their_units_across_the_snapshot() -> None:
    """The bundled WebBook snapshot and live pages must share the J/mol scale."""
    ratios = []
    for species in chemdb.all_species():
        rows = {r.source: r.value for r in chemdb.values(species.cas, "Hf_gas")}
        reviewed = rows.get("nist_review", rows.get("nist"))
        if reviewed and "nist_snapshot" in rows and abs(reviewed) > 20_000.0:
            ratios.append(rows["nist_snapshot"] / reviewed)
    assert len(ratios) > 20
    ratios.sort()
    assert 0.9 < ratios[len(ratios) // 2] < 1.1


def test_antoine_windows_are_ordered_and_coefficients_finite() -> None:
    with (_DIR / "antoine.csv").open(encoding="utf8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["Tmin"] and row["Tmax"]:
                assert float(row["Tmin"]) < float(row["Tmax"])
            assert math.isfinite(float(row["A"]))


def test_density_is_in_kg_per_m3() -> None:
    assert chemdb.value("water", "rho_liquid").value == pytest.approx(
        convert(1.0, "g/cm3", "kg/m3"), rel=0.01
    )


def test_every_reference_eos_fluid_keeps_its_critical_point() -> None:
    """Regression: a swapped IUPAC row gave cyclohexane Tc 532.7 K at grade A."""
    checked = 0
    for fluid in CP.get_global_param_string("fluids_list").split(","):
        cas = CP.get_fluid_param_string(fluid, "CAS")
        try:
            Tc = chemdb.value(cas, "Tc").value
        except chemdb.ChemDbError:
            continue
        checked += 1
        assert Tc == pytest.approx(CP.PropsSI("Tcrit", fluid), rel=1e-6), fluid
    assert checked > 80


def test_a_swapped_source_row_is_outvoted_but_kept() -> None:
    assert chemdb.value("cyclohexane", "Tc").source == "coolprop"
    assert 532.0 < min(r.value for r in chemdb.values("cyclohexane", "Tc")) < 533.0
