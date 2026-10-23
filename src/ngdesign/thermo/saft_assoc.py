"""Wertheim TPT1 association term shared across the SAFT/CPA family (spec T-17).

The thermodynamics: first-order thermodynamic perturbation theory of Wertheim
(1984, J. Stat. Phys. 35, 19-34 and 35, 35-47), in the compressibility-factor
formulation of Michelsen & Hendriks, Fluid Phase Equilib. 180-181 (2001)
165-174, eq. A.5:

    A_assoc/(N R T) = sum_i x_i sum_A (ln X_Ai - X_Ai/2 + 1/2)

with the site fractions solved here by damped successive substitution.
Association schemes 2B/3B/4C follow Huang & Radosz, Ind. Eng. Chem. Res. 29
(1990) 2284-2294, Table 6: 2B = one donor + one acceptor site, 3B = two donors
+ one acceptor, 4C = two donors + two acceptors, encoded as the site lists
('d'/'a') carried by the parameter file.

One solver serves every associating row: cpa_srk (whose bound cases must stay
byte-identical — the arithmetic below is moved verbatim from the T-07
_CpaKernel), cpa_pr, and the new pc_saft_assoc row. Each row supplies its own
Delta^AiBj builder (the definition of the association strength differs: CPA's
cubic-combined form vs PC-SAFT's hard-sphere contact RDF form); the site
iteration and the A_assoc summation are here, once.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

#: CODATA 2018 molar gas constant, J/(mol.K) (the same constant the bridge uses).
R_GAS = 8.31446261815324


def solve_site_fractions(rho: float, delta: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Site fractions X_A by damped successive substitution from a deterministic start.

    X = 1/(1 + rho*Delta*X*w), iterated with 0.5 damping. The iteration must be
    a pure function of state: a warm start carried across calls made alpha_r
    history-dependent, which flipped marginal states (saturated-liquid roots
    hugging their spinodal) between SSA branches depending on call order and
    made scans and fugacities irreproducible.

    ``weights`` carries the composition to the site list (z_i per site).
    """
    x = np.asarray(1.0 / (1.0 + rho * (delta @ weights)), dtype=float)
    # Undamped SSA 2-cycles at liquid-like densities for strongly associating
    # feeds (observed: it stalled above 1e-13 and burned its whole iteration
    # budget every call); 0.5-damping contracts the cycle and reaches the same
    # fixed point. Tolerance 1e-10 keeps the association term smooth enough that
    # the composition finite differences meet the harness's 1e-6 Gibbs-Duhem bar
    # (measured integral ratio 8.6e-7 here; a Newton variant reached a tighter
    # residual yet a WORSE integral, so the sweep residual is not the binding
    # error source - keep the simple damped iteration).
    for _ in range(150):
        nxt = np.asarray(1.0 / (1.0 + rho * (delta @ (x * weights))), dtype=float)
        nxt = 0.5 * x + 0.5 * nxt
        delta_x = float(np.max(np.abs(nxt - x)))
        x = nxt
        if delta_x < 1e-10:
            break
    return x


def alpha_assoc_value(weights: np.ndarray, x: np.ndarray) -> float:
    """sum_i x_i sum_A (ln X_A - X_A/2 + 1/2): exactly zero when X = 1."""
    return float(np.sum(weights * (np.log(x) - x / 2.0 + 0.5)))


