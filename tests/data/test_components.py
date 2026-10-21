"""Open component resolution (spec P1-02): curated slate, databank, pseudo-components.

The Lee-Kesler / Riazi-Daubert reference values for the C7+ pseudo below were
hand-computed from the published correlation forms for Tb = 372.0 K, sg = 0.73:
Tc = 549.69 K and Pc = 3.0605e6 Pa (Kesler & Lee 1976, Hydrocarbon Processing
55(3), 153), omega = 0.3221 (Lee-Kesler 1975 acentric-factor correlation as
implemented in chemicals.acentric.LK_omega), MW = 101.07 (Riazi & Daubert 1980,
Hydrocarbon Processing 59(3)). The correlations themselves are also spot-checked
against databank pure components (n-heptane, n-pentane) in the implementation.
"""

from __future__ import annotations

import pytest

from ngdesign.data import PseudoDefinition, component_record, register_pseudo

_C7P_TB = 372.0
_C7P_SG = 0.73


@pytest.fixture
def c7plus() -> None:
    register_pseudo("C7+", "C7+ pseudo", Tb=_C7P_TB, sg=_C7P_SG)


def test_curated_id_resolves_with_databank_properties() -> None:
    record = component_record("C1")
    assert record["cas"] == "74-82-8"
    assert record["kind"] == "curated"
    assert record["mw"] == pytest.approx(16.04, abs=0.05)
    assert record["Tc"] == pytest.approx(190.56, abs=0.1)
    assert record["provenance"]["name"] == "curated"
    assert record["provenance"]["Tc"].startswith("chemicals")


def test_databank_by_name() -> None:
    record = component_record("n-heptane")
    assert record["kind"] == "databank"
    assert record["formula"] == "C7H16"
    assert record["mw"] == pytest.approx(100.2, abs=0.1)
    assert record["cas"].replace("-", "") == "142825"


def test_databank_by_cas() -> None:
    record = component_record("142-82-5")
    assert record["kind"] == "databank"
    assert record["mw"] == pytest.approx(100.2, abs=0.1)


def test_pseudo_resolves_with_lee_kesler_and_provenance(c7plus: None) -> None:
    record = component_record("C7+")
    assert record["kind"] == "pseudo"
    assert record["cas"] is None
    assert record["Tc"] == pytest.approx(549.69, rel=0.03)
    assert record["Pc"] == pytest.approx(3.0605e6, rel=0.03)
    assert record["omega"] == pytest.approx(0.3221, rel=0.03)
    assert record["mw"] == pytest.approx(101.07, rel=0.03)
    assert record["Tb"] == _C7P_TB
    assert record["sg"] == _C7P_SG
    for prop in ("Tc", "Pc", "omega", "mw"):
        assert record["provenance"][prop], f"{prop} provenance empty"
    assert "Kesler & Lee 1976" in record["provenance"]["Tc"]
    assert "Riazi & Daubert 1980" in record["provenance"]["mw"]
    assert record["provenance"]["Tb"] == "user"


def test_pseudo_re_registration_is_idempotent(c7plus: None) -> None:
    register_pseudo("C7+", "C7+ pseudo", Tb=_C7P_TB, sg=_C7P_SG)  # same definition: no-op


def test_pseudo_conflicting_definition_raises(c7plus: None) -> None:
    with pytest.raises(ValueError, match="different definition"):
        register_pseudo("C7+", "C7+ pseudo", Tb=400.0, sg=_C7P_SG)


def test_pseudo_cannot_shadow_curated_ids() -> None:
    with pytest.raises(ValueError, match="reserved"):
        register_pseudo("C1", "methane pseudo", Tb=111.7, sg=0.3)


def test_unknown_component_raises_naming_the_key() -> None:
    with pytest.raises(ValueError, match="unobtanium"):
        component_record("unobtanium")


# ------------------------------------------------------------------ spec P1-07


def test_explicit_pseudos_mapping_resolves_without_registration() -> None:
    definition = PseudoDefinition(id="C9+", name="C9+ pseudo", Tb=450.0, sg=0.82)
    record = component_record("C9+", pseudos={"C9+": definition})
    assert record["kind"] == "pseudo"
    assert record["Tb"] == 450.0
    assert record["sg"] == 0.82
    assert record["provenance"]["Tb"] == "user"


def test_explicit_pseudos_mapping_is_the_only_pseudo_source() -> None:
    # A flowsheet context never falls back to the module-level register_pseudo
    # default: two flowsheets in one process stay independent (spec P1-07).
    with pytest.raises(ValueError, match="unobtanium9"):
        component_record("unobtanium9", pseudos={})


def test_override_replaces_the_correlated_value() -> None:
    definition = PseudoDefinition(
        id="C9+", name="C9+ pseudo", Tb=450.0, sg=0.82, mw=120.0, provenance=(("mw", "lab distillation"),)
    )
    record = component_record("C9+", pseudos={"C9+": definition})
    assert record["mw"] == 120.0
    assert record["provenance"]["mw"] == "lab distillation"
    assert "Kesler" in record["provenance"]["Tc"]  # un-overridden props stay correlated
