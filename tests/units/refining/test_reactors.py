"""Spec U-H2 acceptance tests: refining reactor R0 adapters.

Each adapter is a mass-only yield-table reactor on a ``mass_elements`` row:
mass closes exactly, elements close on the formula-bearing species, and the
duty is the sensible-only package enthalpy change (flagged in info).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from tests.conftest import flash_feed

E12_2_FEEDS = {
    "naphtha_in": {
        "T": 700.0,
        "P": 3000000.0,
        "molar_flow": 0.14073154,
        "composition": {
            "thiophene": 0.05320367,
            "1-pentene": 0.38297573,
            "benzene": 0.17192783,
            "octane": 0.39189277,
        },
    },
    "h2_in": {
        "T": 320.0,
        "P": 3000000.0,
        "molar_flow": 0.12574708,
        "composition": {"H2": 1.0},
    },
}


def _solve(
    thermo: Thermo, unit_id: str, feeds: dict[str, Any] | None, params: dict[str, Any]
) -> tuple[dict[str, StreamState], UnitResult]:
    unit = registry.create("unit", unit_id)
    if feeds is None:
        feeds, _defaults = unit.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    _feeds, defaults = unit.example_case()
    return inlets, unit.solve(inlets, {"model": "R0", **defaults, **params}, thermo)


def _mass_flows(inlets: dict[str, StreamState], result: UnitResult) -> tuple[float, float]:
    from ngdesign.data import component_record

    def _side(states: Any) -> float:
        return float(
            sum(
                s.molar_flow * y * float(component_record(cid)["mw"])
                for s in states
                for cid, y in s.composition.items()
            )
        )

    return _side(inlets.values()), _side(result.outlets.values())


class TestDelayedCoker:
    def test_example_case_yields_match_the_ccr_correlations(self, thermo: Thermo) -> None:
        """Gary–Handwerk ch. 5 equations at the Jechura feed point (13.5 wt% CCR)."""
        _, result = _solve(thermo, "coker", None, {"ccr_wt_pct": 13.5})
        assert result.info["coke_wt_pct"] == pytest.approx(1.6 * 13.5, abs=1e-9)
        assert result.info["gas_wt_pct"] == pytest.approx(7.8 + 0.144 * 13.5, abs=1e-9)
        assert result.info["naphtha_wt_pct"] == pytest.approx(11.29 + 0.343 * 13.5, abs=1e-9)
        gasoil = 100.0 - 1.6 * 13.5 - (7.8 + 0.144 * 13.5) - (11.29 + 0.343 * 13.5)
        assert result.info["gasoil_wt_pct"] == pytest.approx(gasoil, abs=1e-9)
        assert result.info["lgo_wt_pct"] == pytest.approx(0.5 * gasoil, abs=1e-9)
        assert result.info["hgo_wt_pct"] == pytest.approx(0.5 * gasoil, abs=1e-9)

    def test_gh_case_study_printed_slate(self, thermo: Thermo) -> None:
        """Gary–Handwerk 5th ed. §5.9 worked example, printed slate at CCR 14.2 wt%.

        The book prints Coke 22.72, Gas (C4-) 9.84, Naphtha 16.16 and Gas oil
        51.3 wt% (pp. 116-118, Table 5.16 material balance on 302,450 lb/h
        feed); the LCGO/HCGO split is its printed 96,967/155,081 lb/h ratio.
        Same point the V1_coker_gh_case_study case anchors.
        """
        _, result = _solve(
            thermo,
            "coker",
            None,
            {"ccr_wt_pct": 14.2, "gasoil_lgo_fraction": 96967.0 / 155081.0},
        )
        assert result.info["coke_wt_pct"] == pytest.approx(22.72, rel=1e-3)
        assert result.info["gas_wt_pct"] == pytest.approx(9.84, rel=1e-3)
        assert result.info["naphtha_wt_pct"] == pytest.approx(16.16, rel=1e-3)
        assert result.info["gasoil_wt_pct"] == pytest.approx(51.3, rel=1e-3)
        assert result.info["lgo_wt_pct"] == pytest.approx(32.061, rel=1e-3)
        assert result.info["hgo_wt_pct"] == pytest.approx(19.214, rel=1e-3)

    def test_gas_oil_split_is_a_configuration_not_a_correlation(self, thermo: Thermo) -> None:
        _, result = _solve(thermo, "coker", None, {"ccr_wt_pct": 13.5, "gasoil_lgo_fraction": 0.25})
        gasoil = result.info["gasoil_wt_pct"]
        assert result.info["lgo_wt_pct"] == pytest.approx(0.25 * gasoil, abs=1e-9)
        assert result.info["hgo_wt_pct"] == pytest.approx(0.75 * gasoil, abs=1e-9)

    def test_mass_closes_exactly(self, thermo: Thermo) -> None:
        inlets, result = _solve(thermo, "coker", None, {"ccr_wt_pct": 13.5})
        mass_in, mass_out = _mass_flows(inlets, result)
        assert mass_out == pytest.approx(mass_in, rel=1e-12)

    def test_duty_is_flagged_sensible_only(self, thermo: Thermo) -> None:
        _, result = _solve(thermo, "coker", None, {"ccr_wt_pct": 13.5})
        assert result.info["heat_of_reaction_basis_sensible_only"] == pytest.approx(1.0)

    @pytest.mark.parametrize("ccr", [0.0, -1.0, 40.0])
    def test_refuses_bad_ccr(self, thermo: Thermo, ccr: float) -> None:
        with pytest.raises(ValueError, match="ccr_wt_pct"):
            _solve(thermo, "coker", None, {"ccr_wt_pct": ccr})

    @pytest.mark.parametrize("split", [0.0, 1.0, 1.5])
    def test_refuses_degenerate_gas_oil_split(self, thermo: Thermo, split: float) -> None:
        with pytest.raises(ValueError, match="gasoil_lgo_fraction"):
            _solve(thermo, "coker", None, {"ccr_wt_pct": 13.5, "gasoil_lgo_fraction": split})


class TestCatalyticReformer:
    def test_example_case_matches_the_printed_e5_2_slate(self, thermo: Thermo) -> None:
        """Fahim Table 5.3 equations at Example E5.2 (RON 94, N 21.7, A 11.5)."""
        _, result = _solve(
            thermo,
            "reformer_cat",
            None,
            {"ron_reformate": 94.0, "naphthenes_vol_pct": 21.7, "aromatics_vol_pct": 11.5},
        )
        n2a = 21.7 + 2.0 * 11.5
        c5p = 142.7914 - 0.77033 * 94.0 + 0.219122 * n2a
        assert result.info["c5p_vol_pct"] == pytest.approx(c5p, rel=1e-9)
        # The book's printed slate (3-4 significant figures).
        assert result.info["c5p_vol_pct"] == pytest.approx(80.17, rel=1e-3)
        assert result.info["h2_wt_pct"] == pytest.approx(2.1051, rel=1e-3)
        assert result.info["c1_wt_pct"] == pytest.approx(1.4871, rel=1e-3)
        assert result.info["c2_wt_pct"] == pytest.approx(2.4012, rel=1e-3)
        assert result.info["c3_wt_pct"] == pytest.approx(3.6441, rel=1e-3)
        assert result.info["c4_total_wt_pct"] == pytest.approx(4.2784, rel=1e-3)

    def test_c4_split_follows_equations_5_13_and_5_14(self, thermo: Thermo) -> None:
        _, result = _solve(
            thermo,
            "reformer_cat",
            None,
            {"ron_reformate": 94.0, "naphthenes_vol_pct": 21.7, "aromatics_vol_pct": 11.5},
        )
        assert result.info["nc4_wt_pct"] == pytest.approx(0.585 * result.info["c4_total_wt_pct"])
        assert result.info["ic4_wt_pct"] == pytest.approx(0.415 * result.info["c4_total_wt_pct"])

    def test_offgas_lump_conserves_feed_mass(self, thermo: Thermo) -> None:
        inlets, result = _solve(
            thermo,
            "reformer_cat",
            None,
            {"ron_reformate": 94.0, "naphthenes_vol_pct": 21.7, "aromatics_vol_pct": 11.5},
        )
        mass_in, mass_out = _mass_flows(inlets, result)
        assert mass_out == pytest.approx(mass_in, rel=1e-12)
        # The species split is reported in info; the streams are two lumps.
        offgas = result.info["offgas_wt_pct"]
        assert result.info["reformate_wt_pct"] == pytest.approx(100.0 - offgas, rel=1e-9)

    def test_refuses_zero_ron(self, thermo: Thermo) -> None:
        with pytest.raises(ValueError, match="ron_reformate"):
            _solve(thermo, "reformer_cat", None, {"ron_reformate": 0.0})

    def test_refuses_severity_past_the_yield_envelope(self, thermo: Thermo) -> None:
        # C5+ crosses zero near RON 199 at this feed N+2A.
        with pytest.raises(ValueError, match="C5\\+"):
            _solve(thermo, "reformer_cat", None, {"ron_reformate": 200.0})


class TestNaphthaHydrotreater:
    def test_e12_2_product_slate(self, thermo: Thermo) -> None:
        """Fahim Example E12.2: 100 lb/h naphtha, 70% olefin / 80% aromatic conversion."""
        _, result = _solve(
            thermo,
            "naphtha_ht",
            E12_2_FEEDS,
            {"pentene_conversion": 0.7, "benzene_conversion": 0.8},
        )
        # Book slate (mol/s from lbmol/h), 3-4 significant figures.
        assert result.info["h2s_mol_s"] == pytest.approx(0.00749687, rel=0.01)
        assert result.info["nbutane_mol_s"] == pytest.approx(0.00749687, rel=0.01)
        assert result.info["npentane_mol_s"] == pytest.approx(0.03779936, rel=0.01)
        assert result.info["cyclohexane_mol_s"] == pytest.approx(0.01938477, rel=0.01)
        assert result.info["h2_consumed_mol_s"] == pytest.approx(0.12495415, rel=0.01)

    def test_full_removal_by_default(self, thermo: Thermo) -> None:
        feeds = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3000000.0,
                "molar_flow": 1.0,
                "composition": {"thiophene": 0.5, "octane": 0.5},
            },
            "h2_in": {
                "T": 320.0,
                "P": 3000000.0,
                "molar_flow": 10.0,
                "composition": {"H2": 1.0},
            },
        }
        _, result = _solve(thermo, "naphtha_ht", feeds, {})
        assert result.info["h2s_mol_s"] == pytest.approx(0.5, rel=1e-9)

    def test_partial_conversions_are_respected(self, thermo: Thermo) -> None:
        feeds = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3000000.0,
                "molar_flow": 1.0,
                "composition": {"1-pentene": 0.4, "octane": 0.6},
            },
            "h2_in": {
                "T": 320.0,
                "P": 3000000.0,
                "molar_flow": 10.0,
                "composition": {"H2": 1.0},
            },
        }
        _, result = _solve(thermo, "naphtha_ht", feeds, {"pentene_conversion": 0.5})
        assert result.info["npentane_mol_s"] == pytest.approx(0.2, rel=1e-9)

    def test_makeup_h2_follows_the_maples_correlation(self, thermo: Thermo) -> None:
        feeds = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3000000.0,
                "molar_flow": 1.0,
                "composition": {"thiophene": 0.5, "octane": 0.5},
            },
            "h2_in": {
                "T": 320.0,
                "P": 3000000.0,
                "molar_flow": 10.0,
                "composition": {"H2": 1.0},
            },
        }
        _, result = _solve(thermo, "naphtha_ht", feeds, {})
        sulfur_w = result.info["feed_sulfur_wt_pct"]
        assert result.info["h2_makeup_maples_scf_bbl"] == pytest.approx(191.0 * sulfur_w - 30.7, rel=1e-9)

    def test_mass_closes_exactly(self, thermo: Thermo) -> None:
        inlets, result = _solve(
            thermo,
            "naphtha_ht",
            E12_2_FEEDS,
            {"pentene_conversion": 0.7, "benzene_conversion": 0.8},
        )
        mass_in, mass_out = _mass_flows(inlets, result)
        assert mass_out == pytest.approx(mass_in, rel=1e-12)

    def test_refuses_a_dead_reaction_set(self, thermo: Thermo) -> None:
        """No hydrogen excess and no reactions means gas_out would be empty."""
        feeds = {
            "naphtha_in": {
                "T": 600.0,
                "P": 3000000.0,
                "molar_flow": 1.0,
                "composition": {"octane": 1.0},
            },
            "h2_in": {
                "T": 320.0,
                "P": 3000000.0,
                "molar_flow": 0.0,
                "composition": {"H2": 1.0},
            },
        }
        with pytest.raises(ValueError, match="nothing to solve"):
            _solve(thermo, "naphtha_ht", feeds, {})


def test_planned_r1_levels_refuse_and_name_implemented_ones(thermo: Thermo) -> None:
    from ngdesign.units.levels import UnitLevelNotImplemented

    for unit_id in ("naphtha_ht", "reformer_cat"):
        unit = registry.create("unit", unit_id)
        with pytest.raises(UnitLevelNotImplemented, match="R0"):
            unit.solve({}, {"model": "R1"}, thermo)
