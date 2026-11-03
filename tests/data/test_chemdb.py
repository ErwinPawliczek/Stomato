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
    for name in ("shomate.csv", "antoine.csv", "wagner.csv", "cp_gas.csv", "cp_gas_points.csv"):
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


@pytest.mark.parametrize(("name", "prop"), [("CI4", "Hf_solid"), ("iodoform", "Hf_solid")])
def test_a_source_sign_slip_is_caught_by_the_gas(name: str, prop: str) -> None:
    """Regression: the CRC table prints these with the wrong sign, grade B, selected."""
    assert chemdb.value(name, prop).value > 0.0
    assert any(r.value < 0.0 and not r.selected for r in chemdb.values(name, prop))


def test_an_ionic_solid_keeps_its_large_gap_below_the_gas() -> None:
    """MgO sits over 600 kJ/mol below its gas: real, and not a reason to move the selection."""
    gas, solid = chemdb.value("MgO", "Hf_gas").value, chemdb.value("MgO", "Hf_solid")
    assert solid.source == "janaf"
    assert gas - solid.value > 500_000.0


def test_condensed_phases_lie_below_their_gas() -> None:
    """Selected ΔfH° across phases, on the species that have a row to choose from."""
    wrong = []
    for species in chemdb.all_species():
        gas = chemdb.maybe(species.cas, "Hf_gas")
        for prop in ("Hf_liquid", "Hf_solid"):
            value = chemdb.maybe(species.cas, prop)
            if gas is None or value is None or len(chemdb.values(species.cas, prop)) < 2:
                continue
            if not gas - value > 0.0:
                wrong.append((species.name, prop, gas, value))
    assert len(wrong) < 40, wrong[:10]


def test_fixed_points_are_ordered_for_almost_every_species() -> None:
    wrong = []
    for species in chemdb.all_species():
        tm, tb, tc = (chemdb.maybe(species.cas, p) for p in ("Tm", "Tb", "Tc"))
        if tb is not None and tc is not None and tb >= tc:
            wrong.append((species.name, "Tb>Tc", tb, tc))
        if tm is not None and tb is not None and tm >= tb and chemdb.value(species.cas, "Tb").grade != "C":
            wrong.append((species.name, "Tm>Tb", tm, tb))
    assert len(wrong) < 0.01 * len(chemdb.all_species()), wrong[:10]


@pytest.mark.parametrize(
    ("species", "fluid"),
    [
        ("water", "Water"),
        ("benzene", "Benzene"),
        ("n-hexane", "n-Hexane"),
        ("ammonia", "Ammonia"),
        ("CO2", "CO2"),
    ],
)
def test_acentric_factor_matches_the_reference_eos(species: str, fluid: str) -> None:
    assert chemdb.value(species, "omega").value == pytest.approx(CP.PropsSI("acentric", fluid), abs=0.01)


