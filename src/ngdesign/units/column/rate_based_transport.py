"""Transport properties and packed-bed mass-transfer correlations for the rate-based
(non-equilibrium) stage model of :mod:`ngdesign.units.column.rate_based`.

Everything here is a pure function of state; no thermo-package calls. The rate-based
solver feeds it the per-phase density, viscosity, heat capacity and thermal
conductivity it reads from the flowsheet package's ``phase_props``.

Sources (every constant below was read from the cited source before coding):

* **Packing - Onda, Takeuchi & Okumoto (1968)**, "Mass transfer coefficients between
  gas and liquid phases in packed columns", J. Chem. Eng. Japan 1(1), 56-62. Read from
  the J-STAGE scan (jcej1968/1/1/1_1_56):

  - eq. (1), wetted area taken as the gas-liquid interfacial area::

        a_w/a_t = 1 - exp{-1.45 (sigma_c/sigma)^0.75 (L/(a_t mu_L))^0.1
                           (L^2 a_t/(rho_L^2 g))^-0.05 (L^2/(rho_L sigma a_t))^0.2}

  - eq. (2), liquid film::

        k_L (rho_L/(mu_L g))^(1/3) = 0.0051 (L/(a_w mu_L))^(2/3)
                                     (mu_L/(rho_L D_L))^(-1/2) (a_t D_p)^0.4

  - eq. (3), gas film::

        k_G R T/(a_t D_G) = 5.23 (G/(a_t mu_G))^0.7 (mu_G/(rho_G D_G))^(1/3) (a_t D_p)^-2.0

    with the constant 5.23 changed to 2.00 for packings smaller than 15 mm (text below
    eq. 3).
  - Stated accuracy: eq. (2) within +-20 %, eq. (3) within +-30 %; Raschig rings,
    Berl saddles, spheres and rods (ceramic, glass, PVC, paraffin-coated). The data
    behind eqs. (2)-(3) span the modified Reynolds numbers on the axes of Figs. 1-3
    and 7: ``Re_L = L/(a_w mu_L)`` about 1 to 1000 and ``Re_G = G/(a_t mu_G)`` about
    1 to 2000. :data:`ONDA_RE_L_RANGE` / :data:`ONDA_RE_G_RANGE` carry those
    figure-axis spans; the solver reports (does not refuse) excursions.

  ``L`` and ``G`` are superficial mass velocities, ``a_t`` the total packing area per
  volume, ``D_p`` the nominal packing size, ``sigma_c`` the critical surface tension of
  the packing material. All groups are dimensionless, so SI inputs give SI outputs;
  ``k_G R T`` is the concentration-based gas coefficient in m/s.

* **Gas diffusivity - Chapman-Enskog**, Bird, Stewart & Lightfoot, *Transport
  Phenomena* (2nd ed., 2007), eq. 17.3-12::

      D_AB [cm2/s] = 0.0018583 sqrt(T^3 (1/M_A + 1/M_B)) / (p[atm] sigma_AB^2 Omega_D)

  with ``sigma_AB = (sigma_A + sigma_B)/2`` [Angstrom], ``eps_AB = sqrt(eps_A eps_B)``,
  ``Omega_D`` at ``T* = kT/eps_AB`` (form and mixing rules confirmed on the TILMedia
  ``binaryDiffCoeff_ij_Chapman_Enskog`` documentation, which cites Poling et al. and
  Bird et al.; the constant equals Poling, Prausnitz & O'Connell 5th ed. eq. 11-3.2's
  0.00266 in bar with ``M_AB = 2/(1/M_A + 1/M_B)``: 0.0018583 * sqrt(2) * 1.01325 =
  0.002663). The Lennard-Jones parameters and the Neufeld-Janzen-Aziz collision
  integral are the ``chemicals.lennard_jones`` library functions. Low-pressure theory:
  the 1/P scaling is used at elevated pressure with no dense-gas correction.

* **Mixture vapour diffusivity - Wilke (1950)** (Blanc's law form), ``D_im = (1 - y_i)
  / sum_{k != i} y_k/D_ik`` (Taylor & Krishna 1993, the effective-diffusivity method).

* **Liquid diffusivity - Wilke & Chang (1955)**, AIChE J. 1, 264::

      D_AB [cm2/s] = 7.4e-8 (phi M_B)^0.5 T / (eta_B[cP] V_A^0.6)

  ``V_A`` the solute molar volume at its normal boiling point [cm3/mol], ``phi`` the
  solvent association factor: 2.6 for water, 1.0 for unassociated solvents (constant
  and factors confirmed on the Universidad de Cantabria OCW mass-transfer problem set
  and the IntechOpen chapter 60799 SI form 7.4e-12). Application choice, stated: the
  solvent of component i is the pseudo-solvent of the other liquid components, its
  ``phi M`` their mole-fraction-weighted mean, ``eta`` the mixture liquid viscosity.
  ``V_A`` comes from the ``chemicals.volume.Yamada_Gunn`` saturated-liquid volume at the
  component's normal boiling point.

* **Heat transfer - Chilton-Colburn analogy** for the vapour film (``j_H = j_D`` gives
  ``h = k c_t c_p Le^(2/3)``, ``Le = lambda/(rho c_p,mass D)``) and the **penetration
  model** (Higbie 1935) for the liquid film (``h = k c_t c_p Le^(1/2)``) - the choices
  the rate-based literature names for this purpose (Taylor & Krishna 1993 ch. 11;
  Taylor, Kooijman & Hung 1994).

The ``chemicals`` package installed with this project (1.5.2) ships no diffusivity
module, so the Wilke-Chang and Chapman-Enskog formulas are written here from the
sources above around the library's Lennard-Jones, collision-integral and liquid-volume
functions.

All SI unless a docstring says otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

from chemicals.lennard_jones import Stockmayer, collision_integral_Neufeld_Janzen_Aziz, molecular_diameter
from chemicals.volume import Yamada_Gunn

from ngdesign.data import component_record

#: CODATA standard gravity, m/s2.
STANDARD_GRAVITY = 9.80665

#: Onda 1968 eq. (3): 5.23 for packings >= 15 mm, 2.00 below.
_ONDA_KG_LARGE = 5.23
_ONDA_KG_SMALL = 2.00
_ONDA_SMALL_PACKING_M = 0.015

#: Figure-axis spans of the Onda (1968) data (Figs. 1-3, 7); reported, not enforced.
ONDA_RE_L_RANGE = (1.0, 1000.0)
ONDA_RE_G_RANGE = (1.0, 2000.0)

#: Bird-Stewart-Lightfoot eq. 17.3-12 constant (D cm2/s, T K, M g/mol, p atm, sigma A).
_CE_CONSTANT = 0.0018583
_ATM_PA = 101325.0

#: Wilke & Chang (1955) constant (D cm2/s, T K, eta cP, V cm3/mol) and association
#: factors (water 2.6; unassociated 1.0).
_WILKE_CHANG = 7.4e-8
_WATER_CAS = "7732-18-5"
_PHI_WATER = 2.6


class RateBasedPropertyError(ValueError):
    """A transport property or correlation input is outside its domain."""


@dataclass(frozen=True)
class ComponentTransport:
    """Per-component constants the correlations need."""

    mw: float  # g/mol
    sigma_lj: float  # Angstrom
    eps_k: float  # K
    v_nbp_cm3: float  # molar volume at the normal boiling point, cm3/mol
    phi: float  # Wilke-Chang association factor (as a solvent)


@lru_cache(maxsize=512)
def component_transport(cid: str) -> ComponentTransport:
    """Lennard-Jones parameters, NBP molar volume and association factor of one component.

    Lennard-Jones sigma and eps/k from ``chemicals.lennard_jones`` (``molecular_diameter``,
    ``Stockmayer``) by CAS; for a component without tabulated values, the same library
    functions' critical-property estimates. NBP volume: ``Yamada_Gunn(Tb, Tc, Pc, omega)``.
    """
    rec = component_record(cid)
    cas = str(rec.get("cas") or "")
    tc, pc, omega, tb = (rec.get(k) for k in ("Tc", "Pc", "omega", "Tb"))
    sigma = molecular_diameter(cas) if cas else None
    eps = Stockmayer(cas) if cas else None
    if sigma is None and tc is not None and pc is not None and omega is not None:
        sigma = molecular_diameter(Tc=float(tc), Pc=float(pc), omega=float(omega))
    if eps is None and tc is not None and omega is not None:
        eps = Stockmayer(Tc=float(tc), omega=float(omega))
    if sigma is None or eps is None or tb is None or tc is None or pc is None or omega is None:
        raise RateBasedPropertyError(
            f"rate-based column: component {cid!r} lacks the constants for its diffusivities "
            "(Lennard-Jones sigma/eps, Tb, Tc, Pc, omega)"
        )
    v_nbp = Yamada_Gunn(float(tb), float(tc), float(pc), float(omega)) * 1e6
    return ComponentTransport(
        mw=float(rec["mw"]),
        sigma_lj=float(sigma),
        eps_k=float(eps),
        v_nbp_cm3=float(v_nbp),
        phi=_PHI_WATER if cas == _WATER_CAS else 1.0,
    )


def chapman_enskog(T: float, P: float, a: ComponentTransport, b: ComponentTransport) -> float:
    """Binary gas diffusivity, m2/s (Bird-Stewart-Lightfoot eq. 17.3-12, see module doc)."""
    sigma_ab = 0.5 * (a.sigma_lj + b.sigma_lj)
    eps_ab = math.sqrt(a.eps_k * b.eps_k)
    omega_d = collision_integral_Neufeld_Janzen_Aziz(T / eps_ab, 1, 1)
    d_cm2 = _CE_CONSTANT * math.sqrt(T**3 * (1.0 / a.mw + 1.0 / b.mw)) / ((P / _ATM_PA) * sigma_ab**2 * omega_d)
    return d_cm2 * 1e-4


def vapour_effective_diffusivities(
    y: list[float], T: float, P: float, comps: list[ComponentTransport]
) -> list[float]:
    """Wilke (1950) mixture diffusivities ``D_im = (1 - y_i)/sum_{k!=i} y_k/D_ik``, m2/s.

    At ``y_i -> 1`` the limit is the mean of the binary pairs (the dilute-others limit
    of the same formula with equal weights).
    """
    n = len(comps)
    out: list[float] = []
    for i in range(n):
        d_pairs = [chapman_enskog(T, P, comps[i], comps[k]) for k in range(n) if k != i]
        w = [y[k] for k in range(n) if k != i]
        s = sum(w)
        if s <= 1e-12:
            out.append(sum(d_pairs) / len(d_pairs))
            continue
        out.append(s / sum(wk / dk for wk, dk in zip(w, d_pairs, strict=True)))
    return out


def liquid_effective_diffusivities(
    x: list[float], T: float, mu_l: float, comps: list[ComponentTransport]
) -> list[float]:
    """Wilke-Chang (1955) diffusivity of each component in the pseudo-solvent of the
    others, m2/s (see module doc for the mixed-solvent application choice)."""
    n = len(comps)
    eta_cp = mu_l * 1e3
    out: list[float] = []
    for i in range(n):
        w = [x[k] for k in range(n) if k != i]
        s = sum(w)
        others = [comps[k] for k in range(n) if k != i]
        if s <= 1e-12:
            phi_m = sum(c.phi * c.mw for c in others) / len(others)
        else:
            phi_m = sum(wk * c.phi * c.mw for wk, c in zip(w, others, strict=True)) / s
        d_cm2 = _WILKE_CHANG * math.sqrt(phi_m) * T / (eta_cp * comps[i].v_nbp_cm3**0.6)
        out.append(d_cm2 * 1e-4)
    return out


@dataclass(frozen=True)
class PackingGeometry:
    """Random-packing segment geometry (Onda 1968 inputs)."""

    diameter_m: float
    segment_height_m: float
    nominal_size_m: float
    specific_area_m2_m3: float
    critical_surface_tension_N_m: float

    @property
    def cross_section_m2(self) -> float:
        return math.pi * self.diameter_m**2 / 4.0


@dataclass(frozen=True)
class OndaResult:
    """Onda (1968) outputs for one packed segment."""

    a_w: float  # wetted (= interfacial) area per packed volume, m2/m3
    k_gas: list[float]  # concentration-based gas film coefficients k_G R T, m/s
    k_liq: list[float]  # liquid film coefficients, m/s
    re_l: float  # L/(a_w mu_L)
    re_g: float  # G/(a_t mu_G)


def onda_1968(
    geom: PackingGeometry,
    gas_mass_flux: float,
    liq_mass_flux: float,
    rho_g: float,
    mu_g: float,
    rho_l: float,
    mu_l: float,
    sigma_l: float,
    d_gas: list[float],
    d_liq: list[float],
) -> OndaResult:
    """Wetted area and film coefficients, Onda, Takeuchi & Okumoto (1968) eqs. (1)-(3).

    ``gas_mass_flux``/``liq_mass_flux`` are superficial mass velocities G, L (kg/m2 s).
    """
    if gas_mass_flux <= 0.0 or liq_mass_flux <= 0.0:
        raise RateBasedPropertyError(
            f"Onda correlation needs positive gas and liquid mass fluxes, got G={gas_mass_flux}, "
            f"L={liq_mass_flux} kg/m2 s"
        )
    a_t = geom.specific_area_m2_m3
    d_p = geom.nominal_size_m
    g = STANDARD_GRAVITY
    big_l, big_g = liq_mass_flux, gas_mass_flux
    # eq. (1)
    expo = (
        1.45
        * (geom.critical_surface_tension_N_m / sigma_l) ** 0.75
        * (big_l / (a_t * mu_l)) ** 0.1
        * (big_l**2 * a_t / (rho_l**2 * g)) ** -0.05
        * (big_l**2 / (rho_l * sigma_l * a_t)) ** 0.2
    )
    a_w = a_t * (1.0 - math.exp(-expo))
    re_l = big_l / (a_w * mu_l)
    re_g = big_g / (a_t * mu_g)
    # eq. (2): k_L = 0.0051 Re_L^(2/3) Sc_L^(-1/2) (a_t D_p)^0.4 (mu_L g/rho_L)^(1/3)
    pre_l = 0.0051 * re_l ** (2.0 / 3.0) * (a_t * d_p) ** 0.4 * (mu_l * g / rho_l) ** (1.0 / 3.0)
    k_liq = [pre_l * (mu_l / (rho_l * d)) ** -0.5 for d in d_liq]
    # eq. (3): k_G R T = C a_t D_G Re_G^0.7 Sc_G^(1/3) (a_t D_p)^-2
    c = _ONDA_KG_LARGE if d_p >= _ONDA_SMALL_PACKING_M else _ONDA_KG_SMALL
    k_gas = [c * a_t * d * re_g**0.7 * (mu_g / (rho_g * d)) ** (1.0 / 3.0) * (a_t * d_p) ** -2.0 for d in d_gas]
    return OndaResult(a_w=a_w, k_gas=k_gas, k_liq=k_liq, re_l=re_l, re_g=re_g)


def chilton_colburn_h(k_mean: float, c_molar: float, cp_molar: float, lam: float, rho: float,
                      cp_mass: float, d_mean: float) -> float:
    """Vapour film heat-transfer coefficient, W/m2 K: ``h = k c_t c_p Le^(2/3)``."""
    le = lam / (rho * cp_mass * d_mean)
    return k_mean * c_molar * cp_molar * le ** (2.0 / 3.0)


def penetration_h(k_mean: float, c_molar: float, cp_molar: float, lam: float, rho: float,
                  cp_mass: float, d_mean: float) -> float:
    """Liquid film heat-transfer coefficient (penetration model), W/m2 K:
    ``h = k c_t c_p Le^(1/2)``."""
    le = lam / (rho * cp_mass * d_mean)
    return k_mean * c_molar * cp_molar * math.sqrt(le)
