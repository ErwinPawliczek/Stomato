"""Extractor adapter tests: the one-distribution-coefficient-name rule (review 9).

``K_D`` and the absorber-style ``k_overrides`` name pick the same mapping;
accepting both names in one call leaves the effective basis ambiguous, so the
adapter refuses the combination (measured: the alias path returns the same
result as ``K_D`` — extract flow 98.5502 mol/s on the Example 5.2 basis).
"""

from __future__ import annotations

from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.column_shortcut.extractor import LiquidLiquidExtractor


def _example_states(thermo: Thermo) -> dict[str, Any]:
    feeds, _params = LiquidLiquidExtractor.example_case()
    return {
        port: thermo.flash_pt(spec["composition"], spec["T"], spec["P"], spec["molar_flow"])
        for port, spec in feeds.items()
    }


def test_extractor_refuses_kd_and_k_overrides_together(thermo: Thermo) -> None:
    """Both names in one call is ambiguous — refused with a naming message."""
    states = _example_states(thermo)
    kd = {"p-dioxane": 5.2027}
    with pytest.raises(ValueError, match="one distribution-coefficient param name"):
        LiquidLiquidExtractor().solve(states, {"N": 2.0, "K_D": kd, "k_overrides": kd}, thermo)


def test_extractor_k_overrides_alias_matches_kd(thermo: Thermo) -> None:
    """The alias name alone produces the K_D result identically."""
    states = _example_states(thermo)
    kd = {"p-dioxane": 5.2027}
    via_kd = LiquidLiquidExtractor().solve(states, {"N": 2.0, "K_D": dict(kd)}, thermo)
    via_alias = LiquidLiquidExtractor().solve(states, {"N": 2.0, "k_overrides": dict(kd)}, thermo)
    assert via_alias.outlets["extract"].molar_flow == pytest.approx(
        via_kd.outlets["extract"].molar_flow
    )
    assert via_alias.outlets["extract"].composition == pytest.approx(
        via_kd.outlets["extract"].composition
    )
