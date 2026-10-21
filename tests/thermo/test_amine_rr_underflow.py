"""Regression: a lean amine liquid with underflowed acid-gas K-values flashes (P1-06 blocker 1).

Measured state from the P1-06 BLOCKED report (issue #98): a reboiled MDEA
regenerator's inside-out walk evaluates the amine package at 412 K / 1.9 bar on
an essentially acid-gas-free liquid. The speciation model's p_eq is ~0 there, so
K_CO2 = 1.9e-17 and K_H2S = 1.3e-11 - positive, so the zero-K guard passes, but
below machine epsilon, so the Rachford-Rice denominator written as
1 + beta * (K - 1) cancelled to exactly 0.0 at beta = 1 and the bracketed root
solve raised ZeroDivisionError. The denominator is now (1 - beta) + beta * K.
"""

from __future__ import annotations

import pytest

from ngdesign import registry

_STATE = {"CO2": 7.0e-30, "H2O": 0.9165, "H2S": 2.6e-23, "MDEA": 0.0835}
# amine_enrtl is CO2-only service (it rejects any H2S rather than estimating it).
_STATE_CO2_ONLY = {"CO2": 7.0e-30, "H2O": 0.9165, "MDEA": 0.0835}


@pytest.mark.parametrize(
    ("model_id", "z", "t_k"),
    [
        ("amine_ke", _STATE, 411.99),
        # the eNRTL window tops out at 400 K; the same lean liquid underflows there too
        ("amine_enrtl", _STATE_CO2_ONLY, 395.0),
    ],
)
def test_lean_liquid_with_underflowed_acid_gas_k_flashes(
    model_id: str, z: dict[str, float], t_k: float
) -> None:
    pkg = registry.create("thermo", model_id)
    state = pkg.flash_pt(z, t_k, 1.9e5, molar_flow=1.0)
    assert 0.0 <= state.vapor_fraction <= 1.0
    assert state.T == pytest.approx(t_k)
