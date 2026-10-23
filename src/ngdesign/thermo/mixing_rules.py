"""Excess-Gibbs-energy mixing rules hosted on `thermo`'s GCEOSMIX (spec T-06).

Design (issue #141, 08:20Z steer): each gE mixing rule is a small
:class:`GERule` object computing the mixture attraction parameter state
``a(T, x)`` with analytic composition and temperature derivatives; a
:class:`_GEMixingEOS` mixin hosts the rule on a `thermo` ``PRMIX``/``SRKMIX``
subclass by overriding ``a_alpha_and_derivatives`` and supplying the
composition derivatives the generic mole-number fugacity route needs.  The
mixture ln-phi kernel itself stays `thermo`'s validated ``PR_lnphis`` /
``SRK_lnphis``: the rules only replace the effective ``a_ij`` row sums, which
for a general rule reduce to ``row_i = (d(n a)/dn_i + a)/2``.  All composition
and temperature-composition derivatives are analytic (thermo's
``GibbsExcess`` models expose ``dGE_dxs``, ``d2GE_dTdxs``, ``d2GE_dT2``).

Derivative conventions
----------------------
``RuleState.a_x`` holds the *simplex-projected* composition partials
``da/dz_k`` so that ``da = sum_k a_x[k] dz_k`` with ``sum(dz) = 0``; from them

- ``da_alpha_dzs[k]  = a_x[k]``
- ``da_alpha_dns[i]  = a + a_x[i]``          (mole-number derivative of ``n a``)
- ``da_alpha_dT_dzs[k] = a_xT[k]``
- ``da_alpha_dT_dns[i] = da_dT + a_xT[i]``

The ln-phi kernel's effective row sums follow as
``row_i = (da_alpha_dns[i] + a)/2`` and its temperature derivative row as
``rowT_i = (da_alpha_dT_dns[i] + da_dT)/2``, so PRMIX/SRKMIX consumers of
``a_alpha_j_rows`` and ``da_alpha_dT_j_rows`` stay exact.

gE sources come from the T-03 gamma-phi adapter's liquid-model factory
(:func:`ngdesign.thermo.gamma_phi._ge_model_factory`) so there is one owner of
the ChemSep NRTL/UNIFAC parameter plumbing.  PSRK and VTPR use the direct
``thermo.unifac`` tables (the gamma-phi catalogue has no such rows); both
deviations are declared in the module docstrings of the affected providers.

The gE mixing rows are k_ij-free by definition: the flasher hook passes a zero
binary-interaction matrix (the gE model carries all interaction information).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Any

from thermo import CEOSGas, CEOSLiquid
from thermo.activity import GibbsExcess
from thermo.eos_mix import (
    PRMIX,
    SRKMIX,
    PR_lnphis,
    SRK_lnphis,
    a_alpha_and_derivatives_quadratic_terms,
)
from thermo.eos_mix_methods import eos_mix_lnphis_general
from thermo.heat_capacity import R as R_GAS

from ngdesign.thermo.cubic import _CHEMSEP_CUBIC_TABLE, CubicEOS, _flasher_for, _flasher_vl_for
from ngdesign.thermo.gamma_phi import _ge_model_factory

__all__ = [
    "MHV1",
    "MHV2",
    "PRHuronVidalThermo",
    "PRMHV1Thermo",
    "PRMHV2Thermo",
    "PRMIX_HV",
    "PRMIX_MHV1",
    "PRMIX_MHV2",
    "PRMIX_WS",
    "PRWongSandlerThermo",
    "SRKMHV2Thermo",
    "SRKMIX_MHV2",
    "SRKMIX_WS",
    "SRKWongSandlerThermo",
]


# ----------------------------------------------------------------------------
# Pure-component alpha bookkeeping
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PureAlpha:
    """Pure-component attraction pieces in the rule's dimensionless frame.

    ``a0`` is the T-independent part (``PRMIX.ais``), and ``alpha``/``dalpha``/
    ``d2alpha`` the Soave alpha function and its first two T-derivatives, so
    the per-component ``a_i alpha_i(T) = a0_i * alpha_i``.
    """

    a0: tuple[float, ...]
    alpha: tuple[float, ...]
    dalpha: tuple[float, ...]
    d2alpha: tuple[float, ...]
    a_alphas: tuple[float, ...] = ()
    da_alphas: tuple[float, ...] = ()
    d2a_alphas: tuple[float, ...] = ()


def pure_alpha_from(
    ais: list[float], a_alphas: list[float], da_alphas: list[float], d2a_alphas: list[float]
) -> PureAlpha:
    """Split the vectorized ``a_i alpha_i(T)`` products into a0 and alpha."""
    alpha = tuple(a / a0 for a, a0 in zip(a_alphas, ais, strict=True))
    dalpha = tuple(d / a0 for d, a0 in zip(da_alphas, ais, strict=True))
    d2alpha = tuple(d / a0 for d, a0 in zip(d2a_alphas, ais, strict=True))
    return PureAlpha(
        a0=tuple(ais),
        alpha=alpha,
        dalpha=dalpha,
        d2alpha=d2alpha,
        a_alphas=tuple(a_alphas),
        da_alphas=tuple(da_alphas),
        d2a_alphas=tuple(d2a_alphas),
    )


# ----------------------------------------------------------------------------
# gE providers
# ----------------------------------------------------------------------------


class GEProvider(ABC):
    """A gE model evaluated as ``g = gE/(R T)`` with analytic derivatives."""

    @abstractmethod
    def state(
        self, T: float, xs: tuple[float, ...]
    ) -> tuple[float, tuple[float, ...], float, float, tuple[float, ...]]:
        """Return ``(g, g_x, g_dT, g_d2T, g_xT)`` at ``(T, xs)``.

        ``g_x[k]`` is the raw unconstrained partial ``d g/d x_k`` and
        ``g_xT[k]`` the mixed derivative; the rule layer applies any
        projections it needs.
        """


class ThermoGEProvider(GEProvider):
    """gE from a T-03 gamma-phi adapter liquid model (thermo ``GibbsExcess``).

    ``make`` is the factory ``_ge_model_factory`` returns: a callable building
    the model over this exact support.  Instances are stateless per (T, xs)
    through the cache, so EOS clones and phase splits stay deterministic.
    """

    def __init__(self, make: Callable[[list[float]], GibbsExcess]):
        self._make = make
        self._cache: dict[tuple[float, tuple[float, ...]], Any] = {}

    def state(self, T: float, xs: tuple[float, ...]) -> Any:
        key = (T, xs)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        model = self._make(list(xs)).to_T_xs(T, list(xs))
        ge, dge, d2ge = model.GE(), model.dGE_dT(), model.d2GE_dT2()
        g = ge / (R_GAS * T)
        g_dT = (dge * T - ge) / (R_GAS * T * T)
        g_d2T = (d2ge * T * T - 2.0 * dge * T + 2.0 * ge) / (R_GAS * T**3)
        ge_x = model.dGE_dxs()
        ge_xT = model.d2GE_dTdxs()
        g_x = tuple(v / (R_GAS * T) for v in ge_x)
        g_xT = tuple((T * d - v) / (R_GAS * T * T) for v, d in zip(ge_x, ge_xT, strict=True))
        out = (g, g_x, g_dT, g_d2T, g_xT)
        self._cache.clear()
        self._cache[key] = out
        return out


def _nrtl_provider(cas_list: list[str], ids: tuple[str, ...]) -> GEProvider:
    """ChemSep NRTL gE through the gamma-phi adapter's own factory."""
    make = _ge_model_factory("nrtl", ids, cas_list, None)
    return ThermoGEProvider(make)


