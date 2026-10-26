"""General electrolyte property packages (spec T-09).

Four literature-anchored aqueous models,
implemented over the same carrier + K-value flash machinery as the amine
packages (``ngdesign.amine.package``):

* ``pitzer_nacl_water`` -- Pitzer NaCl(aq) with the classic 25 C parameter
  set: osmotic coefficient, mean ionic activity coefficient (exact
  Gibbs-Duhem integration of the osmotic form), water activity, and the
  solid-liquid saturation anchor (6.146 mol/kg at gamma = 1.0065; Pitzer,
  Peiper & Busey 1984).  See ``data/thermo_params/electrolyte/pitzer.yaml``.
* ``sour_water`` -- EPA-600/2-80-067 SWEQ (Wilson 1980) NH3-H2S-H2O
  speciation and equilibrium partial pressures, constants character-verified
  against the report's printed worked examples and cross-checked against
  DWSIM's transcription.  See
  ``data/thermo_params/electrolyte/reactions.yaml``.
* ``enrtl_nacl_water`` -- electrolyte-NRTL NaCl(aq): the Pitzer-Debye-Hueckel
  long-range term (Chen, Britt, Boston & Evans 1982) over the Chen & Evans
  1986 local-composition binary (tau transcribed via the open Kwaterski &
  Herri copy).  See ``data/thermo_params/electrolyte/enrtl.yaml``.
* ``ext_uniquac_nacl_water`` -- extended UNIQUAC NaCl(aq) (Thomsen &
  Rasmussen 1999 parameter set; formulation, infinite-dilution and
  molality-scale conventions per Leal et al. 2025).  See
  ``data/thermo_params/electrolyte/ext_uniquac.yaml``.

Streams stay molecular (ionic species never leave this module): the brine
model takes (H2O, NaCl), the sour-water model (H2O, NH3, H2S); anything else
refuses with the documented gap.  The CO2/carbonate path of the SWEQ model is
data-side only this cycle -- CO2 in a sour-water feed refuses with that reason.

Feeds without water flash on the carrier, so mixed flowsheets keep their
plain-cubic behaviour byte-identical.

SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, cast

import yaml

from ngdesign.amine.package import _phase, _registry_get
from ngdesign.amine.roots import brent_root
from ngdesign.contracts import PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import (
    PhaseProps,
    PropertyDerivatives,
    SaturationError,
    SaturationPoint,
)
from ngdesign.data import DATA_DIR, component_record
from ngdesign.registry import register
from ngdesign.thermo import _state
from ngdesign.thermo.saturation import solve_saturation

__all__ = [
    "ElectrolyteChemistryError",
    "ElectrolyteENRTLNaCl",
    "ElectrolyteExtUNIQUAC",
    "ElectrolytePitzerNaCl",
    "ElectrolyteSourWater",
    "SWEQConstants",
    "SWHenry",
    "SourWaterSpeciation",
    "enrtl_mean_gamma",
    "enrtl_osmotic",
    "enrtl_saturation_molality",
    "enrtl_water_activity",
    "ext_uniquac_mean_gamma",
    "ext_uniquac_osmotic",
    "ext_uniquac_saturation_molality",
    "ext_uniquac_water_activity",
    "pitzer_mean_gamma",
    "pitzer_osmotic",
    "pitzer_saturation_molality",
    "pitzer_water_activity",
    "sour_water_partial_pressures",
    "sour_water_speciation",
    "sweq_constants",
    "sweq_henry",
]

#: Parameter directory (data-side, cited in the files themselves).
_PARAMS_DIR = DATA_DIR / "thermo_params" / "electrolyte"

#: K-value ceiling for a volatile the liquid carries none of (its equilibrium
#: partial pressure is exactly zero): effectively all-vapour instead of zero,
#: which would divide by zero in the Rachford-Rice terms (the amine packages'
#: convention).
_ALL_VAPOR_K = 1e12

#: K-value floor for the involatile salt: effectively all-liquid.
_NONVOLATILE_K = 1e-12

#: Composition fixed-point tolerance (max mole-fraction change) and cap.
_FLASH_MAX_ITER = 50

#: Relative tolerance on the saturation unknown; interior vf edge targets.
_SATURATION_REL_TOL = 1e-8
_VF_EDGE = 1e-9

#: Numeric-derivative half step, K (the amine packages' Gibbs-Helmholtz step).
_DERIV_D_T = 0.5

#: Per-package property-cache size (P1-01's per-package LRU size).
_CACHE_SIZE = _state.PROPERTY_CACHE_SIZE

#: 1 psia in Pa (exact by definition of the pound-force inch-2).  The report's
#: Henry constants are psia per gmol/kg solution; the package surfaces Pa.
_PSIA_TO_PA = 6894.757293168

#: NaCl molality cap: the verified parameter domain ends at the 298.15 K
#: saturation (6.146 mol/kg); a nominal molality above it is outside the
#: single-liquid model, and the flash clamps to the saturated anchor (the
#: amine packages' loading-clamp precedent).
_MAX_MOLALITY = 6.15

#: Water molar mass on the molality basis the electrolyte anchor tables use
#: (kg/mol; mol water per kg solvent below), and its reciprocal.
_MW_WATER_KG = 0.018015268
_NW = 1.0 / _MW_WATER_KG

#: The fitted/verified chemistry windows per model (K), mirrored by the
#: catalogue rows' applicability T_K.  All three brine parameter sets are
#: the 25 C ones (temperature dependence enters only through Psat).
_MODEL_WINDOWS: dict[str, tuple[float, float]] = {
    "pitzer": (293.15, 303.15),
    "enrtl": (293.15, 303.15),
    "ext_uniquac": (293.15, 303.15),
    "sour_water": (293.15, 373.15),
}

#: Molecular support per model (stream keys; ionic species never leave).
_MODEL_SUPPORTS: dict[str, frozenset[str]] = {
    "pitzer": frozenset({"H2O", "NaCl"}),
    "enrtl": frozenset({"H2O", "NaCl"}),
    "ext_uniquac": frozenset({"H2O", "NaCl"}),
    "sour_water": frozenset({"H2O", "NH3", "H2S"}),
}

#: Brine models (involatile-salt paths).  Everything else with a window is
#: the sour-water chemistry.
_BRINE_MODELS: tuple[str, ...] = ("pitzer", "enrtl", "ext_uniquac")

#: First-use refusals: models whose open parameter bases are not verifiable
#: (the T-07 precedent: refuse, never silently idealize).  T-09b replaced the
#: last two entries (enrtl, ext_uniquac) with real parameter-backed models.
_REFUSALS: dict[str, str] = {}


class ElectrolyteChemistryError(ValueError):
    """The electrolyte chemistry left its fitted window.

    Typed subclass of ValueError (the contract's flash-failure type) so
    callers can distinguish a chemistry-window excursion from other flash
    failures; the message names the model, the window and the state.
    """


# -- Pitzer NaCl(aq) (classic 25 C parameter set) ---------------------------------


@cache
def _pitzer() -> dict[str, Any]:
    """Cached Pitzer parameter table (data/thermo_params/electrolyte/pitzer.yaml)."""
    with (_PARAMS_DIR / "pitzer.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


def pitzer_osmotic(molality: float) -> float:
    """Osmotic coefficient phi of NaCl(aq) at the 25 C parameter set.

    phi - 1 = -Aphi*sqrt(I)/(1 + b*sqrt(I)) + m*(beta0 + beta1*exp(-alpha*sqrt(I)))
              + m^2*Cphi, with I = m for the 1:1 electrolyte (molality basis,
    kg solvent per mol solute).
    """
    p = _pitzer()
    sq = math.sqrt(molality)
    return (
        1.0
        - float(p["aphi"]) * sq / (1.0 + float(p["b"]) * sq)
        + molality * (float(p["beta0"]) + float(p["beta1"]) * math.exp(-float(p["alpha"]) * sq))
        + molality * molality * float(p["cphi"])
    )


def pitzer_mean_gamma(molality: float) -> float:
    """Mean ionic activity coefficient of NaCl(aq) at the 25 C parameter set.

    Exact Gibbs-Duhem integration of the osmotic form above:

    ln gamma = (phi - 1) - Aphi*(2/b)*ln(1 + b*sqrt(I)) + beta0*m
               + beta1*(2/alpha^2)*(1 - (1 + alpha*sqrt(I))*exp(-alpha*sqrt(I)))
               + Cphi*m^2/2

    (the naive closed forms found in some secondary sources are not the
    integral of this osmotic expression and misestimate by up to ~10 %).
    """
    p = _pitzer()
    sq = math.sqrt(molality)
    aphi, b, alpha = float(p["aphi"]), float(p["b"]), float(p["alpha"])
    phi_minus_1 = (
        -aphi * sq / (1.0 + b * sq)
        + molality * (float(p["beta0"]) + float(p["beta1"]) * math.exp(-alpha * sq))
        + molality * molality * float(p["cphi"])
    )
    ln_gamma = (
        phi_minus_1
        - aphi * (2.0 / b) * math.log1p(b * sq)
        + float(p["beta0"]) * molality
        + float(p["beta1"]) * (2.0 / alpha**2) * (1.0 - (1.0 + alpha * sq) * math.exp(-alpha * sq))
        + float(p["cphi"]) * molality * molality / 2.0
    )
    return math.exp(ln_gamma)


def pitzer_water_activity(molality: float) -> float:
    """Water activity of NaCl(aq): a_w = exp(-2*m*phi/55.5084)."""
    molar_base = float(_pitzer()["molality_of_water"])
    return math.exp(-2.0 * molality * pitzer_osmotic(molality) / molar_base)


def pitzer_saturation_molality() -> float:
    """NaCl solubility (mol/kg) from the solid-liquid equilibrium condition.

    The SLE condition gamma_sat(m) == gamma(m) with the saturated-solution
    mean activity coefficient 1.0065 from the reference (p. 11); solved by
    bracketed root finding on the rising branch past 4 molal.
    """
    gamma_sat = float(_pitzer()["saturation"]["mean_gamma"])

    def residual(m: float) -> float:
        return pitzer_mean_gamma(m) - gamma_sat

    return brent_root(residual, 4.0, 10.0)


# -- eNRTL NaCl(aq) (Chen et al. 1982 PDH + Chen & Evans 1986 local composition) ----


@cache
def _enrtl() -> dict[str, Any]:
    """Cached eNRTL parameter table (data/thermo_params/electrolyte/enrtl.yaml)."""
    with (_PARAMS_DIR / "enrtl.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


def _enrtl_gE_rt(xw: float, xi: float) -> float:
    """G^E/RT per total mole on the effective-fraction basis (xw + 2*xi = 1).

    Long range: Pitzer-Debye-Hueckel on the mole-fraction basis (Chen, Britt,
    Boston & Evans 1982), A_phi = 0.392, closest-approach rho = 14.9.  Short
    range: the single-salt local-composition reduction of the Chen & Evans
    1986 binary (tau_CA,w = -4.5916, tau_w,CA = 9.0234, alpha = 0.2, G =
    exp(-alpha*tau)): a molecule cell and one ion cell per ion, X_CA = 2*xi,
    X_i = xi (derived from Kwaterski & Herri eq 25; the salt-side composition
    derivative of n*G^E returns ln gamma_Na + ln gamma_Cl for the 1:1 salt).
    """
    p = _enrtl()
    aphi, rho, alpha = float(p["aphi"]), float(p["rho"]), float(p["alpha"])
    ix = xi  # mole-fraction ionic strength (|z| = 1 for both ions)
    g_pdh = -4.0 * aphi / math.sqrt(_MW_WATER_KG) * (ix / rho) * math.log1p(rho * math.sqrt(ix))
    tau_caw, tau_wca = float(p["tau_ca_w"]), float(p["tau_w_ca"])
    g_c = math.exp(-alpha * tau_caw)
    g_w = math.exp(-alpha * tau_wca)
    x_ca = 2.0 * xi
    g_lc = xw * x_ca * g_c * tau_caw / (xw + x_ca * g_c) + x_ca * xw * g_w * tau_wca / (xw * g_w + xi)
    return g_pdh + g_lc


def _enrtl_ln_props(molality: float) -> tuple[float, float]:
    """(ln gamma+-(m), ln a_w) of NaCl(aq) at the 25 C parameter set.

    The composition derivatives of n*G^E/RT are numeric central differences
    (the closed local-composition derivatives of the reduced single-salt form
    are not published; the finite-difference form is pinned by the Gibbs-Duhem
    unit tests): the salt-side derivative returns ln gamma_Na + ln gamma_Cl in
    the SYMMETRIC rational convention, so the unsymmetric molality-scale mean
    takes the infinite-dilution difference and the ln x_w conversion
    (ln gamma+-(m) = ln gamma+-(x) - ln(1 + nu*m*M_w), worth ~22 % at 6 m);
    the water side is already symmetric-rational, so a_w = gamma_w * x_w.
    """
    h = 1e-6 * max(molality, 1e-3)

    def total(ms: float, mw: float = _NW) -> float:
        n = mw + 2.0 * ms
        return n * _enrtl_gE_rt(mw / n, ms / n)

    d_salt = (total(molality + h) - total(molality - h)) / (2.0 * h)
    d0 = (total(h) - total(0.0)) / h  # infinite-dilution reference (unsymmetric normalisation)
    dw = 1e-3
    d_w = (total(molality, _NW + dw) - total(molality, _NW - dw)) / (2.0 * dw)
    xw = _NW / (_NW + 2.0 * molality)
    ln_gamma_pm = 0.5 * (d_salt - d0) + math.log(xw)
    ln_aw = d_w + math.log(xw)
    return ln_gamma_pm, ln_aw


def enrtl_mean_gamma(molality: float) -> float:
    """Mean ionic activity coefficient of NaCl(aq), eNRTL 25 C parameter set.

    Applicability: literature-faithful to ~1-5 % vs the PPB84 anchors (the
    source model's own fit quality; the high-accuracy NaCl row is Pitzer).
    """
    return math.exp(_enrtl_ln_props(molality)[0])


def enrtl_water_activity(molality: float) -> float:
    """Water activity of NaCl(aq), eNRTL 25 C parameter set (a_w = gamma_w * x_w)."""
    return math.exp(_enrtl_ln_props(molality)[1])


def enrtl_osmotic(molality: float) -> float:
    """Osmotic coefficient phi = -ln a_w / (nu * m * M_w), eNRTL 25 C parameter set."""
    return -_enrtl_ln_props(molality)[1] / (2.0 * molality * _MW_WATER_KG)


def enrtl_saturation_molality() -> float:
    """NaCl solubility (mol/kg) from the SLE condition gamma(m) == 1.0065 (PPB84 p. 11)."""
    gamma_sat = float(_enrtl()["saturation"]["mean_gamma"])

    def residual(m: float) -> float:
        return enrtl_mean_gamma(m) - gamma_sat

    return brent_root(residual, 4.0, 10.0)


# -- extended UNIQUAC NaCl(aq) (Thomsen & Rasmussen 1999; formulation per Leal 2025) --


@cache
def _ext_uniquac() -> dict[str, Any]:
    """Cached extended-UNIQUAC parameter table (data/thermo_params/electrolyte/ext_uniquac.yaml)."""
    with (_PARAMS_DIR / "ext_uniquac.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


#: Species order of the extended-UNIQUAC parameter tables.
_EU_SPECIES: tuple[str, str, str] = ("H2O", "Na", "Cl")


def _eu_u_ij(p: dict[str, Any], k1: str, k2: str, t_k: float) -> float:
    """u_ji = u0_ji + u1_ji*(T - 298.15), symmetric pair lookup (Leal eq 24)."""
    u0, u1 = p["u0"], p["u1"]
    pair = f"{k1}-{k2}" if f"{k1}-{k2}" in u0 else f"{k2}-{k1}"
    return float(u0[pair]) + float(u1[pair]) * (t_k - 298.15)


def _eu_a_dh(t_k: float) -> float:
    """Extended-Debye-Hueckel A(T), (kg/mol)^0.5 (Sander et al. correlation as in Leal eq 40)."""
    a = _ext_uniquac()["dh"]["a"]
    t = t_k - 273.15
    return float(a["c0"]) + float(a["c1"]) * t + float(a["c2"]) * t * t


def _eu_state(
    molality: float, t_k: float
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, dict[str, float]]]:
    """(x, phi_, theta, psi[j][i]) over the species order (H2O, Na, Cl).

    Basis: 1 kg of water.  psi_ji = exp[(u_ii - u_ji)/T] (Leal eq 23; the
    division is by T, NOT RT -- the /RT reading of the J/mol table is the
    transcription error that broke the first prototype; cross-checked against
    Reaktoro ActivityModelExtendedUNIQUAC.cpp L249, used as a verification
    reference only).
    """
    p = _ext_uniquac()
    q: dict[str, float] = {k: float(v) for k, v in p["q"].items()}
    r: dict[str, float] = {k: float(v) for k, v in p["r"].items()}
    n = _NW + 2.0 * molality
    x = {"H2O": _NW / n, "Na": molality / n, "Cl": molality / n}
    rsum = sum(r[k] * x[k] for k in _EU_SPECIES)
    qsum = sum(q[k] * x[k] for k in _EU_SPECIES)
    phi_ = {k: x[k] * r[k] / rsum for k in _EU_SPECIES}
    theta = {k: x[k] * q[k] / qsum for k in _EU_SPECIES}
    psi: dict[str, dict[str, float]] = {}
    for j in _EU_SPECIES:
        psi[j] = {i: math.exp((_eu_u_ij(p, i, i, t_k) - _eu_u_ij(p, j, i, t_k)) / t_k) for i in _EU_SPECIES}
    return x, phi_, theta, psi


def _eu_ln_gamma_u(
    x: dict[str, float], phi_: dict[str, float], theta: dict[str, float], psi: dict[str, dict[str, float]]
) -> dict[str, float]:
    """Closed-form UNIQUAC (combinatorial + residual) ln gamma (Leal eq 43).

    The residual denominator S_j = sum_l theta_l * psi_lj -- the SAME
    orientation as the G^E; the transposed form fails the finite-difference
    check (verified to 6 decimals in all species and both directions).
    """
    p = _ext_uniquac()
    zc = float(p["zq"])
    q: dict[str, float] = {k: float(v) for k, v in p["q"].items()}
    out: dict[str, float] = {}
    for k in _EU_SPECIES:
        sk = sum(theta[j] * psi[j][k] for j in _EU_SPECIES)
        comb = (
            math.log(phi_[k] / x[k])
            + 1.0
            - phi_[k] / x[k]
            - (zc / 2.0) * q[k] * (math.log(phi_[k] / theta[k]) + 1.0 - phi_[k] / theta[k])
        )
        res_sum = sum(
            theta[j] * psi[k][j] / sum(theta[sp] * psi[sp][j] for sp in _EU_SPECIES) for j in _EU_SPECIES
        )
        res = q[k] * (1.0 - math.log(sk) - res_sum)
        out[k] = comb + res
    return out


def _eu_ln_gamma_inf(k: str, t_k: float) -> float:
    """Infinite-dilution (x_w -> 1) UNIQUAC ln gamma of solute k (Leal eq 44).

    The last term is q_k*[1 - ln psi_wk - psi_kw/psi_ww] with psi_ww = 1
    (Reaktoro L284, used as a verification reference only).
    """
    p = _ext_uniquac()
    zc = float(p["zq"])
    qw, rw = float(p["q"]["H2O"]), float(p["r"]["H2O"])
    qk, rk = float(p["q"][k]), float(p["r"][k])
    psi_wk = math.exp((_eu_u_ij(p, k, k, t_k) - _eu_u_ij(p, "H2O", k, t_k)) / t_k)
    psi_kw = math.exp((_eu_u_ij(p, "H2O", "H2O", t_k) - _eu_u_ij(p, k, "H2O", t_k)) / t_k)
    comb = (
        math.log(rk / rw)
        + 1.0
        - rk / rw
        - (zc / 2.0) * qk * (math.log(rk * qw / (rw * qk)) + 1.0 - rk * qw / (rw * qk))
    )
    return comb + qk * (1.0 - math.log(psi_wk) - psi_kw)  # psi_ww == 1


def _ext_uniquac_ln_props(molality: float, t_k: float) -> tuple[float, float]:
    """(ln gamma+-(m, T), ln a_w(m, T)) of NaCl(aq), extended-UNIQUAC.

    Assembly per Leal et al. 2025: ions ln gamma_i = ln gamma_i,DH +
    (ln gamma_i,U - ln gamma_i,U^inf) + ln x_w (eq 45, unsymmetric molality
    scale); water ln gamma_w = ln gamma_w,DH + ln gamma_w,U with
    a_w = gamma_w * x_w (eqs 46, 39).  The DH term (eq 40/42) uses
    b = 1.50 (kg/mol)^0.5 and A(T) in (kg/mol)^0.5.
    """
    p = _ext_uniquac()
    b_dh = float(p["dh"]["b"])
    x, _phi_, _theta, psi = _eu_state(molality, t_k)
    sq = math.sqrt(molality)  # ionic strength == molality for the 1:1 salt
    big = 1.0 + b_dh * sq
    a_dh = _eu_a_dh(t_k)
    ln_g_dh_ion = -a_dh * sq / big
    ln_g_dh_w = (2.0 * a_dh * _MW_WATER_KG / b_dh**3) * (big - 1.0 / big - 2.0 * math.log(big))
    ln_g_u = _eu_ln_gamma_u(x, _phi_, _theta, psi)
    xw = x["H2O"]
    ln_g_na = ln_g_dh_ion + ln_g_u["Na"] - _eu_ln_gamma_inf("Na", t_k) + math.log(xw)
    ln_g_cl = ln_g_dh_ion + ln_g_u["Cl"] - _eu_ln_gamma_inf("Cl", t_k) + math.log(xw)
    ln_g_w = ln_g_dh_w + ln_g_u["H2O"]
    return 0.5 * (ln_g_na + ln_g_cl), ln_g_w + math.log(xw)


def ext_uniquac_mean_gamma(molality: float, t_k: float = 298.15) -> float:
    """Mean ionic activity coefficient of NaCl(aq), extended-UNIQUAC (Thomsen params).

    Applicability: literature-faithful to a few % vs the PPB84 anchors (the
    source model's own fit quality; the high-accuracy NaCl row is Pitzer).
    """
    return math.exp(_ext_uniquac_ln_props(molality, t_k)[0])


def ext_uniquac_water_activity(molality: float, t_k: float = 298.15) -> float:
    """Water activity of NaCl(aq), extended-UNIQUAC (a_w = gamma_w * x_w)."""
    return math.exp(_ext_uniquac_ln_props(molality, t_k)[1])


def ext_uniquac_osmotic(molality: float, t_k: float = 298.15) -> float:
    """Osmotic coefficient phi = -ln a_w / (nu * m * M_w), extended-UNIQUAC."""
    return -_ext_uniquac_ln_props(molality, t_k)[1] / (2.0 * molality * _MW_WATER_KG)


def ext_uniquac_saturation_molality() -> float:
    """NaCl solubility (mol/kg) from the SLE condition gamma(m) == 1.0065 (PPB84 p. 11)."""
    gamma_sat = float(_ext_uniquac()["saturation"]["mean_gamma"])

    def residual(m: float) -> float:
        return ext_uniquac_mean_gamma(m) - gamma_sat

    return brent_root(residual, 4.0, 10.0)


# -- EPA-600/2-80-067 SWEQ sour-water chemistry -----------------------------------


@cache
def _reactions() -> dict[str, Any]:
    """Cached SWEQ constant tables (data/thermo_params/electrolyte/reactions.yaml)."""
    with (_PARAMS_DIR / "reactions.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


def _degR(t_k: float) -> float:
    """The report's temperature unit: degR = (degC + 273.15) * 1.8 = K * 1.8."""
    return t_k * 1.8


def _poly(coefs: dict[str, Any], t: float) -> float:
    """ln k = a + b/T + c/T^2 + d/T^3 + e/T^4 at degR temperature t."""
    out = float(coefs["a"]) + float(coefs["b"]) / t
    for key, power in (("c", 2), ("d", 3), ("e", 4)):
        if key in coefs:
            out += float(coefs[key]) / t**power
    return out


@dataclass(frozen=True)
class SWEQConstants:
    """Dimensionless SWEQ equilibrium constants at T (gmol/kg-solution basis)."""

    k_nh4: float  # k3: H+ + NH3 <=> NH4+ (association)
    k_h2s: float  # k5: H2S <=> HS- + H+
    k_hs: float  # k6: HS- <=> S2- + H+
    k_w: float  # k7: H2O <=> OH- + H+


def sweq_constants(t_k: float) -> SWEQConstants:
    """The four SWEQ reaction constants at T (K), from the report's polynomials."""
    t = _degR(t_k)
    r = _reactions()["reactions"]
    return SWEQConstants(
        k_nh4=math.exp(_poly(r["nh4_association"], t)),
        k_h2s=math.exp(_poly(r["h2s_dissociation"], t)),
        k_hs=math.exp(_poly(r["hs_dissociation"], t)),
        k_w=math.exp(_poly(r["water_dissociation"], t)),
    )


@dataclass(frozen=True)
class SWHenry:
    """SWEQ Henry constants (psia per gmol/kg solution) at T."""

    nh3: float
    h2s: float


def sweq_henry(t_k: float, cas: float, cs: float, cc: float = 0.0) -> SWHenry:
    """Henry constants at T (K) with the report's composition corrections.

    ``cas`` is the FREE ammonia concentration, ``cs`` the TOTAL H2S
    concentration, ``cc`` the total CO2-bearing species (gmol/kg solution).
    In this package's NH3-H2S-H2O scope cc is zero (the CO2 path is not
    implemented), which reduces both correlations to their printed
    worked-example form.
    """
    t = _degR(t_k)
    h = _reactions()["henry"]
    nh3 = h["nh3"]
    ln_h_nh3 = (
        float(nh3["constant"])
        + float(nh3["inv_t"]) / t
        + float(nh3["ln_t"]) * math.log(t)
        + float(nh3["t"]) * t
        + (float(nh3["cas_inv_t"]) / t + float(nh3["cas"])) * cas
        + float(nh3["cs"]) * cs
    )
    h2s = h["h2s"]
    ln_h_h2s = (
        float(h2s["constant"])
        + float(h2s["inv_t"]) / t
        + float(h2s["inv_t2"]) / t**2
        + float(h2s["inv_t3"]) / t**3
        + float(h2s["inv_t4"]) / t**4
        + float(h2s["cas"]) * cas
        + (float(h2s["cc"]) / t + float(h2s["cc_inv_t"])) * cc
    )
    return SWHenry(nh3=math.exp(ln_h_nh3), h2s=math.exp(ln_h_h2s))


@dataclass(frozen=True)
class SourWaterSpeciation:
    """Aqueous speciation at T (gmol/kg solution)."""

    h: float
    nh4: float
    nh3_free: float
    h2s: float
    hs: float
    s2: float
    oh: float

    @property
    def ph(self) -> float:
        return -math.log10(self.h)


def _species_at(m_nh3: float, m_h2s: float, c: SWEQConstants, h: float) -> SourWaterSpeciation:
    """Closed-form speciation at fixed [H+] (analytic mass balances)."""
    nh4 = m_nh3 * c.k_nh4 * h / (1.0 + c.k_nh4 * h)
    denom = h * h + c.k_h2s * h + c.k_h2s * c.k_hs
    return SourWaterSpeciation(
        h=h,
        nh4=nh4,
        nh3_free=m_nh3 - nh4,
        h2s=m_h2s * h * h / denom,
        hs=m_h2s * c.k_h2s * h / denom,
        s2=m_h2s * c.k_h2s * c.k_hs / denom,
        oh=c.k_w / h,
    )


def sour_water_speciation(
    m_nh3: float, m_h2s: float, t_k: float, ph: float | None = None
) -> SourWaterSpeciation:
    """Speciation of an NH3/H2S aqueous solution at T (K).

    Charge balance [H+] + [NH4+] == [OH-] + [HS-] + 2[S2-] solved by bracketed
    root finding on [H+] (in log space; the residual is negative in the
    alkaline limit, positive in the acid limit); a fixed pH short-circuits the
    balance (the report's buffered-solution convention).  The polynomials are
    numerically safe far outside the fitted window, so saturation scans may
    evaluate them freely; window enforcement lives at the flash boundary.
    """
    c = sweq_constants(t_k)
    if ph is not None:
        return _species_at(m_nh3, m_h2s, c, 10.0 ** (-ph))

    def residual(log_h: float) -> float:
        s = _species_at(m_nh3, m_h2s, c, math.exp(log_h))
        return (s.h + s.nh4) - (s.oh + s.hs + 2.0 * s.s2)

    return _species_at(m_nh3, m_h2s, c, math.exp(brent_root(residual, -32.0, 0.0, xtol=1e-14)))


def sour_water_partial_pressures(
    m_nh3: float, m_h2s: float, t_k: float, ph: float | None = None
) -> tuple[float, float]:
    """Equilibrium (p_NH3, p_H2S) in Pa over the solution at T (K).

    The report's p_i = H_i * c_i,free (Henry constants psia per gmol/kg
    solution, converted to Pa).  ``ph`` fixes the liquid pH (buffered
    convention); by default the charge balance sets it.
    """
    spec = sour_water_speciation(m_nh3, m_h2s, t_k, ph)
    henry = sweq_henry(t_k, cas=max(spec.nh3_free, 0.0), cs=m_h2s)
    return henry.nh3 * spec.nh3_free * _PSIA_TO_PA, henry.h2s * spec.h2s * _PSIA_TO_PA


# -- shared plumbing ---------------------------------------------------------------


@cache
def _record(cid: str) -> Any:
    """Databank record of a supported component (open thermo registry)."""
    rec = component_record(cid)
    if rec is None:
        raise ElectrolyteChemistryError(f"component {cid!r} is not in the open component registry")
    return rec


@cache
def _mw(cid: str) -> float:
    """Molecular weight (g/mol) of a supported component."""
    return float(_record(cid)["mw"])


def _molality_nacl(x_nacl: float, x_w: float) -> float:
    """NaCl molality (mol/kg water) from liquid mole fractions, clamped to the fitted domain."""
    if x_w <= 0.0:
        raise ElectrolyteChemistryError("the brine liquid carries no water (molality undefined)")
    m = 1000.0 * x_nacl / (_mw("H2O") * x_w)
    return min(m, _MAX_MOLALITY)


def _solution_molalities(x: dict[str, float]) -> tuple[float, float]:
    """(m_NH3, m_H2S) in gmol per kg of SOLUTION from liquid mole fractions."""
    kg_per_mol = sum(x[cid] * _mw(cid) for cid in x) / 1000.0
    if kg_per_mol <= 0.0:
        raise ElectrolyteChemistryError("empty liquid composition")
    return x.get("NH3", 0.0) / kg_per_mol, x.get("H2S", 0.0) / kg_per_mol


def _psat_or_wilson(cid: str, t_k: float) -> float:
    """Databank Psat (Pa), falling back to the Wilson correlation bound past Tc."""
    psat = _state.pure_psat(cid, t_k)
    return psat if psat is not None else _state._wilson_psat(cid, t_k)


# -- the package --------------------------------------------------------------------


#: Per-model water-activity surface of the brine models (the K-value and
#: fugacity driver: K_H2O = a_w(m) * Psat_H2O / P; the salt is involatile).
_WATER_ACTIVITY: dict[str, Callable[[float], float]] = {
    "pitzer": pitzer_water_activity,
    "enrtl": enrtl_water_activity,
    "ext_uniquac": ext_uniquac_water_activity,
}


class ElectrolytePackage(Thermo):
    """Electrolyte property package over a plain-cubic carrier.

    Subclasses pin the model (a ``_BRINE_MODELS`` brine or ``sour_water``)
    and register the catalogue rows; models whose open parameter bases are
    not verifiable stay in ``_REFUSALS`` and raise at first use.
    K-values come from the model's own chemistry (water activity x Psat for
    the brine; the speciation equilibrium partial pressures for sour water),
    the phase split is a Rachford-Rice solve with a Wegstein-damped
    composition fixed point, and the physical-phase properties are the
    carrier's aqueous/vapour properties with the model's fugacity overrides.
    """

    #: Electrolyte model key (``_MODEL_WINDOWS``/``_MODEL_SUPPORTS`` keys).
    model: str = ""

    def __init__(self, model: str | None = None) -> None:
        self._model = model or type(self).model
        carrier_cls = cast(type[Thermo], _registry_get("thermo", "pr"))
        self._carrier: Thermo = carrier_cls()
        self._lru_cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()

    # -- plumbing -------------------------------------------------------------

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        """Per-package LRU property cache (P1-01's semantics)."""
        cache_ = self._lru_cache
        hit = cache_.get(key)
        if hit is not None:
            cache_.move_to_end(key)
            return hit
        value = compute()
        cache_[key] = value
        while len(cache_) > _CACHE_SIZE:
            cache_.popitem(last=False)
        return value

    def _support(self, z: dict[str, float]) -> tuple[str, ...]:
        """Sorted positive-fraction ids (the _state helpers' support semantics)."""
        return _state.support_ids(z)

    def _water_activity(self, molality: float) -> float:
        """This model's water-activity surface a_w(m) (the brine chemistry driver)."""
        return _WATER_ACTIVITY[self._model](molality)

    def _refuse_if_needed(self) -> None:
        """First-use refusals (the T-07 idiom: construction never raises)."""
        reason = _REFUSALS.get(self._model)
        if reason is not None:
            raise NotImplementedError(reason)

    def _require_window(self, t_k: float) -> None:
        lo, hi = _MODEL_WINDOWS[self._model]
        if not lo <= t_k <= hi:
            raise ElectrolyteChemistryError(
                f"electrolyte model {self._model!r} left its fitted window: T={t_k} K outside [{lo}, {hi}] K"
            )

    def _electrolyte_domain(self, z: dict[str, float]) -> bool:
        """True when the feed is this package's chemistry; False to delegate.

        Feeds without water have no electrolyte solvent (the carrier flashes
        them, byte-identical).  Unsupported components refuse at first use
        with the documented gap.
        """
        self._refuse_if_needed()
        if z.get("H2O", 0.0) <= 0.0:
            return False
        unsupported = [cid for cid in self._support(z) if cid not in _MODEL_SUPPORTS[self._model]]
        if unsupported:
            co2_note = (
                " (the CO2/carbonate path of EPA-600/2-80-067 is data-side only "
                "this cycle: no verified carbonate anchor; k1/k2/k4 would need the "
                "same character-level verification the NH3/H2S set received)"
                if "CO2" in unsupported
                else ""
            )
            raise NotImplementedError(
                f"electrolyte model {self._model!r} supports "
                f"{sorted(_MODEL_SUPPORTS[self._model])}; no verified parameters "
                f"for {sorted(unsupported)}{co2_note} (first-use refusal, T-07 precedent)"
            )
        return True

    # -- K-values -------------------------------------------------------------

    def _k_values_internal(
        self, z: dict[str, float], t_k: float, p: float, x: dict[str, float]
    ) -> dict[str, float]:
        """K-values of the full key set at liquid composition ``x``."""
        if self._model != "sour_water":
            return self._k_brine(z, t_k, p, x)
        return self._k_sour_water(z, t_k, p, x)

    def _k_brine(self, z: dict[str, float], t_k: float, p: float, x: dict[str, float]) -> dict[str, float]:
        """Brine K-values: K_H2O = a_w(m) * Psat_H2O / P; the salt is involatile.

        The 25 C parameter sets are used as-is across the models' window
        (293.15-303.15 K, the catalogue rows' T_K): the osmotic surfaces are
        T-independent by construction (the extended-UNIQUAC u_ij/A(T)
        T-dependence is negligible across the 10 K window; see the parameter
        file) and temperature dependence enters only through Psat.  Saturation
        scans evaluate these K-values at exploratory temperatures outside the
        window by design; the solved point is what must be inside it (checked
        in :meth:`_boundary`).
        """
        m = _molality_nacl(x.get("NaCl", 0.0), x.get("H2O", 0.0))
        k_h2o = self._water_activity(m) * _psat_or_wilson("H2O", t_k) / p
        return {cid: (k_h2o if cid == "H2O" else _NONVOLATILE_K) for cid in z}

    def _k_sour_water(
        self, z: dict[str, float], t_k: float, p: float, x: dict[str, float]
    ) -> dict[str, float]:
        """Sour-water K-values from the SWEQ equilibrium partial pressures.

        The VLE data convention (as in the report's sample problem): the
        species partial pressure IS the equilibrium y_i * P, so
        K_i = p_eq_i / (P * x_i); water is Raoult (Psat/P, the report's own
        water term p_H2O = V.P._H2O * X_H2O).  Like the brine path, the
        polynomials evaluate at exploratory temperatures during saturation
        scans; the solved point must be inside the fitted window
        (:meth:`_boundary` checks it).
        """
        m_nh3, m_h2s = _solution_molalities(x)
        p_nh3, p_h2s = sour_water_partial_pressures(m_nh3, m_h2s, t_k)
        k: dict[str, float] = {}
        for cid in z:
            if cid == "H2O":
                k[cid] = _psat_or_wilson("H2O", t_k) / p
            else:
                p_eq = p_nh3 if cid == "NH3" else p_h2s
                x_i = max(x.get(cid, 0.0), 1e-12)
                k[cid] = p_eq / (p * x_i)
                if k[cid] <= 0.0:  # absent from the liquid: effectively all-vapour
                    k[cid] = _ALL_VAPOR_K
        return k

    # -- phase split ----------------------------------------------------------

    def _equilibrium_internal(
        self, z: dict[str, float], t_k: float, p: float
    ) -> tuple[Literal["liquid", "vapor", "two_phase"], float, dict[str, float], dict[str, float]]:
        """Phase split at (T, P) on the model's K-values.

        Returns (state, vapour_fraction, liquid_x, vapour_y).

        The brine model needs no fixed-point walk: the salt never leaves the
        liquid, so the two-phase region is fixed analytically by the salt
        balance and the concentrated liquid's bubble condition
        (:meth:`_brine_split`).  A fixed-point walk there is *wrong*, not
        merely slow: concentrating the liquid lowers its bubble pressure
        until the walked liquid is subcooled, the split's stability edge
        reclassifies the state as liquid, and the vaporised water vanishes
        from the balance.

        The sour-water model keeps the walk: all its species are volatile,
        so the K-values depend on the liquid composition only mildly and the
        substitution converges (Wegstein-damped; tolerance 1e-12, cap 50
        iterations).  A non-converged iterate is never returned.
        """
        if self._model in _BRINE_MODELS:
            return self._brine_split(z, t_k, p)
        # The stability edges are a property of the FEED: classify once at
        # x = z, then take a single Rachford-Rice split at the
        # feed-composition K-values.  Iterating the K-values to a
        # self-consistent liquid (as the amine packages do) does not
        # converge for these reactive K-values: concentrating the liquid
        # protonates the free ammonia faster than the total molality rises,
        # the feed-weighted K-sum dips back below the stability edge, and
        # the fixed-point walk oscillates across the phase boundary.  The
        # feed-composition split is exact at the saturation boundaries
        # (where the liquid is the feed) and the tests pin it there; the
        # mid-region liquid composition carries that documented
        # approximation (docs/validation.md).
        k = self._k_values_internal(z, t_k, p, z)
        if sum(f * k[cid] for cid, f in z.items()) <= 1.0:
            return "liquid", 0.0, dict(z), dict(z)
        if sum(f / k[cid] for cid, f in z.items()) <= 1.0:
            return "vapor", 1.0, dict(z), dict(z)
        beta, x_new, y = self._rr_core(z, k)
        return "two_phase", beta, x_new, y

    def _brine_split(
        self, z: dict[str, float], t_k: float, p: float
    ) -> tuple[Literal["liquid", "vapor", "two_phase"], float, dict[str, float], dict[str, float]]:
        """Exact split for an involatile-salt brine.

        The salt stays in the liquid (y_NaCl = 0), so two-phase states carry
        pure-water vapour and follow from two balances: the liquid
        concentrates until its bubble pressure a_w(m*)*Psat(T) == P, and the
        salt balance sets the vapour fraction beta = 1 - z_NaCl/x_NaCl(m*).
        Above the feed's bubble pressure the state is a single liquid at the
        feed molality; below the saturated-solution pressure the salt would
        precipitate, which the model refuses (it carries no solid phase).
        """
        if z.get("NaCl", 0.0) <= 0.0:
            psat = _psat_or_wilson("H2O", t_k)
            if p >= psat:
                return "liquid", 0.0, dict(z), dict(z)
            return "vapor", 1.0, dict(z), dict(z)
        m_feed = _molality_nacl(z["NaCl"], z.get("H2O", 0.0))
        psat = _psat_or_wilson("H2O", t_k)
        if p >= self._water_activity(m_feed) * psat:
            return "liquid", 0.0, dict(z), dict(z)
        # Below the feed's bubble pressure the boiling liquid concentrates,
        # shedding pure-water vapour, until it reaches the saturated-solution
        # molality -- the model's two-phase limit.  Below the saturated
        # solution's own bubble pressure a solid NaCl phase would appear,
        # which the model does not carry: the split pins the liquid at the
        # saturation molality there (a constant-vf plateau, so saturation
        # scans keep a continuous surface) and the FLASH path refuses the
        # state (_build_state checks the solved liquid's molality).

        def excess(m: float) -> float:
            return pitzer_water_activity(m) * psat - p

        # excess starts positive at m_feed (the state is above its bubble)
        # and decreases with m (a_w falls); the root exists inside the
        # bracket exactly when the saturated-solution end has gone negative.
        if excess(_MAX_MOLALITY) < 0.0:
            m_star = brent_root(excess, m_feed, _MAX_MOLALITY)
        else:
            m_star = _MAX_MOLALITY
        mw_water = _mw("H2O") / 1000.0  # kg/mol, to match the molality basis
        x_salt = m_star * mw_water / (1.0 + m_star * mw_water)
        beta = min(1.0 - z["NaCl"] / x_salt, 1.0)
        x = {cid: (1.0 - x_salt if cid == "H2O" else x_salt) for cid in z}
        y = {cid: (1.0 if cid == "H2O" else 0.0) for cid in z}
        return "two_phase", beta, x, y

    def _rr_core(
        self, z: dict[str, float], k: dict[str, float]
    ) -> tuple[float, dict[str, float], dict[str, float]]:
        """The Rachford-Rice split itself: one vapour fraction, phase compositions.

        The denominator is written (1 - beta) + beta * K, not
        1 + beta * (K - 1): with an involatile K of 1e-12 (the salt) the
        second form cancels to exactly 0.0 at beta = 1; the first evaluates
        to K there (the amine packages' numerical-safety convention).
        """

        def rr(beta: float) -> float:
            return sum(f * (k[cid] - 1.0) / ((1.0 - beta) + beta * k[cid]) for cid, f in z.items())

        # The classification above guarantees the bracket: rr(0) > 0 (the
        # feed's K-sum passed the liquid edge) and rr(1) < 0 (it passed the
        # vapour edge).
        beta = brent_root(rr, 0.0, 1.0)
        y_raw: dict[str, float] = {}
        x_new: dict[str, float] = {}
        for cid, f in z.items():
            denom = (1.0 - beta) + beta * k[cid]
            y_raw[cid] = max(f * k[cid] / denom, 0.0)
            x_new[cid] = max(y_raw[cid] / k[cid], 0.0)
        sy, sx = sum(y_raw.values()), sum(x_new.values())
        y = {cid: v / sy for cid, v in y_raw.items()}
        x_new = {cid: v / sx for cid, v in x_new.items()}
        return beta, x_new, y

    # -- flashes --------------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: electrolyte equilibrium at temperature T (K), pressure P (Pa abs)."""
        if not self._electrolyte_domain(z):
            return self._carrier.flash_pt(z, T, P, molar_flow)
        self._require_window(T)
        key = ("pt", *_state.cache_key(z, T, P), float(molar_flow))
        return cast(StreamState, self._cached(key, lambda: self._build_state(z, T, P, molar_flow)))

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: secant on T through the electrolyte flash enthalpy (carrier T guess).

        The secant is free to explore outside the fitted window (the carrier's
        guess can sit outside it); the SOLVED temperature is window-checked by
        the final guarded flash_pt.
        """
        if not self._electrolyte_domain(z):
            return self._carrier.flash_ph(z, P, H, molar_flow)
        t = self._carrier.flash_ph(z, P, H, molar_flow).T

        def h_of(t_try: float) -> float:
            return self._build_state(z, t_try, P, molar_flow).enthalpy

        t_prev, h_prev = t, h_of(t)
        t_try = t_prev + _DERIV_D_T
        h_try = h_of(t_try)
        for _ in range(_FLASH_MAX_ITER):
            if abs(h_try - H) <= 1e-8 * max(abs(H), 1.0):
                return self.flash_pt(z, t_try, P, molar_flow)
            denom = h_try - h_prev
            if denom == 0.0:
                break
            t_next = t_try - (h_try - H) * (t_try - t_prev) / denom
            t_prev, h_prev = t_try, h_try
            t_try = t_next
            h_try = h_of(t_try)
        raise ValueError(f"electrolyte PH flash did not converge at P={P} Pa, H={H} J/mol")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: secant on T through the electrolyte flash entropy (carrier T guess).

        As in flash_ph, exploratory evaluations are unguarded; the solved
        temperature is window-checked by the final guarded flash_pt.
        """
        if not self._electrolyte_domain(z):
            return self._carrier.flash_ps(z, P, S, molar_flow)
        t = self._carrier.flash_ps(z, P, S, molar_flow).T

        def s_of(t_try: float) -> float:
            return self._build_state(z, t_try, P, molar_flow).entropy

        t_prev, s_prev = t, s_of(t)
        t_try = t_prev + _DERIV_D_T
        s_try = s_of(t_try)
        for _ in range(_FLASH_MAX_ITER):
            if abs(s_try - S) <= 1e-8 * max(abs(S), 1.0):
                return self.flash_pt(z, t_try, P, molar_flow)
            denom = s_try - s_prev
            if denom == 0.0:
                break
            t_next = t_try - (s_try - S) * (t_try - t_prev) / denom
            t_prev, s_prev = t_try, s_try
            t_try = t_next
            s_try = s_of(t_try)
        raise ValueError(f"electrolyte PS flash did not converge at P={P} Pa, S={S} J/(mol K)")

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: vapour fraction vf in [0, 1] at temperature T (K)."""
        if not self._electrolyte_domain(z):
            return self._carrier.flash_tvf(z, T, vf, molar_flow)
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        p_bub = None if vf <= _VF_EDGE else self._boundary(z, "bubble", T=T).P
        p_dew = None if vf >= 1.0 - _VF_EDGE else self._boundary(z, "dew", T=T).P
        if p_bub is None and p_dew is None:  # pragma: no cover - vf cannot be both edges
            raise ValueError("vapour fraction at both phase edges")
        if p_bub is None or p_dew is None:
            return self.flash_pt(z, T, cast(float, p_bub or p_dew), molar_flow)

        def g(p: float) -> float:
            return self._equilibrium_internal(z, T, p)[1] - vf

        p = brent_root(g, min(p_dew, p_bub), max(p_dew, p_bub), xtol=_SATURATION_REL_TOL * 1e-2)
        return self.flash_pt(z, T, p, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: vapour fraction vf in [0, 1] at pressure P (Pa abs)."""
        if not self._electrolyte_domain(z):
            return self._carrier.flash_pvf(z, P, vf, molar_flow)
        if not 0.0 <= vf <= 1.0:
            raise ValueError(f"vapour fraction {vf} outside [0, 1]")
        t_bub = None if vf <= _VF_EDGE else self._boundary(z, "bubble", P=P).T
        t_dew = None if vf >= 1.0 - _VF_EDGE else self._boundary(z, "dew", P=P).T
        if t_bub is None and t_dew is None:  # pragma: no cover - vf cannot be both edges
            raise ValueError("vapour fraction at both phase edges")
        if t_bub is None or t_dew is None:
            return self.flash_pt(z, cast(float, t_bub or t_dew), P, molar_flow)

        def g(t: float) -> float:
            return self._equilibrium_internal(z, t, P)[1] - vf

        t = brent_root(g, min(t_dew, t_bub), max(t_dew, t_bub), xtol=_SATURATION_REL_TOL * 1e-2)
        return self.flash_pt(z, t, P, molar_flow)

    # -- saturation -----------------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point of an electrolyte feed: exactly one of T (K) and P (Pa)."""
        if not self._electrolyte_domain(z):
            return self._carrier.bubble_point(z, T=T, P=P)
        return self._boundary(z, "bubble", T=T, P=P)

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point of an electrolyte feed: exactly one of T (K) and P (Pa)."""
        if not self._electrolyte_domain(z):
            return self._carrier.dew_point(z, T=T, P=P)
        return self._boundary(z, "dew", T=T, P=P)

    def _boundary(
        self,
        z: dict[str, float],
        kind: Literal["bubble", "dew"],
        *,
        T: float | None = None,
        P: float | None = None,
    ) -> SaturationPoint:
        """Bubble/dew point solved on the package's own vapour fraction.

        The shared plateau-scan-then-bracketed-secant solver
        (``thermo.saturation``) runs on this package's vf between
        Wilson-correlation bounds.  Pressure bounds are wide (0.2x..30x
        water's Wilson Psat): at moderate molalities the ammonia partial
        pressure alone exceeds 3x water's Psat.  Temperature bounds are the
        solvent's Wilson saturation temperature padded 0.9x..1.15x.
        """
        if (T is None) == (P is None):
            raise ValueError("specify exactly one of T and P")

        def vf_at(x: float) -> float:
            return self._equilibrium_internal(z, T if T is not None else x, P if P is not None else x)[1]

        if T is not None:
            w = _state._wilson_psat("H2O", T)
            bounds = (0.2 * w, 30.0 * w)
            label = f"T={T} K"
            unknown: Literal["P", "T"] = "P"
        else:
            p_given = cast(float, P)
            t_w = _state._wilson_T_safe("H2O", p_given)
            if t_w is None:
                raise SaturationError(f"no Wilson T bound at P={p_given} Pa for H2O")
            bounds = (0.9 * t_w, 1.15 * t_w)
            label = f"P={p_given} Pa"
            unknown = "T"

        x_star = solve_saturation(vf_at, kind=kind, unknown=unknown, bounds=bounds, label=label)
        lo, hi = _MODEL_WINDOWS[self._model]
        if unknown == "T" and not lo <= x_star <= hi:
            raise ElectrolyteChemistryError(
                f"electrolyte model {self._model!r} {kind} point solved outside its "
                f"fitted window: T={x_star:.2f} K outside [{lo}, {hi}] K at {label}"
            )
        if T is not None:
            return SaturationPoint(T=T, P=x_star, kind=kind, incipient_composition=dict(z))
        return SaturationPoint(T=x_star, P=cast(float, P), kind=kind, incipient_composition=dict(z))

    # -- properties -----------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i at (T, P); None when the electrolyte flash is single-phase."""
        if not self._electrolyte_domain(z):
            return self._carrier.k_values(z, T, P)
        state, _vf, x, y = self._equilibrium_internal(z, T, P)
        if state != "two_phase":
            return None
        return {cid: (y[cid] / x[cid] if x[cid] > 0.0 else 0.0) for cid in z}

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        return _state.pure_psat(cid, T)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """Single-phase properties at (composition, T, P), built without flashing."""
        key = ("pp", str(kind), *_state.cache_key(composition, T, P))
        return cast(
            PhaseProps,
            self._cached(key, lambda: self._phase_props(composition, T, P, kind)),
        )

    def _phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """The aqueous phase carries the electrolyte fugacity surface.

        Enthalpy/entropy/cp stay the carrier's (no reaction-enthalpy term is
        implemented this cycle; the spec carries no reactive-cp criterion).
        Fugacity fractions follow the report's VLE convention: the water
        fugacity is a_w * Psat_H2O (brine) and each volatile's fugacity is its
        SWEQ equilibrium partial pressure, both with the carrier's pure-vapour
        phi^V at the species' own pressure (zero-BIP limit, the amine packages'
        form).
        """
        if kind != PhaseKind.AQUEOUS or not self._electrolyte_domain(composition):
            return self._carrier.phase_props(composition, T, P, kind)
        base = self._carrier.phase_props(composition, T, P, PhaseKind.AQUEOUS)
        ln_phi = dict(base.ln_phi)
        for cid, f_i in self._fugacities(composition, T, P).items():
            if f_i is None or f_i <= 0.0:
                continue
            phi_v = self._carrier.phase_props({cid: 1.0}, T, f_i, PhaseKind.VAPOR).ln_phi[cid]
            ln_phi[cid] = math.log(f_i * math.exp(phi_v) / P)
        return base.model_copy(update={"ln_phi": ln_phi})

    def _fugacities(self, x: dict[str, float], T: float, P: float) -> dict[str, float | None]:
        """Component fugacities f_i (Pa) on the aqueous electrolyte liquid.

        Pitzer brine: f_H2O = a_w(m) * Psat_H2O, the salt involatile (None).
        Sour water: f_NH3 and f_H2S are the SWEQ equilibrium partial
        pressures.  Absent components return None.
        """
        if self._model != "sour_water":
            m = _molality_nacl(x.get("NaCl", 0.0), x.get("H2O", 0.0))
            a_w = self._water_activity(m)
            return {cid: (a_w * _psat_or_wilson("H2O", T) if cid == "H2O" else None) for cid in x}
        m_nh3, m_h2s = _solution_molalities(x)
        p_nh3, p_h2s = sour_water_partial_pressures(m_nh3, m_h2s, T)
        return {cid: (p_nh3 if cid == "NH3" else p_h2s if cid == "H2S" else None) for cid in x}

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PropertyDerivatives:
        """d ln phi / dT and d ln phi / dP per component for one phase.

        Aqueous volatile derivatives are numeric central differences of
        d ln f_i / dT at fixed composition (f_i is pressure-independent at a
        fixed liquid state, so d ln phi_i / dP = -1/P); everything else is the
        carrier's.
        """
        if kind != PhaseKind.AQUEOUS or not self._electrolyte_domain(composition):
            return self._carrier.derivatives(composition, T, P, kind)
        base = self._carrier.derivatives(composition, T, P, kind)
        d_t = dict(base.dlnphi_dT)
        d_p = dict(base.dlnphi_dP)
        for cid, f_hi in self._fugacities(composition, T + _DERIV_D_T, P).items():
            if f_hi is None or f_hi <= 0.0:
                continue
            f_lo = self._fugacities(composition, T - _DERIV_D_T, P)[cid]
            assert f_lo is not None  # same composition set
            if min(f_hi, f_lo) > 0.0:
                d_t[cid] = (math.log(f_hi) - math.log(f_lo)) / (2.0 * _DERIV_D_T)
            d_p[cid] = -1.0 / P
        return PropertyDerivatives(dlnphi_dT=d_t, dlnphi_dP=d_p)

    # -- state construction ---------------------------------------------------

    def _build_state(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        state, beta, x, y = self._equilibrium_internal(z, T, P)
        if state == "two_phase" and self._model in _BRINE_MODELS and x.get("H2O", 0.0) > 0.0:
            m_liq = 1000.0 * x.get("NaCl", 0.0) / (_mw("H2O") * x["H2O"])
            if m_liq >= _MAX_MOLALITY:
                raise ElectrolyteChemistryError(
                    f"the brine flash at T={T} K, P={P} Pa needs more than the "
                    f"saturated-solution molality ({_MAX_MOLALITY} mol/kg): NaCl would "
                    "precipitate, which the model does not represent"
                )
        if state == "vapor":
            props = self._carrier.phase_props(z, T, P, PhaseKind.VAPOR)
            phase = _phase(PhaseKind.VAPOR, 1.0, z, props)
            return StreamState(
                T=T,
                P=P,
                molar_flow=molar_flow,
                composition=dict(z),
                vapor_fraction=1.0,
                enthalpy=props.enthalpy,
                entropy=props.entropy,
                phases=[phase],
            )
        liquid_props = self.phase_props(x, T, P, PhaseKind.AQUEOUS)
        liquid = _phase(PhaseKind.AQUEOUS, 1.0 - beta, x, liquid_props)
        if state == "liquid":
            return StreamState(
                T=T,
                P=P,
                molar_flow=molar_flow,
                composition=dict(z),
                vapor_fraction=0.0,
                enthalpy=liquid_props.enthalpy,
                entropy=liquid_props.entropy,
                phases=[liquid],
            )
        vapor_props = self._carrier.phase_props(y, T, P, PhaseKind.VAPOR)
        vapor = _phase(PhaseKind.VAPOR, beta, y, vapor_props)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=beta,
            enthalpy=beta * vapor_props.enthalpy + (1.0 - beta) * liquid_props.enthalpy,
            entropy=beta * vapor_props.entropy + (1.0 - beta) * liquid_props.entropy,
            phases=[vapor, liquid],
        )


@register("thermo", "pitzer_nacl_water")
class ElectrolytePitzerNaCl(ElectrolytePackage):
    """Pitzer NaCl(aq): water activity, osmotic and mean activity coefficients."""

    model = "pitzer"


@register("thermo", "sour_water")
class ElectrolyteSourWater(ElectrolytePackage):
    """EPA-600/2-80-067 SWEQ sour water: NH3-H2S-H2O speciation and partial pressures."""

    model = "sour_water"


@register("thermo", "enrtl_nacl_water")
class ElectrolyteENRTLNaCl(ElectrolytePackage):
    """eNRTL NaCl(aq): PDH long range + Chen & Evans 1986 local composition."""

    model = "enrtl"


@register("thermo", "ext_uniquac_nacl_water")
class ElectrolyteExtUNIQUAC(ElectrolytePackage):
    """Extended UNIQUAC NaCl(aq): Thomsen & Rasmussen 1999 parameter set."""

    model = "ext_uniquac"