class CPAWertheim:
    """The CPA association term: cubic-combined Delta with CR1 cross-association.

    Delta_AB = g(rho) * (exp(eps_AB/(R T)) - 1) * beta_AB * b_ij with b_ij the
    arithmetic mean of the co-volumes, donor-acceptor site pairing only, and
    CR1 cross-association (epsilon arithmetic mean, beta geometric mean;
    Kontogeorgis, Voutsas, Yakoumis & Tassios, Ind. Eng. Chem. Res. 35 (1996)
    4631-4642). Radial distribution function g = 1/(1 - 1.9 eta) with
    eta = b_mix*rho/4 (the SRK-based CPA form, Kontogeorgis et al. 1996, eq.
    13-14; carried unchanged into the CPA-PR row per the CPA-PR literature).
    """

    def __init__(self, params: list[dict[str, Any]]) -> None:
        self.params = params
        # Memo for the temperature-only association strength: density root scans
        # rebuild Delta at ~60-100 densities per scan and only the scalar radial
        # factor g(rho) changes with rho. Cached values are pure functions of
        # (T, composition), so results never depend on call order.
        self._delta_t_cache: dict[tuple[float, bytes], np.ndarray] = {}

    def _site_iter(self) -> list[tuple[int, str]]:
        return [(i, t) for i, p in enumerate(self.params) for t in p["sites"]]

    def _site_weights(self, z: np.ndarray) -> np.ndarray:
        return np.array([z[i] for i, _t in self._site_iter()])

    def _delta_t_matrix(self, T: float, z: np.ndarray) -> np.ndarray:
        """Temperature-only association strength (exp(eps/RT)-1) * beta * b_ij."""
        key = (round(T, 12), z.tobytes())
        cached = self._delta_t_cache.get(key)
        if cached is None:
            sites = self._site_iter()
            d = np.zeros((len(sites), len(sites)))
            for a, (ia, ta) in enumerate(sites):
                pa = self.params[ia]
                for b, (ib, tb) in enumerate(sites):
                    if not ((ta == "d" and tb == "a") or (ta == "a" and tb == "d")):
                        continue
                    pb = self.params[ib]
                    if ia == ib:
                        eps, beta = pa["epsilon_AB"], pa["beta_AB"]
                    else:  # CR1 cross-association rule
                        eps = 0.5 * (pa["epsilon_AB"] + pb["epsilon_AB"])
                        beta = math.sqrt(pa["beta_AB"] * pb["beta_AB"])
                    b_ij = 0.5 * (pa["b"] + pb["b"])
                    d[a, b] = (math.exp(eps / (R_GAS * T)) - 1.0) * beta * b_ij
            cached = d
            self._delta_t_cache[key] = cached
        return cached

    def _delta_matrix(self, T: float, rho: float, z: np.ndarray) -> np.ndarray:
        """Delta_AB over the site list (association pairs donor with acceptor only)."""
        eta = float(sum(x * p["b"] for x, p in zip(z, self.params, strict=True))) * rho / 4.0
        g = 1.0 / (1.0 - 1.9 * eta) if eta < 0.49 else 1.0e10
        return g * self._delta_t_matrix(T, z)

    def alpha(self, T: float, rho: float, z: np.ndarray) -> float:
        """A_assoc/(N R T) at (T, rho, z)."""
        d = self._delta_matrix(T, rho, z)
        x = solve_site_fractions(rho, d, self._site_weights(z))
        return alpha_assoc_value(self._site_weights(z), x)

    def derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """A_assoc/(N R T) and its exact rho / composition derivatives at the fixed point.

        Returns ``(alpha, dalpha/drho, dalpha/dz_i)`` with the site fractions
        differentiated through the fixed-point equation X = 1/(1 + rho*Delta*X*w)
        by implicit differentiation: (dF/dX) dX = -dF/explicit, where
        F_s = X_s (1 + N_s) - 1 and N_s = (rho Delta X w)_s. Delta carries the
        composition dependence only through the radial distribution factor
        g(eta), eta = b_mix rho / 4 (the site-level Delta_t entries are pair
        properties), and the weights w through z. Closed-form derivatives keep
        an analytic-physical-term kernel coherent: a Gibbs-Duhem loop measures
        the *surface* ln phi_i, and any finite-difference error field left in
        one derivative (density, Z or mu) integrates into the loop residual.
        """
        sites = self._site_iter()
        w = self._site_weights(z)
        d = self._delta_matrix(T, rho, z)
        big_d = rho * d
        x = solve_site_fractions(rho, d, w)
        xw = x * w
        big_n = big_d @ xw
        phi = np.log(x) - x / 2.0 + 0.5
        dphi = 1.0 / x - 0.5
        alpha = float(np.sum(w * phi))
        b_mix = float(sum(xi * p["b"] for xi, p in zip(z, self.params, strict=True)))
        eta = b_mix * rho / 4.0
        one_m = 1.0 - 1.9 * eta
        # dD/drho with D = rho*Delta = rho*g*Delta_t: Delta + rho*Delta_t*g'(eta)*b_mix/4
        # and g'(eta)*b_mix/4 * rho/g = 1.9 b_mix rho / (4 (1-1.9 eta)) since 1/g = (1-1.9 eta)
        d_d_drho = d * (1.0 + rho * 1.9 * b_mix / (4.0 * one_m))
        # Jacobian of F_s = X_s (1 + N_s) - 1 wrt X, with N = (rho Delta)(X w)
        jac = np.diag(1.0 + big_n) + x[:, None] * big_d * w[None, :]
        ns = len(sites)
        rhs = np.zeros((ns, 1 + z.size))
        rhs[:, 0] = x * (d_d_drho @ xw)
        comp_of = [ia for ia, _t in sites]
        for i in range(z.size):
            # dD/dz_i = D * 1.9 b_i rho / (4 (1-1.9 eta)): only g depends on z
            dd_di = big_d * (1.9 * float(self.params[i]["b"]) * rho / (4.0 * one_m))
            m_i = np.array([1.0 if comp_of[s] == i else 0.0 for s in range(ns)])
            rhs[:, 1 + i] = x * ((dd_di @ xw) + (big_d @ (x * m_i)))
        # (dF/dX) dX = -dF/explicit, solved for rho and every z_i at once
        dx = np.linalg.solve(jac, -rhs)
        dalpha_drho = float(np.sum(w * dphi * dx[:, 0]))
        dalpha_dz = np.zeros(z.size)
        for i in range(z.size):
            site_own = np.array([1.0 if comp_of[s] == i else 0.0 for s in range(ns)])
            dalpha_dz[i] = float(np.sum(site_own * phi + w * dphi * dx[:, 1 + i]))
        return alpha, dalpha_drho, dalpha_dz