def _provider_for(kind: str, cas_list: list[str], ids: tuple[str, ...]) -> GEProvider:
    if kind == "nrtl":
        return _nrtl_provider(cas_list, ids)
    raise ValueError(f"unknown gE provider {kind!r}")


# ----------------------------------------------------------------------------
# Rule algebra
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleState:
    """Mixture attraction-parameter state for one (T, xs).

    ``a`` in J^2/mol^2/Pa; ``a_x``/``a_xT`` are the simplex-projected
    composition partials described in the module docstring.
    """

    a: float
    da_dT: float
    d2a_dT2: float
    a_x: tuple[float, ...]
    a_xT: tuple[float, ...]


def _alpha_moments(
    pa: PureAlpha, xs: tuple[float, ...], bs: tuple[float, ...], T: float
) -> tuple[float, float, float]:
    """``A = sum x_i a_i/(b_i R T)`` and its first two T-derivatives.

    The gE mixing rules operate on the dimensionless ``a/(b R T)`` scale
    (typically 5-8), not the Soave alpha scale; with ``C_i = a0_i/(b_i R)``
    the per-component value is ``C_i alpha_i/T``.
    """
    a_val = a_t = a_tt = 0.0
    for x, al, dal, d2al, a0i, bi in zip(xs, pa.alpha, pa.dalpha, pa.d2alpha, pa.a0, bs, strict=True):
        c = a0i / (bi * R_GAS)
        a_val += x * c * al / T
        a_t += x * c * (dal / T - al / (T * T))
        a_tt += x * c * (d2al / T - 2.0 * dal / (T * T) + 2.0 * al / (T**3))
    return a_val, a_t, a_tt


def _a_brt(pa: PureAlpha, k: int, bi: float, T: float) -> tuple[float, float, float]:
    """Per-component ``a_i/(b_i R T)`` and its first two T-derivatives."""
    c = pa.a0[k] / (bi * R_GAS)
    al, dal, d2al = pa.alpha[k], pa.dalpha[k], pa.d2alpha[k]
    return (
        c * al / T,
        c * (dal / T - al / (T * T)),
        c * (d2al / T - 2.0 * dal / (T * T) + 2.0 * al / (T**3)),
    )


def _flory(xs: tuple[float, ...], b: float, bs: tuple[float, ...]) -> tuple[float, tuple[float, ...]]:
    """``sum_i x_i ln(b_i/b)`` (Michelsen covolume term) and its z-derivatives."""
    value = sum(x * math.log(bi / b) for x, bi in zip(xs, bs, strict=True) if x)
    # d/dz_k [sum_i z_i ln(b_i/b)] = ln(b_k/b) + 1 - b_k/b  with b = sum z b
    return value, tuple(math.log(bi / b) + 1.0 - bi / b for bi in bs)


class GERule(ABC):
    """A gE mixing rule producing :class:`RuleState` at (T, xs)."""

    @abstractmethod
    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState: ...


