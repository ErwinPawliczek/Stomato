"""General electrolyte property packages (spec T-09).

Four literature-anchored aqueous models,
implemented over the same carrier + K-value flash machinery as the amine
packages (``ngdesign.amine.package``):

* ``pitzer_nacl_water`` -- Pitzer single-salt brines with the PHRQPITZ 25 C
  parameter sets (USGS WRI 88-4153; NaCl, KCl, KBr, LiCl, NaBr, MgCl2, keyed
  by salt and ion pair): osmotic coefficient, mean ionic activity coefficient
  (exact Gibbs-Duhem integration of the osmotic form), water activity, and
  for NaCl the solid-liquid saturation anchor (6.146 mol/kg at gamma =
  1.0065; Pitzer, Peiper & Busey 1984).  See
  ``data/thermo_params/electrolyte/pitzer.yaml``.
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
* ``pitzer_debye_huckel`` -- the long-range term of ``enrtl_nacl_water`` alone (no
  short-range binary), a dilute-solution model refused above its molality cap.
* ``enrtl_rk``, ``enrtl_hoc``, ``pitzer_hoc`` -- the same brine liquids with a real
  water vapour: the Redlich-Kwong or Hayden-O'Connell fugacity coefficient enters
  the water K-value, and the vapour properties come from that model.
* ``enrtl_crystallisation`` -- ``enrtl_nacl_water`` with a solid NaCl phase instead of
  the refusal/supersaturated liquid past the solubility limit.

Streams stay molecular (ionic species never leave this module): the brine
models take water plus one salt of their parameter file (pitzer.yaml: NaCl,
KCl, KBr, LiCl, NaBr, MgCl2; enrtl.yaml and ext_uniquac.yaml: NaCl -- all
three are single-salt forms with the salt keyed by ion pair, charges and
stoichiometry as data), the sour-water model (H2O, NH3, H2S); anything else
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
from ngdesign.contracts import Phase, PhaseKind, StreamState
from ngdesign.contracts.plugins import Thermo
from ngdesign.contracts.thermo import (
    PhaseProps,
    PropertyDerivatives,
    SaturationError,
    SaturationPoint,
)
from ngdesign.data import DATA_DIR, DATABANK_LOCK, component_record
from ngdesign.provenance.thermo_hook import TracedThermo
from ngdesign.registry import register
from ngdesign.thermo import _state
from ngdesign.thermo.gamma_phi import GammaPhiPackage, _constants_for
from ngdesign.thermo.saturation import solve_saturation

__all__ = [
    "ElectrolyteChemistryError",
    "ElectrolyteENRTLCrystal",
    "ElectrolyteENRTLHOC",
    "ElectrolyteENRTLNaCl",
    "ElectrolyteENRTLRK",
    "ElectrolyteExtUNIQUAC",
    "ElectrolytePDH",
    "ElectrolytePitzerHOC",
    "ElectrolytePitzerNaCl",
    "ElectrolyteSourWater",
    "PitzerSalt",
    "SWEQConstants",
    "SWHenry",
    "SourWaterSpeciation",
    "enrtl_mean_gamma",
    "enrtl_crystallisation_molality",
    "enrtl_osmotic",
    "enrtl_saturation_molality",
    "enrtl_water_activity",
    "ext_uniquac_mean_gamma",
    "ext_uniquac_osmotic",
    "ext_uniquac_saturation_molality",
    "ext_uniquac_water_activity",
    "pitzer_mean_gamma",
    "pitzer_osmotic",
    "pitzer_salt",
    "pitzer_salts",
    "pitzer_saturation_molality",
    "pitzer_water_activity",
    "pdh_mean_gamma",
    "pdh_water_activity",
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

#: Default molality clamp of :func:`_salt_molality` (the NaCl saturation, 6.146
#: mol/kg at 298.15 K); the packages always pass their salt's own cap
#: (``molality_cap`` of its parameter-file entry), and the flash clamps a
#: nominal molality above it to the saturated anchor (the amine packages'
#: loading-clamp precedent).
_MAX_MOLALITY = 6.15

#: The Pitzer-Debye-Hueckel term alone has no short-range physics: it is a dilute-
#: solution model: gamma+- is 3.5 % below the PPB84 value at this molality and 8 % at
#: 0.5 mol/kg (measured in tests/thermo/test_electrolyte_variants.py).
_PDH_MAX_MOLALITY = 0.2

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
    "pdh": (293.15, 303.15),
    "ext_uniquac": (293.15, 303.15),
    "sour_water": (293.15, 373.15),
}

#: Molecular support of the sour-water model (stream keys; ionic species never
#: leave).  The brine supports are data-driven (water plus every salt of the
#: model's parameter file), see :data:`_BRINE_SALTS`.
_MODEL_SUPPORTS: dict[str, frozenset[str]] = {
    "sour_water": frozenset({"H2O", "NH3", "H2S"}),
}

#: Brine models (involatile-salt paths).  Everything else with a window is
#: the sour-water chemistry.
_BRINE_MODELS: tuple[str, ...] = ("pitzer", "enrtl", "pdh", "ext_uniquac")

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


# -- single-salt ion pairs (shared by every brine model's parameter file) ---------


@dataclass(frozen=True)
class SaltIons:
    """One salt's ion pair and stoichiometry, as every brine parameter file keys it.

    ``cation``/``anion`` are the species keys of the owning file, ``z_*`` the
    charge magnitudes and ``nu_*`` the stoichiometric numbers of the salt
    C_nuC A_nuA; ``molality_cap`` (mol/kg) is the top of the verified range.
    ``zz`` = |z_M z_X|, ``nu`` = nu_M + nu_X and ``charge_sum`` =
    nu_M z_M^2 + nu_X z_X^2 (so I = m * charge_sum / 2); all read 1, 2 and 2
    exactly for a 1:1 salt.
    """

    salt: str
    cation: str
    anion: str
    z_cation: int
    z_anion: int
    nu_cation: int
    nu_anion: int
    molality_cap: float

    @property
    def zz(self) -> float:
        return float(self.z_cation * self.z_anion)

    @property
    def nu(self) -> float:
        return float(self.nu_cation + self.nu_anion)

    @property
    def charge_sum(self) -> float:
        return float(self.nu_cation * self.z_cation**2 + self.nu_anion * self.z_anion**2)


def _salt_entry(table: dict[str, Any], salt: str, model: str, source: str) -> dict[str, Any]:
    """The ``salts`` entry for ``salt`` of a brine parameter file; unknown salts refuse."""
    entry = table["salts"].get(salt)
    if entry is None:
        raise ElectrolyteChemistryError(
            f"no {model} parameters for {salt!r}: data/thermo_params/electrolyte/{source} "
            f"carries {sorted(table['salts'])} (single-salt sets with cited sources)"
        )
    return cast(dict[str, Any], entry)


def _salt_ions(salt: str, entry: dict[str, Any]) -> SaltIons:
    """The ion pair and stoichiometry of one ``salts`` entry."""
    return SaltIons(
        salt=salt,
        cation=str(entry["cation"]),
        anion=str(entry["anion"]),
        z_cation=int(entry["z_cation"]),
        z_anion=int(entry["z_anion"]),
        nu_cation=int(entry["nu_cation"]),
        nu_anion=int(entry["nu_anion"]),
        molality_cap=float(entry["molality_cap"]),
    )


def _sle_molality(gamma: Callable[[float], float], entry: dict[str, Any], salt: str, source: str) -> float:
    """Salt solubility (mol/kg) from the SLE condition gamma(m) == gamma_sat.

    gamma_sat is the saturated-solution mean activity coefficient of the
    entry's ``saturation`` anchor (NaCl: 1.0065, Pitzer, Peiper & Busey 1984,
    p. 11); bracketed root finding on the rising branch past 4 molal.  Only
    salts whose entry carries the anchor have one.
    """
    if "saturation" not in entry:
        raise ElectrolyteChemistryError(f"no saturation anchor for {salt!r} in {source}")
    gamma_sat = float(entry["saturation"]["mean_gamma"])

    def residual(m: float) -> float:
        return gamma(m) - gamma_sat

    return brent_root(residual, 4.0, 10.0)


# -- Pitzer single-salt brines (PHRQPITZ 25 C parameter sets) ----------------------


@cache
def _pitzer() -> dict[str, Any]:
    """Cached Pitzer parameter table (data/thermo_params/electrolyte/pitzer.yaml)."""
    with (_PARAMS_DIR / "pitzer.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


@dataclass(frozen=True)
class PitzerSalt:
    """One salt's single-salt Pitzer entry, keyed by its ion pair.

    ``zz`` = |z_M z_X|; ``nu`` = nu_M + nu_X; ``f_b`` = 2 nu_M nu_X / nu and
    ``f_c`` = 2 (nu_M nu_X)^(3/2) / nu are the stoichiometric weights of the
    B and C terms (Pitzer 1991, ch. 3, eqs. 3.43-3.45); ``charge_sum`` =
    nu_M z_M^2 + nu_X z_X^2, so I = m * charge_sum / 2.  All four reduce to
    exactly 1.0 (and I to m) for a 1:1 salt.
    """

    salt: str
    cation: str
    anion: str
    zz: float
    nu: float
    f_b: float
    f_c: float
    charge_sum: float
    beta0: float
    beta1: float
    cphi: float
    molality_cap: float


@cache
def pitzer_salt(salt: str) -> PitzerSalt:
    """The single-salt Pitzer entry for ``salt`` (a component id); unknown salts refuse."""
    entry = _salt_entry(_pitzer(), salt, "Pitzer", "pitzer.yaml")
    ions = _salt_ions(salt, entry)
    if ions.z_cation >= 2 and ions.z_anion >= 2:
        # 2:2 salts need beta2 with alpha1 = 1.4, alpha2 = 12 (Pitzer & Mayorga 1974);
        # no such entry is shipped, so the form is not implemented.
        raise ElectrolyteChemistryError(f"{salt!r} is a 2:2 salt; the beta2 form is not implemented")
    nc, na = ions.nu_cation, ions.nu_anion
    return PitzerSalt(
        salt=salt,
        cation=ions.cation,
        anion=ions.anion,
        zz=ions.zz,
        nu=ions.nu,
        f_b=2.0 * nc * na / ions.nu,
        f_c=2.0 * float(nc * na) ** 1.5 / ions.nu,
        charge_sum=ions.charge_sum,
        beta0=float(entry["beta0"]),
        beta1=float(entry["beta1"]),
        cphi=float(entry["cphi"]),
        molality_cap=ions.molality_cap,
    )


def pitzer_salts() -> tuple[str, ...]:
    """Every salt (component id) with a single-salt Pitzer entry, sorted."""
    return tuple(sorted(_pitzer()["salts"]))


def _pitzer_constants() -> tuple[float, float, float]:
    """The shared (Aphi, b, alpha) of the parameter file."""
    p = _pitzer()
    return float(p["aphi"]), float(p["b"]), float(p["alpha"])


def pitzer_osmotic(molality: float, salt: str = "NaCl") -> float:
    """Osmotic coefficient phi of a single-salt solution at the 25 C parameter set.

    phi - 1 = |z_M z_X| f^phi + m (2 nu_M nu_X / nu) B^phi + m^2 (2 (nu_M nu_X)^1.5 / nu) C^phi,
    f^phi = -Aphi sqrt(I)/(1 + b sqrt(I)), B^phi = beta0 + beta1 exp(-alpha sqrt(I)),
    I = m (nu_M z_M^2 + nu_X z_X^2)/2 (Pitzer 1991, Activity Coefficients in
    Electrolyte Solutions, 2nd ed., ch. 3; the PHRQPITZ form, USGS WRI 88-4153).
    For a 1:1 salt this is the classic phi - 1 = -Aphi sqrt(m)/(1 + b sqrt(m))
    + m (beta0 + beta1 e^(-alpha sqrt(m))) + m^2 Cphi; the stoichiometric weights
    are exactly 1.0 there, so the NaCl values are bit-for-bit the 1:1 form's.
    """
    s = pitzer_salt(salt)
    aphi, b, alpha = _pitzer_constants()
    sq = math.sqrt(0.5 * molality * s.charge_sum)
    return (
        1.0
        - s.zz * (aphi * sq / (1.0 + b * sq))
        + molality * s.f_b * (s.beta0 + s.beta1 * math.exp(-alpha * sq))
        + molality * molality * s.f_c * s.cphi
    )


def pitzer_mean_gamma(molality: float, salt: str = "NaCl") -> float:
    """Mean ionic activity coefficient of a single-salt solution at the 25 C parameter set.

    Exact Gibbs-Duhem integration of the osmotic form above (Pitzer 1991, ch. 3):

    ln gamma = (phi - 1) - |z_M z_X| Aphi (2/b) ln(1 + b sqrt(I))
               + (2 nu_M nu_X / nu) beta0 m
               + (2 nu_M nu_X / nu) beta1 (2/alpha^2)(m/I)(1 - (1 + alpha sqrt(I)) e^(-alpha sqrt(I)))
               + (2 (nu_M nu_X)^1.5 / nu) Cphi m^2 / 2

    (the naive closed forms found in some secondary sources are not the
    integral of this osmotic expression and misestimate by up to ~10 %).
    """
    s = pitzer_salt(salt)
    aphi, b, alpha = _pitzer_constants()
    ionic = 0.5 * molality * s.charge_sum
    sq = math.sqrt(ionic)
    phi_minus_1 = (
        -s.zz * (aphi * sq / (1.0 + b * sq))
        + molality * s.f_b * (s.beta0 + s.beta1 * math.exp(-alpha * sq))
        + molality * molality * s.f_c * s.cphi
    )
    m_over_i = molality / ionic if ionic > 0.0 else 1.0
    ln_gamma = (
        phi_minus_1
        - s.zz * aphi * (2.0 / b) * math.log1p(b * sq)
        + s.f_b * s.beta0 * molality
        + s.f_b * s.beta1 * (2.0 / alpha**2) * m_over_i * (1.0 - (1.0 + alpha * sq) * math.exp(-alpha * sq))
        + s.f_c * s.cphi * molality * molality / 2.0
    )
    return math.exp(ln_gamma)


def pitzer_water_activity(molality: float, salt: str = "NaCl") -> float:
    """Water activity of a single-salt solution: a_w = exp(-nu m phi / 55.5084)."""
    molar_base = float(_pitzer()["molality_of_water"])
    return math.exp(-pitzer_salt(salt).nu * molality * pitzer_osmotic(molality, salt) / molar_base)


def pitzer_saturation_molality(salt: str = "NaCl") -> float:
    """Salt solubility (mol/kg) from the solid-liquid equilibrium condition.

    The SLE condition gamma_sat(m) == gamma(m) with the saturated-solution
    mean activity coefficient of the reference (NaCl: 1.0065, PPB84 p. 11);
    solved by bracketed root finding on the rising branch past 4 molal.  Only
    salts whose entry carries a ``saturation`` anchor have one.
    """
    entry = _pitzer()["salts"][pitzer_salt(salt).salt]
    return _sle_molality(lambda m: pitzer_mean_gamma(m, salt), entry, salt, "pitzer.yaml")


# -- eNRTL single-salt brines (Chen et al. 1982 PDH + Chen & Evans 1986 local composition)


@cache
def _enrtl() -> dict[str, Any]:
    """Cached eNRTL parameter table (data/thermo_params/electrolyte/enrtl.yaml)."""
    with (_PARAMS_DIR / "enrtl.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


@dataclass(frozen=True)
class ENRTLSalt:
    """One salt's eNRTL entry: its ion pair and the salt-water NRTL binary.

    ``tau_ca_w`` / ``tau_w_ca`` are the Chen & Evans (1986) salt-molecule and
    molecule-salt energy parameters and ``alpha`` the nonrandomness factor
    (0.2 in their single-solvent sets); G = exp(-alpha tau).
    """

    ions: SaltIons
    alpha: float
    tau_ca_w: float
    tau_w_ca: float


@cache
def enrtl_salt(salt: str) -> ENRTLSalt:
    """The eNRTL entry for ``salt`` (a component id); unknown salts refuse."""
    entry = _salt_entry(_enrtl(), salt, "eNRTL", "enrtl.yaml")
    return ENRTLSalt(
        ions=_salt_ions(salt, entry),
        alpha=float(entry["alpha"]),
        tau_ca_w=float(entry["tau_ca_w"]),
        tau_w_ca=float(entry["tau_w_ca"]),
    )


def enrtl_salts() -> tuple[str, ...]:
    """Every salt (component id) with an eNRTL entry, sorted."""
    return tuple(sorted(_enrtl()["salts"]))


def _pdh_gE_rt(xc: float, xa: float, ions: SaltIons) -> float:
    """Pitzer-Debye-Hueckel G^E/RT per total mole, mole-fraction basis, one salt.

    -(4 A_phi I_x / rho) sqrt(1000/M_w) ln(1 + rho sqrt(I_x)), I_x = (z_c^2 x_c +
    z_a^2 x_a)/2, with A_phi = 0.392 and the closest-approach rho = 14.9 (Pitzer,
    J. Am. Chem. Soc. 102 (1980) 2902; Chen, Britt, Boston & Evans, AIChE J. 28
    (1982) 588, eq. 4; infinite-dilution reference, I_x = 0 in pure water).  I_x
    reduces exactly to the per-ion fraction for a 1:1 salt.
    """
    p = _enrtl()
    aphi, rho = float(p["aphi"]), float(p["rho"])
    ix = 0.5 * (ions.z_cation**2 * xc + ions.z_anion**2 * xa)
    return -4.0 * aphi / math.sqrt(_MW_WATER_KG) * (ix / rho) * math.log1p(rho * math.sqrt(ix))


def _enrtl_gE_rt(xw: float, xc: float, xa: float, s: ENRTLSalt) -> float:
    """G^E/RT per total mole (x_w + x_c + x_a = 1), PDH long range + local composition.

    Short range: the single-salt, single-solvent local-composition G^E of Chen
    & Evans (1986), AIChE J. 32, 444, eq. 13 with one salt-water pair
    (G_cw = G_aw = exp(-alpha tau_ca,w), G_w,ca = exp(-alpha tau_w,ca)) on the
    effective fractions X_w = x_w, X_c = z_c x_c, X_a = z_a x_a:

        g_lc = X_w (X_c + X_a) G_cw tau_ca,w / (X_w + (X_c + X_a) G_cw)
             + X_c X_w G_w,ca tau_w,ca / (X_a + X_w G_w,ca)
             + X_a X_w G_w,ca tau_w,ca / (X_c + X_w G_w,ca)

    (a molecule cell and one cell per ion; for a 1:1 salt X_c = X_a and the two
    ion cells coincide, the reduction derived from Kwaterski & Herri eq. 25).
    The salt-side composition derivative of n*G^E returns
    nu_c ln gamma_c + nu_a ln gamma_a.
    """
    ions = s.ions
    g_c = math.exp(-s.alpha * s.tau_ca_w)
    g_w = math.exp(-s.alpha * s.tau_w_ca)
    big_xc, big_xa = ions.z_cation * xc, ions.z_anion * xa
    x_ion = big_xc + big_xa
    g_lc = xw * x_ion * g_c * s.tau_ca_w / (xw + x_ion * g_c)
    if big_xc == big_xa:
        g_lc += x_ion * xw * g_w * s.tau_w_ca / (xw * g_w + big_xa)
    else:
        g_lc += big_xc * xw * g_w * s.tau_w_ca / (xw * g_w + big_xa)
        g_lc += big_xa * xw * g_w * s.tau_w_ca / (xw * g_w + big_xc)
    return _pdh_gE_rt(xc, xa, ions) + g_lc


def _enrtl_ln_props(
    molality: float, salt: str = "NaCl", long_range_only: bool = False
) -> tuple[float, float]:
    """(ln gamma+-(m), ln a_w) of a single-salt solution at the 25 C parameter set.

    The composition derivatives of n*G^E/RT are numeric central differences
    (the closed local-composition derivatives of the reduced single-salt form
    are not published; the finite-difference form is pinned by the Gibbs-Duhem
    unit tests): the salt-side derivative returns nu_c ln gamma_c + nu_a ln gamma_a
    in the SYMMETRIC rational convention, so the unsymmetric molality-scale mean
    takes the infinite-dilution difference over nu and the ln x_w conversion
    (ln gamma+-(m) = ln gamma+-(x) - ln(1 + nu*m*M_w), worth ~22 % for NaCl at
    6 m); the water side is already symmetric-rational, so a_w = gamma_w * x_w.
    ``long_range_only`` drops the local-composition term (the PDH row).  The
    forward-difference infinite-dilution reference d0 carries an O(|z_c z_a|
    A_phi sqrt(I(h))) bias in ln gamma+- (1.1e-3 for NaCl at 2 m, ~4e-3 for a
    2:1 salt; measured against the Gibbs-Duhem integral of phi, see
    tests/thermo/test_electrolyte_general.py); kept so NaCl stays bit-identical.
    """
    s = enrtl_salt(salt)
    ions = s.ions
    nu = ions.nu
    nc, na = float(ions.nu_cation), float(ions.nu_anion)
    h = 1e-6 * max(molality, 1e-3)

    def ge_rt(xw: float, xc: float, xa: float) -> float:
        if long_range_only:
            return _pdh_gE_rt(xc, xa, ions)
        return _enrtl_gE_rt(xw, xc, xa, s)

    def total(ms: float, mw: float = _NW) -> float:
        n = mw + nu * ms
        return n * ge_rt(mw / n, nc * ms / n, na * ms / n)

    d_salt = (total(molality + h) - total(molality - h)) / (2.0 * h)
    d0 = (total(h) - total(0.0)) / h  # infinite-dilution reference (unsymmetric normalisation)
    dw = 1e-3
    d_w = (total(molality, _NW + dw) - total(molality, _NW - dw)) / (2.0 * dw)
    xw = _NW / (_NW + nu * molality)
    ln_gamma_pm = (d_salt - d0) / nu + math.log(xw)
    ln_aw = d_w + math.log(xw)
    return ln_gamma_pm, ln_aw


def enrtl_mean_gamma(molality: float, salt: str = "NaCl") -> float:
    """Mean ionic activity coefficient of a single salt, eNRTL 25 C parameter set.

    Applicability: literature-faithful to ~1-5 % vs the PPB84 anchors for NaCl
    (the source model's own fit quality; the high-accuracy brine row is Pitzer).
    """
    return math.exp(_enrtl_ln_props(molality, salt)[0])


def enrtl_water_activity(molality: float, salt: str = "NaCl") -> float:
    """Water activity of a single-salt solution, eNRTL 25 C set (a_w = gamma_w * x_w)."""
    return math.exp(_enrtl_ln_props(molality, salt)[1])


def enrtl_osmotic(molality: float, salt: str = "NaCl") -> float:
    """Osmotic coefficient phi = -ln a_w / (nu * m * M_w), eNRTL 25 C parameter set."""
    return -_enrtl_ln_props(molality, salt)[1] / (enrtl_salt(salt).ions.nu * molality * _MW_WATER_KG)


def pdh_mean_gamma(molality: float, salt: str = "NaCl") -> float:
    """Mean ionic activity coefficient of a single salt from the long-range term alone."""
    return math.exp(_enrtl_ln_props(molality, salt, long_range_only=True)[0])


def pdh_water_activity(molality: float, salt: str = "NaCl") -> float:
    """Water activity of a single salt from the long-range term alone (a_w = gamma_w * x_w)."""
    return math.exp(_enrtl_ln_props(molality, salt, long_range_only=True)[1])


@cache
def enrtl_crystallisation_molality(salt: str = "NaCl") -> float:
    """Solubility (mol/kg) of the eNRTL liquid against the anhydrous solid's solubility product.

    SLE for C_nuc A_nua(s) = nu_c C + nu_a A: (nu_c m)^nu_c (nu_a m)^nu_a gamma+-^nu = K_sp,
    a_w absent for the anhydrous solid; the stoichiometric factor is the same at the
    anchor and at the solution, so the condition is m gamma+- = m_sat gamma_sat for any
    salt.  K_sp comes from the model-independent anchor (NaCl: 6.146 mol/kg at gamma
    1.0065, Pitzer, Peiper & Busey 1984), so the molality this returns is what the
    eNRTL liquid predicts for that solid, with the liquid model's own error in it.
    """
    entry = _salt_entry(_enrtl(), salt, "eNRTL", "enrtl.yaml")
    if "saturation" not in entry:
        raise ElectrolyteChemistryError(f"no saturation anchor for {salt!r} in enrtl.yaml")
    p = entry["saturation"]
    product = float(p["solubility_molality"]) * float(p["mean_gamma"])

    def residual(m: float) -> float:
        return m * enrtl_mean_gamma(m, salt) - product

    return brent_root(residual, 4.0, 10.0)


def enrtl_saturation_molality(salt: str = "NaCl") -> float:
    """Solubility (mol/kg) from the SLE condition gamma(m) == gamma_sat (NaCl: PPB84 p. 11)."""
    entry = _salt_entry(_enrtl(), salt, "eNRTL", "enrtl.yaml")
    return _sle_molality(lambda m: enrtl_mean_gamma(m, salt), entry, salt, "enrtl.yaml")


# -- extended UNIQUAC single-salt brines (Thomsen & Rasmussen 1999; formulation per Leal 2025)


@cache
def _ext_uniquac() -> dict[str, Any]:
    """Cached extended-UNIQUAC parameter table (data/thermo_params/electrolyte/ext_uniquac.yaml)."""
    with (_PARAMS_DIR / "ext_uniquac.yaml").open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return cast(dict[str, Any], data)


@cache
def ext_uniquac_salt(salt: str) -> SaltIons:
    """The ion pair of ``salt`` in ext_uniquac.yaml (species keys of the r/q/u tables).

    A salt whose ions lack an r, q or u0/u1 pair entry refuses here, not mid-solve.
    """
    p = _ext_uniquac()
    ions = _salt_ions(salt, _salt_entry(p, salt, "extended-UNIQUAC", "ext_uniquac.yaml"))
    species = ("H2O", ions.cation, ions.anion)
    missing = [k for k in species if k not in p["q"] or k not in p["r"]]
    missing += [
        f"{i}-{j}"
        for i in species
        for j in species
        if f"{i}-{j}" not in p["u0"] and f"{j}-{i}" not in p["u0"]
    ]
    if missing:
        raise ElectrolyteChemistryError(
            f"ext_uniquac.yaml entry {salt!r} lacks species parameters {sorted(set(missing))}"
        )
    return ions


def ext_uniquac_salts() -> tuple[str, ...]:
    """Every salt (component id) with an extended-UNIQUAC entry, sorted."""
    return tuple(sorted(_ext_uniquac()["salts"]))


def _eu_species(salt: str) -> tuple[str, str, str]:
    """Species order of the extended-UNIQUAC tables for one salt: (H2O, cation, anion)."""
    ions = ext_uniquac_salt(salt)
    return ("H2O", ions.cation, ions.anion)


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
    molality: float, t_k: float, salt: str = "NaCl"
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, dict[str, float]]]:
    """(x, phi_, theta, psi[j][i]) over the species order (H2O, cation, anion).

    Basis: 1 kg of water, x_c = nu_c m / n, x_a = nu_a m / n, n = 1/M_w + nu m.
    psi_ji = exp[(u_ii - u_ji)/T] (Leal eq 23; the division is by T, NOT RT --
    the /RT reading of the J/mol table is the transcription error that broke
    the first prototype; cross-checked against Reaktoro
    ActivityModelExtendedUNIQUAC.cpp L249, used as a verification reference only).
    """
    p = _ext_uniquac()
    ions = ext_uniquac_salt(salt)
    species = _eu_species(salt)
    q: dict[str, float] = {k: float(p["q"][k]) for k in species}
    r: dict[str, float] = {k: float(p["r"][k]) for k in species}
    n = _NW + ions.nu * molality
    x = {"H2O": _NW / n, ions.cation: ions.nu_cation * molality / n, ions.anion: ions.nu_anion * molality / n}
    rsum = sum(r[k] * x[k] for k in species)
    qsum = sum(q[k] * x[k] for k in species)
    phi_ = {k: x[k] * r[k] / rsum for k in species}
    theta = {k: x[k] * q[k] / qsum for k in species}
    psi: dict[str, dict[str, float]] = {}
    for j in species:
        psi[j] = {i: math.exp((_eu_u_ij(p, i, i, t_k) - _eu_u_ij(p, j, i, t_k)) / t_k) for i in species}
    return x, phi_, theta, psi


def _eu_ln_gamma_u(
    x: dict[str, float], phi_: dict[str, float], theta: dict[str, float], psi: dict[str, dict[str, float]]
) -> dict[str, float]:
    """Closed-form UNIQUAC (combinatorial + residual) ln gamma (Leal eq 43).

    The species are the keys of ``x`` (water first, as :func:`_eu_state` builds
    it).  The residual denominator S_j = sum_l theta_l * psi_lj -- the SAME
    orientation as the G^E; the transposed form fails the finite-difference
    check (verified to 6 decimals in all species and both directions).
    """
    p = _ext_uniquac()
    zc = float(p["zq"])
    species = tuple(x)
    q: dict[str, float] = {k: float(p["q"][k]) for k in species}
    out: dict[str, float] = {}
    for k in species:
        sk = sum(theta[j] * psi[j][k] for j in species)
        comb = (
            math.log(phi_[k] / x[k])
            + 1.0
            - phi_[k] / x[k]
            - (zc / 2.0) * q[k] * (math.log(phi_[k] / theta[k]) + 1.0 - phi_[k] / theta[k])
        )
        res_sum = sum(theta[j] * psi[k][j] / sum(theta[sp] * psi[sp][j] for sp in species) for j in species)
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


def _ext_uniquac_ln_props(molality: float, t_k: float, salt: str = "NaCl") -> tuple[float, float]:
    """(ln gamma+-(m, T), ln a_w(m, T)) of a single-salt solution, extended-UNIQUAC.

    Assembly per Leal et al. 2025: ions ln gamma_i = ln gamma_i,DH +
    (ln gamma_i,U - ln gamma_i,U^inf) + ln x_w (eq 45, unsymmetric molality
    scale), ln gamma_i,DH = -z_i^2 A sqrt(I)/(1 + b sqrt(I)), I = m (nu_c z_c^2 +
    nu_a z_a^2)/2; water ln gamma_w = ln gamma_w,DH + ln gamma_w,U with
    a_w = gamma_w * x_w (eqs 46, 39); the mean is (nu_c ln gamma_c +
    nu_a ln gamma_a)/nu.  The DH term (eq 40/42) uses b = 1.50 (kg/mol)^0.5 and
    A(T) in (kg/mol)^0.5.
    """
    p = _ext_uniquac()
    ions = ext_uniquac_salt(salt)
    b_dh = float(p["dh"]["b"])
    x, _phi_, _theta, psi = _eu_state(molality, t_k, salt)
    sq = math.sqrt(0.5 * molality * ions.charge_sum)  # sqrt(I); I == m for a 1:1 salt
    big = 1.0 + b_dh * sq
    a_dh = _eu_a_dh(t_k)
    ln_g_dh_w = (2.0 * a_dh * _MW_WATER_KG / b_dh**3) * (big - 1.0 / big - 2.0 * math.log(big))
    ln_g_u = _eu_ln_gamma_u(x, _phi_, _theta, psi)
    xw = x["H2O"]
    ln_g_c = (
        -(ions.z_cation**2) * a_dh * sq / big
        + ln_g_u[ions.cation]
        - _eu_ln_gamma_inf(ions.cation, t_k)
        + math.log(xw)
    )
    ln_g_a = (
        -(ions.z_anion**2) * a_dh * sq / big
        + ln_g_u[ions.anion]
        - _eu_ln_gamma_inf(ions.anion, t_k)
        + math.log(xw)
    )
    ln_g_w = ln_g_dh_w + ln_g_u["H2O"]
    return (ions.nu_cation * ln_g_c + ions.nu_anion * ln_g_a) / ions.nu, ln_g_w + math.log(xw)


def ext_uniquac_mean_gamma(molality: float, t_k: float = 298.15, salt: str = "NaCl") -> float:
    """Mean ionic activity coefficient of a single salt, extended-UNIQUAC (Thomsen params).

    Applicability: literature-faithful to a few % vs the PPB84 anchors for NaCl
    (the source model's own fit quality; the high-accuracy brine row is Pitzer).
    """
    return math.exp(_ext_uniquac_ln_props(molality, t_k, salt)[0])


def ext_uniquac_water_activity(molality: float, t_k: float = 298.15, salt: str = "NaCl") -> float:
    """Water activity of a single-salt solution, extended-UNIQUAC (a_w = gamma_w * x_w)."""
    return math.exp(_ext_uniquac_ln_props(molality, t_k, salt)[1])


def ext_uniquac_osmotic(molality: float, t_k: float = 298.15, salt: str = "NaCl") -> float:
    """Osmotic coefficient phi = -ln a_w / (nu * m * M_w), extended-UNIQUAC."""
    nu = ext_uniquac_salt(salt).nu
    return -_ext_uniquac_ln_props(molality, t_k, salt)[1] / (nu * molality * _MW_WATER_KG)


def ext_uniquac_saturation_molality(salt: str = "NaCl") -> float:
    """Solubility (mol/kg) from the SLE condition gamma(m) == gamma_sat (NaCl: PPB84 p. 11)."""
    entry = _salt_entry(_ext_uniquac(), salt, "extended-UNIQUAC", "ext_uniquac.yaml")
    return _sle_molality(lambda m: ext_uniquac_mean_gamma(m, salt=salt), entry, salt, "ext_uniquac.yaml")


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


def _salt_molality(x_salt: float, x_w: float, cap: float = _MAX_MOLALITY) -> float:
    """Salt molality (mol/kg water) from liquid mole fractions, clamped to the fitted domain."""
    if x_w <= 0.0:
        raise ElectrolyteChemistryError("the brine liquid carries no water (molality undefined)")
    m = 1000.0 * x_salt / (_mw("H2O") * x_w)
    return min(m, cap)


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


#: Per-model water-activity surface a_w(m, salt) of the brine models (the K-value
#: and fugacity driver: K_H2O = a_w(m) * Psat_H2O / P; the salt is involatile).
_WATER_ACTIVITY: dict[str, Callable[[float, str], float]] = {
    "pitzer": pitzer_water_activity,
    "enrtl": enrtl_water_activity,
    "pdh": pdh_water_activity,
    "ext_uniquac": lambda m, salt: ext_uniquac_water_activity(m, salt=salt),
}

#: Per-model salt tables: (salts with an entry, salt -> its molality cap).  The
#: PDH row reads the eNRTL file (its A_phi, rho and the salts' charges).
_BRINE_SALTS: dict[str, tuple[Callable[[], tuple[str, ...]], Callable[[str], float]]] = {
    "pitzer": (pitzer_salts, lambda salt: pitzer_salt(salt).molality_cap),
    "enrtl": (enrtl_salts, lambda salt: enrtl_salt(salt).ions.molality_cap),
    "pdh": (enrtl_salts, lambda salt: enrtl_salt(salt).ions.molality_cap),
    "ext_uniquac": (ext_uniquac_salts, lambda salt: ext_uniquac_salt(salt).molality_cap),
}

#: What a multi-salt feed would need on each brine model (the first-use refusal).
_MIXING_GAP: dict[str, str] = {
    "pitzer": "the mixing parameters theta/psi",
    "enrtl": "the salt-salt NRTL pairs",
    "pdh": "the eNRTL salt-salt NRTL pairs",
    "ext_uniquac": "the cross-salt ion-ion u_ij pairs",
}


class ElectrolytePackage(TracedThermo, Thermo):
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

    #: Vapour model: None keeps the ideal-vapour K_H2O = a_w Psat / P with the
    #: carrier's vapour properties; "rk" and "hoc" put a real water vapour in both.
    vapour_model: str | None = None

    #: Top of the liquid's molality range: the saturated solution (or the verified
    #: range) for this row and salt.
    def _molality_cap(self, salt: str = "NaCl") -> float:
        return _BRINE_SALTS[self._model][1](salt)

    def __init__(self, model: str | None = None) -> None:
        self._model = model or type(self).model
        carrier_cls = cast(type[Thermo], _registry_get("thermo", "pr"))
        self._carrier: Thermo = carrier_cls()
        self._vapour: Thermo = self._carrier
        if self.vapour_model == "rk":
            self._vapour = cast(type[Thermo], _registry_get("thermo", "rk"))()
        elif self.vapour_model == "hoc":
            # Only the vapour half is used: pure water has no NRTL pair to look up.
            self._vapour = cast(Thermo, GammaPhiPackage("nrtl", "hoc"))
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

    def _water_activity(self, molality: float, salt: str = "NaCl") -> float:
        """This model's water-activity surface a_w(m) (the brine chemistry driver)."""
        return _WATER_ACTIVITY[self._model](molality, salt)

    def _supported_ids(self) -> frozenset[str]:
        """Stream ids this model's chemistry covers (water plus its salts or volatiles)."""
        if self._model in _BRINE_SALTS:
            return frozenset({"H2O", *_BRINE_SALTS[self._model][0]()})
        return _MODEL_SUPPORTS[self._model]

    def _salt_id(self, comp: dict[str, float]) -> str:
        """The brine's salt: the one non-water component present (NaCl when none is).

        With no salt present every salt fraction reads 0.0, so the default only
        names which (zero) entry is looked up; :meth:`_electrolyte_domain`
        has already refused a feed with more than one salt.
        """
        present = [cid for cid in self._support(comp) if cid != "H2O"]
        return present[0] if present else "NaCl"

    def _water_vapour_ln_phi(self, t_k: float, p: float) -> float:
        """ln phi of pure water vapour on this package's vapour model."""
        return self._vapour.phase_props({"H2O": 1.0}, t_k, p, PhaseKind.VAPOR).ln_phi["H2O"]

    def _water_fugacity_ratio(self, t_k: float, p: float) -> float:
        """phi_sat(T) / phi_V(T, P) of water: the real-vapour factor on K_H2O.

        Equal water fugacities a_w Psat phi_sat = y P phi_V, the Poynting term of a
        brine at these pressures left out.  1.0 on the ideal-vapour rows, and at or
        above Psat, where no water vapour exists to evaluate (a brine's bubble
        pressure is below Psat, so such a state is a liquid regardless).
        """
        psat = _psat_or_wilson("H2O", t_k)
        if self.vapour_model is None or p >= psat:
            return 1.0
        return math.exp(self._water_vapour_ln_phi(t_k, psat) - self._water_vapour_ln_phi(t_k, p))

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
        supported = self._supported_ids()
        unsupported = [cid for cid in self._support(z) if cid not in supported]
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
                f"{sorted(supported)}; no verified parameters "
                f"for {sorted(unsupported)}{co2_note} (first-use refusal, T-07 precedent)"
            )
        salts = [cid for cid in self._support(z) if cid != "H2O"]
        if self._model in _BRINE_MODELS and len(salts) > 1:
            raise NotImplementedError(
                f"electrolyte model {self._model!r} is single-salt: {sorted(salts)} together need "
                f"{_MIXING_GAP[self._model]}, which this row does not ship (first-use refusal)"
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
        salt = self._salt_id(x)
        m = _salt_molality(x.get(salt, 0.0), x.get("H2O", 0.0), self._molality_cap(salt))
        psat = _psat_or_wilson("H2O", t_k) * self._water_fugacity_ratio(t_k, p)
        k_h2o = self._water_activity(m, salt) * psat / p
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

        The salt stays in the liquid (y_salt = 0), so two-phase states carry
        pure-water vapour and follow from two balances: the liquid
        concentrates until its bubble pressure a_w(m*)*Psat(T) == P, and the
        salt balance sets the vapour fraction beta = 1 - z_salt/x_salt(m*).
        Above the feed's bubble pressure the state is a single liquid at the
        feed molality; below the saturated-solution pressure the salt would
        precipitate, which the model refuses (it carries no solid phase).
        """
        psat = _psat_or_wilson("H2O", t_k)
        salt = self._salt_id(z)
        if z.get(salt, 0.0) <= 0.0:
            if p >= psat:
                return "liquid", 0.0, dict(z), dict(z)
            return "vapor", 1.0, dict(z), dict(z)
        cap = self._molality_cap(salt)
        m_feed = _salt_molality(z[salt], z.get("H2O", 0.0), cap)
        psat *= self._water_fugacity_ratio(t_k, p)
        if p >= self._water_activity(m_feed, salt) * psat:
            return "liquid", 0.0, dict(z), dict(z)
        # Below the feed's bubble pressure the boiling liquid concentrates,
        # shedding pure-water vapour, until it reaches the saturated-solution
        # molality -- the model's two-phase limit.  Below the saturated
        # solution's own bubble pressure a solid salt phase would appear,
        # which the model does not carry: the split pins the liquid at the
        # saturation molality there (a constant-vf plateau, so saturation
        # scans keep a continuous surface) and the FLASH path refuses the
        # state (_build_state checks the solved liquid's molality).

        def excess(m: float) -> float:
            return self._water_activity(m, salt) * psat - p

        # excess starts positive at m_feed (the state is above its bubble)
        # and decreases with m (a_w falls); the root exists inside the
        # bracket exactly when the saturated-solution end has gone negative.
        if excess(cap) < 0.0:
            m_star = brent_root(excess, m_feed, cap)
        else:
            m_star = cap
        mw_water = _mw("H2O") / 1000.0  # kg/mol, to match the molality basis
        x_salt = m_star * mw_water / (1.0 + m_star * mw_water)
        beta = min(1.0 - z[salt] / x_salt, 1.0)
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
        # The bubble-point liquid is the feed itself.
        self._refuse_beyond_pdh_cap(z, "its bubble point")
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
            # A real-vapour row refers the water fugacity to phi_sat, the reference
            # its K-value uses; the other rows keep the amine packages' form.
            p_ref = _psat_or_wilson("H2O", T) if self.vapour_model and cid == "H2O" else f_i
            phi_v = self._vapour.phase_props({cid: 1.0}, T, p_ref, PhaseKind.VAPOR).ln_phi[cid]
            ln_phi[cid] = math.log(f_i * math.exp(phi_v) / P)
        return base.model_copy(update={"ln_phi": ln_phi})

    def _fugacities(self, x: dict[str, float], T: float, P: float) -> dict[str, float | None]:
        """Component fugacities f_i (Pa) on the aqueous electrolyte liquid.

        Pitzer brine: f_H2O = a_w(m) * Psat_H2O, the salt involatile (None).
        Sour water: f_NH3 and f_H2S are the SWEQ equilibrium partial
        pressures.  Absent components return None.
        """
        if self._model != "sour_water":
            salt = self._salt_id(x)
            m = _salt_molality(x.get(salt, 0.0), x.get("H2O", 0.0), self._molality_cap(salt))
            a_w = self._water_activity(m, salt)
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

    def _refuse_beyond_pdh_cap(self, x: dict[str, float], where: str) -> None:
        """Refuse a PDH liquid above its dilute-solution molality cap (other models: no-op)."""
        if self._model == "pdh" and x.get("H2O", 0.0) > 0.0:
            m_liq = 1000.0 * x.get(self._salt_id(x), 0.0) / (_mw("H2O") * x["H2O"])
            if m_liq > _PDH_MAX_MOLALITY:
                raise ElectrolyteChemistryError(
                    f"the Pitzer-Debye-Hueckel term alone is a dilute-solution model: liquid "
                    f"molality {m_liq:.3g} mol/kg at {where} is above its "
                    f"{_PDH_MAX_MOLALITY} mol/kg cap - use enrtl_nacl_water or pitzer_nacl_water"
                )

    def _build_state(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        state, beta, x, y = self._equilibrium_internal(z, T, P)
        self._refuse_beyond_pdh_cap(x, f"T={T} K, P={P} Pa")
        if state == "two_phase" and self._model in _BRINE_MODELS and x.get("H2O", 0.0) > 0.0:
            salt = self._salt_id(x)
            m_liq = 1000.0 * x.get(salt, 0.0) / (_mw("H2O") * x["H2O"])
            if m_liq >= self._molality_cap(salt):
                raise ElectrolyteChemistryError(
                    f"the brine flash at T={T} K, P={P} Pa needs more than the "
                    f"saturated-solution molality ({self._molality_cap(salt)} mol/kg): {salt} would "
                    "precipitate, which the model does not represent"
                )
        if state == "vapor":
            props = self._vapour.phase_props(z, T, P, PhaseKind.VAPOR)
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
        vapor_props = self._vapour.phase_props(y, T, P, PhaseKind.VAPOR)
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
    """Pitzer single-salt brine: water activity, osmotic and mean activity coefficients.

    The row id keeps its historical name; the salt is whichever single salt of
    data/thermo_params/electrolyte/pitzer.yaml the feed carries (NaCl, KCl,
    KBr, LiCl, NaBr, MgCl2 at the PHRQPITZ 25 C sets).
    """

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


class ElectrolytePDH(ElectrolytePackage):
    """The Pitzer-Debye-Hueckel long-range term alone, NaCl(aq) below 0.2 mol/kg."""

    model = "pdh"


class ElectrolyteENRTLRK(ElectrolyteENRTLNaCl):
    """eNRTL NaCl(aq) liquid with a Redlich-Kwong water vapour."""

    vapour_model = "rk"


class ElectrolyteENRTLHOC(ElectrolyteENRTLNaCl):
    """eNRTL NaCl(aq) liquid with a Hayden-O'Connell water vapour."""

    vapour_model = "hoc"


class ElectrolytePitzerHOC(ElectrolytePitzerNaCl):
    """Pitzer single-salt brine liquid with a Hayden-O'Connell water vapour."""

    vapour_model = "hoc"


class ElectrolyteENRTLCrystal(ElectrolyteENRTLNaCl):
    """eNRTL NaCl(aq) with solid NaCl past the solubility limit.

    The solubility is :func:`enrtl_crystallisation_molality`, m_sat. Regions at (T, P),
    with P* = a_w(m_sat) Psat the saturated solution's bubble pressure:

    - P < P*: vapour plus solid: all the water boils off the salt;
    - feed at or below m_sat, P >= P*: the base row's liquid or vapour + liquid;
    - feed above m_sat, P >= P*: saturated liquid plus solid.

    The solid's volume and heat capacity are the databank's. Its enthalpy and entropy
    are the carrier's values for NaCl: the heat of crystallisation is not represented,
    as the base rows carry no heat of solution.
    """

    def _molality_cap(self, salt: str = "NaCl") -> float:
        return enrtl_crystallisation_molality(salt)

    def solubility(self, cid: str, T: float) -> float:
        """Mole fraction of salt ``cid`` in its saturated solution at ``T`` (K).

        x_sat = m_sat M_w / (1 + m_sat M_w), the salt counted as one undissociated
        species on the package's stream basis (the saturated liquid's composition in
        :meth:`_build_state`), m_sat from :func:`enrtl_crystallisation_molality`
        (mol/kg) and M_w water's molar mass (kg/mol). The 25 C parameter set has no
        temperature dependence, so T only gates the row's window.
        """
        if cid == "H2O" or cid not in self._supported_ids():
            raise ElectrolyteChemistryError(f"no solubility for {cid!r}: not a salt of this row")
        lo, hi = _MODEL_WINDOWS[self._model]
        if not lo <= T <= hi:
            raise ElectrolyteChemistryError(
                f"solubility at T={T} K is outside the {self._model!r} window [{lo}, {hi}] K"
            )
        return self._saturated_salt_fraction(cid)

    def _saturated_salt_fraction(self, salt: str) -> float:
        """Salt mole fraction of the saturated liquid (the stream basis, salt undissociated)."""
        m_mw = self._molality_cap(salt) * (_mw("H2O") / 1000.0)
        return m_mw / (1.0 + m_mw)

    def _build_state(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        salt_id = self._salt_id(z)
        salt, water = z.get(salt_id, 0.0), z.get("H2O", 0.0)
        if salt <= 0.0 or water <= 0.0:
            return super()._build_state(z, T, P, molar_flow)
        m_sat = self._molality_cap(salt_id)
        p_star = self._water_activity(m_sat, salt_id) * _psat_or_wilson("H2O", T)
        mw_water = _mw("H2O") / 1000.0  # kg/mol
        if P >= p_star and salt / (water * mw_water) <= m_sat:
            return super()._build_state(z, T, P, molar_flow)
        solid_pure = {cid: (1.0 if cid == salt_id else 0.0) for cid in z}
        if P < p_star:
            y = {cid: (1.0 if cid == "H2O" else 0.0) for cid in z}
            fluid = _phase(PhaseKind.VAPOR, water, y, self._vapour.phase_props(y, T, P, PhaseKind.VAPOR))
        else:
            x_salt = self._saturated_salt_fraction(salt_id)
            x = {cid: (x_salt if cid == salt_id else 1.0 - x_salt) for cid in z}
            props = self.phase_props(x, T, P, PhaseKind.AQUEOUS)
            fluid = _phase(PhaseKind.AQUEOUS, water / (1.0 - x_salt), x, props)
        solid = self._solid_phase(1.0 - fluid.mole_fraction, solid_pure, T, P, salt_id)
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=fluid.mole_fraction if fluid.kind == PhaseKind.VAPOR else 0.0,
            enthalpy=fluid.mole_fraction * fluid.enthalpy + solid.mole_fraction * solid.enthalpy,
            entropy=fluid.mole_fraction * fluid.entropy + solid.mole_fraction * solid.entropy,
            phases=[fluid, solid],
        )

    def _solid_phase(
        self, fraction: float, composition: dict[str, float], T: float, P: float, salt: str = "NaCl"
    ) -> Phase:
        """The anhydrous salt(s) phase; a databank with no solid volume or Cp refuses."""
        record = _record(salt)
        with DATABANK_LOCK:
            _constants, correlations = _constants_for((str(record["cas"]),))
        volume = correlations.VolumeSolids[0](T)
        cp = correlations.HeatCapacitySolids[0](T)
        if volume is None or cp is None:
            raise ElectrolyteChemistryError(f"no solid {salt} volume or Cp in the databank at T={T} K")
        carrier = self._carrier.phase_props({salt: 1.0}, T, P, PhaseKind.HC_LIQUID)
        mw = _mw(salt)
        return Phase(
            kind=PhaseKind.SOLID,
            mole_fraction=fraction,
            composition=composition,
            density=mw / 1000.0 / float(volume),
            molecular_weight=mw,
            enthalpy=carrier.enthalpy,
            entropy=carrier.entropy,
            cp=float(cp),
        )
