"""Typed option declarations for the cubic-EOS adapter (specs T-01/T-02).

A catalogue row selects option values as DATA; this module declares the value
vocabulary each option group accepts plus :class:`CubicOptionValues`, the
frozen runtime value object the cubic adapter keys its flasher cache on.

Implemented value -> mechanism (spec T-02):

- ``AlphaFunction.TWU``: the `thermo` library's generalised-Twu classes
  (``TWUPRMIX`` / ``TWUSRKMIX``, Twu et al. 1995) — PRMIX/SRKMIX with the
  generalised three-parameter Twu alpha.
- ``AlphaFunction.MATHIAS_COPEMAN``: in-house ``PRMIX_MC`` / ``SRKMIX_MC``
  (Mathias-Copeman 1983 polynomial alpha) with the published per-component
  parameters of Coquelet et al. (2004) Table II where a component has them and
  the EOS default alpha (``c1 = kappa(omega)``) otherwise.
- ``AlphaFunction.BOSTON_MATHIAS``: in-house ``PRMIX_BM`` / ``SRKMIX_BM`` —
  Soave/PR alpha below Tr=1 and the Boston-Mathias (1980) supercritical
  extrapolation ``alpha = exp[C_d (1 - Tr^d)]`` with ``d = 1 + m/2`` and
  ``C_d = m/d^2`` above (positive and decreasing where the Soave bracket goes
  through zero and negative).
- ``AlphaFunction.ZUDKEVITCH_JOFFE``: in-house ``ZJRKMIX`` — RK whose
  ``Omega_a(T)`` is solved per component so the pure-component fugacity
  equality holds at the databank vapour pressure (Zudkevitch & Joffe 1970),
  falling back to the RK ``Tr^-0.5`` form at/above Tc. Vocabulary extension
  beyond the spec's option list (deviation documented in the PR): the spec
  does not name the ZJ row's option.
- ``AlphaFunction.TWU_SIM_TASSONE``: in-house ``TSTMIX`` — the Twu-Sim-Tassone
  (2002) cubic (``ac = 0.470507 R^2 Tc^2 / Pc``, ``b = 0.0740740 RTc/Pc``,
  ``v^2 + 2.5 b v - 1.5 b^2``) with its fitted Twu-form alpha table.
  Vocabulary extension (deviation documented in the PR).
- ``MixingRule.KABADI_DANNER``: in-house ``SRKMIXKD`` — SRK with the Kabadi-Danner
  (1985) water-hydrocarbon asymmetric mixing rule ``x_w x_j^2 a''_j(T)``.
  Vocabulary extension (deviation documented in the PR).
- ``VolumeTranslation.PENELOUX``: the library's translated classes
  (``PRMIXTranslated`` / ``SRKMIXTranslated``) fed in-house Rackett ``cs``
  (Peneloux et al. 1982); shifts density, never VLE.
- ``LiquidDensity``: vocabulary per the spec; only ``EOS`` (the plain EOS
  density) has an implementation. No family-A row declares a non-default
  value, so the others stay declaration-only and ``catalogue.build`` rejects
  them until a row needs one.
- ``SourTerm.SOUR``: in-house Wilson API-955-style sour-water ionisation
  correction on the aqueous liquid phase (API Publication 955 / EPA-600/2-80-067).
- ``EnthalpyMethod.LEE_KESLER``: in-house Lee-Kesler (1975) corresponding-states
  enthalpy departures replacing the cubic EOS departure on the phase objects
  (enthalpy only, never VLE).

An option value outside its group's vocabulary never loads: the catalogue
validates row options against these declarations at load time
(``ngdesign.thermo.catalogue``), with the file and row named.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AlphaFunction(StrEnum):
    """Alpha-function group of the cubic adapter."""

    DEFAULT = "default"
    TWU = "twu"
    MATHIAS_COPEMAN = "mathias_copeman"
    BOSTON_MATHIAS = "boston_mathias"
    ZUDKEVITCH_JOFFE = "zudkevitch_joffe"
    TWU_SIM_TASSONE = "twu_sim_tassone"


class VolumeTranslation(StrEnum):
    """Volume-translation group of the cubic adapter."""

    NONE = "none"
    PENELOUX = "peneloux"


class KValueModel(StrEnum):
    """K-value correlation group of the K-value adapters (spec T-05)."""

    CHAO_SEADER = "chao_seader"
    GRAYSON_STREED = "grayson_streed"
    BRAUN_K10 = "braun_k10"
    LEE_KESLER_PLOCKER = "lee_kesler_plocker"
    IDEAL = "ideal"
    HENRY_IDEAL = "henry_ideal"


class LiquidDensity(StrEnum):
    """Liquid-density model group of the cubic adapter."""

    EOS = "eos"
    RACKETT = "rackett"
    COSTALD = "costald"
    API = "api"


class SourTerm(StrEnum):
    """Sour-water treatment group of the cubic adapter."""

    NONE = "none"
    SOUR = "sour"


class MixingRule(StrEnum):
    """Mixing-rule modification group of the cubic adapter."""

    NONE = "none"
    KABADI_DANNER = "kabadi_danner"


class EnthalpyMethod(StrEnum):
    """Enthalpy-departure group of the cubic adapter."""

    EOS = "eos"
    LEE_KESLER = "lee_kesler"


class GammaPhiLiquid(StrEnum):
    """Liquid-phase model group of the gamma-phi adapter (spec T-03)."""

    NRTL = "nrtl"
    UNIQUAC = "uniquac"
    WILSON = "wilson"
    VANLAAR = "vanlaar"
    MARGULES = "margules"
    REGULAR_SOLUTION = "regular_solution"
    UNIFAC = "unifac"
    UNIFAC_DORTMUND = "unifac_dortmund"
    UNIFAC_PSRK = "unifac_psrk"
    UNIFAC_NIST = "unifac_nist"
    UNIFAC_LLE = "unifac_lle"
    UNIFAC_LYNGBY = "unifac_lyngby"


class GammaPhiVapour(StrEnum):
    """Vapour-phase model group of the gamma-phi adapter (spec T-03)."""

    IDEAL = "ideal"
    HOC = "hoc"
    NOTHNAGEL = "nothnagel"
    RK = "rk"
    PR = "pr"


class GammaPhiOptions(BaseModel):
    """Typed options for family ``gamma_phi`` (values declared in thermo.options).

    Parameters provenance stays in each row's ``params`` field and in
    ``data/thermo_params/<model>/``; the options only pin which liquid and
    vapour models the row's flasher wires together.
    """

    model_config = ConfigDict(extra="forbid")

    liquid: GammaPhiLiquid
    vapour: GammaPhiVapour


@dataclass(frozen=True)
class CubicOptionValues:
    """The option values that change the cubic flasher's construction.

    Frozen and hashable: the flasher factory cache keys on it, so two rows
    whose options differ never share a flasher instance.
    """

    alpha: AlphaFunction = AlphaFunction.DEFAULT
    translation: VolumeTranslation = VolumeTranslation.NONE
    liquid_density: LiquidDensity = LiquidDensity.EOS
    sour: SourTerm = SourTerm.NONE
    enthalpy: EnthalpyMethod = EnthalpyMethod.EOS
    mixing: MixingRule = MixingRule.NONE

    @property
    def is_default(self) -> bool:
        """True when every value is the plain ``thermo``-library behaviour."""
        return self == CUBIC_OPTION_DEFAULTS


CUBIC_OPTION_DEFAULTS = CubicOptionValues()