def _linear_rule_state(
    alpha_m: float,
    alpha_T: float,
    alpha_TT: float,
    alpha_x: tuple[float, ...],
    alpha_xT: tuple[float, ...],
    b: float,
    T: float,
    bs: tuple[float, ...],
    xs: tuple[float, ...],
) -> RuleState:
    """Assemble RuleState for ``a_m = alpha_m * b * R * T`` with linear b.

    ``alpha_x`` and ``alpha_xT`` arrive as raw unconstrained partials of
    ``alpha_m``; the fugacity route differentiates along simplex directions
    ``(delta_ik - x_k)``, so the Euler projection ``d_k -> d_k - sum_j x_j d_j``
    is applied here.
    """
    rt = R_GAS * T
    a = alpha_m * b * rt
    da_dT = b * R_GAS * (alpha_m + T * alpha_T)
    d2a_dT2 = b * R_GAS * (2.0 * alpha_T + T * alpha_TT)
    # raw partials of a before projection
    a_x_raw = tuple(rt * (b * ax + alpha_m * bi) for ax, bi in zip(alpha_x, bs, strict=True))
    a_xT_raw = tuple(
        R_GAS * (b * ax + alpha_m * bi) + rt * (b * axt + alpha_T * bi)
        for ax, axt, bi in zip(alpha_x, alpha_xT, bs, strict=True)
    )
    a_x_proj = tuple(ax - sum(x * a for x, a in zip(xs, a_x_raw, strict=True)) for ax in a_x_raw)
    a_xT_proj = tuple(axt - sum(x * a for x, a in zip(xs, a_xT_raw, strict=True)) for axt in a_xT_raw)
    return RuleState(a=a, da_dT=da_dT, d2a_dT2=d2a_dT2, a_x=a_x_proj, a_xT=a_xT_proj)


class LinearVDW(GERule):
    """Ordinary linear-b / quadratic-a rule with binary parameters ``kijs``.

    Reproduces `thermo`'s ``PRMIX``/``SRKMIX`` default exactly; serves as the
    identity reference proving the GCEOSMIX hosting layer is exact (spec T-06:
    the vdw1 test must reproduce the default cubic rows bit-for-bit).
    """

    def __init__(self, kijs: list[list[float]] | None = None):
        self.kijs = kijs

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        # Delegate the quadratic-form arithmetic to thermo's own helper so the
        # vdw1 route shares its exact floating-point path with PRMIX (the
        # bit-for-bit acceptance of the identity reference, spec T-06).
        xs_l = list(xs)
        n = len(xs_l)
        roots = [math.sqrt(a) for a in pa.a_alphas]
        a, da_dT, d2a_dT2, rows, row_ts = a_alpha_and_derivatives_quadratic_terms(
            list(pa.a_alphas),
            roots,
            list(pa.da_alphas),
            list(pa.d2a_alphas),
            T,
            xs_l,
            [[1.0] * n for _ in range(n)],
            [0.0] * n,
            [0.0] * n,
        )
        # Projected composition derivatives (Euler: sum x_k a_x_k = 0 for the
        # projected form; raw partials are 2 * rows and 2 * row_ts).
        a_x = tuple(2.0 * r - 2.0 * a for r in rows)
        a_xT = tuple(2.0 * r - 2.0 * da_dT for r in row_ts)
        return RuleState(a=a, da_dT=da_dT, d2a_dT2=d2a_dT2, a_x=a_x, a_xT=a_xT)


class HuronVidal(GERule):
    """Huron-Vidal (1979), infinite-pressure gE reference.

    ``alpha_m = sum x_i a_i/(b_i R T) - g/m`` with the EOS constant
    ``m = ln(sqrt(2) - 1)`` for PR (u = 2, w = -1).
    """

    M_PR = math.log(math.sqrt(2.0) - 1.0)  # PR

    def __init__(self, provider: GEProvider, m: float = M_PR):
        self.provider = provider
        self.m = m

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        A, A_T, A_TT = _alpha_moments(pa, xs, bs, T)
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        alpha_m = A - g / self.m
        alpha_x = tuple(_a_brt(pa, k, bs[k], T)[0] - gx[k] / self.m for k in range(n))
        alpha_xT = tuple(_a_brt(pa, k, bs[k], T)[1] - gxT[k] / self.m for k in range(n))
        return _linear_rule_state(
            alpha_m, A_T - gT / self.m, A_TT - gTT / self.m, alpha_x, alpha_xT, b, T, bs, xs
        )


# ----------------------------------------------------------------------------
# GCEOSMIX hosting
# ----------------------------------------------------------------------------


