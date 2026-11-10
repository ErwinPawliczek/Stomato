"""VTBMSR-III equation of state (Mangold et al. 2019), density-only adapter.

Catalogue row ``vtbmsr3``. Model: Mangold, F.; Pilz, St.; Bjelic, S.; Vogel, F.,
"Equation of state and thermodynamic properties for mixtures of H2O, O2, N2, and CO2
from ambient up to 1000 K and 280 MPa", J. Supercrit. Fluids 153 (2019) 104476,
doi:10.1016/j.supflu.2019.02.016 (CC BY 4.0). A Redlich-Kwong-Soave cubic with

- the Schwartzentruber-Renon(-Watanasiri) polar alpha with the ``(1 - Tr)`` polar
  term (eq. 22a) and the Boston-Mathias-type exponential above Tc with the exponent
  ``d`` (eqs. 22b-22e);
- a temperature-dependent volume translation ``c(T)`` (eqs. 17-21) mixed linearly
  (eq. 28);
- the Schwartzentruber-Renon mixing rules (eqs. 23-24) with temperature-dependent
  ``k_b,ij`` (eq. 26); the paper does not use ``k_a,ij`` or ``l_ij`` (Table 7 note).

This is NOT the Aspen SR-POLAR (RKUPP) alpha, which carries ``(1 - Tr^0.5)`` in the
polar term; docs/thermo-catalogue-plan.md row 14 keeps that distinction.

Scope (density only, single-phase supercritical fluid): the paper validates molar
volume, enthalpy and heat capacity but prints no vapour-pressure or phase-equilibrium
check, and its water parameters come in a liquid set and a vapour/supercritical set
selected by the phase of water. This adapter therefore answers only states where the
phase is unambiguous without a VLE model: temperature above the mixture's Kay
pseudo-critical temperature and a single real root of the cubic. It uses the
H2O(v/sc) parameter set (see data/thermo_params/vtbmsr/mangold2019.yaml). Every
other surface refuses with :class:`VtbmsrError`, and the caloric fields of the phase
it returns are NaN (not computed) so no energy balance can consume them silently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache
from typing import Any

import yaml
from fluids.numerics import roots_cubic

from ngdesign.contracts.stream import Phase, PhaseKind, StreamState
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.data import component_record
from ngdesign.provenance.thermo_hook import TracedThermo
from ngdesign.thermo._state import R_IDEAL

#: Caloric fields the density-only adapter does not compute. One shared object, so two
#: identical flashes dump identical (``is``-equal) values for the L0 determinism check.
NOT_COMPUTED = math.nan

_CBRT2_M1 = 2.0 ** (1.0 / 3.0) - 1.0


class VtbmsrError(ValueError):
    """A VTBMSR-III call outside the density-only, single-phase supercritical scope."""


@dataclass(frozen=True)
class VtbmsrComponent:
    """Pure-component inputs (Mangold 2019 Table 2 and Table 5); SI units."""

    Tc: float  # K
    Pc: float  # Pa
    omega: float  # -
    c0: float  # m3/mol
    c1: float  # m3/mol
    c2: float  # -
    p0: float  # -
    p1: float  # -
    p2: float  # -


@dataclass(frozen=True)
class VtbmsrParameters:
    """The cited parameter table: pure components and symmetric k_b,ij(T) triples."""

    components: dict[str, VtbmsrComponent]
    kb: dict[frozenset[str], tuple[float, float, float]]


@cache
def load_parameters() -> VtbmsrParameters:
    """Read data/thermo_params/vtbmsr/mangold2019.yaml (cached)."""
    from ngdesign.thermo.gamma_phi import PARAMS_DIR

    raw: dict[str, Any] = yaml.safe_load((PARAMS_DIR / "vtbmsr" / "mangold2019.yaml").read_text())
    comps = {
        cid: VtbmsrComponent(**{k: float(v) for k, v in entry.items() if k != "source"})
        for cid, entry in raw["components"].items()
    }
    kb = {
        frozenset(entry["pair"]): (float(entry["kb0"]), float(entry["kb1"]), float(entry["kb2"]))
        for entry in raw["binaries"]
    }
    return VtbmsrParameters(comps, kb)


def rks_constants(Tc: float, Pc: float) -> tuple[float, float]:
    """RKS ``a_c`` [Pa m6/mol2] and ``b`` [m3/mol], Mangold 2019 eqs. 15-16.

    a_c = R^2 Tc^2 / (9 (2^(1/3) - 1) pc),  b = (2^(1/3) - 1)/3 * R Tc / pc
    (Omega_a = 0.42748, Omega_b = 0.08664, Table 1).
    """
    a_c = R_IDEAL**2 * Tc**2 / (9.0 * _CBRT2_M1 * Pc)
    b = _CBRT2_M1 / 3.0 * R_IDEAL * Tc / Pc
    return a_c, b


def sqrt_alpha(omega: float, p0: float, p1: float, p2: float, Tr: float) -> float:
    """Square root of the polar alpha function, Mangold 2019 eqs. 22a-22e.

    Tr <= 1:  sqrt(alpha) = 1 + m (1 - Tr^0.5) - p0 (1 - Tr)(1 + p1 Tr + p2 Tr^2)   (22a)
    Tr > 1:   sqrt(alpha) = exp(cd (1 - Tr^d))                                      (22b)
    cd = 1 - 1/d (22c),  d = 1 + 0.5 m - p0 (1 + p1 + p2) (22d),
    m = 0.48508 + 1.55191 omega - 0.15613 omega^2 (22e).
    """
    m = 0.48508 + 1.55191 * omega - 0.15613 * omega * omega
    if Tr <= 1.0:
        return 1.0 + m * (1.0 - math.sqrt(Tr)) - p0 * (1.0 - Tr) * (1.0 + p1 * Tr + p2 * Tr * Tr)
    d = 1.0 + 0.5 * m - p0 * (1.0 + p1 + p2)
    cd = 1.0 - 1.0 / d
    return math.exp(cd * (1.0 - Tr**d))


def volume_translation(c0: float, c1: float, c2: float, b: float, Tr: float) -> float:
    """Pure-component volume translation c(T) [m3/mol], Mangold 2019 eqs. 17-21.

    Tr <= 1:            c = c0 + c1 / (1 + c2 - Tr)                     (17)
    Tr <= 1, c2 = Tr-1: c = c0                                          (18)
    Tr > 1, c1 = 0:     c = c0                                          (19)
    Tr > 1, c1 != 0:    c = b + K^2 c1 / (1 + c2 K - Tr),
                        K = (c0 - b) c2 / c1 + 1                        (20)
    Tr > 1, c1 != 0, c2 K = Tr - 1:  c = c0                             (21)
    Eq. 20 is continuous with eq. 17 at Tr = 1.
    """
    if Tr <= 1.0:
        if c2 == Tr - 1.0:
            return c0
        return c0 + c1 / (1.0 + c2 - Tr)
    if c1 == 0.0:
        return c0
    K = (c0 - b) * c2 / c1 + 1.0
    if c2 * K == Tr - 1.0:
        return c0
    return b + K * K * c1 / (1.0 + c2 * K - Tr)


def kay_pseudocritical_T(z: dict[str, float], Tc: dict[str, float]) -> float:
    """Kay's-rule pseudo-critical temperature T_pc = sum_i z_i Tc_i [K].

    Kay, W. B., "Density of hydrocarbon gases and vapors at high temperature and
    pressure", Ind. Eng. Chem. 28 (1936) 1014.
    """
    return sum(x * Tc[cid] for cid, x in z.items())


@dataclass(frozen=True)
class FluidState:
    """The single-phase result of one (z, T, P) evaluation."""

    molar_volume: float  # m3/mol (translated)
    molecular_weight: float  # g/mol

    @property
    def density(self) -> float:
        """Mass density [kg/m3]."""
        return self.molecular_weight / 1000.0 / self.molar_volume


def mixture_volume(params: VtbmsrParameters, z: dict[str, float], T: float, P: float) -> float:
    """Translated molar volume v [m3/mol] of a single-phase supercritical fluid.

    Mixture (Mangold 2019): a_mix = sum_ij x_i x_j sqrt(a_i a_j) (eq. 23, k_a = l = 0),
    b_mix = sum_ij x_i x_j (b_i + b_j)/2 (1 - k_b,ij) (eq. 24) with
    k_b,ij = kb0 + kb1 T + kb2 / T (eq. 26), c_mix = sum_i x_i c_i (eq. 28).
    EOS (eq. 14): p = RT/(v + c - b) - a/((v + c)(v + c + b)); with u = v + c,
    p u^3 - RT u^2 + (a - p b^2 - RT b) u - a b = 0. Refuses unless T exceeds the
    Kay pseudo-critical temperature and the cubic has exactly one real root u > b.
    """
    unknown = sorted(set(z) - set(params.components))
    if unknown:
        raise VtbmsrError(
            f"VTBMSR-III (Mangold 2019) has parameters for {sorted(params.components)} only; got {unknown}"
        )
    comps = {cid: params.components[cid] for cid in z}
    t_pc = kay_pseudocritical_T(z, {cid: c.Tc for cid, c in comps.items()})
    if T <= t_pc:
        raise VtbmsrError(
            f"T={T:g} K is not above the Kay pseudo-critical temperature {t_pc:.6g} K: the "
            "density-only adapter answers single-phase supercritical states only (the phase "
            "selects the water parameter set and no VLE model is validated)"
        )
    a_i: dict[str, float] = {}
    b_i: dict[str, float] = {}
    c_mix = 0.0
    for cid, comp in comps.items():
        a_c, b = rks_constants(comp.Tc, comp.Pc)
        Tr = T / comp.Tc
        a_i[cid] = a_c * sqrt_alpha(comp.omega, comp.p0, comp.p1, comp.p2, Tr) ** 2
        b_i[cid] = b
        c_mix += z[cid] * volume_translation(comp.c0, comp.c1, comp.c2, b, Tr)
    a_mix = 0.0
    b_mix = 0.0
    for i, xi in z.items():
        for j, xj in z.items():
            a_mix += xi * xj * math.sqrt(a_i[i] * a_i[j])
            if i == j:
                kb = 0.0
            else:
                kb0, kb1, kb2 = params.kb.get(frozenset((i, j)), (0.0, 0.0, 0.0))
                kb = kb0 + kb1 * T + kb2 / T
            b_mix += xi * xj * 0.5 * (b_i[i] + b_i[j]) * (1.0 - kb)
    RT = R_IDEAL * T
    roots = roots_cubic(P, -RT, a_mix - P * b_mix * b_mix - RT * b_mix, -a_mix * b_mix)
    real = [r.real if isinstance(r, complex) else float(r) for r in roots if _is_real(r)]
    physical = sorted({u for u in real if u > b_mix})
    if len(physical) != 1:
        raise VtbmsrError(
            f"VTBMSR-III cubic has {len(physical)} physical volume roots at T={T:g} K, "
            f"P={P:g} Pa: not a single-phase supercritical state (phase selection needs a "
            "VLE assessment this density-only adapter does not have)"
        )
    return physical[0] - c_mix


def _is_real(r: complex | float) -> bool:
    return not isinstance(r, complex) or abs(r.imag) <= 1e-12 * max(abs(r.real), 1.0)


class VtbmsrPackage(TracedThermo):
    """VTBMSR-III density-only property package (kind ``thermo``, row ``vtbmsr3``).

    ``flash_pt`` returns one supercritical fluid phase (labelled VAPOR, the protocol's
    single-fluid label) with density and Z; enthalpy, entropy, cp and gibbs are NaN.
    ``phase_props`` answers VAPOR only, from the same evaluation. Saturation, VF/H/S
    flashes and fugacity derivatives refuse; ``pure_psat`` and ``k_values`` are None.
    """

    def trace_model(self) -> str | None:
        return "vtbmsr3"

    def _fluid(self, z: dict[str, float], T: float, P: float) -> FluidState:
        zp = {cid: x for cid, x in z.items() if x > 0.0}
        v = mixture_volume(load_parameters(), zp, T, P)
        mw = sum(x * float(component_record(cid)["mw"]) for cid, x in zp.items())
        return FluidState(v, mw)

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        st = self._fluid(z, T, P)
        phase = Phase(
            kind=PhaseKind.VAPOR,
            mole_fraction=1.0,
            composition=dict(z),
            density=st.density,
            molecular_weight=st.molecular_weight,
            z_factor=P * st.molar_volume / (R_IDEAL * T),
            enthalpy=NOT_COMPUTED,
            entropy=NOT_COMPUTED,
            cp=NOT_COMPUTED,
        )
        return StreamState(
            T=T,
            P=P,
            molar_flow=molar_flow,
            composition=dict(z),
            vapor_fraction=1.0,
            enthalpy=NOT_COMPUTED,
            entropy=NOT_COMPUTED,
            phases=[phase],
        )

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: PhaseKind) -> PhaseProps:
        if kind is not PhaseKind.VAPOR:
            raise VtbmsrError(
                f"VTBMSR-III density-only adapter answers the supercritical fluid (VAPOR) only, got {kind}"
            )
        st = self._fluid(composition, T, P)
        return PhaseProps(
            kind=PhaseKind.VAPOR,
            mole_fraction=1.0,
            composition=dict(composition),
            molecular_weight=st.molecular_weight,
            density=st.density,
            enthalpy=NOT_COMPUTED,
            entropy=NOT_COMPUTED,
            cp=NOT_COMPUTED,
            gibbs=NOT_COMPUTED,
            z_factor=P * st.molar_volume / (R_IDEAL * T),
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        raise VtbmsrError("VTBMSR-III adapter is density-only: no enthalpy, so no PH flash")

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        raise VtbmsrError("VTBMSR-III adapter is density-only: no entropy, so no PS flash")

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        raise VtbmsrError("VTBMSR-III adapter has no validated phase equilibrium: no vapour-fraction flash")

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        raise VtbmsrError("VTBMSR-III adapter has no validated phase equilibrium: no vapour-fraction flash")

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise VtbmsrError("VTBMSR-III adapter has no validated phase equilibrium: no bubble point")

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        raise VtbmsrError("VTBMSR-III adapter has no validated phase equilibrium: no dew point")

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        return None

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: PhaseKind
    ) -> PropertyDerivatives:
        raise VtbmsrError("VTBMSR-III adapter is density-only: no fugacity model is exposed")

    def pure_psat(self, cid: str, T: float) -> float | None:
        return None
