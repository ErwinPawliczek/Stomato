"""BWR-family equations of state: Younglove-Ely MBWR-32 and BWR-Lee-Starling.

``MBWR32Package`` is the provisional ``mbwr`` catalogue row: the 32-term
Modified BWR of Younglove & Ely (1987), *J. Phys. Chem. Ref. Data* 16, 577,
pressure-form coefficients for methane, ethane and propane transcribed from
the report's Appendix J (NIST-hosted reprint), pure fluids only. The
coefficient tables were numerically verified two ways: the closed-form
residual-Helmholtz pressure integral against numerical integration, and
saturation against CoolProp 8.0.0 (worst sampled Psat deviation about 0.4%).
All 96 Appendix-J coefficients were later digit-verified against the printed
tables (pp. 794-796): the ethane G(3) entry had been mistranscribed and is
corrected here — finite-difference and consistency tests had passed on the
wrong value. One source caveat remains, not resolved in this work: selected
Younglove-Ely isobar cross-checks (propane 250 K, methane 100 K) disagree by
several percent for reasons not resolved here.

``BWRLeeStarlingPackage`` is the provisional ``bwr_ls`` catalogue row: the
BWR-Lee-Starling equation reusing the BWRS parameter-dictionary equations of
``helmholtz`` with Han-Starling generalised mixing. Its k_ij table is
deliberately empty (no verifiable open C1/C3 interaction set was found), and
with the table empty the mixing law reduces to the one used by ``bwrs`` - that
equivalence is the row's only tested claim; the k_ij dependence itself is
unvalidated. Four reference cases are bound (three pure-fluid saturation
points and one near-pure-propane C1/C3 VLE point): densities and pressures
track the reference data closely, but Cp comes out large and negative from the
shared BWRS parameter evaluation — the misses are bound and assessed per case,
not excluded, so the defect stays visible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Final

from ngdesign.contracts.thermo import SaturationError
from ngdesign.thermo._state import R_IDEAL
from ngdesign.thermo.helmholtz import (
    _BWRS_COMPONENTS,
    _BWRS_PAR,
    _BWRS_R,
    _IA,
    _IAL,
    _IAO,
    _IB,
    _IBO,
    _IC,
    _ICO,
    _ID,
    _IDO,
    _IEO,
    _IGA,
    BWRSPackage,
    ComponentNotSupported,
    _bwrs_a_res,
    _bwrs_h_dep,
    _bwrs_h_dep_j,
    _bwrs_lnphi,
    _bwrs_mix,
    _bwrs_pressure,
    _bwrs_root_between,
    _SinglePhase,
)

__all__ = [
    "BWRLeeStarlingPackage",
    "MBWR32Package",
]

# ---------------------------------------------------------------------------
# Younglove-Ely MBWR-32 (mbwr): Appendix J constants
# ---------------------------------------------------------------------------

_R_YE: Final[float] = 0.00831434  # MPa dm3/(mol K), the report's gas constant

#: The 32-term structure, Sec. 2.1: density power -> ((1-based G index), T power).
_YE_TERMS: Final[tuple[tuple[int, tuple[tuple[int, float], ...]], ...]] = (
    (2, ((1, 1.0), (2, 0.5), (3, 0.0), (4, -1.0), (5, -2.0))),
    (3, ((6, 1.0), (7, 0.0), (8, -1.0), (9, -2.0))),
    (4, ((10, 1.0), (11, 0.0), (12, -1.0))),
    (5, ((13, 0.0),)),
    (6, ((14, -1.0), (15, -2.0))),
    (7, ((16, -1.0),)),
    (8, ((17, -1.0), (18, -2.0))),
    (9, ((19, -2.0),)),
)
_YE_EXP_TERMS: Final[tuple[tuple[int, tuple[tuple[int, float], ...]], ...]] = (
    (3, ((20, -2.0), (21, -3.0))),
    (5, ((22, -2.0), (23, -4.0))),
    (7, ((24, -2.0), (25, -3.0))),
    (9, ((26, -2.0), (27, -4.0))),
    (11, ((28, -2.0), (29, -3.0))),
    (13, ((30, -2.0), (31, -3.0), (32, -4.0))),
)


@dataclass(frozen=True)
class _YEFluid:
    cid: str
    tc: float
    rhoc: float
    mw: float
    g: tuple[float, ...]
    src: str


_METHANE: Final[_YEFluid] = _YEFluid(
    cid="C1",
    tc=190.53,
    rhoc=10.150,
    mw=16.043,
    g=(
        0.9898937956e-5,
        0.2199608275e-1,
        -0.5322788000e0,
        0.2021657962e2,
        -0.2234398926e4,
        0.1067940280e-4,
        0.1457922469e-3,
        -0.9265816666e0,
        0.2915364732e3,
        0.2313546209e-6,
        0.1387214274e-3,
        0.4780467451e-2,
        0.1176103833e-4,
        -0.1982096730e-3,
        -0.2512887756e-1,
        0.9748899826e-5,
        -0.1202192137e-6,
        0.4128353939e-4,
        -0.7215842918e-6,
        0.5081738255e3,
        -0.9198903192e5,
        -0.2732264677e1,
        0.7499024351e5,
        0.1114060908e-2,
        0.1083955159e1,
        -0.4490960312e-4,
        -0.1380337847e1,
        -0.2371902232e-7,
        0.3761652197e-4,
        -0.2375166954e-9,
        -0.1237640790e-7,
        0.6766926453e-6,
    ),
    src="Appendix J, p. 794",
)

_ETHANE: Final[_YEFluid] = _YEFluid(
    cid="C2",
    tc=305.34,
    rhoc=6.875,
    mw=30.070,
    g=(
        -0.3204748852e-3,
        0.6529792241e-1,
        -0.1669704591e1,
        0.1147983381e3,
        -0.1854721998e5,
        0.4994149431e-4,
        -0.4858871291e-1,
        0.1225345776e2,
        0.8622615988e4,
        -0.1081290283e-5,
        0.6279096996e-2,
        -0.1716912675e1,
        -0.1640779401e-4,
        -0.4356516111e-2,
        -0.1966649699e1,
        0.4026724698e-3,
        -0.6498241861e-5,
        0.5111594139e-2,
        -0.1113010349e-3,
        -0.7157747547e3,
        -0.1848571024e7,
        -0.2137365569e3,
        0.6275079986e7,
        -0.9974911056e0,
        0.1129115014e3,
        -0.1026469558e-1,
        -0.5660525915e3,
        -0.4209846430e-4,
        0.2374523553e-1,
        -0.1289637823e-6,
        -0.5423801068e-4,
        0.2239717230e-2,
    ),
    src="Appendix J, p. 795",
)

_PROPANE: Final[_YEFluid] = _YEFluid(
    cid="C3",
    tc=369.85,
    rhoc=5.000,
    mw=44.097,
    g=(
        -0.2804337729e-3,
        0.1180666107e0,
        -0.3756325860e1,
        0.5624374521e3,
        -0.9354759605e5,
        -0.4557405505e-4,
        0.1530044332e0,
        -0.1078107476e3,
        0.2218072099e5,
        0.6629473971e-5,
        -0.6199354447e-2,
        0.6754207966e1,
        0.6472837570e-3,
        -0.6804325262e-1,
        -0.9726162355e1,
        0.5097956459e-2,
        -0.1004655900e-3,
        0.4363693352e-1,
        -0.1249351947e-2,
        0.2644755879e5,
        -0.7944237270e7,
        -0.7299920845e3,
        0.5381095003e8,
        0.3450217377e1,
        0.9936666689e3,
        -0.2166699036e0,
        -0.1612103424e5,
        -0.3633126990e-3,
        0.1108612343e1,
        -0.1330932838e-4,
        -0.3157701101e-2,
        0.1423083811e0,
    ),
    src="Appendix J, p. 796",
)

_YE_FLUIDS: Final[dict[str, _YEFluid]] = {f.cid: f for f in (_METHANE, _ETHANE, _PROPANE)}


def _ye_i_exp(rho: float, gam: float, j: int) -> float:
    u = rho * rho
    total = 0.0
    for m in range(j + 1):
        total += (-1.0) ** m * math.factorial(j) / (gam ** (m + 1) * math.factorial(j - m)) * u ** (j - m)
    return 0.5 * (math.exp(gam * u) * total - (-1.0) ** j * math.factorial(j) / gam ** (j + 1))


def _ye_state(fluid: _YEFluid, rho: float, T: float) -> tuple[float, float, float]:
    """Pressure (MPa), a_res/R (dimensionless), and d(a_res/R)/dT at (rho, T)."""
    g = fluid.g
    gam = -1.0 / fluid.rhoc**2
    p = rho * _R_YE * T
    phi = 0.0
    dphi = 0.0
    for k, terms in _YE_TERMS:
        rho_k = rho**k
        for gi, m in terms:
            c = g[gi - 1]
            p += rho_k * c * T**m
            f = rho ** (k - 1) * c * T ** (m - 1) / ((k - 1) * _R_YE)
            phi += f
            dphi += (m - 1.0) * f / T
    ex = math.exp(gam * rho * rho)
    for k, terms in _YE_EXP_TERMS:
        rho_k = rho**k
        i_n = _ye_i_exp(rho, gam, (k - 3) // 2)
        for gi, m in terms:
            c = g[gi - 1]
            p += rho_k * c * T**m * ex
            f = i_n * c * T ** (m - 1) / _R_YE
            phi += f
            dphi += (m - 1.0) * f / T
    return p, phi, dphi


def _ye_roots(fluid: _YEFluid, T: float, P: float) -> list[float]:
    """All density roots (mol/l) of P(rho) = P on a log scan of (1e-8, 4 rhoc)."""
    p_mpa = P / 1e6
    hi = 4.0 * fluid.rhoc
    roots: list[float] = []
    prev = 1e-8
    f_prev = _ye_state(fluid, prev, T)[0] - p_mpa
    steps = 240
    for i in range(1, steps + 1):
        r = 10.0 ** (-8.0 + (math.log10(hi) + 8.0) * i / steps)
        f_r = _ye_state(fluid, r, T)[0] - p_mpa
        if f_prev * f_r < 0.0:
            lo, hi_b = prev, r
            for _ in range(60):
                mid = 0.5 * (lo + hi_b)
                f_mid = _ye_state(fluid, mid, T)[0] - p_mpa
                if f_prev * f_mid <= 0.0:
                    hi_b = mid
                else:
                    lo, f_prev = mid, f_mid
            roots.append(0.5 * (lo + hi_b))
        prev, f_prev = r, f_r
    return roots


def _ye_root_between(fluid: _YEFluid, T: float, p_mpa: float, lo: float, hi: float) -> float:
    """Density root of P(rho) = p_mpa inside (lo, hi) by bisection."""
    f_lo = _ye_state(fluid, lo, T)[0] - p_mpa
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        f_mid = _ye_state(fluid, mid, T)[0] - p_mpa
        if f_lo * f_mid <= 0.0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


def _ye_psat(fluid: _YEFluid, T: float) -> float | None:
    """Pure saturation pressure (Pa) by equal-fugacity bisection, or None outside the dome."""
    grid = [10.0 ** (-8.0 + (math.log10(4.0 * fluid.rhoc) + 8.0) * i / 400.0) for i in range(401)]
    p_grid = [_ye_state(fluid, r, T)[0] for r in grid]
    i_max: int | None = None
    i_min: int | None = None
    for i in range(1, len(grid) - 1):
        if p_grid[i] > p_grid[i - 1] and p_grid[i] > p_grid[i + 1] and i_max is None:
            i_max = i
        if p_grid[i] < p_grid[i - 1] and p_grid[i] < p_grid[i + 1]:
            i_min = i
    if i_max is None or i_min is None or i_min <= i_max:
        return None
    p_vsp = p_grid[i_max]
    p_lsp = p_grid[i_min]
    if p_vsp <= 0.0:
        return None

    def g(p_mpa: float) -> float:
        rho_v = _ye_root_between(fluid, T, p_mpa, grid[0], grid[i_max])
        rho_l = _ye_root_between(fluid, T, p_mpa, grid[i_min], grid[-1])
        zv = p_mpa / (rho_v * _R_YE * T)
        zl = p_mpa / (rho_l * _R_YE * T)
        phi_v = _ye_state(fluid, rho_v, T)[1]
        phi_l = _ye_state(fluid, rho_l, T)[1]
        return (phi_l + zl - 1.0 - math.log(zl)) - (phi_v + zv - 1.0 - math.log(zv))

    p_lo, p_hi = max(p_lsp, 4.0 * p_grid[0]), p_vsp
    if p_lo >= p_hi:
        return None
    if g(p_lo) * g(p_hi) > 0.0:
        return None
    for _ in range(100):
        mid = 0.5 * (p_lo + p_hi)
        if g(p_lo) * g(mid) <= 0.0:
            p_hi = mid
        else:
            p_lo = mid
    return 0.5 * (p_lo + p_hi) * 1e6


class MBWR32Package(BWRSPackage):
    """Younglove-Ely 32-term MBWR for pure methane, ethane and propane.

    Inherits the ideal-gas correlation machinery from the BWRS surface; the
    EOS side is the Appendix J pressure form with rho in mol/l and P in MPa.
    Mixtures are refused: the report gives no mixing rules for these tables.
    """

    SUPPORTED: ClassVar[frozenset[str]] = frozenset(_YE_FLUIDS)

    def _require_pure(self, ids: tuple[str, ...]) -> _YEFluid:
        if len(ids) != 1:
            raise ComponentNotSupported(
                "MBWR-32 (Younglove-Ely) is a pure-fluid package; the report gives"
                f" no mixing rules for {sorted(ids)}"
            )
        return _YE_FLUIDS[ids[0]]

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        fluid = self._require_pure(ids)
        roots = _ye_roots(fluid, T, P)
        if not roots:
            raise SaturationError(f"MBWR-32 found no density root at T={T} K, P={P} Pa for {ids}")
        rho = roots[0] if phase == "vapor" else roots[-1]
        return self._props_at_root_ye(fluid, ids, xs, T, P, rho, phase)

    def _props_at_root_ye(
        self,
        fluid: _YEFluid,
        ids: tuple[str, ...],
        xs: tuple[float, ...],
        T: float,
        P: float,
        rho: float,
        phase: str,
    ) -> _SinglePhase:
        """Properties at a density root; ideal-gas reference as for ``bwrs``."""
        p_mpa, phi, dphi = _ye_state(fluid, rho, T)
        z = p_mpa / (rho * _R_YE * T)
        # departures from the verified a_res/R surface: u_res/(RT) = -T dphi/dT,
        # s_res/R = u_res/(RT) - a_res/R, h_res/(RT) = u_res/(RT) + Z - 1.
        u_dep_over_rt = -T * dphi
        h_dep_j = R_IDEAL * T * (u_dep_over_rt + z - 1.0)
        s_dep_over_r = u_dep_over_rt - phi
        cp_ig = self._cp_ig(ids, xs, T)
        h_ig = self._h_ig(ids, xs, T)
        s_ig = self._s_ig(ids, xs, T, P)
        h = h_ig + h_dep_j
        s = s_ig + s_dep_over_r * R_IDEAL
        cp = cp_ig + self._cp_dep_ye(fluid, ids, xs, T, P, phase)
        ln_phi = phi + z - 1.0 - math.log(z)
        mw = fluid.mw
        return _SinglePhase(
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            molecular_weight=mw,
            density=rho * mw,  # mol/l * g/mol -> g/l == kg/m3
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z,
            ln_phi={c: ln_phi for c in ids},
        )

    def _cp_dep_ye(
        self, fluid: _YEFluid, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> float:
        """Residual Cp as the central-difference slope of the departure enthalpy."""
        d_t = 0.5

        def h_dep(t: float) -> float:
            roots = _ye_roots(fluid, t, P)
            if not roots:
                raise SaturationError(f"MBWR-32 found no density root at T={t} K, P={P} Pa")
            r = roots[0] if phase == "vapor" else roots[-1]
            p_mpa, phi, dphi = _ye_state(fluid, r, t)
            z = p_mpa / (r * _R_YE * t)
            return R_IDEAL * t * (-t * dphi + z - 1.0)

        return (h_dep(T + d_t) - h_dep(T - d_t)) / (2.0 * d_t)

    def _psat(self, cid: str, T: float) -> float | None:
        if cid not in _YE_FLUIDS:  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"MBWR32Package has no parameters for component {cid!r}")
        return _ye_psat(_YE_FLUIDS[cid], T)


# ---------------------------------------------------------------------------
# BWR-Lee-Starling (bwr_ls): BWRS equations + Han-Starling generalised mixing
# ---------------------------------------------------------------------------

# Deliberately empty: no verifiable open C1/C3 Lee-Starling interaction set was
# found (spec T-16b). With every k_ij = 0 the mixing law below reduces to the
# one used by ``bwrs``; that equivalence is the row's only tested claim.
_LS_KIJ: Final[dict[tuple[str, str], float]] = {}


def _ls_mix(ids: tuple[str, ...], xs: tuple[float, ...]) -> dict[str, float]:
    """Han-Starling generalised mixing of the BWRS parameter dictionary.

    Quadratic parameters (Ao, Co, Do, Eo): double geometric sums with
    (1 - k_ij). Cubic parameters (a, b, c, d, al): triple cube-root sums with
    (1 - k_ij); ga: double square-root sum. With the k_ij table empty this
    delegates to the ``bwrs`` mixing implementation, so the empty-table limit
    is bit-identical to the tested BWRS path.
    """
    if not _LS_KIJ:
        return _bwrs_mix(ids, xs)
    names = [_BWRS_COMPONENTS[c] for c in ids]
    par = _BWRS_PAR
    bo = sum(xsi * par[n][_IBO] for xsi, n in zip(xs, names, strict=True))
    ao = co = do_ = eo = 0.0
    for i, xsi in enumerate(xs):
        for j, xsj in enumerate(xs):
            kij = _LS_KIJ.get((names[i], names[j]), 0.0)
            ao += xsi * xsj * (1.0 - kij) * math.sqrt(par[names[i]][_IAO] * par[names[j]][_IAO])
            co += xsi * xsj * (1.0 - kij) * math.sqrt(par[names[i]][_ICO] * par[names[j]][_ICO])
            do_ += xsi * xsj * (1.0 - kij) * math.sqrt(par[names[i]][_IDO] * par[names[j]][_IDO])
            eo += xsi * xsj * (1.0 - kij) * math.sqrt(par[names[i]][_IEO] * par[names[j]][_IEO])
    a3 = b3 = c3 = d3 = al3 = 0.0
    for i, xsi in enumerate(xs):
        for j, xsj in enumerate(xs):
            for k, xk in enumerate(xs):
                kij = _LS_KIJ.get((names[i], names[j]), 0.0)
                a3 += (
                    xsi
                    * xsj
                    * xk
                    * (1.0 - kij)
                    * (par[names[i]][_IA] * par[names[j]][_IA] * par[names[k]][_IA]) ** (1.0 / 3.0)
                )
                b3 += (
                    xsi
                    * xsj
                    * xk
                    * (1.0 - kij)
                    * (par[names[i]][_IB] * par[names[j]][_IB] * par[names[k]][_IB]) ** (1.0 / 3.0)
                )
                c3 += (
                    xsi
                    * xsj
                    * xk
                    * (1.0 - kij)
                    * (par[names[i]][_IC] * par[names[j]][_IC] * par[names[k]][_IC]) ** (1.0 / 3.0)
                )
                d3 += (
                    xsi
                    * xsj
                    * xk
                    * (1.0 - kij)
                    * (par[names[i]][_ID] * par[names[j]][_ID] * par[names[k]][_ID]) ** (1.0 / 3.0)
                )
                al3 += (
                    xsi
                    * xsj
                    * xk
                    * (1.0 - kij)
                    * (par[names[i]][_IAL] * par[names[j]][_IAL] * par[names[k]][_IAL]) ** (1.0 / 3.0)
                )
    ga2 = sum(xsi * par[n][_IGA] ** 0.5 for xsi, n in zip(xs, names, strict=True)) ** 2
    return {
        "Bo": bo,
        "Ao": ao,
        "Co": co,
        "Do": do_,
        "Eo": eo,
        "a": a3,
        "b": b3,
        "c": c3,
        "d": d3,
        "al": al3,
        "ga": ga2,
    }


class BWRLeeStarlingPackage(BWRSPackage):
    """BWR-Lee-Starling over the BWRS parameter dictionary, provisional.

    Reuses the merged BWRS pressure/Helmholtz/property equations; only the
    mixing step routes through :func:`_ls_mix`. The shipped k_ij table is
    empty, so every path reduces to the tested ``bwrs`` implementation.
    """

    SUPPORTED: ClassVar[frozenset[str]] = frozenset(_BWRS_COMPONENTS)

    def _ls_roots(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float) -> list[float]:
        """All density roots (lbmol/ft3) of P(rho) = P on a log scan of (1e-12, 3)."""
        p = _ls_mix(ids, xs)
        p_psia = P / 6894.757293168
        roots: list[float] = []
        prev = 1e-12
        f_prev = _bwrs_pressure(prev, T * 1.8, p) - p_psia
        for i in range(1, 401):
            r = 10.0 ** (-12.0 + (math.log10(3.0) + 12.0) * i / 400.0)
            f_r = _bwrs_pressure(r, T * 1.8, p) - p_psia
            if f_prev * f_r < 0.0:
                roots.append(_bwrs_root_between(p, T * 1.8, p_psia, prev, r))
            prev, f_prev = r, f_r
        return roots

    def _single_phase(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> _SinglePhase:
        roots = self._ls_roots(ids, xs, T, P)
        if not roots:
            raise SaturationError(f"BWR-Lee-Starling found no density root at T={T} K, P={P} Pa for {ids}")
        rho = roots[0] if phase == "vapor" else roots[-1]
        return self._props_at_root_ls(ids, xs, T, P, rho, phase)

    def _props_at_root_ls(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, rho: float, phase: str
    ) -> _SinglePhase:
        """Properties at a density root; ideal-gas reference as for ``bwrs``."""
        t_r = T * 1.8
        p_psia = P / 6894.757293168
        p_mix = _ls_mix(ids, xs)
        z = p_psia / (rho * _BWRS_R * t_r)
        a_res = _bwrs_a_res(rho, t_r, p_mix)
        h_dep_j = _bwrs_h_dep_j(rho, t_r, p_mix)
        u_dep_over_rt = _bwrs_h_dep(rho, t_r, p_mix) - (z - 1.0)
        s_dep_over_r = u_dep_over_rt - 2.0 * a_res
        cp_ig = self._cp_ig(ids, xs, T)
        h_ig = self._h_ig(ids, xs, T)
        s_ig = self._s_ig(ids, xs, T, P)
        h = h_ig + h_dep_j
        s = s_ig + s_dep_over_r * R_IDEAL
        cp = cp_ig + self._cp_dep(ids, xs, T, P, phase)
        ln_phi = self._ls_lnphi(ids, xs, rho, t_r, p_psia)
        mws = self._mws(ids)
        mw = sum(xsi * mw_i for xsi, mw_i in zip(xs, mws, strict=True))
        return _SinglePhase(
            composition={c: xsi for c, xsi in zip(ids, xs, strict=True)},
            molecular_weight=mw,
            density=rho * mw / 0.06242796,  # lbmol/ft3 -> kg/m3 (times g/mol / 1000 * 1000)
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z,
            ln_phi=ln_phi,
        )

    def _cp_dep(self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str) -> float:
        """Residual Cp as the central-difference slope of the departure enthalpy."""
        d_t = 0.5
        h0 = self._hdep_on_branch(ids, xs, T - d_t, P, phase)
        h1 = self._hdep_on_branch(ids, xs, T + d_t, P, phase)
        return (h1 - h0) / (2.0 * d_t)

    def _hdep_on_branch(
        self, ids: tuple[str, ...], xs: tuple[float, ...], T: float, P: float, phase: str
    ) -> float:
        """Departure enthalpy (J/mol) on the requested branch."""
        roots = self._ls_roots(ids, xs, T, P)
        if not roots:
            raise SaturationError(f"BWR-Lee-Starling found no density root at T={T} K, P={P} Pa for {ids}")
        rho = roots[0] if phase == "vapor" else roots[-1]
        t_r = T * 1.8
        return _bwrs_h_dep_j(rho, t_r, _ls_mix(ids, xs))

    def _ls_lnphi(
        self, ids: tuple[str, ...], xs: tuple[float, ...], rho: float, t_r: float, p_psia: float
    ) -> dict[str, float]:
        """Component ln phi: the BWRS analytic form on the (empty-kij) mixing path."""
        if _LS_KIJ:
            raise NotImplementedError(
                "Lee-Starling k_ij != 0 fugacity is not implemented; no validated"
                " interaction set exists (spec T-16b)"
            )
        return _bwrs_lnphi(ids, xs, rho, t_r, p_psia)

    def _psat(self, cid: str, T: float) -> float | None:
        if cid not in _BWRS_COMPONENTS:  # pragma: no cover - _support already refuses
            raise ComponentNotSupported(f"BWRLeeStarlingPackage has no parameters for {cid!r}")
        ids = (cid,)
        xs = (1.0,)
        t_r = T * 1.8
        p_mix = _ls_mix(ids, xs)
        grid = [10.0 ** (-12.0 + 15.0 * i / 1200.0) for i in range(1201)]
        p_grid = [_bwrs_pressure(r, t_r, p_mix) for r in grid]
        i_max: int | None = None
        i_min: int | None = None
        for i in range(1, len(grid) - 1):
            if p_grid[i] > p_grid[i - 1] and p_grid[i] > p_grid[i + 1] and i_max is None:
                i_max = i
            if p_grid[i] < p_grid[i - 1] and p_grid[i] < p_grid[i + 1]:
                i_min = i
        if i_max is None or i_min is None or i_min <= i_max:
            return None
        p_vsp = p_grid[i_max]
        p_lsp = p_grid[i_min]
        if p_vsp <= 0.0:
            return None

        def g(p_psia: float) -> float:
            rho_v = _bwrs_root_between(p_mix, t_r, p_psia, grid[0], grid[i_max])
            rho_l = _bwrs_root_between(p_mix, t_r, p_psia, grid[i_min], grid[-1])
            zv = p_psia / (rho_v * _BWRS_R * t_r)
            zl = p_psia / (rho_l * _BWRS_R * t_r)
            lnphi_v = _bwrs_a_res(rho_v, t_r, p_mix) + zv - 1.0 - math.log(zv)
            lnphi_l = _bwrs_a_res(rho_l, t_r, p_mix) + zl - 1.0 - math.log(zl)
            return lnphi_l - lnphi_v

        p_lo, p_hi = max(p_lsp, 1e-4), p_vsp
        if g(p_lo) * g(p_hi) > 0.0:
            return None
        for _ in range(200):
            mid = 0.5 * (p_lo + p_hi)
            g_mid = g(mid)
            if abs(g_mid) < 1e-12:
                return mid * 6894.757293168
            if g(p_lo) * g_mid <= 0.0:
                p_hi = mid
            else:
                p_lo = mid
        return 0.5 * (p_lo + p_hi) * 6894.757293168