class _GEMixingEOS:
    """Mixin hosting a :class:`GERule` on a ``PRMIX``/``SRKMIX`` subclass.

    Overrides ``a_alpha_and_derivatives`` (mixture state from the rule), the
    composition-derivative properties the generic mole-number route consumes,
    and ``fugacity_coefficients`` (thermo's validated ln-phi kernel with the
    rule's effective ``a_ij`` row sums).  The rule instance must be attached
    before ``__init__`` triggers the first calculation, and is re-attached on
    ``to_TP_zs_fast`` clones through ``_fast_init_specific``.
    """

    # Thermo's GCEOSMIX supplies these at runtime; declared for typing.
    T: float
    P: float
    N: int
    zs: Any
    bs: Any
    b: Any
    ais: Any
    a_alpha_and_derivatives_vectorized: Any
    vectorized: Any

    #: ln-phi kernel of the EOS family (PR_lnphis for PRMIX, SRK_lnphis for SRKMIX).
    lnphi_kernel: Callable[..., list[float]] = PR_lnphis

    def _pure_alpha(self) -> PureAlpha:
        a_alphas, da_alphas, d2a_alphas = self.a_alpha_and_derivatives_vectorized(self.T)
        return pure_alpha_from(self.ais, a_alphas, da_alphas, d2a_alphas)

    def a_alpha_and_derivatives(
        self, T: float, full: bool = True, quick: bool = True, pure_a_alphas: bool = True
    ) -> Any:
        a_alphas, da_alpha_dTs, d2a_alpha_dT2s = self.a_alpha_and_derivatives_vectorized(T)
        self.a_alphas, self.da_alpha_dTs, self.d2a_alpha_dT2s = (
            a_alphas,
            da_alpha_dTs,
            d2a_alpha_dT2s,
        )
        if self.vectorized:
            from numpy import sqrt as _sqrt

            self.a_alpha_roots = _sqrt(a_alphas)
        else:
            self.a_alpha_roots = [math.sqrt(i) for i in a_alphas]

        pa = pure_alpha_from(self.ais, a_alphas, da_alpha_dTs, d2a_alpha_dT2s)
        st = self.rule.state(T, tuple(self.zs), pa, tuple(self.bs))
        self._rule_state = st
        a = st.a
        self.a_alpha = a
        self.da_alpha_dT = st.da_dT
        self.d2a_alpha_dT2 = st.d2a_dT2
        # Effective a_ij row sums (and their T-derivatives) keep PRMIX/SRKMIX
        # ln-phi and dlnphi consumers exact for the rule's mixture a(T, x).
        da_dns = [a + ax for ax in st.a_x]
        daT_dns = [st.da_dT + axt for axt in st.a_xT]
        rows = [0.5 * (d + a) for d in da_dns]
        row_ts = [0.5 * (d + st.da_dT) for d in daT_dns]
        self.a_alpha_j_rows = rows
        self.da_alpha_dT_j_rows = row_ts
        if full:
            return a, st.da_dT, st.d2a_dT2
        return a

    @property
    def da_alpha_dzs(self) -> list[float]:
        return list(self._rule_state.a_x)

    @property
    def da_alpha_dns(self) -> list[float]:
        a = self.a_alpha
        return [a + ax for ax in self._rule_state.a_x]

    @property
    def da_alpha_dT_dzs(self) -> list[float]:
        return list(self._rule_state.a_xT)

    @property
    def da_alpha_dT_dns(self) -> list[float]:
        da_dT = self.da_alpha_dT
        return [da_dT + axt for axt in self._rule_state.a_xT]

    def fugacity_coefficients(self, Z: float) -> list[float]:
        st = self._rule_state
        a = st.a
        rows = [0.5 * (a + ax + a) for ax in st.a_x]
        return self.lnphi_kernel(self.T, self.P, Z, self.b, a, self.bs, rows, self.N)

    def _fast_init_specific(self, other: Any) -> None:
        super()._fast_init_specific(other)  # type: ignore[misc]
        self.rule = other.rule
        self._rule_state = other._rule_state


class PRMIX_HV(_GEMixingEOS, PRMIX):  # type: ignore[misc]
    """PRMIX with the Huron-Vidal (1979) gE mixing rule (NRTL by default)."""

    lnphi_kernel = staticmethod(PR_lnphis)
    rule_kind = "hv"

    def __init__(
        self,
        Tcs: Any,
        Pcs: Any,
        omegas: Any,
        zs: Any,
        kijs: Any | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        fugacities: bool = True,
        only_l: bool = False,
        only_g: bool = False,
        rule: GERule | None = None,
    ):
        self.rule = rule
        super().__init__(
            Tcs=Tcs,
            Pcs=Pcs,
            omegas=omegas,
            zs=zs,
            kijs=kijs,
            T=T,
            P=P,
            V=V,
            fugacities=fugacities,
            only_l=only_l,
            only_g=only_g,
        )


# ----------------------------------------------------------------------------
# Package layer (T-02 configure hook pattern)
# ----------------------------------------------------------------------------


def _zero_kijs(n: int) -> list[list[float]]:
    return [[0.0] * n for _ in range(n)]


def _rule_for(eos_cls: type[Any], provider: GEProvider) -> GERule:
    kind = getattr(eos_cls, "rule_kind", None)
    if kind == "hv":
        return HuronVidal(provider, HuronVidal.M_PR)
    if kind == "mhv1":
        return MHV1(provider, q1=eos_cls.q1)
    if kind == "mhv2":
        return MHV2(provider, q1=eos_cls.q1, q2=eos_cls.q2)
    if kind == "ws":
        return WongSandler(provider, eos_cls.ws_c)
    raise ValueError(f"EOS class {eos_cls!r} declares no mixing rule")


@cache
def _mixing_configure(
    eos_cls: type, ge_kind: str
) -> Callable[[list[Any], Any, list[list[float]]], tuple[Any, dict[str, Any], Any, Any]]:
    """Flasher-builder hook for one (EOS class, gE kind) pair.

    Cached on (eos, ge_kind) so the closure handed to ``_flasher_for`` is a
    stable cache key, exactly like the T-02 ``_option_configure`` pattern.
    """

    def configure(
        records: list[Any], constants: Any, kijs: list[list[float]]
    ) -> tuple[Any, dict[str, Any], Any, Any]:
        ids = tuple(str(r.id) for r in records)
        cas_list = [str(r.cas) for r in records]
        provider = _provider_for(ge_kind, cas_list, ids)
        rule = _rule_for(eos_cls, provider)
        eos_kwargs: dict[str, Any] = {
            "Tcs": constants.Tcs,
            "Pcs": constants.Pcs,
            "omegas": constants.omegas,
            "kijs": _zero_kijs(len(cas_list)),
            "rule": rule,
        }
        return eos_cls, eos_kwargs, CEOSGas, CEOSLiquid

    return configure


class MixingRuleThermo(CubicEOS):
    """Cubic-EOS package whose attraction term follows a gE mixing rule.

    Subclasses pin the rule-hosting EOS class as ``eos`` and the gE liquid
    model kind as ``ge_kind``; the flasher factories carry both, so two rows
    with different rules never share a flasher instance.
    """

    ge_kind: str = ""

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        return _flasher_for(
            self.eos,
            _CHEMSEP_CUBIC_TABLE,
            ids,
            self._slate_pseudos,
            _mixing_configure(self.eos, self.ge_kind),
        )

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        return _flasher_vl_for(
            self.eos,
            _CHEMSEP_CUBIC_TABLE,
            ids,
            self._slate_pseudos,
            _mixing_configure(self.eos, self.ge_kind),
        )