def test_omega_from_its_definition_agrees_with_stated_values() -> None:
    """The derived row, where a stated row exists to judge it, on a broad sample."""
    differences = []
    for species in chemdb.all_species():
        rows = {r.source: r.value for r in chemdb.values(species.cas, "omega")}
        if "omega_definition" in rows and "psrk" in rows:
            differences.append(abs(rows["omega_definition"] - rows["psrk"]))
    assert len(differences) > 100
    differences.sort()
    assert differences[len(differences) // 2] < 0.02


@pytest.mark.parametrize(
    ("query", "fluid", "T"),
    [("n-octane", "n-Octane", 350.0), ("acetone", "Acetone", 320.0), ("1-butene", "1-Butene", 280.0)],
)
def test_broader_vapour_pressure_coverage_matches_the_reference_eos(query: str, fluid: str, T: float) -> None:
    from ngdesign.data import vapour_pressure

    fit = vapour_pressure.fit_at(query, T)
    assert fit is not None
    assert fit.pressure(T) == pytest.approx(CP.PropsSI("P", "T", T, "Q", 0, fluid), rel=0.02)


def test_liquid_fit_model_tracks_the_reference_cp() -> None:
    from ngdesign.data.species_models import _CpFitCurve, _liquid_fit_pieces

    pieces = _liquid_fit_pieces("71-43-2")
    assert pieces
    curve = _CpFitCurve(pieces, 0.0)
    assert curve.cp(330.0) == pytest.approx(CP.PropsSI("CPMOLAR", "T", 330.0, "Q", 0, "Benzene"), rel=0.02)
    h = 0.5
    assert (curve.dh(330.0 + h) - curve.dh(330.0 - h)) / (2 * h) == pytest.approx(curve.cp(330.0), rel=1e-4)
    assert (curve.s(330.0 + h) - curve.s(330.0 - h)) / (2 * h) == pytest.approx(
        curve.cp(330.0) / 330.0, rel=1e-4
    )


def test_dissolved_gas_sources_agree_where_both_exist() -> None:
    """Sander's compilation and the WebBook Henry medians are separate routes to S°(aq)."""
    for gas in ("CO2", "H2S", "methane", "oxygen"):
        rows = {r.source: r.value for r in chemdb.values(gas, "Hf_aq")}
        assert {"nist_henry", "sander"} <= set(rows), gas
        assert rows["nist_henry"] == pytest.approx(rows["sander"], abs=1500.0), gas


def test_snapshot_shomate_gives_solids_a_heat_capacity() -> None:
    from ngdesign.data.species_models import species_thermo

    solids = [
        s for s in chemdb.all_species()[:4000] if any(r["F"] is None for r in chemdb.shomate(s.cas, "solid"))
    ]
    assert solids
    modelled = 0
    for species in solids[:40]:
        try:
            model = species_thermo(species.cas, "solid")
        except chemdb.ChemDbError:
            continue
        if model.model == "cp_fit:nist_snapshot":
            modelled += 1
            h = 0.5
            T = 500.0 if model.t_range[1] > 501 else (model.t_range[0] + model.t_range[1]) / 2
            assert (model.h(T + h) - model.h(T - h)) / (2 * h) == pytest.approx(model.cp(T), rel=1e-6)
            assert 0.0 < model.cp(T) < 2000.0  # a units slip shows here first (it did: -2.9e6)
    assert modelled > 0


def test_ammonia_solubility_follows_the_reviewed_compilation_value() -> None:
    """The NH3 flag: the packaged Sander set gives 42.7 mol/(kg bar), the WebBook median 58.

    Sander's compilation itself, version 5.0.0 (Atmos. Chem. Phys. 23, 10901, 2023;
    https://www.henrys-law.org/henry/casrn/7664-41-7, retrieved 2026-11-02), lists its
    literature-review ("L") entries at Hscp = 0.59 mol/(m3 Pa), 4200 K: 59 mol/(kg bar)
    with water at 997 kg/m3. The packaged 42.7 matches none of them, so the WebBook value
    stays selected and the solubility it gives must sit near the reviewed one.
    """
    from ngdesign.chem.thermochem import reaction_thermo

    k = reaction_thermo("NH3(g) -> NH3(aq)").K  # mol/(kg bar) on the 1 molal, 1 bar standard states
    assert k == pytest.approx(0.59 * 1e5 / 997.05, rel=0.05)
    assert chemdb.value("NH3", "Hf_aq").source == "nist_henry"


def test_nasa9_polynomials_reproduce_janaf_where_both_exist() -> None:
    """A check of the reader on species whose CEA and JANAF data are the same generation.

    CH4 is left out on purpose: CEA follows Gurvich (1991) and JANAF a 1961 review, and
    they part by 2.6 % in Cp at 1000 K (73.68 against 71.80 J/(mol K)), a real difference
    between evaluations rather than a reading error.
    """
    from ngdesign.data.species_models import _Nasa9Curve

    for query in ("CO2", "H2O", "N2", "O2"):
        pieces = chemdb.nasa9(query, "gas")
        assert pieces, query
        janaf = next(t for t in chemdb.janaf(query).values() if t[0]["phase_298"] == "gas")  # N2, O2: "ref"
        curve = _Nasa9Curve(pieces)
        for row in janaf:
            if row["T"] in (500.0, 1000.0, 1500.0):
                assert curve.cp(row["T"]) == pytest.approx(row["Cp"], rel=1e-2), (query, row["T"])
                assert curve.s(row["T"]) == pytest.approx(row["S"], abs=0.5), (query, row["T"])


def test_nasa9_is_internally_consistent() -> None:
    from ngdesign.data.species_models import _Nasa9Curve

    curve = _Nasa9Curve(chemdb.nasa9("Fe2O3", "solid"))
    T, h = 450.0, 0.5  # inside a piece: 600 K is a piece boundary
    assert (curve.dh(T + h) - curve.dh(T - h)) / (2 * h) == pytest.approx(curve.cp(T), rel=1e-6)
    assert (curve.s(T + h) - curve.s(T - h)) / (2 * h) == pytest.approx(curve.cp(T) / T, rel=1e-6)
    assert curve.dh(298.15) == pytest.approx(0.0, abs=1e-6)


def test_nasa9_header_enthalpy_is_the_polynomial_value_at_298() -> None:
    """The reading of thermo.inp the build relies on, checked on every record kept."""
    from ngdesign.data.species_models import _Nasa9Curve

    checked = 0
    with (_DIR / "nasa9.csv").open(encoding="utf8", newline="") as handle:
        by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in csv.DictReader(handle):
            by_key[(row["cas"], row["phase"])].append(row)
    for rows in by_key.values():
        pieces = [
            {k: (float(v) if k not in ("cas", "phase", "reference") else v) for k, v in r.items()}
            for r in rows
        ]
        curve = _Nasa9Curve(pieces)
        # fit residual of the polynomials at 298.15 K, measured over 406 records:
        # median 2.6, 99th percentile 15, maximum 25.7 J/mol
        assert curve._absolute_h(298.15) == pytest.approx(float(rows[0]["hf298"]), abs=30.0), rows[0]["cas"]
        checked += 1
    assert checked > 500


def test_cp0_eos_terms_reproduce_coolprop_and_integrate_consistently() -> None:
    """cp0_eos.csv against CoolProp's own ideal-gas Cp0, and the curve's dH, dS against Cp."""
    from ngdesign.data.species_models import _Cp0EosCurve

    with (_DIR / "cp0_eos.csv").open(encoding="utf8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {r["source"] for r in rows} == {"coolprop_ig"}
    assert "coolprop_ig" in chemdb.sources()
    fluids = {
        CP.get_fluid_param_string(f, "CAS"): f for f in CP.get_global_param_string("fluids_list").split(",")
    }
    checked = 0
    for cas in sorted({r["cas"] for r in rows}):
        terms = chemdb.cp0_eos(cas)
        assert "CoolProp key" in terms[0]["reference"], cas
        curve = _Cp0EosCurve(terms, 0.0)
        state = CP.AbstractState("HEOS", fluids[cas])
        T = 0.5 * (curve.tmin + curve.tmax)
        state.update(CP.DmolarT_INPUTS, 1e-6, T)
        assert curve.cp(T) == pytest.approx(state.cp0molar(), rel=1e-9), cas
        h = 1e-3 * T
        assert (curve.dh(T + h) - curve.dh(T - h)) / (2 * h) == pytest.approx(curve.cp(T), rel=1e-6), cas
        assert (curve.s(T + h) - curve.s(T - h)) / (2 * h) == pytest.approx(curve.cp(T) / T, rel=1e-6), cas
        checked += 1
    assert checked >= 100


@pytest.mark.parametrize(
    ("query", "T"),
    [("propane", 300.0), ("propane", 500.0), ("benzene", 400.0), ("isobutane", 300.0), ("CO2", 500.0)],
)
def test_cp0_eos_agrees_with_an_independent_gas_source(query: str, T: float) -> None:
    """Independent cross-check: a reference EOS's ideal-gas part against the species'
    own gas Cp source (JANAF, NASA or TRC), within the 2 % AUDIT limit. The four
    species past it are listed in AUDIT.txt."""
    from ngdesign.data.species_models import _Cp0EosCurve, species_thermo

    model = species_thermo(query, "gas")
    assert not model.curve.name.startswith("cp0_eos")
    eos = _Cp0EosCurve(chemdb.cp0_eos(query), 0.0)
    assert eos.cp(T) == pytest.approx(model.curve.cp(T), rel=0.02)


def test_cp0_eos_gives_a_gas_model_where_no_other_cp_source_exists() -> None:
    """Hexamethyldisiloxane: CRC states Hf, S and Cp(298) for the gas but no Cp(T); the
    reference-EOS ideal-gas part now carries the shape, and agrees with the CRC 298 K
    heat capacity (238.5 J/(mol K), an independent source) to 1 %."""
    from ngdesign.data.species_models import species_thermo

    model = species_thermo("107-46-0", "gas")
    assert model.curve.name == "cp0_eos:coolprop_ig"
    assert model.curve.cp(298.15) == pytest.approx(238.5, rel=0.01)
    assert model.curve.cp(500.0) > model.curve.cp(298.15)


def test_tabulated_gas_cp_reproduces_its_table_and_integrates_consistently() -> None:
    """Every gas model built on a stated Cp(T) table returns the table at its nodes,
    holds S°298 there, and its dH, dS are the integrals of its Cp."""
    from ngdesign.data.species_models import _cp_table, species_thermo

    cases = sorted({r["cas"] for r in chemdb._rows("cp_gas_points.csv")})  # noqa: SLF001
    checked = 0
    for cas in cases:
        try:
            model = species_thermo(cas, "gas")
        except chemdb.MissingPropertyError:
            continue
        if not model.curve.name.startswith("cp_table"):
            continue
        table = _cp_table(cas)
        assert table is not None
        for row in table:
            assert model.cp(float(row["T"])) == pytest.approx(float(row["Cp"]), rel=1e-12), cas
        assert model.s(298.15) == pytest.approx(chemdb.value(cas, "S0_gas").value, rel=1e-12), cas
        assert model.h(298.15) == pytest.approx(model.hf298, abs=1e-9), cas
        nodes = [float(row["T"]) for row in table]
        for T in (0.5 * (a + b) for a, b in zip(nodes, nodes[1:], strict=False)):  # Cp has kinks at nodes
            h = 1e-4 * T
            assert (model.h(T + h) - model.h(T - h)) / (2 * h) == pytest.approx(model.cp(T), rel=1e-6), cas
            assert (model.s(T + h) - model.s(T - h)) / (2 * h) == pytest.approx(model.cp(T) / T, rel=1e-6), (
                cas
            )
        checked += 1
    assert checked >= 3


def test_thermoml_points_are_stated_values_with_their_article() -> None:
    """ThermoML rows cite a DOI and are never the archive's predictions (the
    decamethylcyclopentasiloxane set, recorded as 'Predicted', stays out)."""
    with (_DIR / "cp_gas_points.csv").open(encoding="utf8", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if r["source"] == "thermoml"]
    assert len(rows) >= 100
    assert all("doi:10." in r["reference"] for r in rows)
    assert not any("predict" in r["reference"].lower() for r in rows)
    assert not any(r["cas"] == "541-02-6" for r in rows)


@pytest.mark.parametrize("T", [298.15, 400.0, 500.0, 700.0, 1000.0])
def test_thermoml_ideal_gas_cp_agrees_with_an_independent_source(T: float) -> None:
    """Benzene: the ThermoML statistical-thermodynamic table (Ruzicka et al. 2014)
    against the TRC eight-term fit, an independent evaluation, within 1 %."""
    from ngdesign.data.species_models import _TabulatedCpCurve, species_thermo

    table = next(
        rows for (source, _), rows in chemdb.cp_gas_points("benzene").items() if source == "thermoml"
    )
    model = species_thermo("benzene", "gas")
    assert model.curve.name == "cp_fit:trc"
    assert _TabulatedCpCurve(table, 0.0).cp(T) == pytest.approx(model.cp(T), rel=0.01)


@pytest.mark.parametrize(
    ("query", "shape", "cp298"),
    [
        ("141-43-5", "cp_table:thermoml", 84.38),  # 2-aminoethanol, Ruzicka et al. 2015
        ("872-50-4", "cp_table:thermoml", 115.26),  # N-methyl-2-pyrrolidone, Ruzicka et al. 2015
        ("132-64-9", "cp_table:nist", 163.05),  # dibenzofuran, Klots 1996 (WebBook)
        ("503-30-0", "cp_table:nist", 61.5),  # oxetane, Dorofeeva 1992 (WebBook)
        ("646-06-0", "cp_table:nist", 71.0),  # 1,3-dioxolane, Dorofeeva 1992 (WebBook)
    ],
)
def test_a_stated_cp_table_gives_a_gas_model_where_no_fit_exists(
    query: str, shape: str, cp298: float
) -> None:
    """These species state ΔfH° and S° for the gas but have no Cp fit; a stated table now
    carries the shape over its own range, and nothing beyond it."""
    from ngdesign.data.species_models import TemperatureRangeError, species_thermo

    model = species_thermo(query, "gas")
    assert model.curve.name == shape
    assert model.cp(298.15) == pytest.approx(cp298, rel=1e-12)
    assert model.cp(500.0) > model.cp(298.15)
    with pytest.raises(TemperatureRangeError):
        model.cp(model.t_range[1] + 1.0)


@pytest.mark.parametrize(
    ("query", "source", "cp298", "rel"),
    [
        ("503-30-0", "Hossenlopp", 61.2, 0.01),  # oxetane: Hossenlopp 1981 measurement (WebBook)
        ("79-14-1", "crc_thermo", 87.1, 0.03),  # glycolic acid: CRC Handbook 298 K value
    ],
)
def test_a_stated_cp_table_agrees_with_an_independent_298_k_value(
    query: str, source: str, cp298: float, rel: float
) -> None:
    """Cross-check of a table-based gas model against a separate source's 298 K Cp."""
    from ngdesign.data.species_models import species_thermo

    stated = [
        v for v in chemdb.values(query, "Cp_gas") if source in (v.source, v.reference.split(";")[0][:10])
    ]
    assert stated and stated[0].value == pytest.approx(cp298)
    assert species_thermo(query, "gas").cp(298.15) == pytest.approx(cp298, rel=rel)


@pytest.mark.parametrize(
    ("query", "reference", "crc_cp298", "crc_s298"),
    [
        ("10038-98-9", "Gurvich", 96.1, 347.7),  # GeCl4: CEA record "GeCL4"
        ("7646-78-8", "Gurvich", 98.3, 365.8),  # SnCl4: CEA record "SnCL4"
        ("7632-51-1", "Nagarajan", 96.2, 362.4),  # VCl4: CEA record "VCL4"
        ("79-08-3", "Dorofeeva", 80.5, 337.0),  # bromoacetic acid: CEA record "CH2Br-COOH"
    ],
)
def test_cea_records_matched_by_elemental_formula_agree_with_the_crc(
    query: str, reference: str, crc_cp298: float, crc_s298: float
) -> None:
    """CEA names write chlorine as ``CL``; these records are matched by their own elemental
    formula, corroborated by the WebBook page. The CRC Handbook's 298 K Cp° and S° are
    the independent check (Cp within 0.5 %, S° within 1.2 %)."""
    from ngdesign.data.species_models import TemperatureRangeError, species_thermo

    model = species_thermo(query, "gas")
    assert model.curve.name == "nasa9"
    assert reference in chemdb.nasa9(query)[0]["reference"]
    assert model.cp(298.15) == pytest.approx(crc_cp298, rel=0.005)
    assert model.s(298.15) == pytest.approx(crc_s298, rel=0.012)
    with pytest.raises(TemperatureRangeError):
        model.cp(model.t_range[1] + 1.0)


def test_cea_formula_fallback_refuses_an_identity_the_webbook_contradicts() -> None:
    """13596-11-7 is AlOCl (WebBook), but its PubChem formula here is AlClHO, the formula
    of CEA's HOAlCl record. Formula alone would attach HOAlCl to it; the WebBook check
    refuses, and isomer-mixture records (C2F2Cl2, C2HClF2) never stand for one species."""
    assert not chemdb.nasa9("13596-11-7")
    assert not chemdb.nasa9("79-35-6")
    assert not chemdb.nasa9("359-10-4")
