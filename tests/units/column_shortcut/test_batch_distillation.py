"""Rayleigh batch distillation: closed form, balances, refusals.

The independent oracle is the Rayleigh equation in closed form for a binary at
constant relative volatility (Seader, Henley & Roper 3rd ed., eq. 13-5),

    ln(n0/n) = [ln(x0/x) + alpha ln((1 - x)/(1 - x0))] / (alpha - 1),

driven through a stub saturation surface with y = alpha x / (1 + (alpha - 1) x).
No package physics enters that test.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign import registry
from ngdesign.contracts import StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import Phase, PhaseKind
from ngdesign.contracts.thermo import PhaseProps, SaturationPoint
from ngdesign.units.column_shortcut.batch_distillation import BatchDistillation, BatchDistillationError
from tests.conftest import flash_feed

ALPHA = 2.5


class _ConstantAlpha:
    """Binary A/B at constant alpha: only what the unit calls, enthalpy-free."""

    def bubble_point(self, z: dict[str, float], *, P: float | None = None, T: float | None = None) -> Any:
        x = z["A"]
        y = ALPHA * x / (1.0 + (ALPHA - 1.0) * x)
        return SaturationPoint(
            T=350.0, P=P or 1e5, kind="bubble", incipient_composition={"A": y, "B": 1.0 - y}
        )

    def phase_props(self, comp: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition=comp,
            molecular_weight=1.0,
            density=1.0,
            enthalpy=0.0,
            entropy=0.0,
            cp=1.0,
            gibbs=0.0,
            z_factor=1.0,
        )

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        return _state(z, P, molar_flow)


def _state(z: dict[str, float], p: float, flow: float) -> StreamState:
    return StreamState(
        T=350.0,
        P=p,
        molar_flow=flow,
        composition=z,
        vapor_fraction=0.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[
            Phase(
                kind=PhaseKind.HC_LIQUID,
                mole_fraction=1.0,
                composition=z,
                molecular_weight=1.0,
                density=1.0,
                enthalpy=0.0,
                entropy=0.0,
                cp=1.0,
                z_factor=1.0,
            )
        ],
    )


@pytest.mark.parametrize("frac", [0.1, 0.5, 0.9])
def test_reproduces_closed_form_rayleigh(frac: float) -> None:
    x0 = 0.4
    charge = _state({"A": x0, "B": 1.0 - x0}, 1e5, 100.0)
    fake: Any = _ConstantAlpha()
    res = BatchDistillation().solve({"charge": charge}, {"fraction_distilled": frac}, fake)
    x = res.outlets["residue"].composition["A"]
    lhs = math.log(1.0 / (1.0 - frac))
    rhs = (math.log(x0 / x) + ALPHA * math.log((1.0 - x) / (1.0 - x0))) / (ALPHA - 1.0)
    assert rhs == pytest.approx(lhs, rel=1e-5)
    # Pooled distillate closes the light-key balance on its own.
    dist = res.outlets["distillate"]
    assert dist.molar_flow * dist.composition["A"] + 100.0 * (1.0 - frac) * x == pytest.approx(
        100.0 * x0, rel=1e-10
    )


def test_real_package_balance_and_direction(thermo: Thermo) -> None:
    feeds, params = BatchDistillation.example_case()
    charge = flash_feed(thermo, feeds["charge"])
    res = BatchDistillation().solve({"charge": charge}, params, thermo)
    dist, resid = res.outlets["distillate"], res.outlets["residue"]
    assert dist.molar_flow + resid.molar_flow == pytest.approx(charge.molar_flow, rel=1e-12)
    # The light key concentrates overhead, the heavy key in the pot, and the
    # pot climbs its boiling line.
    assert dist.composition["C3"] > charge.composition["C3"] > resid.composition["C3"]
    assert dist.composition["nC5"] < charge.composition["nC5"] < resid.composition["nC5"]
    assert res.info["pot_T_end_K"] > res.info["pot_T_start_K"]
    # Heat in at the pot, out at the condenser, both physical.
    assert res.info["pot_duty_W"] > 0.0
    assert res.info["condenser_duty_W"] > 0.0
    closure = (
        charge.enthalpy * charge.molar_flow
        + res.info["pot_duty_W"]
        - res.info["condenser_duty_W"]
        - dist.enthalpy * dist.molar_flow
        - resid.enthalpy * resid.molar_flow
    )
    assert closure == pytest.approx(0.0, abs=1e-6)


def test_first_drop_is_the_bubble_vapour(thermo: Thermo) -> None:
    """Limit fraction -> 0: the distillate is the charge's equilibrium vapour."""
    feeds, _ = BatchDistillation.example_case()
    charge = flash_feed(thermo, feeds["charge"])
    res = BatchDistillation().solve({"charge": charge}, {"fraction_distilled": 1e-4}, thermo)
    sat = thermo.bubble_point(dict(charge.composition), P=charge.P)
    for cid, y in sat.incipient_composition.items():
        assert res.outlets["distillate"].composition[cid] == pytest.approx(y, rel=1e-3)


@pytest.mark.parametrize(
    "params",
    [{"fraction_distilled": 0.0}, {"fraction_distilled": 1.0}, {}, {"fraction_distilled": 0.5, "x": 1}],
)
def test_refusals(thermo: Thermo, params: dict[str, Any]) -> None:
    feeds, _ = BatchDistillation.example_case()
    charge = flash_feed(thermo, feeds["charge"])
    with pytest.raises(BatchDistillationError):
        BatchDistillation().solve({"charge": charge}, params, thermo)


def test_unit_is_registered_at_r3() -> None:
    unit = registry.create("unit", "batch_distillation")
    assert unit.outlet_ports == ("distillate", "residue")