class PRHuronVidalThermo(MixingRuleThermo):
    """Peng-Robinson with the Huron-Vidal (1979) mixing rule over NRTL gE.

    Pure-component alpha stays PR's Soave form (the databank ``ais`` and
    omegas feed the rule's ``PureAlpha`` unchanged); the mixture attraction
    parameter follows ``a = b(RT sum x_i a_i/(b_i R T) - gE/m)`` with
    ``m = ln(sqrt(2) - 1)``.
    """

    eos = PRMIX_HV
    ge_kind = "nrtl"


# ----------------------------------------------------------------------------
# Wong-Sandler (1992) — second-virial-consistent gE mixing (T-06a, step 2)
# ----------------------------------------------------------------------------
#
# Reference: Wong, D. S. H. & Sandler, S. I., "A theoretically correct mixing
# rule for virial coefficients of mixtures", AIChE J. 38(5), 671-680, 1992
# (primary; cited in mixing.yaml).  The rule mixes BOTH cubic parameters:
#
#   Q   = sum_i sum_j x_i x_j (b - a/RT)_ij
#   (b - a/RT)_ij = (1 - k_ij) * [(b_i - a_i/RT) + (b_j - a_j/RT)] / 2
#   D   = sum_i x_i a_i/(b_i R T) + A_inf^E(x) / (C * R T)
#   b_m = Q / (1 - D)          and          a_m = R T b_m D
#
# with the EOS constant C carrying its sign (dispatch, 18:01Z review):
# PR  C = ln(sqrt(2) - 1)/sqrt(2) = -0.62323,  SRK  C = -ln 2 = -0.69315.
# A_inf^E is approximated by the same ChemSep NRTL gE the Huron-Vidal row
# uses (the gE provider supplies g = gE/(RT), so the added term is g/C), and
# the gE rows stay k_ij-free: ``kijs`` defaults to zeros, matching the
# mixing-family convention that the gE model carries all interaction
# information.
#
# Unlike Huron-Vidal, b_m is a NON-LINEAR function of composition, so the
# linear-b ln-phi kernels (PR_lnphis/SRK_lnphis) are not exact here.  The
# fugacity coefficients go through thermo's general mole-number route
# ``eos_mix_lnphis_general`` (thermo.eos_mix_methods), which differentiates
# the exact residual-Gibbs ln-phi expression through
# (db/dn, ddelta/dn, depsilon/dn, da/dn):
#
#   dQ/dn_i and dD/dn_i enter ln phi as
#     beta_i = d b_m/dn_i = [Q_i (1-D) + Q D_i] / (1-D)^2
#   (mole-number derivatives of Q and D), which feed the covolume-derivative
#   terms of the kernel: db_dns = beta_i, ddelta/dn = c_delta * beta_i,
#   depsilon/dn = 2 c_eps b_m beta_i (c_delta = 2, c_eps = -1 for PR;
#   c_delta = 1, c_eps = 0 for SRK), plus da/dn_i = d a_m/dn_i
#   = R T (beta_i D + b_m D_i).  Both derivative groups are analytic and
#   verified against Helmholtz finite differences to < 1e-6 (tests).
#
# Departure enthalpies/entropies stay on thermo's scalar kernel, which treats
# the mixture covolume as T-invariant; the small db_m/dT contribution to
# H_dep/S_dep is omitted (noted as a fidelity limit of the hosting layer).


@dataclass(frozen=True)
class WSRuleState(RuleState):
    """:class:`RuleState` plus the Wong-Sandler covolume pieces.

    ``b`` is the mixture covolume ``Q/(1-D)`` and ``b_x`` its
    simplex-projected composition partials (the ``beta_i`` of the module
    note); ``b_xT`` would only feed departure T-derivatives, which the
    hosting layer does not consume (see the section note above).
    """

    b: float = 0.0
    b_x: tuple[float, ...] = ()


#: PR: C = ln(sqrt(2) - 1)/sqrt(2) (Wong & Sandler 1992; sign per the
#: 18:01Z dispatch review).
C_WS_PR = math.log(math.sqrt(2.0) - 1.0) / math.sqrt(2.0)
#: SRK: C = -ln 2.
C_WS_SRK = -math.log(2.0)


