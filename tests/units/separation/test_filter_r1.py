"""Filter R1 closed-form tests (spec ``specs/backend/units/filter.md``).

The expected numbers are the spec's CF1-CF4 set, hand-computed here from the
spec's equations (SI):

- c = mdot_s/Q_f = 0.10/2.0e-3 = 50 kg/m3 (F6).
- V_cycle = Q_f*(t_f + t_d) = 2.0e-3*(600 + 300) = 1.8 m3 (F3).
- a = mu*alpha*c/(2*dP) = 8.937e-4*1e11*50/(2*1e5) = 22342.5 s/m2 (F1).
- b = mu*R_m/dP = 8.937e-4*1e10/1e5 = 89.37 s/m (F1).
- v = (-b + sqrt(b^2 + 4*a*t_f))/(2a)
    = (-89.37 + sqrt(89.37^2 + 4*22342.5*600))/(2*22342.5)
    = (-89.37 + sqrt(53629986.9969))/44685
    = 7233.879.../44685 = 0.161886086 m  (F2).
- A_req = 1.8/0.161886086 = 11.118929634834254 m2 (F3). The spec prints
  11.1189296, its 9-significant-digit rounding.
- capacity_ratio at A = 10 m2: 10/11.118929634834254 = 0.8993671448977621 (F7).
- L_cake = 50*1.8/(11.118929634834254*2650*0.6) = 5.090757423949597e-3 m (F4).
- q_ret = 0.4/0.6*0.10/2650 = 2.515723270440252e-5 m3/s (F5), a fraction
  2.515723270440252e-5/2.0e-3 = 0.01257861635220126 of the 2.0e-3 m3/s
  filtrate. The spec prints 0.0125786164, its 9-digit rounding.

rtol 1e-9 per the spec; the expected constants are the exact evaluation of
the spec's printed inputs, so the comparison is not absorbed by print
rounding (the spec's 9-digit prints sit ~3e-9 relative away from them).
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from ngdesign.contracts import PhaseKind
from ngdesign.contracts.plugins import Thermo
from ngdesign.units.separation.filter import Filter, FilterSpecError
from ngdesign.units.separation.filter_r1 import (
    FilterR1,
    FilterR1SpecError,
    cake_thickness,
    capacity_ratio,
    concentration,
    retained_liquid_rate,
    ruth_area,
    ruth_constants,
    ruth_time,
    ruth_volume_per_area,
)
from tests.conftest import flash_feed

_MU = 8.937e-4  # Pa s
_ALPHA = 1e11  # m/kg
_RM = 1e10  # 1/m
_DP = 1e5  # Pa
_MDOT_S = 0.10  # kg/s dry solids
_QF = 2.0e-3  # m3/s filtrate
_TF = 600.0  # s
_TD = 300.0  # s


class TestCF1RuthArea:
    """CF1: a, b, v and the required area from one set of printed inputs."""

    def test_coefficients(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert a == pytest.approx(22342.5, rel=1e-9)
        assert b == pytest.approx(89.37, rel=1e-9)

    def test_volume_per_area(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        v = ruth_volume_per_area(_TF, a, b)
        assert v == pytest.approx(0.161886086, rel=1e-9)

    def test_root_is_the_positive_one(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert ruth_volume_per_area(_TF, a, b) > 0.0

    def test_ruth_time_inverts_volume_per_area(self) -> None:
        a, b = ruth_constants(_MU, _ALPHA, 50.0, _DP, _RM)
        assert ruth_time(0.161886086, a, b) == pytest.approx(_TF, rel=1e-9)

    def test_required_area(self) -> None:
        area = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert area == pytest.approx(11.118929634834254, rel=1e-9)


class TestCF2Capacity:
    """CF2: an installed area of 10 m2 against the required 11.1189296 m2."""

    def test_capacity_ratio(self) -> None:
        area_required = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert capacity_ratio(10.0, area_required) == pytest.approx(0.899367145, rel=1e-9)


class TestCF3CakeThickness:
    """CF3: cake thickness at the required area, rho_s = 2650, eps = 0.4."""

    def test_thickness(self) -> None:
        area_required = ruth_area(_MU, _ALPHA, 50.0, _DP, _RM, _TF, 1.8)
        assert cake_thickness(50.0, 1.8, area_required, 2650.0, 0.4) == pytest.approx(5.09075742e-3, rel=1e-9)


class TestCF4Moisture:
    """CF4: liquid held in the cake voids, eps = 0.4, rho_s = 2650."""

    def test_retained_rate_and_fraction(self) -> None:
        q_ret = retained_liquid_rate(_MDOT_S, 2650.0, 0.4)
        assert q_ret == pytest.approx(2.515723270440252e-5, rel=1e-9)
        assert q_ret / _QF == pytest.approx(0.01257861635220126, rel=1e-9)


class TestF6Concentration:
    """F6 sanity: c = mdot_s/Q_f."""

    def test_concentration(self) -> None:
        assert concentration(_MDOT_S, _QF) == pytest.approx(50.0, rel=1e-12)
        assert math.isclose(concentration(0.3, 1.5), 0.2)


# --- adapter (step 2) --------------------------------------------------------


class _NoViscosityThermo:
    """A Thermo that delegates, stripping phase viscosities (refusal test)."""

    def __init__(self, inner: Thermo) -> None:
        self._inner = inner

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> Any:
        return _strip(self._inner.flash_pt(z, T, P, molar_flow))

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> Any:
        return _strip(self._inner.flash_ph(z, P, H, molar_flow))

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> Any:
        return _strip(self._inner.flash_ps(z, P, S, molar_flow))

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> Any:
        return _strip(self._inner.flash_tvf(z, T, vf, molar_flow))

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> Any:
        return _strip(self._inner.flash_pvf(z, P, vf, molar_flow))


def _strip(state: Any) -> Any:
    return state.model_copy(
        update={"phases": [p.model_copy(update={"viscosity": None}) for p in state.phases]}
    )


def _inlets(
    thermo: Thermo,
    feed_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    feeds, _ = FilterR1.example_case()
    if feed_overrides:
        feeds["inlet"].update(feed_overrides)
    return {"inlet": flash_feed(thermo, feeds["inlet"])}


def _default_params(**overrides: Any) -> dict[str, Any]:
    _, defaults = FilterR1.example_case()
    return {**defaults, **overrides}


class TestIdentity:
    """cake_porosity = 0 gives exactly the R0 split with the user's fractions."""

    def test_outlets_equal_r0(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        params = _default_params(cake_porosity=0.0)
        params.pop("filtrate_viscosity_Pa_s")  # not needed with no moisture
        r0 = Filter().solve(inlets, {"cake_fractions": {"SiO2": 1.0}, "dP": 3.0e4}, thermo)
        r1 = FilterR1().solve(inlets, params, thermo)
        assert r1.outlets["filtrate"] == r0.outlets["filtrate"]
        assert r1.outlets["cake"] == r0.outlets["cake"]
        assert r1.duty_W == r0.duty_W
        # Sizing is still reported.
        assert r1.info["A_required_m2"] > 0.0
        assert r1.info["moisture_fraction"] == 0.0


class TestMoisture:
    """eps = 0.4: filtrate-composition liquid moves to the cake at f_m."""

    def test_cake_flows_f_m_and_balances(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        r0 = Filter().solve(inlets, {"cake_fractions": {"SiO2": 1.0}, "dP": 3.0e4}, thermo)
        r1 = FilterR1().solve(inlets, _default_params(), thermo)

        # f_m recomputed from the R0 outlets' properties (F5 and step 3 of
        # the spec's algorithm), independently of the adapter.
        cake0, filt0 = r0.outlets["cake"], r0.outlets["filtrate"]
        mdot_s = cake0.mass_flow
        q_ret = 0.4 / 0.6 * mdot_s / 2650.0
        liquid = max(
            (p for p in filt0.phases if p.kind is not PhaseKind.VAPOR),
            key=lambda p: p.mole_fraction * p.molecular_weight / p.density,
        )
        mw = sum(p.mole_fraction * p.molecular_weight for p in filt0.phases) / 1000.0
        f_m = q_ret * liquid.density / mw / filt0.molar_flow

        assert r1.info["moisture_fraction"] == pytest.approx(f_m, rel=1e-12)
        cake1, filt1 = r1.outlets["cake"], r1.outlets["filtrate"]
        h2o_f0 = filt0.component_flows()["H2O"]
        assert cake1.component_flows()["H2O"] == pytest.approx(f_m * h2o_f0, rel=1e-12)
        # The solids are untouched by the moisture move.
        assert cake1.component_flows()["SiO2"] == pytest.approx(cake0.component_flows()["SiO2"], rel=1e-12)

        # Balances: moles at 1e-12, energy at 1e-8.
        n_in = inlets["inlet"].molar_flow
        n_out = filt1.molar_flow + cake1.molar_flow
        assert n_out == pytest.approx(n_in, rel=1e-12)
        h_in = inlets["inlet"].enthalpy * inlets["inlet"].molar_flow
        h_out = filt1.enthalpy * filt1.molar_flow + cake1.enthalpy * cake1.molar_flow
        assert h_in + r1.duty_W == pytest.approx(h_out, rel=1e-8)

    def test_capacity_ratio_reported_not_refused(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        result = FilterR1().solve(inlets, _default_params(area_m2=1.0e-3), thermo)
        assert 0.0 < result.info["capacity_ratio"] < 1.0  # undersized, still solved


class TestRefusals:
    """One test per row of the spec's refusal table."""

    def test_dp_missing_or_zero(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        params = _default_params()
        del params["dP"]
        with pytest.raises(FilterR1SpecError, match="dP"):
            FilterR1().solve(inlets, params, thermo)
        with pytest.raises(FilterR1SpecError, match="dP"):
            FilterR1().solve(inlets, _default_params(dP=0.0), thermo)

    def test_alpha_not_positive(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        zero = _default_params(specific_cake_resistance_m_kg=0.0)
        with pytest.raises(FilterR1SpecError, match="specific_cake_resistance_m_kg"):
            FilterR1().solve(inlets, zero, thermo)
        params = _default_params()
        del params["specific_cake_resistance_m_kg"]
        with pytest.raises(FilterR1SpecError, match="specific_cake_resistance_m_kg"):
            FilterR1().solve(inlets, params, thermo)

    def test_medium_resistance_negative(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterR1SpecError, match="medium_resistance_1_m"):
            FilterR1().solve(inlets, _default_params(medium_resistance_1_m=-1.0), thermo)

    def test_filtration_time_not_positive(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterR1SpecError, match="t_filtration_s"):
            FilterR1().solve(inlets, _default_params(t_filtration_s=0.0), thermo)

    def test_downtime_negative(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterR1SpecError, match="t_down_s"):
            FilterR1().solve(inlets, _default_params(t_down_s=-1.0), thermo)

    def test_solid_density_missing_or_not_positive(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        params = _default_params()
        del params["solid_density_kg_m3"]
        with pytest.raises(FilterR1SpecError, match="solid_density_kg_m3"):
            FilterR1().solve(inlets, params, thermo)
        with pytest.raises(FilterR1SpecError, match="solid_density_kg_m3"):
            FilterR1().solve(inlets, _default_params(solid_density_kg_m3=0.0), thermo)

    def test_porosity_outside_range(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterR1SpecError, match="cake_porosity"):
            FilterR1().solve(inlets, _default_params(cake_porosity=1.0), thermo)
        with pytest.raises(FilterR1SpecError, match="cake_porosity"):
            FilterR1().solve(inlets, _default_params(cake_porosity=-0.1), thermo)

    def test_area_not_positive(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterR1SpecError, match="area_m2"):
            FilterR1().solve(inlets, _default_params(area_m2=0.0), thermo)

    def test_moisture_over_capacity(self, thermo: Thermo) -> None:
        """eps = 0.99 with a 50 mol % solids slurry: f_m > 1."""
        inlets = _inlets(thermo, {"composition": {"H2O": 0.5, "SiO2": 0.5}})
        with pytest.raises(FilterR1SpecError, match="moisture"):
            FilterR1().solve(inlets, _default_params(cake_porosity=0.99), thermo)

    def test_no_cake_component_flows(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo, {"composition": {"H2O": 1.0, "SiO2": 0.0}})
        with pytest.raises(FilterR1SpecError, match="cake_fractions"):
            FilterR1().solve(inlets, _default_params(cake_porosity=0.0), thermo)

    def test_viscosity_unavailable(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        params = _default_params()
        del params["filtrate_viscosity_Pa_s"]
        with pytest.raises(FilterR1SpecError, match="filtrate_viscosity_Pa_s"):
            FilterR1().solve(inlets, params, cast(Thermo, _NoViscosityThermo(thermo)))

    def test_r0_spec_error_propagates(self, thermo: Thermo) -> None:
        inlets = _inlets(thermo)
        with pytest.raises(FilterSpecError, match="not in the feed"):
            FilterR1().solve(inlets, _default_params(cake_fractions={"Nope": 1.0}), thermo)
