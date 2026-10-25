"""Decanter R1 closed-form tests (spec specs/backend/units/decanter.md).

Hand-computed anchors (re-derived here from the spec's equations, not from
the implementation).

Tolerance note: the spec prints its anchors to 9 significant digits and asks
for rtol 1e-9, but a 9-digit rendering is itself coarser than 1e-9 relative
(Re_t = 0.1838746875 is printed truncated as 0.183874687, a 2.7e-9 shift;
u_h is printed rounded). The binding closed-form check is therefore the
implementation against the full-precision derivation of the spec's own
equation at rel 1e-9; the printed 9-digit anchors are pinned separately as a
transcription check at 1e-8 relative (one last-printed-digit granularity).
Nothing here loosens a comparison to match code output — the derivation is
independent arithmetic.

- CF1 Stokes (D1): u_t = 9.80665·(150e-6)²·|900 − 1000|/(18·1.0e-3)
      = 9.80665·2.25e-8·100/0.018 = 1.22583125e-3 m/s (exact in decimal);
      Re_t = 1000·1.22583125e-3·150e-6/1.0e-3 = 0.1838746875 (< 0.2, so D3
      gives n = 4.65 — and Stokes validity Re_t < 1 holds).
- CF2 Richardson-Zaki (D2–D4): Q_c = 1.5e-3, Q_d = 0.3e-3 gives
      φ = 0.3/1.8 = 1/6, n = 4.65 (Re_t < 0.2) and
      u_h = 1.22583125e-3·(1 − 1/6)^4.65 = 5.250950139608834e-4 m/s.
- CF3 Hazen (D5): η = min(1, u_h·A_i/Q_c):
      A_i = 0.5 → 0.17503167132029446;
      A_i = 2.0 → 0.7001266852811778.
- CF4 geometry: D5's A_i for a horizontal cylinder with the interface at the
  centre line is D·L = 0.8·2.5 = 2.0 m², exact.
- CF5 exponent branches (D3): Re = 0.1 → 4.65; Re = 0.5 → 4.4·0.5^−0.03
      = 4.492453353111651; Re = 600 → 2.4. Exact by branch construction.
"""

from __future__ import annotations

import pytest

from ngdesign.units.separation.decanter_r1 import (
    rz_exponent,
    settler_efficiency,
    stokes_velocity,
)

_D, _RHO_D, _RHO_C, _MU_C = 150e-6, 900.0, 1000.0, 1.0e-3
_Q_C, _Q_D = 1.5e-3, 0.3e-3


def _stokes() -> float:
    """D1 by hand: g·d²·|ρ_d − ρ_c|/(18·μ_c)."""
    return 9.80665 * _D**2 * abs(_RHO_D - _RHO_C) / (18.0 * _MU_C)


def _test_anchor(value: float, printed: str) -> None:
    """Transcription check: the derivation matches the spec's printed anchor."""
    assert value == pytest.approx(float(printed), rel=1e-8)


def test_cf1_stokes_velocity_and_reynolds() -> None:
    u_t = stokes_velocity(_D, _RHO_D, _RHO_C, _MU_C)
    re_t = _RHO_C * u_t * _D / _MU_C
    # Full-precision D1 derivation, at the spec's rtol.
    assert u_t == pytest.approx(_stokes(), rel=1e-9)
    assert re_t == pytest.approx(_RHO_C * _stokes() * _D / _MU_C, rel=1e-9)
    # The spec's printed anchors.
    _test_anchor(u_t, "1.22583125e-3")
    _test_anchor(re_t, "0.183874687")


def test_cf2_volume_fraction_exponent_and_hindered_velocity() -> None:
    phi = _Q_D / (_Q_C + _Q_D)
    assert phi == pytest.approx(1.0 / 6.0, rel=1e-9)
    n = rz_exponent(0.1838746875)
    assert n == pytest.approx(4.65, rel=1e-9)
    u_h = _stokes() * (1.0 - phi) ** n
    assert u_h == pytest.approx(5.250950139608834e-4, rel=1e-9)
    _test_anchor(phi, "0.166666667")
    _test_anchor(u_h, "5.25095014e-4")


def test_cf3_settler_efficiency() -> None:
    u_h = _stokes() * (1.0 - 1.0 / 6.0) ** 4.65
    eta_half = settler_efficiency(u_h, 0.5, _Q_C)
    eta_full = settler_efficiency(u_h, 2.0, _Q_C)
    assert eta_half == pytest.approx(0.17503167132029446, rel=1e-9)
    assert eta_full == pytest.approx(0.7001266852811778, rel=1e-9)
    _test_anchor(eta_half, "0.175031671")
    _test_anchor(eta_full, "0.700126685")


def test_cf4_geometry_interface_area() -> None:
    diameter, length = 0.8, 2.5
    assert diameter * length == pytest.approx(2.0, rel=0.0)


def test_cf5_exponent_branches() -> None:
    assert rz_exponent(0.1) == pytest.approx(4.65, rel=0.0)
    assert rz_exponent(0.5) == pytest.approx(4.4 * 0.5**-0.03, rel=1e-9)
    _test_anchor(rz_exponent(0.5), "4.49245335")
    assert rz_exponent(600.0) == pytest.approx(2.4, rel=0.0)
