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

import pytest

from ngdesign.units.flow.pipe_segment_r1 import (
    PipeSegmentR1Error,
    PipeSegmentSpecError,
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
        P_in = 1.0e6
        P_out = march(P_in, self.L_M, self.D_M, self.DZ, self.EPS, self.MDOT, self._props, n)
        dP = P_in - P_out
        assert dP == pytest.approx(112036.249127719, abs=1e-10)

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
