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
    PR_lnphis,
    SRKMIX,
    SRK_lnphis,
    TWUPRMIX,
    a_alpha_and_derivatives_quadratic_terms,
)
from thermo.heat_capacity import R as R_GAS

from ngdesign.thermo.cubic import (
    _CHEMSEP_CUBIC_TABLE,
    CubicEOS,
    _MC_SRK,
    _flasher_for,
    _flasher_vl_for,
    _mc_coeffs,
    SRKMIX_MC,
)
from ngdesign.thermo.gamma_phi import _ge_model_factory

__all__ = [
    "PRMIX_HV",
    "PRHuronVidalThermo",
    "MHV1Rule",
    "VTPRRule",
    "LCVMRule",
    "SRKMIX_PSRK",
    "PRMIX_VTPR",
    "PRMIX_LCVM",
    "SRKPSRKThermo",
    "PRVTPRThermo",
    "PRLCVMThermo",
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
    if kind.startswith("unifac"):
        # The gamma-phi adapter owns the UNIFAC group tables (one owner of the
        # group-assignment plumbing); variants: unifac (original), unifac_psrk
        # and unifac_vtpr, each a data/thermo_params/unifac/groups.yaml entry.
        return ThermoGEProvider(_ge_model_factory(kind, ids, cas_list, None))
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


def _rule_for(eos_cls: type, provider: GEProvider) -> GERule:
    kind = getattr(eos_cls, "rule_kind", None)
    if kind == "hv":
        return HuronVidal(provider, HuronVidal.M_PR)
    if kind == "psrk":
        return MHV1Rule(provider, MHV1Rule.Q1_SRK)
    if kind == "vtpr":
        return VTPRRule(provider)
    if kind == "lcvm":
        return LCVMRule(provider)
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
        mc_table = getattr(eos_cls, "mc_table", None)
        if mc_table is not None:
            # Mathias-Copeman alpha (T-02 table, Coquelet et al. 2004 fits):
            # components without a published fit fall back to the EOS default
            # alpha inside _mc_coeffs.
            eos_kwargs["alpha_coeffs"] = [
                _mc_coeffs(str(r.id), mc_table, om)
                for r, om in zip(records, constants.omegas, strict=True)
            ]
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
# T-06c: PSRK, VTPR, LCVM (self-contained block; see head note on issue #141)
# ----------------------------------------------------------------------------


class MHV1Rule(GERule):
    """MHV1 (Michelsen 1990; Dahl & Michelsen 1990), zero-pressure gE reference.

    ``alpha_m = A + (g + F)/q1`` with ``A = sum x_i a_i/(b_i R T)`` (the
    dimensionless pure-component moments) and ``F = sum x_i ln(b_i/b)`` the
    Michelsen covolume term (linear b).  ``q1`` is the signed per-EOS constant:
    ``q1 = -0.64663`` for SRK (Holderbaum & Gmehling 1991, PSRK); for a pure
    feed ``g = F = 0`` and the rule collapses exactly to the base cubic.
    """

    Q1_SRK = -0.64663  # SRK, Holderbaum & Gmehling (1991)
    Q1_PR = -0.62363  # PR, Dahl & Michelsen (1990)

    def __init__(self, provider: GEProvider, q1: float = Q1_SRK):
        self.provider = provider
        self.q1 = q1

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        A, A_T, A_TT = _alpha_moments(pa, xs, bs, T)
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        fl, fl_x = _flory(xs, b, bs)
        alpha_m = A + (g + fl) / self.q1
        alpha_x = tuple(
            _a_brt(pa, k, bs[k], T)[0] + (gx[k] + fl_x[k]) / self.q1 for k in range(n)
        )
        # F is T-independent (linear b).
        alpha_xT = tuple(_a_brt(pa, k, bs[k], T)[1] + gxT[k] / self.q1 for k in range(n))
        return _linear_rule_state(
            alpha_m, A_T + gT / self.q1, A_TT + gTT / self.q1, alpha_x, alpha_xT, b, T, bs, xs
        )


class VTPRRule(GERule):
    """VTPR mixing rule (Ahlers & Gmehling 2001): residual-gE reference.

    ``alpha_m = A - g_res/0.53087`` where the gE model supplies the *residual*
    part only - the VTPR UNIFAC variant (thermo version 3) omits the
    combinatorial contribution, matching the source form.  Declared deviations
    of the hosted form: linear covolume mixing (the paper's power-mean b
    combining) and thermo's generalised Twu alpha on the host class (the
    Ahlers-Gmehling fitted Twu table is not openly available).
    """

    A1_INV = 1.0 / 0.53087

    def __init__(self, provider: GEProvider):
        self.provider = provider

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        A, A_T, A_TT = _alpha_moments(pa, xs, bs, T)
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        alpha_m = A - g * self.A1_INV
        alpha_x = tuple(_a_brt(pa, k, bs[k], T)[0] - gx[k] * self.A1_INV for k in range(n))
        alpha_xT = tuple(_a_brt(pa, k, bs[k], T)[1] - gxT[k] * self.A1_INV for k in range(n))
        return _linear_rule_state(
            alpha_m, A_T - gT * self.A1_INV, A_TT - gTT * self.A1_INV, alpha_x, alpha_xT, b, T, bs, xs
        )


class LCVMRule(GERule):
    """LCVM (Boukouvalas et al. 1994): linear combination of the Vidal and
    MHV1 references.

    ``alpha_m = (1 - lambda)(A - g/m_V) + lambda(A + (g + F)/q1)`` with
    ``lambda = 0.36``, the PR Vidal constant ``m_V = ln(sqrt(2) - 1)`` (the
    merged HV row's constant) and the PR MHV1 constant ``q1 = -0.62363``.
    The original Boukouvalas weighting is kept: 64 % Vidal / 36 % Michelsen.
    """

    LAMBDA = 0.36
    M_V = HuronVidal.M_PR

    def __init__(self, provider: GEProvider, lam: float = LAMBDA):
        self.provider = provider
        self.lam = lam

    def state(self, T: float, xs: tuple[float, ...], pa: PureAlpha, bs: tuple[float, ...]) -> RuleState:
        n = len(xs)
        g, gx, gT, gTT, gxT = self.provider.state(T, tuple(xs))
        A, A_T, A_TT = _alpha_moments(pa, xs, bs, T)
        b = sum(x * bi for x, bi in zip(xs, bs, strict=True))
        fl, fl_x = _flory(xs, b, bs)
        c_v = (1.0 - self.lam) / self.M_V
        c_m = self.lam / MHV1Rule.Q1_PR
        alpha_m = A - c_v * g + c_m * (g + fl)
        alpha_x = tuple(
            _a_brt(pa, k, bs[k], T)[0] - c_v * gx[k] + c_m * (gx[k] + fl_x[k]) for k in range(n)
        )
        alpha_xT = tuple(
            _a_brt(pa, k, bs[k], T)[1] - c_v * gxT[k] + c_m * gxT[k] for k in range(n)
        )
        return _linear_rule_state(
            alpha_m,
            A_T - c_v * gT + c_m * gT,
            A_TT - c_v * gTT + c_m * gTT,
            alpha_x,
            alpha_xT,
            b,
            T,
            bs,
            xs,
        )


class SRKMIX_PSRK(_GEMixingEOS, SRKMIX_MC):  # type: ignore[misc]
    """SRKMIX with the PSRK rule (MHV1 over PSRK-UNIFAC) and the T-02
    Mathias-Copeman alpha (the published PSRK alpha treatment for polar
    components; components without a published fit keep the EOS default)."""

    lnphi_kernel = staticmethod(SRK_lnphis)
    rule_kind = "psrk"
    mc_table = _MC_SRK

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
        alpha_coeffs: list[list[float]] | None = None,
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
            alpha_coeffs=alpha_coeffs or [],
        )


