"""TSTMIX (Twu-Sim-Tassone) derivative regression: analytic vs central finite differences.

The TST repulsive term uses delta = 2.5 b and epsilon = -1.5 b^2, so thermo's
PR-convention (delta = 2b, epsilon = -b^2) derivative properties and PRMIX's
SymPy-derived dlnphis_dT/dlnphis_dP are wrong for TST. cubic.py overrides them;
these tests pin the corrections to finite differences so a thermo upgrade or a
refactor that reintroduces the PR forms fails loudly.
"""

from __future__ import annotations

import math

from ngdesign.thermo.cubic import TSTMIX

T = 300.0
P = 1.0e6
# Fitted propane/methane pair from the TST reference data.
TCS = [369.83, 190.56]
PCS = [4.248e6, 4.599e6]
OMEGAS = [0.152, 0.011]
ALPHA_0 = [0.856729, 0.937274, 0.617916]
ZS = [0.7, 0.3]


def _build(zs: list[float], t: float = T, p: float = P) -> TSTMIX:
    return TSTMIX(
        Tcs=TCS,
        Pcs=PCS,
        omegas=OMEGAS,
        zs=list(zs),
        alpha_coeffs=[ALPHA_0, None],
        T=t,
        P=p,
    )


def test_fitted_alpha_triplet_direct() -> None:
    """Fitted (l, m, n) triplet drives alpha: a = a_i * Tr^(m(n-1)) * exp(l(1-Tr^(m*n)))."""
    e = _build(ZS, t=350.0)
    tr = 350.0 / TCS[0]
    twu_l, twu_m, twu_n = ALPHA_0
    alpha = tr ** (twu_n * (twu_m - 1.0)) * math.exp(twu_l * (1.0 - tr ** (twu_n * twu_m)))
    # Component 0 carries the fitted triplet explicitly; component 1 has
    # alpha_coeffs=None and uses the generalized interpolation by omega,
    # selecting the sub- or supercritical pair by its own reduced temperature.
    a_i0 = 0.470507 * 8.31446261815324**2 * TCS[0] * TCS[0] / PCS[0]
    assert math.isclose(e.a_alphas[0], a_i0 * alpha, rel_tol=1e-12)

    def gen_alpha(lmn: tuple[float, float, float], tr: float) -> float:
        gl, gm, gn = lmn
        return float(tr ** (gn * (gm - 1.0)) * math.exp(gl * (1.0 - tr ** (gn * gm))))

    tr1 = 350.0 / TCS[1]
    if tr1 < 1.0:
        pair = ((0.125283, 0.911807, 1.948150), (0.511614, 0.784054, 2.812520))
    else:
        pair = ((0.401219, 4.963070, -0.2), (0.024955, 1.248089, -8.0))
    a_i1 = 0.470507 * 8.31446261815324**2 * TCS[1] * TCS[1] / PCS[1]
    alpha_1 = gen_alpha(pair[0], tr1) + OMEGAS[1] * (gen_alpha(pair[1], tr1) - gen_alpha(pair[0], tr1))
    assert math.isclose(e.a_alphas[1], a_i1 * alpha_1, rel_tol=1e-12)


def test_delta_epsilon_composition_derivatives_match_fd() -> None:
    e = _build(ZS)
    h = 1.0e-8
    for j in range(2):
        zp = list(ZS)
        zp[j] += h
        zm = list(ZS)
        zm[j] -= h
        ep, em = _build(zp), _build(zm)
        d_delta = (ep.delta - em.delta) / (2.0 * h)
        d_eps = (ep.epsilon - em.epsilon) / (2.0 * h)
        assert math.isclose(d_delta, e.ddelta_dzs[j], rel_tol=1e-6), j
        assert math.isclose(d_eps, e.depsilon_dzs[j], rel_tol=1e-6), j


def test_dlnphis_dT_matches_finite_difference() -> None:
    e = _build(ZS)
    h = 1.0e-4 * T
    ep, em = _build(ZS, t=T + 2.0 * h), _build(ZS, t=T - 2.0 * h)
    fd = [
        (a - b) / (4.0 * h)
        for a, b in zip(ep.fugacity_coefficients(ep.Z_g), em.fugacity_coefficients(em.Z_g), strict=True)
    ]
    ana = e.dlnphis_dT("g")
    for i in range(2):
        assert math.isclose(ana[i], fd[i], rel_tol=5.0e-3), i


def test_dlnphis_dP_matches_finite_difference() -> None:
    e = _build(ZS)
    h = 1.0e-4 * P
    ep, em = _build(ZS, p=P + 2.0 * h), _build(ZS, p=P - 2.0 * h)
    fd = [
        (a - b) / (4.0 * h)
        for a, b in zip(ep.fugacity_coefficients(ep.Z_g), em.fugacity_coefficients(em.Z_g), strict=True)
    ]
    ana = e.dlnphis_dP("g")
    for i in range(2):
        assert math.isclose(ana[i], fd[i], rel_tol=5.0e-3), i


def test_lnphi_matches_chemical_potential_consistency() -> None:
    """ln phi_i must equal d(n * G_dep)/dn_i / (R T) (central FD in mole numbers)."""
    e = _build(ZS)
    lnphi = e.fugacity_coefficients(e.Z_g)
    n = list(ZS)
    h = 1.0e-6
    for i in range(2):
        np_ = list(n)
        np_[i] += h
        nm = list(n)
        nm[i] -= h

        def total_g(ns: list[float]) -> float:
            total = sum(ns)
            eos = _build([x / total for x in ns])
            return total * float(eos.G_dep_g)

        mu = (total_g(np_) - total_g(nm)) / (2.0 * h) / 8.31446261815324 / T
        assert math.isclose(lnphi[i], mu, rel_tol=5.0e-3), i


def test_dlnphi_dzs_matches_g_dep_fd() -> None:
    """dlnphi_dzs is thermo's mixture form (1/RT) dG_dep/dz_j at fixed other zs."""
    e = _build(ZS)
    ana = e.dlnphi_dzs(e.Z_g)
    h = 1.0e-6
    rt = 8.31446261815324 * T
    for j in range(2):
        zp = list(ZS)
        zp[j] += h
        zm = list(ZS)
        zm[j] -= h
        gp = _build(zp).G_dep_g / rt
        gm = _build(zm).G_dep_g / rt
        fd = (gp - gm) / (2.0 * h)
        assert math.isclose(ana[j], fd, rel_tol=1.0e-5), j


def test_gibbs_duhem_consistency_of_fugacities() -> None:
    """Per-species composition derivatives must satisfy Gibbs-Duhem:
    sum_k z_k * dln(phi_k)/dz_j = 0 at fixed T, P (FD in each z_j, others fixed)."""
    h = 1.0e-7
    for j in range(2):
        zp = list(ZS)
        zp[j] += h
        zm = list(ZS)
        zm[j] -= h
        ep, em = _build(zp), _build(zm)
        a1 = ep.fugacity_coefficients(ep.Z_g)
        a0 = em.fugacity_coefficients(em.Z_g)
        col = [(a1[i] - a0[i]) / (2.0 * h) for i in range(2)]
        residual = sum(zs * d for zs, d in zip(ZS, col, strict=True))
        assert abs(residual) < 1.0e-3, (j, residual, col)
