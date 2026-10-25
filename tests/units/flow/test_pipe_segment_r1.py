"""Closed-form tests for the pipe_segment R1 marcher (spec C1 and C2).

Independent check constants: the friction factors are recomputed here with an
own fixed-point Colebrook solve (not the repo's ``darcy_colebrook``), and the
expected pressure drops are the spec's hand-derived values, transcribed from
specs/backend/units/pipe_segment.md.

C1 -- incompressible liquid, constant props, through ``march``:
    D = 0.1023 m, L = 100 m, eps = 4.57e-5 m, mdot = 10 kg/s, dz = +10 m.
    v = 1.21906906257652 m/s, Re = 124461.343571375, f = 0.0195416887606116
    (the independent Colebrook fixed point below reproduces f).
    dP_friction = 14165.8821277191 Pa, hydrostatic = 97870.3670000000 Pa,
    so march gives dP = 112036.249127719 Pa. The fittings helper
    (Crane TP-410 K method, sum K = 2.5) gives 1853.94640071566 Pa,
    adapter-level total 113890.195528435 Pa.
    Heun is exact for a constant derivative: tolerance 1e-10.

C2 -- isothermal ideal gas, horizontal, rho(P) = P*M/(R*T):
    M = 0.016043 kg/mol, T = 300 K, P1 = 5.0e6 Pa, D = 0.1023 m, L = 5000 m,
    mdot = 2.0 kg/s, eps = 4.57e-5 m.
    G = 243.326184890273 kg/(m2 s), Re = 2262933.51947954 (constant along
    the line, so f is constant), f = 0.0165365270433975.
    The exact solution of dP/dx = -f/D * G^2/(2 rho(P)) is
    P1^2 - P2^2 = f * G^2 * R * T * L / (M * D), giving P2 = 4190438.20059489 Pa.
    The refined Heun march reproduces it to a relative error on dP of 9.7e-8;
    test tolerance 1e-6 relative on dP.
"""

from __future__ import annotations

import math
from typing import cast

import pytest

from ngdesign.units.flow.pipe_segment import PipeSegmentSpecError
from ngdesign.units.flow.pipe_segment_r1 import (
    PipeSegmentR1Error,
    dP_fittings_Pa,
    march,
    march_refined,
)

R_GAS = 8.31446261815324  # J/(mol K), CODATA


def _colebrook_independent(Re: float, eD: float) -> float:
    """Colebrook (1939) fixed point, solved here independently of the repo code."""
    f = 0.02
    for _ in range(200):
        rhs = -2.0 * math.log10(eD / 3.7 + 2.51 / (Re * math.sqrt(f)))
        f_new = (1.0 / rhs) ** 2
        if abs(f_new - f) < 1e-15:
            return f_new
        f = f_new
    return f


class TestC1IncompressibleLiquid:
    D_M = 0.1023
    L_M = 100.0
    EPS = 4.57e-5
    MDOT = 10.0
    DZ = 10.0
    RHO = 998.0
    MU = 1.0e-3
    K = 2.5

    @staticmethod
    def _props(P: float) -> tuple[float, float]:
        return TestC1IncompressibleLiquid.RHO, TestC1IncompressibleLiquid.MU

    def test_printed_f_matches_independent_colebrook(self) -> None:
        area = math.pi * self.D_M**2 / 4
        v = self.MDOT / self.RHO / area
        Re = self.RHO * v * self.D_M / self.MU
        assert v == pytest.approx(1.21906906257652, rel=1e-13)
        assert Re == pytest.approx(124461.343571375, rel=1e-12)
        f = _colebrook_independent(Re, self.EPS / self.D_M)
        assert f == pytest.approx(0.0195416887606116, rel=1e-12)

    @pytest.mark.parametrize("n", [1, 4, 10])
    def test_march_constant_props_exact(self, n: int) -> None:
        # Heun is exact for a constant derivative, so every n gives the same
        # dP to round-off; the printed reference carries 15-digit rounding, so
        # the comparison is 1e-12 relative (tighter than 1e-10 absolute here).
        P_in = 1.0e6
        P_out = march(P_in, self.L_M, self.D_M, self.DZ, self.EPS, self.MDOT, self._props, n)
        dP = P_in - P_out
        assert dP == pytest.approx(112036.249127719, rel=1e-12)

    def test_fittings_helper(self) -> None:
        dP_K = dP_fittings_Pa(self.K, self.D_M, self.MDOT, self.RHO)
        assert dP_K == pytest.approx(1853.94640071566, abs=1e-10)
        total = 112036.249127719 + dP_K
        assert total == pytest.approx(113890.195528435, abs=1e-9)


