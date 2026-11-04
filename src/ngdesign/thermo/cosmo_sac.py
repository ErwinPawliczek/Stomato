"""COSMO-SAC 2010 activity-coefficient model on three sigma profiles (NHB, OH, OT).

The model of Hsieh, Sandler & Lin, Fluid Phase Equilib. 297, 90 (2010), as written and
benchmarked in Bell et al., "A Benchmark Open-Source Implementation of COSMO-SAC",
J. Chem. Theory Comput. 16(4), 2635 (2020), doi:10.1021/acs.jctc.9b01016, sec. 2.1-2.2 and
3.2, Table 2 (equation numbers below are that paper's):

- combinatorial (Staverman-Guggenheim, eqs. 15-20)
    ln gamma_i^C = ln(phi_i/x_i) + (z/2) q_i ln(theta_i/phi_i) + l_i - (phi_i/x_i) sum_j x_j l_j
    theta_i = x_i q_i / sum x_j q_j, phi_i = x_i r_i / sum x_j r_j,
    l_i = (z/2)(r_i - q_i) - (r_i - 1), r_i = V_i/r0, q_i = A_i/q0;
- residual (eqs. 34-35)
    ln gamma_i^R = (A_i/a_eff) sum_t sum_m p_i^t(sigma_m) [ln Gamma_S^t(sigma_m) - ln Gamma_i^t(sigma_m)]
    ln Gamma^t(sigma_m) = -ln sum_s sum_n p^s(sigma_n) Gamma^s(sigma_n) exp(-dW(sigma_m^t, sigma_n^s)/RT)
  over the mixture profile p_S = sum x_i A_i p_i / sum x_i A_i and each pure profile;
- exchange energy (eqs. 31-33)
    dW = c_ES(T) (sigma_m + sigma_n)^2 - c_hb (sigma_m - sigma_n)^2, c_ES = A_ES + B_ES/T^2,
    c_hb = c_OH-OH, c_OT-OT or c_OH-OT for an OH/OT pair of opposite sign, else 0.

Constants (Table 2): q0 79.53 A^2, r0 66.69 A^3, z 10, a_eff 7.25 A^2, A_ES 6525.69 and
B_ES 1.4859e8 kcal A^4 K^2/(mol e^2), c_OH-OH 4013.78, c_OT-OT 932.31, c_OH-OT 3016.43
kcal A^4/(mol e^2); R = k_B N_A / 4184 kcal/(mol K) (2018 SI), as in the reference code.

The segment activity coefficients are solved by the reference implementation's damped
successive substitution (Gamma <- (Gamma + Gamma_new)/2), to a relative change of 1e-12,
over the sigma bins in which some component of the support has surface (empty bins carry
zero weight in every sum, so dropping them is exact). The Hsieh et al. (2014) dispersion
term (COSMO-SAC-dsp) is not included: the reference implementation defines it for binaries
only.

``dGE_dxs`` returns RT ln gamma_i (the base class's gamma route reduces it to ln gamma_i
exactly). The composition and temperature second derivatives are central differences of
the model itself: no analytic form is published.
"""

from __future__ import annotations

import math
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from thermo.activity import GibbsExcess

PROFILES_PATH = Path(__file__).resolve().parents[3] / "data" / "thermo_params" / "cosmo_sac" / "profiles.yaml"

#: Bell et al. (2020) Table 2: COSMO-SAC 2010 constants.
Q0_A2 = 79.53
R0_A3 = 66.69
Z_COORDINATION = 10.0
A_EFF_A2 = 7.25
A_ES = 6525.69
B_ES = 1.4859e8
C_OH_OH = 4013.78
C_OT_OT = 932.31
C_OH_OT = 3016.43
#: kcal/(mol K): k_B N_A / 4184 with the 2018 SI constants (reference implementation).
R_KCAL = 1.38064903e-23 * 6.022140758e23 / 4184.0
#: J/(mol K), for G^E in J/mol.
R_J = 8.31446261815324

N_BINS = 51
SIGMA_GRID = np.linspace(-0.025, 0.025, N_BINS)
_PROFILE_KEYS = ("psigmaA_nhb", "psigmaA_oh", "psigmaA_ot")
_GAMMA_TOL = 1e-12
_GAMMA_MAX_ITER = 20000