#: Universal dispersive constants of the PC-SAFT chain and dispersion terms,
#: Gross & Sadowski, Ind. Eng. Chem. Res. 40 (2001) 1244-1257, Table 3 (the rows
#: are the constant, (m-1)/m and (m-1)(m-2)/m^2 coefficient series of I1 and I2,
#: eqs. A.18-A.19; C1 is eq. A.11 and C2 = dC1/deta is eq. A.31). Typed from the
#: NIST teqp source (usnistgov/teqp, src/data/PCSAFT.cpp, GrossSadowski2001
#: namespace, public-domain code carrying the IECR 2019 erratum corrections),
#: retrieved 2026-10-23, and cross-checked numerically against teqp's PCSAFT
#: engine (the check-value test in tests/thermo/test_saft.py).
_PCSAFT_A = (
    (0.9105631445, 0.6361281449, 2.6861347891, -26.547362491, 97.759208784, -159.59154087, 91.297774084),
    (-0.3084016918, 0.1860531159, -2.5030047259, 21.419793629, -65.255885330, 83.318680481, -33.746922930),
    (-0.0906148351, 0.4527842806, 0.5962700728, -1.7241829131, -4.1302112531, 13.776631870, -8.6728470368),
)
_PCSAFT_B = (
    (0.7240946941, 2.2382791861, -4.0025849485, -21.003576815, 26.855641363, 206.55133841, -355.60235612),
    (-0.5755498075, 0.6995095521, 3.8925673390, -17.215471648, 192.67226447, -161.82646165, -165.20769346),
    (0.0976883116, -0.2557574982, -9.1558561530, 20.642075974, -38.804430052, 93.626774077, -29.666905585),
)

#: Avogadro constant (CODATA 2018); converts molar density (mol/m3) to number
#: density in molecules/A^3, the unit the PC-SAFT hard-sphere and dispersive
#: terms are written in (sigma in Angstrom).
N_AVOGADRO = 6.02214076e23
_MOL_TO_A3 = N_AVOGADRO * 1.0e-30


def _ck(mat: tuple[tuple[float, ...], ...], k: int, mbar: float) -> float:
    """The Table 3 coefficient c_k(mbar) = row0 + row1 (m-1)/m + row2 (m-1)(m-2)/m^2."""
    r = mbar - 1.0
    return mat[0][k] + mat[1][k] * (r / mbar) + mat[2][k] * (r * (mbar - 2.0)) / (mbar * mbar)


def _dck(mat: tuple[tuple[float, ...], ...], k: int, mbar: float) -> float:
    """dc_k/dmbar: d((m-1)/m)/dm = 1/m^2, d((m-1)(m-2)/m^2)/dm = 3/m^2 - 4/m^3."""
    return mat[1][k] / (mbar * mbar) + mat[2][k] * (3.0 / (mbar * mbar) - 4.0 / mbar**3)