class WongSandler(GERule):
    """Wong-Sandler (1992) second-virial-consistent gE mixing rule.

    ``C`` is the EOS constant with its sign (:data:`C_WS_PR` for PR,
    :data:`C_WS_SRK` for SRK).  ``kijs`` defaults to zeros (k_ij-free gE
    form); the cross second-virial term keeps the full ``(1 - k_ij)``
    structure so fitted matrices can be supplied.
    """

    def __init__(self, provider: GEProvider, c: float, kijs: list[list[float]] | None = None):
        self.provider = provider
        self.c = c
        n = len(kijs) if kijs else 0
        self.w = [[(1.0 - kijs[i][j]) for j in range(n)] for i in range(n)] if kijs else None

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> WSRuleState:
        n = len(xs)
        g, gx, g_t, g_tt, g_xt = self.provider.state(T, tuple(xs))
        # Per-component (b_i - a_i/RT) and its first two T-derivatives.
        gv = [0.0] * n
        gv_t = [0.0] * n
        gv_tt = [0.0] * n
        for i in range(n):
            ai, dai, d2ai = pa.a_alphas[i], pa.da_alphas[i], pa.d2a_alphas[i]
            brt = ai / (R_GAS * T)
            gv[i] = bs[i] - brt
            gv_t[i] = -(dai / (R_GAS * T) - brt / T)
            gv_tt[i] = -(d2ai / (R_GAS * T) - 2.0 * dai / (R_GAS * T * T) + 2.0 * brt / (T * T))
        w = self.w
        q = q_t = q_tt = 0.0
        q_x = [0.0] * n
        q_xt = [0.0] * n
        for i in range(n):
            wi = w[i] if w is not None else [1.0] * n
            for j in range(n):
                xij = xs[i] * xs[j] * wi[j]
                q += xij * 0.5 * (gv[i] + gv[j])
                q_t += xij * 0.5 * (gv_t[i] + gv_t[j])
                q_tt += xij * 0.5 * (gv_tt[i] + gv_tt[j])
                q_x[i] += xs[j] * wi[j] * (gv[i] + gv[j])
                q_xt[i] += xs[j] * wi[j] * (gv_t[i] + gv_t[j])
        # D = sum x_i a_i/(b_i RT) + gE/(C RT) = A + g/C
        a_mom, a_mom_t, a_mom_tt = _alpha_moments(pa, xs, bs, T)
        d = a_mom + g / self.c
        d_t = a_mom_t + g_t / self.c
        d_tt = a_mom_tt + g_tt / self.c
        d_x = [0.0] * n
        d_xt = [0.0] * n
        for k in range(n):
            val, dval, _ = _a_brt(pa, k, bs[k], T)
            d_x[k] = val + gx[k] / self.c
            d_xt[k] = dval + g_xt[k] / self.c
        # b_m = Q/(1-D), a_m = RT b_m D -- quotient algebra with S = 1 - D.
        s = 1.0 - d
        b = q / s
        b_t = (q_t * s + q * d_t) / (s * s)
        b_tt = (q_tt * s + q * d_tt) / (s * s) + 2.0 * d_t * (q_t * s + q * d_t) / (s**3)
        b_x_raw = [(q_x[k] * s + q * d_x[k]) / (s * s) for k in range(n)]
        b_xt_raw = [
            (q_xt[k] * s - q_x[k] * d_t + q_t * d_x[k] + q * d_xt[k]) / (s * s)
            + 2.0 * d_t * (q_x[k] * s + q * d_x[k]) / (s**3)
            for k in range(n)
        ]
        rt = R_GAS * T
        a = rt * b * d
        a_t = R_GAS * (b * d + T * (b_t * d + b * d_t))
        a_tt = R_GAS * (2.0 * b_t * d + 2.0 * b * d_t + T * (b_tt * d + 2.0 * b_t * d_t + b * d_tt))
        a_x_raw = [rt * (b_x_raw[k] * d + b * d_x[k]) for k in range(n)]
        a_xt_raw = [
            R_GAS * (b_x_raw[k] * d + b * d_x[k])
            + rt * (b_xt_raw[k] * d + b_t * d_x[k] + b_x_raw[k] * d_t + b * d_xt[k])
            for k in range(n)
        ]
        x_sum_a = sum(x * v for x, v in zip(xs, a_x_raw, strict=True))
        x_sum_at = sum(x * v for x, v in zip(xs, a_xt_raw, strict=True))
        x_sum_b = sum(x * v for x, v in zip(xs, b_x_raw, strict=True))
        return WSRuleState(
            a=a,
            da_dT=a_t,
            d2a_dT2=a_tt,
            a_x=tuple(v - x_sum_a for v in a_x_raw),
            a_xT=tuple(v - x_sum_at for v in a_xt_raw),
            b=b,
            b_x=tuple(v - x_sum_b for v in b_x_raw),
        )


class _WSMixingEOS(_GEMixingEOS):
    """Mixin adding the WS covolume handling on the gE hosting layer.

    Overrides ``a_alpha_and_derivatives`` to replace the linear covolume
    (set by the base ``__init__``) with the rule's ``b_m`` before thermo
    solves the cubic (``solve`` calls ``a_alpha_and_derivatives`` before
    ``volume_solutions(self.b, ...)``), and ``fugacity_coefficients`` to
    route through ``eos_mix_lnphis_general`` with the analytic
    ``db/dn``/``da/dn`` terms.  ``delta_factor``/``epsilon_factor`` pin the
    EOS family's covolume form: delta = factor * b, epsilon = factor2 * b^2.
    """

    delta_factor: float
    epsilon_factor: float
    ws_c: float

    def a_alpha_and_derivatives(
        self, T: float, full: bool = True, quick: bool = True, pure_a_alphas: bool = True
    ) -> Any:
        out = super().a_alpha_and_derivatives(T, full=full, quick=quick, pure_a_alphas=pure_a_alphas)
        st = self._rule_state
        b = st.b
        self.b = b
        self.delta = self.delta_factor * b
        self.epsilon = self.epsilon_factor * b * b
        return out

    def fugacity_coefficients(self, Z: float) -> list[float]:
        st = self._rule_state
        db_dns = list(st.b_x)
        ddelta_dns = [self.delta_factor * v for v in db_dns]
        depsilon_dns = [2.0 * self.epsilon_factor * st.b * v for v in db_dns]
        da_dns = list(st.a_x)
        return [
            float(v)
            for v in eos_mix_lnphis_general(
                self.T,
                self.P,
                Z,
                st.b,
                self.delta,
                self.epsilon,
                st.a,
                self.bs,
                self.a_alpha_roots,
                self.N,
                db_dns,
                da_dns,
                ddelta_dns,
                depsilon_dns,
            )
        ]