class PRMIX_VTPR(_GEMixingEOS, TWUPRMIX):  # type: ignore[misc]
    """PRMIX with the VTPR rule (Ahlers & Gmehling 2001) over VTPR-UNIFAC.

    The host carries thermo's generalised Twu alpha (TWUPRMIX); the fitted
    Ahlers-Gmehling Twu table and the paper's Peneloux volume translation are
    declared deviations (the latter changes liquid density only, not VLE).
    """

    lnphi_kernel = staticmethod(PR_lnphis)
    rule_kind = "vtpr"

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


class PRMIX_LCVM(_GEMixingEOS, PRMIX):  # type: ignore[misc]
    """PRMIX with the LCVM rule (Boukouvalas et al. 1994) over original UNIFAC."""

    lnphi_kernel = staticmethod(PR_lnphis)
    rule_kind = "lcvm"

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


class SRKPSRKThermo(MixingRuleThermo):
    """PSRK (Holderbaum & Gmehling 1991): SRK + Mathias-Copeman alpha + MHV1
    (q1 = -0.64663) over PSRK-UNIFAC (thermo PSRKSG/PSRKIP)."""

    eos = SRKMIX_PSRK
    ge_kind = "unifac_psrk"


class PRVTPRThermo(MixingRuleThermo):
    """VTPR (Ahlers & Gmehling 2001): Twu-alpha PR host with the residual-gE
    rule over VTPR-UNIFAC (thermo VTPRSG/VTPRIP, no combinatorial term)."""

    eos = PRMIX_VTPR
    ge_kind = "unifac_vtpr"


class PRLCVMThermo(MixingRuleThermo):
    """LCVM (Boukouvalas et al. 1994): PR + linear Vidal/MHV1 combination
    (lambda = 0.36) over original UNIFAC."""

    eos = PRMIX_LCVM
    ge_kind = "unifac"