class TestC2IsothermalIdealGas:
    M = 0.016043  # kg/mol, methane
    T = 300.0
    P_IN = 5.0e6
    D_M = 0.1023
    L_M = 5000.0
    MDOT = 2.0
    EPS = 4.57e-5
    MU = 1.1e-5

    def _props(self, P: float) -> tuple[float, float]:
        return P * self.M / (R_GAS * self.T), self.MU

    def test_printed_f_matches_independent_colebrook(self) -> None:
        area = math.pi * self.D_M**2 / 4
        G = self.MDOT / area
        assert G == pytest.approx(243.326184890273, rel=1e-12)
        Re = G * self.D_M / self.MU
        assert Re == pytest.approx(2262933.51947954, rel=1e-12)
        f = _colebrook_independent(Re, self.EPS / self.D_M)
        assert f == pytest.approx(0.0165365270433975, rel=1e-12)

    def test_refined_march_matches_analytic_solution(self) -> None:
        P_out, n_used = march_refined(
            self.P_IN, self.L_M, self.D_M, 0.0, self.EPS, self.MDOT, self._props, 20
        )
        dP_num = self.P_IN - P_out
        P2_exact = 4190438.20059489
        dP_exact = self.P_IN - P2_exact
        assert abs(dP_num - dP_exact) / dP_exact <= 1.0e-6
        assert n_used >= 20


def test_march_refuses_bad_geometry() -> None:
    props = lambda P: (998.0, 1.0e-3)  # noqa: E731
    with pytest.raises(PipeSegmentSpecError, match="L_m"):
        march(1.0e6, 0.0, 0.1023, 0.0, 4.57e-5, 10.0, props, 10)
    with pytest.raises(PipeSegmentSpecError, match="D_m"):
        march(1.0e6, 100.0, -1.0, 0.0, 4.57e-5, 10.0, props, 10)
    with pytest.raises(PipeSegmentSpecError, match="roughness_m"):
        march(1.0e6, 100.0, 0.1023, 0.0, -1.0, 10.0, props, 10)
    with pytest.raises(PipeSegmentSpecError, match="n_segments"):
        march(1.0e6, 100.0, 0.1023, 0.0, 4.57e-5, 10.0, props, 0)


def test_march_refuses_pressure_collapse() -> None:
    # A huge flow on a gas line drives the march through zero pressure.
    props = lambda P: (P * 0.016043 / (R_GAS * 300.0), 1.1e-5)  # noqa: E731
    with pytest.raises(PipeSegmentR1Error, match="pressure falls to zero"):
        march(2.0e5, 5000.0, 0.1023, 0.0, 4.57e-5, 50.0, props, 10)


# --- R1 adapter (spec step 2) -------------------------------------------------

from ngdesign.contracts import StreamState  # noqa: E402
from ngdesign.contracts.plugins import Thermo  # noqa: E402
from ngdesign.units.flow.pipe_segment import PipeSegment  # noqa: E402
from ngdesign.units.flow.pipe_segment_r1 import PipeSegmentR1  # noqa: E402
from tests.conftest import flash_feed  # noqa: E402

CONDENSATE_FEED = {
    "T": 293.15,
    "P": 1.0e6,
    "molar_flow": 50.0,
    "composition": {"iC4": 0.392, "nC4": 0.248, "iC5": 0.157, "nC5": 0.203},
}


