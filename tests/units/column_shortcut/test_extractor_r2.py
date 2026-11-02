"""Liquid-liquid extractor R2: one stage is a flash; isofugacity; stage balances; Kremser."""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units.column_shortcut.extractor_r2 import ExtractorR2, ExtractorR2Error
from tests.conftest import flash_feed

COMPS = ["H2O", "MeOH", "nC6"]


def _inlets(thermo: Thermo) -> dict[str, Any]:
    feeds, _ = ExtractorR2.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def test_one_stage_is_the_flash_of_the_mixed_feeds(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    res = ExtractorR2().solve(inlets, {"n_stages": 1}, thermo)
    z = {"nC6": 80.0 / 140.0, "MeOH": 20.0 / 140.0, "H2O": 40.0 / 140.0}
    flash = thermo.flash_pt(z, 300.0, 1.0e6, 140.0)
    water_rich = max(flash.phases, key=lambda p: p.composition["H2O"])
    assert res.outlets["extract"].molar_flow == pytest.approx(140.0 * water_rich.mole_fraction, rel=1e-6)
    for c in COMPS:
        assert res.outlets["extract"].composition[c] == pytest.approx(
            water_rich.composition.get(c, 0.0), rel=1e-5, abs=1e-9
        )


def test_every_stage_closes_and_is_isofugacious(thermo: Thermo) -> None:
    inlets = _inlets(thermo)
    res = ExtractorR2().solve(inlets, {"n_stages": 4}, thermo)
    info = res.info
    for j in range(4):
        r, e = info[f"stage_{j}_R_mol_s"], info[f"stage_{j}_E_mol_s"]
        x = {c: info[f"stage_{j}_xR_{c}"] for c in COMPS}
        y = {c: info[f"stage_{j}_xE_{c}"] for c in COMPS}
        for c in COMPS:
            n_in = 0.0
            if j:
                n_in += info[f"stage_{j - 1}_R_mol_s"] * info[f"stage_{j - 1}_xR_{c}"]
            else:
                n_in += inlets["feed"].molar_flow * inlets["feed"].composition.get(c, 0.0)
            if j < 3:
                n_in += info[f"stage_{j + 1}_E_mol_s"] * info[f"stage_{j + 1}_xE_{c}"]
            else:
                n_in += inlets["solvent_in"].molar_flow * inlets["solvent_in"].composition.get(c, 0.0)
            assert n_in == pytest.approx(r * x[c] + e * y[c], abs=1e-6), (j, c)
        xr = {c: v for c, v in x.items() if v > 1e-12}
        xe = {c: v for c, v in y.items() if v > 1e-12}
        ln_r = thermo.phase_props(xr, 300.0, 1.0e6, PhaseKind.HC_LIQUID).ln_phi
        ln_e = thermo.phase_props(xe, 300.0, 1.0e6, PhaseKind.AQUEOUS).ln_phi
        for c in set(xr) & set(xe):
            assert math.log(xr[c]) + ln_r[c] == pytest.approx(math.log(xe[c]) + ln_e[c], abs=1e-4), (j, c)


def test_stages_extract_more_and_end_at_the_kremser_limit(thermo: Thermo) -> None:
    """Dilute solute on near-constant K: the extracted fraction is the Kremser one."""
    feeds, _ = ExtractorR2.example_case()
    feeds["feed"]["composition"] = {"nC6": 0.999, "MeOH": 0.001}
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    done = []
    for n in (1, 2, 4):
        res = ExtractorR2().solve(inlets, {"n_stages": n}, thermo)
        kept = res.outlets["raffinate"].molar_flow * res.outlets["raffinate"].composition["MeOH"] / 0.1
        done.append(1.0 - kept)
        if n == 4:
            info = res.info
            # Effective factor: the geometric mean over the stages, whose K and
            # flows move with the mutual solubility.
            factors = [
                info[f"stage_{j}_K_MeOH"] * info[f"stage_{j}_E_mol_s"] / info[f"stage_{j}_R_mol_s"]
                for j in range(4)
            ]
            factor = math.prod(factors) ** 0.25
            kremser = (factor**5 - factor) / (factor**5 - 1.0)
            assert done[-1] == pytest.approx(kremser, rel=0.03)
    assert done == sorted(done)


def test_no_second_liquid_refused(thermo: Thermo) -> None:
    feeds = {
        "feed": {"T": 300.0, "P": 1.0e6, "molar_flow": 100.0, "composition": {"nC6": 0.5, "nC7": 0.5}},
        "solvent_in": {"T": 300.0, "P": 1.0e6, "molar_flow": 40.0, "composition": {"nC8": 1.0}},
    }
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    with pytest.raises(ExtractorR2Error, match="needs exactly two"):
        ExtractorR2().solve(inlets, {"n_stages": 2}, thermo)


def test_bad_params_refused(thermo: Thermo) -> None:
    for params in ({}, {"n_stages": 0}, {"n_stages": 2, "x": 1}):
        with pytest.raises(ExtractorR2Error):
            ExtractorR2().solve(_inlets(thermo), params, thermo)


def test_registered_at_r2(thermo: Thermo) -> None:
    unit = registry.create("unit", "liquid_liquid_extractor")
    res = unit.solve(_inlets(thermo), {"model": "R2", "n_stages": 2}, thermo)
    assert res.info["n_stages"] == 2.0
