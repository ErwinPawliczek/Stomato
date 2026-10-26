"""Flash drum R1 tests (spec flash_drum.md): identity, refusals, carry-over split.

The pure helper functions (York K, Souders-Brown sizing, Morrison cut
diameter, Rosin-Rammler fines, carry-over) are tested in
``tests/units/separation/test_scrubber_r1.py`` — this module imports them, it
does not re-test them. Here: the adapter identity against R0, the refusal
table (the scrubber R1 table plus the flash drum's two-liquid row), the
closed-form velocity relation, and the mass-proportional carry-over split
across ``liquid_out`` and ``aqueous_out``.

Constant checks (spec U-R1 round-1 conventions): no new constants are typed —
every number the adapter touches comes from the scrubber R1 helpers, whose
constants are cross-checked in the scrubber test module.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from ngdesign.contracts import PhaseKind, StreamState, UnitResult
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.units.separation.flash_drum import FlashDrum, FlashDrumSpecError
from ngdesign.units.separation.flash_drum_r1 import FlashDrumR1, FlashDrumR1SpecError
from tests.conftest import flash_feed

#: The spec's test case (Tests, "Closed form"): the R0 example feeds with
#: duty_W 5e5, diameter_m 0.6, E 0.05, d_RR 3e-4 m, n_RR 2.5.
_BALANCE_PARAMS: dict[str, Any] = {
    "duty_W": 5.0e5,
    "diameter_m": 0.6,
    "inlet_entrained_fraction": 0.05,
    "droplet_d_rr_m": 3e-4,
    "droplet_n_rr": 2.5,
}


def _inlets(thermo: Thermo) -> dict[str, StreamState]:
    feeds, _params = FlashDrumR1.example_case()
    return {port: flash_feed(thermo, f) for port, f in feeds.items()}


def _r0(thermo: Thermo, inlets: dict[str, StreamState], params: dict[str, Any] | None = None) -> UnitResult:
    return FlashDrum().solve(inlets, params or {}, thermo)


class TestIdentity:
    """Reduction to the lower level: exact identity, no tolerance.

    Without diameter_m, and with diameter_m at inlet_entrained_fraction = 0,
    every outlet equals R0's exactly, duty_W equals R0's (the same objects
    summed in the same order), and info.T_out_K equals R0's (spec
    "Reduction to the lower level").
    """

    def test_no_diameter_reduces_to_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r1 = FlashDrumR1().solve(inlets, {}, thermo)
        r0 = _r0(thermo, inlets)
        assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
        assert r1.outlets["liquid_out"] == r0.outlets["liquid_out"]
        assert r1.outlets["aqueous_out"] == r0.outlets["aqueous_out"]
        assert r1.duty_W == r0.duty_W
        assert r1.power_W == 0.0
        assert r1.info["T_out_K"] == r0.info["T_out_K"]

    def test_duty_spec_reduces_to_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r1 = FlashDrumR1().solve(inlets, {"duty_W": 5.0e5}, thermo)
        r0 = _r0(thermo, inlets, {"duty_W": 5.0e5})
        assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
        assert r1.outlets["liquid_out"] == r0.outlets["liquid_out"]
        assert r1.outlets["aqueous_out"] == r0.outlets["aqueous_out"]
        assert r1.duty_W == r0.duty_W
        assert r1.info["T_out_K"] == r0.info["T_out_K"]

    def test_zero_entrainment_with_diameter_reduces_to_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        params = {**_BALANCE_PARAMS, "inlet_entrained_fraction": 0.0}
        r1 = FlashDrumR1().solve(inlets, params, thermo)
        r0 = _r0(thermo, inlets, {"duty_W": 5.0e5})
        assert r1.outlets["gas_out"] == r0.outlets["gas_out"]
        assert r1.outlets["liquid_out"] == r0.outlets["liquid_out"]
        assert r1.outlets["aqueous_out"] == r0.outlets["aqueous_out"]
        assert r1.duty_W == r0.duty_W
        # The carry-over chain runs and reports 0.
        assert r1.info["carryover_kg_s"] == 0.0
        assert r1.info["carryover_mol_fraction"] == 0.0


class TestClosedFormVelocity:
    """Closed-form check of the velocity relation (spec algorithm, step 5).

    Hand-computed: at diameter D the actual gas velocity is
    v_G = 4 Q_G / (pi D^2) and v_ratio = v_G / v_max, with Q_G and v_max
    taken from the same solve's info (rho_G is the flashed-vapour density, so
    Q_G = mdot_G / rho_G is itself the closed-form definition).
    """

    def test_velocity_relations_at_D_060(self, thermo: Thermo) -> None:
        r1 = FlashDrumR1().solve(_inlets(thermo), dict(_BALANCE_PARAMS), thermo)
        v_G = 4.0 * r1.info["Q_gas_m3_s"] / (math.pi * 0.6**2)
        assert r1.info["v_gas_m_s"] == pytest.approx(v_G, rel=1e-12)
        assert r1.info["v_ratio"] == pytest.approx(v_G / r1.info["v_max_m_s"], rel=1e-12)


class TestRefusals:
    """One test per refusal-table row (spec Refusals): the scrubber R1 table
    plus the flash-drum row, each a typed FlashDrumR1SpecError."""

    def _solve(self, thermo: Thermo, params: dict[str, Any], inlets: dict[str, StreamState] | None = None) -> UnitResult:
        return FlashDrumR1().solve(inlets or _inlets(thermo), params, thermo)

    def test_diameter_m_must_be_positive(self, thermo: Thermo) -> None:
        for bad in (0.0, -1.0):
            with pytest.raises(FlashDrumR1SpecError, match="diameter_m"):
                self._solve(thermo, {"diameter_m": bad})

    def test_K_m_s_must_be_positive(self, thermo: Thermo) -> None:
        with pytest.raises(FlashDrumR1SpecError, match="K_m_s"):
            self._solve(thermo, {"K_m_s": 0.0})

    def test_entrained_fraction_within_0_1(self, thermo: Thermo) -> None:
        for bad in (1.5, -0.1):
            with pytest.raises(FlashDrumR1SpecError, match="inlet_entrained_fraction"):
                self._solve(thermo, {"inlet_entrained_fraction": bad})

    def test_diameter_requires_entrainment_and_distribution(self, thermo: Thermo) -> None:
        with pytest.raises(FlashDrumR1SpecError, match="requires"):
            self._solve(thermo, {"diameter_m": 0.6})

    def test_droplet_params_must_be_positive(self, thermo: Thermo) -> None:
        with pytest.raises(FlashDrumR1SpecError, match="droplet_d_rr_m"):
            self._solve(thermo, {**_BALANCE_PARAMS, "droplet_d_rr_m": 0.0})
        with pytest.raises(FlashDrumR1SpecError, match="droplet_n_rr"):
            self._solve(thermo, {**_BALANCE_PARAMS, "droplet_n_rr": 0.0})

    def test_needs_both_a_gas_and_a_liquid(self, thermo: Thermo) -> None:
        # Pure water at 300 K, 1 bar stays liquid: R0's gas outlet is
        # zero-flow, so no sizing is possible.
        liquid_only = {
            "inlet": flash_feed(
                thermo, {"T": 300.0, "P": 1.0e5, "molar_flow": 10.0, "composition": {"H2O": 1.0}}
            )
        }
        with pytest.raises(FlashDrumR1SpecError, match="both a gas and a liquid"):
            self._solve(thermo, dict(_BALANCE_PARAMS), liquid_only)
        # Superheated methane at 320 K, 1 bar stays vapour: every liquid
        # outlet is zero-flow, the other half of the same refusal row.
        vapor_only = {
            "inlet": flash_feed(
                thermo, {"T": 320.0, "P": 1.0e5, "molar_flow": 10.0, "composition": {"C1": 1.0}}
            )
        }
        with pytest.raises(FlashDrumR1SpecError, match="both a gas and a liquid"):
            self._solve(thermo, dict(_BALANCE_PARAMS), vapor_only)

    def test_york_pressure_band_without_explicit_K(self, thermo: Thermo) -> None:
        # C1/H2O 50/50 at 6 kPa, 293 K: two-phase (water's Psat is 2.34 kPa,
        # so its liquid persists) and 6000 Pa = 0.870 psia is below the York
        # band's 1 psia floor, with no K_m_s given.
        inlets = {
            "inlet": flash_feed(
                thermo, {"T": 293.15, "P": 6.0e3, "molar_flow": 10.0, "composition": {"C1": 0.5, "H2O": 0.5}}
            )
        }
        with pytest.raises(FlashDrumR1SpecError, match="York"):
            self._solve(thermo, {}, inlets)

    def test_gas_viscosity_unavailable_needs_override(self, thermo: Thermo) -> None:
        stub = _NoViscosityThermo(thermo)
        with pytest.raises(FlashDrumR1SpecError, match="gas_viscosity_Pa_s"):
            self._solve(stub, dict(_BALANCE_PARAMS))

    def test_r0_refusal_propagates_unchanged(self, thermo: Thermo) -> None:
        # R0 refuses both duty_W and vapor_fraction; its own error type passes
        # through the R1 adapter untouched.
        with pytest.raises(FlashDrumSpecError, match="duty_W"):
            self._solve(thermo, {"duty_W": 1.0e5, "vapor_fraction": 0.5})


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


def _erase_viscosity(stream: StreamState) -> StreamState:
    """The flash result with every phase's viscosity set to None."""
    return stream.model_copy(
        update={"phases": [p.model_copy(update={"viscosity": None}) for p in stream.phases]}
    )