def test_r1_reduces_to_r0_on_a_horizontal_line(thermo: Thermo) -> None:
    """R1 to R0 identity: R0 in dP mode with dP = friction + fittings and no
    elevation gives the identical outlet (P to 1e-10 relative, T to 1e-12 K)."""
    params = {"L_m": 500.0, "D_m": 0.1023, "K_fittings": 1.2}
    inlets = {"inlet": flash_feed(thermo, CONDENSATE_FEED)}
    r1 = PipeSegmentR1().solve(inlets, params, thermo)
    dP = r1.info["dP_friction_Pa"] + r1.info["dP_fittings_Pa"]
    r0 = PipeSegment().solve(inlets, {"dP": dP, "elevation_m": 0.0}, thermo)
    assert r0.outlets["outlet"].P == pytest.approx(r1.outlets["outlet"].P, rel=1e-10)
    assert r0.outlets["outlet"].T == pytest.approx(r1.outlets["outlet"].T, abs=1e-12)


def test_r1_n_butane_liquid_line_hydrostatic(thermo: Thermo) -> None:
    """A 20 m rise books the integrated rho*g*dz: within 1e-3 relative of
    rho_in*g*20 (the density varies slightly along the line)."""
    feed = {"T": 293.15, "P": 1.0e6, "molar_flow": 100.0, "composition": {"nC4": 1.0}}
    params = {"L_m": 100.0, "D_m": 0.0779, "elevation_m": 20.0}
    inlets = {"inlet": flash_feed(thermo, feed)}
    result = PipeSegmentR1().solve(inlets, params, thermo)
    rho_in = max(inlets["inlet"].phases, key=lambda p: p.mole_fraction).density
    assert result.info["hydrostatic_Pa"] == pytest.approx(rho_in * 9.80665 * 20.0, rel=1e-3)


def test_r1_methane_gas_line_matches_z_corrected_analytic(thermo: Thermo) -> None:
    """Methane at 5 MPa: dP_total agrees with the C2 analytic form evaluated
    with the inlet-state Z-corrected density, to 2% (real-gas sanity bound)."""
    feed = {"T": 300.0, "P": 5.0e6, "molar_flow": 124.7, "composition": {"C1": 1.0}}
    params = {"L_m": 5000.0, "D_m": 0.1023}
    inlets = {"inlet": flash_feed(thermo, feed)}
    result = PipeSegmentR1().solve(inlets, params, thermo)
    inlet = inlets["inlet"]
    dom = max(inlet.phases, key=lambda p: p.mole_fraction)
    G = inlet.mass_flow / (math.pi * 0.1023**2 / 4)
    # rho_in is the real-gas density, so P/rho_in = ZRT/M directly (no Z factor).
    dP_sq = result.info["darcy_f_in"] * G**2 * (inlet.P / dom.density) * 5000.0 / 0.1023
    dP_analytic = 5.0e6 - math.sqrt(5.0e6**2 - dP_sq)
    assert result.info["dP_total_Pa"] == pytest.approx(dP_analytic, rel=0.02)


def test_r1_example_case_solves(thermo: Thermo) -> None:
    feeds, params = PipeSegmentR1.example_case()
    inlets = {port: flash_feed(thermo, f) for port, f in feeds.items()}
    result = PipeSegmentR1().solve(inlets, params, thermo)
    assert result.outlets["outlet"].P > 0
    assert result.info["n_segments_used"] >= 10


def test_r1_refuses_two_phase_inlet() -> None:
    # Hand-assembled two-phase state (a pure-component two-phase PT flash is
    # not obtainable from the PR package): the refusal must fire on the inlet.
    from ngdesign.contracts.stream import Phase, PhaseKind

    comps = {"C1": 0.5, "nC4": 0.5}
    liquid = Phase(
        kind=PhaseKind.HC_LIQUID,
        mole_fraction=0.5,
        composition=comps,
        density=600.0,
        molecular_weight=44.0,
        viscosity=3.0e-4,
    )
    vapor = Phase(
        kind=PhaseKind.VAPOR,
        mole_fraction=0.5,
        composition=comps,
        density=30.0,
        molecular_weight=44.0,
        viscosity=1.2e-5,
    )
    inlet = StreamState(
        T=300.0,
        P=2.0e6,
        molar_flow=100.0,
        composition=comps,
        vapor_fraction=0.5,
        enthalpy=0.0,
        entropy=0.0,
        phases=[liquid, vapor],
    )
    with pytest.raises(PipeSegmentR1Error, match="two-phase inlet; use R2"):
        PipeSegmentR1().solve({"inlet": inlet}, {"L_m": 100.0, "D_m": 0.0779}, cast(Thermo, _NoFlashThermo()))


