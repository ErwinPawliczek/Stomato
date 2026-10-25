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

from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import SaturationPoint
from ngdesign.units.separation.decanter import Decanter
from ngdesign.units.separation.decanter_r1 import (
    DecanterR1,
    DecanterR1SpecError,
    rz_exponent,
    settler_efficiency,
    stokes_velocity,
)
from tests.conftest import flash_feed

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


# --- Unit-level tests (step 2) -------------------------------------------


class _NoViscosityThermo:
    """``pr`` with every flashed phase's viscosity stripped: reaches the mu_c refusal."""

    def __init__(self, inner: Thermo) -> None:
        self._inner = inner

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        state = self._inner.flash_pt(z, T, P, molar_flow)
        return state.model_copy(
            update={"phases": [p.model_copy(update={"viscosity": None}) for p in state.phases]}
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        return self._inner.flash_ph(z, P, H, molar_flow)

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        return self._inner.flash_ps(z, P, S, molar_flow)

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        return self._inner.flash_tvf(z, T, vf, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        return self._inner.flash_pvf(z, P, vf, molar_flow)

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        return self._inner.bubble_point(z, T=T, P=P)

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        return self._inner.dew_point(z, T=T, P=P)

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        return self._inner.k_values(z, T, P)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> Any:
        return self._inner.phase_props(composition, T, P, kind)

    def derivatives(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> Any:
        return self._inner.derivatives(composition, T, P, kind)

    def pure_psat(self, cid: str, T: float) -> float | None:
        return self._inner.pure_psat(cid, T)


def _identity_params() -> dict[str, Any]:
    """R1 params at the reduction limit (eta = 1): the spec's identity case."""
    return {"dispersed_phase": "light", "droplet_diameter_m": 150e-6, "interface_area_m2": 1.0e4}


def _r0_inlets_and_outlets(thermo: Thermo) -> tuple[dict[str, StreamState], Any]:
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    return inlets, Decanter().solve(inlets, {}, thermo)


def test_identity_eta_one_returns_r0_exactly(thermo: Thermo) -> None:
    """u_h·A_i >= Q_c (A_i = 1e4 m2): every outlet equals R0's, same duty."""
    inlets, r0 = _r0_inlets_and_outlets(thermo)
    result = DecanterR1().solve(inlets, _identity_params(), thermo)
    assert result.outlets == r0.outlets
    assert result.duty_W == pytest.approx(r0.duty_W, rel=1e-10)
    assert result.power_W == 0.0
    assert result.info["separation_efficiency"] == 1.0


def test_entrainment_scales_dispersed_and_reflashes_continuous(thermo: Thermo) -> None:
    """0 < eta < 1: entrained light liquid shows up in the heavy outlet."""
    inlets, r0 = _r0_inlets_and_outlets(thermo)
    params = {**_identity_params(), "interface_area_m2": 0.25}
    result = DecanterR1().solve(inlets, params, thermo)
    eta = result.info["separation_efficiency"]
    assert 0.0 < eta < 1.0

    # The dispersed (light) outlet is the R0 outlet scaled, never re-flashed.
    assert result.outlets["light_out"].molar_flow == pytest.approx(
        eta * r0.outlets["light_out"].molar_flow, rel=1e-12
    )

    # The continuous (heavy) outlet carries the entrained light liquid.
    r0_nc5 = r0.outlets["heavy_out"].composition["nC5"] * r0.outlets["heavy_out"].molar_flow
    r1_nc5 = result.outlets["heavy_out"].composition["nC5"] * result.outlets["heavy_out"].molar_flow
    assert r1_nc5 > r0_nc5

    # Balances: moles at 1e-12, energy at 1e-8.
    n_in = inlets["inlet"].molar_flow
    n_out = sum(s.molar_flow for s in result.outlets.values())
    assert n_out == pytest.approx(n_in, rel=1e-12)
    h_in = inlets["inlet"].enthalpy * n_in
    h_out = sum(s.enthalpy * s.molar_flow for s in result.outlets.values())
    assert result.duty_W == pytest.approx(h_out - h_in, rel=1e-8)


def test_refusal_dispersed_phase() -> None:
    with pytest.raises(DecanterR1SpecError, match="dispersed_phase"):
        DecanterR1().solve(
            {},
            {"dispersed_phase": "middle", "droplet_diameter_m": 150e-6, "interface_area_m2": 1.0},
            thermo=None,  # type: ignore[arg-type]
        )


def test_refusal_geometry_forms(thermo: Thermo) -> None:
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    base = {"dispersed_phase": "light", "droplet_diameter_m": 150e-6}
    # Neither form.
    with pytest.raises(DecanterR1SpecError, match="interface_area_m2"):
        DecanterR1().solve(inlets, dict(base), thermo)
    # Both forms.
    both = {**base, "interface_area_m2": 1.0, "diameter_m": 0.8, "length_m": 2.5}
    with pytest.raises(DecanterR1SpecError, match="interface_area_m2"):
        DecanterR1().solve(inlets, both, thermo)


def test_refusal_nonpositive_geometry(thermo: Thermo) -> None:
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    with pytest.raises(DecanterR1SpecError, match="interface_area_m2"):
        DecanterR1().solve(
            inlets,
            {"dispersed_phase": "light", "droplet_diameter_m": 150e-6, "interface_area_m2": 0.0},
            thermo,
        )
    with pytest.raises(DecanterR1SpecError, match="diameter_m"):
        DecanterR1().solve(
            inlets,
            {"dispersed_phase": "light", "droplet_diameter_m": 150e-6, "diameter_m": -0.8, "length_m": 2.5},
            thermo,
        )
    with pytest.raises(DecanterR1SpecError, match="length_m"):
        DecanterR1().solve(
            inlets,
            {"dispersed_phase": "light", "droplet_diameter_m": 150e-6, "diameter_m": 0.8, "length_m": 0.0},
            thermo,
        )


def test_refusal_droplet_diameter(thermo: Thermo) -> None:
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    base = {"dispersed_phase": "light", "interface_area_m2": 1.0e4}
    with pytest.raises(DecanterR1SpecError, match="droplet_diameter_m"):
        DecanterR1().solve(inlets, dict(base), thermo)
    with pytest.raises(DecanterR1SpecError, match="droplet_diameter_m"):
        DecanterR1().solve(inlets, {**base, "droplet_diameter_m": 0.0}, thermo)


def test_refusal_viscosity_unavailable(thermo: Thermo) -> None:
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    stripped = _NoViscosityThermo(thermo)
    params = {"dispersed_phase": "light", "droplet_diameter_m": 150e-6, "interface_area_m2": 1.0e4}
    with pytest.raises(DecanterR1SpecError, match="continuous_viscosity_Pa_s"):
        DecanterR1().solve(inlets, params, stripped)


def test_refusal_stokes_out_of_range(thermo: Thermo) -> None:
    """A 2 mm droplet breaks Re_t < 1: refuse, never extrapolate."""
    feeds, _ = DecanterR1.example_case()
    inlets = {"inlet": flash_feed(thermo, feeds["inlet"])}
    params = {"dispersed_phase": "light", "droplet_diameter_m": 2.0e-3, "interface_area_m2": 1.0e4}
    with pytest.raises(DecanterR1SpecError, match="Stokes"):
        DecanterR1().solve(inlets, params, thermo)