class CosmoSacProfile:
    """One component's sigma profiles: p(sigma)A over the 153 NHB/OH/OT bins, A and V."""

    __slots__ = ("cas", "psigma_area", "area", "volume")

    def __init__(self, cas: str, psigma_area: np.ndarray, volume: float) -> None:
        self.cas = cas
        self.psigma_area = psigma_area
        self.area = float(psigma_area.sum())
        self.volume = float(volume)


@cache
def _profile_table() -> dict[str, Any]:
    parsed: dict[str, Any] = yaml.safe_load(PROFILES_PATH.read_text())["profiles"]
    return parsed


def load_profile(cid: str, cas: str) -> CosmoSacProfile:
    """The shipped profile of ``cas``; a component without one raises naming it."""
    entry = _profile_table().get(cas)
    if entry is None:
        raise ValueError(
            f"no COSMO-SAC sigma profile for {cid} ({cas}) in "
            "data/thermo_params/cosmo_sac/profiles.yaml; refusing to predict"
        )
    values = np.array([v for key in _PROFILE_KEYS for v in entry[key]], dtype=float)
    return CosmoSacProfile(cas, values, float(entry["volume_A3"]))


@cache
def _delta_w_parts() -> tuple[np.ndarray, np.ndarray]:
    """(sigma_m + sigma_n)^2 and c_hb (sigma_m - sigma_n)^2 over the 153 x 153 bins (eqs. 31, 33)."""
    sigma = np.tile(SIGMA_GRID, 3)
    kind = np.repeat(np.arange(3), N_BINS)  # 0 NHB, 1 OH, 2 OT
    c_table = np.array([[0.0, 0.0, 0.0], [0.0, C_OH_OH, C_OH_OT], [0.0, C_OH_OT, C_OT_OT]])
    sm, sn = sigma[:, None], sigma[None, :]
    c_hb = np.where(sm * sn < 0.0, c_table[kind[:, None], kind[None, :]], 0.0)
    return (sm + sn) ** 2, c_hb * (sm - sn) ** 2


@lru_cache(maxsize=4096)
def _pure_ln_gamma(T: float, cas: str, active: tuple[bool, ...]) -> np.ndarray:
    """ln Gamma_i of one pure component's profile (depends on T and the active bins only)."""
    entry = _profile_table()[cas]
    values = np.array([v for key in _PROFILE_KEYS for v in entry[key]], dtype=float)
    return segment_ln_gamma(T, values / values.sum(), np.array(active))


def segment_ln_gamma(T: float, psigma: np.ndarray, active: np.ndarray) -> np.ndarray:
    """ln Gamma over the ``active`` bins of a normalised profile ``psigma`` (eq. 35)."""
    es, hb = _delta_w_parts()
    idx = np.flatnonzero(active)
    delta_w = (A_ES + B_ES / T**2) * es[np.ix_(idx, idx)] - hb[np.ix_(idx, idx)]
    weights = np.exp(-delta_w / (R_KCAL * T)) * psigma[idx][None, :]
    gamma = np.ones(idx.size)
    for _ in range(_GAMMA_MAX_ITER):
        new = 1.0 / (weights @ gamma)
        gamma = 0.5 * (gamma + new)
        if float(np.max(np.abs((gamma - new) / gamma))) < _GAMMA_TOL:
            result: np.ndarray = np.log(gamma)
            return result
    raise ArithmeticError(f"COSMO-SAC segment activity coefficients did not converge at T={T} K")


