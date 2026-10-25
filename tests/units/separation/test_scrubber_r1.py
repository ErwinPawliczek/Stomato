"""Scrubber R1 tests (spec scrubber.md): closed-form CF1-CF5, identity, balance, refusals.

Every closed-form number is hand-computed from the spec's equations (S1-S6) and
reproduced by scratchpad/unit-specs/calc_scrubber.py, which is independent of
fluids and ngdesign. The spec table prints the script's values at 10
significant digits; the rtol 1e-9 comparisons below run against the script's
full-precision output (the spec's declared source of the closed-form numbers),
since a 10-digit print itself carries up to ~3e-9 of relative rounding.

Constant checks (spec U-R1 round-1 conventions):
- York K constants (0.1821, 0.0029, 0.0460, 0.35, 0.430, 0.023, 0.3048 m/ft,
  6894.757293168 Pa/psia): CF1 cross-checks them against the fluids package's
  independent implementation of the same Svrcek-Monnery 1993 fit.
- g = 9.80665 m/s2: CF3's cut diameter is found with it through Morrison drag
  from fluids; the resulting Re = 234.541079 is an independent residual check.
- Rosin-Rammler: CF4/CF5 chain d_cut from CF3 through F(d) and E*mdot_L*F, so
  the carry-over number closes the whole chain.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.units.separation.scrubber_r1 import (
    ScrubberR1,
    ScrubberR1SpecError,
    carryover_mass_flow,
    cut_diameter_m,
    rosin_rammler_fines,
    size_gas_section,
    york_K_m_s,
)
from ngdesign.units.separator import Scrubber
from tests.conftest import flash_feed


class TestCF1YorkK:
    """CF1 York K, relative tolerance 1e-9.

    Hand-computed at the three spec points (P in psia, K in ft/s, x 0.3048):
    - 3.447e6 Pa = 500.0 psia: 40 < P <= 5500, K = 0.430 - 0.023 ln(500)
      = 0.430 - 0.023*6.2146081 = 0.287064 ft/s -> 0.0874978814 m/s.
    - 2.0e5 Pa = 29.0075 psia: on the 15-40 psia plateau, K = 0.35 ft/s
      -> 0.10668 m/s.
    - 5.0e4 Pa = 7.25185 psia: 1 <= P < 15, K = 0.1821 + 0.0029*7.25185
      + 0.0460*ln(7.25185) = 0.2942695 ft/s -> 0.0896930418 m/s.
    """

    @pytest.mark.parametrize(
        ("P_Pa", "expected"),
        [
            (3.447e6, 0.0874978814),
            (2.0e5, 0.10668),
            (5.0e4, 0.0896930418),
        ],
    )
    def test_york_K(self, P_Pa: float, expected: float) -> None:
        assert york_K_m_s(P_Pa) == pytest.approx(expected, rel=1e-9)

    def test_refuses_outside_1_5500_psia(self) -> None:
        """fluids clamps silently; the wrapper must refuse first (spec S2)."""
        below = 0.9 * 6894.757293168
        above = 5501.0 * 6894.757293168
        with pytest.raises(ScrubberR1SpecError, match="York"):
            york_K_m_s(below)
        with pytest.raises(ScrubberR1SpecError, match="York"):
            york_K_m_s(above)


class TestCF2SoudersBrown:
    """CF2 sizing through the unit's pure function, rtol 1e-9.

    Hand-computed with K = 0.107 m/s, rho_L = 600, rho_G = 30, Q_G = 1 m3/s:
    v_max = 0.107*sqrt(570/30) = 0.107*sqrt(19) = 0.466402187 m/s;
    D_min = sqrt(4*1/(pi*0.466402187)) = sqrt(2.7299650...) = 1.652246232 m.
    """

    def test_sizing(self) -> None:
        size = size_gas_section(0.107, 600.0, 30.0, 1.0)
        assert size["v_max_m_s"] == pytest.approx(0.466402187, rel=1e-9)
        assert size["min_diameter_m"] == pytest.approx(1.6522462324369869, rel=1e-9)


class TestCF3CutDiameter:
    """CF3 cut diameter through the public helper, rtol 1e-8.

    Hand-computed for D = 2.0 m, Q = 1.0 m3/s, mu_G = 1.2e-5 Pa s, with the
    CF2 v_max = 0.466402187 m/s:
    v_G = 4*1/(pi*2^2) = 1/pi = 0.318309886 m/s;
    v_ratio = 0.318309886/0.466402187 = 0.682479403;
    d_cut solves g(d) = 4 g d (600-30)/(3 C_D(Re) 30 v_G^2) - 1 = 0 with
    Re = 30*0.318309886*d/1.2e-5 and Morrison C_D: d_cut = 2.94733012e-4 m,
    where Re = 30*0.318309886*2.94733012e-4/1.2e-5 = 234.541079.
    (The root is located by bisection per the spec; the Re value above is the
    independent hand check that the reported cut sits on the residual zero.)
    """

    D_M = 2.0
    Q_M3_S = 1.0
    V_MAX = 0.466402187

    def test_cut(self) -> None:
        v_G = 4.0 * self.Q_M3_S / (math.pi * self.D_M**2)
        assert v_G == pytest.approx(0.318309886, rel=1e-8)
        assert v_G / self.V_MAX == pytest.approx(0.682479403, rel=1e-8)
        cut = cut_diameter_m(v_G, 600.0, 30.0, 1.2e-5)
        assert cut["d_cut_m"] == pytest.approx(2.94733012e-4, rel=1e-8)
        assert cut["Re"] == pytest.approx(234.541079, rel=1e-8)

    def test_all_carried_gives_infinite_cut(self) -> None:
        """g(1e-1) < 0: even a 10 cm drop is carried, so d_cut = inf (spec step 7).

        Near-critical liquid (rho_L = 30.1 vs rho_G = 30 kg/m3) at a gas
        velocity well above any droplet's terminal velocity: the settling
        driving force 4 g d (rho_L - rho_G) is smaller than the gas drag
        3 C_D rho_G v_G^2 at d = 0.1 m, so nothing settles.
        """
        cut = cut_diameter_m(0.15, 30.1, 30.0, 1.2e-5)
        assert math.isinf(cut["d_cut_m"])


class TestCF4RosinRammler:
    """CF4 fines fraction, rtol 1e-9.

    Hand-computed at the CF3 cut diameter, d_RR = 400e-6 m, n_RR = 2.5:
    (d_cut/d_RR) = 0.73683..., ^2.5 = 0.46622..., so
    F = 1 - exp(-0.46622...) = 0.372516998. The cut is taken from
    cut_diameter_m (full precision) rather than the rounded CF3 print.
    """

    def test_fines(self) -> None:
        cut = cut_diameter_m(0.3183098861837907, 600.0, 30.0, 1.2e-5)
        assert rosin_rammler_fines(cut["d_cut_m"], 400e-6, 2.5) == pytest.approx(0.372516998, rel=1e-9)


class TestCF5Carryover:
    """CF5 carry-over through the pure function, rtol 1e-8.

    Hand-computed with mdot_L = 10 kg/s, E = 0.02 and the CF4 fines fraction:
    mdot_co = 0.02*10*0.372516998 = 0.0745033996 kg/s.
    """

    def test_carryover(self) -> None:
        cut = cut_diameter_m(0.3183098861837907, 600.0, 30.0, 1.2e-5)
        F = rosin_rammler_fines(cut["d_cut_m"], 400e-6, 2.5)
        assert carryover_mass_flow(10.0, 0.02, F) == pytest.approx(0.0745033996, rel=1e-8)


# --- adapter (spec steps 2, 8, 9) ------------------------------------------


def _inlets(thermo: Thermo) -> dict[str, StreamState]:
    feeds, _params = ScrubberR1.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _r0(thermo: Thermo, inlets: dict[str, StreamState]) -> UnitResult:
    return Scrubber().solve(inlets, {"dP": 0.0}, thermo)


#: The unit-level balance case: R0 example feed, D = 0.5 m, E = 0.05,
#: d_RR = 300 um, n_RR = 2.5 (spec Tests, "Unit-level balance").
_BALANCE_PARAMS: dict[str, Any] = {
    "diameter_m": 0.5,
    "inlet_entrained_fraction": 0.05,
    "droplet_d_rr_m": 300e-6,
    "droplet_n_rr": 2.5,
}


class TestIdentity:
    """Reduction to the lower level: exact identity, no tolerance.

    Without diameter_m, and with diameter_m at inlet_entrained_fraction = 0,
    every outlet equals R0's exactly (the same objects inside one solve) and
    duty_W equals R0's (spec "Reduction to the lower level").
    """

    def test_no_diameter_reduces_to_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r1 = ScrubberR1().solve(inlets, {}, thermo)
        r0 = _r0(thermo, inlets)
        assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
        assert r1.outlets["liquid_out"] == r0.outlets["liquid_out"]
        assert r1.duty_W == r0.duty_W
        assert r1.power_W == r0.power_W

    def test_zero_entrainment_with_diameter_reduces_to_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r1 = ScrubberR1().solve(inlets, {**_BALANCE_PARAMS, "inlet_entrained_fraction": 0.0}, thermo)
        r0 = _r0(thermo, inlets)
        assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
        assert r1.outlets["liquid_out"] == r0.outlets["liquid_out"]
        assert r1.duty_W == r0.duty_W
        # Sizing info is always reported; the carry-over chain runs and reports 0.
        assert r1.info["carryover_kg_s"] == 0.0
        assert r1.info["carryover_mol_fraction"] == 0.0


class TestBalance:
    """Unit-level balance on the R0 example feed with D = 0.5 m, E = 0.05,
    d_RR = 300 um, n_RR = 2.5 (spec Tests, "Unit-level balance")."""

    def test_moles_and_energy_close_and_gas_gains(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r1 = ScrubberR1().solve(inlets, dict(_BALANCE_PARAMS), thermo)
        r0 = _r0(thermo, inlets)
        n_in = inlets["inlet"].molar_flow
        n_out = sum(s.molar_flow for s in r1.outlets.values())
        assert abs(n_out - n_in) / n_in < 1e-12
        h_in = abs(inlets["inlet"].enthalpy * n_in)
        assert abs(r1.duty_W) <= 1e-8 * h_in
        # The gas outlet absorbs the carried droplets; the liquid outlet shrinks.
        assert r1.outlets["gas_out"].molar_flow > r0.outlets["gas_out"].molar_flow
        assert r1.outlets["liquid_out"].molar_flow < r0.outlets["liquid_out"].molar_flow


def _erase_viscosity(stream: StreamState) -> StreamState:
    """The flash result with every phase's viscosity set to None."""
    return stream.model_copy(
        update={"phases": [p.model_copy(update={"viscosity": None}) for p in stream.phases]}
    )


