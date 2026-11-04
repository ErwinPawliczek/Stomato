"""teqp bridge: PC-SAFT, SAFT-VR-Mie, CPA-SRK, multi-fluid Helmholtz, GERG-2008 (spec T-07).

Family F through NIST's ``teqp`` (MIT licence) where teqp has a usable engine, plus a
hand-rolled CPA-SRK kernel where it does not (teqp 0.23.2's own CPA NaNs its fugacity
coefficients at liquid-like densities and collapses the water saturation line with the
published Kontogeorgis parameters — measured in the T-07 exploration). The bridge owns
the VLE flash loop (teqp has no general VLE driver):

- pressure from ``Z = 1 + rho*dalphar/drho`` via teqp ``get_Ar01`` (exact; ``get_pr``
  is broken in 0.23.2 and ``get_Ar10`` is *not* ``delta*alphar_delta``);
- residual enthalpy from ``get_Ar10 = -T*dalphar/dT`` (finite-difference fallback for
  models without it), residual entropy from H - G with G from the fugacity coefficients;
- fugacity coefficients: pure-fluid shortcut ``lnphi = Ar00 + Z - 1 - ln Z`` (exact),
  mixture path finite difference of ``Ar00`` (teqp's own ``get_fugacity_coefficients``
  returns phi, not ln phi, and NaNs for CPA-type engines);
- PT flash by a density-root scan between zero and the EOS maximum density (vapor root
  lowest, liquid root highest; the vapor root may exceed P/(RT) when Z < 1, so it is
  never bracketed at P/(RT)), Rachford-Rice on K = phi_l/phi_v by successive
  substitution, pure feeds short-circuited to a pure Psat solver;
- ideal-gas part from the ``thermo`` correlations the other packages use, via the
  resolved component records.

teqp is an optional dependency (``uv sync --extra saft``). The module imports lazily:
the catalogue rows load and their packages construct without the extra; the first
property call raises :class:`SaftDependencyMissing` (an ``ImportError``) when it is absent.
Unsupported components are refused by name — never silently treated as ideal.

The last two family-F rows (T-07 follow-up, issue #164): ``gerg2008_teqp`` runs the
GERG-2008 natural-gas mixture through teqp's multi-fluid machinery with the Kunz &
Wagner (2012) reducing/departure parameters as distributed in teqp 0.23.2's bundled
fluid library (the exact-backend cross-check the T-04 ``gerg2008`` row defers to);
``soft_saft`` (Blas & Vega 1997; reference fluid Johnson, Zollweg & Gubbins 1993) runs
on teqp 0.23.2's ``SoftSAFT`` kind (non-associating, van der Waals one-fluid mixing
with Lorentz-Berthelot rules) with the Pamies (2003) thesis parameter tables.

Registered through the thermo catalogue (data/thermo_models/saft.yaml); the adapter
classes carry no ``@register`` decorator (catalogue how-to, section 1).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import numpy as np
import yaml

from ngdesign.contracts.components import resolve
from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationError, SaturationPoint
from ngdesign.thermo import _state
from ngdesign.thermo import saft_assoc as _saft_assoc
from ngdesign.thermo.cubic import ThermoSurfaceMixin

#: CODATA 2018 molar gas constant, J/(mol.K).
R_GAS = 8.31446261815324

#: Reference state for the ideal-gas enthalpy/entropy integrals (the IUPAC standard).
T_REF = 298.15
P_REF = 101325.0

#: Ideal-gas enthalpy/entropy Simpson sub-intervals (smooth correlations).
_IG_N = 64

#: Density-root-scan resolution (geometric grid points per PT flash).
_ROOT_GRID = 70

#: Fugacity finite-difference steps (relative), validated in the T-07 exploration:
#: central differences of Ar00 at h = 1e-5*rho reproduce teqp's own phi to ~6 digits,
#: and the d(alphar)/drho route reproduces CoolProp pressure to 10 digits.
_DRHO_H = 1e-5
_DPTH_H = 1e-4

#: Evenly spaced dense-range root-scan points for the multi-fluid Helmholtz kernels.
#: Inside the two-phase dome a reference EOS oscillates wildly (Span-Wagner CO2 at
#: 265 K swings between -4.6e10 and +1.1e11 Pa over 5000-15000 mol/m3), and the
#: 40 %-wide cells of the geometric grid hide the liquid branch's crossing in pairs:
#: the scan returned a spurious 11016 mol/m3 root as "the liquid" and the pure Psat
#: hunt reported "at/above Tc" at 265 K and 196 kPa (vs 4.71 MPa) at 285 K. Cells of
#: cap/200 (~210 mol/m3 for CO2) resolve the liquid crossing.
_MULTIFLUID_DENSE_GRID = 200

#: Incipient-phase successive substitution at one trial pressure (bubble/dew K-sum):
#: iteration cap and convergence bar on the largest mole-fraction step.
_SAT_INNER_ITERS = 60
_SAT_INNER_TOL = 1e-9
#: Near-critical vapour test of the bubble/dew K-sum: a light root with
#: _SAT_VAPOUR_Z_MIN < Z <= 0.5 still counts as vapour when the heavy root is more
#: than _SAT_NEAR_CRIT_SPLIT times denser (see ``_sat_ksum_solve``).
_SAT_VAPOUR_Z_MIN = 0.3
#: Largest |ln K| the PT-flash successive substitution accepts (K ~ 1e30).
_LN_K_MAX = 70.0
_SAT_NEAR_CRIT_SPLIT = 2.0

#: Cited pure-component parameter file (see data/thermo_params/saft/pure.yaml).
_PARAMS_PATH = Path(__file__).resolve().parents[3] / "data" / "thermo_params" / "saft" / "pure.yaml"


class SaftDependencyMissing(ImportError):
    """The optional ``saft`` extra (teqp) is not installed in this environment."""


class SaftParameterError(ValueError):
    """A component has no verified SAFT parameters; the bridge refuses it by name."""


def _teqp() -> Any:
    """The teqp module, imported on first use (optional extra)."""
    try:
        import teqp  # noqa: PLC0415 - deliberate lazy import of the optional extra
    except ImportError as exc:
        raise SaftDependencyMissing(
            "teqp is not installed; install the optional extra with `uv sync --extra saft`"
        ) from exc
    return teqp


@lru_cache(maxsize=1)
def _saft_params() -> dict[str, Any]:
    """The cited pure-component parameter file, loaded once."""
    raw = yaml.safe_load(_PARAMS_PATH.read_text())
    assert isinstance(raw, dict), f"{_PARAMS_PATH}: malformed parameter file"
    return raw


def _require_params(kind: str, cids: tuple[str, ...], subkey: str | None = None) -> dict[str, Any]:
    """The parameter block for one model kind, refusing unsupported components by name.

    ``subkey`` digs one level into the block (e.g. multifluid's alias table).
    """
    block = _saft_params().get(kind)
    assert isinstance(block, dict), f"{_PARAMS_PATH}: missing {kind} block"
    if subkey is not None:
        nested = block.get(subkey)
        assert isinstance(nested, dict), f"{_PARAMS_PATH}: missing {kind}.{subkey} block"
        block = nested
    unsupported = [cid for cid in cids if cid not in block]
    if unsupported:
        raise SaftParameterError(
            f"no verified {kind} parameters for {unsupported}; supported: {sorted(block)} "
            "(unsupported components are refused, never treated as ideal)"
        )
    return block


@lru_cache(maxsize=256)
def _ig_constants(cids: tuple[str, ...]) -> tuple[Any, Any]:
    """(constants, correlations) for one sorted support, through the component registry."""
    records = [resolve(cid) for cid in cids]
    return _state._constants_package(records)  # noqa: SLF001 - same-package helper


class _IdealGasPart:
    """Ideal-gas cp/enthalpy/entropy integrals for one support."""

    def __init__(self, cids: tuple[str, ...]) -> None:
        constants, correlations = _ig_constants(cids)
        self.mws: list[float] = [float(mw) for mw in constants.MWs]
        self._cps: list[Any] = list(correlations.HeatCapacityGases)

    def cp(self, i: int, T: float) -> float:
        """Ideal-gas cp of component i at T (J/(mol K))."""
        got = self._cps[i].T_dependent_property(T)
        if got is None:
            raise SaftParameterError(f"ideal-gas cp correlation returned nothing at T={T} K")
        return float(got)

    def enthalpy(self, i: int, T: float) -> float:
        """Integral of cp from T_REF to T (J/mol), Simpson on the correlation."""
        if T == T_REF:
            return 0.0
        h = (T - T_REF) / _IG_N
        total = self.cp(i, T_REF) + self.cp(i, T)
        for k in range(1, _IG_N):
            total += (4.0 if k % 2 == 1 else 2.0) * self.cp(i, T_REF + k * h)
        return total * h / 3.0

    def entropy_ref(self, i: int, T: float) -> float:
        """Integral of cp/T from T_REF to T at the reference pressure (J/(mol K))."""
        if T == T_REF:
            return 0.0
        h = (T - T_REF) / _IG_N
        total = self.cp(i, T_REF) / T_REF + self.cp(i, T) / T
        for k in range(1, _IG_N):
            tk = T_REF + k * h
            total += (4.0 if k % 2 == 1 else 2.0) * self.cp(i, tk) / tk
        return total * h / 3.0


class _Kernel:
    """One residual-Helmholtz engine behind the bridge's shared flash machinery.

    All methods take molar density (mol/m3) and mole-fraction arrays in support
    order; compositions need not be renormalized after finite-difference shifts.
    """

    name: str
    #: Extra evenly spaced root-scan points over the dense range (0.02-0.999 of the
    #: cap). Zero for the smooth SAFT/CPA kernels; the multi-fluid Helmholtz kernels
    #: need them (see ``_build_kernel``).
    dense_grid_points: int = 0

    def pressure(self, T: float, rho: float, z: np.ndarray) -> float:
        raise NotImplementedError

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def h_res_rt(self, T: float, rho: float, z: np.ndarray) -> float:
        raise NotImplementedError

    def max_density(self, T: float, z: np.ndarray) -> float:
        raise NotImplementedError

    def pure_saturation_pressure(self, T: float) -> tuple[bool, float | None]:
        """Pure-fluid Psat from an engine-native VLE solver.

        ``(False, None)``: no native solver, run the bridge's root hunt. ``(True, p)``:
        the native answer, ``p`` None when no vapour pressure exists (T >= Tc).
        """
        return False, None

    def roots(self, T: float, P: float, z: np.ndarray) -> list[float]:
        """Density roots of p(rho) = P, lowest first, bisected to ~1e-12 relative.

        Between coarse grid points whose residuals are both positive the geometric
        midpoint is probed as well: the liquid-branch pressure dip can be narrower
        than one grid cell, and a dip below P hides two roots from a plain
        sign-change scan.
        """
        cap = self.max_density(T, z)
        grid = np.geomspace(cap * 1e-10, cap * 0.999, _ROOT_GRID)
        if self.dense_grid_points:
            grid = np.union1d(grid, np.linspace(cap * 0.02, cap * 0.999, self.dense_grid_points))

        def bisect(lo: float, hi: float, flo: float) -> float:
            for _ in range(80):
                mid = 0.5 * (lo + hi)
                fm = self.pressure(T, mid, z) - P
                if flo * fm <= 0.0:
                    hi = mid
                else:
                    lo, flo = mid, fm
            return 0.5 * (lo + hi)

        out: list[float] = []
        prev_r = float(grid[0])
        prev_res = self.pressure(T, prev_r, z) - P
        for k in range(1, grid.size):
            r = float(grid[k])
            res = self.pressure(T, r, z) - P
            if prev_res == 0.0:
                out.append(prev_r)
            elif prev_res * res < 0.0:
                out.append(bisect(prev_r, r, prev_res))
            elif prev_res > 0.0 and res > 0.0:
                gm = math.sqrt(prev_r * r)
                gmres = self.pressure(T, gm, z) - P
                if gmres < 0.0:
                    out.append(bisect(prev_r, gm, prev_res))
                    out.append(bisect(gm, r, gmres))
            prev_r, prev_res = r, res
        return out


def _mu_shift(
    residual: Callable[[float, np.ndarray], float], rho: float, z: np.ndarray, h: float
) -> np.ndarray:
    """d((rho+s)*Ar00(T, rho+s, z(s)))/ds at s=0 by central finite difference.

    The Michelsen path z(s) = (rho*z + s*e_i)/(rho + s) moves density and
    composition together, which makes the finite difference a true
    chemical-potential derivative (mu_i_res/RT) for Helmholtz models. The
    product derivative already carries the alpha_r term: for a pure fluid it
    is exactly alpha_r + (Z - 1).
    """
    out = np.zeros(z.size)
    for i in range(z.size):
        up_comp = (rho * z + h * _unit(i, z.size)) / (rho + h)
        down_comp = (rho * z - h * _unit(i, z.size)) / (rho - h)
        up = residual(rho + h, up_comp) * (rho + h)
        down = residual(rho - h, down_comp) * (rho - h)
        out[i] = (up - down) / (2.0 * h)
    return out


def _unit(i: int, n: int) -> np.ndarray:
    """Standard basis vector e_i of length n."""
    e = np.zeros(n)
    e[i] = 1.0
    return e


class _NonPhysicalZ(ValueError):
    """ln phi requested at a state with Z <= 0 (stretched liquid past its root)."""


class _TeqpKernel(_Kernel):
    """teqp residual-Helmholtz engine (PC-SAFT, SAFT-VR-Mie, multi-fluid)."""

    def __init__(self, name: str, model: Any) -> None:
        self.name = name
        self.model = model

    def pressure(self, T: float, rho: float, z: np.ndarray) -> float:
        # Z = 1 + rho*dalphar/drho, exact through teqp's Ar01 (get_pr is broken in 0.23.2).
        return rho * R_GAS * T * (1.0 + float(self.model.get_Ar01(T, rho, z)))

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        Z = 1.0 + float(self.model.get_Ar01(T, rho, z))
        if Z <= 0.0:
            raise _NonPhysicalZ(f"Z={Z:.6g} at T={T} K, rho={rho:.6g}")
        if z.size == 1:
            # Pure-fluid shortcut, exact: mu_res/RT = Ar00 + Z - 1.
            return np.array([float(self.model.get_Ar00(T, rho, z)) + Z - 1.0 - math.log(Z)])
        mu = _mu_shift(lambda r, comp: float(self.model.get_Ar00(T, r, comp)), rho, z, _DRHO_H * rho)
        return mu - math.log(Z)

    def h_res_rt(self, T: float, rho: float, z: np.ndarray) -> float:
        Z = 1.0 + float(self.model.get_Ar01(T, rho, z))
        ar10 = getattr(self.model, "get_Ar10", None)
        if callable(ar10):
            got = float(ar10(T, rho, z))
            if math.isfinite(got):
                # get_Ar10 = -T*dalphar/dT (validated in the T-07 exploration).
                return got + Z - 1.0
        h = _DPTH_H * T
        d = (float(self.model.get_Ar00(T + h, rho, z)) - float(self.model.get_Ar00(T - h, rho, z))) / (
            2.0 * h
        )
        return -T * d + Z - 1.0

    def max_density(self, T: float, z: np.ndarray) -> float:
        max_rho_n = getattr(self.model, "max_rhoN", None)
        if callable(max_rho_n):  # SAFT kinds expose the packing limit exactly
            return float(max_rho_n(T, z)) / 6.02214076e23 * 0.999
        reducing = getattr(self.model, "get_reducing_density", None)
        if callable(reducing):  # multi-fluid: stay within a finite delta
            try:
                return float(reducing(z)) * 4.0
            except RuntimeError:
                pass  # SAFT kinds carry the attribute but raise on call
        return 3.0e4


class _MultifluidKernel(_TeqpKernel):
    """teqp multi-fluid Helmholtz engine (CoolProp fluid library or exact GERG-2008).

    Reference equations of state oscillate wildly inside the two-phase dome, which
    the root scan must resolve (``dense_grid_points``) and which can make a spurious
    in-dome root look like the stable liquid to the pure-Psat root hunt (measured,
    Span-Wagner CO2 at 285 K: near-critical, no liquid root exists below the
    ~3.5 MPa liquid spinodal and the in-dome root at 10984 mol/m3 has the lower
    fugacity, so the hunt closed on 196 kPa against 4.71 MPa; GERG-2008 CO2 at
    300 K closed on 6.50 MPa against 6.71 MPa). The pure Psat is therefore teqp's
    Newton solve of the pure VLE (``pure_VLE_T``: equal pressure and Gibbs energy of
    both phases), seeded by teqp's VLE ancillaries of the fluid-library equation
    (``seed_model``; the model itself when it carries them), and refused at or
    above the model's own critical temperature (``solve_pure_critical``).
    """

    dense_grid_points = _MULTIFLUID_DENSE_GRID

    def __init__(self, name: str, model: Any, seed_model: Any = None) -> None:
        super().__init__(name, model)
        self._seed_model = seed_model if seed_model is not None else model
        self._ancillaries: Any = None
        self._t_crit: float | None = None

    def pure_saturation_pressure(self, T: float) -> tuple[bool, float | None]:
        build = getattr(self._seed_model, "build_ancillaries", None)
        if not callable(build):
            return False, None
        z = np.array([1.0])
        if self._ancillaries is None:
            self._ancillaries = build()
            t_red = float(self.model.get_reducing_temperature(z))
            rho_red = float(self.model.get_reducing_density(z))
            self._t_crit = float(self.model.solve_pure_critical(t_red, rho_red)[0])
        assert self._t_crit is not None
        if T >= self._t_crit:
            return True, None
        anc = self._ancillaries
        try:
            rho_l, rho_v = (float(v) for v in self.model.pure_VLE_T(T, anc.rhoL(T), anc.rhoV(T), 50))
        except (RuntimeError, ValueError):
            return False, None
        if not (math.isfinite(rho_l) and math.isfinite(rho_v) and rho_v > 0.0 and rho_l > 1.001 * rho_v):
            return False, None  # Newton collapsed onto one density: let the hunt decide
        p_l, p_v = self.pressure(T, rho_l, z), self.pressure(T, rho_v, z)
        mu_l = float(self.ln_phi(T, rho_l, z)[0]) + math.log(p_l)
        mu_v = float(self.ln_phi(T, rho_v, z)[0]) + math.log(p_v)
        if abs(p_l - p_v) > 1e-8 * p_v or abs(mu_l - mu_v) > 1e-8:
            return False, None
        return True, p_v


class _SoftSaftKernel(_TeqpKernel):
    """teqp ``SoftSAFT`` with a density cap inside the reference fluid's fitted range.

    teqp's soft-SAFT kind exposes neither ``max_rhoN`` nor a reducing density, so
    the root scan is capped at the largest reduced segment density of the
    Johnson, Zollweg & Gubbins (1993) MBWR fit, rho* = rho_seg sigma^3 = 1.25
    (Mol. Phys. 78, 591, p. 594: "densities ranged from 0.1 <= rho* <= 1.25 at
    the highest temperature"). At low T* the MBWR turns over below that density
    (methane at 114 K: the pressure peaks near rho* = 1.14 and goes negative by
    1.25), so the cap stops at the first pressure maximum on the compressed-liquid
    branch; past it the fit is extrapolating and its roots are not physical.
    sigma^3 and the segment count follow the van der Waals one-fluid rules of the
    kernel (Pamies 2003 thesis eqs 2.2 and 2.4; sigma_ij arithmetic mean).
    """

    #: Highest reduced segment density in the JZG (1993) simulation data set.
    RHO_STAR_MAX = 1.25
    #: Start of the compressed-liquid scan, reduced segment density.
    _RHO_STAR_SCAN = 0.7
    _SCAN_POINTS = 56

    def __init__(self, name: str, model: Any, params: list[dict[str, Any]]) -> None:
        super().__init__(name, model)
        self._m = np.array([float(p["m"]) for p in params])
        self._sigma = np.array([float(p["sigma_Angstrom"]) * 1e-10 for p in params])
        self._cap_cache: dict[tuple[float, bytes], float] = {}

    def _segment_scale(self, z: np.ndarray) -> float:
        """Molar density per unit reduced segment density, 1/(m_mix sigma_mix^3 N_A)."""
        mz = self._m * z
        pair = ((self._sigma[:, None] + self._sigma[None, :]) / 2.0) ** 3
        sig3 = float(mz @ pair @ mz) / float(mz.sum()) ** 2
        return 1.0 / (float(mz.sum()) * sig3 * 6.02214076e23)

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        """Exact ln phi from teqp's automatic-differentiation fugacity coefficients.

        The finite-difference mixture path of the base class carries ~4e-8 noise,
        which fails the 1e-6 Gibbs-Duhem L0 bar on dense liquids (measured 1.3e-4
        on C3/nC6 at 300 K, 5 MPa); teqp's ``get_fugacity_coefficients`` is exact
        and finite for this kind (it NaNs only for the CPA-type engines).
        """
        if z.size == 1:
            return super().ln_phi(T, rho, z)
        Z = 1.0 + float(self.model.get_Ar01(T, rho, z))
        if Z <= 0.0:
            raise _NonPhysicalZ(f"Z={Z:.6g} at T={T} K, rho={rho:.6g}")
        phi = np.asarray(self.model.get_fugacity_coefficients(T, rho * z / float(z.sum())), dtype=float)
        return np.log(phi)

    def max_density(self, T: float, z: np.ndarray) -> float:
        key = (round(T, 9), z.tobytes())
        hit = self._cap_cache.get(key)
        if hit is not None:
            return hit
        scale = self._segment_scale(z)
        grid = np.linspace(self._RHO_STAR_SCAN, self.RHO_STAR_MAX, self._SCAN_POINTS) * scale
        cap = float(grid[-1])
        prev = self.pressure(T, float(grid[0]), z)
        for k in range(1, grid.size):
            cur = self.pressure(T, float(grid[k]), z)
            if prev > 0.0 and cur < prev:
                cap = float(grid[k - 1])
                break
            prev = cur
        self._cap_cache[key] = cap
        return cap


class _CpaKernel(_Kernel):
    """Hand-rolled CPA-SRK engine (Kontogeorgis, Voutsas, Yakoumis & Tassios 1999).

    Cubic part: SRK with a_i(T) = a0_i*(1 + c1_i*(1 - sqrt(T/Tc_i)))^2, standard
    vdW mixing (a_ij = sqrt(a_i a_j), zero k_ij). Association part: the CPA
    association term with donor-acceptor site pairing, CR1 cross-association
    (epsilon arithmetic mean, beta geometric mean), SRK radial distribution
    function g = 1/(1 - 1.9 eta) with eta = b*rho/4, and site fractions X_A by
    successive substitution. Every derivative comes from the same alpha_r
    finite-difference route the teqp kernels use, so the bridge's flash and
    property layer is engine-agnostic. With X = 1 (no association) the
    association term is exactly zero, which the pure-alkane guard tests rely on.
    """

    def __init__(self, name: str, params: list[dict[str, Any]], tcs: list[float]) -> None:
        self.name = name
        self.params = params
        self.tcs = tcs
        # The Wertheim association term lives in saft_assoc.py (spec T-17), shared
        # with the cpa_pr and pc_saft_assoc rows; the arithmetic is moved verbatim,
        # so this row's numbers are unchanged.
        self._assoc = _saft_assoc.CPAWertheim(params)

    def _a_i(self, i: int, T: float) -> float:
        p = self.params[i]
        return float(p["a0"]) * (1.0 + float(p["c1"]) * (1.0 - math.sqrt(T / self.tcs[i]))) ** 2

    def _b_mix(self, z: np.ndarray) -> float:
        return float(sum(x * p["b"] for x, p in zip(z, self.params, strict=True)))

    def _alpha_phys(self, T: float, rho: float, z: np.ndarray) -> float:
        b_mix = self._b_mix(z)
        a_mix = 0.0
        for i, xi in enumerate(z):
            for j, xj in enumerate(z):
                a_mix += xi * xj * math.sqrt(self._a_i(i, T) * self._a_i(j, T))
        br = b_mix * rho
        return -math.log(1.0 - br) - (a_mix / (b_mix * R_GAS * T)) * math.log(1.0 + br)

    def _alpha_assoc(self, T: float, rho: float, z: np.ndarray) -> float:
        return self._assoc.alpha(T, rho, z)

    def _alpha_r(self, T: float, rho: float, z: np.ndarray) -> float:
        return self._alpha_phys(T, rho, z) + self._alpha_assoc(T, rho, z)

    def pressure(self, T: float, rho: float, z: np.ndarray) -> float:
        h = _DRHO_H * rho
        dadrho = (self._alpha_r(T, rho + h, z) - self._alpha_r(T, rho - h, z)) / (2.0 * h)
        return rho * R_GAS * T * (1.0 + rho * dadrho)

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        h = _DRHO_H * rho
        dadrho = (self._alpha_r(T, rho + h, z) - self._alpha_r(T, rho - h, z)) / (2.0 * h)
        Z = 1.0 + rho * dadrho
        if Z <= 0.0:
            raise _NonPhysicalZ(f"Z={Z:.6g} at T={T} K, rho={rho:.6g}")
        mu = _mu_shift(lambda r, comp: self._alpha_r(T, r, comp), rho, z, h)
        return mu - math.log(Z)

    def h_res_rt(self, T: float, rho: float, z: np.ndarray) -> float:
        h = _DRHO_H * rho
        dadrho = (self._alpha_r(T, rho + h, z) - self._alpha_r(T, rho - h, z)) / (2.0 * h)
        Z = 1.0 + rho * dadrho
        ht = _DPTH_H * T
        d = (self._alpha_r(T + ht, rho, z) - self._alpha_r(T - ht, rho, z)) / (2.0 * ht)
        return -T * d + Z - 1.0

    def max_density(self, T: float, z: np.ndarray) -> float:
        # The SRK pole sits at rho = 1/b_mix; the association g-divergence at 2/b_mix.
        return 0.98 / self._b_mix(z)


class _CpaPrKernel(_CpaKernel):
    """CPA-PR (row ``cpa_pr``): PR physical term + the shared association term.

    Physical part: Peng-Robinson, a_i(T) = a0_i (1 + c1_i (1 - sqrt(T/Tc_i)))^2
    (the paper's fitted Soave-type alpha, Sorensen et al. 2018, Appendix A eq. A2),
    classical vdW mixing with the paper's temperature-dependent k_ij (Table 7), and
    A_phys/(NRT) = -ln(1 - b rho)
                    - a_mix/(2 sqrt(2) b R T) ln((1 + (1 + sqrt 2) b rho) / (1 + (1 - sqrt 2) b rho)).
    Association part: identical to cpa_srk — the shared saft_assoc.CPAWertheim term
    with the paper's simplified-CPA RDF g = 1/(1 - 1.9 eta), eta = b rho/4
    (Appendix A eq. A14) and CR-1 combining rules (eq. A15-A16).
    """

    def __init__(
        self, name: str, params: list[dict[str, Any]], tcs: list[float], kij_table: dict[str, Any]
    ) -> None:
        super().__init__(name, params, tcs)
        self._kij_table = kij_table

    def _kij(self, i: int, j: int, T: float) -> float:
        """Temperature-dependent binary interaction parameter (Sorensen 2018, Table 7)."""
        key = "-".join(sorted((self.params[i]["name"], self.params[j]["name"])))
        entry = self._kij_table.get(key)
        if entry is None:
            return 0.0
        return float(entry["kij_ref"]) + float(entry["kij_prime"]) * (T - float(entry["T_ref"]))

    def _a_mix(self, T: float, z: np.ndarray) -> float:
        a_mix = 0.0
        for i, xi in enumerate(z):
            for j, xj in enumerate(z):
                a_mix += xi * xj * math.sqrt(self._a_i(i, T) * self._a_i(j, T)) * (1.0 - self._kij(i, j, T))
        return a_mix

    def _alpha_phys(self, T: float, rho: float, z: np.ndarray) -> float:
        b_mix = self._b_mix(z)
        a_mix = self._a_mix(T, z)
        br = b_mix * rho
        return -math.log(1.0 - br) - (a_mix / (2.0 * math.sqrt(2.0) * b_mix * R_GAS * T)) * math.log(
            (1.0 + (1.0 + math.sqrt(2.0)) * br) / (1.0 + (1.0 - math.sqrt(2.0)) * br)
        )

    def _alpha_phys_derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """a_phys and its exact rho / composition derivatives at fixed (T, rho).

        Returns ``(a_phys, da/drho, [da/dz_i])``. The composition derivative is

            da/dz_i = rho b_i/(1 - B)
                      - 1/(2 sqrt(2) R T) [ ((da_i b - a b_i)/b^2) f(B)
                                            + (a/b) rho b_i f'(B) ],

        with B = b rho, f(B) the PR log term, da_i = da_mix/dz_i = 2 sum_j z_j a_ij,
        and da/drho = b/(1 - B) - a f'(B)/(2 sqrt(2) R T).
        """
        b = self._b_mix(z)
        a = self._a_mix(T, z)
        br = b * rho
        s2 = math.sqrt(2.0)
        f = math.log((1.0 + (1.0 + s2) * br) / (1.0 + (1.0 - s2) * br))
        fp = (1.0 + s2) / (1.0 + (1.0 + s2) * br) - (1.0 - s2) / (1.0 + (1.0 - s2) * br)
        a_phys = -math.log(1.0 - br) - (a / (2.0 * s2 * b * R_GAS * T)) * f
        dadrho = b / (1.0 - br) - a * fp / (2.0 * s2 * R_GAS * T)
        out = np.zeros(z.size)
        for i in range(z.size):
            bi = float(self.params[i]["b"])
            da_i = 0.0
            for j, xj in enumerate(z):
                da_i += xj * math.sqrt(self._a_i(i, T) * self._a_i(j, T)) * (1.0 - self._kij(i, j, T))
            da_i *= 2.0
            out[i] = rho * bi / (1.0 - br) - ((da_i * b - a * bi) / (b * b) * f + (a / b) * rho * bi * fp) / (
                2.0 * s2 * R_GAS * T
            )
        return a_phys, dadrho, out

    def _alpha_r_derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """a_r and its exact rho / composition derivatives (PR physical + association)."""
        a_phys, dadrho_phys, dz_phys = self._alpha_phys_derivs(T, rho, z)
        alpha_a, dadrho_a, dz_a = self._assoc.derivs(T, rho, z)
        return a_phys + alpha_a, dadrho_phys + dadrho_a, dz_phys + dz_a

    def pressure(self, T: float, rho: float, z: np.ndarray) -> float:
        """P = rho R T (1 + rho da_r/drho) with both derivative terms in closed form."""
        _a, dadrho, _dz = self._alpha_r_derivs(T, rho, z)
        return rho * R_GAS * T * (1.0 + rho * dadrho)

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        """Fully analytic fugacity coefficients.

        ln phi_i = a_r + rho da_r/drho + da_r/dz_i - sum_j z_j da_r/dz_j - ln Z,
        every term closed-form (the PR physical term and the association term
        both differentiated exactly). The Michelsen-shift finite difference the
        parent class uses carries a truncation error of order h^2 times the
        third shift-derivative, which at this row's liquid-like packing
        fractions (the PR pole sits at 1/b_mix) breaks the bridge's 1e-6
        Gibbs-Duhem integral: measured 3.7e-6 at 30 midpoint steps, 3.5e-6 at
        120 (quadrature-converged), against cpa_srk's 5.7e-8 on the flatter
        ln(1+B) SRK form. Closed-form derivatives on the whole surface remove
        the finite-difference error fields entirely; partial fixes (analytic mu
        with finite-difference Z and density roots) keep an incoherent surface
        and still measured 3.8e-6.
        """
        a_r, dadrho, dz = self._alpha_r_derivs(T, rho, z)
        Z = 1.0 + rho * dadrho
        if Z <= 0.0:
            raise _NonPhysicalZ(f"Z={Z:.6g} at T={T} K, rho={rho:.6g}")
        mu = a_r + rho * dadrho + dz - float(z @ dz)
        return mu - math.log(Z)

    def max_density(self, T: float, z: np.ndarray) -> float:
        # The PR pole sits at rho = 1/b_mix (same co-volume as the SRK pole);
        # the association g-divergence at 1.96/b_mix is beyond it.
        return 0.98 / self._b_mix(z)


class _PCSaftAssocKernel(_Kernel):
    """Hand-rolled PC-SAFT engine with the Wertheim association term (spec T-17).

    Physical part: PC-SAFT hard-chain + dispersion exactly as published (Gross &
    Sadowski 2001, Table 3 constants, closed-form density and composition
    derivatives) — reimplemented because teqp's PC-SAFT carries no association
    contribution, and the shared kernel surface needs one coherent analytic
    derivative field. The hand-rolled physical term is pinned to teqp's by the
    check-value test in tests/thermo/test_saft.py before any association case
    binds to it. Association part: the shared PCSaftWertheim term with G&S
    2002's two-site (2B) assignment for every associating fluid and the eq. 2-3
    cross-association combining rules; pure fluids associate through their own
    donor-acceptor site pairs exactly as in the CPA kernels.
    """

    def __init__(self, name: str, params: list[dict[str, Any]]) -> None:
        self.name = name
        self.params = params
        self._phys = _saft_assoc.PCSaftPhysical(params)
        self._assoc = _saft_assoc.PCSaftWertheim(params)

    def _alpha_r_derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """alpha_r and its exact rho / composition derivatives (chain + disp + assoc)."""
        a_phys, dadrho_phys, dz_phys = self._phys.derivs(T, rho, z)
        alpha_a, dadrho_a, dz_a = self._assoc.derivs(T, rho, z)
        return a_phys + alpha_a, dadrho_phys + dadrho_a, dz_phys + dz_a

    def pressure(self, T: float, rho: float, z: np.ndarray) -> float:
        """P = rho R T (1 + rho da_r/drho), the derivative in closed form."""
        _a, dadrho, _dz = self._alpha_r_derivs(T, rho, z)
        return rho * R_GAS * T * (1.0 + rho * dadrho)

    def ln_phi(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        """Fully analytic fugacity coefficients (the cpa_pr formula, closed form)."""
        a_r, dadrho, dz = self._alpha_r_derivs(T, rho, z)
        Z = 1.0 + rho * dadrho
        if Z <= 0.0:
            raise _NonPhysicalZ(f"Z={Z:.6g} at T={T} K, rho={rho:.6g}")
        mu = a_r + rho * dadrho + dz - float(z @ dz)
        return mu - math.log(Z)

    def h_res_rt(self, T: float, rho: float, z: np.ndarray) -> float:
        """-T d(alpha_r)/dT + Z - 1; the T derivative is a central difference (the
        cpa kernels' pattern; the density and composition derivatives stay analytic)."""
        _a, dadrho, _dz = self._alpha_r_derivs(T, rho, z)
        Z = 1.0 + rho * dadrho
        ht = _DPTH_H * T
        up = (self._alpha_r_derivs(T + ht, rho, z)[0] - self._alpha_r_derivs(T - ht, rho, z)[0]) / (2.0 * ht)
        return -T * up + Z - 1.0

    def max_density(self, T: float, z: np.ndarray) -> float:
        """The BMCSL packing limit zeta_3 = 0.74 (teqp's max_rhoN), at 99.9 %."""
        eps = np.array([float(p["epsilon_over_k"]) for p in self.params])
        m = np.array([float(p["m"]) for p in self.params])
        sigma = np.array([float(p["sigma_Angstrom"]) for p in self.params])
        d = sigma * (1.0 - 0.12 * np.exp(-3.0 * eps / T))
        packing_a3 = 6.0 * 0.74 / math.pi / float(np.sum(z * m * d**3))
        return packing_a3 / _saft_assoc._MOL_TO_A3 * 0.999


class _PCSaftPolarKernel(_PCSaftAssocKernel):
    """Hand-rolled PC-SAFT + Gross & Vrabec dipolar term (row ``pc_saft_polar``).

    Physical part identical to the association kernel (the teqp-pinned
    PCSaftPhysical term); the association slot is replaced by the shared
    PCSaftDipolar term (Gross & Vrabec 2006), so pressure, fugacity
    coefficients, enthalpy and max density reuse the association kernel's
    machinery unchanged. No association contribution: the bound slate
    (acetone, DME) is non-associating.
    """

    def __init__(self, name: str, params: list[dict[str, Any]]) -> None:
        self.name = name
        self.params = params
        self._phys = _saft_assoc.PCSaftPhysical(params)
        self._dip = _saft_assoc.PCSaftDipolar(params)

    def _alpha_r_derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """alpha_r and its exact rho / composition derivatives (chain + disp + dipolar)."""
        a_phys, dadrho_phys, dz_phys = self._phys.derivs(T, rho, z)
        alpha_d, dadrho_d, dz_d = self._dip.derivs(T, rho, z)
        return a_phys + alpha_d, dadrho_phys + dadrho_d, dz_phys + dz_d


def _polymer_pcsaft_params() -> dict[str, Any]:
    """The cited polymer PC-SAFT parameter file, loaded once (spec T-10)."""
    path = Path(__file__).resolve().parents[3] / "data" / "thermo_params" / "special" / "polymer.yaml"
    raw = yaml.safe_load(path.read_text())
    assert isinstance(raw, dict), f"{path}: malformed parameter file"
    block = raw.get("polymer_pc_saft") or {}
    assert isinstance(block, dict) and block, f"{path}: missing polymer_pc_saft block"
    return block


@lru_cache(maxsize=64)
def _build_kernel(kind: str, cids: tuple[str, ...]) -> _Kernel:
    """Build (and cache) the kernel for one model kind over one sorted support."""
    if kind == "pc_saft":
        block = _require_params("pc_saft", cids)
        coeffs = [
            {
                "name": cid,
                "m": float(block[cid]["m"]),
                "sigma_Angstrom": float(block[cid]["sigma_Angstrom"]),
                "epsilon_over_k": float(block[cid]["epsilon_over_k"]),
                "BibTeXKey": "Gross-IECR-2001",
            }
            for cid in cids
        ]
        return _TeqpKernel(kind, _teqp().make_model({"kind": "PCSAFT", "model": {"coeffs": coeffs}}))
    if kind == "saft_vr_mie":
        block = _require_params("saft_vr_mie", cids)
        coeffs = [
            {
                "name": cid,
                "m": float(block[cid]["m"]),
                "sigma_Angstrom": float(block[cid]["sigma_Angstrom"]),
                "epsilon_over_k": float(block[cid]["epsilon_over_k"]),
                "lambda_r": float(block[cid]["lambda_r"]),
                "lambda_a": float(block[cid]["lambda_a"]),
                "BibTeXKey": "Lafitte-JCP-2013",
            }
            for cid in cids
        ]
        return _TeqpKernel(kind, _teqp().make_model({"kind": "SAFT-VR-Mie", "model": {"coeffs": coeffs}}))
    if kind == "soft_saft":
        block = _require_params("soft_saft", cids)
        params = [block[cid] for cid in cids]
        model = _teqp().make_model(
            {
                "kind": "SoftSAFT",
                "model": {
                    "m": [float(p["m"]) for p in params],
                    "sigma / m": [float(p["sigma_Angstrom"]) * 1e-10 for p in params],
                    "epsilon/kB / K": [float(p["epsilon_over_k"]) for p in params],
                },
            }
        )
        return _SoftSaftKernel(kind, model, params)
    if kind == "gerg2008_teqp":
        # teqp's exact GERG-2008 kind (Kunz & Wagner 2012 pure-fluid and mixture
        # residual parts), not the multi-fluid builder over the CoolProp fluid
        # library: GERG-2008's own pure-fluid equations differ from the reference
        # EOSs that library carries.
        block = _require_params(kind, cids, subkey="aliases")
        names = [str(block[cid]) for cid in cids]
        # Pure-VLE seeds: teqp's ancillaries of the same fluid's library equation
        # (the multifluid_pure alias table; GERG2008resid carries none).
        seed = None
        if len(cids) == 1:
            library = _require_params("multifluid_pure", cids, subkey="aliases")
            datapath = _teqp().get_datapath()
            seed = _teqp().build_multifluid_model([str(library[cids[0]])], datapath)
        model = _teqp().make_model({"kind": "GERG2008resid", "model": {"names": names}})
        return _MultifluidKernel(kind, model, seed_model=seed)
    if kind in ("multifluid", "multifluid_pure"):
        # Kind-keyed: the mixture row excludes H2O (no water interaction data in
        # teqp's bundled pair library); the pure row keeps it.
        block = _require_params(kind, cids, subkey="aliases")
        teqp = _teqp()
        datapath = teqp.get_datapath()
        model = teqp.build_multifluid_model(
            [str(block[cid]) for cid in cids],
            datapath,
            datapath + "/dev/mixtures/mixture_binary_pairs.json",
            {},
            datapath + "/dev/mixtures/mixture_departure_functions.json",
        )
        return _MultifluidKernel(kind, model)
    if kind == "cpa_srk":
        block = _require_params("cpa_srk", cids)
        # Tc from the resolved component records (the same constants every other
        # package uses); the Kontogeorgis table carries the a0/b/c1 fit only.
        tcs = [float(resolve(cid).Tc) for cid in cids]
        return _CpaKernel(kind, [block[cid] for cid in cids], tcs)
    if kind == "cpa_pr":
        block = _require_params("cpa_pr", cids)
        # Tc from the resolved component records (the cpa_srk pattern); the paper's
        # Table 6 carries the a0/b/c1 fit and the association parameters only.
        # The paper's own Tc (Table 6), not the databank's: a0/c1 were fitted with it.
        tcs = [float(block[cid]["Tc"]) for cid in cids]
        params = [block[cid] | {"name": cid} for cid in cids]
        kij_table = block.get("binary_kij") or {}
        return _CpaPrKernel(kind, params, tcs, kij_table)
    if kind == "pc_saft_assoc":
        block = _require_params("pc_saft_assoc", cids)
        params = [block[cid] | {"name": cid} for cid in cids]
        return _PCSaftAssocKernel(kind, params)
    if kind == "pc_saft_polar":
        block = _require_params("pc_saft_polar", cids)
        params = [block[cid] | {"name": cid} for cid in cids]
        return _PCSaftPolarKernel(kind, params)
    if kind == "polymer_pc_saft":
        # Polymer PC-SAFT (spec T-10): same PCSAFT engine as "pc_saft", but the
        # parameters live in the special-family file (polymer.yaml), keyed by
        # component id, so unsupported components refuse by name from there.
        block = _polymer_pcsaft_params()
        unsupported = [cid for cid in cids if cid not in block]
        if unsupported:
            raise SaftParameterError(
                f"no verified polymer_pc_saft parameters for {unsupported}; supported: "
                f"{sorted(block)} (unsupported components are refused, never treated as ideal)"
            )
        coeffs = [
            {
                "name": cid,
                "m": float(block[cid]["m"]),
                "sigma_Angstrom": float(block[cid]["sigma_Angstrom"]),
                "epsilon_over_k": float(block[cid]["epsilon_over_k"]),
                "BibTeXKey": "Gross-IECR-2001",
            }
            for cid in cids
        ]
        return _TeqpKernel(kind, _teqp().make_model({"kind": "PCSAFT", "model": {"coeffs": coeffs}}))
    raise NotImplementedError(f"no SAFT kernel for model kind {kind!r}")


def _vapour_like(P: float, T: float, rho_light: float, rho_heavy: float) -> bool:
    """Whether the lightest density root is a vapour that may vote against ``rho_heavy``.

    Z > 0.5 (the pure-psat test), or, near a mixture critical point, Z down to
    _SAT_VAPOUR_Z_MIN when the pair is clearly split (density ratio above
    _SAT_NEAR_CRIT_SPLIT). Measured: the SAFT-VR-Mie C1/CO2 incipient bubble vapour at
    298.142 K, 7.0 MPa is a real vapour at Z ~ 0.49 against a liquid 2.9x denser,
    while dense supercritical roots (Z 0.3-0.5 against a liquid ~1.2x denser on the
    GERG-2008 C1/N2 dew walk), unstable middle-branch roots (Z ~ 0.09 on the C1/N2
    130 K isotherm) and the in-dome artefact roots of the multi-fluid reference
    equations (GERG-2008 90/10 C1/N2 at 150 K, 3 MPa: Z = 0.236 at 10205 mol/m3,
    against the 21936 mol/m3 liquid, with the LOWER Gibbs energy) must not.
    """
    z_light = P / (rho_light * R_GAS * T)
    return z_light > 0.5 or (z_light > _SAT_VAPOUR_Z_MIN and rho_heavy / rho_light > _SAT_NEAR_CRIT_SPLIT)


class TeqpPackage(ThermoSurfaceMixin):
    """Shared SAFT-family surface over the teqp / CPA kernels (spec T-07).

    Subclasses pin the catalogue model kind as ``model_kind``. The flash loop,
    saturation solvers, and property layer are implemented here (the mixin's
    ``thermo``-library flasher helpers do not apply to these engines); reused
    from the mixin: the per-instance property cache.
    """

    model_kind: str

    def __init__(self) -> None:
        super().__init__()
        self._psat_cache: dict[tuple[str, tuple[str, ...], float], tuple[float]] = {}

    def _validate_kind(self) -> None:
        """Refusal rows raise here at FIRST USE, naming the missing engine.

        Construction never touches the optional backend: every catalogue row
        must instantiate through the registry without the extra installed (the
        CoolProp and virial rows set the pattern), so the API can list it, the
        contract test can type it and the refusal reason surfaces at the first
        property call via ``_kernel`` - the single entry to the engines.

        pc_saft_polar refuses per-component from _require_params inside
        _build_kernel (the pc_saft_assoc pattern), so it has no kind-level
        branch here. No row refuses at kind level today; the hook stays so a
        future engine-less row refuses at first use rather than at load.
        """

    # -- kernel plumbing -------------------------------------------------------

    def _ids(self, z: dict[str, float]) -> tuple[str, ...]:
        ids = _state.support_ids(z)
        if self.model_kind == "multifluid_pure" and len(ids) != 1:
            raise SaftParameterError(f"multifluid_pure flashes pure fluids only; got {sorted(ids)}")
        return ids

    def _kernel(self, z: dict[str, float]) -> tuple[_Kernel, tuple[str, ...], _IdealGasPart]:
        # The one entry to the engines: refusal rows refuse here, and a missing
        # teqp extra surfaces here as SaftDependencyMissing (from _build_kernel).
        self._validate_kind()
        ids = self._ids(z)
        return _build_kernel(self.model_kind, ids), ids, _IdealGasPart(ids)

    @staticmethod
    def _zvec(z: dict[str, float], ids: tuple[str, ...]) -> np.ndarray:
        return np.array([float(z[cid]) for cid in ids])

    # -- root picking and labelling ---------------------------------------------

    def _root_for_kind(self, kernel: _Kernel, z: np.ndarray, T: float, P: float, kind: PhaseKind) -> float:
        """Density root matching the requested phase kind (SaturationError when absent)."""
        roots = kernel.roots(T, P, z)
        if not roots:
            raise SaturationError(f"no {kind.value} density root at T={T} K, P={P:.6g} Pa")
        return roots[0] if kind == PhaseKind.VAPOR else roots[-1]

    def _liquid_kind(self, ids: tuple[str, ...], z: np.ndarray) -> PhaseKind:
        """Water-rich liquids are AQUEOUS (the same 0.5 rule the cubic packages use)."""
        if "H2O" in ids and z[ids.index("H2O")] > _state.AQUEOUS_WATER_FRACTION:
            return PhaseKind.AQUEOUS
        return PhaseKind.HC_LIQUID

    # -- phase properties -------------------------------------------------------

    def _s_ig_mix(self, ig: _IdealGasPart, z: np.ndarray, T: float, P: float) -> float:
        """Ideal-gas mixture entropy at (T, P): correlation integrals + mixing + pressure."""
        s = float(sum(x * ig.entropy_ref(i, T) for i, x in enumerate(z)))
        s -= R_GAS * float(sum(x * math.log(max(x, 1e-300)) for x in z))
        s -= R_GAS * math.log(P / P_REF)
        return s

    def _h_at(
        self, kernel: _Kernel, ig: _IdealGasPart, z: np.ndarray, T: float, P: float, kind: PhaseKind
    ) -> float:
        """Phase enthalpy (J/mol) at (T, P), re-solving the density root for T."""
        rho = self._root_for_kind(kernel, z, T, P, kind)
        h_res = kernel.h_res_rt(T, rho, z) * R_GAS * T
        h_ig = float(sum(x * ig.enthalpy(i, T) for i, x in enumerate(z)))
        return h_res + h_ig

    def _cp_at(
        self, kernel: _Kernel, ig: _IdealGasPart, z: np.ndarray, T: float, P: float, kind: PhaseKind
    ) -> float:
        """cp as the central difference of the phase enthalpy at fixed P (dT = 1 K)."""
        return (
            self._h_at(kernel, ig, z, T + 0.5, P, kind) - self._h_at(kernel, ig, z, T - 0.5, P, kind)
        ) / 1.0

    def _phase_props_at(
        self,
        kernel: _Kernel,
        ig: _IdealGasPart,
        ids: tuple[str, ...],
        z: np.ndarray,
        T: float,
        rho: float,
        P: float,
        kind: PhaseKind,
    ) -> PhaseProps:
        """PhaseProps at a known density root (no re-scan)."""
        lnphi = kernel.ln_phi(T, rho, z)
        mw = float(sum(x * mw for x, mw in zip(z, ig.mws, strict=True)))
        h_res = kernel.h_res_rt(T, rho, z) * R_GAS * T
        g_res = float(np.dot(z, lnphi)) * R_GAS * T
        s_res = (h_res - g_res) / T
        h_ig = float(sum(x * ig.enthalpy(i, T) for i, x in enumerate(z)))
        s_ig = self._s_ig_mix(ig, z, T, P)
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition={cid: float(x) for cid, x in zip(ids, z, strict=True)},
            molecular_weight=mw,
            density=rho * mw / 1000.0,
            enthalpy=h_res + h_ig,
            entropy=s_res + s_ig,
            cp=self._cp_at(kernel, ig, z, T, P, kind),
            gibbs=g_res + h_ig - T * (s_res + s_ig),
            z_factor=P / (rho * R_GAS * T),
            ln_phi={cid: float(v) for cid, v in zip(ids, lnphi, strict=True)},
        )

    def _phase_props_cached(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        key = ("pp", str(kind), *_state.cache_key(composition, T, P))
        return cast(
            PhaseProps, self._cached(key, lambda: self._phase_props_uncached(composition, T, P, kind))
        )

    def _phase_props_uncached(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PhaseProps:
        kernel, ids, ig = self._kernel(composition)
        z = self._zvec(composition, ids)
        phase = PhaseKind(kind)
        rho = self._root_for_kind(kernel, z, T, P, phase)
        return self._phase_props_at(kernel, ig, ids, z, T, rho, P, phase)

    # -- stream assembly ---------------------------------------------------------

    def _single_phase_at(
        self,
        kernel: _Kernel,
        ig: _IdealGasPart,
        ids: tuple[str, ...],
        feed: np.ndarray,
        z: dict[str, float],
        T: float,
        P: float,
        molar_flow: float,
        kind: PhaseKind,
    ) -> StreamState:
        rho = self._root_for_kind(kernel, feed, T, P, kind)
        props = self._phase_props_at(kernel, ig, ids, feed, T, rho, P, kind)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=1.0 if kind == PhaseKind.VAPOR else 0.0,
            enthalpy=props.enthalpy,
            entropy=props.entropy,
            phases=[
                Phase(
                    kind=kind,
                    mole_fraction=1.0,
                    composition=props.composition,
                    density=props.density,
                    molecular_weight=props.molecular_weight,
                    enthalpy=props.enthalpy,
                    entropy=props.entropy,
                    cp=props.cp,
                    ln_phi=props.ln_phi,
                )
            ],
        )

    def _two_phase_at(
        self,
        kernel: _Kernel,
        ig: _IdealGasPart,
        ids: tuple[str, ...],
        feed: dict[str, float],
        T: float,
        P: float,
        molar_flow: float,
        rho_v: float,
        rho_l: float,
        y: np.ndarray,
        x: np.ndarray,
        beta: float,
    ) -> StreamState:
        """StreamState from a converged VLE split (beta = molar vapour fraction)."""
        pv = self._phase_props_at(kernel, ig, ids, y, T, rho_v, P, PhaseKind.VAPOR)
        kind_l = self._liquid_kind(ids, x)
        pl = self._phase_props_at(kernel, ig, ids, x, T, rho_l, P, kind_l)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(feed),
            vapor_fraction=beta,
            enthalpy=beta * pv.enthalpy + (1.0 - beta) * pl.enthalpy,
            entropy=beta * pv.entropy + (1.0 - beta) * pl.entropy,
            phases=[
                Phase(
                    kind=PhaseKind.VAPOR,
                    mole_fraction=beta,
                    composition=pv.composition,
                    density=pv.density,
                    molecular_weight=pv.molecular_weight,
                    enthalpy=pv.enthalpy,
                    entropy=pv.entropy,
                    cp=pv.cp,
                    ln_phi=pv.ln_phi,
                ),
                Phase(
                    kind=kind_l,
                    mole_fraction=1.0 - beta,
                    composition=pl.composition,
                    density=pl.density,
                    molecular_weight=pl.molecular_weight,
                    enthalpy=pl.enthalpy,
                    entropy=pl.entropy,
                    cp=pl.cp,
                    ln_phi=pl.ln_phi,
                ),
            ],
        )

    # -- pure-fluid saturation ----------------------------------------------------

    def _pure_psat_kernel(self, kernel: _Kernel, T: float, seed: float) -> float | None:
        """Model-intrinsic pure Psat: bracket lnphi_l = lnphi_v in P by bisection.

        Returns None when the fluid is single-phase at every pressure (T at/above
        Tc). Below Psat a single root is vapour-like (Z ~ 1); above it, liquid-like
        (Z << 1) — the Z > 0.5 test classifies the bracket side. With several
        roots the comparison is lnphi of the outermost (vapour-like, liquid-like)
        roots — but only once the lowest root really is on the vapour branch
        (Z > 0.5): above the vapour spinodal the lowest root is the unstable
        middle branch, whose fugacity must not vote (the liquid is stable there).
        """
        native, exact = kernel.pure_saturation_pressure(T)
        if native:
            return exact
        z = np.array([1.0])
        cap = kernel.max_density(T, z)
        p_max = kernel.pressure(T, cap * 0.999, z)
        p_min = max(R_GAS * T * cap * 1e-9, 1e-6)
        lo: float | None = None
        hi: float | None = None
        d_lo: float | None = None
        d_hi: float | None = None
        p = min(max(seed, p_min * 1.001), p_max * 0.999)
        for _ in range(90):
            roots = kernel.roots(T, p, z)
            if not roots:
                lo = p  # lighter than any root: below the saturation line
            elif len(roots) < 2:
                if kernel.pressure(T, roots[0], z) / (roots[0] * R_GAS * T) > 0.5:
                    lo = p
                else:
                    hi = p
            elif p / (roots[0] * R_GAS * T) < 0.5:
                hi = p  # no vapour-like root: above the vapour spinodal
            else:
                d = float(kernel.ln_phi(T, roots[-1], z)[0]) - float(kernel.ln_phi(T, roots[0], z)[0])
                if d > 0.0:
                    lo, d_lo = p, d
                    if d_hi is not None:
                        d_hi *= 0.5  # Illinois inflation of the retained side
                elif d < 0.0:
                    hi, d_hi = p, d
                    if d_lo is not None:
                        d_lo *= 0.5
                else:
                    return p
            if lo is not None and hi is not None:
                # Regula falsi on lnphi_l - lnphi_v (monotone in P) in log-P space,
                # falling back to the geometric midpoint until both bracket ends carry
                # a fugacity difference; each iteration costs a density-root scan, so
                # the evaluation count is the runtime.
                if d_lo is not None and d_hi is not None and d_lo != d_hi:
                    x_lo, x_hi = math.log(lo), math.log(hi)
                    x = (d_lo * x_hi - d_hi * x_lo) / (d_lo - d_hi)
                    mid = min(max(math.exp(x), lo * (1.0 + 1e-15)), hi * (1.0 - 1e-15))
                else:
                    mid = math.sqrt(lo * hi)
                if mid <= lo * (1.0 + 1e-8):
                    return mid
                p = mid
            elif lo is not None:
                if p >= p_max:
                    return None  # never two roots up to the packing limit: above Tc
                p = min(p * 4.0, p_max * 1.001)
            else:
                if p <= p_min:
                    return None
                p = max(p / 4.0, p_min * 0.999)
        return None

    def _psat_cached(self, ids: tuple[str, ...], T: float) -> float:
        """Pure Psat of a single-component feed, instance-cached (raises above Tc)."""
        key = (self.model_kind, ids, round(T, 9))
        hit = self._psat_cache.get(key)
        if hit is not None:
            return hit[0]
        kernel, _, _ = self._kernel({ids[0]: 1.0})
        # Wilson seed: measured within 2.5x of the exact psat for these fluids, so the
        # bracket search starts near the answer instead of at a geometric midpoint
        # spanning ~15 decades of pressure.
        seed = self._wilson_p({ids[0]: 1.0}, ids, T, bubble=True)
        got = self._pure_psat_kernel(kernel, T, seed=seed)
        if got is None:
            raise SaturationError(f"no vapour pressure for {ids[0]!r} at T={T} K (at/above Tc)")
        self._psat_cache[key] = (got,)
        return got

    def _pure_T_of_psat(self, ids: tuple[str, ...], P: float) -> float:
        """Invert the model Psat(T) = P by bisection (monotone; None above Tc)."""
        kernel, _, _ = self._kernel({ids[0]: 1.0})

        def f(t: float) -> float | None:
            seed = self._wilson_p({ids[0]: 1.0}, ids, t, bubble=True)
            got = self._pure_psat_kernel(kernel, t, seed=seed)
            return None if got is None else got - P

        constants, _ = _ig_constants(ids)
        # Scale the bracket floor with the fluid: a fixed 30 K floor mis-evaluates
        # heavy associating components (methanol returned no usable Psat there).
        # Walk down only if the target P sits below the floor's saturation pressure.
        lo = max(30.0, 0.3 * float(constants.Tcs[0]))
        flo = f(lo)
        while (flo is None or flo >= 0.0) and lo > 30.0:
            lo = max(30.0, lo / 4.0)
            flo = f(lo)
        assert flo is not None and flo < 0.0, "Psat at the 30 K floor should sit below any reachable target P"
        hi: float | None = None
        t = max(150.0, lo * 2.0)
        while t <= 2000.0:
            got = f(t)
            if got is None:
                hi = t  # above Tc: the root lies below
                break
            if got > 0.0:
                hi = t
                break
            lo, flo = t, got
            t *= 2.0
        if hi is None:
            raise SaturationError(f"no saturation T for P={P:.6g} Pa within [30, 2000] K")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            fm = f(mid)
            if fm is None or hi - lo < 1e-11 * mid:
                hi = mid
                break
            if flo * fm <= 0.0:
                hi = mid
            else:
                lo, flo = mid, fm
        return 0.5 * (lo + hi)

    # -- flashes -------------------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: pure feeds short-circuit on the model Psat; mixtures use root scan + RR."""
        key = ("pt", *_state.cache_key(z, T, P), float(molar_flow))
        return cast(StreamState, self._cached(key, lambda: self._flash_pt_uncached(z, T, P, molar_flow)))

    def _flash_pt_uncached(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        ids = self._ids(z)
        kernel, _, ig = self._kernel(z)
        feed = self._zvec(z, ids)
        psat: float | None = None
        if len(ids) == 1:
            # Cheap-first classification: a single physical density root is unambiguous
            # (one phase), so the expensive pure-saturation solve is only needed in the
            # two-root region near saturation. The PH/PS inversion bisections evaluate
            # ~30 trial temperatures; a full psat per trial dominates their runtime.
            probe_roots = kernel.roots(T, P, feed)
            if len(probe_roots) == 1:
                z_factor = P / (probe_roots[0] * R_GAS * T)
                kind = PhaseKind.VAPOR if z_factor > 0.5 else self._liquid_kind(ids, feed)
                return self._single_phase_at(kernel, ig, ids, feed, z, T, P, molar_flow, kind)
            # Far from saturation the Wilson estimate classifies the state without a full
            # pure-saturation solve: the PH/PS inversions evaluate ~15-30 trial
            # temperatures and an exact psat per trial dominates their runtime. Measured
            # against the exact psat (H2O and MeOH, 240-480 K) the estimate never
            # misses by more than 2.54x, so a 5x band keeps classification correct with
            # headroom while confining the exact solve to states near saturation.
            w_est = self._wilson_p(z, ids, T, bubble=True)
            if P > 5.0 * w_est:
                return self._single_phase_at(
                    kernel, ig, ids, feed, z, T, P, molar_flow, self._liquid_kind(ids, feed)
                )
            if P < 0.2 * w_est:
                return self._single_phase_at(kernel, ig, ids, feed, z, T, P, molar_flow, PhaseKind.VAPOR)
            # Best effort: outside the model's two-phase window (below the triple-point
            # region or at/above Tc) no vapour pressure exists and the PT state is still
            # classifiable on density roots - e.g. the supercritical dhdT_cp round trip.
            try:
                psat = self._psat_cached(ids, T)
            except SaturationError:
                psat = None
        if psat is not None:
            if P < psat * (1.0 - 1e-12):
                return self._single_phase_at(kernel, ig, ids, feed, z, T, P, molar_flow, PhaseKind.VAPOR)
            if P > psat * (1.0 + 1e-12):
                return self._single_phase_at(
                    kernel, ig, ids, feed, z, T, P, molar_flow, self._liquid_kind(ids, feed)
                )
            roots = kernel.roots(T, psat, feed)
            if len(roots) < 2:
                raise SaturationError(f"no two-phase roots at T={T} K, P={psat:.6g} Pa")
            return self._two_phase_at(
                kernel, ig, ids, z, T, psat, molar_flow, roots[0], roots[-1], feed, feed, 0.5
            )
        roots = kernel.roots(T, P, feed)
        if len(roots) < 2:
            if not roots:
                raise SaturationError(f"no density root at T={T} K, P={P:.6g} Pa")
            # Same Z > 0.5 rule as the pure-feed path above: Z < 1 alone is not a
            # vapour test (a compressed liquid's single root has Z ~ 0.1-0.3).
            z_factor = P / (roots[0] * R_GAS * T)
            kind = PhaseKind.VAPOR if z_factor > 0.5 else self._liquid_kind(ids, feed)
            return self._single_phase_at(kernel, ig, ids, feed, z, T, P, molar_flow, kind)
        rho_v, rho_l = roots[0], roots[-1]
        if not _vapour_like(P, T, rho_v, rho_l):
            # The light root is no vapour (an in-dome artefact or a dense
            # supercritical root): the feed is one dense phase.
            return self._single_phase_at(
                kernel, ig, ids, feed, z, T, P, molar_flow, self._liquid_kind(ids, feed)
            )
        x = feed.copy()
        y = feed.copy()
        beta = 0.5
        for _ in range(400):
            ln_k = kernel.ln_phi(T, rho_l, x) - kernel.ln_phi(T, rho_v, y)
            if not np.all(np.isfinite(ln_k)) or float(np.max(np.abs(ln_k))) > _LN_K_MAX:
                # Successive substitution walked onto a non-physical root pair (the
                # overflow/NaN RuntimeWarnings of the multi-fluid L0 sweeps): no
                # equilibrium K-values exist along this path.
                raise SaturationError(f"PT flash: non-physical K-values at T={T} K, P={P:.6g} Pa")
            k = np.exp(ln_k)
            beta = self._rachford_rice(k, feed)
            x_new = feed / (1.0 + beta * (k - 1.0))
            x_new /= x_new.sum()
            y_new = k * x_new
            y_new /= y_new.sum()
            if np.max(np.abs(x_new - x)) < 1e-11 and np.max(np.abs(y_new - y)) < 1e-11:
                x, y = x_new, y_new
                break
            x, y = 0.7 * x + 0.3 * x_new, 0.7 * y + 0.3 * y_new
            roots_x = kernel.roots(T, P, x)
            roots_y = kernel.roots(T, P, y)
            if not roots_x or not roots_y:
                raise SaturationError(f"VLE roots vanished during RR at T={T} K, P={P:.6g} Pa")
            rho_l, rho_v = roots_x[-1], roots_y[0]
            if not _vapour_like(P, T, rho_v, rho_l):
                raise SaturationError(f"PT flash: vapour root lost during RR at T={T} K, P={P:.6g} Pa")
        # Collapse degenerate splits: a converged beta of 0 or 1 is a single phase
        # (the all-condensed / all-vapour end of the two-phase window), and carrying
        # a zero-fraction phase breaks the single-phase-limit L0 checks.
        if beta <= 1e-12:
            return self._single_phase_at(
                kernel, ig, ids, feed, z, T, P, molar_flow, self._liquid_kind(ids, x)
            )
        if beta >= 1.0 - 1e-12:
            return self._single_phase_at(kernel, ig, ids, feed, z, T, P, molar_flow, PhaseKind.VAPOR)
        return self._two_phase_at(kernel, ig, ids, z, T, P, molar_flow, rho_v, rho_l, y, x, beta)

    @staticmethod
    def _rachford_rice(k: np.ndarray, z: np.ndarray) -> float:
        """Vapour fraction from K and feed z by bisection (monotone on [0, 1])."""

        def f(b: float) -> float:
            # 1 + b(K - 1) written as (1 - b) + bK: at b = 1 with K < 1e-16 the
            # textbook form cancels to 0 (divide-by-zero RuntimeWarnings, measured on
            # the multifluid L0 sweep); this form stays K > 0 there.
            return float(np.sum(z * (k - 1.0) / ((1.0 - b) + b * k)))

        if f(0.0) <= 0.0:
            return 0.0
        if f(1.0) >= 0.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(120):
            mid = 0.5 * (lo + hi)
            if f(lo) * f(mid) <= 0.0:
                hi = mid
            else:
                lo = mid
        return 0.5 * (lo + hi)

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: T from a bracketed solve on the PT enthalpy at fixed P."""
        return self._solve_T(z, P, molar_flow, H, lambda s: s.enthalpy, "enthalpy")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: T from a bracketed solve on the PT entropy at fixed P."""
        return self._solve_T(z, P, molar_flow, S, lambda s: s.entropy, "entropy")

    def _solve_T(
        self,
        z: dict[str, float],
        P: float,
        molar_flow: float,
        target: float,
        pick: Callable[[StreamState], float],
        prop: str,
    ) -> StreamState:
        def f(t: float) -> float:
            try:
                return pick(self.flash_pt(z, t, P, molar_flow)) - target
            except (SaturationError, _NonPhysicalZ):
                # The trial sits outside the classifiable window (all-condensed cold
                # end, all-vapour hot end, or a degenerate RR region): enthalpy and
                # entropy are monotone in T, so the target lies toward the bracket
                # interior and the residual points that way.
                return -1.0 if t < 0.5 * (lo + hi) else 1.0

        # Scale the floor with the fluid: a fixed 40 K floor evaluates associating
        # kernels below their physical window (water at 40 K: the association term is
        # meaningless and the radial distribution function goes negative - observed as
        # a math domain error in the round-trip L0 check).
        constants, _ = _ig_constants(self._ids(z))
        lo, hi = max(40.0, 0.35 * min(float(tc) for tc in constants.Tcs)), 400.0
        flo = f(lo)
        fhi = f(hi)
        for _ in range(40):
            if hi - lo < 1e-6:
                break
            if flo * fhi <= 0.0:
                break
            # Directional expansion: extend only toward the side the target lies on
            # (both residuals negative means the target is above hi). Extending both
            # ends blindly evaluated associating and multifluid kernels at tens of
            # kelvin, far below any physically meaningful state.
            if flo < 0.0:
                if hi >= 3000.0:
                    break
                hi = min(hi * 2.0, 3000.0)
                fhi = f(hi)
            else:
                if lo <= 2.0:
                    break
                lo = max(lo * 0.5, 2.0)
                flo = f(lo)
        else:
            raise SaturationError(
                f"PH/PS flash: no T in [2, 3000] K reaches {prop}={target:.6g} at P={P:.6g} Pa"
            )
        # Illinois regula falsi: H and S are smooth and monotone in T within a branch,
        # so the secant step converges superlinearly (~8-12 evaluations) where plain
        # bisection needed ~36; each evaluation costs a full PT flash with a fresh
        # pure-saturation solve, so the evaluation count is the runtime.
        for _ in range(60):
            if hi - lo <= 1e-6 * hi:
                break
            slope = (fhi - flo) / (hi - lo)
            mid = hi - fhi / slope if slope != 0.0 else 0.5 * (lo + hi)
            if not lo < mid < hi:
                mid = 0.5 * (lo + hi)
            fm = f(mid)
            if fm == 0.0:
                return self.flash_pt(z, mid, P, molar_flow)
            if flo * fm < 0.0:
                hi, fhi = mid, fm
                flo *= 0.5  # inflate the retained endpoint
            else:
                lo, flo = mid, fm
                fhi *= 0.5
        return self.flash_pt(z, 0.5 * (lo + hi), P, molar_flow)

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: pressure on the vapour-fraction isotherm between dew and bubble."""
        return self._solve_vf(z, T, vf, molar_flow, on_T=True)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: temperature on the vapour-fraction isobar between dew and bubble."""
        return self._solve_vf(z, P, vf, molar_flow, on_T=False)

    def _solve_vf(
        self, z: dict[str, float], anchor: float, vf: float, molar_flow: float, *, on_T: bool
    ) -> StreamState:
        ids = self._ids(z)
        if len(ids) == 1:
            # Pure fluid: the two-phase state exists only on the saturation line.
            if on_T:
                psat = self._psat_cached(ids, anchor)
                T = anchor
            else:
                T = self._pure_T_of_psat(ids, anchor)
                psat = anchor
            kernel, _, ig = self._kernel(z)
            feed = np.array([1.0])
            roots = kernel.roots(T, psat, feed)
            if len(roots) < 2:
                raise SaturationError(f"no two-phase roots at T={T} K, P={psat:.6g} Pa")
            if vf <= 0.0:
                return self._single_phase_at(
                    kernel, ig, ids, feed, z, T, psat, molar_flow, self._liquid_kind(ids, feed)
                )
            if vf >= 1.0:
                return self._single_phase_at(kernel, ig, ids, feed, z, T, psat, molar_flow, PhaseKind.VAPOR)
            return self._two_phase_at(
                kernel, ig, ids, z, T, psat, molar_flow, roots[0], roots[-1], feed, feed, vf
            )
        # Mixtures: vapour fraction rises monotonically from 0 at the bubble point
        # to 1 at the dew point; bisect the anchor between them.
        if on_T:
            lo, hi = self._dew_p_of_t(z, ids, anchor)[0], self._bubble_p_of_t(z, ids, anchor)[0]

            def g(p: float) -> float:
                return self.flash_pt(z, anchor, p, molar_flow).vapor_fraction - vf

            def state_at(p: float) -> StreamState:
                return self.flash_pt(z, anchor, p, molar_flow)
        else:
            lo = self._sat_t_of_p(z, ids, anchor, bubble=False)[0]  # dew T (low)
            hi = self._sat_t_of_p(z, ids, anchor, bubble=True)[0]  # bubble T (high)

            def g(p: float) -> float:
                return self.flash_pt(z, p, anchor, molar_flow).vapor_fraction - vf

            def state_at(p: float) -> StreamState:
                return self.flash_pt(z, p, anchor, molar_flow)

        flo = g(lo)
        fhi = g(hi)
        if flo * fhi > 0.0:
            raise SaturationError(f"TVF/PVF: vapour fraction {vf} unreachable at anchor={anchor:.6g}")
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            fm = g(mid)
            if fm == 0.0 or hi - lo <= 1e-10 * max(abs(mid), 1.0):
                return state_at(mid)
            if flo * fm < 0.0:
                hi, fhi = mid, fm
            else:
                lo, flo = mid, fm
        return state_at(0.5 * (lo + hi))

    # -- saturation points -----------------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point; exactly one of T (K) and P (Pa) given."""
        key = ("bub", *_state.cache_key(z, T or 0.0, P or 0.0), T is not None, P is not None)
        return cast(SaturationPoint, self._cached(key, lambda: self._sat_point(z, T=T, P=P, bubble=True)))

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point; exactly one of T (K) and P (Pa) given."""
        key = ("dew", *_state.cache_key(z, T or 0.0, P or 0.0), T is not None, P is not None)
        return cast(SaturationPoint, self._cached(key, lambda: self._sat_point(z, T=T, P=P, bubble=False)))

    def _sat_point(
        self, z: dict[str, float], *, T: float | None, P: float | None, bubble: bool
    ) -> SaturationPoint:
        ids = self._ids(z)
        kind = "bubble" if bubble else "dew"
        if len(ids) == 1:
            if T is not None:
                return SaturationPoint(
                    T=T, P=self._psat_cached(ids, T), kind=kind, incipient_composition={ids[0]: 1.0}
                )
            assert P is not None, "exactly one of T and P is given"
            t = self._pure_T_of_psat(ids, P)
            return SaturationPoint(T=t, P=P, kind=kind, incipient_composition={ids[0]: 1.0})
        if T is not None:
            p, inc = self._bubble_p_of_t(z, ids, T) if bubble else self._dew_p_of_t(z, ids, T)
            return SaturationPoint(T=T, P=p, kind=kind, incipient_composition=inc)
        assert P is not None, "exactly one of T and P is given"
        t, inc = self._sat_t_of_p(z, ids, P, bubble=bubble)
        return SaturationPoint(T=t, P=P, kind=kind, incipient_composition=inc)

    def _wilson_p(self, z: dict[str, float], ids: tuple[str, ...], T: float, *, bubble: bool) -> float:
        """Wilson K-value pressure estimate anchoring the saturation iterations.

        Bubble: sum_i z_i K_i = 1 with K_i = (Pc_i/P) exp(A_i) gives P = sum z_i Pc_i e^{A_i};
        dew: sum_i z_i/K_i = 1 gives P = 1 / sum(z_i e^{-A_i}/Pc_i). Both are pressures.
        A_i uses the Wilson argument (1 - Tc_i/T): the reciprocal (1 - T/Tc_i) inverts the
        exponent sign for subcritical states and puts the seed orders of magnitude above
        the true saturation pressure (observed 615 MPa vs 31.5 kPa for MeOH/H2O at
        322.91 K), which steers the bracketed solve into the EOS's spurious high-pressure
        K-sum crossings.
        """
        constants, _ = _ig_constants(ids)
        if bubble:
            p = 0.0
            for i, cid in enumerate(ids):
                omega = float(constants.omegas[i]) if constants.omegas[i] is not None else 0.01
                a = 5.373 * (1.0 + omega) * (1.0 - float(constants.Tcs[i]) / T)
                p += float(z[cid]) * float(constants.Pcs[i]) * math.exp(a)
        else:
            inv = 0.0
            for i, cid in enumerate(ids):
                omega = float(constants.omegas[i]) if constants.omegas[i] is not None else 0.01
                a = 5.373 * (1.0 + omega) * (1.0 - float(constants.Tcs[i]) / T)
                inv += float(z[cid]) * math.exp(-a) / float(constants.Pcs[i])
            p = 1.0 / inv if inv > 0.0 else 1.0
        return max(p, 1e-3)

    def _bubble_p_of_t(
        self, z: dict[str, float], ids: tuple[str, ...], T: float
    ) -> tuple[float, dict[str, float]]:
        """Isothermal bubble point: bracketed solve of sum_i K_i x_i = 1 in ln P."""
        p, y = self._sat_ksum_solve(z, ids, T, bubble=True)
        return p, {cid: float(v) for cid, v in zip(ids, y, strict=True)}

    def _dew_p_of_t(
        self, z: dict[str, float], ids: tuple[str, ...], T: float
    ) -> tuple[float, dict[str, float]]:
        """Isothermal dew point: bracketed solve of sum_i y_i/K_i = 1 in ln P."""
        p, x = self._sat_ksum_solve(z, ids, T, bubble=False)
        return p, {cid: float(v) for cid, v in zip(ids, x, strict=True)}

    def _wilson_k(self, z: dict[str, float], ids: tuple[str, ...], T: float, p: float) -> np.ndarray:
        """Wilson K_i = (Pc_i/p)·exp(5.373(1+ω)(1−Tc_i/T)) in the component order of ``ids``.

        Wilson (1968); the argument is (1 - Tc/T), as in ``_wilson_p``. The reciprocal
        (1 - T/Tc) flips the exponent sign below Tc and seeded the MeOH/H2O
        101.325 kPa bubble-T solve at 179.68 K (no two-phase state there), crashing it.
        """
        constants, _ = _ig_constants(ids)
        out = np.empty(len(ids))
        for i in range(len(ids)):
            omega = float(constants.omegas[i]) if constants.omegas[i] is not None else 0.01
            a = 5.373 * (1.0 + omega) * (1.0 - float(constants.Tcs[i]) / T)
            out[i] = float(constants.Pcs[i]) * math.exp(a) / p
        return out

    def _sat_ksum_solve(
        self, z: dict[str, float], ids: tuple[str, ...], T: float, *, bubble: bool
    ) -> tuple[float, np.ndarray]:
        """K-sum saturation solve shared by the bubble and dew directions.

        Bubble: sum_i K_i x_i = 1; dew: sum_i y_i / K_i = 1, with K_i = phi_i^L / phi_i^V
        (Michelsen & Mollerup, "Thermodynamic Models: Fundamentals & Computational
        Aspects", 2nd ed. 2007, ch. 12). At every trial pressure the incipient-phase
        composition is converged first (successive substitution at fixed T, p) and only
        then does the K-sum classify the pressure: g = +/- ln(sum) is monotone in ln p
        (K_i ~ 1/p) only for the converged incipient phase. Classifying on a
        half-converged composition put one bracket end on the wrong side for good
        (measured: the GERG-2008 50/50 C1/N2 dew at 153.41 K closed on 2.799 MPa where
        the converged K-sum crosses at 2.658 MPa, the AGA8 check value). Once both
        bracket ends carry a converged g the pressure moves by Illinois regula falsi in
        ln p (the pure-psat solver's scheme), else by the geometric midpoint.
        The incipient phase starts from the feed (bubble) or the condensable part of
        the feed (dew), not from Wilson K-values: a dew liquid concentrates heavies so
        strongly that a vapour-like seed has no liquid density root near the seed
        pressure. States with missing or coincident density roots (outside the
        two-phase region) are classified to a bracket side by the compressibility of
        the single root, the same test the pure-psat hunt uses.
        """
        kernel, _, _ = self._kernel({cid: 1.0 for cid in ids})
        feed = self._zvec(z, ids)
        p = self._wilson_p(z, ids, T, bubble=bubble)
        if bubble:
            comp = feed.copy()  # incipient vapour: a vapour root exists for any composition
        else:
            # The incipient dew liquid must be condensable-rich. Wilson seeds misrank
            # supercritical lights (N2 at Tr > 2 flips volatility), and the resulting
            # vapour-like composition has no liquid density root to iterate from.
            constants, _ = _ig_constants(ids)
            condensable = feed * np.array([float(tc) > T for tc in constants.Tcs])
            if condensable.sum() <= 0.0:
                raise SaturationError(f"dew point: no condensable component at T={T} K")
            comp = condensable / condensable.sum()

        def converge(p: float, comp: np.ndarray) -> tuple[float | None, bool | None, np.ndarray]:
            """(g, None, comp) for a liquid/vapour pair, (None, side, comp) otherwise.

            side True means below the saturation line (bracket ``lo``).
            """
            g: float | None = None
            paired = comp
            for _ in range(_SAT_INNER_ITERS):
                x_liq = feed if bubble else comp
                y_vap = comp if bubble else feed
                rho_heavy = kernel.roots(T, p, x_liq)
                rho_light = kernel.roots(T, p, y_vap)
                # 1.05: the two roots must be a genuinely distinct liquid/vapour pair.
                # Below the mixture saturation pressure the root scan also returns two
                # spurious vapour-like roots (ratio -> 1), whose K-sum converges on the
                # trivial K -> 1 crossing (~10 kPa reported for a 6 MPa bubble, the
                # 293.13 K C1/CO2 case). Above it the scan can return several dense
                # roots whose lowest sits on the unstable middle branch (Z ~ 0.09 on
                # the C1/N2 130 K isotherm), whose fugacity difference is not a K-value
                # (measured K_C1 = 4e8): the lowest root must be genuinely vapour-like
                # (``_vapour_like``) before its fugacity votes.
                split = rho_heavy[-1] / rho_light[0] if (rho_heavy and rho_light) else 0.0
                light_vapour_like = bool(split) and _vapour_like(p, T, rho_light[0], rho_heavy[-1])
                if not (rho_heavy and light_vapour_like and split > 1.05):
                    if g is not None:
                        # The last update stepped off the two-phase window: the
                        # previous (paired) composition and its K-sum stand.
                        return g, None, paired
                    probe = rho_light[0] if rho_light else (rho_heavy[-1] if rho_heavy else None)
                    if probe is None:
                        return None, False, comp  # no density root: above the isotherm ceiling
                    # vapour-like single root: below the line; liquid-like: above it
                    return None, p / (probe * R_GAS * T) > 0.5, comp
                k = np.exp(kernel.ln_phi(T, rho_heavy[-1], x_liq) - kernel.ln_phi(T, rho_light[0], y_vap))
                tot = float(np.sum(k * x_liq)) if bubble else float(np.sum(y_vap / k))
                g = math.log(tot) if bubble else -math.log(tot)
                fresh = (k * x_liq / tot) if bubble else (y_vap / k / tot)
                step = float(np.max(np.abs(fresh - comp)))
                paired, comp = comp, fresh
                if step < _SAT_INNER_TOL:
                    break
            return g, None, comp

        lo: float | None = None
        hi: float | None = None
        g_lo: float | None = None
        g_hi: float | None = None
        seed = p
        for _ in range(200):
            g, below, comp = converge(p, comp)
            if g is not None:
                if abs(g) < 1e-10:
                    return p, comp
                if g > 0.0:
                    lo, g_lo = p, g
                    if g_hi is not None:
                        g_hi *= 0.5  # Illinois inflation of the retained side
                else:
                    hi, g_hi = p, g
                    if g_lo is not None:
                        g_lo *= 0.5
            elif below:
                lo, g_lo = p, None
            else:
                hi, g_hi = p, None
            if lo is not None and hi is not None:
                if hi - lo <= 1e-9 * hi:
                    if g is None:
                        raise SaturationError(
                            f"{'bubble' if bubble else 'dew'} point: the K-sum bracket closed "
                            f"on a phase-boundary discontinuity at T={T} K, P={p:.6g} Pa"
                        )
                    return p, comp
                if g_lo is not None and g_hi is not None and g_lo != g_hi:
                    x_lo, x_hi = math.log(lo), math.log(hi)
                    x = (g_lo * x_hi - g_hi * x_lo) / (g_lo - g_hi)
                    p = min(max(math.exp(x), lo * (1.0 + 1e-12)), hi * (1.0 - 1e-12))
                else:
                    p = math.sqrt(lo * hi)
            else:
                p *= 5.0 if hi is None else 1.0 / 5.0
            if not (seed * 1e-6 <= p <= seed * 1e6):
                # The solution lives within a few orders of magnitude of the Wilson
                # seed; a walk this far out is classifying noise, not an approach to
                # a root (observed: the spurious gigapascal K-sum crossings a wrong
                # seed steered the solver into).
                raise SaturationError(
                    f"{'bubble' if bubble else 'dew'} point: K-sum walk left the seed "
                    f"neighbourhood at T={T} K"
                )
        raise SaturationError(f"{'bubble' if bubble else 'dew'} point: no convergence at T={T} K")

    def _sat_t_of_p(
        self, z: dict[str, float], ids: tuple[str, ...], P: float, *, bubble: bool
    ) -> tuple[float, dict[str, float]]:
        """Isobaric saturation temperature by joint successive substitution at P.

        Nesting the isothermal K-sum solver over T fails on associating feeds:
        approached from the wrong side the feed liquid stretches to its spinodal —
        the CPA MeOH/H2O saturated-liquid root sits ~0.2 mol/m3 from the
        mechanical-stability limit at 322.91 K — where the fugacity finite
        difference turns marginal and history-dependent. At fixed P instead, every
        temperature on the safe side of the answer (below bubble, above dew) sees
        a compressed liquid root, and tot(T) crosses 1 monotonically; a relaxed
        secant step on ln tot drives T there while the incipient composition
        updates alongside. Convergence tot within 5e-3 of 1 maps to ~0.1 % in T,
        ten times tighter than the 0.5 % validation tolerance.
        """
        kernel, _, _ = self._kernel({cid: 1.0 for cid in ids})
        feed = self._zvec(z, ids)
        constants, _ = _ig_constants(ids)
        t_lo = 0.35 * min(float(tc) for tc in constants.Tcs)
        t_hi = 0.999 * max(float(tc) for tc in constants.Tcs)

        # Seed T from the Wilson correlation alone (no EOS cost): tot(T) is monotone.
        def wilson_tot(t: float) -> float:
            kw = self._wilson_k(z, ids, t, P)
            return float(np.sum(kw * feed)) if bubble else float(np.sum(feed / kw))

        w_lo, w_hi = t_lo, t_hi
        for _ in range(80):
            mid = 0.5 * (w_lo + w_hi)
            below = wilson_tot(mid) < 1.0 if bubble else wilson_tot(mid) > 1.0
            if below:
                w_lo = mid
            else:
                w_hi = mid
        t = 0.5 * (w_lo + w_hi)

        if bubble:
            comp = feed.copy()  # incipient vapour: a vapour root exists for any composition
        else:
            condensable = feed * np.array([float(tc) > t for tc in constants.Tcs])
            if condensable.sum() <= 0.0:
                raise SaturationError(f"dew point: no condensable component at P={P:.6g} Pa")
            comp = condensable / condensable.sum()

        t_good: float | None = None
        t_prev: float | None = None
        lt_prev: float | None = None
        for _ in range(60):
            x_liq = feed if bubble else comp
            y_vap = comp if bubble else feed
            rho_heavy = kernel.roots(t, P, x_liq)
            rho_light = kernel.roots(t, P, y_vap)
            if not (rho_heavy and rho_light and rho_heavy[-1] / rho_light[0] > 1.0 + 1e-9):
                if t_good is None:
                    raise SaturationError(
                        f"{'bubble' if bubble else 'dew'} point: no two-phase state at the "
                        f"Wilson seed T={t:.2f} K, P={P:.6g} Pa"
                    )
                t = 0.5 * (t + t_good)  # stepped past the two-phase limit: retreat halfway
                continue
            try:
                k = np.exp(kernel.ln_phi(t, rho_heavy[-1], x_liq) - kernel.ln_phi(t, rho_light[0], y_vap))
            except _NonPhysicalZ:
                if t_good is None:
                    raise SaturationError(
                        f"{'bubble' if bubble else 'dew'} point: non-physical fugacity at the "
                        f"seed T={t:.2f} K, P={P:.6g} Pa"
                    ) from None
                t = 0.5 * (t + t_good)
                continue
            tot = float(np.sum(k * x_liq)) if bubble else float(np.sum(y_vap / k))
            fresh = (k * x_liq / tot) if bubble else (y_vap / k / tot)
            if abs(tot - 1.0) <= 5e-3:
                # T is converged; the incipient composition is not yet (one damped
                # update per T step): returning it reported a half-iterated vapour
                # (CPA-PR MeOH/H2O at 101.325 kPa, x = 0.238: y_MeOH 0.460 where the
                # isothermal bubble solve at the same T, P gives 0.532). Converge it
                # by successive substitution at the final (T, P).
                comp = self._converge_incipient(kernel, feed, fresh, t, P, bubble=bubble)
                return t, {cid: float(v) for cid, v in zip(ids, comp, strict=True)}
            comp = np.sqrt(comp * fresh)  # damped (geometric-mean) update
            comp /= comp.sum()
            lt = math.log(tot)
            slope: float | None = None
            if t_prev is not None and lt_prev is not None and abs(t - t_prev) > 1e-9 * t:
                slope = (lt - lt_prev) / (t - t_prev)
            if slope is not None and abs(slope) > 1e-9:
                t_new = t - lt / slope
                t_new = min(max(t_new, t * 0.95), t * 1.05)  # cap the step at 5 %
            else:
                # No usable slope yet: a 2 % step down the tot gradient, which points
                # toward the answer from either side for both bubble and dew.
                t_new = t * (1.0 + (0.02 if lt > 0.0 else -0.02))
            t_prev, lt_prev = t, lt
            t_good = t
            t = min(max(t_new, t_lo), t_hi)
        raise SaturationError(f"{'bubble' if bubble else 'dew'} point: no convergence at P={P:.6g} Pa")

    @staticmethod
    def _converge_incipient(
        kernel: _Kernel, feed: np.ndarray, comp: np.ndarray, T: float, P: float, *, bubble: bool
    ) -> np.ndarray:
        """Incipient-phase composition by successive substitution at fixed (T, P).

        Stops at a step below _SAT_INNER_TOL, after _SAT_INNER_ITERS sweeps, or when
        the pair stops being a liquid/vapour pair (the last paired composition stands).
        """
        for _ in range(_SAT_INNER_ITERS):
            x_liq = feed if bubble else comp
            y_vap = comp if bubble else feed
            rho_heavy = kernel.roots(T, P, x_liq)
            rho_light = kernel.roots(T, P, y_vap)
            if not (rho_heavy and rho_light and rho_heavy[-1] / rho_light[0] > 1.05):
                break
            if not _vapour_like(P, T, rho_light[0], rho_heavy[-1]):
                break
            k = np.exp(kernel.ln_phi(T, rho_heavy[-1], x_liq) - kernel.ln_phi(T, rho_light[0], y_vap))
            fresh = k * x_liq if bubble else y_vap / k
            fresh = fresh / fresh.sum()
            step = float(np.max(np.abs(fresh - comp)))
            comp = fresh
            if step < _SAT_INNER_TOL:
                break
        return comp

    # -- K values, pure Psat, derivatives ---------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i from the PT flash; None when single-phase."""
        state = self.flash_pt(z, T, P, 1.0)
        if len(state.phases) < 2:
            return None
        vap = next(p for p in state.phases if p.kind == PhaseKind.VAPOR)
        liq = next(p for p in state.phases if p.kind != PhaseKind.VAPOR)
        return {
            cid: vap.composition.get(cid, 0.0) / max(liq.composition.get(cid, 1e-300), 1e-300) for cid in z
        }

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        try:
            self._ids({cid: 1.0})
        except SaftParameterError:
            raise SaftParameterError(f"pure_psat: no verified parameters for {cid!r}") from None
        try:
            return self._psat_cached((cid,), T)
        except SaturationError:
            return None

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PropertyDerivatives:
        """d ln phi / dT and d ln phi / dP per component, for one phase (FD).

        Central differences where both probe states are physical (Z > 0); a
        one-sided difference when a probe falls in the stretched region past the
        liquid root, which happens for liquids near saturation.
        """
        phase = PhaseKind(kind)
        kernel, ids, _ = self._kernel(composition)
        z = self._zvec(composition, ids)
        rho = self._root_for_kind(kernel, z, T, P, phase)

        def lp_at(t: float, r: float) -> np.ndarray | None:
            try:
                return kernel.ln_phi(t, r, z)
            except _NonPhysicalZ:
                return None

        def diff(plus: np.ndarray | None, mid: np.ndarray, minus: np.ndarray | None, h: float) -> np.ndarray:
            if plus is not None and minus is not None:
                return np.asarray((plus - minus) / (2.0 * h), dtype=float)
            if plus is not None:
                return np.asarray((plus - mid) / h, dtype=float)
            if minus is not None:
                return np.asarray((mid - minus) / h, dtype=float)
            raise SaturationError("derivatives: no physical probe state on either side")

        base = lp_at(T, rho)
        if base is None:  # pragma: no cover - a pressure root always has Z > 0
            raise SaturationError("derivatives: root state has non-physical Z")
        h_t = _DPTH_H * T
        # d lnphi/dT at fixed P: the density root moves with T, so re-solve per side.
        rho_up = self._root_for_kind(kernel, z, T + h_t, P, phase)
        rho_dn = self._root_for_kind(kernel, z, T - h_t, P, phase)
        dt = diff(lp_at(T + h_t, rho_up), base, lp_at(T - h_t, rho_dn), h_t)
        # d lnphi/dP: lnphi depends on P through rho only; drho/dP = 1/(dp/drho).
        h_r = _DPTH_H * rho
        dp_drho = (kernel.pressure(T, rho + h_r, z) - kernel.pressure(T, rho - h_r, z)) / (2.0 * h_r)
        dp = diff(lp_at(T, rho + h_r), base, lp_at(T, rho - h_r), h_r) / dp_drho
        return PropertyDerivatives(
            dlnphi_dT={cid: float(v) for cid, v in zip(ids, dt, strict=True)},
            dlnphi_dP={cid: float(v) for cid, v in zip(ids, dp, strict=True)},
        )

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """Single-phase properties at (composition, T, P) — no flash."""
        return self._phase_props_cached(composition, T, P, kind)


class PCSaftThermo(TeqpPackage):
    """PC-SAFT over teqp (Gross & Sadowski 2001 parameters; catalogue row ``pc_saft``)."""

    model_kind = "pc_saft"


class PCSaftAssocThermo(TeqpPackage):
    """Hand-rolled PC-SAFT + association kernel (row ``pc_saft_assoc``, spec T-17)."""

    model_kind = "pc_saft_assoc"


class PCSaftPolarThermo(TeqpPackage):
    """Hand-rolled PC-SAFT + Gross & Vrabec (2006) dipolar term (row ``pc_saft_polar``)."""

    model_kind = "pc_saft_polar"


class SaftVrMieThermo(TeqpPackage):
    """SAFT-VR-Mie over teqp (Lafitte et al. 2013 parameters; row ``saft_vr_mie``)."""

    model_kind = "saft_vr_mie"


class CpaSrkThermo(TeqpPackage):
    """CPA-SRK over the hand-rolled association kernel (row ``cpa_srk``)."""

    model_kind = "cpa_srk"


class CpaPrThermo(TeqpPackage):
    """Refusal row: teqp's CPA is unusable (row ``cpa_pr``)."""

    model_kind = "cpa_pr"


class MultifluidThermo(TeqpPackage):
    """Multi-fluid Helmholtz over teqp's fluid library (row ``multifluid``)."""

    model_kind = "multifluid"


class MultifluidPureThermo(TeqpPackage):
    """Pure-fluid-only multi-fluid Helmholtz (row ``multifluid_pure``); mixtures refuse."""

    model_kind = "multifluid_pure"


class Gerg2008TeqpThermo(TeqpPackage):
    """GERG-2008 through teqp's exact ``GERG2008resid`` kind (row ``gerg2008_teqp``).

    The exact-backend cross-check the T-04 ``gerg2008`` row (CoolProp's fitted
    parameters) defers to: the Kunz & Wagner (2012) formulation, its own pure-fluid
    residual equations plus the binary reducing/departure parameters (J. Chem. Eng.
    Data 57, 3032-3091), restricted to the GERG-2008 component slate
    (data/thermo_params/saft/pure.yaml, ``gerg2008_teqp.aliases``).
    """

    model_kind = "gerg2008_teqp"


class SoftSaftThermo(TeqpPackage):
    """soft-SAFT over teqp's ``SoftSAFT`` kind (row ``soft_saft``).

    Blas & Vega (1997) soft-SAFT, non-associating: Johnson, Zollweg & Gubbins (1993)
    Lennard-Jones MBWR reference plus the Wertheim TPT1 chain term with the Johnson,
    Muller & Gubbins (1994) contact-value fit (Pamies 2003 thesis, eqs 2.2-2.7 and
    A.20-A.26). Parameters: Pamies (2003) Tables 4.1, 4.6 and 4.10.
    """

    model_kind = "soft_saft"