def cosmo_sac_ln_gammas(T: float, xs: list[float], profiles: list[CosmoSacProfile]) -> list[float]:
    """ln gamma_i = ln gamma_i^C + ln gamma_i^R of COSMO-SAC 2010 (Bell et al. 2020, eqs. 15-35)."""
    x = np.array(xs, dtype=float)
    areas = np.array([p.area for p in profiles])
    q = areas / Q0_A2
    r = np.array([p.volume for p in profiles]) / R0_A3
    ell = Z_COORDINATION / 2.0 * (r - q) - (r - 1.0)
    xq, xr, xl = float(x @ q), float(x @ r), float(x @ ell)
    stack = np.array([p.psigma_area for p in profiles])
    active = stack.sum(axis=0) > 0.0
    mix = (x @ stack) / float(x @ areas)
    ln_mix = segment_ln_gamma(T, mix, active)
    idx = np.flatnonzero(active)
    out = []
    for i, prof in enumerate(profiles):
        pure = prof.psigma_area / prof.area
        ln_pure = _pure_ln_gamma(float(T), prof.cas, tuple(bool(a) for a in active))
        residual = prof.area / A_EFF_A2 * float(pure[idx] @ (ln_mix - ln_pure))
        phi_over_x = r[i] / xr
        theta_over_phi = (q[i] / xq) / phi_over_x
        comb = (
            math.log(phi_over_x)
            + Z_COORDINATION / 2.0 * q[i] * math.log(theta_over_phi)
            + ell[i]
            - phi_over_x * xl
        )
        out.append(comb + residual)
    return out


class CosmoSac(GibbsExcess):  # type: ignore[misc]  # thermo ships no stubs for GibbsExcess
    # thermo's GibbsExcessLiquid stamps itself 20000 + model_id; see ge_models.VanLaar.
    model_id = 900
    """COSMO-SAC 2010 gE model over shipped sigma profiles (see the module docstring)."""

    __slots__ = ("profiles", "T", "xs", "N", "vectorized", "_lngammas")

    _STEP_T = 1e-2
    _STEP_X = 1e-5

    def __init__(self, *, xs: list[float], T: float = 298.15, profiles: list[CosmoSacProfile]) -> None:
        self.profiles = profiles
        self.T = T
        self.xs = list(xs)
        self.N = len(xs)
        self.vectorized = False
        self._lngammas: list[float] | None = None

    def to_T_xs(self, T: float, xs: list[float]) -> CosmoSac:
        return CosmoSac(xs=list(xs), T=T, profiles=self.profiles)

    def ln_gammas(self) -> list[float]:
        if self._lngammas is None:
            self._lngammas = cosmo_sac_ln_gammas(self.T, self.xs, self.profiles)
        return self._lngammas

    def GE(self) -> float:
        return R_J * self.T * sum(x * lg for x, lg in zip(self.xs, self.ln_gammas(), strict=True))

    def dGE_dxs(self) -> list[float]:
        return [R_J * self.T * lg for lg in self.ln_gammas()]

    def _at_T(self, T: float) -> CosmoSac:
        return self.to_T_xs(T, self.xs)

    def d2GE_dxixjs(self) -> list[list[float]]:
        step = self._STEP_X
        rows: list[list[float]] = [[0.0] * self.N for _ in range(self.N)]
        for j in range(self.N):
            up = list(self.xs)
            dn = list(self.xs)
            up[j] += step
            dn[j] -= step
            total_up, total_dn = sum(up), sum(dn)
            hi = self.to_T_xs(self.T, [v / total_up for v in up]).dGE_dxs()
            lo = self.to_T_xs(self.T, [v / total_dn for v in dn]).dGE_dxs()
            for i in range(self.N):
                rows[i][j] = (hi[i] - lo[i]) / (2.0 * step)
        return rows

    def dGE_dT(self) -> float:
        h = self._STEP_T
        return (self._at_T(self.T + h).GE() - self._at_T(self.T - h).GE()) / (2.0 * h)

    def d2GE_dT2(self) -> float:
        h = self._STEP_T
        return (self._at_T(self.T + h).GE() - 2.0 * self.GE() + self._at_T(self.T - h).GE()) / h**2

    def d3GE_dT3(self) -> float:
        h = self._STEP_T
        values = [self._at_T(self.T + k * h).GE() for k in (-2, -1, 1, 2)]
        return (values[3] - 2.0 * values[2] + 2.0 * values[1] - values[0]) / (2.0 * h**3)

    def d2GE_dTdxs(self) -> list[float]:
        h = self._STEP_T
        hi = self._at_T(self.T + h).dGE_dxs()
        lo = self._at_T(self.T - h).dGE_dxs()
        return [(a - b) / (2.0 * h) for a, b in zip(hi, lo, strict=True)]

    def __repr__(self) -> str:
        return f"CosmoSac(T={self.T!r}, xs={self.xs!r}, cas={[p.cas for p in self.profiles]!r})"