class _NoViscosityThermo(Thermo):
    """The real package with flash results' phase viscosities erased.

    Exercises the solve-level 'gas viscosity unavailable' refusal; no current
    package returns None, so the stub is the only way to reach that branch.
    """

    def __init__(self, inner: Thermo) -> None:
        self._inner = inner

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        return _erase_viscosity(self._inner.flash_pt(z, T, P, molar_flow))

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

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        return self._inner.phase_props(composition, T, P, kind)

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        return self._inner.derivatives(composition, T, P, kind)

    def pure_psat(self, cid: str, T: float) -> float | None:
        return self._inner.pure_psat(cid, T)


class TestRefusals:
    """One test per refusal-table row (spec Refusals), each a typed
    ScrubberR1SpecError naming the parameter."""

    def _solve(
        self, thermo: Thermo, params: dict[str, Any], inlets: dict[str, StreamState] | None = None
    ) -> UnitResult:
        return ScrubberR1().solve(inlets or _inlets(thermo), params, thermo)

    def test_diameter_m_must_be_positive(self, thermo: Thermo) -> None:
        for bad in (0.0, -1.0):
            with pytest.raises(ScrubberR1SpecError, match="diameter_m"):
                self._solve(thermo, {"diameter_m": bad})

    def test_K_m_s_must_be_positive(self, thermo: Thermo) -> None:
        with pytest.raises(ScrubberR1SpecError, match="K_m_s"):
            self._solve(thermo, {"K_m_s": 0.0})

    def test_entrained_fraction_within_0_1(self, thermo: Thermo) -> None:
        for bad in (1.5, -0.1):
            with pytest.raises(ScrubberR1SpecError, match="inlet_entrained_fraction"):
                self._solve(thermo, {"inlet_entrained_fraction": bad})

    def test_diameter_requires_entrainment_and_distribution(self, thermo: Thermo) -> None:
        with pytest.raises(ScrubberR1SpecError, match="requires"):
            self._solve(thermo, {"diameter_m": 0.5})

    def test_droplet_params_must_be_positive(self, thermo: Thermo) -> None:
        with pytest.raises(ScrubberR1SpecError, match="droplet_d_rr_m"):
            self._solve(thermo, {**_BALANCE_PARAMS, "droplet_d_rr_m": 0.0})
        with pytest.raises(ScrubberR1SpecError, match="droplet_n_rr"):
            self._solve(thermo, {**_BALANCE_PARAMS, "droplet_n_rr": 0.0})

    def test_sizing_needs_both_phases(self, thermo: Thermo) -> None:
        # Pure water at 300 K, 1 bar flashes to a single liquid phase: R0's
        # gas outlet is zero-flow, so no sizing is possible.
        inlets = {
            "inlet": flash_feed(
                thermo, {"T": 300.0, "P": 1.0e5, "molar_flow": 10.0, "composition": {"H2O": 1.0}}
            )
        }
        with pytest.raises(ScrubberR1SpecError, match="both a gas and a liquid"):
            self._solve(thermo, {}, inlets)

    def test_york_pressure_band_without_explicit_K(self, thermo: Thermo) -> None:
        # C1/H2O 50/50 at 6 kPa, 293 K: two-phase (water's Psat is 2.34 kPa,
        # so its aqueous phase persists) and 6000 Pa = 0.870 psia is below the
        # York band's 1 psia floor, with no K_m_s given.
        inlets = {
            "inlet": flash_feed(
                thermo, {"T": 293.15, "P": 6.0e3, "molar_flow": 10.0, "composition": {"C1": 0.5, "H2O": 0.5}}
            )
        }
        with pytest.raises(ScrubberR1SpecError, match="York"):
            self._solve(thermo, {}, inlets)

    def test_gas_viscosity_unavailable_needs_override(self, thermo: Thermo) -> None:
        stub = _NoViscosityThermo(thermo)
        with pytest.raises(ScrubberR1SpecError, match="gas_viscosity_Pa_s"):
            self._solve(stub, dict(_BALANCE_PARAMS))