def test_r1_refuses_node_flashing_two_phase(thermo: Thermo) -> None:
    # A near-saturation n-butane liquid line loses enough pressure to cross
    # the bubble point part-way along.
    feed = {"T": 295.0, "P": 3.0e5, "molar_flow": 200.0, "composition": {"nC4": 1.0}}
    params = {"L_m": 500.0, "D_m": 0.1}
    inlets = {"inlet": flash_feed(thermo, feed)}
    with pytest.raises(PipeSegmentR1Error, match="flashes to two-phase at x"):
        PipeSegmentR1().solve(inlets, params, thermo)


def test_r1_refuses_vapour_pressure_ratio_below_half(thermo: Thermo) -> None:
    feed = {"T": 300.0, "P": 5.0e6, "molar_flow": 210.0, "composition": {"C1": 1.0}}
    params = {"L_m": 5000.0, "D_m": 0.1023}
    inlets = {"inlet": flash_feed(thermo, feed)}
    with pytest.raises(PipeSegmentR1Error, match="pressure ratio below 0.5"):
        PipeSegmentR1().solve(inlets, params, thermo)


def test_r1_refuses_pressure_falls_to_zero(thermo: Thermo) -> None:
    feed = {"T": 300.0, "P": 2.0e5, "molar_flow": 12470.0, "composition": {"C1": 1.0}}
    params = {"L_m": 5000.0, "D_m": 0.1023}
    inlets = {"inlet": flash_feed(thermo, feed)}
    with pytest.raises(PipeSegmentR1Error, match="pressure falls to zero"):
        PipeSegmentR1().solve(inlets, params, thermo)


def test_r1_refuses_missing_viscosity() -> None:
    from ngdesign.contracts.stream import Phase, PhaseKind

    phase = Phase(
        kind=PhaseKind.VAPOR,
        mole_fraction=1.0,
        composition={"C1": 1.0},
        density=30.0,
        molecular_weight=16.043,
        viscosity=None,
    )
    inlet = StreamState(
        T=300.0,
        P=5.0e6,
        molar_flow=100.0,
        composition={"C1": 1.0},
        vapor_fraction=1.0,
        enthalpy=0.0,
        entropy=0.0,
        phases=[phase],
    )
    with pytest.raises(PipeSegmentSpecError, match="mu_Pa_s"):
        PipeSegmentR1().solve({"inlet": inlet}, {"L_m": 100.0, "D_m": 0.0779}, cast(Thermo, _NoFlashThermo()))


class _NoFlashThermo:
    """Stub thermo; never reached — the viscosity refusal fires first."""

    def flash_ph(
        self, z: dict[str, float], P: float, H: float, molar_flow: float
    ) -> StreamState:  # pragma: no cover
        raise AssertionError("flash_ph must not be called before the viscosity refusal")


def test_r1_refuses_zero_flow(thermo: Thermo) -> None:
    inlet = flash_feed(thermo, CONDENSATE_FEED).model_copy(update={"molar_flow": 0.0})
    with pytest.raises(PipeSegmentSpecError, match="molar_flow"):
        PipeSegmentR1().solve({"inlet": inlet}, {"L_m": 100.0, "D_m": 0.0779}, thermo)


def test_r1_refuses_bad_params(thermo: Thermo) -> None:
    inlets = {"inlet": flash_feed(thermo, CONDENSATE_FEED)}
    with pytest.raises(PipeSegmentSpecError, match="L_m"):
        PipeSegmentR1().solve(inlets, {"D_m": 0.0779}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="L_m"):
        PipeSegmentR1().solve(inlets, {"L_m": 0.0, "D_m": 0.0779}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="D_m"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": -1.0}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="roughness_m"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": 0.0779, "roughness_m": -1.0}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="K_fittings"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": 0.0779, "K_fittings": -0.1}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="elevation_m"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": 0.0779, "elevation_m": 200.0}, thermo)
    with pytest.raises(PipeSegmentSpecError, match="n_segments"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": 0.0779, "n_segments": 0}, thermo)
    with pytest.raises(PipeSegmentR1Error, match="did not converge"):
        PipeSegmentR1().solve(inlets, {"L_m": 100.0, "D_m": 0.0779, "n_segments": 1024}, thermo)
