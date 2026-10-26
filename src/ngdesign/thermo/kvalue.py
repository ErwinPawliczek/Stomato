"""Classic K-value correlations (spec T-05).

Catalogue rows: ``chao-seader``, ``grayson-streed``, ``grayson-streed-extended``,
``braun-k10``, ``lee-kesler-ploecker``, ``esso-tabular``, ``antoine-ideal-k``,
``ideal-raoult``, ``henry-sander`` and ``ideal-lk``.

Method shapes (all K on the y/x convention):

- **gamma-phi** (``chao_seader``, ``grayson_streed``): ``K = nu0 * gamma / phi_hat``
  (Chao & Seader 1961) with the ``nu0`` pure-liquid fugacity coefficient from the
  coefficient tables, a regular-solution activity coefficient and the original
  Redlich-Kwong vapour fugacity coefficient.
- **lee_kesler_plocker**: ``K = phi_L / phi_V`` from the Lee-Kesler three-parameter
  corresponding-states EOS evaluated at Plöcker pseudo-critical conditions
  (Plöcker, Knapp & Prausnitz 1978; binary k_ij = 0).
- **ideal**: ``K = Psat / P`` (Raoult's law); Antoine WebBook coefficients where
  the row's basis declares them, the component databank vapour pressure otherwise.
- **henry_ideal**: Henry's law for the dilute acid gas (Versteeg & van Swaaij CO2
  constants) and Raoult's law for the remaining components.
- **braun_k10**: the low-pressure ideal-K asymptote of the Braun K10
  convergence-pressure charts (every convergence-pressure chart collapses to the
  ideal-K locus as P -> 0). The published chart parameterisation is proprietary;
  full digitisation stays blocked on a source (issue #139), so the row refuses
  service above 0.7 MPa where the convergence-pressure correction is no longer
  negligible.

Every row shares this base: Rachford-Rice PT flashes with successive-substitution
K updates, bubble/dew solves, TVF/PVF and PH/PS flashes, and Lee-Kesler departure
enthalpies/entropies (the ``EnthalpyMethod.LEE_KESLER`` basis, T-02's option
group) evaluated at Plöcker pseudo-critical conditions over ideal-gas Cp from the
component databank. Ideal-gas reference state for this family: H = S = 0 at
298.15 K, 101325 Pa — internal to these rows, not comparable across packages.

Parameter tables with per-table provenance live in ``data/thermo_params/kvalue/``.
Gamma-phi rows refuse feeds containing components without regular-solution
constants (pseudo-components, water, alcohols); the LKP row estimates a missing
pseudo-critical volume from the corresponding-states Zc relation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from typing import Any, ClassVar, cast

import yaml

from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import (
    PhaseProps,
    PropertyDerivatives,
    SaturationError,
    SaturationPoint,
)
from ngdesign.data import DATA_DIR
from ngdesign.thermo._state import (
    AQUEOUS_WATER_FRACTION,
    R_IDEAL,
    SlatePseudos,
    _records,
    _wilson_psat,
    support_ids,
)
from ngdesign.thermo.cubic import ThermoSurfaceMixin

#: Pressure above which the Braun K10 row refuses service: the charts' ideal-K
#: asymptote is only valid well below the 10 MPa convergence pressure.
_BRAUN_MAX_PA = 7.0e5

#: Perturbation for the composition derivatives of the LKP residual Gibbs surface.
_LKP_FD_EPS = 1.0e-5

#: Central-difference stencils for numeric Cp and ln-phi derivatives.
_CP_D_T = 0.25
_DERIV_D_T = 0.01
_DERIV_D_P_FRACTION = 1.0e-6

_PARAMS_DIR = DATA_DIR / "thermo_params" / "kvalue"


@cache
def _load_yaml(name: str) -> dict[str, Any]:
    raw = yaml.safe_load((_PARAMS_DIR / name).read_text())
    if not isinstance(raw, dict):
        raise RuntimeError(f"kvalue parameter table {name!r} is malformed")
    return cast(dict[str, Any], raw)


# -- Chao-Seader / Grayson-Streed correlations --------------------------------------


def _nu0(model: str, mw: float, omega_cs: float, T: float, P: float, tc: float, pc: float) -> float:
    """Pure-liquid fugacity coefficient f_L/P of the gamma-phi correlations.

    log10(nu0) = log10(nu0_0) + omega_cs * log10(nu0_1), with the coefficient sets
    and the set selection (by molar mass) from nu0.yaml (Chao & Seader 1961,
    Grayson & Streed 1963; see the table's provenance note).
    """
    table = _load_yaml("nu0.yaml")
    sets = cast(dict[str, Any], table["sets"])[model]
    selection = cast(dict[str, Any], table["selection"])
    key = (
        "hydrogen"
        if mw < selection["hydrogen_max_mw"]
        else ("methane" if mw < selection["methane_max_mw"] else "simple")
    )
    a = cast(list[float], sets[key])
    tr, pr = T / tc, P / pc
    log_nu0_0 = (
        a[0]
        + a[1] / tr
        + a[2] * tr
        + a[3] * tr**2
        + a[4] * tr**3
        + (a[5] + a[6] * tr + a[7] * tr**2) * pr
        + (a[8] + a[9] * tr) * pr**2
        - math.log10(pr)
    )
    b = cast(list[float], table["nu1"])
    log_nu0_1 = b[0] + b[1] * tr + b[2] / tr + b[3] * tr**3 + b[4] * (pr - 0.6)
    return float(10.0 ** (log_nu0_0 + omega_cs * log_nu0_1))


def _regular_solution_gammas(sup: _Support, x: list[float], T: float) -> list[float]:
    """Regular-solution ln gamma -> gamma (Scatchard-Hildebrand), per nu0's companion form.

    ln gamma_i = V_i (delta_i - delta_bar)^2 / (R T) with the volume-fraction-weighted
    mean solubility parameter delta_bar.
    """
    v = sup.rs_v
    d = sup.rs_delta
    assert v is not None and d is not None, "regular-solution constants missing for gamma evaluation"
    d_bar = sum(x[i] * v[i] * d[i] for i in range(len(x))) / sum(x[i] * v[i] for i in range(len(x)))
    return [math.exp(v[i] * (d[i] - d_bar) ** 2 / (R_IDEAL * T)) for i in range(len(x))]


def _rk_roots(a_mix: float, b_mix: float, A: float, B: float) -> list[float]:
    """Real roots of the original Redlich-Kwong cubic Z^3 - Z^2 + (A - B - B^2) Z - A B."""
    p = A - B - B**2
    depressed_p = p - 1.0 / 3.0
    depressed_q = -2.0 / 27.0 + p / 3.0 - A * B
    disc = (depressed_q / 2.0) ** 2 + (depressed_p / 3.0) ** 3
    roots: list[float] = []
    if disc > 0.0:
        sq = math.sqrt(disc)
        roots.append(_cbrt(-depressed_q / 2.0 + sq) + _cbrt(-depressed_q / 2.0 - sq) + 1.0 / 3.0)
    else:
        m = 2.0 * math.sqrt(-depressed_p / 3.0)
        arg = max(-1.0, min(1.0, 3.0 * depressed_q / (depressed_p * m)))
        theta = math.acos(arg) / 3.0
        for k in range(3):
            roots.append(m * math.cos(theta - 2.0 * math.pi * k / 3.0) + 1.0 / 3.0)
    return [z for z in roots if z > 0.0]


def _cbrt(value: float) -> float:
    return math.copysign(abs(value) ** (1.0 / 3.0), value)


def _rk_vapour(sup: _Support, y: list[float], T: float, P: float) -> tuple[float, list[float]]:
    """(Z, ln phi_i) of the original Redlich-Kwong EOS (k_ij = 0), largest root."""
    r2 = R_IDEAL**2
    sqrt_a = [
        math.sqrt(0.42748 * r2 * sup.tcs[i] ** 2.5 / (sup.pcs[i] * math.sqrt(T))) for i in range(len(y))
    ]
    b_i = [0.08664 * R_IDEAL * sup.tcs[i] / sup.pcs[i] for i in range(len(y))]
    a_mix = sum(y[i] * sqrt_a[i] for i in range(len(y))) ** 2
    b_mix = sum(y[i] * b_i[i] for i in range(len(y)))
    # sqrt_a carries the RK T^-0.5 temperature dependence, so A = a_mix*P/(R^2*T^2)
    # (the T^2.5 form belongs to the temperature-independent a_c convention).
    A = a_mix * P / (r2 * T**2)
    B = b_mix * P / (R_IDEAL * T)
    roots = _rk_roots(a_mix, b_mix, A, B)
    if not roots:
        raise ValueError(f"Redlich-Kwong cubic has no physical root at T={T} K, P={P} Pa")
    z = max(roots)
    ln_phi = [
        b_i[i] / b_mix * (z - 1.0)
        - math.log(z - B)
        - A / B * (2.0 * sqrt_a[i] / math.sqrt(a_mix) - b_i[i] / b_mix) * math.log(1.0 + B / z)
        for i in range(len(y))
    ]
    return z, ln_phi


# -- Lee-Kesler corresponding states -------------------------------------------------


def _lk_bcd(fluid: dict[str, float], tr: float) -> tuple[float, float, float]:
    b = fluid["b1"] - fluid["b2"] / tr - fluid["b3"] / tr**2 - fluid["b4"] / tr**3
    c = fluid["c1"] - fluid["c2"] / tr + fluid["c3"] / tr**3
    d = fluid["d1"] + fluid["d2"] / tr
    return b, c, d


def _lk_z_of_rho(fluid: dict[str, float], tr: float, rho_r: float) -> float:
    """Z at a given reduced density (rho_r = Vc/V = Z Pr/Tr) from the Lee-Kesler EOS."""
    b, c, d = _lk_bcd(fluid, tr)
    exp_term = math.exp(-fluid["gamma"] * rho_r**2)
    return (
        1.0
        + b * rho_r
        + c * rho_r**2
        + d * rho_r**5
        + fluid["c4"] / tr**3 * rho_r**2 * (fluid["beta"] + fluid["gamma"] * rho_r**2) * exp_term
    )


def _lk_mixed_z_of_rho(
    fluid0: dict[str, float], fluid1: dict[str, float], q: float, tr: float, rho_r: float
) -> float:
    """Z_eos(rho_r) of the one-fluid LKP blend: Z - 1 of the two fluids, omega-weighted.

    Lee-Kesler blends departure functions, not roots: the mixture EOS is the
    omega-weighted blend of the two Z polynomials, solved once at a common root.
    """
    z0 = _lk_z_of_rho(fluid0, tr, rho_r)
    z1 = _lk_z_of_rho(fluid1, tr, rho_r)
    return 1.0 + (1.0 - q) * (z0 - 1.0) + q * (z1 - 1.0)


def _lk_mixed_roots(
    fluid0: dict[str, float], fluid1: dict[str, float], q: float, tr: float, pr: float
) -> tuple[float | None, float | None]:
    """(gas, liquid) reduced-density roots of the blended Lee-Kesler EOS.

    Scans a log grid of rho_r for sign changes of Z_eos(rho_r) - Pr/(rho_r Tr)
    and bisects each bracket; the smallest root is the vapour, the largest the
    liquid.
    """

    def residual(rho: float) -> float:
        return _lk_mixed_z_of_rho(fluid0, fluid1, q, tr, rho) - pr / (rho * tr)

    n_grid = 480
    lo = math.log(1.0e-6)
    hi = math.log(200.0)
    gas: float | None = None
    liquid: float | None = None
    prev_rho = math.exp(lo)
    prev_res = residual(prev_rho)
    for k in range(1, n_grid + 1):
        rho = math.exp(lo + (hi - lo) * k / n_grid)
        res = residual(rho)
        if prev_res == 0.0:
            root = prev_rho
        elif prev_res * res < 0.0:
            a, b_, fa = prev_rho, rho, prev_res
            for _ in range(100):
                mid = 0.5 * (a + b_)
                fm = residual(mid)
                if fa * fm <= 0.0:
                    b_ = mid
                else:
                    a, fa = mid, fm
            root = 0.5 * (a + b_)
        else:
            root = None
        if root is not None:
            if gas is None:
                gas = root
            liquid = root
        prev_rho, prev_res = rho, res
    return gas, liquid


def _lk_ares_rt(fluid: dict[str, float], tr: float, rho_r: float) -> float:
    """Residual Helmholtz A/(R T) of the Lee-Kesler EOS at (Tr, rho_r).

    A_res/(R T) = integral of (Z - 1) d rho_r / rho_r from 0 to rho_r (closed form;
    the exponential term integrates to
    (beta + 1)/(2 gamma) (1 - e^{-gamma rho_r^2}) - rho_r^2/2 e^{-gamma rho_r^2}).
    """
    b, c, d = _lk_bcd(fluid, tr)
    g = fluid["gamma"]
    exp_term = math.exp(-g * rho_r**2)
    i_exp = (fluid["beta"] + 1.0) / (2.0 * g) * (1.0 - exp_term) - rho_r**2 / 2.0 * exp_term
    return b * rho_r + c * rho_r**2 / 2.0 + d * rho_r**5 / 5.0 + fluid["c4"] / tr**3 * i_exp


def _lk_hres_rt(fluid: dict[str, float], tr: float, rho_r: float) -> float:
    """tau * d(alpha_r)/d(tau) of one Lee-Kesler fluid at (Tr, rho_r).

    H_res/(R T) = Z - 1 + tau d(alpha_r)/d(tau), with tau = 1/Tr and the
    temperature derivative taken at fixed reduced density (fixed volume).
    """
    tau = 1.0 / tr
    g = fluid["gamma"]
    exp_term = math.exp(-g * rho_r**2)
    i_exp = (fluid["beta"] + 1.0) / (2.0 * g) * (1.0 - exp_term) - rho_r**2 / 2.0 * exp_term
    return tau * (
        -rho_r * (fluid["b2"] + 2.0 * fluid["b3"] * tau + 3.0 * fluid["b4"] * tau**2)
        + rho_r**2 / 2.0 * (-fluid["c2"] + 3.0 * fluid["c3"] * tau**2)
        + rho_r**5 * fluid["d2"] / 5.0
        + 3.0 * fluid["c4"] * tau**2 * i_exp
    )


@cache
def _lk_fluids() -> tuple[dict[str, float], dict[str, float], float]:
    simple = cast(dict[str, Any], _load_yaml("lee_kesler.yaml")["simple"])
    reference = cast(dict[str, Any], _load_yaml("lee_kesler.yaml")["reference"])
    omega_ref = float(_load_yaml("lee_kesler.yaml")["omega_ref"])
    return (
        {k: float(v) for k, v in simple.items()},
        {k: float(v) for k, v in reference.items()},
        omega_ref,
    )


@dataclass
class _Support:
    """Per-support constants for one K-value package (built once per slate)."""

    ids: tuple[str, ...]
    tcs: list[float]
    pcs: list[float]
    mws: list[float]
    omegas: list[float]  # databank acentric factors (Lee-Kesler omega_m)
    vcs: list[float]  # critical volumes (estimated from Zc when the databank lacks them)
    cps: list[Any]  # ideal-gas heat capacity correlations
    vls: list[Any]  # saturated-liquid molar volume correlations
    vp: list[Any]  # vapour-pressure correlations (databank basis)
    antoine: list[dict[str, float] | None]  # WebBook Antoine constants per component
    henry: list[tuple[float, float] | None]  # (A, B) of H = A exp(B/T), Pa.m3/mol
    # regular-solution constants (gamma-phi rows only; None otherwise)
    rs_omega_cs: list[float] | None = None
    rs_v: list[float] | None = None
    rs_delta: list[float] | None = None

    @classmethod
    def build(cls, ids: tuple[str, ...], k_model: str, pseudos: SlatePseudos) -> _Support:
        from ngdesign.thermo import _state

        records = _records(ids, pseudos)
        constants, correlations = _state._constants_package(records)
        n = len(records)
        tcs = [float(r.Tc) for r in records]
        pcs = [float(r.Pc) for r in records]
        mws = [float(r.mw) for r in records]
        omegas = [float(r.omega) for r in records]
        vcs_raw = list(getattr(constants, "Vcs", [None] * n))
        vcs = [
            float(v) if v is not None else (0.2905 - 0.085 * omegas[i]) * R_IDEAL * tcs[i] / pcs[i]
            for i, v in enumerate(vcs_raw)
        ]
        cps = list(correlations.HeatCapacityGases)
        vls = list(correlations.VolumeLiquids)
        vps = list(correlations.VaporPressures)
        antoine: list[dict[str, float] | None] = []
        for vp_obj in vps:
            params = getattr(vp_obj, "Antoine_parameters", {}) or {}
            webbook = params.get("ANTOINE_WEBBOOK")
            antoine.append({k: float(v) for k, v in webbook.items()} if webbook else None)
        henry_table = _load_yaml("henry.yaml")["components"]
        henry = [
            (float(e["A"]), float(e["B"])) if (e := henry_table.get(cid)) is not None else None for cid in ids
        ]

        rs_omega_cs = rs_v = rs_delta = None
        if k_model in ("chao_seader", "grayson_streed"):
            table = _load_yaml("regular_solution.yaml")["components"]
            missing = [cid for cid in ids if cid not in table]
            if missing:
                raise ValueError(
                    f"no Chao-Seader/Grayson-Streed regular-solution constants for "
                    f"{', '.join(missing)}; extend data/thermo_params/kvalue/regular_solution.yaml "
                    f"from a cited source (pseudo-components, water and alcohols are outside "
                    f"the correlation's scope)"
                )
            rs_omega_cs = [float(table[cid]["omega_cs"]) for cid in ids]
            rs_v = [float(table[cid]["v_liq"]) for cid in ids]
            rs_delta = [float(table[cid]["delta"]) for cid in ids]
        return cls(
            ids=ids,
            tcs=tcs,
            pcs=pcs,
            mws=mws,
            omegas=omegas,
            vcs=vcs,
            cps=cps,
            vls=vls,
            vp=vps,
            antoine=antoine,
            henry=henry,
            rs_omega_cs=rs_omega_cs,
            rs_v=rs_v,
            rs_delta=rs_delta,
        )

    def wilson_psat(self, i: int, T: float, pseudos: SlatePseudos) -> float:
        """Wilson vapour-pressure estimate, defined past Tc (bracket/K-estimate duty)."""
        return _wilson_psat(self.ids[i], T, pseudos)

    def databank_psat(self, i: int, T: float) -> float | None:
        prop = self.vp[i].T_dependent_property(T)
        return None if prop is None else float(prop)

    def antoine_psat(self, i: int, T: float) -> float | None:
        """WebBook Antoine pressure (Pa) when T is inside the correlation range."""
        a = self.antoine[i]
        if a is None or not a["Tmin"] <= T <= a["Tmax"]:
            return None
        return float(a["base"] ** (a["A"] - a["B"] / (T + a["C"])))

    def cp(self, i: int, T: float) -> float:
        """Ideal-gas Cp (J/(mol K)), clamped-flat outside the correlation range."""
        value = self.cps[i].T_dependent_property(T)
        if value is None:
            tmin = getattr(self.cps[i], "Tmin", None)
            tmax = getattr(self.cps[i], "Tmax", None)
            if tmin is not None and T < tmin:
                value = self.cps[i].T_dependent_property(float(tmin))
            elif tmax is not None and T > tmax:
                value = self.cps[i].T_dependent_property(float(tmax))
        if value is None:
            raise ValueError(f"no ideal-gas Cp for {self.ids[i]} at T={T} K")
        return float(value)

    def liquid_molar_volume(self, x: list[float], T: float) -> float:
        """Ideal-liquid mixture molar volume (m3/mol): mole-fraction-weighted databank volumes."""
        v_total = 0.0
        for i, xi in enumerate(x):
            v_i = self.vls[i].T_dependent_property(T)
            if v_i is None:
                raise ValueError(f"no liquid volume for {self.ids[i]} at T={T} K")
            v_total += xi * float(v_i)
        return v_total

    def pseudo_criticals(self, x: list[float]) -> tuple[float, float, float]:
        """Plöcker pseudo-criticals (Tcm [K], Pcm [Pa], omega_m) for the Lee-Kesler mixture."""
        n = len(x)
        v_ij = [
            [((self.vcs[i] ** (1.0 / 3.0) + self.vcs[j] ** (1.0 / 3.0)) / 2.0) ** 3 for j in range(n)]
            for i in range(n)
        ]
        vcm = sum(x[i] * x[j] * v_ij[i][j] for i in range(n) for j in range(n))
        tcm = (
            sum(
                x[i] * x[j] * math.sqrt(self.tcs[i] * self.tcs[j]) * v_ij[i][j]
                for i in range(n)
                for j in range(n)
            )
            / vcm
        )
        omega_m = sum(x[i] * self.omegas[i] for i in range(n))
        zcm = 0.2905 - 0.085 * omega_m
        pcm = zcm * R_IDEAL * tcm / vcm
        return tcm, pcm, omega_m

    def _lk_state(self, x: list[float], T: float, P: float, gas: bool) -> tuple[float, float, float] | None:
        """(Z, alpha_r, tau d alpha_r/d tau) of the LKP one-fluid mixture; None without a root.

        The departure functions are blended at the common reduced-density root of
        the blended EOS (Lee-Kesler one-fluid convention, teqp's LKP formulation).
        """
        f0, f1, omega_ref = _lk_fluids()
        tcm, pcm, omega_m = self.pseudo_criticals(x)
        tr, pr = T / tcm, P / pcm
        q = omega_m / omega_ref
        gas_root, liquid_root = _lk_mixed_roots(f0, f1, q, tr, pr)
        if gas_root is None:
            return None
        if gas_root == liquid_root:
            # Single EOS crossing: at the critical reduced density rho_r = 1 the
            # root is liquid-like above it and vapour-like below it, and the
            # other phase simply has no root at this state (metastable branches
            # vanish in the LKP blend well before the spinodal).
            root = gas_root
            if gas == (root > 1.0):
                return None
        else:
            if liquid_root is None:
                return None
            root = gas_root if gas else liquid_root
        z = pr / (root * tr)
        w = 1.0 - q
        ares = w * _lk_ares_rt(f0, tr, root) + q * _lk_ares_rt(f1, tr, root)
        hres = w * _lk_hres_rt(f0, tr, root) + q * _lk_hres_rt(f1, tr, root)
        return z, ares, hres

    def lk_mixture_gtilde(self, x: list[float], T: float, P: float, gas: bool) -> float | None:
        """Residual Gibbs G_res/(R T) = ln(phi_mix) of the LKP one-fluid mixture; None without a root."""
        state = self._lk_state(x, T, P, gas)
        if state is None:
            return None
        z, ares, _ = state
        return ares + z - 1.0 - math.log(z)

    def lk_mixture_z(self, x: list[float], T: float, P: float, gas: bool) -> float | None:
        """Compressibility factor of the LKP one-fluid mixture; None without a root."""
        state = self._lk_state(x, T, P, gas)
        return None if state is None else state[0]

    def lk_mixture_hres_rt(self, x: list[float], T: float, P: float, gas: bool) -> float | None:
        """(H - H_ig)/(R T) of the LKP one-fluid mixture; None without a root."""
        state = self._lk_state(x, T, P, gas)
        return None if state is None else state[0] - 1.0 + state[2]

    def lk_ln_phi(self, x: list[float], T: float, P: float, gas: bool) -> list[float]:
        """Per-component ln phi_i of the LKP one-fluid mixture.

        ln phi_i = d(n G_res/(R T))/d n_i of the corresponding-states residual Gibbs
        surface: partial molar values from central composition differences of
        ``lk_mixture_gtilde``. Exact Gibbs-Duhem consistency by construction.
        """
        g0 = self.lk_mixture_gtilde(x, T, P, gas)
        if g0 is None:
            raise ValueError(
                f"Lee-Kesler EOS has no {'vapour' if gas else 'liquid'} root at T={T} K, P={P} Pa"
            )
        n = len(x)
        d_g: list[float] = []
        for i in range(n):
            x_plus = list(x)
            x_plus[i] += _LKP_FD_EPS
            x_minus = list(x)
            x_minus[i] -= _LKP_FD_EPS
            norm_p = sum(x_plus)
            norm_m = sum(x_minus)
            g_plus = self.lk_mixture_gtilde([v / norm_p for v in x_plus], T, P, gas)
            g_minus = self.lk_mixture_gtilde([v / norm_m for v in x_minus], T, P, gas)
            if g_plus is None or g_minus is None:
                raise ValueError(f"Lee-Kesler root lost under composition perturbation at T={T} K")
            d_g.append((g_plus - g_minus) / (2.0 * _LKP_FD_EPS))
        total = sum(x[i] * d_g[i] for i in range(n))
        return [g0 + d_g[i] - total for i in range(n)]


# -- root finding (stdlib Brent, no scipy) -------------------------------------------


def _brentq(func: Any, a: float, b: float, xtol: float, rtol: float) -> float:
    """Root of func on a sign-changing bracket (Numerical Recipes `zbrent`)."""
    fa, fb = func(a), func(b)
    if fa * fb > 0.0:
        raise ValueError("root bracket does not change sign")
    c, fc = b, fb
    d = e = 0.0
    for _ in range(200):
        if (fb > 0.0 and fc > 0.0) or (fb < 0.0 and fc < 0.0):
            c, fc = a, fa
            d = e = b - a
        if abs(fc) < abs(fb):
            a, fa = b, fb
            b, fb = c, fc
            c, fc = a, fa
        tol1 = 2.0 * 2.22e-16 * abs(b) + 0.5 * xtol
        xm = 0.5 * (c - b)
        if abs(xm) <= tol1 or fb == 0.0:
            return b
        if abs(e) >= tol1 and abs(fa) > abs(fb):
            s = fb / fa
            if a == c:
                p = 2.0 * xm * s
                q = 1.0 - s
            else:
                q = fa / fc
                r = fb / fc
                p = s * (2.0 * xm * q * (q - r) - (b - a) * (r - 1.0))
                q = (q - 1.0) * (r - 1.0) * (s - 1.0)
            if p > 0.0:
                q = -q
            p = abs(p)
            if 2.0 * p < min(3.0 * xm * q - abs(tol1 * q), abs(e * q)):
                e = d
                d = p / q
            else:
                d = xm
                e = d
        else:
            d = xm
            e = d
        a, fa = b, fb
        if abs(d) > tol1:
            b += d
        else:
            b += tol1 if d > 0.0 else -tol1
        fb = func(b)
    return b


def _expand_bracket(func: Any, center: float, factor: float, low: float, high: float) -> tuple[float, float]:
    """Grow a log-spaced bracket around `center` until func changes sign (or fail)."""
    lo = max(center / factor, low)
    hi = min(center * factor, high)
    for _ in range(60):
        if func(lo) * func(hi) <= 0.0:
            return lo, hi
        lo = max(lo / factor, low)
        hi = min(hi * factor, high)
        if lo == low and hi == high:
            break
    raise SaturationError(
        f"no two-phase region found for the kvalue correlation between {low:g} and {high:g}"
    )


# -- the shared K-value package -------------------------------------------------------


class KValuePackage(ThermoSurfaceMixin):
    """Shared flash/enthalpy machinery for the classic K-value catalogue rows.

    Subclasses pin ``k_model`` (the K-value method) and, for the ideal rows, the
    ``psat_basis``. Enthalpies and entropies use the Lee-Kesler departures for
    every row (spec T-05's shared base).
    """

    k_model: ClassVar[str] = ""
    psat_basis: ClassVar[str] = "databank"

    def __init__(self) -> None:
        super().__init__()
        self._supports: dict[tuple[tuple[str, ...], SlatePseudos], _Support] = {}

    def _support(self, ids: tuple[str, ...]) -> _Support:
        key = (ids, self._slate_pseudos)
        sup = self._supports.get(key)
        if sup is None:
            sup = _Support.build(ids, self.k_model, self._slate_pseudos)
            self._supports[key] = sup
        return sup

    # -- K models ---------------------------------------------------------

    def _psat_basis_value(self, sup: _Support, i: int, T: float) -> float | None:
        """The row's own vapour-pressure basis (Antoine rows fall back to the databank)."""
        if self.psat_basis == "antoine":
            antoine = sup.antoine_psat(i, T)
            if antoine is not None:
                return antoine
        return sup.databank_psat(i, T)

    def _initial_k(self, sup: _Support, x: list[float], T: float, P: float) -> list[float]:
        """Wilson/Psat K estimate, defined for every component at any T (solver start)."""
        k: list[float] = []
        for i in range(len(x)):
            psat = sup.databank_psat(i, T)
            if psat is None:
                psat = sup.wilson_psat(i, T, self._slate_pseudos)
            k.append(psat / P)
        return k

    def _henry_k(self, sup: _Support, i: int, x: list[float], T: float, P: float) -> float | None:
        """Henry-law K for a component with a cited water Henry constant, else None."""
        entry = sup.henry[i]
        if entry is None:
            return None
        water = sup.ids.index("H2O") if "H2O" in sup.ids else None
        if water is None or x[water] <= 0.0:
            return None
        v_water = sup.vls[water].T_dependent_property(T)
        if v_water is None:
            return None
        h = entry[0] * math.exp(entry[1] / T)  # Pa.m3/mol
        c_liquid = 1.0 / float(v_water)  # mol/m3 of the aqueous phase
        return h * c_liquid / P

    def _model_k(self, sup: _Support, x: list[float], y: list[float], T: float, P: float) -> list[float]:
        """The row's K-values at (composition x liquid / y vapour, T, P)."""
        n = len(x)
        if self.k_model in ("chao_seader", "grayson_streed"):
            assert sup.rs_omega_cs is not None and sup.rs_v is not None and sup.rs_delta is not None
            _z_vap, ln_phi_v = _rk_vapour(sup, y, T, P)
            gammas = _regular_solution_gammas(sup, x, T)
            return [
                _nu0(
                    self.k_model,
                    sup.mws[i],
                    sup.rs_omega_cs[i],
                    T,
                    P,
                    sup.tcs[i],
                    sup.pcs[i],
                )
                * gammas[i]
                / math.exp(ln_phi_v[i])
                for i in range(n)
            ]
        if self.k_model == "lee_kesler_plocker":
            ln_phi_l = sup.lk_ln_phi(x, T, P, gas=False)
            ln_phi_v = sup.lk_ln_phi(y, T, P, gas=True)
            return [math.exp(ln_phi_l[i] - ln_phi_v[i]) for i in range(n)]
        if self.k_model in ("ideal", "braun_k10", "henry_ideal"):
            k: list[float] = []
            for i in range(n):
                if self.k_model == "henry_ideal":
                    henry = self._henry_k(sup, i, x, T, P)
                    if henry is not None:
                        k.append(henry)
                        continue
                if x[i] > 0.0:
                    # The Wilson estimate below is a solver start, never a K basis.
                    # A basis that is out of range or missing is a coverage refusal
                    # (recorded visibly by the audit's L4 sweep), not a default.
                    if T > sup.tcs[i]:
                        raise ValueError(
                            f"{self.k_model!r} K basis is undefined for {sup.ids[i]} at T={T} K: "
                            f"above its critical temperature {sup.tcs[i]:.1f} K the pure component "
                            f"has no vapour-pressure curve; refusing rather than defaulting - select "
                            f"a thermo model whose basis covers this state"
                        )
                    psat = self._psat_basis_value(sup, i, T)
                    if psat is None:
                        raise ValueError(
                            f"no vapour-pressure basis for {sup.ids[i]} at T={T} K on row basis "
                            f"{self.psat_basis!r}; refusing rather than defaulting - extend the row's "
                            f"basis table under data/thermo_params/kvalue/ from a cited source"
                        )
                else:
                    psat = self._psat_basis_value(sup, i, T)
                    if psat is None:
                        psat = sup.wilson_psat(i, T, self._slate_pseudos)
                k.append(psat / P)
            return k
        raise NotImplementedError(f"unknown k_model {self.k_model!r}")

    # -- enthalpy / entropy ------------------------------------------------

    def _h_ig(self, sup: _Support, x: list[float], T: float) -> float:
        """Ideal-gas enthalpy (J/mol) above the 298.15 K reference, Simpson-integrated."""
        if T == _REF_T:
            return 0.0
        n_steps = 32
        dt = (T - _REF_T) / n_steps
        total = 0.0
        for i, xi in enumerate(x):
            if xi <= 0.0:
                continue
            cp_sum = sup.cp(i, _REF_T) + sup.cp(i, T)
            for step in range(1, n_steps):
                cp_sum += (4.0 if step % 2 == 1 else 2.0) * sup.cp(i, _REF_T + step * dt)
            total += xi * cp_sum * dt / 3.0
        return total

    def _s_ig(self, sup: _Support, x: list[float], T: float, P: float) -> float:
        """Ideal-gas entropy (J/(mol K)) with mixing, above the 298.15 K / 101325 Pa reference."""
        n_steps = 32
        total = 0.0
        mixing = 0.0
        for i, xi in enumerate(x):
            if xi <= 0.0:
                continue
            t0, t1 = _REF_T, T
            ln_t0, ln_t1 = math.log(t0), math.log(t1)
            cp_sum = 0.0
            for step in range(n_steps + 1):
                t = math.exp(ln_t0 + (ln_t1 - ln_t0) * step / n_steps)
                weight = 1.0 if step in (0, n_steps) else (4.0 if step % 2 == 1 else 2.0)
                cp_sum += weight * sup.cp(i, t) / t
            integral = cp_sum * (ln_t1 - ln_t0) / 3.0
            total += xi * (integral - R_IDEAL * math.log(P / _REF_P))
            mixing += xi * math.log(xi) if xi > 0.0 else 0.0
        return total - R_IDEAL * mixing

    def _h_res(self, sup: _Support, x: list[float], T: float, P: float, gas: bool) -> float:
        """Lee-Kesler residual enthalpy (J/mol) at Plöcker pseudo-critical conditions."""
        hres_rt = sup.lk_mixture_hres_rt(x, T, P, gas)
        if hres_rt is None:
            raise ValueError(
                f"Lee-Kesler departure has no {'vapour' if gas else 'liquid'} root at T={T} K, P={P} Pa"
            )
        return hres_rt * R_IDEAL * T

    def _s_res(self, sup: _Support, x: list[float], T: float, P: float, gas: bool) -> float:
        """Lee-Kesler residual entropy: S_res/(R T) = H_res/(R T) - G_res/(R T)."""
        hres_rt = sup.lk_mixture_hres_rt(x, T, P, gas)
        gres_rt = sup.lk_mixture_gtilde(x, T, P, gas)
        if hres_rt is None or gres_rt is None:
            raise ValueError(
                f"Lee-Kesler departure has no {'vapour' if gas else 'liquid'} root at T={T} K, P={P} Pa"
            )
        return (hres_rt - gres_rt) * R_IDEAL

    # -- phase numbers ------------------------------------------------------

    def _liquid_ln_phi(self, sup: _Support, x: list[float], T: float, P: float) -> list[float]:
        """Liquid-phase ln fugacity coefficient per component (f_L/P of the row's basis)."""
        if self.k_model in ("chao_seader", "grayson_streed"):
            assert sup.rs_omega_cs is not None
            gammas = _regular_solution_gammas(sup, x, T)
            return [
                math.log(
                    _nu0(
                        self.k_model,
                        sup.mws[i],
                        sup.rs_omega_cs[i],
                        T,
                        P,
                        sup.tcs[i],
                        sup.pcs[i],
                    )
                    * gammas[i]
                )
                for i in range(len(x))
            ]
        if self.k_model == "lee_kesler_plocker":
            return sup.lk_ln_phi(x, T, P, gas=False)
        # ideal rows: phi_L = Psat/P (or Henry's K), so that K = phi_L / phi_V with phi_V = 1
        k = self._model_k(sup, x, x, T, P)
        return [math.log(k_i) for k_i in k]

    def _vapour_ln_phi(self, sup: _Support, y: list[float], T: float, P: float) -> list[float]:
        if self.k_model in ("chao_seader", "grayson_streed"):
            return [v for v in _rk_vapour(sup, y, T, P)[1]]
        if self.k_model == "lee_kesler_plocker":
            return sup.lk_ln_phi(y, T, P, gas=True)
        return [0.0] * len(y)  # ideal vapour

    def _vapour_z(self, sup: _Support, y: list[float], T: float, P: float) -> float:
        if self.k_model in ("chao_seader", "grayson_streed"):
            return _rk_vapour(sup, y, T, P)[0]
        if self.k_model == "lee_kesler_plocker":
            z = sup.lk_mixture_z(y, T, P, gas=True)
            if z is None:
                raise ValueError(f"Lee-Kesler vapour root missing at T={T} K, P={P} Pa")
            return z
        return 1.0  # ideal vapour

    def _kind_for(self, sup: _Support, x: list[float]) -> PhaseKind:
        """Aqueous when water dominates the phase, otherwise hc_liquid."""
        if "H2O" in sup.ids:
            i = sup.ids.index("H2O")
            if x[i] > AQUEOUS_WATER_FRACTION:
                return PhaseKind.AQUEOUS
        return PhaseKind.HC_LIQUID

    def _phase_props_values(
        self, sup: _Support, x: list[float], T: float, P: float, kind: PhaseKind
    ) -> tuple[float, float, float, float, float, list[float]]:
        """(z_factor, density, enthalpy, entropy, cp, ln_phi) of ONE phase at its own composition."""
        gas = kind == PhaseKind.VAPOR
        mw = sum(x[i] * sup.mws[i] for i in range(len(x)))
        if gas:
            z = self._vapour_z(sup, x, T, P)
            density = P * (mw / 1000.0) / (z * R_IDEAL * T)
            h = self._h_ig(sup, x, T) + self._h_res(sup, x, T, P, gas=True)
            s = self._s_ig(sup, x, T, P) + self._s_res(sup, x, T, P, gas=True)
            ln_phi = self._vapour_ln_phi(sup, x, T, P)
        else:
            if self.k_model == "lee_kesler_plocker":
                z_lk = sup.lk_mixture_z(x, T, P, gas=False)
                if z_lk is None:
                    raise ValueError(f"Lee-Kesler liquid root missing at T={T} K, P={P} Pa")
                z = z_lk
                v_molar = z * R_IDEAL * T / P
            else:
                v_molar = sup.liquid_molar_volume(x, T)
                z = P * v_molar / (R_IDEAL * T)
            density = mw / 1000.0 / v_molar
            h = self._h_ig(sup, x, T) + self._h_res(sup, x, T, P, gas=False)
            s = self._s_ig(sup, x, T, P) + self._s_res(sup, x, T, P, gas=False)
            ln_phi = self._liquid_ln_phi(sup, x, T, P)
        h_plus = self._phase_enthalpy(sup, x, T + _CP_D_T, P, kind)
        h_minus = self._phase_enthalpy(sup, x, T - _CP_D_T, P, kind)
        cp = (h_plus - h_minus) / (2.0 * _CP_D_T)
        return z, density, h, s, cp, ln_phi

    def _phase_enthalpy(self, sup: _Support, x: list[float], T: float, P: float, kind: PhaseKind) -> float:
        gas = kind == PhaseKind.VAPOR
        return self._h_ig(sup, x, T) + self._h_res(sup, x, T, P, gas=gas)

    # -- StreamState assembly ------------------------------------------------

    def _phase(
        self,
        sup: _Support,
        comp: dict[str, float],
        T: float,
        P: float,
        kind: PhaseKind,
        mole_fraction: float,
    ) -> Phase:
        ids = sup.ids
        x = [comp.get(cid, 0.0) for cid in ids]
        z, density, h, s, cp, ln_phi = self._phase_props_values(sup, x, T, P, kind)
        mw = sum(x[i] * sup.mws[i] for i in range(len(x)))
        return Phase(
            kind=kind,
            mole_fraction=mole_fraction,
            composition={cid: float(comp.get(cid, 0.0)) for cid in comp},
            molecular_weight=mw,
            density=density,
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z,
            viscosity=None,
            ln_phi={cid: 0.0 for cid in comp} | {cid: ln_phi[i] for i, cid in enumerate(ids)},
        )

    def _state_from_split(
        self,
        sup: _Support,
        z: dict[str, float],
        T: float,
        P: float,
        molar_flow: float,
        beta: float,
        x: dict[str, float],
        y: dict[str, float],
    ) -> StreamState:
        phases: list[Phase] = []
        enthalpy = 0.0
        entropy = 0.0
        if beta > 0.0:
            phases.append(self._phase(sup, y, T, P, PhaseKind.VAPOR, beta))
            enthalpy += beta * phases[-1].enthalpy
            entropy += beta * phases[-1].entropy
        if beta < 1.0:
            liquid_kind = self._kind_for(sup, [x[cid] for cid in sup.ids])
            phases.append(self._phase(sup, x, T, P, liquid_kind, 1.0 - beta))
            enthalpy += (1.0 - beta) * phases[-1].enthalpy
            entropy += (1.0 - beta) * phases[-1].entropy
        if not phases:
            raise ValueError(f"flash produced no phases at T={T} K, P={P} Pa")
        order = {k: i for i, k in enumerate((PhaseKind.VAPOR, PhaseKind.HC_LIQUID, PhaseKind.AQUEOUS))}
        phases.sort(key=lambda p: order[p.kind])
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=beta,
            enthalpy=enthalpy,
            entropy=entropy,
            phases=phases,
        )

    def _single_phase_state(
        self,
        sup: _Support,
        z: dict[str, float],
        T: float,
        P: float,
        molar_flow: float,
        vapor: bool,
    ) -> StreamState:
        x_vec = [z[cid] for cid in sup.ids]
        if vapor:
            return self._state_from_split(sup, z, T, P, molar_flow, 1.0, dict(z), dict(z))
        kind = self._kind_for(sup, x_vec)
        phase = self._phase(sup, dict(z), T, P, kind, 1.0)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=0.0,
            enthalpy=phase.enthalpy,
            entropy=phase.entropy,
            phases=[phase],
        )

    # -- flashes -------------------------------------------------------------

    def _rr_beta(self, sup: _Support, zi: list[float], k: list[float]) -> float:
        """Rachford-Rice vapour fraction by bisection (f is strictly decreasing)."""

        def f(beta: float) -> float:
            return sum(zi[i] * (k[i] - 1.0) / (1.0 + beta * (k[i] - 1.0)) for i in range(len(zi)))

        return _brentq(f, 0.0, 1.0, 1.0e-13, 1.0e-14)

    def _check_pressure(self, P: float) -> None:
        if self.k_model == "braun_k10" and P > _BRAUN_MAX_PA:
            raise ValueError(
                f"braun-k10 serves only the low-pressure ideal-K asymptote of the Braun K10 "
                f"charts (P <= {_BRAUN_MAX_PA:g} Pa); got P={P:g} Pa. The digitised charts are "
                f"blocked on a published parameter source (issue #139)."
            )

    def _ss_loop(
        self,
        sup: _Support,
        zi: list[float],
        k: list[float],
        beta: float,
        T: float,
        P: float,
    ) -> tuple[list[float], float]:
        """Successive-substitution K refinement with Rachford-Rice beta updates (damped)."""
        x_vec = list(zi)
        y_vec = list(zi)
        for _ in range(60):
            x_vec = [zi[i] / (1.0 + beta * (k[i] - 1.0)) for i in range(len(zi))]
            sum_x = sum(x_vec)
            x_vec = [v / sum_x for v in x_vec]
            y_vec = [k[i] * x_vec[i] for i in range(len(zi))]
            sum_y = sum(y_vec)
            y_vec = [v / sum_y for v in y_vec]
            k_new = self._model_k(sup, x_vec, y_vec, T, P)
            err = sum(abs(k_new[i] - k[i]) / max(k_new[i], 1.0e-30) for i in range(len(zi)))
            k = [0.5 * (k[i] + k_new[i]) for i in range(len(zi))]
            if err < 1.0e-10:
                break
            beta = self._rr_beta(sup, zi, k)
        return k, beta

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: Rachford-Rice split with successive-substitution K updates."""
        self._check_pressure(P)
        key = ("pt", *_state_cache_key(z, T, P), float(molar_flow))
        return cast(StreamState, self._cached(key, lambda: self._flash_pt_compute(z, T, P, molar_flow)))

    def _flash_pt_compute(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        ids = support_ids(z)
        sup = self._support(ids)
        zi = [z[cid] for cid in ids]
        try:
            k = self._model_k(sup, zi, zi, T, P)
        except ValueError:
            # Lee-Kesler: the EOS has a single root at this state, so the stream
            # is single-phase; classify by whichever root does exist.
            vapor_exists = sup.lk_mixture_z(zi, T, P, gas=True) is not None
            return self._single_phase_state(sup, z, T, P, molar_flow, vapor=vapor_exists)
        sum_k = sum(zi[i] * k[i] for i in range(len(zi)))
        sum_k_inv = sum(zi[i] / k[i] for i in range(len(zi)))
        if sum_k <= 1.0:
            return self._single_phase_state(sup, z, T, P, molar_flow, vapor=False)
        if sum_k_inv <= 1.0:
            return self._single_phase_state(sup, z, T, P, molar_flow, vapor=True)

        beta = self._rr_beta(sup, zi, k)
        k, _beta = self._ss_loop(sup, zi, k, beta, T, P)
        beta = self._rr_beta(sup, zi, k)
        x_vec = [zi[i] / (1.0 + beta * (k[i] - 1.0)) for i in range(len(zi))]
        sum_x = sum(x_vec)
        x_vec = [v / sum_x for v in x_vec]
        y_vec = [k[i] * x_vec[i] for i in range(len(zi))]
        sum_y = sum(y_vec)
        y_vec = [v / sum_y for v in y_vec]
        x_comp = {cid: 0.0 for cid in z} | {cid: x_vec[i] for i, cid in enumerate(ids)}
        y_comp = {cid: 0.0 for cid in z} | {cid: y_vec[i] for i, cid in enumerate(ids)}
        return self._state_from_split(sup, z, T, P, molar_flow, beta, x_comp, y_comp)

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: solve T from P (Pa) and H (J/mol) on the isobaric enthalpy curve."""
        self._check_pressure(P)

        def f(t: float) -> float:
            return self.flash_pt(z, t, P, molar_flow).enthalpy - H

        lo, hi = _expand_bracket(f, 298.15, 2.0, 1.0, 3000.0)
        t = _brentq(f, lo, hi, 1.0e-9, 1.0e-14)
        return self.flash_pt(z, t, P, molar_flow)

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: solve T from P (Pa) and S (J/(mol K)) on the isobaric entropy curve."""
        self._check_pressure(P)

        def f(t: float) -> float:
            return self.flash_pt(z, t, P, molar_flow).entropy - S

        lo, hi = _expand_bracket(f, 298.15, 2.0, 1.0, 3000.0)
        t = _brentq(f, lo, hi, 1.0e-9, 1.0e-14)
        return self.flash_pt(z, t, P, molar_flow)

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: solve P between the dew and bubble pressures for vapour fraction vf."""
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        bubble = self.bubble_point(z, T=T)
        dew = self.dew_point(z, T=T)
        if vf <= 0.0:
            return self.flash_pt(z, T, bubble.P, molar_flow)
        if vf >= 1.0:
            return self.flash_pt(z, T, dew.P, molar_flow)

        def f(p: float) -> float:
            state = self.flash_pt(z, T, p, molar_flow)
            return state.vapor_fraction - vf

        p = _brentq(f, dew.P, bubble.P, 1.0e-7, 1.0e-12)
        return self.flash_pt(z, T, p, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: solve T between the bubble and dew temperatures for vapour fraction vf."""
        self._check_pressure(P)
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        bubble = self.bubble_point(z, P=P)
        dew = self.dew_point(z, P=P)
        if vf <= 0.0:
            return self.flash_pt(z, bubble.T, P, molar_flow)
        if vf >= 1.0:
            return self.flash_pt(z, dew.T, P, molar_flow)

        def f(t: float) -> float:
            state = self.flash_pt(z, t, P, molar_flow)
            return state.vapor_fraction - vf

        t = _brentq(f, bubble.T, dew.T, 1.0e-7, 1.0e-12)
        return self.flash_pt(z, t, P, molar_flow)

    # -- saturation ----------------------------------------------------------

    def _saturation_fallback(self, sup: _Support, x: list[float], T: float, P: float, dew: bool) -> float:
        """Signed residual push when the LKP phase pair collapsed to a single root.

        Below saturation the vapour-like root exists and the liquid branch does
        not; above it the roles swap.  A tiny constant of the physically correct
        sign keeps the bracketer away from the degenerate K == 1 zero.
        """
        vapor_exists = sup.lk_mixture_z(x, T, P, gas=True) is not None
        if dew:
            return -1.0e-3 if vapor_exists else 1.0e-3
        return 1.0e-3 if vapor_exists else -1.0e-3

    def _saturation_at_t(self, sup: _Support, z: dict[str, float], T: float, dew: bool) -> SaturationPoint:
        """Bubble/dew pressure at T by successive substitution on the incipient composition."""
        ids = sup.ids
        zi = [z[cid] for cid in ids]
        pressure = _estimate_pressure(sup, zi, T)
        try:
            k = self._model_k(sup, zi, zi, T, pressure)
        except ValueError:
            # The Wilson estimate can sit where the LKP EOS has a single root;
            # seed the loop from the databank/Wilson K-values instead.
            k = self._initial_k(sup, zi, T, pressure)
        for _ in range(100):
            # freeze the incipient composition, re-evaluate K at each trial pressure
            if dew:
                x_fixed = _normalized([zi[i] / k[i] for i in range(len(zi))])
                y_fixed = list(zi)
            else:
                x_fixed = list(zi)
                y_fixed = _normalized([zi[i] * k[i] for i in range(len(zi))])

            def f(p: float, x_f: list[float] = x_fixed, y_f: list[float] = y_fixed) -> float:
                try:
                    kk = self._model_k(sup, x_f, y_f, T, p)
                except ValueError:
                    # Single-root region: one phase has no root at this state, so
                    # push the bracket towards the two-phase side instead of
                    # returning a spurious exact zero (K collapses to 1 there).
                    return self._saturation_fallback(sup, x_f, T, p, dew)
                if dew:
                    return sum(zi[i] / kk[i] for i in range(len(zi))) - 1.0
                return sum(zi[i] * kk[i] for i in range(len(zi))) - 1.0

            lo, hi = _expand_bracket(f, pressure, 1.5, 1.0e-1, 1.0e9)
            pressure_new = _first_root(f, lo, hi)
            try:
                k_new = self._model_k(sup, x_fixed, y_fixed, T, pressure_new)
            except ValueError:
                # The Lee-Kesler two-phase region collapses before K crosses
                # unity at this temperature.
                raise SaturationError(
                    f"kvalue saturation at T={T} K: Lee-Kesler two-phase region "
                    "collapses before K crosses unity"
                ) from None
            k_err = sum(abs(k_new[i] - k[i]) / max(k_new[i], 1.0e-30) for i in range(len(zi)))
            converged = abs(pressure_new - pressure) / pressure < 1.0e-11 and k_err < 1.0e-10
            pressure, k = pressure_new, k_new
            if converged:
                break
        else:
            raise SaturationError(f"kvalue saturation at T={T} K did not converge")

        if dew:
            incipient = {
                cid: (zi[i] / k[i]) / sum(zi[j] / k[j] for j in range(len(zi))) for i, cid in enumerate(ids)
            }
        else:
            y_vap = [zi[i] * k[i] for i in range(len(zi))]
            norm = sum(y_vap)
            incipient = {cid: v / norm for cid, v in zip(ids, y_vap, strict=True)}
        return SaturationPoint(
            T=T,
            P=pressure,
            kind="dew" if dew else "bubble",
            incipient_composition=incipient,
        )

    def _saturation_at_p(self, sup: _Support, z: dict[str, float], P: float, dew: bool) -> SaturationPoint:
        """Bubble/dew temperature at P by successive substitution on T."""
        ids = sup.ids
        zi = [z[cid] for cid in ids]
        temperature = sum(zi[i] * sup.tcs[i] * 0.6 for i in range(len(zi)))
        try:
            k = self._model_k(sup, zi, zi, temperature, P)
        except ValueError:
            k = self._initial_k(sup, zi, temperature, P)
        for _ in range(100):
            # freeze the incipient composition, re-evaluate K at each trial temperature
            if dew:
                x_fixed = _normalized([zi[i] / k[i] for i in range(len(zi))])
                y_fixed = list(zi)
            else:
                x_fixed = list(zi)
                y_fixed = _normalized([zi[i] * k[i] for i in range(len(zi))])

            def f(t: float, x_f: list[float] = x_fixed, y_f: list[float] = y_fixed) -> float:
                try:
                    kk = self._model_k(sup, x_f, y_f, t, P)
                except ValueError:
                    return self._saturation_fallback(sup, x_f, t, P, dew)
                if dew:
                    return sum(zi[i] / kk[i] for i in range(len(zi))) - 1.0
                return sum(zi[i] * kk[i] for i in range(len(zi))) - 1.0

            lo, hi = _expand_bracket(f, temperature, 1.1, 10.0, 2000.0)
            t_new = _first_root(f, lo, hi)
            try:
                k_new = self._model_k(sup, x_fixed, y_fixed, t_new, P)
            except ValueError:
                # The Lee-Kesler two-phase region collapses before K crosses
                # unity at this pressure.
                raise SaturationError(
                    f"kvalue saturation at P={P} Pa: Lee-Kesler two-phase region "
                    "collapses before K crosses unity"
                ) from None
            converged = (
                abs(t_new - temperature) / temperature < 1.0e-11
                and sum(abs(k_new[i] - k[i]) / max(k_new[i], 1.0e-30) for i in range(len(zi))) < 1.0e-10
            )
            temperature, k = t_new, k_new
            if converged:
                return self._saturation_at_t(sup, z, temperature, dew)
        raise SaturationError(f"kvalue saturation at P={P} Pa did not converge")

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point of the feed; exactly one of T (K) and P (Pa) given."""
        ids = support_ids(z)
        sup = self._support(ids)

        if (T is None) == (P is None):
            raise ValueError("bubble_point needs exactly one of T and P")
        if T is not None:
            self._check_single_region(z, T)
            return self._saturation_at_t(sup, z, T, dew=False)
        assert P is not None
        self._check_pressure(P)
        return self._saturation_at_p(sup, z, P, dew=False)

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point of the feed; exactly one of T (K) and P (Pa) given."""
        ids = support_ids(z)
        sup = self._support(ids)

        if (T is None) == (P is None):
            raise ValueError("dew_point needs exactly one of T and P")
        if T is not None:
            self._check_single_region(z, T)
            return self._saturation_at_t(sup, z, T, dew=True)
        assert P is not None
        self._check_pressure(P)
        return self._saturation_at_p(sup, z, P, dew=True)

    def _check_single_region(self, z: dict[str, float], T: float) -> None:
        """Refuse pure feeds at or above their critical temperature (no two-phase region)."""
        ids = support_ids(z)
        if len(ids) == 1:
            sup = self._support(ids)
            if T >= sup.tcs[0]:
                raise SaturationError(
                    f"{ids[0]} has no two-phase region at T={T} K (>= Tc = {sup.tcs[0]:g} K)"
                )

    # -- properties ------------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """Equilibrium K_i at a liquid composition (z, T, P), bubble-consistent.

        Chart-style references quote K against the liquid composition of the
        equilibrium pair, so gamma acts on the liquid z while the vapour phase is
        fixed by the bubble consistency y_i = K_i z_i / sum(K z) and phi_hat acts
        on that y. Returns None when the row's correlation is undefined at the
        state (missing component parameters, single EOS root, refused pressure).
        """
        ids = support_ids(z)
        sup = self._support(ids)
        zi = [z[cid] for cid in ids]
        self._check_pressure(P)
        if len(zi) == 1:
            # Pure feed: the two-phase region degenerates to the saturation point,
            # where x = y and K = 1 by construction (catalogue plan L0).
            return {ids[0]: 1.0}
        try:
            # Start from the psat/P K estimate: a correlation K evaluated with the
            # feed as the vapour composition sits on the liquid fugacity root for
            # near-bubble states and traps the y fixed point in that root.
            k = []
            for i in range(len(zi)):
                psat = self._psat_basis_value(sup, i, T)
                if psat is None:
                    psat = sup.wilson_psat(i, T, self._slate_pseudos)
                k.append(psat / P)
            y_vec = list(zi)
            for _ in range(60):
                y_vec = [k[i] * zi[i] for i in range(len(zi))]
                sum_y = sum(y_vec)
                y_vec = [v / sum_y for v in y_vec]
                k_new = self._model_k(sup, zi, y_vec, T, P)
                err = sum(abs(k_new[i] - k[i]) / max(k_new[i], 1.0e-30) for i in range(len(zi)))
                k = [0.5 * (k[i] + k_new[i]) for i in range(len(zi))]
                if err < 1.0e-10:
                    break
        except ValueError:
            return None
        return {cid: k[i] for i, cid in enumerate(ids)}

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        """Flashless single-phase properties at (composition, T, P) for the requested phase kind."""
        ids = support_ids(composition)
        sup = self._support(ids)
        x = [composition[cid] for cid in ids]
        z, density, h, s, cp, ln_phi = self._phase_props_values(sup, x, T, P, kind)
        mw = sum(x[i] * sup.mws[i] for i in range(len(x)))
        return PhaseProps(
            kind=kind,
            mole_fraction=1.0,
            composition={cid: float(composition.get(cid, 0.0)) for cid in composition},
            molecular_weight=mw,
            density=density,
            enthalpy=h,
            entropy=s,
            cp=cp,
            z_factor=z,
            gibbs=h - T * s,
            viscosity=None,
            ln_phi={cid: 0.0 for cid in composition} | {cid: ln_phi[i] for i, cid in enumerate(ids)},
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        """Numeric d ln phi / d(T, P) per component from the flashless phase properties."""
        h_t = _DERIV_D_T
        h_p = max(P * _DERIV_D_P_FRACTION, 1.0e-3)
        plus_t = self.phase_props(composition, T + h_t, P, kind).ln_phi
        minus_t = self.phase_props(composition, T - h_t, P, kind).ln_phi
        plus_p = self.phase_props(composition, T, P + h_p, kind).ln_phi
        minus_p = self.phase_props(composition, T, P - h_p, kind).ln_phi
        return PropertyDerivatives(
            dlnphi_dT={cid: (plus_t[cid] - minus_t[cid]) / (2.0 * h_t) for cid in composition},
            dlnphi_dP={cid: (plus_p[cid] - minus_p[cid]) / (2.0 * h_p) for cid in composition},
        )

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Vapour pressure (Pa) on the row's own basis; None at or above Tc for the databank basis."""
        support = self._support((cid,))
        i = support.ids.index(cid)
        return self._psat_basis_value(support, i, T)


_REF_T = 298.15
_REF_P = 101325.0


def _normalized(values: list[float]) -> list[float]:
    total = sum(values)
    return [v / total for v in values]


def _first_root(func: Any, low: float, high: float, slices: int = 96) -> float:
    """Lowest-value root of func in [low, high] by scanning for the first sign change.

    The Lee-Kesler residual can cross zero more than once: the physical
    bubble/dew crossing sits at the lowest pressure (or temperature), while
    further crossings near the loop-collapse boundary are degenerate K == 1
    artifacts where one phase loses its EOS root.
    """
    fa = func(low)
    if fa == 0.0:
        return low
    step = (high - low) / slices
    xb = low
    for _ in range(slices):
        fb = func(xb + step)
        if fa * fb < 0.0:
            return _brentq(func, xb, xb + step, 1.0e-9, 1.0e-14)
        fa, xb = fb, xb + step
    raise ValueError("root bracket does not change sign")


def _estimate_pressure(sup: _Support, zi: list[float], T: float) -> float:
    """Initial saturation-pressure estimate: the mole-fraction-weighted max Wilson Psat."""
    return max(sup.wilson_psat(i, T, ()) for i in range(len(zi))) * 1.2


def _state_cache_key(z: dict[str, float], T: float, P: float) -> tuple[Any, ...]:
    """Mirror of _state.cache_key (exact composition/T/P) to key the property cache."""
    from ngdesign.thermo import _state

    return _state.cache_key(z, T, P)


# -- row adapters ----------------------------------------------------------------------


class ChaoSeaderThermo(KValuePackage):
    """Chao-Seader K-values (nu0 + regular solution / original RK), hydrocarbon-light-gas service."""

    k_model = "chao_seader"


class GraysonStreedThermo(KValuePackage):
    """Grayson-Streed K-values (GS nu0 sets); the extended row shares this adapter."""

    k_model = "grayson_streed"


class LeeKeslerPloeckerThermo(KValuePackage):
    """Lee-Kesler-Plöcker corresponding-states K-values and departures (k_ij = 0)."""

    k_model = "lee_kesler_plocker"


class BraunK10Thermo(KValuePackage):
    """Braun K10 low-pressure limit (ideal-K asymptote of the K10 charts); refuses P > 0.7 MPa."""

    k_model = "braun_k10"


class IdealRaoultThermo(KValuePackage):
    """Ideal Raoult-law K-values on the databank vapour-pressure basis (rows ideal-raoult, ideal-lk)."""

    k_model = "ideal"
    psat_basis = "databank"


class AntoineIdealKThermo(KValuePackage):
    """Antoine-basis ideal K-values (rows antoine-ideal-k, esso-tabular)."""

    k_model = "ideal"
    psat_basis = "antoine"


class HenryIdealThermo(KValuePackage):
    """Henry's law for the dilute solutes (CH4, CO2; see henry.yaml) + Raoult for the rest."""

    k_model = "henry_ideal"
