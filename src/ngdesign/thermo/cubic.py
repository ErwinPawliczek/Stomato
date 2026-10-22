"""One cubic-EOS base; PR, SRK and PR78 become registrations (spec P0-04).

:class:`CubicEOS` implements the ``Thermo`` protocol (plugin kind "thermo")
over Caleb Bell's `thermo` library: a FlashVLN flasher with two liquid phases
(free water forms a separate aqueous phase), CEOSGas / CEOSLiquid phase
wrappers, and a Michelsen-style stability re-check for single-phase results.
It is parameterised by the `thermo`-library mixture EOS class (``PRMIX``,
``SRKMIX``, ``PR78MIX``) and the k_ij source used today — the embedded
'ChemSep PR' IPDB table, 0 where the table has no pair. Component ids resolve
through the open component registry (spec P1-02): constants build in
:mod:`ngdesign.thermo._state` from the resolved Component records, so any
curated id, databank CAS/name or registered pseudo-components flash here.

The contract-v2 surface (flashes, saturation, K-values, single-phase
properties, derivatives, property cache) lives in
:class:`ThermoSurfaceMixin` (spec P1-01) and is shared with the NRTL package.
SI units throughout: K, Pa, kg/m3, Pa.s, J/mol, J/(mol K).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable
from functools import cache
from itertools import pairwise
from typing import Any, cast

from thermo.eos_mix import (
    APISRKMIX,
    PRMIX,
    PRSV2MIX,
    PRSVMIX,
    RKMIX,
    SRKMIX,
    TWUPRMIX,
    TWUSRKMIX,
    VDWMIX,
    PRMIXTranslated,
    SRKMIXTranslated,
)
from thermo.phases import CEOSGas, CEOSLiquid

from ngdesign.contracts import StreamState
from ngdesign.contracts.components import ComponentSet, data_definitions
from ngdesign.contracts.thermo import PhaseProps, PropertyDerivatives, SaturationPoint
from ngdesign.data import PseudoDefinition as DataPseudoDefinition
from ngdesign.thermo import _state
from ngdesign.thermo.options import (
    CUBIC_OPTION_DEFAULTS,
    AlphaFunction,
    CubicOptionValues,
    EnthalpyMethod,
    MixingRule,
    SourTerm,
    VolumeTranslation,
)

#: The IPDB's fitted cubic-EOS kijs (no SRK/PR78-specific table exists in thermo).
_CHEMSEP_CUBIC_TABLE = "ChemSep PR"


class ThermoSurfaceMixin:
    """The Thermo-protocol v2 surface shared by every property package (spec P1-01).

    Implements the flashes, saturation points, K-values, single-phase
    properties, derivatives and the property cache on top of two
    package-provided flasher factories: ``_build_flasher`` (the full three-phase
    FlashVLN flasher) and ``_build_flasher_vl`` (the FlashVL fast path the
    saturation solvers use when the feed cannot form a second liquid).

    The cache is a per-instance LRU of PROPERTY_CACHE_SIZE entries keyed on
    (tag, composition rounded to 1e-10, T to 1e-6, P to 1e-3) for PT flashes and
    phase_props; molar_flow is part of the PT-flash key because StreamState
    carries it. StreamState and Phase are frozen models, so a cached object
    can be handed to every caller without copying.
    """

    def __init__(self) -> None:
        self._lru_cache: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
        # The solving slate's flowsheet-owned pseudo definitions (spec P1-07),
        # set once per solve through set_component_set. Empty = no flowsheet
        # context: pseudo ids resolve through the module register_pseudo default.
        self._slate_pseudos: tuple[DataPseudoDefinition, ...] = ()
        super().__init__()

    def set_component_set(self, cs: ComponentSet) -> None:
        """Receive the slate resolved once at solve entry (spec P1-07).

        The solver hands over the ComponentSet it built from
        ``Flowsheet.components``; flasher and Psat constants for
        flowsheet-owned pseudo-components then build from the flowsheet's own
        definitions, never from the module-level register_pseudo default. The
        solver calls this once per solve, before any flash.
        """
        self._slate_pseudos = data_definitions(cs.pseudo_definitions)

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        """The package's full FlashVLN flasher over this sorted component support."""
        raise NotImplementedError

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        """The package's two-phase FlashVL flasher over this sorted component support."""
        raise NotImplementedError

    def _flasher(self, z: dict[str, float]) -> Any:
        return self._build_flasher(_state.support_ids(z))

    def _sat_flasher(self, ids: tuple[str, ...]) -> Any:
        """FlashVL fast path when no second liquid can exist (no water in the feed)."""
        if _state.WATER_ID in ids:
            return self._build_flasher(ids)
        return self._build_flasher_vl(ids)

    def _cached(self, key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
        # The slate's flowsheet-owned pseudo definitions (spec P1-07) scope every
        # per-instance result cache entry: pseudo constants change with the
        # solving slate, so a cached flash or phase-prop result from one
        # flowsheet must never satisfy another's request for the same (z, T, P).
        cache = self._lru_cache
        key = (self._slate_pseudos, *key)
        hit = cache.get(key)
        if hit is not None:
            cache.move_to_end(key)
            return hit
        value = compute()
        cache[key] = value
        while len(cache) > _state.PROPERTY_CACHE_SIZE:
            cache.popitem(last=False)
        return value

    # -- flashes ------------------------------------------------------------

    def flash_pt(self, z: dict[str, float], T: float, P: float, molar_flow: float) -> StreamState:
        """PT flash: full phase split at temperature T (K) and pressure P (Pa abs)."""
        key = ("pt", *_state.cache_key(z, T, P), round(molar_flow, 9))
        return cast(
            StreamState,
            self._cached(key, lambda: _state.run_flash(self._flasher(z), z, molar_flow, T=T, P=P)),
        )

    def flash_ph(self, z: dict[str, float], P: float, H: float, molar_flow: float) -> StreamState:
        """PH flash: solve T from pressure P (Pa abs) and enthalpy H (J/mol)."""
        return _state.run_flash(self._flasher(z), z, molar_flow, P=P, H=H)

    def flash_ps(self, z: dict[str, float], P: float, S: float, molar_flow: float) -> StreamState:
        """PS flash: solve T from pressure P (Pa abs) and entropy S (J/(mol K))."""
        return _state.run_flash(self._flasher(z), z, molar_flow, P=P, S=S)

    def flash_tvf(self, z: dict[str, float], T: float, vf: float, molar_flow: float) -> StreamState:
        """TVF flash: vapour fraction vf in [0, 1] at temperature T (K)."""
        return _state.flash_tvf(self, z, T, vf, molar_flow)

    def flash_pvf(self, z: dict[str, float], P: float, vf: float, molar_flow: float) -> StreamState:
        """PVF flash: vapour fraction vf in [0, 1] at pressure P (Pa abs)."""
        return _state.flash_pvf(self, z, P, vf, molar_flow)

    # -- saturation ----------------------------------------------------------

    def bubble_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Bubble point; exactly one of T (K) and P (Pa) given."""
        return _state.bubble_point(
            self._sat_flasher(_state.support_ids(z)), z, T=T, P=P, pseudos=self._slate_pseudos
        )

    def dew_point(
        self, z: dict[str, float], *, T: float | None = None, P: float | None = None
    ) -> SaturationPoint:
        """Dew point; exactly one of T (K) and P (Pa) given."""
        return _state.dew_point(
            self._sat_flasher(_state.support_ids(z)), z, T=T, P=P, pseudos=self._slate_pseudos
        )

    def pure_psat(self, cid: str, T: float) -> float | None:
        """Pure-component vapour pressure (Pa) at T (K); None at or above Tc."""
        return _state.pure_psat(cid, T, self._slate_pseudos)

    # -- properties -----------------------------------------------------------

    def k_values(self, z: dict[str, float], T: float, P: float) -> dict[str, float] | None:
        """K_i = y_i/x_i from a PT flash; None when single-phase."""
        return _state.k_values(self._flasher(z), z, T, P)

    def phase_props(self, composition: dict[str, float], T: float, P: float, kind: Any) -> PhaseProps:
        """Single-phase properties at (composition, T, P) — no flash."""
        key = ("pp", str(kind), *_state.cache_key(composition, T, P))
        return cast(
            PhaseProps,
            self._cached(
                key, lambda: _state.phase_props(self._flasher(composition), composition, T, P, kind)
            ),
        )

    def derivatives(
        self, composition: dict[str, float], T: float, P: float, kind: Any
    ) -> PropertyDerivatives:
        """d ln phi / dT and d ln phi / dP per component, for one phase."""
        return _state.derivatives(self._flasher(composition), composition, T, P, kind)


class CubicEOS(ThermoSurfaceMixin):
    """Cubic-EOS Thermo package; subclasses pin the EOS class as ``eos``."""

    #: `thermo`-library mixture EOS class (PRMIX, SRKMIX, PR78MIX).
    eos: Any

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        return _flasher_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        return _flasher_vl_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos)


@cache
def _flasher_for(
    eos: Any,
    kij_table: str,
    ids: tuple[str, ...],
    pseudos: tuple[DataPseudoDefinition, ...] = (),
    configure: Callable[[list[Any], Any, list[list[float]]], tuple[Any, dict[str, Any], Any, Any]]
    | None = None,
) -> Any:
    """Build (and cache) a FlashVLN flasher over exactly this sorted component set.

    Zero-fraction components are dropped by the caller before this is reached, so
    the cache key is the reduced, sorted support of the feed composition (plus the
    EOS class and k_ij table, which pin the package variant, plus the slate's
    flowsheet-owned pseudo definitions - spec P1-07: two flowsheets with
    different definitions of the same pseudo id never share a flasher).
    The T-02 ``configure`` hook (stable per (eos, options) pair) keeps two rows
    with different option values on distinct flasher instances.
    """
    return _state.build_flasher(ids, eos, kij_table, pseudos, configure)


@cache
def _flasher_vl_for(
    eos: Any,
    kij_table: str,
    ids: tuple[str, ...],
    pseudos: tuple[DataPseudoDefinition, ...] = (),
    configure: Callable[[list[Any], Any, list[list[float]]], tuple[Any, dict[str, Any], Any, Any]]
    | None = None,
) -> Any:
    """Build (and cache) the two-phase FlashVL saturation fast path (spec P1-01).

    Cache key carries the slate's flowsheet-owned pseudo definitions (spec P1-07)
    and the T-02 ``configure`` hook, like the full flasher.
    """
    return _state.build_flasher_vl(ids, eos, kij_table, pseudos, configure)


# ---------------------------------------------------------------------------
# T-02: cubic option implementations
# ---------------------------------------------------------------------------
# The option objects live in ngdesign.thermo.options; this section holds the
# physics each non-default value selects, the per-component parameter tables
# the alpha functions need, and ``configure_options`` -- the single hook
# ``_state.build_flasher`` calls for non-default options so the default pr /
# srk / pr78 construction path stays byte-identical.
#
# Parameter provenance:
# - Mathias-Copeman coefficients: Coquelet, Chapoy & Richon, "Review of the
#   alpha function..." (Ind. Eng. Chem. Res. 43 (2004) 7359; open-access 2004
#   comparative study), Table II (PR and SRK fits). The table's "Sulfur
#   dioxide" row carries H2S critical properties (Tc 373.53 K, Pc 8.94 MPa)
#   and omega 0.0942, so it is keyed as H2S here.
# - Boston-Mathias supercritical form: alpha = exp[Cd(1 - Tr^d)], d = 1 + m/2,
#   Cd = m/d^2 (Boston & Mathias 1980; as documented in the Clapeyron.jl and
#   IDAES cubic-EOS references), subcritical branch identical to the EOS
#   default Soave form.
# - Kabadi-Danner: a''_j = G_j a_w [1 - (T/Tcw)^0.8], mixed with weight
#   x_w x_j^2; group contributions g_CH4 = 1.3580, g_CH3 = 0.9822,
#   g_CH2 = 1.0780 (Kabadi & Danner, Ind. Eng. Chem. Process Des. Dev. 24
#   (1985) 537); G_i by group sum (methane 1.3580, ethane 1.9644,
#   propane 3.0424, n-butane 4.1202 = 1.3580 + 0.9822 + 2*1.0780 - ... by
#   groups; paraffins larger than propane reuse the CH2 sum). Components
#   outside the published paraffinic groups carry no a'' term.
# - Lee-Kesler constants: Lee & Kesler, AIChE J. 21 (1975) 510, Table II
#   (simple fluid omega_r = 0, reference fluid omega_r = 0.3978).
# - Sour-water ionisation: Wilson/API Publication 955 speciation framework;
#   constants held at 298.15 K literature values (documented deviation).

#: Temperature-independent ionisation pK values at 298.15 K (documented
#: deviation: the API-955 temperature correlations could not be re-verified
#: this session, so no invented temperature form is used).
_SOUR_PK_H2S = 7.00  # H2S -> HS- (pKa1)
_SOUR_PK_CO2 = 6.35  # CO2 -> HCO3- (pKa1)
_SOUR_PK_NH3 = 9.25  # NH4+ -> NH3
_SOUR_PK_W = 14.00

_R = 8.31446261815324  # J/(mol K), CODATA 2018 - shared by KD and LK terms

_MC_SRK: dict[str, tuple[float, float, float]] = {
    "H2": (0.161, -0.225, -0.232),
    "C1": (0.549, -0.409, 0.603),
    "N2": (0.584, -0.396, 0.736),
    "H2S": (0.641, -0.183, 0.513),
    "C2": (0.711, -0.573, 0.894),
    "C3": (0.775, -0.476, 0.815),
    "IC4": (0.807, -0.432, 0.910),
    "NC4": (0.823, -0.267, 0.402),
    "IC5": (0.876, -0.386, 0.660),
    "NC5": (0.901, -0.305, 0.542),
    "CO2": (0.867, -0.674, 2.471),
    "NC6": (1.005, -0.591, 1.203),
    "H2O": (1.095, -0.678, 0.700),
}

_MC_PR: dict[str, tuple[float, float, float]] = {
    "H2": (0.0948721, -0.275148, -0.0293089),
    "C1": (0.415742, -0.172651, 0.348424),
    "N2": (0.448322, -0.156813, 0.468652),
    "H2S": (0.507354, 0.0075766, 0.342291),
    "C2": (0.531245, -0.0618124, 0.214238),
    "C3": (0.600066, -0.0063038, 0.173899),
    "IC4": (0.652444, -0.149356, 0.599234),
    "NC4": (0.677341, -0.0810913, 0.298538),
    "IC5": (0.723543, -0.166075, 0.514866),
    "NC5": (0.762864, -0.224305, 0.669507),
    "CO2": (0.704606, -0.314862, 1.89083),
    "NC6": (0.870257, -0.587964, 1.50392),
    "H2O": (0.919263, -0.332035, 0.317204),
}

#: Twu-Sim-Tassone (2002) fitted Twu-form alpha coefficients [L, M, N] for the
#: normal paraffins the paper publishes; other components fall back to the
#: generalised Twu form (thermo's TwuPR95 constants).
_TST_LMN: dict[str, tuple[float, float, float]] = {
    "C1": (0.573159, 0.982462, 0.600000),
    "C2": (0.602469, 0.900708, 0.726375),
    "C3": (0.856729, 0.937274, 0.617916),
    "NC4": (0.512768, 0.846110, 1.03032),
    "NC5": (0.379003, 0.817571, 1.37301),
    "NC6": (0.116525, 0.861045, 3.24960),
}

#: Kabadi-Danner group contributions (g_CH4, g_CH3, g_CH2) and the group
#: makeup of each published paraffin; G_i = sum of group contributions.
_KD_G: dict[str, float] = {
    "C1": 1.3580,
    "C2": 1.9644,
    "C3": 3.0424,
    "NC4": 4.1204,  # g_CH4 + g_CH3 + 2 g_CH2 - 1 (paraffin group sum)
    "NC5": 5.1984,
    "NC6": 6.2764,
}


def _mc_coeffs(cid: str, table: dict[str, tuple[float, float, float]], omega: float) -> list[float]:
    """Mathias-Copeman coefficients in the mixin's [c3, c2, c1, 1] order.

    Components without published fits fall back to the EOS default alpha:
    c1 = kappa(omega), c2 = c3 = 0 makes the MC polynomial exactly the Soave
    form, so a missing entry degrades gracefully instead of inventing data.
    """
    c1, c2, c3 = table.get(cid, (float("nan"),) * 3)
    if math.isnan(c1):
        if table is _MC_PR:
            c1 = omega * (-0.26992 * omega + 1.54226) + 0.37464
        else:
            c1 = omega * (-0.176 * omega + 1.574) + 0.480
        c2 = c3 = 0.0
    return [c3, c2, c1, 1.0]


class BostonMathias_a_alpha:
    """Boston-Mathias (1980) supercritical alpha, shared by PR and SRK mixes.

    Subcritical (Tr <= 1) the alpha is the EOS default Soave form built from
    the instance's own ``kappas``; supercritical it is
    ``exp[Cd (1 - Tr^d)]`` with ``d = 1 + m/2`` and ``Cd = m/d^2`` -- positive,
    monotonically decreasing, and value-continuous at Tr = 1 where the Soave
    bracket crosses zero at high Tr.

    Mixed into thermo EOS mixes (untyped), which provide these attributes.
    """

    N: int
    Tcs: list[float]
    ais: list[float]
    kappas: list[float]
    ms: list[float]

    def _bm_eval(self, T: float) -> tuple[list[float], list[float], list[float]]:
        a_alphas, das, d2as = [], [], []
        kappas = getattr(self, "kappas", None)
        if kappas is None:  # SRK mixes store the Soave m as ``ms``
            kappas = self.ms
        for i in range(self.N):
            Tc, a, m = self.Tcs[i], self.ais[i], kappas[i]
            rt = math.sqrt(T / Tc)
            if T <= Tc:
                x0 = 1.0 + m * (1.0 - rt)
                a_alpha = x0 * x0 * a
                da = -a * (rt * x0 * m / T)
                d2 = a * m * rt * (x0 + m * rt) / (2.0 * T * T)
            else:
                d = 1.0 + m / 2.0
                cd = m / (d * d)
                e = math.exp(cd * (1.0 - (T / Tc) ** d))
                a_alpha = e * a
                da = -a * e * cd * d * (T / Tc) ** (d - 1.0) / Tc
                d2 = (
                    a
                    * e
                    * (
                        (cd * d * (T / Tc) ** (d - 1.0) / Tc) ** 2
                        - cd * d * (d - 1.0) * (T / Tc) ** (d - 2.0) / (Tc * Tc)
                    )
                )
            a_alphas.append(a_alpha)
            das.append(da)
            d2as.append(d2)
        return a_alphas, das, d2as

    def a_alphas_vectorized(self, T: float) -> Any:
        return self._bm_eval(T)[0]

    def a_alpha_and_derivatives_vectorized(self, T: float) -> Any:
        return self._bm_eval(T)

    def a_alpha_pure(self, T: float) -> Any:
        return self._bm_eval(T)[0][0]

    def a_alpha_and_derivatives_pure(self, T: float) -> Any:
        vals = self._bm_eval(T)
        return vals[0][0], vals[1][0], vals[2][0]


class MC_a_alpha:
    """Mathias-Copeman (1983) polynomial alpha from ``self.alpha_coeffs``.

    Coefficient order is the thermo mixin's ``[c3, c2, c1, 1.0]``; the
    supercritical branch uses the published c1-only form.

    Mixed into thermo EOS mixes (untyped), which provide these attributes.
    """

    N: int
    Tcs: list[float]
    ais: list[float]
    alpha_coeffs: list[list[float]]

    def _mc_eval(self, T: float) -> tuple[list[float], list[float], list[float]]:
        a_alphas, das, d2as = [], [], []
        for i in range(self.N):
            Tc, a = self.Tcs[i], self.ais[i]
            rt = math.sqrt(T / Tc)
            tau = 1.0 - rt
            c3, c2, c1, _ = self.alpha_coeffs[i]
            if T < Tc:
                x0 = c3 * tau**3 + c2 * tau * tau + c1 * tau + 1.0
                x1 = 3.0 * c3 * tau * tau + 2.0 * c2 * tau + c1
                x2 = 6.0 * c3 * tau + 2.0 * c2
                a_alpha = x0 * x0 * a
                da = -a * (rt * x0 * x1 / T)
                d2 = a * (rt * rt * (x1 * x1 + x0 * x2) + rt * x0 * x1) / (2.0 * T * T)
            else:
                x = 1.0 + c1 * tau
                a_alpha = x * x * a
                da = -a * rt * x * c1 / T
                d2 = a * c1 * rt * (1.0 + c1) / (2.0 * T * T)
            a_alphas.append(a_alpha)
            das.append(da)
            d2as.append(d2)
        return a_alphas, das, d2as

    def a_alphas_vectorized(self, T: float) -> Any:
        return self._mc_eval(T)[0]

    def a_alpha_and_derivatives_vectorized(self, T: float) -> Any:
        return self._mc_eval(T)

    def a_alpha_pure(self, T: float) -> Any:
        return self._mc_eval(T)[0][0]

    def a_alpha_and_derivatives_pure(self, T: float) -> Any:
        vals = self._mc_eval(T)
        return vals[0][0], vals[1][0], vals[2][0]


class TST_a_alpha:
    """Twu-form alpha ``Tr^(N(M-1)) exp[L (1 - Tr^(NM))]`` from ``alpha_coeffs``.

    A ``None`` entry selects the generalised Twu form for that component:
    ``alpha = alpha0 + omega (alpha1 - alpha0)`` with the generalised triplets
    (subcritical: L 0.125283 / 0.511614, M 0.911807 / 0.784054, N 1.948150 /
    2.812520; supercritical per thermo's TwuPR95_a_alpha), matching the
    library's omega-interpolated alpha rather than a single fitted triplet.

    Mixed into thermo EOS mixes (untyped), which provide these attributes.
    """

    N: int
    Tcs: list[float]
    ais: list[float]
    omegas: list[float]
    alpha_coeffs: list[list[float] | None]

    def _tst_eval(self, T: float) -> tuple[list[float], list[float], list[float]]:
        a_alphas, das, d2as = [], [], []
        for i in range(self.N):
            Tc, a = self.Tcs[i], self.ais[i]
            tr = T / Tc
            coeffs = self.alpha_coeffs[i]
            if coeffs is not None:
                al, dal, d2al = _twu_triplet(coeffs[0], coeffs[1], coeffs[2], tr)
                a_alphas.append(a * al)
                das.append(a * dal / Tc)
                d2as.append(a * d2al / (Tc * Tc))
            else:
                trips = _TWU_GEN_SUB if tr < 1.0 else _TWU_GEN_SUP
                al0, dal0, d2al0 = _twu_triplet(*trips[0], tr)
                al1, dal1, d2al1 = _twu_triplet(*trips[1], tr)
                w = self.omegas[i]
                a_alphas.append(a * (al0 + w * (al1 - al0)))
                das.append(a * (dal0 + w * (dal1 - dal0)) / Tc)
                d2as.append(a * (d2al0 + w * (d2al1 - d2al0)) / (Tc * Tc))
        return a_alphas, das, d2as

    def a_alphas_vectorized(self, T: float) -> Any:
        return self._tst_eval(T)[0]

    def a_alpha_and_derivatives_vectorized(self, T: float) -> Any:
        return self._tst_eval(T)

    def a_alpha_pure(self, T: float) -> Any:
        return self._tst_eval(T)[0][0]

    def a_alpha_and_derivatives_pure(self, T: float) -> Any:
        vals = self._tst_eval(T)
        return vals[0][0], vals[1][0], vals[2][0]


class PRMIX_BM(BostonMathias_a_alpha, PRMIX):  # type: ignore[misc]
    """PRMIX with the Boston-Mathias supercritical alpha."""


class SRKMIX_BM(BostonMathias_a_alpha, SRKMIX):  # type: ignore[misc]
    """SRKMIX with the Boston-Mathias supercritical alpha."""


class _AlphaCoeffsInit:
    """Stores ``alpha_coeffs`` before the EOS init solves with them."""

    def __init__(
        self,
        Tcs: list[float],
        Pcs: list[float],
        omegas: list[float],
        zs: list[float],
        alpha_coeffs: list[list[float] | None] | None = None,
        kijs: list[list[float]] | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        **kw: Any,
    ) -> None:
        self.alpha_coeffs = alpha_coeffs
        super().__init__(Tcs=Tcs, Pcs=Pcs, omegas=omegas, zs=zs, kijs=kijs, T=T, P=P, V=V, **kw)  # type: ignore[call-arg]


class PRMIX_MC(_AlphaCoeffsInit, MC_a_alpha, PRMIX):  # type: ignore[misc]
    """PRMIX with the Mathias-Copeman alpha (alpha_coeffs in eos_kwargs)."""


class SRKMIX_MC(_AlphaCoeffsInit, MC_a_alpha, SRKMIX):  # type: ignore[misc]
    """SRKMIX with the Mathias-Copeman alpha (alpha_coeffs in eos_kwargs)."""


class TSTMIX(_AlphaCoeffsInit, TST_a_alpha, PRMIX):  # type: ignore[misc]
    """The Twu-Sim-Tassone (2002) cubic: PR-family attraction with c1 = 0.470507,
    b = 0.0740740 RTc/Pc and the ``v^2 + 2.5 b v - 1.5 b^2`` denominator."""

    c1 = 0.470507
    c2 = 0.0740740
    c1R2_c2R = c1 * 8.31446261815324 * 8.31446261815324
    c2R = c2 * 8.31446261815324

    def __init__(
        self,
        Tcs: list[float],
        Pcs: list[float],
        omegas: list[float],
        zs: list[float],
        alpha_coeffs: list[list[float] | None] | None = None,
        kijs: list[list[float]] | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(
            Tcs=Tcs,
            Pcs=Pcs,
            omegas=omegas,
            zs=zs,
            alpha_coeffs=alpha_coeffs,
            kijs=kijs,
            T=T,
            P=P,
            V=V,
            **kw,
        )
        # PR's init solved with PR's delta/epsilon; re-pin the TST repulsive
        # term and re-solve the roots at the requested state.
        self.delta = 2.5 * self.b
        self.epsilon = -1.5 * self.b * self.b
        if T is not None and P is not None:
            self.solve(only_l=True, only_g=True)


_TWU_GEN_SUB = ((0.125283, 0.911807, 1.948150), (0.511614, 0.784054, 2.812520))
_TWU_GEN_SUP = ((0.401219, 4.963070, -0.2), (0.024955, 1.248089, -8.0))


def _twu_triplet(L: float, M: float, N: float, tr: float) -> tuple[float, float, float]:
    """Raw Twu alpha and its first two Tr derivatives (d/ Tr, not ln)."""
    al = tr ** (N * (M - 1.0)) * math.exp(L * (1.0 - tr ** (N * M)))
    dal = al * (N * (M - 1.0) / tr - L * N * M * tr ** (N * M - 1.0))
    d2al = al * (
        (N * (M - 1.0) / tr - L * N * M * tr ** (N * M - 1.0)) ** 2
        - N * (M - 1.0) / (tr * tr)
        - L * N * M * (N * M - 1.0) * tr ** (N * M - 2.0)
    )
    return al, dal, d2al


def _tst_coeffs(cid: str, omega: float) -> list[float] | None:
    """TST fitted [L, M, N] where published; None selects the generalised form."""
    fitted = _TST_LMN.get(cid)
    if fitted is not None:
        return list(fitted)
    return None


class SRKMIXKD(SRKMIX):  # type: ignore[misc]
    """SRK with the Kabadi-Danner (1985) water-hydrocarbon mixing rule.

    Adds ``x_w x_j^2 a''_j(T)`` to the mixed a_alpha,
    ``a''_j = G_j a_w (T) [1 - (T/Tcw)^0.8]`` with ``a_w`` the RK-SRK pure
    attractive term of water. Components outside the published paraffinic
    groups have no a'' term. ``fugacity_coefficients`` gains the a''-term's
    composition derivative so ln phi_i stays thermodynamically consistent
    with the modified mixing rule.
    """

    _water_i: int = -1
    _a_prime: dict[int, float] = {}  # component index -> G_j (0 = no term)

    def __init__(
        self,
        Tcs: list[float],
        Pcs: list[float],
        omegas: list[float],
        zs: list[float],
        kd_water_index: int = -1,
        kd_groups: dict[int, float] | None = None,
        kijs: list[list[float]] | None = None,
        T: float | None = None,
        P: float | None = None,
        V: float | None = None,
        **kw: Any,
    ) -> None:
        self._water_i = kd_water_index
        self._a_prime = kd_groups if kd_groups is not None else {}
        super().__init__(Tcs=Tcs, Pcs=Pcs, omegas=omegas, zs=zs, kijs=kijs, T=T, P=P, V=V, **kw)

    def _a_prime_values(self, T: float) -> list[float]:
        cids = _cids_from_criticals(self)
        iw = cids.index("H2O") if "H2O" in cids else -1
        Tcw = self.Tcs[iw]
        aw = self.ais[iw] * math.sqrt(Tcw / T)  # SRK pure a_alpha of water
        out = []
        for cid in cids:
            g = _KD_G.get(cid, 0.0)
            out.append(g * aw * (1.0 - (T / Tcw) ** 0.8) if g else 0.0)
        return out

    def a_alpha_and_derivatives(
        self, T: float, full: bool = True, quick: bool = True, pure_a_alphas: bool = True
    ) -> Any:
        vals = super().a_alpha_and_derivatives(T, full=full, quick=quick, pure_a_alphas=pure_a_alphas)
        cids = _cids_from_criticals(self)
        iw = cids.index("H2O") if "H2O" in cids else -1
        xw = self.zs[iw] if 0 <= iw < self.N else 0.0
        if xw <= 0.0:
            return vals
        aps = self._a_prime_values(T)
        # a_KD = xw * sum_j x_j^2 a''_j; T derivatives from the same factors.
        a_kd = xw * sum(x * x * ap for x, ap in zip(self.zs, aps, strict=True))
        h = 1e-4
        a_kd_p = xw * sum(x * x * p for x, p in zip(self.zs, self._a_prime_values(T + h), strict=True))
        a_kd_m = xw * sum(x * x * p for x, p in zip(self.zs, self._a_prime_values(T - h), strict=True))
        da_kd = (a_kd_p - a_kd_m) / (2.0 * h)
        d2a_kd = (a_kd_p - 2.0 * a_kd + a_kd_m) / (h * h)
        a_mix, da_mix, d2a_mix = vals
        return (a_mix + a_kd, da_mix + da_kd, d2a_mix + d2a_kd)

    def fugacity_coefficients(self, Z: float) -> Any:
        """SRK lnphis with the Kabadi-Danner mixing-rule correction applied.

        ``solve`` ran with the corrected ``a_alpha`` (base rows plus
        ``x_w sum_j x_j^2 a''_j``), so the base formula's attractive
        denominator and ``A`` are already the KD values; the only missing
        piece is the a''-term's composition derivative ``d(n a'')/dn_i / n``
        inside the bracket, which the standard SRK rule does not have.
        """
        lnphis = super().fugacity_coefficients(Z)
        cids = _cids_from_criticals(self)
        iw = cids.index("H2O") if "H2O" in cids else -1
        zs = self.zs
        if not (0 <= iw < self.N) or zs[iw] <= 0.0:
            return lnphis
        xw = zs[iw]
        aps = self._a_prime_values(self.T)
        S = sum(x * x * ap for x, ap in zip(zs, aps, strict=True))
        # A/B = a_alpha/(R T b); A tracks the KD-corrected a_alpha, so a_alpha
        # cancels and the correction collapses to -ln(1 + B/Z)/(R T b).
        big_b = self.b * self.P / (_R * self.T)
        corr = -math.log(1.0 + big_b / Z) / (_R * self.T * self.b)
        for i in range(self.N):
            if i == iw:
                kd_i = (1.0 - xw) * S + 2.0 * xw * xw * aps[i]
            else:
                kd_i = xw * (2.0 * zs[i] * aps[i] - S)
            lnphis[i] += corr * kd_i
        return lnphis


_ZJ_CONSTANTS: dict[str, tuple[float, float]] = {}  # cid -> (a_c, b)


@cache
def _zj_alpha(cid: str, T: float) -> float:
    """Zudkevitch-Joffe (1970) alpha: pure-RK fugacity equality at Psat.

    Solves alpha so the RK saturation pressure at T equals the databank Psat
    (``ln phi_l == ln phi_v`` at ``(T, Psat)``): raising alpha raises the EOS
    saturation pressure, so g crosses from negative to positive. Falls back to
    the RK ``sqrt(Tc/T)`` form at/above Tc or when no two-root sign change
    brackets the root (near-critical). Cached per (component, T) -- the
    databank Psat underneath is cached too.
    """
    psat = _state.pure_psat(cid, T)
    Tc, Pc = _ZJ_COMPONENT_CRITICALS[cid]
    a_c, b = _ZJ_CONSTANTS[cid]
    if psat is None or T >= Tc:
        return math.sqrt(Tc / T)

    def g(alpha: float) -> float | None:
        pair = _rk_pure_lnphis(alpha, a_c, b, T, psat)
        if pair is None:
            return None
        return pair[0] - pair[1]

    # Inside the two-root window g runs positive->negative as alpha rises (the
    # EOS saturation pressure crosses the databank Psat from below to above);
    # single-root alphas are unfittable and skipped. Bisect that crossing.
    xs = [0.2 * 1.15**i for i in range(45)]
    prev: tuple[float, float] | None = None
    lo = hi = 0.0
    for x in xs:
        gx = g(x)
        if gx is None:
            continue
        if prev is not None and prev[1] > 0.0 > gx:
            lo, hi = prev[0], x
            break
        prev = (x, gx)
    else:
        return math.sqrt(Tc / T)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if gm is None:
            break  # unreachable inside a two-root bracket; keep the best estimate
        if gm > 0.0:
            lo = mid
        elif gm < 0.0:
            hi = mid
        else:
            return mid
    return 0.5 * (lo + hi)


_ZJ_COMPONENT_CRITICALS: dict[str, tuple[float, float]] = {}

#: Reverse of the option criticals tables: (Tc, Pc) -> component id. thermo
#: clones EOS instances per flash state (``to_TP_zs_fast``) with an attribute
#: whitelist, so per-instance ids/indices do not survive a re-solve; (Tc, Pc)
#: pairs are copied verbatim and identify the component exactly.
_CID_BY_CRITICALS: dict[tuple[float, float], str] = {}


def _cids_from_criticals(eos: Any) -> list[str]:
    """Per-component ids of an option EOS instance, recovered from (Tc, Pc)."""
    try:
        return [_CID_BY_CRITICALS[(tc, pc)] for tc, pc in zip(eos.Tcs, eos.Pcs, strict=True)]
    except KeyError as exc:  # a slate component configure never registered
        raise KeyError(f"option EOS component with (Tc, Pc)={exc.args[0]} is not registered") from exc


def _rk_pure_lnphis(alpha: float, a_c: float, b: float, T: float, P: float) -> tuple[float, float] | None:
    """(ln phi_liquid, ln phi_vapour) of a pure RK fluid at (T, P); None when one root.

    RK: ``P = RT/(v-b) - a(T)/(v (v+b))`` with the T-folded attraction
    ``a(T) = a_c alpha(T)`` (``a_c = 0.42748 R^2 Tc^2/Pc``, ``alpha =
    sqrt(Tc/T)`` -- the ``1/sqrt(T)`` is already inside ``alpha``);
    ``A = a(T) P/(R^2 T^2)``, ``B = b P/(RT)``; Z-roots of the RK/SRK cubic
    ``Z^3 - Z^2 + (A - B - B^2) Z - A B = 0``; ``ln phi = Z - 1 - ln(Z - B) -
    (A/B) ln(1 + B/Z)``.
    """
    R = 8.31446261815324
    A = a_c * alpha * P / (R * R * T * T)
    B = b * P / (R * T)
    if B <= 0.0 or A <= 0.0:
        return None

    def f(z: float) -> float:
        return z**3 - z * z + (A - B - B * B) * z - A * B

    roots: list[float] = []
    # Dense edge grid: the RK cubic below Tc has three real roots (liquid,
    # middle, vapour); a coarse grid can leave two of them inside one interval
    # with no endpoint sign change.
    edges = (1e-12, 1e-6, 1e-4, 1e-3, 3e-3, 0.01, 0.03, 0.1, 0.3, 0.7, 1.0, 1e3)
    for z0, z1 in pairwise(edges):
        f0, f1 = f(z0), f(z1)
        if f0 == 0.0:
            roots.append(z0)
        elif f0 * f1 < 0.0:
            lo, hi = z0, z1
            for _ in range(120):
                mid = 0.5 * (lo + hi)
                if f(lo) * f(mid) <= 0.0:
                    hi = mid
                else:
                    lo = mid
            roots.append(0.5 * (lo + hi))
    if len(roots) < 2:
        return None
    roots.sort()
    z_l, z_v = roots[0], roots[-1]
    if z_l <= B:
        return None

    def lnphi(z: float) -> float:
        return z - 1.0 - math.log(z - B) - (A / B) * math.log(1.0 + B / z)

    return lnphi(z_l), lnphi(z_v)


class ZJRKMIX(RKMIX):  # type: ignore[misc]
    """Redlich-Kwong with the Zudkevitch-Joffe (1970) Psat-fitted alpha.

    ``Omega_a(T)`` per component solves the pure-fugacity equality at the
    databank vapour pressure. Documented deviation: the published fit's
    temperature-dependent ``Omega_b`` is not implemented -- it would require
    overriding the repulsive-term matrix inside thermo's EOSMIX machinery;
    ``Omega_b`` stays at the RK constant. At/above Tc the RK alpha applies.
    Components are identified from their (Tc, Pc) pairs, so the fitted ids
    survive thermo's EOS state clones (see :func:`_cids_from_criticals`).
    """

    def _zj_eval(self, T: float) -> tuple[list[float], list[float], list[float]]:
        a_alphas, das, d2as = [], [], []
        h = 1e-4
        for i, cid in enumerate(_cids_from_criticals(self)):
            a = self.ais[i]
            a0 = _zj_alpha(cid, T)
            am = _zj_alpha(cid, T - h)
            ap = _zj_alpha(cid, T + h)
            da = (ap - am) / (2.0 * h)
            d2 = (ap - 2.0 * a0 + am) / (h * h)
            a_alphas.append(a * a0)
            das.append(a * da)
            d2as.append(a * d2)
        return a_alphas, das, d2as

    def a_alphas_vectorized(self, T: float) -> Any:
        return self._zj_eval(T)[0]

    def a_alpha_and_derivatives_vectorized(self, T: float) -> Any:
        return self._zj_eval(T)

    def a_alpha_pure(self, T: float) -> Any:
        return self._zj_eval(T)[0][0]

    def a_alpha_and_derivatives_pure(self, T: float) -> Any:
        vals = self._zj_eval(T)
        return vals[0][0], vals[1][0], vals[2][0]


# -- Lee-Kesler enthalpy departures (EnthalpyMethod.LEE_KESLER) ---------------

_LK_SIMPLE = {
    "b1": 0.1181193,
    "b2": 0.265728,
    "b3": 0.154790,
    "b4": 0.030323,
    "c1": 0.0236744,
    "c2": 0.0186984,
    "c3": 0.0,
    "c4": 0.042724,
    "d1": 0.155428e-4,
    "d2": 0.623689e-4,
    "beta": 0.65392,
    "gamma": 0.060167,
}
_LK_REFERENCE = {
    "b1": 0.2026579,
    "b2": 0.331511,
    "b3": 0.027655,
    "b4": 0.203488,
    "c1": 0.0313385,
    "c2": 0.0503618,
    "c3": 0.016901,
    "c4": 0.041577,
    "d1": 0.487360e-4,
    "d2": 0.740336e-5,
    "beta": 1.226,
    "gamma": 0.03754,
}
_LK_OMEGA_REF = 0.3978
_LK_R = _R


def _lk_solve_vr(Tr: float, Pr: float, p: dict[str, float], gas: bool) -> float | None:
    """Reduced volume Vr solving the Lee-Kesler EOS; gas (rightmost) or liquid root."""

    def f(vr: float) -> float:
        B = p["b1"] - p["b2"] / Tr - p["b3"] / (Tr * Tr) - p["b4"] / Tr**3
        C = p["c1"] - p["c2"] / Tr + p["c3"] / Tr**3
        D = p["d1"] + p["d2"] / Tr
        E = (
            p["c4"]
            / (Tr**3 * vr * vr)
            * (p["beta"] + p["gamma"] / (vr * vr))
            * math.exp(-p["gamma"] / (vr * vr))
        )
        return Pr * vr / Tr - (1.0 + B / vr + C / (vr * vr) + D / vr**5 + E)

    # Lee & Kesler (1975): the vapour root is the largest positive solution, the
    # liquid root the smallest. At low Tr the liquid-root region can be narrower
    # than a coarse scan step -- a positive island between two negative ends
    # (the 0.25-decade scan walked straight over the compressed-liquid root and
    # handed the vapour root to the liquid) -- so bracket on a dense log scan.
    lo0, hi0, steps = 1e-6, 1e6, 2000
    step = (math.log10(hi0) - math.log10(lo0)) / steps
    brackets = []
    v_prev, f_prev = lo0, f(lo0)
    for i in range(1, steps + 1):
        v = 10.0 ** (math.log10(lo0) + i * step)
        fv = f(v)
        if f_prev * fv <= 0.0:
            brackets.append((v_prev, v))
        v_prev, f_prev = v, fv
    if not brackets:
        return None
    lo, hi = brackets[0] if not gas else brackets[-1]
    for _ in range(120):
        mid = 0.5 * (lo + hi)
        if f(lo) * f(mid) <= 0.0:
            hi = mid
        else:
            lo = mid
    return float(0.5 * (lo + hi))


def _lk_hdep_fluid(Tr: float, Pr: float, p: dict[str, float], gas: bool) -> float | None:
    """Residual enthalpy/(R Tc) of one Lee-Kesler corresponding-states fluid."""
    vr = _lk_solve_vr(Tr, Pr, p, gas)
    if vr is None:
        return None
    z = Pr * vr / Tr
    b_d = p["b2"] / (Tr * Tr) + 2.0 * p["b3"] / Tr**3 + 3.0 * p["b4"] / Tr**4
    c_d = p["c2"] / (Tr * Tr) - 3.0 * p["c3"] / Tr**4
    d_d = -p["d2"] / (Tr * Tr)
    e = math.exp(-p["gamma"] / (vr * vr))
    quad = b_d / vr + c_d / (2.0 * vr * vr) + d_d / (5.0 * vr**4)
    exp_part = p["beta"] * (1.0 - e) / (2.0 * p["gamma"]) + (1.0 - e * (1.0 + p["gamma"] / (vr * vr))) / (
        2.0 * p["gamma"]
    )
    return Tr * (z - 1.0) - Tr * Tr * quad + 3.0 * p["c4"] / (Tr * Tr) * exp_part


def _lee_kesler_H_dep(
    T: float, P: float, Tcs: list[float], Pcs: list[float], omegas: list[float], zs: list[float], gas: bool
) -> float:
    """Lee-Kesler (1975) enthalpy departure (J/mol) with Kay mixing rules.

    H_dep = RTcm [H0 + (omega_m/omega_r)(Hr - H0)]; enthalpy only -- the flash
    (K-values, phase split, density) stays the selected cubic EOS's.
    """
    Tcm = sum(y * tc for y, tc in zip(zs, Tcs, strict=True))
    Pcm = sum(y * pc for y, pc in zip(zs, Pcs, strict=True))
    om = sum(y * w for y, w in zip(zs, omegas, strict=True))
    Tr, Pr = T / Tcm, P / Pcm
    h0 = _lk_hdep_fluid(Tr, Pr, _LK_SIMPLE, gas)
    hr = _lk_hdep_fluid(Tr, Pr, _LK_REFERENCE, gas)
    if h0 is None or hr is None:
        return float("nan")
    return float(_LK_R * Tcm * (h0 + om / _LK_OMEGA_REF * (hr - h0)))


class LKCEOSGas(CEOSGas):  # type: ignore[misc]
    """CEOSGas whose enthalpy departure comes from Lee-Kesler (1975)."""

    def H_dep(self) -> float:
        return _lee_kesler_H_dep(
            self.T, self.P, self.eos_mix.Tcs, self.eos_mix.Pcs, self.eos_mix.omegas, self.zs, gas=True
        )

    def Cp(self) -> float:
        """Cp as the T-derivative of the full enthalpy, matching the LK departure.

        The LK departure is a corresponding-states correlation, so its T-slope
        is not the cubic EOS's Cp; the secant over +/-0.5 K of the same H chain
        keeps H and Cp thermodynamically consistent.
        """
        d_t = 0.5
        return (
            float(self.to(T=self.T + d_t, P=self.P, zs=self.zs).H())
            - float(self.to(T=self.T - d_t, P=self.P, zs=self.zs).H())
        ) / (2.0 * d_t)


class LKCEOSLiquid(CEOSLiquid):  # type: ignore[misc]
    """CEOSLiquid whose enthalpy departure comes from Lee-Kesler (1975)."""

    def H_dep(self) -> float:
        return _lee_kesler_H_dep(
            self.T, self.P, self.eos_mix.Tcs, self.eos_mix.Pcs, self.eos_mix.omegas, self.zs, gas=False
        )

    def Cp(self) -> float:
        """Cp as the T-derivative of the full enthalpy; see LKCEOSGas.Cp."""
        d_t = 0.5
        return (
            float(self.to(T=self.T + d_t, P=self.P, zs=self.zs).H())
            - float(self.to(T=self.T - d_t, P=self.P, zs=self.zs).H())
        ) / (2.0 * d_t)


# -- Sour-water ionisation correction (SourTerm.SOUR) ------------------------


def _sour_molecular_fractions(
    zs: list[float], water_index: int, ionising: tuple[tuple[int, float], ...]
) -> list[float]:
    """Molecular (un-ionised) fractions given total fractions and pK values.

    ``ionising`` maps component index -> pKa at 298.15 K: H2S/CO2 as acids
    (pKa1) and NH3 via its conjugate-acid pKa. Electroneutrality gives
    ``[H+]``:  H+ + NH4+ = OH- + HS- + HCO3-; each acid's ionised fraction is
    Ka/([H+] + Ka), the base's is [H+]/([H+] + Ka). Concentrations are taken
    molar over the aqueous medium (55.5084 mol/L pure water).
    """
    kw = 10.0**-_SOUR_PK_W
    xw = max(zs[water_index], 1e-12)
    c_mol = [z / xw * 55.5084 for z in zs]  # mol/L over water

    def charge(h: float) -> float:
        """Electroneutrality residual: H+ + NH4+ - (OH- + HS- + HCO3-)."""
        positive = h
        negative = kw / h
        for idx, pk in ionising:
            ka = 10.0**-pk
            if pk == _SOUR_PK_NH3:  # base: NH4+ carries positive charge
                positive += c_mol[idx] * h / (h + ka)
            else:  # acid: the ionised fraction carries negative charge
                negative += c_mol[idx] * ka / (h + ka)
        return float(positive - negative)

    lo, hi = 1e-14, 1.0
    for _ in range(200):
        h = math.sqrt(lo * hi)
        if charge(h) > 0.0:
            hi = h
        else:
            lo = h
    h = math.sqrt(lo * hi)
    out = list(zs)
    for idx, pk in ionising:
        ka = 10.0**-pk
        alpha = h / (h + ka) if pk == _SOUR_PK_NH3 else ka / (h + ka)
        out[idx] = zs[idx] * (1.0 - alpha)
    return out


class SourCEOSLiquid(CEOSLiquid):  # type: ignore[misc]
    """Aqueous liquid with the Wilson/API-955 ionisation apparent-fugacity correction.

    On water-rich roots (x_w > 0.5) the ionising species' ln phi gains
    ``ln(x_mol/x_total)`` so the apparent fugacity over the TOTAL (analytical)
    loading reproduces the sour-water volatility the API 955 model defines.
    Off the aqueous root and for non-ionising mixtures this is exactly the
    base EOS liquid.
    """

    sour_ionising: tuple[tuple[int, float], ...] = ()
    sour_water_index: int = -1

    def lnphis(self) -> Any:
        base = super().lnphis()
        iw = self.sour_water_index
        if iw < 0 or not self.sour_ionising or self.zs[iw] <= 0.5:
            return base
        xmol = _sour_molecular_fractions(list(self.zs), iw, self.sour_ionising)
        return [
            b + math.log(xm / x) if x > 1e-300 else b for b, xm, x in zip(base, xmol, self.zs, strict=True)
        ]


# -- option wiring -----------------------------------------------------------


def configure_options(
    options: CubicOptionValues,
    eos: Any,
    records: list[Any],
    constants: Any,
    kijs: list[list[float]],
    pseudos: tuple[Any, ...] = (),
) -> tuple[Any, dict[str, Any], Any, Any]:
    """Assemble the option-adjusted (eos, eos_kwargs, gas_cls, liquid_cls) set.

    The row's adapter already pins the option classes (the catalogue validates
    ``options.eos`` against ``adapter.eos.__name__``); this hook adds the
    per-slate parameters the option classes need and the option-specific phase
    classes. Called by ``_state.build_flasher``/``build_flasher_vl`` only for
    non-default options, so the default rows' construction path is untouched.
    """
    ids = [r.id for r in records]
    eos_kwargs: dict[str, Any] = {
        "Tcs": constants.Tcs,
        "Pcs": constants.Pcs,
        "omegas": constants.omegas,
        "kijs": kijs,
    }
    gas_cls, liquid_cls = CEOSGas, CEOSLiquid

    if options.alpha == AlphaFunction.MATHIAS_COPEMAN:
        table = _MC_PR if getattr(eos, "__name__", "").startswith("PR") else _MC_SRK
        eos_kwargs["alpha_coeffs"] = [
            _mc_coeffs(cid, table, om) for cid, om in zip(ids, constants.omegas, strict=True)
        ]
    elif options.alpha == AlphaFunction.TWU_SIM_TASSONE:
        eos_kwargs["alpha_coeffs"] = [
            _tst_coeffs(cid, om) for cid, om in zip(ids, constants.omegas, strict=True)
        ]
    elif options.alpha == AlphaFunction.ZUDKEVITCH_JOFFE:
        for cid, tc, pc in zip(ids, constants.Tcs, constants.Pcs, strict=True):
            _ZJ_COMPONENT_CRITICALS[cid] = (tc, pc)
            _CID_BY_CRITICALS[(tc, pc)] = cid
            _ZJ_CONSTANTS[cid] = (
                0.4274802327 * _LK_R**2 * tc * tc / pc,
                0.0866403500 * _LK_R * tc / pc,
            )

    if options.translation == VolumeTranslation.PENELOUX:
        # The constant volume shift c from the Rackett (1970) Z_RA, with the
        # EOS-family correlation: SRK uses Peneloux, Rauzy & Freze (1982); PR
        # uses Jhaveri & Youngren (1988) -- PR over-predicts liquid density, so
        # its shift acts opposite to SRK's.
        if getattr(eos, "__name__", "").startswith("PR"):
            eos_kwargs["cs"] = [
                0.50033 * _LK_R * tc / pc * (0.25969 - (0.29056 - 0.08775 * om))
                for tc, pc, om in zip(constants.Tcs, constants.Pcs, constants.omegas, strict=True)
            ]
        else:
            eos_kwargs["cs"] = [
                0.40768 * _LK_R * tc / pc * (0.29441 - (0.29056 - 0.08775 * om))
                for tc, pc, om in zip(constants.Tcs, constants.Pcs, constants.omegas, strict=True)
            ]

    if options.mixing == MixingRule.KABADI_DANNER:
        for cid, tc, pc in zip(ids, constants.Tcs, constants.Pcs, strict=True):
            _CID_BY_CRITICALS[(tc, pc)] = cid
        groups = {i: _KD_G[cid] for i, cid in enumerate(ids) if cid in _KD_G}
        eos_kwargs["kd_water_index"] = ids.index("H2O") if "H2O" in ids else -1
        eos_kwargs["kd_groups"] = groups

    if options.enthalpy == EnthalpyMethod.LEE_KESLER:
        gas_cls, liquid_cls = LKCEOSGas, LKCEOSLiquid

    if options.sour == SourTerm.SOUR:
        ionising = []
        for i, cid in enumerate(ids):
            if cid == "H2S":
                ionising.append((i, _SOUR_PK_H2S))
            elif cid == "CO2":
                ionising.append((i, _SOUR_PK_CO2))
            elif cid == "NH3":
                ionising.append((i, _SOUR_PK_NH3))
        liquid_cls = type(
            "SourCEOSLiquidConfigured",
            (SourCEOSLiquid,),
            {
                "sour_ionising": tuple(ionising),
                "sour_water_index": ids.index("H2O") if "H2O" in ids else -1,
            },
        )

    return eos, eos_kwargs, gas_cls, liquid_cls


# -- option-aware adapter and the T-02 row adapters (spec T-02) ---------------


@cache
def _option_configure(
    eos: Any, options: CubicOptionValues
) -> Callable[[list[Any], Any, list[list[float]]], tuple[Any, dict[str, Any], Any, Any]]:
    """The flasher-builder hook for one (EOS class, option value) pair.

    Cached on (eos, options) so the closure handed to ``_flasher_for`` is a
    stable cache key: two rows with different option values never share a
    flasher instance, and a row never rebuilds one per flash.
    """

    def configure(
        records: list[Any], constants: Any, kijs: list[list[float]]
    ) -> tuple[Any, dict[str, Any], Any, Any]:
        return configure_options(options, eos, records, constants, kijs)

    return configure


class OptionCubicEOS(CubicEOS):
    """Cubic-EOS package over an option-adjusted EOS class (spec T-02).

    Row adapters pin the option-adjusted `thermo`-library EOS class as ``eos``
    and their catalogue-declared option values as ``options``; the flasher
    factories carry both, so the builder can add the option parameters
    (alpha coefficients, translation shifts, sour/LK phase classes) and two
    rows with different options never share a flasher.
    """

    options: CubicOptionValues = CUBIC_OPTION_DEFAULTS

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        configure = None if self.options.is_default else _option_configure(self.eos, self.options)
        return _flasher_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos, configure)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        configure = None if self.options.is_default else _option_configure(self.eos, self.options)
        return _flasher_vl_for(self.eos, _CHEMSEP_CUBIC_TABLE, ids, self._slate_pseudos, configure)


class RedlichKwongThermo(OptionCubicEOS):
    """Redlich-Kwong (Redlich & Kwong 1949) over `thermo`'s RKMIX."""

    eos = RKMIX


class VanDerWaalsThermo(OptionCubicEOS):
    """van der Waals (1873) over `thermo`'s VDWMIX."""

    eos = VDWMIX


class PrsvThermo(OptionCubicEOS):
    """PRSVMIX: PR with the PRSV temperature-specific alpha (Twu et al. 1991)."""

    eos = PRSVMIX


class Prsv2Thermo(OptionCubicEOS):
    """PRSV2MIX: PR with the PRSV2 three-parameter alpha (per-component fits)."""

    eos = PRSV2MIX


class TwuPengRobinsonThermo(OptionCubicEOS):
    """PRMIX with the generalised Twu (1995) three-parameter alpha."""

    eos = TWUPRMIX
    options = CubicOptionValues(alpha=AlphaFunction.TWU)


class TwuSrkThermo(OptionCubicEOS):
    """SRKMIX with the generalised Twu (1995) three-parameter alpha."""

    eos = TWUSRKMIX
    options = CubicOptionValues(alpha=AlphaFunction.TWU)


class ApiSrkThermo(OptionCubicEOS):
    """API SRK (API 14D / the API RP-14D form) over `thermo`'s APISRKMIX."""

    eos = APISRKMIX


class PrBostonMathiasThermo(OptionCubicEOS):
    """PRMIX with the Boston-Mathias (1980) supercritical alpha."""

    eos = PRMIX_BM
    options = CubicOptionValues(alpha=AlphaFunction.BOSTON_MATHIAS)


class SrkBostonMathiasThermo(OptionCubicEOS):
    """SRKMIX with the Boston-Mathias (1980) supercritical alpha."""

    eos = SRKMIX_BM
    options = CubicOptionValues(alpha=AlphaFunction.BOSTON_MATHIAS)


class PrMathiasCopemanThermo(OptionCubicEOS):
    """PRMIX with the Mathias-Copeman (1983) alpha (Coquelet et al. 2004 fits)."""

    eos = PRMIX_MC
    options = CubicOptionValues(alpha=AlphaFunction.MATHIAS_COPEMAN)


class SrkMathiasCopemanThermo(OptionCubicEOS):
    """SRKMIX with the Mathias-Copeman (1983) alpha (Coquelet et al. 2004 fits)."""

    eos = SRKMIX_MC
    options = CubicOptionValues(alpha=AlphaFunction.MATHIAS_COPEMAN)


class PrPenelouxThermo(OptionCubicEOS):
    """PRMIXTranslated with the Jhaveri & Youngren (1988) Rackett-derived shift."""

    eos = PRMIXTranslated
    options = CubicOptionValues(translation=VolumeTranslation.PENELOUX)


class SrkPenelouxThermo(OptionCubicEOS):
    """SRKMIXTranslated with the Peneloux, Rauzy & Freze (1982) Rackett-derived shift."""

    eos = SRKMIXTranslated
    options = CubicOptionValues(translation=VolumeTranslation.PENELOUX)


class SourPrThermo(OptionCubicEOS):
    """PRMIX with the Wilson/API-955 sour-water ionisation correction."""

    eos = PRMIX
    options = CubicOptionValues(sour=SourTerm.SOUR)


class SourSrkThermo(OptionCubicEOS):
    """SRKMIX with the Wilson/API-955 sour-water ionisation correction."""

    eos = SRKMIX
    options = CubicOptionValues(sour=SourTerm.SOUR)


class KabadiDannerSrkThermo(OptionCubicEOS):
    """SRK with the Kabadi-Danner (1985) water-hydrocarbon mixing rule."""

    eos = SRKMIXKD
    options = CubicOptionValues(mixing=MixingRule.KABADI_DANNER)


class ZudkevitchJoffeRkThermo(OptionCubicEOS):
    """RK with the Zudkevitch-Joffe (1970) Psat-fitted alpha."""

    eos = ZJRKMIX
    options = CubicOptionValues(alpha=AlphaFunction.ZUDKEVITCH_JOFFE)


_TST_REFUSAL = (
    "Twu-Sim-Tassone row: the TST liquid-volume form and its mixture fugacity expressions "
    "are not implemented (TSTMIX subclasses PRMIX and would predict liquid volumes wrong "
    "by an order of magnitude). The row is experimental: it refuses at first use and runs "
    "no validation cases (PR #161 review; issue #136)."
)


class TwuSimTassoneThermo(OptionCubicEOS):
    """Twu-Sim-Tassone cubic (EXPERIMENTAL: builds, refuses at first use).

    TSTMIX reproduces the paper's alpha form but not its distinct EOS volume
    form, so the row cannot be validated; it stays in the catalogue as
    ``experimental`` and raises :class:`NotImplementedError` on any flash.
    """

    eos = TSTMIX
    options = CubicOptionValues(alpha=AlphaFunction.TWU_SIM_TASSONE)

    def _build_flasher(self, ids: tuple[str, ...]) -> Any:
        raise NotImplementedError(_TST_REFUSAL)

    def _build_flasher_vl(self, ids: tuple[str, ...]) -> Any:
        raise NotImplementedError(_TST_REFUSAL)


class PrBmThermo(OptionCubicEOS):
    """Databank-variant PR-BM row: same physics as PrBostonMathiasThermo."""

    eos = PRMIX_BM
    options = CubicOptionValues(alpha=AlphaFunction.BOSTON_MATHIAS)


class RksBmThermo(OptionCubicEOS):
    """Databank-variant RKS-BM row: same physics as SrkBostonMathiasThermo."""

    eos = SRKMIX_BM
    options = CubicOptionValues(alpha=AlphaFunction.BOSTON_MATHIAS)


class PrLeeKeslerThermo(OptionCubicEOS):
    """PRMIX VLE with Lee-Kesler (1975) enthalpy departures."""

    eos = PRMIX
    options = CubicOptionValues(enthalpy=EnthalpyMethod.LEE_KESLER)


class SrkLeeKeslerThermo(OptionCubicEOS):
    """SRKMIX VLE with Lee-Kesler (1975) enthalpy departures."""

    eos = SRKMIX
    options = CubicOptionValues(enthalpy=EnthalpyMethod.LEE_KESLER)
