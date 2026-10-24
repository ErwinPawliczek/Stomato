"""Closed-form tests for the shared isentropic step (spec U-B).

Pin: ideal-gas N2 (diatomic, k = 1.4), where PR sits within ~0.1 % of the
ideal-gas relations, compared against

    T2s = T1 * (P2/P1)^((k-1)/k)          and     T2 = T1 + (T2s - T1)/eta.

PR's Cp/(Cp - R) at 300 K / 1 bar is 1.3985 (checked against the registered
package), so the reference values below carry a 0.5 % band for the residual
real-gas deviation — the spec's "within the ideal-gas deviation".
"""

from __future__ import annotations

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind
from ngdesign.units._physics.efficiency import isentropic_step
from tests.conftest import flash_feed

K_IDEAL = 1.4
N2_FEED = {
    "T": 300.0,
    "P": 1.0e5,
    "molar_flow": 10.0,
    "composition": {"N2": 1.0},
}

#: T2s for 1 -> 3 bar at k = 1.4: 300 * 3^(0.4/1.4).
T2S_1_TO_3 = 300.0 * 3.0 ** ((K_IDEAL - 1.0) / K_IDEAL)


def test_isentropic_compress_matches_ideal_gas_t2s(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, N2_FEED)
    outlet, power = isentropic_step(inlet, 3.0e5, 1.0, thermo, "compress")
    assert outlet.T == pytest.approx(T2S_1_TO_3, rel=0.005)
    assert outlet.P == 3.0e5
    assert power > 0.0


def test_eta_compression_temperature_and_power(thermo: Thermo) -> None:
    """T2 = T1 + (T2s - T1)/eta for an ideal gas with constant cp."""
    inlet = flash_feed(thermo, N2_FEED)
    eta = 0.8
    outlet, power = isentropic_step(inlet, 3.0e5, eta, thermo, "compress")
    assert outlet.T == pytest.approx(300.0 + (T2S_1_TO_3 - 300.0) / eta, rel=0.005)
    # Power = F * cp * dT with cp from the registered package.
    cp = thermo.phase_props({"N2": 1.0}, 300.0, 1.0e5, PhaseKind.VAPOR).cp
    assert power == pytest.approx(10.0 * cp * (outlet.T - 300.0), rel=0.02)


def test_eta_expansion_mirrors_compression(thermo: Thermo) -> None:
    """Expansion from 3 bar recovers eta of the isentropic drop."""
    inlet = flash_feed(thermo, {"T": 300.0, "P": 3.0e5, "molar_flow": 10.0, "composition": {"N2": 1.0}})
    outlet, power = isentropic_step(inlet, 1.0e5, 0.8, thermo, "expand")
    t_isentropic = 300.0 * (1.0 / 3.0) ** ((K_IDEAL - 1.0) / K_IDEAL)
    assert outlet.T == pytest.approx(300.0 - 0.8 * (300.0 - t_isentropic), rel=0.005)
    assert power < 0.0  # shaft power leaves the process


def test_refuses_wrong_direction_and_bad_eta(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, N2_FEED)
    with pytest.raises(ValueError, match="exceed"):
        isentropic_step(inlet, 0.5e5, 1.0, thermo, "compress")
    with pytest.raises(ValueError, match="below"):
        isentropic_step(inlet, 3.0e5, 1.0, thermo, "expand")
    with pytest.raises(ValueError, match="eta"):
        isentropic_step(inlet, 3.0e5, 0.0, thermo, "compress")
    with pytest.raises(ValueError, match="mode"):
        isentropic_step(inlet, 3.0e5, 1.0, thermo, "pump")  # type: ignore[arg-type]
