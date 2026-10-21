"""Typed option declarations for the cubic-EOS adapter (spec T-01).

A catalogue row selects option values as DATA; this module declares the value
vocabulary each option group accepts. Declarations only: the ``DEFAULT`` /
``NONE`` / ``EOS`` member of each group is the one implementation the cubic
adapter has today (the plain ``thermo``-library behaviour), and the catalogue
row's default values are exactly what the existing packages do. T-02 fills the
non-default implementations (Twu and Mathias-Copeman alpha, Peneloux volume
translation, Lee-Kesler enthalpy departures); until then ``catalogue.build``
raises :class:`NotImplementedError` naming the option when a row declares a
non-default value.

An option value outside its group's vocabulary never loads: the catalogue
validates row options against these declarations at load time
(``ngdesign.thermo.catalogue``), with the file and row named.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AlphaFunction(StrEnum):
    """Alpha-function group of the cubic adapter (T-02 adds the implementations)."""

    DEFAULT = "default"
    TWU = "twu"
    MATHIAS_COPEMAN = "mathias_copeman"


class VolumeTranslation(StrEnum):
    """Volume-translation group of the cubic adapter (T-02 adds Peneloux)."""

    NONE = "none"
    PENELOUX = "peneloux"


class EnthalpyMethod(StrEnum):
    """Enthalpy-departure group of the cubic adapter (T-02 adds Lee-Kesler)."""

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