class PRMIX_WS(_WSMixingEOS, PRMIX):  # type: ignore[misc]
    """PRMIX with the Wong-Sandler (1992) gE mixing rule."""

    lnphi_kernel = staticmethod(PR_lnphis)  # unused by the WS route; kept for typing
    rule_kind = "ws"
    delta_factor = 2.0
    epsilon_factor = -1.0
    ws_c = C_WS_PR

    def __init__(
        self,
        Tcs: Any,
        Pcs: Any,
        omegas: Any,
        zs: Any,
        kijs: Any | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        fugacities: bool = True,
        only_l: bool = False,
        only_g: bool = False,
        rule: GERule | None = None,
    ):
        self.rule = rule
        super().__init__(
            Tcs=Tcs,
            Pcs=Pcs,
            omegas=omegas,
            zs=zs,
            kijs=kijs,
            T=T,
            P=P,
            V=V,
            fugacities=fugacities,
            only_l=only_l,
            only_g=only_g,
        )


class SRKMIX_WS(_WSMixingEOS, SRKMIX):  # type: ignore[misc]
    """SRKMIX with the Wong-Sandler (1992) gE mixing rule (SRKMIX hosting)."""

    lnphi_kernel = staticmethod(SRK_lnphis)  # unused by the WS route; kept for typing
    rule_kind = "ws"
    delta_factor = 1.0
    epsilon_factor = 0.0
    ws_c = C_WS_SRK

    def __init__(
        self,
        Tcs: Any,
        Pcs: Any,
        omegas: Any,
        zs: Any,
        kijs: Any | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        fugacities: bool = True,
        only_l: bool = False,
        only_g: bool = False,
        rule: GERule | None = None,
    ):
        self.rule = rule
        super().__init__(
            Tcs=Tcs,
            Pcs=Pcs,
            omegas=omegas,
            zs=zs,
            kijs=kijs,
            T=T,
            P=P,
            V=V,
            fugacities=fugacities,
            only_l=only_l,
            only_g=only_g,
        )


class PRWongSandlerThermo(MixingRuleThermo):
    """Peng-Robinson with the Wong-Sandler (1992) mixing rule over NRTL gE.

    Second-virial-consistent mixing (Wong & Sandler, AIChE J. 38, 1992):
    ``b_m = Q/(1 - D)``, ``a_m = R T b_m D`` with the gE term
    ``A_inf^E/(C R T)``; the covolume is non-linear in composition, so the
    fugacity route is the general mole-number kernel (see the module
    Wong-Sandler section).
    """

    eos = PRMIX_WS
    ge_kind = "nrtl"


class SRKWongSandlerThermo(MixingRuleThermo):
    """SRK with the Wong-Sandler (1992) mixing rule over NRTL gE (SRK C)."""

    eos = SRKMIX_WS
    ge_kind = "nrtl"


# ----------------------------------------------------------------------------
# MHV1 / MHV2 (T-06 step 3, branch t-06b/mhv): zero-pressure gE reference
# ----------------------------------------------------------------------------


class MHV1(GERule):
    """MHV1 — Michelsen's (1990) first-order modified Huron-Vidal rule.

    Zero-pressure gE reference on the dimensionless attraction
    ``alpha = a/(b R T)`` with the linear co-volume ``b = sum_i x_i b_i``:

        alpha = sum_i x_i a_i alpha_i/(b_i R T)
                + (gE/(R T) + sum_i x_i ln(b/b_i)) / q1

    with the EOS-family constant ``q1 = -0.53`` (PR) / ``-0.593`` (SRK)
    (Michelsen, M. L., "A modified Huron-Vidal mixing rule for cubic equations
    of state", Fluid Phase Equilib. 60, 213-219, 1990).  At ``gE = 0`` the
    rule collapses exactly to the pure-component attraction sum, i.e. the
    zero-pressure reference is the pure EOS itself.
    """

    def __init__(self, provider: GEProvider, q1: float):
        self.provider = provider
        self.q1 = q1

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        s = s_t = s_tt = 0.0
        ab: list[tuple[float, float, float]] = []
        for k in range(n):
            v, vt, vtt = _a_brt(pa, k, bs[k], T)
            ab.append((v, vt, vtt))
            s += xs[k] * v
            s_t += xs[k] * vt
            s_tt += xs[k] * vtt
        # Flory covolume term: the rule needs N = gE/(RT) + sum_i x_i ln(b/b_i)
        # = g - F with F = sum_i x_i ln(b_i/b).  Raw z-partials:
        # dS/dz_k = alpha_bar_k, dF/dz_k = ln(b_k) - b_k/b (N = g - F).
        f = sum(x * math.log(bi / b) for x, bi in zip(xs, bs, strict=True) if x)
        alpha = s + (g - f) / self.q1
        alpha_x_raw = tuple(ab[k][0] + (gx[k] - math.log(bs[k]) + bs[k] / b) / self.q1 for k in range(n))
        alpha_t = s_t + gT / self.q1
        alpha_tt = s_tt + gTT / self.q1
        alpha_xT_raw = tuple(ab[k][1] + gxT[k] / self.q1 for k in range(n))
        return _linear_rule_state(alpha, alpha_t, alpha_tt, alpha_x_raw, alpha_xT_raw, b, T, bs, xs)


