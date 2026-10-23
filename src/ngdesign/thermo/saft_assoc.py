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
