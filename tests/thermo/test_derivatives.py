"""Fugacity derivative contract: analytic dlnphi vs central finite differences (P1-01)."""

from __future__ import annotations

import math

import pytest

from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.stream import PhaseKind

Z = {"C1": 0.6, "C3": 0.2, "nC5": 0.2}
T = 300.0
P = 3.0e6
KINDS = [PhaseKind.VAPOR, PhaseKind.HC_LIQUID]


@pytest.mark.parametrize("kind", KINDS)
def test_dlnphi_dT_matches_finite_difference(thermo: Thermo, kind: PhaseKind) -> None:
    h = 1e-4 * T
    d = thermo.derivatives(dict(Z), T, P, kind)
    lo = thermo.phase_props(dict(Z), T - h, P, kind).ln_phi
    hi = thermo.phase_props(dict(Z), T + h, P, kind).ln_phi
    for cid, base in d.dlnphi_dT.items():
        if Z[cid] == 0.0:
            continue
        fd = (hi[cid] - lo[cid]) / (2.0 * h)
        assert math.isclose(base, fd, rel_tol=1e-5), (kind, cid)


@pytest.mark.parametrize("kind", KINDS)
def test_dlnphi_dP_matches_finite_difference(thermo: Thermo, kind: PhaseKind) -> None:
    h = 1e-4 * P
    d = thermo.derivatives(dict(Z), T, P, kind)
    lo = thermo.phase_props(dict(Z), T, P - h, kind).ln_phi
    hi = thermo.phase_props(dict(Z), T, P + h, kind).ln_phi
    for cid, base in d.dlnphi_dP.items():
        if Z[cid] == 0.0:
            continue
        fd = (hi[cid] - lo[cid]) / (2.0 * h)
        assert math.isclose(base, fd, rel_tol=1e-5), (kind, cid)


def test_derivative_keys_cover_the_feed(thermo: Thermo) -> None:
    d = thermo.derivatives(dict(Z), T, P, PhaseKind.VAPOR)
    assert set(d.dlnphi_dT) == set(Z)
    assert set(d.dlnphi_dP) == set(Z)