class PCSaftPhysical:
    """The PC-SAFT hard-chain + dispersion residual term (Gross & Sadowski 2001).

    Chain: BMCSL hard-sphere reference (eq. A.6), contact RDF g_ij^hs (eq. A.7),
    chain term (eq. A.4). Dispersion: the I1/I2 power series in the packing
    fraction eta = zeta_3 with the Table 3 constants and the C1 chain-length
    correction (eqs. A.11, A.18-A.19, A.24-A.26), cross interactions epsilon_ij
    geometric and sigma_ij arithmetic mean (eq. A.5, zero k_ij — the pure and
    self-associating binaries this row serves have no citable k_ij in G&S 2002
    Table 2). Every density and composition derivative is closed-form: the four
    zeta moments are linear in rho with known composition slopes, and I1, I2,
    C1 are polynomial/rational in (eta, m). Closed forms are required, not
    stylistic: the Gibbs-Duhem bar is 1e-6 and finite-difference composition
    shifts measured 3.7e-6 on the cpa_pr surface.
    """

    def __init__(self, params: list[dict[str, Any]]) -> None:
        self._m = np.array([float(p["m"]) for p in params])
        self._sigma = np.array([float(p["sigma_Angstrom"]) for p in params])
        self._eps = np.array([float(p["epsilon_over_k"]) for p in params])

    # -- state functions of (T, rho, z) ---------------------------------------

    def _d(self, T: float) -> np.ndarray:
        """Temperature-dependent hard-segment diameters, eq. A.9 (Barker-Henderson)."""
        return self._sigma * (1.0 - 0.12 * np.exp(-3.0 * self._eps / T))

    def _zeta(self, rho_a3: float, z: np.ndarray, d: np.ndarray) -> np.ndarray:
        """The four zeta moments, eq. A.8: zeta_k = pi/6 rho_A3 sum x m d^k."""
        return np.array(
            [np.pi / 6.0 * rho_a3 * float(np.sum(z * self._m * d**k)) for k in range(4)]
        )

    def _s_terms(self, T: float, z: np.ndarray) -> tuple[float, float]:
        """The dispersion cross sums (eqs. A.24-A.26): S1 = sum x_i x_j m_i m_j
        (eps_ij/T) sigma_ij^3 and S2 with (eps_ij/T)^2."""
        s1 = 0.0
        s2 = 0.0
        n = z.size
        for i in range(n):
            for j in range(n):
                sigma_ij3 = (0.5 * (self._sigma[i] + self._sigma[j])) ** 3
                e_ij = math.sqrt(self._eps[i] * self._eps[j]) / T
                s1 += z[i] * z[j] * self._m[i] * self._m[j] * e_ij * sigma_ij3
                s2 += z[i] * z[j] * self._m[i] * self._m[j] * e_ij * e_ij * sigma_ij3
        return s1, s2

    @staticmethod
    def _c1(eta: float, mbar: float) -> float:
        """C1, eq. A.11 (teqp's erratum-corrected form: the reciprocal of the printed RHS)."""
        ome = 1.0 - eta
        denom = (
            1.0
            + mbar * (8.0 * eta - 2.0 * eta * eta) / ome**4
            + (1.0 - mbar)
            * (20.0 * eta - 27.0 * eta * eta + 12.0 * eta**3 - 2.0 * eta**4)
            / (ome * ome * (2.0 - eta) * (2.0 - eta))
        )
        return 1.0 / denom

    @staticmethod
    def _c2(eta: float, mbar: float) -> float:
        """dC1/deta, eq. A.31."""
        ome = 1.0 - eta
        c1 = PCSaftPhysical._c1(eta, mbar)
        return -c1 * c1 * (
            mbar * (-4.0 * eta * eta + 20.0 * eta + 8.0) / ome**5
            + (1.0 - mbar)
            * (2.0 * eta**3 + 12.0 * eta * eta - 48.0 * eta + 40.0)
            / ((1.0 - eta) * (2.0 - eta)) ** 3
        )

    @staticmethod
    def _dc1_dmbar(eta: float, mbar: float) -> float:
        ome = 1.0 - eta
        c1 = PCSaftPhysical._c1(eta, mbar)
        d_denom = (8.0 * eta - 2.0 * eta * eta) / ome**4 - (
            20.0 * eta - 27.0 * eta * eta + 12.0 * eta**3 - 2.0 * eta**4
        ) / (ome * ome * (2.0 - eta) * (2.0 - eta))
        return -c1 * c1 * d_denom

    @staticmethod
    def _i_series(eta: float, mbar: float, mat: tuple[tuple[float, ...], ...]) -> float:
        return sum(_ck(mat, k, mbar) * eta**k for k in range(7))

    @staticmethod
    def _di_deta(eta: float, mbar: float, mat: tuple[tuple[float, ...], ...]) -> float:
        return sum(k * _ck(mat, k, mbar) * eta ** (k - 1) for k in range(1, 7))

    @staticmethod
    def _di_dmbar(eta: float, mbar: float, mat: tuple[tuple[float, ...], ...]) -> float:
        return sum(_dck(mat, k, mbar) * eta**k for k in range(7))

    def derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """alpha_hc + alpha_disp and its exact rho / composition derivatives.

        Returns ``(alpha, dalpha/drho, [dalpha/dz_i])`` at fixed (T, rho).
        """
        d = self._d(T)
        mbar = float(np.sum(z * self._m))
        m_minus1 = self._m - 1.0
        rho_a3 = rho * _MOL_TO_A3
        zeta = self._zeta(rho_a3, z, d)
        z0, z1, z2, z3 = (float(v) for v in zeta)
        eta = z3
        u = 1.0 - z3

        # -- hard sphere, eq. A.6, and its partials wrt the four moments ---------
        tiny = z3 < 1.0e-9
        if tiny:
            # rho -> 0 series (teqp's form): ratios D_k = zeta_k / rho_A3 cancel
            # the 1/zeta_0 pole; exact to first order in rho.
            dk = [np.pi / 6.0 * float(np.sum(z * self._m * d**k)) for k in range(4)]
            alpha_hs = (
                3.0 * dk[1] / dk[0] * z2 / u
                + dk[2] * dk[2] * z2 / (dk[3] * dk[0] * u * u)
                - math.log(u)
                + dk[2] ** 3 / (dk[3] * dk[3] * dk[0]) * math.log(u)
            )
            pa = np.zeros(4)
        else:
            t1 = 3.0 * z1 * z2 / u
            t2 = z2**3 / (z3 * u * u)
            t3 = (z2**3 / z3**2 - z0) * math.log(u)
            alpha_hs = (t1 + t2 + t3) / z0
            pa = np.array(
                [
                    -(t1 + t2 + t3) / (z0 * z0) - math.log(u) / z0,
                    3.0 * z2 / (u * z0),
                    (3.0 * z1 / u + 3.0 * z2 * z2 / (z3 * u * u) + 3.0 * z2 * z2 * math.log(u) / z3**2) / z0,
                    (
                        t1 / u
                        + t2 * (-1.0 / z3 + 2.0 / u)
                        - 2.0 * z2**3 * math.log(u) / z3**3
                        - (z2**3 / z3**2 - z0) / u
                    ) / z0,
                ]
            )

        # -- hard chain, eq. A.4: g_ii with d_i d_j/(d_i+d_j) = d_i/2 -------------
        ci1 = 1.5 * d
        ci2 = 0.5 * d * d
        g_ii = 1.0 / u + ci1 * z2 / u**2 + ci2 * z2 * z2 / u**3
        lng = np.log(g_ii)
        dg2 = (ci1 / u**2 + 2.0 * ci2 * z2 / u**3) / g_ii  # d ln g_ii / dzeta_2
        dg3 = (1.0 / u**2 + 2.0 * ci1 * z2 / u**3 + 3.0 * ci2 * z2 * z2 / u**4) / g_ii
        alpha_hc = mbar * alpha_hs - float(np.sum(z * m_minus1 * lng))

        # -- dispersion, eqs. A.24-A.26 -------------------------------------------
        s1, s2 = self._s_terms(T, z)
        i1 = self._i_series(eta, mbar, _PCSAFT_A)
        i2 = self._i_series(eta, mbar, _PCSAFT_B)
        c1 = self._c1(eta, mbar)
        alpha_disp = -2.0 * math.pi * rho_a3 * i1 * s1 - math.pi * rho_a3 * mbar * c1 * i2 * s2

        if tiny:
            # roots() grid edge: rho R T dominates the pressure; exact derivatives
            # are not needed there and the finite-difference flash never lands on
            # these states.
            return alpha_hc + alpha_disp, 0.0, np.zeros(z.size)

        # -- shared derivative pieces ---------------------------------------------
        # dzeta_k/drho = zeta_k/rho (every moment is linear in rho)
        # dzeta_k/dz_i = pi/6 rho_A3 m_i d_i^k
        di1_deta = self._di_deta(eta, mbar, _PCSAFT_A)
        di2_deta = self._di_deta(eta, mbar, _PCSAFT_B)
        di1_dm = self._di_dmbar(eta, mbar, _PCSAFT_A)
        di2_dm = self._di_dmbar(eta, mbar, _PCSAFT_B)
        dc1_deta = self._c2(eta, mbar)
        dc1_dm = self._dc1_dmbar(eta, mbar)

        # -- d/drho ----------------------------------------------------------------
        da_hs_drho = float(np.dot(pa, zeta)) / rho
        da_hc_drho = mbar * da_hs_drho - float(np.sum(z * m_minus1 * (dg2 * z2 + dg3 * z3))) / rho
        da_disp_drho = (
            -2.0 * math.pi * _MOL_TO_A3 * i1 * s1
            - 2.0 * math.pi * rho_a3 * di1_deta * (eta / rho) * s1
            - math.pi * _MOL_TO_A3 * mbar * c1 * i2 * s2
            - math.pi * rho_a3 * mbar * c1 * di2_deta * (eta / rho) * s2
            - math.pi * rho_a3 * mbar * dc1_deta * (eta / rho) * i2 * s2
        )
        da_drho = da_hc_drho + da_disp_drho

        # -- d/dz_i ----------------------------------------------------------------
        dz = np.zeros(z.size)
        for i in range(z.size):
            mi = float(self._m[i])
            dzk_i = np.array([np.pi / 6.0 * rho_a3 * mi * float(d[i] ** k) for k in range(4)])
            deta_i = dzk_i[3]
            # chain: mbar and the ln g_ii sum, plus alpha_hs through every moment
            hc_i = (
                mi * alpha_hs
                - float(m_minus1[i]) * lng[i]
                + mbar * float(np.dot(pa, dzk_i))
                - float(np.sum(z * m_minus1 * (dg2 * dzk_i[2] + dg3 * dzk_i[3])))
            )
            # dispersion: dmbar (direct + through I1/I2/C1), deta, and the cross sums
            ds1_i = 2.0 * mi * self._row_sum(T, z, i, 1)
            ds2_i = 2.0 * mi * self._row_sum(T, z, i, 2)
            disp_i = (
                -2.0 * math.pi * rho_a3 * (di1_dm * mi + di1_deta * deta_i) * s1
                - 2.0 * math.pi * rho_a3 * i1 * ds1_i
                - math.pi
                * rho_a3
                * (
                    mi * c1 * i2
                    + mbar * dc1_dm * mi * i2
                    + mbar * dc1_deta * deta_i * i2
                    + mbar * c1 * di2_dm * mi
                    + mbar * c1 * di2_deta * deta_i
                )
                * s2
                - math.pi * rho_a3 * mbar * c1 * i2 * ds2_i
            )
            dz[i] = hc_i + disp_i
        return alpha_hc + alpha_disp, da_drho, dz

    def _row_sum(self, T: float, z: np.ndarray, i: int, which: int) -> float:
        """sum_j z_j m_j (eps_ij/T)^which sigma_ij^3 — the dS/dz_i row sum."""
        total = 0.0
        for j in range(z.size):
            sigma_ij3 = (0.5 * (self._sigma[i] + self._sigma[j])) ** 3
            e_ij = math.sqrt(self._eps[i] * self._eps[j]) / T
            total += z[j] * self._m[j] * (e_ij if which == 1 else e_ij * e_ij) * sigma_ij3
        return total


