"""A pure component below its critical point is a liquid above its vapour
pressure and a vapour below it - whatever wrapper class thermo's flash returns.

Found reviewing P1-09: ``pr`` flashed pure nC4 at 300 K / 2 MPa (Psat 2.58 bar)
as ``vapor`` with vapour fraction 1 and the liquid's enthalpy, because the
classifier trusted ``isinstance(phase, CEOSGas)`` and thermo hands back the gas
wrapper on the single liquid root. Mixtures with a trace of a second component
were classified correctly, which is how the absorber review caught it.
"""

from __future__ import annotations

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind


@pytest.mark.parametrize(
    ("cid", "T", "P", "kind"),
    [
        ("nC4", 300.0, 2.0e6, PhaseKind.HC_LIQUID),  # Psat 2.58 bar: subcooled liquid
        ("nC4", 300.0, 5.0e5, PhaseKind.HC_LIQUID),
        ("nC4", 300.0, 1.0e5, PhaseKind.VAPOR),  # below Psat: vapour
        ("C3", 300.0, 2.0e6, PhaseKind.HC_LIQUID),  # Psat 9.98 bar
        ("C1", 300.0, 2.0e6, PhaseKind.VAPOR),  # supercritical: gas by S-01
        ("H2O", 300.0, 1.0e5, PhaseKind.AQUEOUS),
    ],
)
def test_pure_component_phase_follows_the_vapour_pressure(
    thermo: Thermo, cid: str, T: float, P: float, kind: PhaseKind
) -> None:
    state = thermo.flash_pt({cid: 1.0}, T, P, 10.0)
    assert [p.kind for p in state.phases] == [kind]
    assert state.vapor_fraction == pytest.approx(1.0 if kind == PhaseKind.VAPOR else 0.0)


def test_pure_liquid_enthalpy_is_continuous_across_pressure(thermo: Thermo) -> None:
    """The mislabelled state carried the liquid enthalpy; the relabelled one must too."""
    h_20bar = thermo.flash_pt({"nC4": 1.0}, 300.0, 2.0e6, 10.0).enthalpy
    h_5bar = thermo.flash_pt({"nC4": 1.0}, 300.0, 5.0e5, 10.0).enthalpy
    assert h_20bar == pytest.approx(h_5bar, rel=5e-3)