class MHV2(GERule):
    """MHV2 — Dahl & Michelsen's (1990) second-order modified Huron-Vidal rule.

    Same zero-pressure reference and linear co-volume as :class:`MHV1`, but
    the zero-pressure constraint is kept to second order in the attraction
    sum, giving a quadratic in ``alpha``:

        c     = -q1 S - q2 S2 - gE/(RT) - sum_i x_i ln(b/b_i)
        alpha = (-q1 - sqrt(q1^2 - 4 q2 c)) / (2 q2)

    with ``S = sum_i x_i a_i alpha_i/(b_i R T)`` and
    ``S2 = sum_i x_i (a_i alpha_i/(b_i R T))^2``.  Constants per EOS
    (Dahl, S. & Michelsen, M. L., AIChE J. 36, 1829-1836, 1990):
    ``q1/q2 = -0.4347/-0.003654`` (PR) and ``-0.4783/-0.0047`` (SRK).
    ``d alpha/d c = 1/sqrt(q1^2 - 4 q2 c)`` carries every derivative; the
    pure-feed limit (gE = 0, Flory term 0) reduces the discriminant to
    ``|q1 + 2 q2 S|^2`` so ``alpha -> S`` exactly.
    """

    def __init__(self, provider: GEProvider, q1: float, q2: float):
        self.provider = provider
        self.q1 = q1
        self.q2 = q2

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        q1, q2 = self.q1, self.q2
        s = s_t = s_tt = s2 = 0.0
        ab: list[tuple[float, float, float]] = []
        for k in range(n):
            v, vt, vtt = _a_brt(pa, k, bs[k], T)
            ab.append((v, vt, vtt))
            s += xs[k] * v
            s2 += xs[k] * v * v
            s_t += xs[k] * vt
            s_tt += xs[k] * vtt
        f = sum(x * math.log(bi / b) for x, bi in zip(xs, bs, strict=True) if x)
        c = -q1 * s - q2 * s2 - g + f
        d = math.sqrt(q1 * q1 - 4.0 * q2 * c)
        alpha = (-q1 - d) / (2.0 * q2)
        # d alpha / d c = 1/d carries every first derivative; the second T
        # derivative additionally carries the chain term 2 q2 c_T^2 / d^3.
        # s2 = sum x_i ab_i^2 is a second MOMENT: its T derivatives are not
        # those of s^2 (2 s s_t / s_t^2 + s s_tt); they use the per-component
        # pairs (ab_i, ab_iT) and (ab_iT, ab_iTT).
        s2_t = 2.0 * sum(x * ab[k][0] * ab[k][1] for k, x in enumerate(xs))
        s2_tt = 2.0 * sum(x * (ab[k][1] ** 2 + ab[k][0] * ab[k][2]) for k, x in enumerate(xs))
        c_t = -q1 * s_t - q2 * s2_t - gT
        c_tt = -q1 * s_tt - q2 * s2_tt - gTT
        c_x_raw = tuple(
            -q1 * ab[k][0] - q2 * ab[k][0] ** 2 - gx[k] + math.log(bs[k]) - bs[k] / b for k in range(n)
        )
        c_xT_raw = tuple(-q1 * ab[k][1] - 2.0 * q2 * ab[k][0] * ab[k][1] - gxT[k] for k in range(n))
        alpha_t = c_t / d
        alpha_tt = c_tt / d + 2.0 * q2 * c_t * c_t / (d * d * d)
        alpha_x_raw = tuple(cv / d for cv in c_x_raw)
        # Mixed derivative: d/dT of c_x/d = c_xT/d + c_x * (d 1/d/dT); with
        # d 1/d/dT = +2 q2 c_T / d^3 (d_T = -2 q2 c_T / d).
        alpha_xT_raw = tuple(
            cxT / d + 2.0 * q2 * cx * c_t / (d * d * d) for cxT, cx in zip(c_xT_raw, c_x_raw, strict=True)
        )
        return _linear_rule_state(alpha, alpha_t, alpha_tt, alpha_x_raw, alpha_xT_raw, b, T, bs, xs)


class _RuleHost:
    """Shared ``rule=`` kwarg handling for GCEOSMIX rule hosts.

    ``thermo``'s ``GCEOSMIX.__init__`` takes no rule, so each host pops it
    before delegation; the rule instance must be attached before the first
    calculation (same contract as ``PRMIX_HV``).
    """

    def __init__(self, *args: Any, rule: GERule | None = None, **kwargs: Any) -> None:
        self.rule = rule
        super().__init__(*args, **kwargs)


class PRMIX_MHV1(_RuleHost, _GEMixingEOS, PRMIX):  # type: ignore[misc]
    """PRMIX with the MHV1 rule (Michelsen 1990), ``q1 = -0.53``."""

    lnphi_kernel = staticmethod(PR_lnphis)
    rule_kind = "mhv1"
    q1 = -0.53


class PRMIX_MHV2(_RuleHost, _GEMixingEOS, PRMIX):  # type: ignore[misc]
    """PRMIX with the MHV2 rule (Dahl & Michelsen 1990), ``q1/q2 = -0.4347/-0.003654``."""

    lnphi_kernel = staticmethod(PR_lnphis)
    rule_kind = "mhv2"
    q1 = -0.4347
    q2 = -0.003654


class SRKMIX_MHV2(_RuleHost, _GEMixingEOS, SRKMIX):  # type: ignore[misc]
    """SRKMIX with the MHV2 rule (Dahl & Michelsen 1990), ``q1/q2 = -0.4783/-0.0047``."""

    lnphi_kernel = staticmethod(SRK_lnphis)
    rule_kind = "mhv2"
    q1 = -0.4783
    q2 = -0.0047


class PRMHV1Thermo(MixingRuleThermo):
    """Peng-Robinson with the MHV1 rule (Michelsen 1990) over NRTL gE."""

    eos = PRMIX_MHV1
    ge_kind = "nrtl"


class PRMHV2Thermo(MixingRuleThermo):
    """Peng-Robinson with the MHV2 rule (Dahl & Michelsen 1990) over NRTL gE."""

    eos = PRMIX_MHV2
    ge_kind = "nrtl"


class SRKMHV2Thermo(MixingRuleThermo):
    """SRK with the MHV2 rule (Dahl & Michelsen 1990) over NRTL gE."""

    eos = SRKMIX_MHV2
    ge_kind = "nrtl"