class PCSaftWertheim:
    """The PC-SAFT association term: Wertheim TPT1 with the hard-sphere contact RDF.

    Delta^AiBj = g_hs^ij(eta) * [exp(eps_AB/(k T)) - 1] * kappa_AB * sigma_ij^3
    (Gross & Sadowski 2001, eq. A.25 with the contact RDF of eq. A.7; the
    association term itself is the same Michelsen-Hendriks sum every row shares).
    Cross-association follows G&S 2002 eqs. 2-3: epsilon arithmetic mean, kappa
    geometric mean, sigma_ij arithmetic mean — no additional binary parameter.
    The site-fraction solver and alpha summation are the shared ones above; this
    class supplies only the Delta builder and its closed-form rho / composition
    derivatives (g depends on the state through zeta_2 and zeta_3 only).
    """

    def __init__(self, params: list[dict[str, Any]]) -> None:
        self.params = params
        self._m = np.array([float(p["m"]) for p in params])
        self._sigma = np.array([float(p["sigma_Angstrom"]) for p in params])
        self._delta_t_cache: dict[tuple[float, bytes], np.ndarray] = {}

    def _site_iter(self) -> list[tuple[int, str]]:
        return [(i, t) for i, p in enumerate(self.params) for t in p["sites"]]

    def _site_weights(self, z: np.ndarray) -> np.ndarray:
        return np.array([z[i] for i, _t in self._site_iter()])

    def _delta_t_matrix(self, T: float, z: np.ndarray) -> np.ndarray:
        """Temperature-only association strength [exp(eps_AB/(kT))-1] kappa_AB sigma_ij^3, A^3.

        Pure function of (T, z) and memoized (the CPAWertheim pattern): density
        scans rebuild Delta at ~60-100 densities per scan and only the RDF factor
        changes with rho.
        """
        key = (round(T, 12), z.tobytes())
        cached = self._delta_t_cache.get(key)
        if cached is not None:
            return cached
        sites = self._site_iter()
        out = np.zeros((len(sites), len(sites)))
        for a, (ia, ta) in enumerate(sites):
            pa = self.params[ia]
            for b, (ib, tb) in enumerate(sites):
                if not ((ta == "d" and tb == "a") or (ta == "a" and tb == "d")):
                    continue
                pb = self.params[ib]
                if ia == ib:
                    eps, kappa = float(pa["epsilon_AB_over_k"]), float(pa["kappa_AB"])
                else:  # G&S 2002 eqs. 2-3 cross-association combining rules
                    eps = 0.5 * (float(pa["epsilon_AB_over_k"]) + float(pb["epsilon_AB_over_k"]))
                    kappa = math.sqrt(float(pa["kappa_AB"]) * float(pb["kappa_AB"]))
                sigma_ij3 = (0.5 * (self._sigma[ia] + self._sigma[ib])) ** 3
                out[a, b] = (math.exp(eps / T) - 1.0) * kappa * sigma_ij3
        self._delta_t_cache[key] = out
        return out

    def _d(self, T: float) -> np.ndarray:
        eps = np.array([float(p["epsilon_over_k"]) for p in self.params])
        return self._sigma * (1.0 - 0.12 * np.exp(-3.0 * eps / T))

    def _g_terms(
        self, d: np.ndarray, zeta2: float, zeta3: float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """g_hs^ij over the site list and its dzeta_2 / dzeta_3 partials (eq. A.7).

        With c1_ab = d_i d_j/(d_i+d_j): g = u^-1 + c1 (3 zeta_2) u^-2
        + c1^2 (2 zeta_2^2) u^-3.
        """
        sites = self._site_iter()
        ns = len(sites)
        u = 1.0 - zeta3
        g = np.zeros((ns, ns))
        dg2 = np.zeros((ns, ns))
        dg3 = np.zeros((ns, ns))
        for a, (ia, _ta) in enumerate(sites):
            for b, (ib, _tb) in enumerate(sites):
                c1 = d[ia] * d[ib] / (d[ia] + d[ib])
                c2 = c1 * c1
                g[a, b] = 1.0 / u + c1 * 3.0 * zeta2 / u**2 + c2 * 2.0 * zeta2 * zeta2 / u**3
                dg2[a, b] = c1 * 3.0 / u**2 + c2 * 4.0 * zeta2 / u**3
                dg3[a, b] = 1.0 / u**2 + c1 * 6.0 * zeta2 / u**3 + c2 * 6.0 * zeta2 * zeta2 / u**4
        return g, dg2, dg3

    def _zeta(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """zeta_2, zeta_3 and the segment diameters (eqs. A.8-A.9)."""
        d = self._d(T)
        rho_a3 = rho * _MOL_TO_A3
        zeta2 = np.pi / 6.0 * rho_a3 * float(np.sum(z * self._m * d**2))
        zeta3 = np.pi / 6.0 * rho_a3 * float(np.sum(z * self._m * d**3))
        return zeta2, zeta3, d

    def _delta_matrix(
        self, T: float, rho: float, z: np.ndarray
    ) -> tuple[np.ndarray, float, float, np.ndarray]:
        """Delta^AiBj in m^3/mol over the site list, plus (zeta_2, zeta_3, d)."""
        zeta2, zeta3, d = self._zeta(T, rho, z)
        g, _dg2, _dg3 = self._g_terms(d, zeta2, zeta3)
        return g * self._delta_t_matrix(T, z) * _MOL_TO_A3, zeta2, zeta3, d

    def alpha(self, T: float, rho: float, z: np.ndarray) -> float:
        """A_assoc/(N R T) at (T, rho, z)."""
        delta, _z2, _z3, _d = self._delta_matrix(T, rho, z)
        w = self._site_weights(z)
        x = solve_site_fractions(rho, delta, w)
        return alpha_assoc_value(w, x)

    def derivs(self, T: float, rho: float, z: np.ndarray) -> tuple[float, float, np.ndarray]:
        """A_assoc/(N R T) and its exact rho / composition derivatives at the fixed point.

        Returns ``(alpha, dalpha/drho, dalpha/dz_i)``. Same implicit
        differentiation of X = 1/(1 + rho Delta X w) as CPAWertheim.derivs; the
        Delta composition dependence runs through the RDF g(zeta_2, zeta_3)
        only (the Delta_T entries are pair constants), so dDelta/drho and
        dDelta/dz_i are closed-form chain rules over two moments.
        """
        sites = self._site_iter()
        w = self._site_weights(z)
        delta, zeta2, zeta3, d = self._delta_matrix(T, rho, z)
        g, dg2, dg3 = self._g_terms(d, zeta2, zeta3)
        big_d = rho * delta
        x = solve_site_fractions(rho, delta, w)
        xw = x * w
        big_n = big_d @ xw
        phi = np.log(x) - x / 2.0 + 0.5
        dphi = 1.0 / x - 0.5
        alpha = float(np.sum(w * phi))
        # dD/drho: D = rho g Delta_T, dg/drho = (dg2 zeta2 + dg3 zeta3)/rho
        dg_drho = (dg2 * zeta2 + dg3 * zeta3) / rho
        d_d_drho = delta * (1.0 + rho * dg_drho / g)
        # Jacobian of F_s = X_s (1 + N_s) - 1 wrt X, with N = (rho Delta)(X w)
        jac = np.diag(1.0 + big_n) + x[:, None] * big_d * w[None, :]
        ns = len(sites)
        rhs = np.zeros((ns, 1 + z.size))
        rhs[:, 0] = x * (d_d_drho @ xw)
        comp_of = [ia for ia, _t in sites]
        for i in range(z.size):
            # dDelta/dz_i = Delta * (dg2 dzeta2/dz_i + dg3 dzeta3/dz_i)/g
            rho_a3 = rho * _MOL_TO_A3
            dz2 = np.pi / 6.0 * rho_a3 * float(self._m[i]) * float(d[i] ** 2)
            dz3 = np.pi / 6.0 * rho_a3 * float(self._m[i]) * float(d[i] ** 3)
            dd_di = big_d * ((dg2 * dz2 + dg3 * dz3) / g)
            m_i = np.array([1.0 if comp_of[s] == i else 0.0 for s in range(ns)])
            rhs[:, 1 + i] = x * ((dd_di @ xw) + (big_d @ (x * m_i)))
        # (dF/dX) dX = -dF/explicit, solved for rho and every z_i at once
        dx = np.linalg.solve(jac, -rhs)
        dalpha_drho = float(np.sum(w * dphi * dx[:, 0]))
        dalpha_dz = np.zeros(z.size)
        for i in range(z.size):
            site_own = np.array([1.0 if comp_of[s] == i else 0.0 for s in range(ns)])
            dalpha_dz[i] = float(np.sum(site_own * phi + w * dphi * dx[:, 1 + i]))
        return alpha, dalpha_drho, dalpha_dz
